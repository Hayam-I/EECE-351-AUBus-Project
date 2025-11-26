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
from gui.p2p_chat_endpoint import P2PChatEndpoint

import requests

#page imports

from gui.weather_helpers import fetch_weather_for_coords
from gui.session import JsonlSession


class ProfileScreen(QWidget):
    driverModeChanged = pyqtSignal(bool)  # emit after successful save

    def __init__(self, session: JsonlSession, user_preview: dict, parent=None):
        super().__init__(parent)
        self.session = session

        # snapshot from login + optional vehicle info (if you later add it to PROFILE.GET)
        veh = user_preview.get("vehicle") or {}
        self.snapshot = {
            "name":       user_preview.get("name", ""),
            "email":      user_preview.get("email", ""),
            "area":       user_preview.get("area", ""),
            "is_driver":  bool(user_preview.get("is_driver", False)),
            "vehicle_make":  veh.get("make", "") if isinstance(veh, dict) else "",
            "vehicle_model": veh.get("model", "") if isinstance(veh, dict) else "",
            "vehicle_color": veh.get("color", "") if isinstance(veh, dict) else "",
            "vehicle_plate": veh.get("plate", "") if isinstance(veh, dict) else "",
            "rating_avg": user_preview.get("rating_avg",0.0),
            "rating_count": user_preview.get("rating_count",0)
        }

        # ---- basic fields ----
        self.in_name = QLineEdit(self.snapshot["name"])
        self.in_name.setObjectName("profileField")
        self.in_email = QLineEdit(self.snapshot["email"])
        self.in_email.setObjectName("profileField")
        self.in_area = QLineEdit(self.snapshot["area"])
        self.in_area.setObjectName("profileField")
        self.chk_driver = QCheckBox("Driver Mode")
        self.chk_driver.setChecked(self.snapshot["is_driver"])

        # ---- vehicle fields (used only when driver) ----
        self.in_vehicle_make  = QLineEdit(self.snapshot["vehicle_make"])
        self.in_vehicle_model = QLineEdit(self.snapshot["vehicle_model"])
        self.in_vehicle_color = QLineEdit(self.snapshot["vehicle_color"])
        self.in_vehicle_plate = QLineEdit(self.snapshot["vehicle_plate"])

        self.in_vehicle_make.setPlaceholderText("e.g. Toyota")
        self.in_vehicle_model.setPlaceholderText("e.g. Corolla")
        self.in_vehicle_color.setPlaceholderText("e.g. White")
        self.in_vehicle_plate.setPlaceholderText("e.g. B 123456")

        # Stronger style for profile fields (reuse for vehicle fields)
        profile_field_css = """
        QLineEdit#profileField,
        QLineEdit#profileField:disabled,
        QLineEdit#profileField:read-only {
            border-radius: 8px;
            padding: 6px 10px;
        }
        QLineEdit#profileField:focus {
            border-width: 1px;
        }
        """

        # apply style
        self.in_name.setStyleSheet(profile_field_css)
        self.in_email.setStyleSheet(profile_field_css)
        self.in_area.setStyleSheet(profile_field_css)

        for w in (self.in_vehicle_make, self.in_vehicle_model, self.in_vehicle_color, self.in_vehicle_plate):
            w.setObjectName("profileField")
            w.setStyleSheet(profile_field_css)

        for w in (self.in_name, self.in_email, self.in_area,
                  self.in_vehicle_make, self.in_vehicle_model,
                  self.in_vehicle_color, self.in_vehicle_plate):
            w.setMinimumWidth(300)
            w.setMaximumWidth(420)

        # ---- form layout ----
        self.form = QFormLayout()
        form = self.form
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignHCenter | Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        form.addRow("Name:", self.in_name)
        form.addRow("Email:", self.in_email)
        form.addRow("Area:", self.in_area)
        form.addRow("", self.chk_driver)

        # vehicle fields always visible but disabled when not a driver
        form.addRow("Car make:", self.in_vehicle_make)
        form.addRow("Car model:", self.in_vehicle_model)
        form.addRow("Car color:", self.in_vehicle_color)
        form.addRow("Plate:", self.in_vehicle_plate)
        self.lbl_rating = QLabel("No reviews yet")
        form.addRow("Rating:", self.lbl_rating)

        self.err = QLabel("")
        self.err.setWordWrap(True)
        self.err.setStyleSheet("color: red;")
        self.err.setVisible(False)

        self.ok = QLabel("")
        self.ok.setWordWrap(True)
        self.ok.setStyleSheet("color: #0a7a0a;")
        self.ok.setVisible(False)

        self.weather_icon = QLabel()
        self.weather_icon.setFixedSize(48, 48)
        self.weather_icon.setScaledContents(True)

        self.weather_label = QLabel("")
        self.weather_label.setWordWrap(False)

        weather_row = QHBoxLayout()
        weather_row.addWidget(self.weather_icon)
        weather_row.addWidget(self.weather_label, 1)

        self.btn_edit = QPushButton("Edit")
        self.btn_save = QPushButton("Save")
        self.btn_cancel = QPushButton("Cancel")

        self.btn_edit.clicked.connect(self.on_edit)
        self.btn_save.clicked.connect(self.on_save)
        self.btn_cancel.clicked.connect(self.on_cancel)

        # Driver checkbox toggles vehicle fields
        self.chk_driver.toggled.connect(self._on_driver_toggled)

        root = QVBoxLayout(self)
        root.addSpacing(10)
        root.addLayout(form)
        root.addWidget(self.err)
        root.addWidget(self.ok)
        root.addSpacing(8)
        root.addLayout(weather_row)
        root.addSpacing(12)

        buttons = QHBoxLayout()
        buttons.addWidget(self.btn_edit)
        buttons.addWidget(self.btn_save)
        buttons.addWidget(self.btn_cancel)
        root.addLayout(buttons)
        root.addStretch(1)

        # start in view mode
        self.set_edit_mode(False)
        # set proper enabled/disabled state for vehicle fields
        self._update_vehicle_visibility(self.snapshot["is_driver"])
        self._on_driver_toggled(self.snapshot["is_driver"])
        # load weather
        self.on_weather_clicked()

    # ---------- helpers ----------
    def set_edit_mode(self, on: bool):
        editing = bool(on)
        for w in (self.in_name, self.in_email, self.in_area,
                  self.in_vehicle_make, self.in_vehicle_model,
                  self.in_vehicle_color, self.in_vehicle_plate):
            w.setReadOnly(not editing)
        self.chk_driver.setEnabled(editing)

        # but even in edit mode, only enable vehicle fields if driver is checked
        self._on_driver_toggled(self.chk_driver.isChecked())

        self.btn_edit.setEnabled(not editing)
        self.btn_save.setEnabled(editing)
        self.btn_cancel.setEnabled(editing)


    def _on_driver_toggled(self, checked: bool):
        """Enable + show car fields only when driver mode is ON."""
        is_driver = bool(checked)

        # visibility
        self._update_vehicle_visibility(is_driver)

        # enabled state (only if not read-only)
        for w in (self.in_vehicle_make, self.in_vehicle_model,
                  self.in_vehicle_color, self.in_vehicle_plate):
            w.setEnabled(is_driver and not w.isReadOnly())


    def _update_vehicle_visibility(self, is_driver: bool):
        """Show/hide car fields + labels depending on driver mode."""
        widgets = (
            self.in_vehicle_make,
            self.in_vehicle_model,
            self.in_vehicle_color,
            self.in_vehicle_plate,
        )
        for w in widgets:
            w.setVisible(is_driver)
            if hasattr(self, "form"):
                label = self.form.labelForField(w)
                if label is not None:
                    label.setVisible(is_driver)


    def reset_fields_from_snapshot(self):
        self.in_name.setText(self.snapshot["name"])
        self.in_email.setText(self.snapshot["email"])
        self.in_area.setText(self.snapshot["area"])
        self.chk_driver.setChecked(self.snapshot["is_driver"])

        self.in_vehicle_make.setText(self.snapshot["vehicle_make"])
        self.in_vehicle_model.setText(self.snapshot["vehicle_model"])
        self.in_vehicle_color.setText(self.snapshot["vehicle_color"])
        self.in_vehicle_plate.setText(self.snapshot["vehicle_plate"])

    def show_error(self, msg):
        self.err.setText(msg)
        self.err.setVisible(True)
        self.ok.setVisible(False)

    def show_ok(self, msg):
        self.ok.setText(msg)
        self.ok.setVisible(True)
        self.err.setVisible(False)
    
    def update_from_user_preview(self, u: dict):
        """Refresh rating info from the latest user preview."""
        avg = u.get("rating_avg") or 0.0
        count = u.get("rating_count") or 0

        if count <= 0:
            self.lbl_rating.setText("No reviews yet")
        else:
            self.lbl_rating.setText(f"{avg:.1f} ({count} reviews)")


    # ---------- buttons ----------
    def on_edit(self):
        self.reset_fields_from_snapshot()
        self.set_edit_mode(True)

    def on_cancel(self):
        self.reset_fields_from_snapshot()
        self.set_edit_mode(False)

    def on_save(self):
        area = self.in_area.text().strip()
        if not area:
            self.show_error("Area is required")
            return

        is_driver = bool(self.chk_driver.isChecked())

        # If driver mode ON => car details are required
        make  = self.in_vehicle_make.text().strip()
        model = self.in_vehicle_model.text().strip()
        color = self.in_vehicle_color.text().strip()
        plate = self.in_vehicle_plate.text().strip()

        if is_driver and (not make or not model or not color or not plate):
            self.show_error("Please fill car make, model, color, and plate to enable driver mode.")
            return

        payload = {
            "name": self.in_name.text().strip(),
            "email": self.in_email.text().strip(),
            "area": area,
            "is_driver": is_driver,
            "vehicle": {
                "make": make if is_driver else "",
                "model": model if is_driver else "",
                "color": color if is_driver else "",
                "plate": plate if is_driver else "",
            },
        }

        req = {"type": "PROFILE.SET_REQ", "id": str(uuid.uuid4()), "payload": payload}
        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return

        if resp.get("type") == "PROFILE.SET_RES":
            prev_driver = self.snapshot["is_driver"]
            # update snapshot
            self.snapshot["name"] = payload["name"]
            self.snapshot["email"] = payload["email"]
            self.snapshot["area"] = payload["area"]
            self.snapshot["is_driver"] = is_driver
            self.snapshot["vehicle_make"] = payload["vehicle"]["make"]
            self.snapshot["vehicle_model"] = payload["vehicle"]["model"]
            self.snapshot["vehicle_color"] = payload["vehicle"]["color"]
            self.snapshot["vehicle_plate"] = payload["vehicle"]["plate"]

            self.set_edit_mode(False)
            self.show_ok("Profile saved.")
            if prev_driver != is_driver:
                self.driverModeChanged.emit(is_driver)
        elif resp.get("type") == "ERROR":
            self.show_error(resp.get("payload", {}).get("message", "Failed to save profile."))
        else:
            self.show_error(f"Unexpected response: {resp.get('type')}")

    def on_weather_clicked(self):
        # Beirut loc
        lat, lon = 33.8938, 35.5018

        self.weather_label.setWordWrap(False)
        self.weather_label.setText("Today's weather in Beirut - loading...")
        self.weather_icon.clear()

        info = fetch_weather_for_coords(lat, lon)
        if not info:
            self.weather_label.setText("Today's weather in Beirut - unavailable.")
            return

        self.weather_label.setWordWrap(False)
        self.weather_label.setText(
            f" Today's weather in Beirut - {info['temp_c']}°C — {info['condition_text']}"
        )

        try:
            icon_resp = requests.get(info["icon_url"], timeout=4)
            pix = QPixmap()
            pix.loadFromData(icon_resp.content)
            self.weather_icon.setPixmap(pix)
        except Exception as e:
            print("Weather icon failed:", e)
