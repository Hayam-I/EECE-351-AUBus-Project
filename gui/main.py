import sys
import traceback
import json
import re
import socket
import uuid
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget, QFormLayout,
    QLineEdit, QMessageBox, QCheckBox, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QTimeEdit
)
from PyQt5.QtCore import Qt, pyqtSignal

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
# We’ll reuse the JSONL send/recv, but manage a persistent socket here.
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
# Register form (unchanged, still does one-shot call – safe pre-login)
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
# Login form (uses session so the socket remains bound post-login)
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
        if not ok: self.show_error(payload_or_msg); return
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
# ProfileScreen – editable fields + Driver Mode toggle + Save + Edit + Cancel (added last two)
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

        # initial values from login
        # self.init_user = user_preview or {}
        # self.current_is_driver = bool(self.init_user.get("is_driver", False))
        # self.current_area = self.init_user.get("area") or ""

        # UI fields (keep minimal for P1-06)
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
        #read only vs edit mode
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

    def show_error(self, msg): self.err.setText(msg); self.err.setVisible(True); self.ok.setVisible(False)
    def show_ok(self, msg): self.ok.setText(msg); self.ok.setVisible(True); self.err.setVisible(False)

    # def on_save(self):
        # minimal client-side validate
        # name = self.in_name.text().strip()
        # email = self.in_email.text().strip()
        # area = self.in_area.text().strip()
        # is_driver = self.chk_driver.isChecked()
        # if not area:
        #     self.show_error("Area is required."); return

        # req = {
        #     "type": "PROFILE.SET_REQ",
        #     "id": str(uuid.uuid4()),
        #     "payload": {
        #         "is_driver": bool(is_driver),
        #         "area": area,
        #         # vehicle is optional in v1
        #         # "vehicle": {...}
        #         "name": name,     # server currently stores name/email on users table
        #         "email": email
        #     }
        # }
        # try:
        #     resp = self.session.request(req)
        # except Exception as e:
        #     self.show_error(f"Network error: {e}")
        #     return

        # if resp.get("type") == "PROFILE.SET_RES":
        #     self.show_ok("Profile saved.")
        #     # notify parent to enable/disable Schedule
        #     self.driverModeChanged.emit(is_driver)
        # elif resp.get("type") == "ERROR":
        #     self.show_error(resp.get("payload", {}).get("message", "Error saving profile"))
        # else:
        #     self.show_error(f"Unexpected response: {resp.get('type')}")


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
            self.show_error(resp.get("payload", {})).get("message", "Failed to save profile.")
        else:
            self.show_error(f"Unexpected response: {resp.get('type')}")
                
class ScheduleScreen(QWidget):
    """adding schedule into a table, be able to delete from that table, driver mode has to be on, persistent TCP connection (to make sure user is logged in)"""
    def __init__(self, session: JsonlSession, parent = None):
        super().__init__(parent)
        self.session = session

        form = QHBoxLayout()

        self.cb_weekday = QComboBox()
        self.cb_weekday.addItems(["Sun", "Mon", "Tues", "Wed", "Thurs", "Fri", "Sat"])

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setKeyboardTracking(False) #save selection when the user leaves it, or clicks enter/tab

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
        req = {"type": "SCHEDULE.LIST_REQ", "id": str(uuid.uuid4()), "payload":{}}
        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return
        if resp.get("type") != "SCHEDULE.LIST_RES":
            self.show_error(resp.get("payload", {}).get("message", f"Unexpected response: {resp.get('type')}"))
            return
        
        items = resp.get("payload",{}).get("items", [])
        self.table.setRowCount(0)
        for item in items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            wd = ["Sun", "Mon", "Tues", "Wed", "Thurs", "Fri", "Sat"][item["weekday"]] if 0 <= item["weekday"] <= 6 else str(item["weekday"])

            c0 = QTableWidgetItem(wd)
            c0.setData(Qt.UserRole, item["schedule_id"])
            self.table.setItem(row,0,c0)
            self.table.setItem(row,1,QTableWidgetItem(item["depart_time"]))
            self.table.setItem(row,2,QTableWidgetItem(item["direction"]))
            self.table.setItem(row,3,QTableWidgetItem(item["area"]))

        self.show_ok(f"Loaded {len(items)} slots.")

    def on_add_slot(self):
        area = self.in_area.text().strip()
        if not area:
            self.show_error("Area is required")
            return
        payload = {
            "weekday":self._weekday_index(),
            "depart_time": self._time_str(),
            "direction": self.cb_direction.currentText(),
            "area":area
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
# Ride placeholder
# =============================================================================
class RidePage(QWidget):
    def __init__(self):
        super().__init__()
        h = QHBoxLayout(self)
        nav = QVBoxLayout()
        self.btn_overview = QPushButton("Overview")
        self.btn_chat = QPushButton("Chat")
        self.btn_rate = QPushButton("Ratings")
        for b in (self.btn_overview, self.btn_chat, self.btn_rate):
            b.setCheckable(True); b.setAutoExclusive(True); nav.addWidget(b)
        nav.addStretch(1)

        self.sub = QStackedWidget()
        self.sub.addWidget(title_page("Ride - Overview"))
        self.sub.addWidget(title_page("Ride - Chat"))
        self.sub.addWidget(title_page("Ride - Ratings"))

        self.btn_overview.clicked.connect(lambda: self.sub.setCurrentIndex(0))
        self.btn_chat.clicked.connect(lambda: self.sub.setCurrentIndex(1))
        self.btn_rate.clicked.connect(lambda: self.sub.setCurrentIndex(2))

        self.btn_overview.setChecked(True); self.sub.setCurrentIndex(0)

        left = QWidget(); left.setLayout(nav); left.setMinimumWidth(160)
        h.addWidget(left); h.addWidget(self.sub, 1)

# =============================================================================
# Main window: wires everything together
# =============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AUBus"); self.resize(1000, 650)

        # Persistent session (used by login + profile + schedule)
        self.session = JsonlSession(HOST, PORT, SOCKET_TIMEOUT)

        self.root = QStackedWidget(); self.setCentralWidget(self.root)

        # ---- Auth Page ----
        auth_page = QWidget(); v_auth = QVBoxLayout(auth_page)
        tabs = QTabWidget()
        self.login_tab = LoginForm(self.session)
        self.register_tab = RegisterForm()
        tabs.addTab(self.login_tab, "Login")
        tabs.addTab(self.register_tab, "Register")
        v_auth.addWidget(tabs, 1)
        self.root.addWidget(auth_page)

        # ---- App Page ----
        app_page = QWidget(); self.root.addWidget(app_page)
        h = QHBoxLayout(app_page)

        left = QWidget(); left_l = QVBoxLayout(left)
        self.btn_profile = QPushButton("Profile")
        self.btn_sched   = QPushButton("Schedule")
        self.btn_ride    = QPushButton("Ride")
        for b in (self.btn_profile, self.btn_sched, self.btn_ride):
            b.setCheckable(True); b.setAutoExclusive(True); left_l.addWidget(b)
        left_l.addStretch(1)

        self.stack = QStackedWidget()
        # profile will be created after login (needs user data)
        self.profile_page = title_page("Profile (login required)")
        self.stack.addWidget(self.profile_page)              # index 0
        self.stack.addWidget(title_page("Your Schedule"))    # index 1
        self.stack.addWidget(RidePage())                     # index 2

        self.btn_profile.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.btn_sched.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.btn_ride.clicked.connect(lambda: self.stack.setCurrentIndex(2))

        self.btn_profile.setChecked(True); self.stack.setCurrentIndex(0)

        h.addWidget(left); h.addWidget(self.stack, 1)

        # connect login signal
        self.login_tab.logged_in.connect(self.after_login)

    def set_schedule_enabled(self, on: bool):
        # requirement: enable/disable Schedule based on Driver Mode
        self.btn_sched.setEnabled(bool(on))

        if hasattr(self, "schedule_page"): #disable the schedule page widget
            self.schedule_page.setEnabled(bool(on))

    def after_login(self, user_preview: dict):
        # Build the Profile screen with logged-in info + bind Save
        profile = ProfileScreen(self.session, user_preview)
        profile.driverModeChanged.connect(self.set_schedule_enabled)

        self.stack.removeWidget(self.profile_page)
        self.profile_page.deleteLater()
        self.profile_page = profile
        self.stack.insertWidget(0, self.profile_page)

        # reflect initial driver mode from server preview
        self.set_schedule_enabled(bool(user_preview.get("is_driver", False)))

        self.schedule_page = ScheduleScreen(self.session)
        self.stack.removeWidget(self.stack.widget(1))
        self.stack.insertWidget(1, self.schedule_page)

        # switch to app
        self.root.setCurrentIndex(1)
        self.btn_profile.setChecked(True)
        self.stack.setCurrentIndex(0)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
