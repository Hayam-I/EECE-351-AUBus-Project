import sys
import traceback
import json
import re
import socket
import uuid
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget, QFormLayout,
    QLineEdit, QMessageBox, QCheckBox, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTimeEdit, QDateTimeEdit, QDialog, QTextEdit
)
from PyQt5.QtCore import Qt, pyqtSignal, QDateTime, QTimer

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


def apply_bento_theme(app: QApplication):
    app.setStyle("Fusion")  # more modern base style

    app.setStyleSheet("""
    /* ====== Global background ====== */
    QMainWindow#MainWindow, QWidget {
        background-color: #020617; /* very dark navy */
        color: #e5e7eb;
        font-family: "Segoe UI", system-ui, sans-serif;
        font-size: 10pt;
    }

    /* ====== Sidebar ====== */
    QWidget#SideBar {
        background-color: #020617;
        border-right: 1px solid #1f2937;
    }

    QWidget#SideBar QPushButton {
        background-color: transparent;
        border: none;
        color: #9ca3af;
        padding: 8px 14px;
        text-align: left;
        border-radius: 10px;
    }

    QWidget#SideBar QPushButton:hover {
        background-color: rgba(99,102,241,0.18); /* soft indigo */
        color: #e5e7eb;
    }

    QWidget#SideBar QPushButton:checked {
        background-color: #4f46e5; /* primary indigo */
        color: #f9fafb;
    }

    /* ====== Cards / panels ====== */
    QStackedWidget, QWidget#login_card, QWidget#register_card {
        background-color: #020617;
        border-radius: 18px;
    }

    QWidget#login_card, QWidget#register_card {
        border: 1px solid rgba(148,163,184,0.35);
        background-color: qlineargradient(
            x1:0, y1:0, x2:1, y2:1,
            stop:0 #020617,
            stop:1 #020617
        );
    }
    
    QLabel {
        color: #e5e7eb;
        background-color: transparent;   /* <<< this removes the black box */
        border: none;
    }

    QLabel#page_title {
        font-size: 18pt;
        font-weight: 600;
        color: #e5e7eb;
    }

    /* ====== Inputs ====== */
    QLineEdit, QTimeEdit, QDateTimeEdit, QComboBox {
        background-color: rgba(255,255,255,0.04);
        border: 1px solid rgba(148,163,184,0.25); 
        border-radius: 8px;
        padding: 6px 10px;
        color: #e5e7eb;
        selection-background-color: #4f46e5;
        selection-color: #f9fafb;
    }

    QLineEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus, QComboBox:focus {
        border: 1px solid #6366f1;
        box-shadow: 0px 0px 6px rgba(99,102,241,0.45);
        background-color: rgba(255,255,255,0.07);
    }

    QComboBox QAbstractItemView {
        background-color: #020617;
        border: 1px solid #1f2937;
        selection-background-color: #4f46e5;
        selection-color: #f9fafb;
    }

    /* ====== Primary / secondary buttons ====== */
    QPushButton {
        background-color: #111827;
        color: #e5e7eb;
        border-radius: 10px;
        padding: 6px 14px;
        border: 1px solid #1f2937;
    }

    QPushButton:hover {
        background-color: #1f2937;
        border-color: #4b5563;
    }

    QPushButton:pressed {
        background-color: #4f46e5;
        border-color: #4f46e5;
        color: #f9fafb;
    }

    QPushButton:disabled {
        background-color: #020617;
        color: #4b5563;
        border-color: #111827;
    }

    /* ====== Tables ====== */
    QTableWidget {
        background-color: #020617;
        alternate-background-color: #020617;
        border: 1px solid #111827;
        border-radius: 14px;
        gridline-color: #111827;
        selection-background-color: rgba(129,140,248,0.25);
        selection-color: #f9fafb;
    }

    QHeaderView::section {
        background-color: #020617;
        color: #9ca3af;
        padding: 6px 8px;
        border: none;
        border-bottom: 1px solid #111827;
    }

    QTableCornerButton::section {
        background-color: #020617;
        border: none;
    }

    /* Scrollbars (subtle) */
    QScrollBar:vertical, QScrollBar:horizontal {
        background: #020617;
        border-radius: 4px;
        width: 10px;
        height: 10px;
        margin: 2px;
    }

    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
        background: #111827;
        border-radius: 4px;
    }

    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
        background: #4b5563;
    }

    QScrollBar::add-line, QScrollBar::sub-line {
        width: 0;
        height: 0;
        background: transparent;
    }

    /* Status labels */
    QLabel {
        color: #e5e7eb;
    }

    QLabel[style*="color: red"] {
        color: #f97373;
    }

    QLabel[style*="#0a7a0a"] {
        color: #4ade80;
    }

    QTabWidget::pane {
        border: 1px solid #111827;
        border-radius: 14px;
        background-color: #020617;
    }

    QTabBar::tab {
        background-color: transparent;
        color: #9ca3af;
        padding: 6px 16px;
        border-radius: 10px;
        margin: 4px;
    }

    QTabBar::tab:selected {
        background-color: #4f46e5;
        color: #f9fafb;
    }

    QTabBar::tab:hover {
        background-color: rgba(79,70,229,0.25);
        color: #e5e7eb;
    }
    """)



# ===== validation regex (mirror server) =====
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,20}$")
PASSWORD_RE = re.compile(r"^.{6,20}$")
EMAIL_RE    = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

# =============================================================================
# Persistent JSONL session (one TCP connection per client after login)
# =============================================================================
class JsonlSession:
    def __init__(self, host: str, port: int, timeout: float = 4.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: socket.socket | None = None

    def ensure_connected(self):
        if self.sock is not None:
            return
        s = socket.create_connection((self.host, self.port), timeout=self.timeout)
        s.settimeout(self.timeout)
        self.sock = s

    def request(self, obj: dict) -> dict:
        """Send 1 request, wait for 1 response, over the SAME socket."""
        self.ensure_connected()
        send_json(self.sock, obj)
        return recv_json(self.sock)

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

        card = QWidget()
        card.setObjectName("register_card")
        card.setStyleSheet("""
            QWidget#register_card {
                background-color: qradialgradient(
                    cx:0.1, cy:0.0, radius:1.4,
                    fx:0.0, fy:0.0,
                    stop:0  rgba(129,140,248,0.25),
                    stop:0.4 rgba(24,31,81,0.90),
                    stop:1  #020617
                );
                border-radius: 20px;
                border: 1px solid rgba(148,163,184,0.45);
            }
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

        card = QWidget()
        card.setObjectName("login_card")
        card.setStyleSheet("""
            QWidget#login_card {
                background-color: qradialgradient(
                    cx:0.9, cy:0.0, radius:1.4,
                    fx:1.0, fy:0.0,
                    stop:0  rgba(236,72,153,0.25),
                    stop:0.4 rgba(24,31,81,0.90),
                    stop:1  #020617
                );
                border-radius: 20px;
                border: 1px solid rgba(148,163,184,0.45);
            }
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

        self.setStyleSheet("""
            QLineEdit {
                background-color: #020617;
                border: 1px solid #1f2937;
                border-radius: 10px;
                padding: 6px 10px;
                color: #e5e7eb;
            }
            QLineEdit:read-only {
                background-color: #020617;
                color: #9ca3af;
            }
            QCheckBox {
                color: #e5e7eb;
            }
        """)


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
            self.show_error(resp.get("payload", {}).get("message",
                            f"Unexpected response: {resp.get('type')}"))
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
            c0.setData(Qt.UserRole, item["schedule_id"])   # schedule_id stored here

            self.table.setItem(row, 0, c0)
            self.table.setItem(row, 1, QTableWidgetItem(item["depart_time"]))
            self.table.setItem(row, 2, QTableWidgetItem(item["direction"]))
            self.table.setItem(row, 3, QTableWidgetItem(item["area"]))

        self.show_ok(f"Loaded {len(items)} slots.")



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

        # NEW: chat button
        self.btn_chat = QPushButton("Open chat")
        self.btn_chat.setEnabled(False)
        self.btn_chat.clicked.connect(self.on_open_chat)

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

        self.current_request_id = None

        root = QVBoxLayout(self)
        root.addLayout(form)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.btn_submit)
        row.addWidget(self.btn_chat)   # chat button here
        row.addStretch(1)
        root.addLayout(row)

        root.addSpacing(10)
        root.addWidget(self.err)
        root.addWidget(self.ok)
        root.addSpacing(12)
        root.addWidget(self.lbl_request_id)
        root.addWidget(self.lbl_status)
        root.addStretch(1)

    def show_error(self, msg):
        self.err.setText(msg); self.err.setVisible(True); self.ok.setVisible(False)

    def show_ok(self, msg):
        self.ok.setText(msg); self.ok.setVisible(True); self.err.setVisible(False)

    def _iso_string(self) -> str:
        return self.dt.dateTime().toString("yyyy-MM-dd HH:mm")
    
    def on_open_chat(self):
        if not self.current_request_id:
            self.show_error("No active request to chat about.")
            return
        dlg = ChatDialog(self.session, self.current_request_id, self)
        dlg.exec_()


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
            req_id = p.get("request_id", "—")
            self.current_request_id = req_id
            self.btn_chat.setEnabled(True)
            found  = p.get("candidates_found", 0)
            self.lbl_request_id.setText(f"Request ID: {req_id}")
            self.lbl_status.setText(f"Status: open — compatible drivers found: {found}")
            self.show_ok("Ride request created.")
        elif rtype == "ERROR":
            self.show_error(p.get("message", "Failed to create ride request."))
        else:
            self.show_error(f"Unexpected response: {rtype}")

class DriverRidePage(QWidget):
    def __init__(self, session: JsonlSession, parent=None):
        super().__init__(parent)
        self.session = session

        # ---- Accepted rides (active) ----
        self.lbl_matches = QLabel("Accepted rides (active):")

        self.table_matches = QTableWidget(0, 4)
        self.table_matches.setHorizontalHeaderLabels(["Req ID", "Area", "Direction", "Time"])
        self.table_matches.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table_matches.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_matches.setSelectionMode(QTableWidget.SingleSelection)

        self.btn_matches_refresh = QPushButton("Refresh accepted")
        self.btn_matches_complete = QPushButton("Complete / remove selected")
        self.btn_open_chat = QPushButton("Open chat")

        self.btn_matches_refresh.clicked.connect(self.refresh_matches)
        self.btn_matches_complete.clicked.connect(self.on_complete_selected)
        self.btn_open_chat.clicked.connect(self.on_open_chat)

        btns_matches = QHBoxLayout()
        btns_matches.addWidget(self.btn_matches_refresh)
        btns_matches.addWidget(self.btn_matches_complete)
        btns_matches.addStretch(1)
        btns_matches.addWidget(self.btn_open_chat)

        # ---- Open requests table ----
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Request ID", "Area", "Direction", "Departure Time"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        self.btn_refresh = QPushButton("Refresh now")
        self.btn_accept = QPushButton("Accept selected")
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_accept.clicked.connect(self.on_accept_selected)

        top = QHBoxLayout()
        top.addWidget(self.btn_refresh)
        top.addWidget(self.btn_accept)
        top.addStretch(1)

        # ---- Status labels ----
        self.err = QLabel("")
        self.err.setWordWrap(True)
        self.err.setStyleSheet("color: red;")
        self.err.setVisible(False)

        self.ok = QLabel("")
        self.ok.setWordWrap(True)
        self.ok.setStyleSheet("color: #0a7a0a;")
        self.ok.setVisible(False)

        # ---- Root layout ----
        root = QVBoxLayout(self)
        root.addSpacing(16)
        root.addWidget(self.lbl_matches)
        root.addWidget(self.table_matches, 1)
        root.addLayout(btns_matches)
        root.addSpacing(10)
        root.addLayout(top)
        root.addWidget(self.err)
        root.addWidget(self.ok)
        root.addSpacing(6)
        root.addWidget(self.table, 1)

        # manual refresh only for now (timer caused response mix-ups)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self._periodic_refresh)
        self.timer.start()

    # ---------------- helpers ----------------
    def show_error(self, msg):
        self.err.setText(msg)
        self.err.setVisible(True)
        self.ok.setVisible(False)

    def show_ok(self, msg):
        self.ok.setText(msg)
        self.ok.setVisible(True)
        self.err.setVisible(False)

    def _periodic_refresh(self):
        self.refresh(preserve_selection=True)
        self.refresh_matches(preserve_selection=True)




    # ---------------- accepted rides (matches) ----------------
    def refresh_matches(self, preserve_selection: bool = False):
        """Load all active matches for this driver."""
        # --- save selection (optional) ---
        selected_req_id = None
        if preserve_selection:
            r = self.table_matches.currentRow()
            if r >= 0:
                item0 = self.table_matches.item(r, 0)
                if item0 is not None:
                    selected_req_id = item0.data(Qt.UserRole) or item0.text()

        req = {
            "type": "RIDE.DRIVER_MATCHES_REQ",
            "id": str(uuid.uuid4()),
            "payload": {},
        }
        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error (matches): {e}")
            return

        if resp.get("type") != "RIDE.DRIVER_MATCHES_RES":
            self.show_error(resp.get("payload", {}).get(
                "message", f"Unexpected response: {resp.get('type')}"
            ))
            return

        items = resp.get("payload", {}).get("items", [])
        self.table_matches.setRowCount(0)

        # --- rebuild table ---
        for item in items:
            row = self.table_matches.rowCount()
            self.table_matches.insertRow(row)

            req_id = item.get("request_id", "—")
            area = item.get("area", "—")
            direction = item.get("direction", "—")
            time_iso = item.get("time_iso", "—")

            c0 = QTableWidgetItem(req_id)
            c0.setData(Qt.UserRole, req_id)

            self.table_matches.setItem(row, 0, c0)
            self.table_matches.setItem(row, 1, QTableWidgetItem(area))
            self.table_matches.setItem(row, 2, QTableWidgetItem(direction))
            self.table_matches.setItem(row, 3, QTableWidgetItem(time_iso))

        # --- restore selection if possible ---
        if preserve_selection and selected_req_id:
            for row in range(self.table_matches.rowCount()):
                item0 = self.table_matches.item(row, 0)
                if not item0:
                    continue
                value = item0.data(Qt.UserRole) or item0.text()
                if value == selected_req_id:
                    self.table_matches.selectRow(row)
                    break

        self.show_ok(f"Loaded {len(items)} accepted rides.")


    def on_complete_selected(self):
        """Mark an accepted ride as completed/removed."""
        r = self.table_matches.currentRow()
        if r < 0:
            self.show_error("Select an accepted ride to complete/remove.")
            return

        item0 = self.table_matches.item(r, 0)
        if not item0:
            self.show_error("Internal error: missing request_id.")
            return

        req_id = item0.data(Qt.UserRole) or item0.text()
        if not isinstance(req_id, str) or not req_id.startswith("req_"):
            self.show_error("Internal error: invalid request_id.")
            return

        req = {
            "type": "RIDE.COMPLETE_REQ",
            "id": str(uuid.uuid4()),
            "payload": {"request_id": req_id},
        }
        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error (complete): {e}")
            return

        if resp.get("type") == "RIDE.COMPLETE_RES":
            self.show_ok(f"Ride {req_id} marked as completed.")
            self.table_matches.clearSelection()
            self.refresh_matches()
        else:
            self.show_error(resp.get("payload", {}).get("message",
                             "Failed to complete ride."))

    # ---------------- open requests (to accept) ----------------
    def refresh(self, preserve_selection: bool = False):
        """Load compatible open ride requests for this driver."""
        selected_req_id = None
        if preserve_selection:
            r = self.table.currentRow()
            if r >= 0:
                item0 = self.table.item(r, 0)
                if item0 is not None:
                    selected_req_id = item0.data(Qt.UserRole)

        req = {
            "type": "RIDE.DRIVER_OPEN_REQS_REQ",
            "id": str(uuid.uuid4()),
            "payload": {},
        }
        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return

        if resp.get("type") != "RIDE.DRIVER_OPEN_REQS_RES":
            self.show_error(resp.get("payload", {}).get(
                "message", f"Unexpected response: {resp.get('type')}"
            ))
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
            c0.setData(Qt.UserRole, req_id)  # store raw request_id

            self.table.setItem(row, 0, c0)
            self.table.setItem(row, 1, QTableWidgetItem(area))
            self.table.setItem(row, 2, QTableWidgetItem(direction))
            self.table.setItem(row, 3, QTableWidgetItem(time_iso))

        # re-select previously selected request if it still exists
        if preserve_selection and selected_req_id:
            for row in range(self.table.rowCount()):
                item0 = self.table.item(row, 0)
                if item0 and item0.data(Qt.UserRole) == selected_req_id:
                    self.table.selectRow(row)
                    break

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
        if not isinstance(req_id, str):
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
            self.refresh_matches()
        elif rtype == "ERROR":
            self.show_error(payload.get("message", "Failed to accept request."))
        else:
            self.show_error(f"Unexpected response: {rtype}")

    # ---------------- chat ----------------
    def on_open_chat(self):
        r = self.table_matches.currentRow()
        if r < 0:
            self.show_error("Select an accepted ride to chat.")
            return

        item0 = self.table_matches.item(r, 0)
        if not item0:
            self.show_error("Internal error: missing request_id.")
            return

        req_id = item0.data(Qt.UserRole) or item0.text()
        if not isinstance(req_id, str) or not req_id.startswith("req_"):
            self.show_error("Internal error: invalid request_id.")
            return

        dlg = ChatDialog(self.session, req_id, self)
        dlg.exec_()


class RidePage(QWidget):
    def __init__(self, session: JsonlSession, parent=None):
        super().__init__(parent)
        self.session = session

        self.tabs = QTabWidget()
        self.passenger_page = RideRequestPage(session)
        self.driver_page = DriverRidePage(session)

        self.tabs.addTab(self.passenger_page, "Passenger")
        self.tabs.addTab(self.driver_page, "Driver")
        # driver tab disabled by default until we know driver mode
        self.tabs.setTabEnabled(1, False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)


class ChatDialog(QDialog):
    def __init__(self, session: JsonlSession, request_id: str, parent=None):
        super().__init__(parent)
        self.session = session
        self.request_id = request_id
        self.last_message_id = 0

        self.setWindowTitle(f"Chat – {request_id}")
        self.resize(400, 300)

        self.view = QTextEdit()
        self.view.setReadOnly(True)

        self.input = QLineEdit()
        self.btn_send = QPushButton("Send")
        self.btn_send.clicked.connect(self.send_message)

        row = QHBoxLayout()
        row.addWidget(self.input, 1)
        row.addWidget(self.btn_send)

        layout = QVBoxLayout(self)
        layout.addWidget(self.view, 1)
        layout.addLayout(row)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_messages)
        self.timer.start(1500)  # 1.5s

        self.poll_messages()  # initial load

    def append_message(self, sender: str, text: str):
        self.view.append(f"<b>{sender}:</b> {text}")

    def send_message(self):
        text = self.input.text().strip()
        if not text:
            return
        req = {
            "type": "RIDE.CHAT_SEND_REQ",
            "id": str(uuid.uuid4()),
            "payload": {"request_id": self.request_id, "text": text},
        }
        try:
            resp = self.session.request(req)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Network error: {e}")
            return

        if resp.get("type") == "RIDE.CHAT_SEND_RES":
            self.input.clear()
            self.poll_messages()
        else:
            QMessageBox.warning(
                self,
                "Error",
                resp.get("payload", {}).get("message", "Failed to send message"),
            )

    def poll_messages(self):
        req = {
            "type": "RIDE.CHAT_POLL_REQ",
            "id": str(uuid.uuid4()),
            "payload": {"request_id": self.request_id, "after_message_id": self.last_message_id},
        }
        try:
            resp = self.session.request(req)
        except Exception:
            # don't spam errors while polling
            return

        if resp.get("type") != "RIDE.CHAT_POLL_RES":
            return

        msgs = resp.get("payload", {}).get("messages", [])
        for m in msgs:
            mid_int = m.get("message_id", 0)
            sender = m.get("sender_user_id", "?")
            text = m.get("text", "")
            self.append_message(sender, text)
            self.last_message_id = max(self.last_message_id, mid_int)

# =============================================================================
# Main window: wires everything together
# =============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AUBus")
        self.setObjectName("MainWindow")
        self.resize(1000, 650)

        # Persistent session (used by login + profile + schedule + ride)
        self.session = JsonlSession(HOST, PORT, SOCKET_TIMEOUT)

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
        left.setObjectName("SideBar")
        left_l = QVBoxLayout(left)
        self.btn_profile = QPushButton("Profile")
        self.btn_sched   = QPushButton("Schedule")
        self.btn_ride    = QPushButton("Ride")
        self.btn_chat    = QPushButton("Chat")
        for b in (self.btn_profile, self.btn_sched, self.btn_ride, self.btn_chat):
            b.setCheckable(True)
            b.setAutoExclusive(True)
            left_l.addWidget(b)
        left_l.addStretch(1)

        self.stack = QStackedWidget()
        # placeholders; will be replaced after login
        self.profile_page = title_page("Profile (login required)")
        self.schedule_page = title_page("Your Schedule")
        self.ride_page = RidePage(self.session)

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
        self.btn_chat.clicked.connect(self.on_chat_clicked)


        self.btn_profile.setChecked(True)
        self.stack.setCurrentIndex(0)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(16, 16, 16, 16)
        center_layout.addWidget(self.stack)

        h.addWidget(left)
        h.addWidget(center, 1)

        # connect login signal
        self.login_tab.logged_in.connect(self.after_login)

        # Schedule initially disabled until we know driver mode
        self.set_schedule_enabled(False)

    def set_schedule_enabled(self, on: bool):
        self.btn_sched.setEnabled(bool(on))
        if hasattr(self, "schedule_page"):
            self.schedule_page.setEnabled(bool(on))
    
    def on_chat_clicked(self):
        # Show the Ride page (index 2 in the stack)
        self.stack.setCurrentIndex(2)

        # Mark Chat as selected in the sidebar
        self.btn_chat.setChecked(True)

        # Focus the driver side and its accepted-rides table as “chat options”
        if hasattr(self, "ride_page") and hasattr(self.ride_page, "driver_page"):
            # switch to driver tab if your RidePage uses tabs
            if hasattr(self.ride_page, "tabs"):
                self.ride_page.tabs.setCurrentWidget(self.ride_page.driver_page)
            # put keyboard focus on the accepted rides list
            self.ride_page.driver_page.table_matches.setFocus()


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

        # remove old ride page (whatever it was)
        if hasattr(self, "ride_page"):
            self.stack.removeWidget(self.ride_page)
            self.ride_page.deleteLater()

        # create the correct ride page for current mode
        if is_driver:
            self.ride_page = DriverRidePage(self.session)
        else:
            self.ride_page = RideRequestPage(self.session)

        # insert it at index 2 (Ride tab)
        self.stack.insertWidget(2, self.ride_page)


def main():
    app = QApplication(sys.argv)

    # APPLY THE THEME HERE
    apply_bento_theme(app)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
