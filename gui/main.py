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
    QHeaderView, QTimeEdit, QDateTimeEdit, QTextEdit, QDialog, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal, QDateTime, QTimer, QObject, QPointF
from PyQt5.QtGui import QTextCursor, QPixmap, QIcon, QPolygonF, QColor, QPainter
from gui.p2p_chat_endpoint import P2PChatEndpoint

import requests



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



#==== weather api constants ======
WEATHER_API_URL = "http://api.weatherapi.com/v1/current.json"
WEATHER_API_KEY = "77ba44421ca942b892a154619252311"



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



# =============================================================================
# design
DARK_STYLESHEET = """
QMainWindow#MainWindow, QWidget {
    background-color: #020617;
    color: #e5e7eb;
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 10pt;
}

/* Sidebar */
QWidget#SideBar {
    background-color: #020617;
    border-right: 1px solid #111827;
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
    background-color: rgba(129,140,248,0.25);
    color: #e5e7eb;
}

QWidget#SideBar QPushButton:checked {
    background-color: #4f46e5;
    color: #f9fafb;
}

/* Cards */
QWidget#login_card, QWidget#register_card {
    background-color: #020617;
    border-radius: 18px;
    border: 1px solid rgba(148,163,184,0.45);
}

/* Inputs */
QLineEdit, QTimeEdit, QDateTimeEdit, QComboBox {
    background-color: rgba(15,23,42,0.85);
    border: 1px solid rgba(148,163,184,0.45);
    border-radius: 8px;
    padding: 6px 10px;
    color: #e5e7eb;
}

QLineEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus, QComboBox:focus {
    border: 1px solid #6366f1;
    background-color: rgba(15,23,42,1.0);
}

/* Buttons */
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

/* Tables */
QTableWidget {
    background-color: #020617;
    border: 1px solid #111827;
    border-radius: 14px;
    gridline-color: #111827;
    selection-background-color: rgba(129,140,248,0.30);
    selection-color: #f9fafb;
}

QHeaderView::section {
    background-color: #020617;
    color: #9ca3af;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid #111827;
}

/* Tabs */
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

/* ---------- Auth card (dark) ---------- */
QFrame#AuthCard {
    /* pretty gradient card */
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #0f172a,
        stop:0.35 #111827,
        stop:1 #1f1b3f
    );
    border-radius: 18px;
    padding: 18px 22px;
    border: 1px solid rgba(148,163,184,0.55);
}

/* make everything inside the card transparent by default */
QFrame#AuthCard * {
    background: transparent;
}

/* title */
QLabel#AuthTitle {
    font-size: 16px;
    font-weight: 600;
    color: #e5e7eb;
}

/* generic labels – no box behind text */
QFrame#AuthCard QLabel {
    color: #e5e7eb;
}

/* input fields: the ONLY things with a background */
QLineEdit#AuthField {
    background-color: rgba(15,23,42,0.92);
    border-radius: 10px;
    padding: 6px 10px;
    border: 1px solid rgba(148,163,184,0.8);
    color: #f9fafb;
}
QLineEdit#AuthField:focus {
    border-color: #6366f1;
    background-color: rgba(15,23,42,1.0);
}

/* primary button */
QPushButton#AuthPrimaryButton {
    margin-top: 8px;
    padding: 6px 14px;
    border-radius: 12px;
    background-color: #6366f1;
    color: #020617;
    font-weight: 600;
    border: none;
}
QPushButton#AuthPrimaryButton:hover {
    background-color: #3f43ee;
}

/* error text */
QLabel#AuthError {
    color: #f97373;
    font-size: 9pt;
}

/* Profile fields – dark mode */
QLineEdit#profileField,
QLineEdit#profileField:disabled,
QLineEdit#profileField:read-only {
    background-color: rgba(255,255,255,0.10);
    border: 1px solid rgba(148,163,184,0.55);
    color: #f9fafb;
}
QLineEdit#profileField:focus {
    border: 1px solid #6366f1;
    background-color: rgba(255,255,255,0.15);
}
"""

LIGHT_STYLESHEET = """
QMainWindow#MainWindow, QWidget {
    background-color: #fff5e9;   /* warm cream */
    color: #3f3a32;
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 10pt;
}

/* Sidebar */
QWidget#SideBar {
    background-color: #f1dfca;
    border-right: 1px solid #e0cbb1;
}

QWidget#SideBar QPushButton {
    background-color: transparent;
    border: none;
    color: #6b5b4b;
    padding: 8px 14px;
    text-align: left;
    border-radius: 10px;
}

QWidget#SideBar QPushButton:hover {
    background-color: rgba(178,132,91,0.16);
    color: #3f3a32;
}

QWidget#SideBar QPushButton:checked {
    background-color: #b8845b;
    color: #fffaf3;
}

/* Cards */
QWidget#login_card, QWidget#register_card {
    background-color: #fffaf3;
    border-radius: 18px;
    border: 1px solid #e0cbb1;
}

/* Inputs */
QLineEdit, QTimeEdit, QDateTimeEdit, QComboBox {
    background-color: #fffaf3;
    border: 1px solid #e1cdb5;
    border-radius: 8px;
    padding: 6px 10px;
    color: #3f3a32;
}

QLineEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus, QComboBox:focus {
    border: 1px solid #c27b4f;
    background-color: #fffdf7;
}

/* Buttons */
QPushButton {
    background-color: #f1dfca;
    color: #3f3a32;
    border-radius: 10px;
    padding: 6px 14px;
    border: 1px solid #ddc3a6;
}

QPushButton:hover {
    background-color: #e7cfb7;
    border-color: #cda57e;
}

QPushButton:pressed {
    background-color: #c27b4f;
    border-color: #c27b4f;
    color: #fffaf3;
}

QPushButton:disabled {
    background-color: #f5e6d4;
    color: #b39a7b;
    border-color: #e3cfb3;
}

/* Tables */
QTableWidget {
    background-color: #fffaf3;
    border: 1px solid #e3cfb3;
    border-radius: 14px;
    gridline-color: #e3cfb3;
    selection-background-color: rgba(194,123,79,0.20);
    selection-color: #3f3a32;
}

QHeaderView::section {
    background-color: #f5e6d4;
    color: #7a6a59;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid #e3cfb3;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #e3cfb3;
    border-radius: 14px;
    background-color: #fffaf3;
}

QTabBar::tab {
    background-color: transparent;
    color: #7a6a59;
    padding: 6px 16px;
    border-radius: 10px;
    margin: 4px;
}

QTabBar::tab:selected {
    background-color: #c27b4f;
    color: #fffaf3;
}

QTabBar::tab:hover {
    background-color: rgba(194,123,79,0.18);
    color: #3f3a32;
}


/* ---------- Auth card (light) ---------- */
QFrame#AuthCard {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #fff2de,
        stop:0.5 #fde4c7,
        stop:1 #1f2344
    );
    border-radius: 18px;
    padding: 18px 22px;
    border: 1px solid rgba(200,160,120,0.55);
}

/* everything inside card is see-through unless we say otherwise */
QFrame#AuthCard * {
    background: transparent;
}

/* title */
QLabel#AuthTitle {
    font-size: 16px;
    font-weight: 600;
    color: #1f2933;
}

/* labels – no box */
QFrame#AuthCard QLabel {
    color: #3f3f46;
}

/* inputs – soft beige pill instead of plain white brick */
QLineEdit#AuthField {
    background-color: #fffaf3;
    border-radius: 10px;
    padding: 6px 10px;
    border: 1px solid rgba(200,160,120,0.9);
    color: #111827;
}
QLineEdit#AuthField:focus {
    border-color: #f97316;
    background-color: #fff3e0;
}

/* primary button */
QPushButton#AuthPrimaryButton {
    margin-top: 8px;
    padding: 6px 14px;
    border-radius: 12px;
    background-color: #fec89a;
    color: #111827;
    font-weight: 600;
    border: none;
}
QPushButton#AuthPrimaryButton:hover {
    background-color: #ffb37a;
}

/* error text */
QLabel#AuthError {
    color: #b91c1c;
    font-size: 9pt;
}

/* Profile fields – light mode */
QLineEdit#profileField,
QLineEdit#profileField:disabled,
QLineEdit#profileField:read-only {
    background-color: #fff7eb;
    border: 1px solid #e6c8a0;
    color: #1f2937;
}
QLineEdit#profileField:focus {
    border: 1px solid #d97706;
    background-color: #fff3e0;
}

"""

# =============================================================================



# =============================================================================
# weather helpers
def fetch_weather_for_coords(lat, lon):
    if lat is None or lon is None:
        return None

    params = {
        "key": WEATHER_API_KEY,
        "q": f"{lat},{lon}",
        "aqi": "no",
    }
    try:
        response = requests.get(WEATHER_API_URL, params=params, timeout=4)
        if not response.ok:
            print("WeatherAPI error:", response.text)
            return None

        content = json.loads(response.content)

        return {
            "location_name": content["location"]["name"],
            "country": content["location"]["country"],
            "temp_c": content["current"]["temp_c"],
            "condition_text": content["current"]["condition"]["text"],
            "icon_url": "http:" + content["current"]["condition"]["icon"],
        }
    except Exception as e:
        print("Weather fetch failed:", e)
        return None
def get_real_location():
    return 33.8938, 35.5018 #beirut loc
def on_refresh_clicked(self):
    lat, lon = self._get_lat_lon()
    if lat is None or lon is None:
        self.lbl_status.setText("Location not available")
        return

    self.lbl_status.setText("Fetching weather...")
    info = fetch_weather_for_coords(lat, lon)
    if not info:
        self.lbl_status.setText("Failed to fetch weather.")
        return

    self.lbl_status.setText(f"Weather for {info['location_name']}, {info['country']}")
    self.lbl_details.setText(f"{info['temp_c']} °C – {info['condition_text']}")

    
    try:
        icon_resp = requests.get(info["icon_url"], timeout=4)
        pix = QPixmap()
        pix.loadFromData(icon_resp.content)
        self.lbl_icon.setPixmap(pix)
    except:
        pass
# =============================================================================


# ===== validation regex (mirror server) =====
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,20}$")
PASSWORD_RE = re.compile(r"^.{6,20}$")
EMAIL_RE    = re.compile(r"^[^@]+@[^@]+\.[^@]+$")



# =============================================================================
#
class JsonlSession(QObject):
    push_reveived = pyqtSignal(dict)
    def __init__(self, host: str, port: int, timeout: float = 4.0, parent=None):
        super().__init__(parent)
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: socket.socket | None = None
    
    def handle_push(self, msg: dict):
        #debug message
        print("PUSH from server:", msg.get("type"), msg.get("payload", {}))
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
            mid = str(uuid.uuid4())
            env["id"] = mid

        if "payload" not in env or env["payload"] is None:
            env["payload"] = {}

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
            if t in ("RIDE.MATCHED", "REQUEST.CLOSED", "DRIVER.BROADCAST", "PROFILE.UPDATED"):
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


# =============================================================================
class RegisterForm(QWidget):
    def __init__(self, session = None, parent=None):
        super().__init__(parent)
        self.session = session

        self.in_name = QLineEdit()
        self.in_email = QLineEdit()
        self.in_username = QLineEdit()
        self.in_password = QLineEdit()
        self.in_password.setEchoMode(QLineEdit.Password)
        self.in_area = QLineEdit()
        for w in (self.in_name, self.in_email, self.in_username, self.in_password, self.in_area):
            w.setMinimumWidth(250)
            w.setMaximumWidth(400)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignHCenter | Qt.AlignCenter)
        form.setContentsMargins(0, 20, 0, 0)
        form.setHorizontalSpacing(15)
        form.setVerticalSpacing(10)
        form.addRow("Name:", self.in_name)
        form.addRow("Email:", self.in_email)
        form.addRow("Username:", self.in_username)
        form.addRow("Password:", self.in_password)
        form.addRow("Area:", self.in_area)

        self.err = QLabel("")
        self.err.setWordWrap(True)
        self.err.setStyleSheet("color: red;")
        self.err.setVisible(False)

        self.btn_register = QPushButton("Create account")
        self.btn_register.setMinimumWidth(120)
        self.btn_register.clicked.connect(self.on_submit)

        card = QWidget()
        card.setObjectName("register_card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(30, 20, 30, 20)
        lay.setSpacing(15)
        lay.addLayout(form)
        lay.addWidget(self.err)
        lay.addSpacing(8)
        lay.addWidget(self.btn_register, 0, Qt.AlignHCenter)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addStretch(1)
        root.addWidget(card, 0, Qt.AlignHCenter)
        root.addStretch(1)

    def show_error(self, msg):
        self.err.setText(msg)
        self.err.setVisible(True)

    def show_ok(self, msg):
        self.err.setStyleSheet("color: #0a7a0a;")
        self.err.setText(msg)
        self.err.setVisible(True)


    def clear_error(self):
        self.err.setText("")
        self.err.setVisible(False)

    def validate(self):
        name = self.in_name.text().strip()
        email = self.in_email.text().strip()
        username = self.in_username.text().strip()
        password = self.in_password.text().strip()
        area = self.in_area.text().strip()

        if not name:
            return False, "Name is required."
        if not email or not EMAIL_RE.match(email):
            return False, "Invalid email format."
        if not username or not USERNAME_RE.match(username):
            return False, "Username must be 5-20 characters (letters, digits, underscores)."
        if not password or not PASSWORD_RE.match(password):
            return False, "Password must be 6-20 characters."
        if not area:
            return False, "Area is required."

        return True, {
            "name": name,
            "email": email,
            "username": username,
            "password": password,
            "area": area
        }

    def jsonl_request(self, obj):
        data = (json.dumps(obj, separators=(",", ":")) + "\n").encode(ENCODING)
        with socket.create_connection((HOST, PORT), timeout=SOCKET_TIMEOUT) as s:
            s.settimeout(SOCKET_TIMEOUT)
            s.sendall(data)
            buf = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if b"\n" in buf:
                    line, _ = buf.split(b"\n", 1)
                    txt = line.decode(ENCODING, errors="replace").rstrip("\r").strip()
                    return json.loads(txt)
        raise RuntimeError("No response from server")

    def on_submit(self):
        # 1) Read inputs
        name = self.in_name.text().strip()
        email = self.in_email.text().strip()
        username = self.in_username.text().strip()
        password = self.in_password.text()
        area = self.in_area.text().strip()

        # 2) Basic client-side validation
        if not name:
            self.show_error("Name is required.")
            return
        if not email:
            self.show_error("Email is required.")
            return
        if not username:
            self.show_error("Username is required.")
            return
        if not password:
            self.show_error("Password is required.")
            return
        if not area:
            self.show_error("Area is required.")
            return

        payload = {
            "name": name,
            "email": email,
            "username": username,
            "password": password,
            "area": area,
        }

        req = {
            "type": "AUTH.REGISTER_REQ",
            "id": str(uuid.uuid4()),
            "payload": payload,
        }

        try:
            # same session.request(...) you already use
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return

        rtype = resp.get("type")
        p = resp.get("payload", {})

        if rtype == "AUTH.REGISTER_RES":
            # success toast / message
            QMessageBox.information(self, "Success", "Account created. You can now log in.")


            # clear form fields
            self.in_name.clear()
            self.in_email.clear()
            self.in_username.clear()
            self.in_password.clear()
            self.in_area.clear()

        elif rtype == "ERROR":
            # server sends codes like AUTH_USERNAME_TAKEN, AUTH_EMAIL_TAKEN, BAD_REQUEST...
            msg = p.get("message", "Failed to register.")
            self.show_error(msg)
        else:
            self.show_error(f"Unexpected response: {rtype}")
# =============================================================================



# =============================================================================
class LoginForm(QWidget):
    logged_in = pyqtSignal(dict)

    def __init__(self, session: JsonlSession, parent=None):
        super().__init__(parent)
        self.session = session

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setObjectName("AuthCard")
        card.setFixedWidth(420)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 28, 32, 28)
        card_layout.setSpacing(16)

        title = QLabel("Log into account")
        title.setObjectName("AuthTitle")
        card_layout.addWidget(title, 0, Qt.AlignHCenter)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignHCenter | Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.in_user = QLineEdit()
        self.in_user.setObjectName("AuthField")
        self.in_pass = QLineEdit()
        self.in_pass.setObjectName("AuthField")
        self.in_pass.setEchoMode(QLineEdit.Password)

        form.addRow("Username:", self.in_user)
        form.addRow("Password:", self.in_pass)

        card_layout.addLayout(form)

        self.err = QLabel("")
        self.err.setWordWrap(True)
        self.err.setObjectName("AuthError")
        self.err.setVisible(False)
        card_layout.addWidget(self.err)

        self.btn_login = QPushButton("Log into account")
        self.btn_login.setObjectName("AuthPrimaryButton")
        self.btn_login.clicked.connect(self.on_login)
        card_layout.addWidget(self.btn_login)

        outer.addWidget(card, 0, Qt.AlignCenter)

    def show_error(self, msg: str):
        self.err.setText(msg)
        self.err.setVisible(True)

    def on_login(self):
        u = self.in_user.text().strip()
        p = self.in_pass.text().strip()
        if not u or not p:
            self.show_error("Username and password are required.")
            return

        req = {
            "type": "AUTH.LOGIN_REQ",
            "id": str(uuid.uuid4()),
            "payload": {"username": u, "password": p},
        }
        try:
            resp = self.session.request(req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return

        if resp.get("type") == "AUTH.LOGIN_RES":
            payload = resp.get("payload", {})
            self.logged_in.emit(payload.get("user", {}))
            self.err.setVisible(False)
        else:
            msg = resp.get("payload", {}).get("message", "Login failed.")
            self.show_error(msg)
# =============================================================================



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
            "is_driver": bool(user_preview.get("is_driver", False)),
            "rating_avg": user_preview.get("rating_avg", 0.0),
            "rating_count": user_preview.get("rating_count", 0),
            
        }

        self.in_name = QLineEdit(self.snapshot["name"])
        self.in_name.setObjectName("profileField")
        self.in_email = QLineEdit(self.snapshot["email"])
        self.in_email.setObjectName("profileField")
        self.in_area = QLineEdit(self.snapshot["area"])
        self.in_area.setObjectName("profileField")
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
        self.rating_label = QLabel("")
        self.rating_label.setStyleSheet("font-size: 11pt; color: #e5e7eb;")
        form.addRow("Rating:", self.rating_label)

        self._update_rating_label()
        form.addRow("", self.chk_driver)

        self.err = QLabel(""); self.err.setWordWrap(True); self.err.setStyleSheet("color: red;"); self.err.setVisible(False)
        self.ok = QLabel(""); self.ok.setWordWrap(True); self.ok.setStyleSheet("color: #0a7a0a;"); self.ok.setVisible(False)

        self.weather_icon = QLabel()
        self.weather_icon.setFixedSize(48,48)
        self.weather_icon.setScaledContents(True)

        self.weather_label = QLabel("")
        self.weather_label.setWordWrap(False)

        weather_row = QHBoxLayout()
        weather_row.addWidget(self.weather_icon)
        weather_row.addWidget(self.weather_label,1)

        

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

        root.addLayout(weather_row)

        root.addSpacing(12)
        
        
        root.addSpacing(8)


        buttons = QHBoxLayout()
        buttons.addWidget(self.btn_edit)
        buttons.addWidget(self.btn_save)
        buttons.addWidget(self.btn_cancel)
        root.addLayout(buttons)
        root.addStretch(1)

        self.set_edit_mode(False)
        self.on_weather_clicked()

    def set_edit_mode(self, on: bool):
        editing = bool(on)
        for w in (self.in_name, self.in_email, self.in_area):
            w.setReadOnly(not editing)
        self.chk_driver.setEnabled(editing)

        self.btn_edit.setEnabled(not editing)
        self.btn_save.setEnabled(editing)
        self.btn_cancel.setEnabled(editing)

        

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
            self._update_rating_label()
  
        elif resp.get("type") == "ERROR":
            self.show_error(resp.get("payload", {}).get("message", "Failed to save profile."))
        else:
            self.show_error(f"Unexpected response: {resp.get('type')}")

    def on_weather_clicked(self):
        #bei loc
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

    def _update_rating_label(self):
        avg = self.snapshot.get("rating_avg")
        count = self.snapshot.get("rating_count")

        if count is None or count == 0:
            self.rating_label.setText("No ratings yet")
            return

        # format avg to 1 decimal place
        avg_str = f"{avg:.1f}"
        self.rating_label.setText(f"{avg_str} ★ ({count})")

    def update_from_user_preview(self, preview: dict):
        """
        Update the profile fields when RIDE.RATE_RES returns new rating info.
        """
        self.snapshot["rating_avg"] = preview.get("rating_avg", self.snapshot.get("rating_avg"))
        self.snapshot["rating_count"] = preview.get("rating_count", self.snapshot.get("rating_count"))


        # Update the rating label
        self._update_rating_label()
# =============================================================================


# =============================================================================
#driver
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
        direction = self.cb_direction.currentText()
        if direction == "to_AUB":
            dlg.setWindowTitle("Select your pickup location")
            dlg.label.setText("Try to approximately locate where you will be picked up (your current location).")
        else:
            dlg.setWindowTitle("Select your drop-off location")
            dlg.label.setText("Try to approximately locate where you will be dropped off.")
        dlg.location_selected.connect(self.on_location_picked)
        dlg.showMaximized()
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
            self.in_area.setPlaceholderText("From where are you driving? (e.g. Hamra)")
            self.btn_pick_location.setText("Pick starting point on map")
        else:
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

        req = {"type": "SCHEDULE.LIST_REQ", "id": str(uuid.uuid4()), "payload": {}}
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
# =============================================================================

# =============================================================================
class PassengerScheduleInfo(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        lbl = QLabel(
            "To add a weekly schedule, enable Driver Mode in your profile.\n\n"
            "This helps passengers find you when your route matches their request."
        )
        lbl.setWordWrap(True)
        v.addStretch(1)
        v.addWidget(lbl, 0, Qt.AlignHCenter)
        v.addStretch(1)
# =============================================================================



# =============================================================================
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

        #rating
        self.cb_min_driver_rating = QComboBox()
        self.cb_min_driver_rating.addItem("Any driver rating", None)
        for stars in range(1, 6):
            self.cb_min_driver_rating.addItem(f"{stars}+ stars", float(stars))


        self.dt = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.dt.setCalendarPopup(True)
        self.dt.setKeyboardTracking(False)

        self.btn_submit = QPushButton("Request Ride")
        self.btn_submit.clicked.connect(self.on_submit)

        self.btn_cancel = QPushButton("Cancel request")
        self.btn_cancel.setEnabled(False)
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
        form.addRow("Min driver rating:", self.cb_min_driver_rating)
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
    
    def _min_driver_rating(self):
        idx = self.cb_min_driver_rating.currentIndex()
        val = self.cb_min_driver_rating.itemData(idx)
        if isinstance(val, (int, float)):
            return float(val)
        return None


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

        min_rating = self._min_driver_rating()
        if min_rating is not None:
            payload["min_driver_rating"] = min_rating

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
            self.poll_timer.start()

        elif rtype == "ERROR":
            code = p.get("code")
            msg = p.get("message", "Failed to create ride request")
            if code == "PASSENGER_BUSY":
                self.current_request_id = None
                self.btn_cancel.setEnabled(False)
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
        self.btn_cancel.setEnabled(False)

    def set_idle_state(self):
        self.current_request_id = None

        try: self.poll_timer.stop()
        except: pass

        self.btn_cancel.setEnabled(False)
        self.btn_submit.setEnabled(True)

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
# =============================================================================



# =============================================================================
# requests table
class DriverRidePage(QWidget):
    rideAccepted = pyqtSignal(str, dict)  # emit request_id when a ride is accepted
    def __init__(self, session: JsonlSession, parent=None):
        super().__init__(parent)
        self.session = session

        # Rating filter: only show requests from passengers above threshold
        self.cb_min_passenger_rating = QComboBox()
        self.cb_min_passenger_rating.addItem("Any passenger rating", None)
        for stars in range(1, 6):
            self.cb_min_passenger_rating.addItem(f"{stars}+ stars", float(stars))


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
        top.addWidget(QLabel("Filter:"))
        top.addWidget(self.cb_min_passenger_rating)
        top.addSpacing(12)
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

        payload = {}
        min_rating = self._min_passenger_rating()
        if min_rating is not None:
            payload["min_passenger_rating"] = min_rating

        req = {
            "type": "RIDE.LIST_REQ",
            "id": str(uuid.uuid4()),
            "payload": payload,
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
            self.rideAccepted.emit(req_id, payload)
        elif rtype == "ERROR":
            code = payload.get("code")
            msg = payload.get("message", "Failed to accept request.")

            if code == "REQUEST.CLOSED":
                msg = "This request is no longer available (cancelled, matched, or expired)"
            
            self.show_error(msg)
            self.table.clearSelection()
            self.refresh()
        else:
            self.show_error(f"Unexpected response: {rtype}")
    
    def handle_request_closed(self, payload):
        QMessageBox.information(self, "Request Closed", "A ride request you are eligible for has been closed (cancelled by passenger or expired).")
        self.refresh()
    
    def add_broadcast(self, payload):
        self.refresh()
    
    def _min_passenger_rating(self):
        idx = self.cb_min_passenger_rating.currentIndex()
        val = self.cb_min_passenger_rating.itemData(idx)
        if isinstance(val, (int, float)):
            return float(val)
        return None
# =============================================================================



# =============================================================================
# from accepting ride until completion
class CurrentRidePage(QWidget):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        v = QVBoxLayout(self)

        self.info_label = QLabel("No active ride")
        v.addWidget(self.info_label)

        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)

        # Strip inherited QSS so our HTML bubbles control the look fully
        self.chat_box.setStyleSheet(
            "QTextEdit, QTextEdit * { all: unset; background: transparent; }"
        )

        v.addWidget(self.chat_box, 1)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type a message...")
        v.addWidget(self.chat_input)

        h = QHBoxLayout()
        self.send_btn = QPushButton("Send")
        self.complete_btn = QPushButton("Complete Ride")
        h.addWidget(self.send_btn)
        h.addWidget(self.complete_btn)
        v.addLayout(h)

        self.complete_btn.hide()  # passenger by default
        self.send_btn.clicked.connect(self.on_send_clicked)

    def append_bubble(self, text: str, outgoing: bool, timestamp=None):
        if not text:
            return

        safe = html.escape(text).replace("\n", "<br/>")

        if timestamp is None:
            timestamp = QDateTime.currentDateTime()
        ts_str = timestamp.toString("HH:mm")

        mw = self.window()
        other_name = None
        if mw is not None:
            other_name = getattr(mw, "other_party_name", None)

        if outgoing:
            align = "right"
            bg = "#4f46e5"
            fg = "#f9fafb"
            name = "You"
        else:
            align = "left"
            bg = "#e5e7eb"
            fg = "#111827"
            name = other_name or "Them"

        bubble_html = f"""
        <div style="padding:4px 0; text-align:{align};">
          <div style="
              display:inline-block;
              max-width:60%;
              background:{bg};
              color:{fg};
              padding:8px 12px;
              border-radius:18px;
              font-size:10pt;
              line-height:1.4;
          ">
            <div style="font-size:8pt; opacity:0.7; margin-bottom:2px;">{name}</div>
            <div>{safe}</div>
            <div style="font-size:8pt; opacity:0.6; margin-top:4px; text-align:right;">
              {ts_str}
            </div>
          </div>
        </div>
        """

        cursor = self.chat_box.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.chat_box.setTextCursor(cursor)
        self.chat_box.insertHtml(bubble_html)
        self.chat_box.moveCursor(QTextCursor.End)
        self.chat_box.ensureCursorVisible()

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

    def load_for_driver(self, match_payload):
        p = match_payload.get("passenger_info", {}) or {}
        passenger_name = p.get("name", "Passenger")
        self.info_label.setText(f"Passenger matched!\nRiding with: {passenger_name}")
        self.complete_btn.show()

    def load_for_passenger(self, payload):
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
# =============================================================================



# =============================================================================
# rating
class StarRatingWidget(QWidget):
    ratingChanged = pyqtSignal(int)

    def __init__(self, parent=None, max_stars=5):
        super().__init__(parent)
        self.max_stars = max_stars
        self._rating = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._pix_empty = self._make_star_pixmap(28, QColor("#4b5563"))   # grey
        self._pix_filled = self._make_star_pixmap(28, QColor("#facc15"))  # yellow

        self._buttons: list[QPushButton] = []
        for i in range(max_stars):
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setFlat(True)
            btn.setIcon(QIcon(self._pix_empty))
            btn.setIconSize(self._pix_empty.size())
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(36, 36)
            btn.setStyleSheet("""
                QPushButton {
                    border: none;
                    background-color: transparent;
                    font-size: 22px;
                    color: #4b5563;
                }
            """)
            btn.clicked.connect(lambda _=False, idx=i: self.set_rating(idx + 1))
            self._buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch(1)
    
    def _make_star_pixmap(self, size: int, color: QColor) -> QPixmap:
        """Draw a 5-point star into a transparent pixmap."""
        import math

        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)

        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)

        cx = cy = size / 2.0
        outer_r = size * 0.45
        inner_r = size * 0.20

        points = []
        # 10 points: outer, inner, outer, inner...
        for i in range(10):
            angle = math.pi / 2 + i * math.pi / 5  # start from top
            r = outer_r if i % 2 == 0 else inner_r
            x = cx + r * math.cos(angle)
            y = cy - r * math.sin(angle)
            points.append(QPointF(x, y))

        poly = QPolygonF(points)
        painter.drawPolygon(poly)
        painter.end()
        return pm

    def set_rating(self, value: int):
        value = max(0, min(self.max_stars, int(value)))
        self._rating = value
        for i, btn in enumerate(self._buttons, start=1):
            filled = i <= value
            btn.setChecked(filled)
            btn.setIcon(QIcon(self._pix_filled if filled else self._pix_empty))
        self.ratingChanged.emit(self._rating)

    def rating(self) -> int:
        return self._rating
class RatingDialog(QDialog):
    def __init__(self, parent=None, title="Rate your ride", subtitle="How was your ride experience?"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        self.setMinimumWidth(480)
        self.setMaximumWidth(480)

        self.setStyleSheet("""
            QDialog {
                background-color: #020617;
            }
            QLabel {
                color: #e5e7eb;
                background-color: transparent;
            }
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
        """)

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(10)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-size: 14pt; font-weight: 600;")
        v.addWidget(lbl_title)

        lbl_sub = QLabel(subtitle)
        lbl_sub.setWordWrap(True)
        lbl_sub.setStyleSheet("color: #9ca3af;")
        v.addWidget(lbl_sub)

        self.star_widget = StarRatingWidget(self)
        v.addWidget(self.star_widget)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self.btn_skip = QPushButton("Skip")
        self.btn_ok = QPushButton("Submit")

        self.btn_skip.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._on_submit)

        btn_row.addWidget(self.btn_skip)
        btn_row.addWidget(self.btn_ok)
        v.addLayout(btn_row)

    def _on_submit(self):
        if self.star_widget.rating() <= 0:
            QMessageBox.information(self, "Rating", "Select at least one star or press Skip.")
            return
        self.accept()

    def get_rating(self):
        """Returns 1–5 or None if skipped."""
        result = self.exec_()
        if result == QDialog.Accepted:
            return self.star_widget.rating()
        return None
# =============================================================================


class MainWindow(QMainWindow):
    incoming_p2p_connection = pyqtSignal(object, tuple)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AUBus")
        self.setObjectName("MainWindow")
        self.resize(1000, 650)

        # --- theme state ---
        self.current_theme = "dark"
        self.theme_toggle_btn_app = None      # sidebar button
        self.theme_toggle_btn_auth = None     # login/register button

        # Persistent session (used by login + profile + schedule + ride)
        self.session = JsonlSession(HOST, PORT, SOCKET_TIMEOUT)
        self.session.push_reveived.connect(self.on_push_received)

        self.p2p_sock = None
        self.p2p_thread = None
        self.chat_endpoint = None
        self.incoming_p2p_connection.connect(self._on_incoming_p2p_connection)

        self.active_request_id = None

        self.root = QStackedWidget()
        self.setCentralWidget(self.root)

        # ------------------------------------------------------------------
        # AUTH PAGE (Login / Register)  + theme toggle
        # ------------------------------------------------------------------
        self.auth_page = QWidget()
        v_auth = QVBoxLayout(self.auth_page)
        v_auth.setContentsMargins(32, 32, 32, 32)

        tabs = QTabWidget()
        self.login_tab = LoginForm(self.session)
        self.register_tab = RegisterForm(self.session)
        tabs.addTab(self.login_tab, "Login")
        tabs.addTab(self.register_tab, "Register")

        v_auth.addStretch(1)
        v_auth.addWidget(tabs, 0, Qt.AlignHCenter)
        v_auth.addStretch(1)

        # bottom row: theme toggle + spacer
        auth_bottom = QHBoxLayout()
        self.theme_toggle_btn_auth = QPushButton("Light mode")
        self.theme_toggle_btn_auth.setObjectName("ThemeToggleAuth")
        self.theme_toggle_btn_auth.setCheckable(True)
        self.theme_toggle_btn_auth.clicked.connect(self.toggle_theme)
        auth_bottom.addWidget(self.theme_toggle_btn_auth)
        auth_bottom.addStretch(1)
        v_auth.addLayout(auth_bottom)

        self.root.addWidget(self.auth_page)

        # ------------------------------------------------------------------
        # APP PAGE (Sidebar + main stack)  + theme toggle
        # ------------------------------------------------------------------
        self.app_page = QWidget()
        self.root.addWidget(self.app_page)
        h = QHBoxLayout(self.app_page)
        h.setContentsMargins(0, 0, 0, 0)

        left = QWidget()
        left.setObjectName("SideBar")
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(12, 16, 12, 16)

        self.btn_profile = QPushButton("Profile")
        self.btn_sched   = QPushButton("Schedule")
        self.btn_ride    = QPushButton("Ride")
        self.btn_current = QPushButton("Current Ride")

        for b in (self.btn_profile, self.btn_sched, self.btn_ride, self.btn_current):
            b.setCheckable(True)
            b.setAutoExclusive(True)
            left_l.addWidget(b)

        left_l.addStretch(1)

        # sidebar theme toggle
        self.theme_toggle_btn_app = QPushButton("Light mode")
        self.theme_toggle_btn_app.setObjectName("ThemeToggleApp")
        self.theme_toggle_btn_app.setCheckable(True)
        self.theme_toggle_btn_app.clicked.connect(self.toggle_theme)
        left_l.addWidget(self.theme_toggle_btn_app)

        self.btn_logout = QPushButton("Logout")
        left_l.addWidget(self.btn_logout)

        self.btn_logout.clicked.connect(self.on_logout)

        self.stack = QStackedWidget()

        # dummy profile until login
        self.profile_page = title_page("Profile (login required)")
        self.stack.addWidget(self.profile_page)

        # schedule (driver / passenger variants)
        self.schedule_page_driver = ScheduleScreen(self.session)
        self.schedule_page_passenger = PassengerScheduleInfo()
        self.stack.addWidget(self.schedule_page_driver)
        self.stack.addWidget(self.schedule_page_passenger)

        self.ride_page = RideRequestPage(self.session)
        self.stack.addWidget(self.ride_page)

        self.current_ride_page = CurrentRidePage(self.session)
        self.stack.addWidget(self.current_ride_page)
        self.current_ride_page.complete_btn.clicked.connect(self.complete_ride)

        self.btn_profile.clicked.connect(lambda: self.stack.setCurrentWidget(self.profile_page))
        # schedule button wiring is handled in on_driver_mode_changed
        self.btn_ride.clicked.connect(lambda: self.stack.setCurrentWidget(self.ride_page))
        self.btn_current.clicked.connect(lambda: self.stack.setCurrentWidget(self.current_ride_page))

        self.btn_current.setEnabled(False)
        self.btn_profile.setChecked(True)
        self.stack.setCurrentWidget(self.profile_page)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(16, 16, 16, 16)
        center_layout.addWidget(self.stack, 1)

        h.addWidget(left)
        h.addWidget(center, 1)

        # connect login signal
        self.login_tab.logged_in.connect(self.after_login)

        # Schedule initially disabled until we know driver mode
        self.set_schedule_enabled(False)

        # finally apply initial theme
        self.set_theme("dark")

    # ------------------------------------------------------------------ helpers
    def set_schedule_enabled(self, on: bool):
        """Enable/disable the Schedule button (used pre/post login)."""
        self.btn_sched.setEnabled(bool(on))

    # ------------------------------------------------------------------ auth / profile / driver mode
    def after_login(self, user_preview: dict):
        """
        Called when LoginForm emits logged_in(user_preview).
        We immediately fetch the full profile from the server so that
        name/email/area/is_driver are always populated, then rebuild
        the ProfileScreen and apply driver/passenger mode.
        """
        if not isinstance(user_preview, dict):
            user_preview = {}

        # --- 1) Ask server for the full profile, merge into user_preview ---
        try:
            resp = self.session.request({
                "type": "PROFILE.GET_REQ",
                "id": str(uuid.uuid4()),
                "payload": {}
            })
            if resp.get("type") == "PROFILE.GET_RES":
                prof = resp.get("payload", {}) or {}
                user_preview.update(prof)
        except Exception as e:
            print("PROFILE.GET_REQ failed:", e)

        # cache it
        self.user_preview = user_preview
        is_driver = bool(user_preview.get("is_driver", False))

        # --- 2) Rebuild the Profile screen with the fresh data ---
        if hasattr(self, "profile_page") and self.profile_page is not None:
            self.stack.removeWidget(self.profile_page)
            self.profile_page.deleteLater()

        self.profile_page = ProfileScreen(self.session, user_preview)
        self.profile_page.driverModeChanged.connect(self.on_driver_mode_changed)
        self.stack.insertWidget(0, self.profile_page)

        # --- 3) Apply driver / passenger mode (wires schedule + ride pages) ---
        self.on_driver_mode_changed(is_driver)

        # ✅ IMPORTANT: re-enable the Schedule button after login
        self.set_schedule_enabled(True)

        # --- 4) Switch to the main app UI ---
        self.root.setCurrentWidget(self.app_page)
        self.stack.setCurrentWidget(self.profile_page)
        self.btn_profile.setChecked(True)


    def on_driver_mode_changed(self, is_driver: bool):
        # P2P listener follows driver mode
        if is_driver:
            self.start_p2p_listener()
        else:
            self.stop_p2p_listener()

        # ---- wire Schedule button target ----
        try:
            self.btn_sched.clicked.disconnect()
        except TypeError:
            # no previous connection, ignore
            pass

        if is_driver:
            # driver sees real schedule editor
            self.btn_sched.clicked.connect(
                lambda: self.stack.setCurrentWidget(self.schedule_page_driver)
            )
        else:
            # passenger sees info: "you must be a driver to add a schedule"
            self.btn_sched.clicked.connect(
                lambda: self.stack.setCurrentWidget(self.schedule_page_passenger)
            )

        # ---- swap ride page between passenger/driver views ----
        # remove old ride_page from stack
        if hasattr(self, "ride_page") and self.ride_page is not None:
            self.stack.removeWidget(self.ride_page)
            self.ride_page.deleteLater()

        if is_driver:
            self.ride_page = DriverRidePage(self.session)
            self.ride_page.rideAccepted.connect(self.on_driver_ride_accepted)
        else:
            self.ride_page = RideRequestPage(self.session)

        # add new ride_page and keep Ride button pointing to it
        self.stack.addWidget(self.ride_page)
        # existing lambda uses self.ride_page, so no need to reconnect btn_ride

    # ------------------------------------------------------------------ window close / logout
    def closeEvent(self, event):
        """On window close, logout cleanly and close the session."""
        try:
            if self.session is not None:
                req = {
                    "type": "AUTH.LOGOUT_REQ",
                    "id": str(uuid.uuid4()),
                    "payload": {}
                }
                try:
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
            req = {
                "type": "AUTH.LOGOUT_REQ",
                "id": str(uuid.uuid4()),
                "payload": {}
            }
            self.session.request(req)
        except Exception:
            pass

        self.stop_p2p_listener()

        if isinstance(self.ride_page, DriverRidePage):
            self.ride_page.timer.stop()

        self.set_schedule_enabled(False)
        self.root.setCurrentWidget(self.auth_page)
        self.btn_profile.setChecked(False)
        self.btn_sched.setChecked(False)
        self.btn_ride.setChecked(False)
        self.btn_current.setEnabled(False)
        self.stack.setCurrentWidget(self.profile_page)

    # ------------------------------------------------------------------ P2P listener / chat
    def _on_incoming_p2p_connection(self, conn, addr):
        """Attach an incoming passenger P2P socket on the GUI thread."""
        if getattr(self, "chat_endpoint", None) is not None:
            try:
                self.chat_endpoint.close()
            except Exception:
                pass

        self.chat_endpoint = P2PChatEndpoint(conn, self)
        self.chat_endpoint.messageReceived.connect(self.on_p2p_message)
        self.chat_endpoint.disconnected.connect(self.on_p2p_disconnected)

    def start_p2p_listener(self):
        """Start TCP listener for driver P2P and announce via PEER.OPEN_REQ."""
        if self.p2p_sock is not None:
            return

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", 0))
            s.listen(1)
            port = s.getsockname()[1]
            self.p2p_sock = s

            req = {
                "type": "PEER.OPEN_REQ",
                "id": str(uuid.uuid4()),
                "payload": {"p2p_port": port}
            }
            try:
                resp = self.session.request(req)
            except Exception as e:
                print(f"PEER.OPEN_REQ failed: {e}")
                s.close()
                self.p2p_sock = None
                return

            if resp.get("type") != "PEER.OPEN_RES":
                print(f"PEER.OPEN_RES error: {resp}")
                s.close()
                self.p2p_sock = None
                return

            def _p2p_loop(listener: socket.socket):
                try:
                    while True:
                        conn, addr = listener.accept()
                        print(f"P2P connection from {addr}")
                        self.incoming_p2p_connection.emit(conn, addr)
                except Exception as e:
                    print("p2p_loop error:", e)

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

        ep = getattr(self, "chat_endpoint", None)
        self.chat_endpoint = None
        if ep:
            try:
                ep.close()
            except Exception:
                pass

    def on_p2p_message(self, text: str):
        page = getattr(self, "current_ride_page", None)
        if page is not None:
            page.append_bubble(text, outgoing=False)

    def on_p2p_disconnected(self):
        """Handle P2P disconnect."""
        if hasattr(self, "current_ride_page") and self.current_ride_page is not None:
            self.current_ride_page.append_bubble("<i>Chat disconnected.</i>", outgoing=False)
        if getattr(self, "chat_endpoint", None) is not None:
            self.chat_endpoint = None

    # ------------------------------------------------------------------ PUSH events
    def on_push_received(self, msg: dict):
        t = msg.get("type")
        payload = msg.get("payload", {})

        if t == "RIDE.MATCHED":
            print("MainWindow: RIDE.MATCHED received, payload =", payload)
            self.btn_ride.setEnabled(False)
            self.btn_current.setEnabled(True)

            self.btn_current.setChecked(True)
            self.stack.setCurrentWidget(self.current_ride_page)

            req_id = payload.get("request_id")
            if req_id is None and isinstance(self.ride_page, RideRequestPage):
                req_id = self.ride_page.current_request_id

            self.active_request_id = req_id

            if self.user_preview.get("is_driver"):
                # driver sees passenger name in chat
                passenger_info = payload.get("passenger_info", {}) or {}
                self.other_party_name = passenger_info.get("name", "Passenger")
                self.current_ride_page.load_for_driver(payload)
            else:
                # passenger sees driver name in chat
                driver_info = payload.get("driver_info", {}) or {}
                self.other_party_name = driver_info.get("name", "Driver")
                self.current_ride_page.load_for_passenger(payload)
                self.on_ride_matched(msg)

                driver_ip = payload.get("driver_ip")
                driver_port = payload.get("driver_port")

                if driver_ip and driver_port:
                    try:
                        sock = socket.create_connection((driver_ip, int(driver_port)), timeout=5.0)
                        sock.settimeout(None)
                    except Exception as e:
                        QMessageBox.warning(self, "Chat", f"Could not connect to driver: {e}")
                    else:
                        if getattr(self, "chat_endpoint", None) is not None:
                            self.chat_endpoint.close()

                        self.chat_endpoint = P2PChatEndpoint(sock, self)
                        self.chat_endpoint.messageReceived.connect(self.on_p2p_message)
                        self.chat_endpoint.disconnected.connect(self.on_p2p_disconnected)
                else:
                    if self.current_ride_page is not None:
                        self.current_ride_page.append_bubble(
                            "<i>Driver did not provide chat info</i>", outgoing=False
                        )

        elif t == "REQUEST.CLOSED":
            self.on_request_closed(msg)

        elif t == "DRIVER.BROADCAST":
            self.on_driver_broadcast(msg)

        elif t == "PROFILE.UPDATED":
            print("PROFILE.UPDATED push:", payload)

            if payload:
                self.user_preview["rating_avg"] = payload.get(
                    "rating_avg", self.user_preview.get("rating_avg"),
                )
                self.user_preview["rating_count"] = payload.get(
                    "rating_count", self.user_preview.get("rating_count"),
                )

            if isinstance(self.profile_page, ProfileScreen):
                self.profile_page.update_from_user_preview(self.user_preview)

    def on_ride_matched(self, msg: dict):
        payload = msg.get("payload", {})
        if isinstance(self.ride_page, RideRequestPage):
            self.ride_page.handle_matched(payload)

    def on_request_closed(self, msg: dict):
        """Called when server notifies that a ride was closed"""
        payload = msg.get("payload", {})
        reason = payload.get("reason")

        if isinstance(self.ride_page, DriverRidePage):
            self.ride_page.handle_request_closed(payload)

        if isinstance(self.ride_page, RideRequestPage):
            self.ride_page.set_idle_state()

        if reason == "completed":
            self.show_rating_dialog()

        try:
            self.return_to_idle_state()
            self.btn_current.setEnabled(False)
            self.btn_ride.setEnabled(True)
            self.btn_ride.setChecked(True)
            self.stack.setCurrentWidget(self.ride_page)
            if hasattr(self, "current_ride_page"):
                self.current_ride_page.chat_box.clear()
                self.current_ride_page.info_label.setText("No active ride")
        except AttributeError:
            pass

    def on_driver_broadcast(self, msg: dict):
        if isinstance(self.ride_page, DriverRidePage):
            self.ride_page.add_broadcast(msg.get("payload", {}))

    # ------------------------------------------------------------------ rating flow
    def show_rating_dialog(self):
        req_id = self.active_request_id
        if not req_id:
            return

        role = "driver" if self.user_preview.get("is_driver") else "passenger"
        if role == "driver":
            title = "Rate your passenger"
            subtitle = "Please rate your passenger before leaving this ride."
        else:
            title = "Rate your driver"
            subtitle = "Please rate your driver before leaving this ride."

        dlg = RatingDialog(self, title=title, subtitle=subtitle)
        rating = dlg.get_rating()
        if rating is None:
            return

        try:
            res = self.session.request({
                "type": "RIDE.RATE_REQ",
                "payload": {
                    "request_id": req_id,
                    "rating": int(rating),
                },
            })
        except Exception as e:
            QMessageBox.warning(self, "Rating failed", f"Network error while sending rating: {e}")
            return

        rtype = res.get("type")
        payload = res.get("payload", {})

        if rtype == "RIDE.RATE_RES":
            QMessageBox.information(self, "Thank you", "Your rating has been recorded.")
        elif rtype == "ERROR":
            msg = payload.get("message", "Failed to save rating.")
            QMessageBox.warning(self, "Rating failed", f"Server error: {msg}")
        else:
            QMessageBox.warning(self, "Rating failed", f"Unexpected response: {rtype}")

    def complete_ride(self):
        # DRIVER ONLY
        if not self.active_request_id:
            QMessageBox.warning(self, "No active ride", "No active ride to rate")
            return

        payload = {"request_id": self.active_request_id}
        try:
            res = self.session.request({"type": "RIDE.COMPLETE_REQ", "payload": payload})
        except Exception as e:
            QMessageBox.warning(self, "Ride Completed", f"Network: {e}")
            return

        if res["type"] == "RIDE.COMPLETE_RES":
            self.show_rating_dialog()
            self.return_to_idle_state()

        elif res["type"] == "ERROR":
            p = res.get("payload", {})
            QMessageBox.warning(self, "Ride Completed", p.get("message", "Failed to complete ride."))
        else:
            QMessageBox.warning(self, "Ride Completed", f"Unexpected response: {res.get('type')}")

    def return_to_idle_state(self):
        # driver or passenger
        self.btn_current.setEnabled(False)
        self.btn_ride.setEnabled(True)
        self.btn_ride.setChecked(True)

        self.stack.setCurrentWidget(self.ride_page)
        self.active_request_id = None

        self.current_ride_page.chat_box.clear()
        self.current_ride_page.info_label.setText("No active ride")

        ep = getattr(self, "chat_endpoint", None)
        self.chat_endpoint = None
        if ep:
            try:
                ep.close()
            except Exception:
                pass

    def on_driver_ride_accepted(self, request_id: str, payload: dict):
        """Called when THIS driver accepts a ride successfully."""
        self.btn_ride.setEnabled(False)
        self.btn_current.setEnabled(True)

        self.btn_current.setChecked(True)
        self.stack.setCurrentWidget(self.current_ride_page)

        self.active_request_id = request_id

        match_payload = dict(payload)
        match_payload.setdefault("request_id", request_id)

        passenger_info = payload.get("passenger_info", {})
        self.other_party_name = passenger_info.get("name", "Passenger")

        self.current_ride_page.load_for_driver(match_payload)

    # ------------------------------------------------------------------ chat send + theme
    def send_chat_message(self, text: str) -> bool:
        ep = getattr(self, "chat_endpoint", None)
        if ep is None:
            print("send_chat_message: no chat_endpoint")
            return False

        try:
            print("send_chat_message: sending:", repr(text))
            ep.send(text)
            print("send_chat_message: send() returned OK")
            return True
        except Exception as e:
            import traceback
            print("send_chat_message: ERROR while sending:", e)
            traceback.print_exc()
            return False



    def set_theme(self, mode: str):
        """mode: 'dark' or 'light'"""
        self.current_theme = "light" if mode == "light" else "dark"

        if self.current_theme == "light":
            QApplication.instance().setStyleSheet(LIGHT_STYLESHEET)
            text = "Dark mode"
            checked = True
        else:
            QApplication.instance().setStyleSheet(DARK_STYLESHEET)
            text = "Light mode"
            checked = False

        # keep both buttons in sync
        if self.theme_toggle_btn_app is not None:
            self.theme_toggle_btn_app.blockSignals(True)
            self.theme_toggle_btn_app.setText(text)
            self.theme_toggle_btn_app.setChecked(checked)
            self.theme_toggle_btn_app.blockSignals(False)

        if self.theme_toggle_btn_auth is not None:
            self.theme_toggle_btn_auth.blockSignals(True)
            self.theme_toggle_btn_auth.setText(text)
            self.theme_toggle_btn_auth.setChecked(checked)
            self.theme_toggle_btn_auth.blockSignals(False)


    def toggle_theme(self):
        if self.current_theme == "dark":
            self.set_theme("light")
        else:
            self.set_theme("dark")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()