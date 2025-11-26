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

from gui.session import JsonlSession

def excepthook(exc_type, exc, tb):
    traceback.print_exception(exc_type, exc, tb)
    QMessageBox.critical(None, "Unhandled Error", f"{exc_type.__name__}: {exc}")
sys.excepthook = excepthook

def set_visible(widget, visible: bool):
    widget.setVisible(visible)


class RideRequestPage(QWidget):
    def __init__(self, session: JsonlSession, parent=None):
        super().__init__(parent)
        self.session = session

        # ---- Coordinates from map ----
        self.selected_lat = None
        self.selected_lon = None

        self.btn_pick_location = QPushButton("Pick location on map")
        self.btn_pick_location.clicked.connect(self.open_map)

        # ---- Polling setup ----
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(3000)
        self.poll_timer.timeout.connect(self._poll_for_match)

        self.current_request_id: str | None = None

        # ---- Form fields ----
        self.in_area = QLineEdit()
        self.in_area.setPlaceholderText("e.g Hamra")

        self.cb_direction = QComboBox()
        self.cb_direction.addItems(["to_AUB", "from_AUB"])
        self.cb_direction.currentTextChanged.connect(self._update_direction_hints)


        self.dt = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.dt.setCalendarPopup(True)
        self.dt.setKeyboardTracking(False)

        self.btn_submit = QPushButton("Request Ride")
        self.btn_submit.clicked.connect(self.on_submit)

        self.btn_cancel = QPushButton("Cancel request")
        set_visible(self.btn_cancel, False)
        self.btn_cancel.clicked.connect(self.on_cancel_clicked)
        self._update_direction_hints()


        # ---- Layout ----
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignCenter | Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        form.addRow("Area:", self.in_area)
        form.addRow("", self.btn_pick_location)       # MAP BUTTON HERE
        form.addRow("Direction:", self.cb_direction)
        form.addRow("Departure Time:", self.dt)

        self.err = QLabel("")
        self.err.setWordWrap(True)
        self.err.setStyleSheet("color: red;")
        self.err.setVisible(False)

        self.ok = QLabel("")
        self.ok.setWordWrap(True)
        self.ok.setStyleSheet("color: #0a7a0a;")
        self.ok.setVisible(False)

        self.lbl_request_id = QLabel("Request ID: —")
        self.lbl_status = QLabel("Status: —")

        # ---- Root ----
        root = QVBoxLayout(self)
        root.addLayout(form)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.btn_submit)
        row.addWidget(self.btn_cancel)
        row.addStretch(1)
        root.addLayout(row)

        root.addSpacing(10)
        root.addWidget(self.err)
        root.addWidget(self.ok)
        root.addSpacing(12)
        root.addWidget(self.lbl_request_id)
        root.addWidget(self.lbl_status)
        root.addStretch(1)

        self.set_idle_state()

    # =====================================================================
    # Helpers
    # =====================================================================
    def show_error(self, msg):
        self.err.setText(msg)
        self.err.setVisible(True)
        self.ok.setVisible(False)

    def show_ok(self, msg):
        self.ok.setText(msg)
        self.ok.setVisible(True)
        self.err.setVisible(False)

    def _iso_string(self) -> str:
        return self.dt.dateTime().toString("yyyy-MM-dd HH:mm")

    # =====================================================================
    # MAP HANDLERS
    # =====================================================================
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
        self.show_ok(f"Location selected ✓ (lat={lat:.5f}, lon={lon:.5f})")

        if hasattr(self, "map_dialog"):
            self.map_dialog.close()
        
    def _update_direction_hints(self):
        direction = self.cb_direction.currentText()
        if direction == "to_AUB":
            # Passenger is off-campus, going TO AUB
            self.in_area.setPlaceholderText("Where are you now? (e.g. Hamra)")
            self.btn_pick_location.setText("Pick your pickup location on map")
        else:
            # Passenger is at AUB, going somewhere else
            self.in_area.setPlaceholderText("Where are you going? (e.g. Hamra)")
            self.btn_pick_location.setText("Pick your drop-off location on map")


    # =====================================================================
    # SUBMIT REQUEST
    # =====================================================================
    def on_submit(self):
        self.err.setVisible(False)
        self.ok.setVisible(False)

        area = self.in_area.text().strip()
        if not area:
            self.show_error("Area is required (for info).")
            return

        if self.selected_lat is None or self.selected_lon is None:
            self.show_error("Please pick your location on the map.")
            return

        payload = {
            "area": area,  # kept for display, NOT used for matching
            "direction": self.cb_direction.currentText(),
            "time_iso": self._iso_string(),
            "lat": float(self.selected_lat),
            "lon": float(self.selected_lon),
        }

        req = {"type": "RIDE.REQUEST_REQ", "id": str(uuid.uuid4()), "payload": payload}

        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return

        rtype = resp.get("type")
        p = resp.get("payload", {})

        if rtype == "RIDE.REQUEST_RES":
            req_id = p.get("request_id")
            found  = p.get("candidates_found", 0)

            self.current_request_id = req_id
            set_visible(self.btn_cancel, True)
            set_visible(self.btn_submit, False)

            self.lbl_request_id.setText(f"Request ID: {req_id}")
            self.lbl_status.setText(f"Status: open — compatible drivers found: {found}")
            self.show_ok("Ride request created.")
            self.poll_timer.start()

        elif rtype == "ERROR":
            code = p.get("code")
            msg = p.get("message", "Failed to create ride request")
            if code == "PASSENGER_BUSY":
                self.current_request_id = None
                set_visible(self.btn_cancel, False)
                set_visible(self.btn_submit, True)
            self.show_error(msg)
        else:
            self.show_error(f"Unexpected response: {rtype}")

    # =====================================================================
    # CANCEL REQUEST
    # =====================================================================
    def on_cancel_clicked(self):
        if not self.current_request_id:
            self.show_error("No active request to cancel.")
            return

        req = {
            "type": "RIDE.CANCEL_REQ",
            "id": str(uuid.uuid4()),
            "payload": {"request_id": self.current_request_id},
        }

        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return

        rtype = resp.get("type")
        payload = resp.get("payload", {})

        if rtype == "RIDE.CANCEL_RES":
            self.current_request_id = None
            self.set_idle_state()
            QMessageBox.information(self, "Request Cancelled", "Your ride request has been cancelled.")

        elif rtype == "ERROR":
            code = payload.get("code")
            msg = payload.get("message", "Unknown error")

            if code == "INVALID_STATE":
                QMessageBox.information(self, "Cannot cancel",
                    "Your request has already been accepted by a driver.")
                return

            QMessageBox.warning(self, "Cancel failed",
                f"Server returned error: {code or 'ERROR'} - {msg}")

        else:
            QMessageBox.warning(self, "Unexpected reply",
                f"Unexpected response to cancel: {rtype}")

    # =====================================================================
    # STATE HANDLING
    # =====================================================================
    def handle_matched(self, payload):
        self.lbl_status.setText("Status: A driver has accepted your request!")
        set_visible(self.btn_cancel, False)

    def set_idle_state(self):
        self.current_request_id = None

        try: self.poll_timer.stop()
        except: pass

        set_visible(self.btn_cancel, False)
        set_visible(self.btn_submit, True)

        self.lbl_request_id.setText("Request ID: —")
        self.lbl_status.setText("Status: —")

    # =====================================================================
    # POLLING (keeps reading matched notifications)
    # =====================================================================
    def _poll_for_match(self):
        if not self.current_request_id:
            return
        try:
            req = {"type": "PING", "id": str(uuid.uuid4()), "payload": {}}
            self.session.request(req)
        except Exception as e:
            print(f"poll_for_match error: {e}")

