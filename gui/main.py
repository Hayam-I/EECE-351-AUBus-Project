import sys
import traceback
import json
import re
import socket
import uuid
import threading
import logging
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget, QFormLayout,
    QLineEdit, QMessageBox, QCheckBox, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTimeEdit, QDateTimeEdit
)
from PyQt5.QtCore import Qt, pyqtSignal, QDateTime, QTimer, QObject

# ===== error popup for uncaught exceptions =====
def excepthook(exc_type, exc, tb):
    traceback.print_exception(exc_type, exc, tb)
    QMessageBox.critical(None, "Unhandled Error", f"{exc_type.__name__}: {exc}")
sys.excepthook = excepthook

# ===== transport config =====
HOST = "127.0.0.1"
PORT = 6000
SOCKET_TIMEOUT = 4.0
ENCODING = "utf-8"

# ===== client helpers from client/net.py =====
from client.net import send_json, recv_json

def title_page(text):
    w = QWidget()
    v = QVBoxLayout(w)
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setObjectName("page_title")
    v.addStretch(1)
    v.addWidget(lbl)
    v.addStretch(1)
    return w

# ===== validation regex (mirror server) =====
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,20}$")
PASSWORD_RE = re.compile(r"^.{6,20}$")
EMAIL_RE    = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

# =============================================================================
# Persistent JSONL session (one TCP connection per client after login)
# =============================================================================
class JsonlSession(QObject):
    push_reveived = pyqtSignal(dict)
    def __init__(self, host: str, port: int, timeout: float = 4.0, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: socket.socket | None = None
    
    def handle_push(self, msg: dict):
        self.push_reveived.emit(msg)

    def ensure_connected(self):
        if self.sock is not None:
            return
        s = socket.create_connection((self.host, self.port), timeout=self.timeout)
        s.settimeout(self.timeout)
        self.sock = s

    def request(self, env: dict) -> dict:
        """Send 1 request, wait for 1 response, over the SAME socket. ignore push messages"""
        if not isinstance(env, dict):
            raise TypeError("JsonlSession.request expects a dict envelope")
        
        self.ensure_connected()

        mid = env.get("id")
        if not mid:
            mid = str(uuid.uuid4)
            env["id"] = mid

        if "payload" not in env or env["payload"] is None:
            env["paylaod"] = {}

        send_json(self.sock, env)

        while True:
            msg = recv_json(self.sock)
            if msg is None:
                # timeout or EOF – adjust error handling
                raise RuntimeError(f"Timeout or disconnect waiting for response to {env.get('type')}")
            if msg.get("id") == mid:
                return msg

            # Otherwise, treat as push / unsolicited
            t = msg.get("type")
            if t in ("RIDE.MATCHED", "REQUEST_CLOSED", "DRIVER.BROADCAST"):
                self.handle_push(msg)
                continue

            # Stray message with some other id; log and ignore
            logging.warning("JsonlSession: ignoring unsolicited message: %r", msg)


      

    def close(self):
        try:
            if self.sock:
                self.sock.close()
        finally:
            self.sock = None

# =============================================================================
# Register form (unchanged, one-shot call – safe pre-login)
# =============================================================================
class RegisterForm(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.in_name = QLineEdit()
        self.in_email = QLineEdit()
        self.in_username = QLineEdit()
        self.in_password = QLineEdit()
        self.in_password.setEchoMode(QLineEdit.Password)
        self.in_area = QLineEdit()
        for w in (self.in_name, self.in_email, self.in_username, self.in_password, self.in_area):
            w.setMinimumWidth(250); w.setMaximumWidth(400)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignHCenter | Qt.AlignCenter)
        form.setContentsMargins(0,20,0,0)
        form.setHorizontalSpacing(15)
        form.setVerticalSpacing(10)
        form.addRow("Name:", self.in_name)
        form.addRow("Email:", self.in_email)
        form.addRow("Username:", self.in_username)
        form.addRow("Password:", self.in_password)
        form.addRow("Area:", self.in_area)

        self.err = QLabel(""); self.err.setWordWrap(True); self.err.setStyleSheet("color: red;"); self.err.setVisible(False)
        self.btn_register = QPushButton("Create account"); self.btn_register.setMinimumWidth(120)
        self.btn_register.clicked.connect(self.on_submit)

        card = QWidget(); card.setObjectName("register_card")
        card.setStyleSheet("""
            QWidget#register_card { background: #fff; border: 1px solid #e5e5e5; border-radius: 12px; }
            QLineEdit { padding: 8px 10px; border: 1px solid #d0d0d0; border-radius: 6px; }
            QLineEdit:focus { border: 1px solid #7aa7ff; outline: none; }
        """)
        lay = QVBoxLayout(card); lay.setContentsMargins(30,20,30,20); lay.setSpacing(15)
        lay.addLayout(form); lay.addWidget(self.err); lay.addSpacing(8); lay.addWidget(self.btn_register,0,Qt.AlignHCenter)

        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0)
        root.addStretch(1); root.addWidget(card,0,Qt.AlignHCenter); root.addStretch(1)

    def show_error(self, msg): self.err.setText(msg); self.err.setVisible(True)
    def clear_error(self): self.err.setText(""); self.err.setVisible(False)

    def validate(self):
        name = self.in_name.text().strip()
        email = self.in_email.text().strip()
        username = self.in_username.text().strip()
        password = self.in_password.text().strip()
        area = self.in_area.text().strip()
        if not name: return False, "Name is required."
        if not email or not EMAIL_RE.match(email): return False, "Invalid email format."
        if not username or not USERNAME_RE.match(username): return False, "Username must be 5-20 characters (letters, digits, underscores)."
        if not password or not PASSWORD_RE.match(password): return False, "Password must be 6-20 characters."
        if not area: return False, "Area is required."
        return True, {"name":name,"email":email,"username":username,"password":password,"area":area}

    def jsonl_request(self, obj):
        data = (json.dumps(obj, separators=(",", ":")) + "\n").encode(ENCODING)
        with socket.create_connection((HOST, PORT), timeout=SOCKET_TIMEOUT) as s:
            s.settimeout(SOCKET_TIMEOUT); s.sendall(data)
            buf=b""
            while True:
                chunk=s.recv(4096)
                if not chunk: break
                buf += chunk
                if b"\n" in buf:
                    line,_=buf.split(b"\n",1)
                    txt=line.decode(ENCODING, errors="replace").rstrip("\r").strip()
                    return json.loads(txt)
        raise RuntimeError("No response from server")

    def on_submit(self):
        self.clear_error()
        ok, payload_or_msg = self.validate()
        if not ok: self.show_error(payload_or_msg); return
        req = {"type":"AUTH.REGISTER_REQ","id":str(uuid.uuid4()),"payload":payload_or_msg}
        try:
            resp = self.jsonl_request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}"); return
        rtype = resp.get("type"); payload = resp.get("payload",{})
        if rtype == "AUTH.REGISTER_RES":
            QMessageBox.information(self,"Success","Account created! You can now log in.")
            for w in (self.in_name,self.in_email,self.in_username,self.in_password,self.in_area): w.clear()
        elif rtype == "ERROR":
            self.show_error(payload.get("message","Unknown error"))
        else:
            self.show_error(f"Unexpected response: {rtype}")

# =============================================================================
# Login form (uses shared session so the socket remains bound post-login)
# =============================================================================
class LoginForm(QWidget):
    logged_in = pyqtSignal(dict)  # emits user_preview dict

    def __init__(self, session: JsonlSession, parent=None):
        super().__init__(parent)
        self.session = session

        self.in_username = QLineEdit()
        self.in_password = QLineEdit(); self.in_password.setEchoMode(QLineEdit.Password)
        for w in (self.in_username, self.in_password): w.setMinimumWidth(250); w.setMaximumWidth(400)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignHCenter | Qt.AlignCenter)
        form.setContentsMargins(0,20,0,0)
        form.setHorizontalSpacing(15); form.setVerticalSpacing(10)
        form.addRow("Username:", self.in_username)
        form.addRow("Password:", self.in_password)

        self.err = QLabel(""); self.err.setWordWrap(True); self.err.setStyleSheet("color: red;"); self.err.setVisible(False)
        self.btn_login = QPushButton("Log into account"); self.btn_login.setMinimumWidth(120)
        self.btn_login.clicked.connect(self.on_submit)

        card = QWidget(); card.setObjectName("login_card")
        card.setStyleSheet("""
            QWidget#login_card { background: #fff; border: 1px solid #e5e5e5; border-radius: 12px; }
            QLineEdit { padding: 8px 10px; border: 1px solid #d0d0d0; border-radius: 6px; }
            QLineEdit:focus { border: 1px solid #7aa7ff; outline: none; }
        """)
        lay = QVBoxLayout(card); lay.setContentsMargins(30,20,30,20); lay.setSpacing(15)
        lay.addLayout(form); lay.addWidget(self.err); lay.addSpacing(8); lay.addWidget(self.btn_login,0,Qt.AlignHCenter)

        root = QVBoxLayout(self); root.setContentsMargins(0,0,0,0)
        root.addStretch(1); root.addWidget(card,0,Qt.AlignHCenter); root.addStretch(1)

    def show_error(self, msg): self.err.setText(msg); self.err.setVisible(True)
    def clear_error(self): self.err.setText(""); self.err.setVisible(False)

    def validate(self):
        u = self.in_username.text().strip()
        p = self.in_password.text().strip()
        if not u or not USERNAME_RE.match(u): return False, "Username is required."
        if not p or not PASSWORD_RE.match(p): return False, "Password is required."
        return True, {"username":u, "password":p}

    def on_submit(self):
        self.clear_error()
        ok, payload_or_msg = self.validate()
        if not ok:
            self.show_error(payload_or_msg); return
        req = {"type":"AUTH.LOGIN_REQ","id":str(uuid.uuid4()),"payload":payload_or_msg}
        try:
            resp = self.session.request(req)  # same socket stays open
        except Exception as e:
            self.show_error(f"Network error: {e}"); return
        rtype = resp.get("type"); payload = resp.get("payload",{})
        if rtype == "AUTH.LOGIN_RES":
            user_preview = payload.get("user", {})
            self.logged_in.emit(user_preview)
            self.in_username.clear(); self.in_password.clear()
        elif rtype == "ERROR":
            self.show_error(payload.get("message","Unknown error"))
        else:
            self.show_error(f"Unexpected response: {rtype}")

# =============================================================================
# ProfileScreen
# =============================================================================
class ProfileScreen(QWidget):
    driverModeChanged = pyqtSignal(bool)  # emit after successful save

    def __init__(self, session: JsonlSession, user_preview: dict, parent=None):
        super().__init__(parent)
        self.session = session

        self.snapshot = {
            "name": user_preview.get("name", ""),
            "email": user_preview.get("email", ""),
            "area": user_preview.get("area", ""),
            "is_driver": bool(user_preview.get("is_driver", False))
        }

        self.in_name = QLineEdit(self.snapshot["name"])
        self.in_email = QLineEdit(self.snapshot["email"])
        self.in_area = QLineEdit(self.snapshot["area"])
        self.chk_driver = QCheckBox("Driver Mode")
        self.chk_driver.setChecked(self.snapshot["is_driver"])

        for w in (self.in_name, self.in_email, self.in_area):
            w.setMinimumWidth(300); w.setMaximumWidth(420)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignHCenter | Qt.AlignTop)
        form.setHorizontalSpacing(14); form.setVerticalSpacing(10)
        form.addRow("Name:", self.in_name)
        form.addRow("Email:", self.in_email)
        form.addRow("Area:", self.in_area)
        form.addRow("", self.chk_driver)

        self.err = QLabel(""); self.err.setWordWrap(True); self.err.setStyleSheet("color: red;"); self.err.setVisible(False)
        self.ok = QLabel(""); self.ok.setWordWrap(True); self.ok.setStyleSheet("color: #0a7a0a;"); self.ok.setVisible(False)

        self.btn_edit = QPushButton("Edit")
        self.btn_save = QPushButton("Save")
        self.btn_cancel = QPushButton("Cancel")

        self.btn_edit.clicked.connect(self.on_edit)
        self.btn_save.clicked.connect(self.on_save)
        self.btn_cancel.clicked.connect(self.on_cancel)

        root = QVBoxLayout(self)
        root.addSpacing(10)
        root.addLayout(form)
        root.addWidget(self.err)
        root.addWidget(self.ok)
        root.addSpacing(8)
        buttons = QHBoxLayout()
        buttons.addWidget(self.btn_edit)
        buttons.addWidget(self.btn_save)
        buttons.addWidget(self.btn_cancel)
        root.addLayout(buttons)
        root.addStretch(1)

        self.set_edit_mode(False)

    def set_edit_mode(self, on: bool):
        editing = bool(on)
        for w in (self.in_name, self.in_email, self.in_area):
            w.setReadOnly(not editing)
        self.chk_driver.setEnabled(editing)

        self.btn_edit.setEnabled(not editing)
        self.btn_save.setEnabled(editing)
        self.btn_cancel.setEnabled(editing)

        self.setStyleSheet("QLineEdit:read-only { background: #f6f6f6; }")

    def reset_fields_from_snapshot(self):
        self.in_name.setText(self.snapshot["name"])
        self.in_email.setText(self.snapshot["email"])
        self.in_area.setText(self.snapshot["area"])
        self.chk_driver.setChecked(self.snapshot["is_driver"])

    def show_error(self, msg):
        self.err.setText(msg); self.err.setVisible(True); self.ok.setVisible(False)

    def show_ok(self, msg):
        self.ok.setText(msg); self.ok.setVisible(True); self.err.setVisible(False)

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

        payload = {
            "name": self.in_name.text().strip(),
            "email": self.in_email.text().strip(),
            "area": area,
            "is_driver": bool(self.chk_driver.isChecked())
        }
        req = {"type":"PROFILE.SET_REQ", "id": str(uuid.uuid4()), "payload": payload}
        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return

        if resp.get("type") == "PROFILE.SET_RES":
            prev_driver = self.snapshot["is_driver"]
            self.snapshot.update(payload)
            self.set_edit_mode(False)
            self.show_ok("Profile saved.")
            if prev_driver != self.snapshot["is_driver"]:
                self.driverModeChanged.emit(self.snapshot["is_driver"])
        elif resp.get("type") == "ERROR":
            self.show_error(resp.get("payload", {}).get("message", "Failed to save profile."))
        else:
            self.show_error(f"Unexpected response: {resp.get('type')}")

# =============================================================================
# ScheduleScreen
# =============================================================================
class ScheduleScreen(QWidget):
    """Driver schedule CRUD using persistent TCP connection."""
    def __init__(self, session: JsonlSession, parent=None):
        super().__init__(parent)
        self.session = session

        form = QHBoxLayout()

        self.cb_weekday = QComboBox()
        self.cb_weekday.addItems(["Sun", "Mon", "Tues", "Wed", "Thurs", "Fri", "Sat"])

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setKeyboardTracking(False)

        self.cb_direction = QComboBox()
        self.cb_direction.addItems(["to_AUB", "from_AUB"])

        self.in_area = QLineEdit()
        self.in_area.setPlaceholderText("e.g Hamra")
        self.btn_add = QPushButton("Add")
        self.btn_add.clicked.connect(self.on_add_slot)

        for w in (self.cb_weekday, self.time_edit, self.cb_direction, self.in_area, self.btn_add):
            form.addWidget(w)

        self.err = QLabel("")
        self.err.setWordWrap(True)
        self.err.setStyleSheet("color: red;")
        self.err.setVisible(False)

        self.ok = QLabel("")
        self.ok.setWordWrap(True)
        self.ok.setStyleSheet("color: green;")
        self.ok.setVisible(False)

        self.table = QTableWidget(0,4)
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

    def refresh(self):
        # remember currently selected schedule_id (if any)
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
            # store schedule_id here
            c0.setData(Qt.UserRole, item["schedule_id"])

            self.table.setItem(row, 0, c0)
            self.table.setItem(row, 1, QTableWidgetItem(item["depart_time"]))
            self.table.setItem(row, 2, QTableWidgetItem(item["direction"]))
            self.table.setItem(row, 3, QTableWidgetItem(item["area"]))

        # try to reselect previous schedule if it still exists
        if selected_sched_id is not None:
            for row in range(self.table.rowCount()):
                item0 = self.table.item(row, 0)
                if item0 is not None and item0.data(Qt.UserRole) == selected_sched_id:
                    self.table.setCurrentCell(row, 0)
                    break

        # up to you if you keep this; it will pop a dialog every refresh
        # self.show_ok(f"Loaded {len(items)} slots.")





    def on_add_slot(self):
        area = self.in_area.text().strip()
        if not area:
            self.show_error("Area is required")
            return
        payload = {
            "weekday": self._weekday_index(),
            "depart_time": self._time_str(),
            "direction": self.cb_direction.currentText(),
            "area": area
        }
        req = {"type": "SCHEDULE.SET_REQ", "id":str(uuid.uuid4()), "payload": payload}
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

        sid = self.table.item(r,0).data(Qt.UserRole)
        if not isinstance(sid, int):
            self.show_error("Internal error: missing schedule_id.")
            return
        req = {"type":"SCHEDULE.REMOVE_REQ", "id":str(uuid.uuid4()), "payload":{"schedule_id":sid}}
        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return

        if resp.get("type") == "SCHEDULE.REMOVE_RES":
            self.show_ok("Slot deleted.")
            self.refresh()
        else:
            self.show_error(resp.get("payload", {}).get("message","Failed to delete slot."))

# =============================================================================
# Passenger Ride Request Page
# =============================================================================
class RideRequestPage(QWidget):
    def __init__(self, session: JsonlSession, parent=None):
        super().__init__(parent)
        self.session = session

        self.current_request_id: str | None = None

        self.in_area = QLineEdit()
        self.in_area.setPlaceholderText("e.g Hamra")

        self.cb_direction = QComboBox()
        self.cb_direction.addItems(["to_AUB", "from_AUB"])

        self.dt = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.dt.setCalendarPopup(True)
        self.dt.setKeyboardTracking(False)

        self.btn_submit = QPushButton("Request Ride")
        self.btn_submit.clicked.connect(self.on_submit)

        self.btn_cancel = QPushButton("Cancel request")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.on_cancel_clicked)

        

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignCenter | Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        form.addRow("Area:", self.in_area)
        form.addRow("Direction:", self.cb_direction)
        form.addRow("Departure Time:", self.dt)

        self.err = QLabel("")
        self.err.setWordWrap(True)
        self.err.setStyleSheet("color: red;")
        self.err.setVisible(False)
        self.ok  = QLabel("")
        self.ok.setWordWrap(True)
        self.ok.setStyleSheet("color: #0a7a0a;")
        self.ok.setVisible(False)

        self.lbl_request_id = QLabel("Request ID: —")
        self.lbl_status     = QLabel("Status: —")

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

    def show_error(self, msg):
        self.err.setText(msg); self.err.setVisible(True); self.ok.setVisible(False)

    def show_ok(self, msg):
        self.ok.setText(msg); self.ok.setVisible(True); self.err.setVisible(False)

    def _iso_string(self) -> str:
        return self.dt.dateTime().toString("yyyy-MM-dd HH:mm")

    def on_submit(self):
        area = self.in_area.text().strip()
        if not area:
            self.show_error("Area is required.")
            return

        payload = {
            "area": area,
            "direction": self.cb_direction.currentText(),
            "time_iso": self._iso_string(),
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
            self.btn_cancel.setEnabled(True)
            self.btn_submit.setEnabled(False)

            self.lbl_request_id.setText(f"Request ID: {req_id}")
            
            self.lbl_status.setText(f"Status: open — compatible drivers found: {found}")
            self.show_ok("Ride request created.")

        elif rtype == "ERROR":
            code = p.get("code")
            msg = p.get("message", "Failed to create ride request")

            #self.show_error(p.get("message", "Failed to create ride request."))
            if code == "PASSENGER_BUSY":
                self.current_request_id = None
                self.btn_cancel.setEnabled(False)
            self.show_error(msg)
        else:
            self.show_error(f"Unexpected response: {rtype}")

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
            return

        elif rtype == "ERROR":
            code = payload.get("code")
            msg = payload.get("message", "Unknown error")
            
            if code == "INVALID_STATE":
                QMessageBox.information(self, "Cannot cancel", "Your request has already been accepted by a driver so it not longer can be cancelled.")
                return
            QMessageBox.warning(self, "Cancel failed", f"Server returned error: {code or 'ERROR'} - {msg}")
            return
        
        QMessageBox.warning(self, "Unexpected reply",
                    f"Unexpected response to cancel: {rtype}")
        

    def handle_matched(self, payload):
        self.lbl_status.setText("Status: A driver has accepted your request!")
        self.btn_cancel.setEnabled(False)

    def set_idle_state(self):
        """Reset the page to 'no active ride request' state."""
        self.current_request_id = None

        try:
            self.btn_cancel.setEnabled(False)
        except AttributeError:
            pass
        try:
            self.btn_submit.setEnabled(True)
            self.lbl_request_id.setText("Request ID: —")
            self.lbl_status.setText("Status: —")
        except AttributeError:
            pass
        try:
            self.lbl_status.setText("No active ride request.")
        except AttributeError:
            pass   

class DriverRidePage(QWidget):
    def __init__(self, session: JsonlSession, parent=None):
        super().__init__(parent)
        self.session = session

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Request ID", "Area", "Direction", "Departure Time"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        self.err = QLabel("")
        self.err.setWordWrap(True)
        self.err.setStyleSheet("color: red;")
        self.err.setVisible(False)

        self.ok = QLabel("")
        self.ok.setWordWrap(True)
        self.ok.setStyleSheet("color: #0a7a0a;")
        self.ok.setVisible(False)

        self.btn_refresh = QPushButton("Refresh now")
        self.btn_accept = QPushButton("Accept selected")

        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_accept.clicked.connect(self.on_accept_selected)

        top = QHBoxLayout()
        top.addWidget(self.btn_refresh)
        top.addWidget(self.btn_accept)
        top.addStretch(1)

        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(self.err)
        root.addWidget(self.ok)
        root.addSpacing(6)
        root.addWidget(self.table, 1)

        # auto-refresh every 5 seconds
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

        self.refresh()

    def show_error(self, msg):
        self.err.setText(msg)
        self.err.setVisible(True)
        self.ok.setVisible(False)

    def show_ok(self, msg):
        self.ok.setText(msg)
        self.ok.setVisible(True)
        self.err.setVisible(False)

    def refresh(self):
        req = {
            "type": "RIDE.LIST_REQ",
            "id": str(uuid.uuid4()),
            "payload": {},
        }
        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return

        if resp.get("type") != "RIDE.LIST_RES":
            self.show_error(resp.get("payload", {}).get("message", f"Unexpected response: {resp.get('type')}"))
            return

        items = resp.get("payload", {}).get("items", [])
        self.table.setRowCount(0)

        for item in items:
            row = self.table.rowCount()
            self.table.insertRow(row)

            req_id = item.get("request_id", "—")
            area = item.get("area", "—")
            direction = item.get("direction", "—")
            time_iso = item.get("time_iso", "—")

            c0 = QTableWidgetItem(req_id)
            # store raw request_id in UserRole, to send later
            c0.setData(Qt.UserRole, req_id)

            self.table.setItem(row, 0, c0)
            self.table.setItem(row, 1, QTableWidgetItem(area))
            self.table.setItem(row, 2, QTableWidgetItem(direction))
            self.table.setItem(row, 3, QTableWidgetItem(time_iso))

        self.show_ok(f"Loaded {len(items)} compatible requests.")

    def on_accept_selected(self):
        r = self.table.currentRow()
        if r < 0:
            self.show_error("Select a request to accept.")
            return

        item0 = self.table.item(r, 0)
        if item0 is None:
            self.show_error("Internal error: missing request id.")
            return

        req_id = item0.data(Qt.UserRole)
        if req_id is None:
            self.show_error("Internal error: invalid request id.")
            return

        req = {
            "type": "RIDE.ACCEPT_REQ",
            "id": str(uuid.uuid4()),
            "payload": {"request_id": req_id},
        }

        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return

        rtype = resp.get("type")
        payload = resp.get("payload", {})

        if rtype == "RIDE.ACCEPT_RES":
            self.show_ok(f"Accepted {req_id}.")
            self.table.clearSelection()
            self.refresh()
        elif rtype == "ERROR":
            code = payload.get("code")
            msg = payload.get("message", "Failed to accept request.")

            if code == "REQUEST_CLOSED":
                msg = "This request is no longer available (cancelled, matched, or expired)"
            
            self.show_error(msg)
            self.table.clearSelection()
            self.refresh()
        else:
            self.show_error(f"Unexpected response: {rtype}")
    
    def handle_request_closed(self, payload):
        QMessageBox.information(self, "Request Closed", "A ride request you accepted has been closed (cancelled by passenger or expired).")
        self.refresh()
    
    def add_broadcast(self, payload):
        self.refresh()


# =============================================================================
# Main window: wires everything together
# =============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AUBus")
        self.resize(1000, 650)

        # Persistent session (used by login + profile + schedule + ride)
        self.session = JsonlSession(HOST, PORT, SOCKET_TIMEOUT)
        self.session.push_reveived.connect(self.on_push_received)

        self.p2p_sock = None
        self.p2p_thread = None

        self.root = QStackedWidget()
        self.setCentralWidget(self.root)

        # ---- Auth Page ----
        auth_page = QWidget()
        v_auth = QVBoxLayout(auth_page)
        tabs = QTabWidget()
        self.login_tab = LoginForm(self.session)
        self.register_tab = RegisterForm()
        tabs.addTab(self.login_tab, "Login")
        tabs.addTab(self.register_tab, "Register")
        v_auth.addWidget(tabs, 1)
        self.root.addWidget(auth_page)

        # ---- App Page ----
        app_page = QWidget()
        self.root.addWidget(app_page)
        h = QHBoxLayout(app_page)

        left = QWidget()
        left_l = QVBoxLayout(left)
        self.btn_profile = QPushButton("Profile")
        self.btn_sched   = QPushButton("Schedule")
        self.btn_ride    = QPushButton("Ride")
        self.btn_logout = QPushButton("Logout")
        
        for b in (self.btn_profile, self.btn_sched, self.btn_ride):
            b.setCheckable(True)
            b.setAutoExclusive(True)
            left_l.addWidget(b)
        left_l.addStretch(1)

        left_l.addWidget(self.btn_logout)
        self.btn_logout.clicked.connect(self.on_logout)

        self.stack = QStackedWidget()
        # placeholders; will be replaced after login
        self.profile_page = title_page("Profile (login required)")
        self.schedule_page = title_page("Your Schedule")
        

        # index 0 → Profile (placeholder until login)
        self.profile_page = title_page("Profile (login required)")
        self.stack.addWidget(self.profile_page)              # index 0

        # index 1 → Schedule (placeholder until login)
        self.schedule_page = title_page("Your Schedule")
        self.stack.addWidget(self.schedule_page)             # index 1

        # index 2 → Ride (placeholder, will be swapped later)
        self.ride_page = RideRequestPage(self.session)
        self.stack.addWidget(self.ride_page)                 # index 2

        self.btn_profile.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.btn_sched.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.btn_ride.clicked.connect(lambda: self.stack.setCurrentIndex(2))

        self.btn_profile.setChecked(True)
        self.stack.setCurrentIndex(0)

        h.addWidget(left)
        h.addWidget(self.stack, 1)

        # connect login signal
        self.login_tab.logged_in.connect(self.after_login)

        # Schedule initially disabled until we know driver mode
        self.set_schedule_enabled(False)

    def set_schedule_enabled(self, on: bool):
        self.btn_sched.setEnabled(bool(on))
        if hasattr(self, "schedule_page"):
            self.schedule_page.setEnabled(bool(on))

    def after_login(self, user_preview: dict):
        # Profile screen
        profile = ProfileScreen(self.session, user_preview)
        profile.driverModeChanged.connect(self.on_driver_mode_changed)

        # replace profile page at index 0
        self.stack.removeWidget(self.profile_page)
        self.profile_page.deleteLater()
        self.profile_page = profile
        self.stack.insertWidget(0, self.profile_page)

        # replace schedule page at index 1
        self.stack.removeWidget(self.schedule_page)
        self.schedule_page.deleteLater()
        self.schedule_page = ScheduleScreen(self.session)
        self.stack.insertWidget(1, self.schedule_page)

        # initial driver mode from server
        is_driver = bool(user_preview.get("is_driver", False))
        self.on_driver_mode_changed(is_driver)

        # switch to app
        self.root.setCurrentIndex(1)
        self.btn_profile.setChecked(True)
        self.stack.setCurrentIndex(0)


    def on_driver_mode_changed(self, is_driver: bool):
        # enable/disable Schedule tab
        self.set_schedule_enabled(is_driver)

        # P2P listener follows driver mode
        if is_driver:
            self.start_p2p_listener()
        else:
            self.stop_p2p_listener()

        # swap ride page (index 2) between driver/passenger views
        if hasattr(self, "ride_page"):
            self.stack.removeWidget(self.ride_page)
            self.ride_page.deleteLater()

        if is_driver:
            self.ride_page = DriverRidePage(self.session)
        else:
            self.ride_page = RideRequestPage(self.session)

        self.stack.insertWidget(2, self.ride_page)

    def closeEvent(self, event):
        """on window close, logout cleanly and close the session"""
        try:
            if self.session is not None:
                req = {
                    "type": "AUTH.LOGOUT_REQ",
                    "id": str(uuid.uuid4()),
                    "payload": {}
                }
                try:
                    # best-effort logout; ignore errors
                    self.session.request(req)
                except Exception:
                    pass

                try:
                    self.stop_p2p_listener() 
                    self.session.close()
                except Exception:
                    pass
        finally:
            super().closeEvent(event)
            
    def on_logout(self):
        try:
            req = {"type": "AUTH.LOGOUT_REQ",
               "id": str(uuid.uuid4()),
               "payload": {}}
            self.session.request(req)
        except Exception:
            # If network fails, still locally reset
            pass

        self.stop_p2p_listener() #stop p2p

        if isinstance(self.ride_page, DriverRidePage):
            self.ride_page.timer.stop()  # stop auto-refresh timer

        self.set_schedule_enabled(False)
        self.root.setCurrentIndex(0)
        self.btn_profile.setChecked(False)
        self.btn_sched.setChecked(False)
        self.btn_ride.setChecked(False)

    def start_p2p_listener(self):
        """Start a simple TCP listener for driver P2P and announce it via PEER.OPEN_REQ."""
        # If already running, do nothing
        if self.p2p_sock is not None:
            return

        try:
            # 1) create listening socket on an ephemeral port
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", 0))   # OS chooses port
            s.listen(1)
            port = s.getsockname()[1]
            self.p2p_sock = s

            # 2) tell server where we are listening
            req = {
                "type": "PEER.OPEN_REQ",
                "id": str(uuid.uuid4()),
                "payload": {
                    "p2p_port": port
                    # we could also send external_ip/external_port if we knew them
                }
            }
            try:
                resp = self.session.request(req)
            except Exception as e:
                # if this fails, just log and shut listener down
                print(f"PEER.OPEN_REQ failed: {e}")
                s.close()
                self.p2p_sock = None
                return

            if resp.get("type") != "PEER.OPEN_RES":
                # server rejected; clean up
                print(f"PEER.OPEN_RES error: {resp}")
                s.close()
                self.p2p_sock = None
                return

            # 3) spin a background thread just to accept connections
            def _p2p_loop(listener: socket.socket):
                try:
                    while True:
                        conn, addr = listener.accept()
                        # minimal behavior: immediately close, or print
                        print(f"P2P connection from {addr}, closing.")
                        conn.close()
                except Exception:
                    # any error → exit thread
                    pass

            t = threading.Thread(target=_p2p_loop, args=(s,), daemon=True)
            t.start()
            self.p2p_thread = t

            print(f"P2P listener started on port {port}")

        except Exception as e:
            print(f"start_p2p_listener failed: {e}")
            if self.p2p_sock:
                self.p2p_sock.close()
            self.p2p_sock = None
            self.p2p_thread = None


    def stop_p2p_listener(self):
        """Stop driver P2P listener if running."""
        if self.p2p_sock is not None:
            try:
                self.p2p_sock.close()
            except Exception:
                pass
        self.p2p_sock = None
        self.p2p_thread = None
    
    def on_push_received(self, msg: dict):
        t = msg.get("type")

        if t == "RIDE.MATCHED":
            self.on_ride_matched(msg)
        
        elif t == "REQUEST_CLOSED":
            self.on_request_closed(msg)
        
        elif t == "DRIVER.BROADCAST":
            self.on_driver_broadcast(msg)
    
    def on_ride_matched(self, msg: dict):
        payload = msg.get("payload", {})
        if isinstance(self.ride_page, RideRequestPage):
            self.ride_page.handle_matched(payload)
    
    def on_request_closed(self, msg: dict):
        if isinstance(self.ride_page, DriverRidePage):
            self.ride_page.handle_request_closed("payload", {})
    
    def on_driver_broadcast(self, msg: dict):
        if isinstance(self.ride_page, DriverRidePage):
            self.ride_page.add_broadcast(msg.get("payload", {}))
    








def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
