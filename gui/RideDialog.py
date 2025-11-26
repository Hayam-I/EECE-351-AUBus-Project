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
from PyQt5.QtGui import QTextCursor, QPixmap


import requests
from io import BytesIO



class RateRideDialog(QDialog):
    def __init__(self, request_id: str, session, parent=None):
        super().__init__(parent)
        self.request_id = request_id
        self.session = session

        self.setWindowTitle("Rate your ride")
        self.setModal(True)

        self.spin = QSpinBox()
        self.spin.setRange(1, 5)
        self.spin.setValue(5)

        lbl = QLabel("How would you rate your ride (1–5)?")

        btn_ok = QPushButton("Submit")
        btn_cancel = QPushButton("Skip")

        btn_ok.clicked.connect(self.on_submit)
        btn_cancel.clicked.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(lbl)
        layout.addWidget(self.spin)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def on_submit(self):
        rating = self.spin.value()
        self.session.send_json({
            "type": "RIDE.RATE_REQ",
            "id": str(uuid.uuid4()),
            "payload": {
                "request_id": self.request_id,  # e.g. "req_7"
                "rating": rating,
            },
        })
        self.accept()
