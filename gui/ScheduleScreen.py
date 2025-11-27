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


from gui.session import JsonlSession


class ScheduleScreen(QWidget):
    """Driver schedule CRUD using persistent TCP connection."""
    def __init__(self, session: JsonlSession, parent=None):
        super().__init__(parent)
        self.session = session

        self.selected_lat = None
        self.selected_lon = None

        form = QHBoxLayout()

        self.cb_weekday = QComboBox()
        self.cb_weekday.addItems(["Sun", "Mon", "Tues", "Wed", "Thurs", "Fri", "Sat"])

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setKeyboardTracking(False)

        self.cb_direction = QComboBox()
        self.cb_direction.addItems(["to_AUB", "from_AUB"])
        self.cb_direction.currentTextChanged.connect(self._update_direction_hints)


        self.in_area = QLineEdit()
        self.in_area.setPlaceholderText("e.g Hamra")

        self.btn_pick_location = QPushButton("Pick location on map")
        self.btn_pick_location.clicked.connect(self.open_map)

        self.btn_add = QPushButton("Add")
        self.btn_add.clicked.connect(self.on_add_slot)

        self._update_direction_hints()


        for w in (self.cb_weekday, self.time_edit, self.cb_direction, self.in_area,
                  self.btn_pick_location, self.btn_add):
            form.addWidget(w)

        self.err = QLabel("")
        self.err.setWordWrap(True)
        self.err.setStyleSheet("color: red;")
        self.err.setVisible(False)

        self.ok = QLabel("")
        self.ok.setWordWrap(True)
        self.ok.setStyleSheet("color: green;")
        self.ok.setVisible(False)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Weekday", "Time", "Direction", "Area"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        btns = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_delete = QPushButton("Delete Selected")
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_delete.clicked.connect(self.on_delete_selected)
        btns.addWidget(self.btn_refresh)
        btns.addWidget(self.btn_delete)
        btns.addStretch(1)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addWidget(self.err)
        root.addWidget(self.ok)
        root.addSpacing(8)

        
        root.addWidget(self.table, 1)
        root.addLayout(btns)

        self.refresh()

    # ---- map picking ----
    def open_map(self):
        dlg = MapSelector(self)

        # (optional) tweak text based on direction
        direction = self.cb_direction.currentText()
        if direction == "to_AUB":
            dlg.setWindowTitle("Select your pickup location")
            dlg.label.setText("Try to approximately locate where you will be picked up (your current location).")
        else:
            dlg.setWindowTitle("Select your drop-off location")
            dlg.label.setText("Try to approximately locate where you will be dropped off.")

        dlg.location_selected.connect(self.on_location_picked)
        dlg.showMaximized()   # important: so showEvent sees the max size
        dlg.exec_()

    def on_location_picked(self, lat, lon):
        self.selected_lat = lat
        self.selected_lon = lon
        self.show_ok(f"Pickup location selected ✓ (lat={lat:.5f}, lon={lon:.5f})")

    # ---- helpers ----
    def show_error(self, msg):
        self.err.setText(msg)
        self.err.setVisible(True)
        self.ok.setVisible(False)

    def show_ok(self, msg):
        self.ok.setText(msg)
        self.ok.setVisible(True)
        self.err.setVisible(False)

    def _weekday_index(self):
        return self.cb_weekday.currentIndex()

    def _time_str(self):
        return self.time_edit.time().toString("HH:mm")
    
    def _update_direction_hints(self):
        direction = self.cb_direction.currentText()
        if direction == "to_AUB":
            # Driver is going TO campus; pin = origin
            self.in_area.setPlaceholderText("From where are you driving? (e.g. Hamra)")
            self.btn_pick_location.setText("Pick starting point on map")
        else:
            # Driver is leaving AUB; pin = destination
            self.in_area.setPlaceholderText("Where are you dropping off? (e.g. Hamra)")
            self.btn_pick_location.setText("Pick drop-off area on map")


    # ---- CRUD ----
    def refresh(self):
        current_row = self.table.currentRow()
        selected_sched_id = None
        if current_row >= 0:
            item0 = self.table.item(current_row, 0)
            if item0 is not None:
                selected_sched_id = item0.data(Qt.UserRole)

        req = {
            "type": "SCHEDULE.LIST_REQ",
            "id": str(uuid.uuid4()),
            "payload": {}
        }
        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return

        if resp.get("type") != "SCHEDULE.LIST_RES":
            self.show_error(
                resp.get("payload", {}).get(
                    "message",
                    f"Unexpected response: {resp.get('type')}"
                )
            )
            return

        items = resp.get("payload", {}).get("items", [])
        self.table.setRowCount(0)

        for item in items:
            row = self.table.rowCount()
            self.table.insertRow(row)

            wd_idx = item["weekday"]
            wd = ["Sun", "Mon", "Tues", "Wed", "Thurs", "Fri", "Sat"][wd_idx] \
                if 0 <= wd_idx <= 6 else str(wd_idx)

            c0 = QTableWidgetItem(wd)
            c0.setData(Qt.UserRole, item["schedule_id"])

            self.table.setItem(row, 0, c0)
            self.table.setItem(row, 1, QTableWidgetItem(item["depart_time"]))
            self.table.setItem(row, 2, QTableWidgetItem(item["direction"]))
            self.table.setItem(row, 3, QTableWidgetItem(item["area"]))

        if selected_sched_id is not None:
            for row in range(self.table.rowCount()):
                item0 = self.table.item(row, 0)
                if item0 is not None and item0.data(Qt.UserRole) == selected_sched_id:
                    self.table.setCurrentCell(row, 0)
                    break

    def on_add_slot(self):
        area = self.in_area.text().strip()
        if not area:
            self.show_error("Area is required (for display).")
            return

        if self.selected_lat is None or self.selected_lon is None:
            self.show_error("Please pick a map location for this schedule.")
            return

        payload = {
            "weekday": self._weekday_index(),
            "depart_time": self._time_str(),
            "direction": self.cb_direction.currentText(),
            "area": area,
            "lat": float(self.selected_lat),
            "lon": float(self.selected_lon),
        }

        req = {"type": "SCHEDULE.SET_REQ", "id": str(uuid.uuid4()), "payload": payload}
        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return

        if resp.get("type") == "SCHEDULE.SET_RES":
            self.show_ok("Slot added.")
            self.refresh()
        else:
            payload = resp.get("payload", {})
            if payload.get("code") == "SCHEDULE_DUPLICATE":
                self.show_error("You have already added this exact slot, change any field to add a new one")
            else:
                self.show_error(resp.get("payload", {}).get("message", "Failed to add slot."))

    def on_delete_selected(self):
        r = self.table.currentRow()
        if r < 0:
            self.show_error("Select a row to delete.")
            return

        sid = self.table.item(r, 0).data(Qt.UserRole)
        if not isinstance(sid, int):
            self.show_error("Internal error: missing schedule_id.")
            return
        req = {"type": "SCHEDULE.REMOVE_REQ", "id": str(uuid.uuid4()), "payload": {"schedule_id": sid}}
        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return

        if resp.get("type") == "SCHEDULE.REMOVE_RES":
            self.show_ok("Slot deleted.")
            self.refresh()
        else:
            self.show_error(resp.get("payload", {}).get("message", "Failed to delete slot."))
