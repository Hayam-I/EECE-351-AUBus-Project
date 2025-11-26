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



class CurrentRidePage(QWidget):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        v = QVBoxLayout(self)

        # Top info label (who you're riding with)
        self.info_label = QLabel("No active ride")
        self.info_label.setWordWrap(True)
        v.addWidget(self.info_label)

        # Chat area
        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)
        self.chat_box.setStyleSheet("QTextEdit, QTextEdit * { background: transparent; }")

        v.addWidget(self.chat_box, 1)

        # Chat input
        self.chat_input = QLineEdit()
        self.chat_input.setObjectName("chatInput")  # so stylesheet can target it
        self.chat_input.setPlaceholderText("Type a message...")
        v.addWidget(self.chat_input)

        # Buttons row
        h = QHBoxLayout()
        self.send_btn = QPushButton("Send")
        self.complete_btn = QPushButton("Complete Ride")
        h.addWidget(self.send_btn)
        h.addStretch(1)
        h.addWidget(self.complete_btn)
        v.addLayout(h)

        # hide complete button by default (passenger view)
        self.complete_btn.hide()

        self.send_btn.clicked.connect(self.on_send_clicked)

    # ===== Chat bubbles =====
    def append_bubble(self, text: str, outgoing: bool, timestamp=None):
        if not text:
            return

        safe = html.escape(text).replace("\n", "<br/>")

        mw = self.window()
        other_name = getattr(mw, "other_party_name", "Them") if mw else "Them"
        is_dark = getattr(mw, "is_dark_mode", True)

        if outgoing:
            side = "right"
            bg = "#4f46e5"
            fg = "#ffffff"
            sender = "You"
        else:
            side = "left"
            bg = "#e5e7eb" if not is_dark else "#1f2937"
            fg = "#111827" if not is_dark else "#e5e7eb"
            sender = other_name

        if timestamp is None:
            timestamp = QDateTime.currentDateTime()
        ts = timestamp.toString("HH:mm")

        html_blob = f"""
        <div style="width:100%; text-align:{side}; margin:8px 0;">
            <div style="
                display:inline-block;
                max-width:60%;
                background:{bg};
                color:{fg};
                padding:10px 14px;
                border-radius:18px;
                font-size:10pt;
                line-height:1.4;
                box-shadow:0px 2px 5px rgba(0,0,0,0.25);
                word-wrap:break-word;
            ">
                <div style="font-size:8pt; opacity:0.7; margin-bottom:4px;">
                    {sender}
                </div>
                {safe}
                <div style="font-size:8pt; text-align:right; opacity:0.6; margin-top:6px;">
                    {ts}
                </div>
            </div>
        </div>
        """

        cursor = self.chat_box.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(html_blob)
        cursor.insertHtml("<br/>")
        self.chat_box.setTextCursor(cursor)
        self.chat_box.ensureCursorVisible()

    # ===== Sending =====
    def on_send_clicked(self):
        msg = self.chat_input.text().strip()
        if not msg:
            return

        mw = self.window()
        ok = False
        if hasattr(mw, "send_chat_message"):
            ok = mw.send_chat_message(msg)

        if ok:
            self.append_bubble(msg, outgoing=True)
            self.chat_input.clear()
        else:
            QMessageBox.warning(self, "Send Failed", "Failed to send message.")

    # ===== Load states =====
    def load_for_driver(self, match_payload):
        """
        Called when driver receives a MATCH notification
        """
        p = match_payload.get("passenger_info", {}) or {}
        passenger_name = p.get("name", "Passenger")
        self.info_label.setText(f"Passenger matched!\nRiding with: {passenger_name}")
        self.complete_btn.show()

    def load_for_passenger(self, payload):
        """
        Called when passenger receives a MATCH notification
        """
        d = payload.get("driver_info", {}) or {}
        name = d.get("name") or "Driver"

        vehicle = d.get("vehicle") or {}
        model = vehicle.get("model") or "Unknown"
        color = vehicle.get("color") or "Unknown"
        plate = vehicle.get("plate") or "Unknown"

        self.info_label.setText(
            f"Driver matched!\n"
            f"Name: {name}\n"
            f"Car: {model} ({color})\n"
            f"Plate: {plate}"
        )

        self.complete_btn.hide()
