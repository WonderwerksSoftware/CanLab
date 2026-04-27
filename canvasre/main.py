#!/usr/bin/env python3
"""CANLAB — CAN Reverse Engineering Suite for Hyundai Kona."""
import sys
import os

# Ensure canvasre/ is on sys.path when running as `python main.py`
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from theme import QSS, mono_font
from mainwindow import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CANLAB")
    app.setOrganizationName("CANLAB")
    app.setStyleSheet(QSS)
    app.setFont(mono_font())

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
