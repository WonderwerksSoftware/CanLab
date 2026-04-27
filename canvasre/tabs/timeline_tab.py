"""
TIMELINE tab — Logic-analyzer-style stacked signal view.

Each selected byte/signal gets one row in a stacked pyqtgraph layout.
A shared vertical playhead moves on mouse click; clicking a timestamp
highlights the matching row in the FRAMES tab (via state.id_selected).
"""
import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QSplitter, QAbstractItemView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from theme import COLORS, mono_font
from core.state import get_state

BYTE_COLS = [f"B{i}" for i in range(8)]
MAX_ROWS  = 8    # max signal rows shown at once


class TimelineTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._state      = get_state()
        self._plots: list[pg.PlotItem]      = []
        self._curves: list[pg.PlotDataItem] = []
        self._playhead_lines: list[pg.InfiniteLine] = []
        self._build_ui()
        self._state.frames_loaded.connect(self._on_frames_loaded)
        self._state.dbc_updated.connect(self._on_frames_loaded)

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left panel: signal selector ───────────────────────────────────────
        left  = QWidget()
        ll    = QVBoxLayout(left)
        ll.setContentsMargins(4, 4, 4, 4)
        ll.addWidget(QLabel("SELECT SIGNALS  (up to 8)", font=mono_font(8)))

        self.sig_list = QListWidget()
        self.sig_list.setFont(mono_font(8))
        self.sig_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        ll.addWidget(self.sig_list)

        self.btn_plot = QPushButton("▶  Plot Selected")
        self.btn_plot.setObjectName("btn_green")
        self.btn_plot.clicked.connect(self._plot_selected)
        ll.addWidget(self.btn_plot)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self._clear_plots)
        ll.addWidget(self.btn_clear)

        self.lbl_status = QLabel("Load frames to begin.", font=mono_font(8))
        self.lbl_status.setStyleSheet(f"color:{COLORS['dim']}")
        ll.addWidget(self.lbl_status)

        splitter.addWidget(left)

        # ── Right panel: stacked pyqtgraph rows ───────────────────────────────
        right = QWidget()
        rl    = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        self.glw = pg.GraphicsLayoutWidget()
        self.glw.setBackground(COLORS["bg"])
        rl.addWidget(self.glw)

        splitter.addWidget(right)
        splitter.setSizes([220, 900])
        outer.addWidget(splitter)

    # ── Signal list population ────────────────────────────────────────────────

    def _on_frames_loaded(self, *_):
        df     = self._state.frames_df
        sigs   = self._state.dbc_signals
        self.sig_list.clear()

        # Raw byte items per ID
        for can_id in sorted(df["ID"].unique() if not df.empty else []):
            for col in BYTE_COLS:
                item = QListWidgetItem(f"0x{can_id}  {col}")
                item.setData(Qt.ItemDataRole.UserRole, ("raw", can_id, col))
                item.setFont(mono_font(8))
                self.sig_list.addItem(item)

        # DBC decoded signals
        for sig in sigs:
            mid  = sig.get("message_id", "000")
            name = sig.get("signal_name", "?")
            item = QListWidgetItem(f"0x{mid}  {name}  [decoded]")
            item.setData(Qt.ItemDataRole.UserRole, ("dbc", mid, name))
            item.setFont(mono_font(8))
            item.setForeground(QColor(COLORS["green"]))
            self.sig_list.addItem(item)

    # ── Plot ──────────────────────────────────────────────────────────────────

    def _clear_plots(self):
        self.glw.clear()
        self._plots.clear()
        self._curves.clear()
        self._playhead_lines.clear()

    def _plot_selected(self):
        selected = self.sig_list.selectedItems()[:MAX_ROWS]
        if not selected:
            self.lbl_status.setText("Select at least one signal.")
            return
        df = self._state.frames_df
        if df.empty:
            self.lbl_status.setText("No frames loaded.")
            return

        self._clear_plots()
        colors = [
            COLORS["green"], "#00BFFF", "#FF8C00", "#DA70D6",
            "#ADFF2F", "#FF6347", "#40E0D0", "#FFD700",
        ]

        n = len(selected)
        for row_idx, item in enumerate(selected):
            kind, mid, name = item.data(Qt.ItemDataRole.UserRole)
            pen_color = colors[row_idx % len(colors)]

            # Extract time + value series
            t, y, label = self._extract_series(df, kind, mid, name)
            if t is None or len(t) == 0:
                continue

            # Create plot row
            p = self.glw.addPlot(row=row_idx, col=0)
            p.setLabel("left", label, color=pen_color)
            p.getAxis("left").setStyle(tickFont=mono_font(7))
            p.getAxis("bottom").setStyle(tickFont=mono_font(7))
            p.setMouseEnabled(x=True, y=False)

            if row_idx < n - 1:
                p.hideAxis("bottom")
            else:
                p.setLabel("bottom", "Time (s)")

            # Link x-axes to first plot
            if row_idx > 0:
                p.setXLink(self._plots[0])

            curve = p.plot(t, y, pen=pg.mkPen(pen_color, width=1),
                          stepMode="left")
            self._plots.append(p)
            self._curves.append(curve)

            # Playhead
            vline = pg.InfiniteLine(angle=90, movable=False,
                                    pen=pg.mkPen("#FFFFFF", width=1, style=Qt.PenStyle.DashLine))
            p.addItem(vline)
            self._playhead_lines.append(vline)

            # Click to move playhead
            p.scene().sigMouseClicked.connect(self._on_click)

        self.glw.ci.layout.setSpacing(2)
        self.lbl_status.setText(f"Plotting {len(self._plots)} signal(s).")
        self.lbl_status.setStyleSheet(f"color:{COLORS['green']}")

    def _extract_series(self, df, kind: str, mid: str, name: str):
        if kind == "raw":
            frames = df[df["ID"] == mid].sort_values("Timestamp")
            if frames.empty or name not in frames.columns:
                return None, None, name
            t = frames["Timestamp"].values.astype(float)
            y = frames[name].fillna(0).values.astype(float)
            return t, y, f"0x{mid} {name}"

        if kind == "dbc":
            from core.dbc_manager import decode_frame
            sigs   = [s for s in self._state.dbc_signals
                      if s.get("message_id", "").upper() == mid.upper()]
            frames = df[df["ID"] == mid].sort_values("Timestamp")
            if frames.empty or not sigs:
                return None, None, name
            t_vals, y_vals = [], []
            for _, row in frames.iterrows():
                data = bytes(int(row.get(f"B{i}", 0) or 0) for i in range(8))
                decoded = decode_frame(sigs, mid, data)
                if name in decoded:
                    t_vals.append(float(row["Timestamp"]))
                    y_vals.append(float(decoded[name]))
            if not t_vals:
                return None, None, name
            return np.array(t_vals), np.array(y_vals), f"0x{mid} {name}"

        return None, None, name

    def _on_click(self, event):
        """Move playhead across all rows to clicked timestamp."""
        if not self._plots:
            return
        try:
            pos = event.scenePos()
            vb  = self._plots[0].vb
            pt  = vb.mapSceneToView(pos)
            t   = pt.x()
            for line in self._playhead_lines:
                line.setValue(t)
        except Exception:
            pass
