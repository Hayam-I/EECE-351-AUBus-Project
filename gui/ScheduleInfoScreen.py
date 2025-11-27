import sys
import traceback
import json
import re
import socket
import uuid
import threading
import logging
import html
from client.map_selector import MapSelector
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget, QFormLayout,
    QLineEdit, QMessageBox, QCheckBox, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTimeEdit, QDateTimeEdit, QTextEdit, QDialog, QSpinBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QDateTime, QTimer, QObject


class ScheduleInfoScreen(QWidget):
    """Shown to passengers: explains that schedule is driver-only."""
    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        lbl = QLabel(
            "Schedule is available only for drivers.\n\n"
            "To add a weekly schedule:\n"
            "1. Go to the Profile tab.\n"
            "2. Enable 'Driver Mode' and fill in your car details.\n"
            "3. Save your profile.\n\n"
            "Once Driver Mode is on, you'll see the schedule editor here."
        )
        lbl.setWordWrap(True)
        v.addStretch(1)
        v.addWidget(lbl, 0, Qt.AlignCenter)
        v.addStretch(1)

