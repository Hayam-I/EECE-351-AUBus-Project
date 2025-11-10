import sys
import traceback
import json
import re
import socket
import uuid
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget, QFormLayout, QLineEdit, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal

"""IMPORTANT!!!!!!!!!
Your jsonl_request() opens a new socket per request. That’s fine for REGISTER/LOGIN, but because your server uses connection-bound login (no tokens), anything like PROFILE.* must be sent over the same TCP connection you logged in on. When you implement Profile editing, create a small persistent session object and reuse it for those requests.

hayam: will do it for schedule page, profile page should be similar
server uses connection-bound login (no tokens), any endpoint that “requires being logged in” — including SCHEDULE.* and your “Driver Mode ON” check — must be called on the same TCP socket that performed AUTH.LOGIN_REQ. So you should keep a small persistent client session (one socket you reuse after login). Otherwise you’d have to re-login on every new socket.
"""


#for errors to show instead of crashing window
def excepthook(exc_type, exc, tb):
    traceback.print_exception(exc_type, exc, tb)
    QMessageBox.critical(None, "Unhandled Error", f"{exc_type.__name__}: {exc}")
sys.excepthook = excepthook

#configuring client - will work only if server is running on localhost
HOST = "127.0.0.1"
PORT = 6000
SOCKET_TIMEOUT = 4.0 #will only wait 4 seconds for a response from server
ENCODING = "utf-8"



def title_page(text):
    """Utility function to create a centered title page."""
    w = QWidget()
    v = QVBoxLayout(w)
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setObjectName("page_title")
    v.addStretch(1)
    v.addWidget(lbl)
    v.addStretch(1)
    return w

#verifying client side that username/password/email are of valid format to match up with server/main.py
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,20}$")
PASSWORD_RE = re.compile(r"^.{6,20}$")
EMAIL_RE = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

#client to server -> create helper function to open socket, connect, encode json, add newline, send, read, split by newline, decode and load json 
# synchronous request-response model - fine for now (register/login) but for chat we need threading
def jsonl_request(host, port, obj):
    data = (json.dumps(obj, separators=(",", ":")) + "\n").encode(ENCODING)
    with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT) as s:
        s.settimeout(SOCKET_TIMEOUT)
        s.sendall(data)
        buffer = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            buffer += chunk
            if b"\n" in buffer:
                line, _rest = buffer.split(b"\n", 1)
                txt = line.decode(ENCODING, errors="replace").rstrip("\r").strip()
                if not txt:
                    raise ValueError("Received empty response from server")
                return json.loads(txt)
    raise RuntimeError("No response received from server")

class RegisterForm(QWidget):
    """validate fields then send AUTH.REGISTER_REQ to server"""
    def __init__(self, parent = None):
        super().__init__(parent)

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
        form.setContentsMargins(0,20,0,0)
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
        card.setStyleSheet("""
            QWidget#register_card {
                background: #ffffff;
                border: 1px solid #e5e5e5;
                border-radius: 12px;
            }
            QLineEdit {
                padding: 8px 10px;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
            }
            QLineEdit:focus {
                border: 1px solid #7aa7ff;
                outline: none;
            }
            
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 20, 30, 20)
        card_layout.setSpacing(15)
        card_layout.addLayout(form)
        card_layout.addWidget(self.err)
        card_layout.addSpacing(8)
        card_layout.addWidget(self.btn_register,0, Qt.AlignHCenter)

        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0)
        root.addStretch(1)
        root.addWidget(card, 0, Qt.AlignHCenter)
        root.addStretch(1)
    
    def show_error(self, message):
        self.err.setText(message)
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
    
    def on_submit(self):
        self.clear_error()
        ok, payload_or_msg = self.validate()
        if not ok:
            self.show_error(payload_or_msg)
            return
        req = {
            "type": "AUTH.REGISTER_REQ",
            "id": str(uuid.uuid4()),
            "payload": payload_or_msg
        }
        try:
            resp = jsonl_request(HOST, PORT, req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return
        rtype = resp.get("type")
        payload = resp.get("payload", {})
        if rtype == "AUTH.REGISTER_RES":
            QMessageBox.information(self, "Success", "Account created successfully! You can now log in.")
            self.in_name.clear()
            self.in_email.clear()
            self.in_username.clear()
            self.in_password.clear()
            self.in_area.clear()

        elif rtype == "ERROR":
            msg = payload.get("message", "Unknown error")
            self.show_error(f"Error: {msg}")
        
        else:
            self.show_error(f"Unexpected response from server. {rtype}")

class LoginForm(QWidget):
    """validate fields then send AUTH.LOGIN_REQ to server"""
    
    logged_in = pyqtSignal(dict)

    def __init__(self, parent = None):
        super().__init__(parent)

        
        self.in_username = QLineEdit()
        self.in_password = QLineEdit()
        self.in_password.setEchoMode(QLineEdit.Password)
        

        for w in (self.in_username, self.in_password):
            w.setMinimumWidth(250)
            w.setMaximumWidth(400)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignHCenter | Qt.AlignCenter)
        form.setContentsMargins(0,20,0,0)
        form.setHorizontalSpacing(15)
        form.setVerticalSpacing(10)

          
        form.addRow("Username:", self.in_username)
        form.addRow("Password:", self.in_password)
        

        self.err = QLabel("")
        self.err.setWordWrap(True)
        self.err.setStyleSheet("color: red;")
        self.err.setVisible(False)

        self.btn_login = QPushButton("Log into account")
        self.btn_login.setMinimumWidth(120)
        self.btn_login.clicked.connect(self.on_submit)

        card = QWidget()
        card.setObjectName("login_card")
        card.setStyleSheet("""
            QWidget#login_card {
                background: #ffffff;
                border: 1px solid #e5e5e5;
                border-radius: 12px;
            }
            QLineEdit {
                padding: 8px 10px;
                border: 1px solid #d0d0d0;
                border-radius: 6px;
            }
            QLineEdit:focus {
                border: 1px solid #7aa7ff;
                outline: none;
            }
            
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 20, 30, 20)
        card_layout.setSpacing(15)
        card_layout.addLayout(form)
        card_layout.addWidget(self.err)
        card_layout.addSpacing(8)
        card_layout.addWidget(self.btn_login,0, Qt.AlignHCenter)

        root = QVBoxLayout(self)
        root.setContentsMargins(0,0,0,0)
        root.addStretch(1)
        root.addWidget(card, 0, Qt.AlignHCenter)
        root.addStretch(1)
    
    def show_error(self, message):
        self.err.setText(message)
        self.err.setVisible(True)
    
    def clear_error(self):
        self.err.setText("")
        self.err.setVisible(False)
    
    def validate(self):
        username = self.in_username.text().strip()
        password = self.in_password.text().strip()
        
        if not username or not USERNAME_RE.match(username):
            return False, "Username is required."
        if not password or not PASSWORD_RE.match(password):
            return False, "Password is required."
        
        return True, {
            "username": username,
            "password": password,
        }
    
    def on_submit(self):
        self.clear_error()
        ok, payload_or_msg = self.validate()
        if not ok:
            self.show_error(payload_or_msg)
            return
        req = {
            "type": "AUTH.LOGIN_REQ",
            "id": str(uuid.uuid4()),
            "payload": payload_or_msg
        }
        try:
            resp = jsonl_request(HOST, PORT, req)
        except Exception as e:
            self.show_error(f"Network error: {e}")
            return
        rtype = resp.get("type")
        payload = resp.get("payload", {})
        if rtype == "AUTH.LOGIN_RES":
            user_preview = payload.get("user", {})
            self.logged_in.emit(user_preview)
            
            self.in_username.clear()
            self.in_password.clear()

        elif rtype == "ERROR":
            msg = payload.get("message", "Unknown error")
            self.show_error(f"Error: {msg}")
        
        else:
            self.show_error(f"Unexpected response from server. {rtype}")

class RidePage(QWidget):
    """Ride page with sub-navigation: Overview | Chat | Ratings"""
    def __init__(self):
        super().__init__()
        h = QHBoxLayout(self)

        # --- Left sub-navigation ---
        nav = QVBoxLayout()
        self.btn_overview = QPushButton("Overview")
        self.btn_chat = QPushButton("Chat")
        self.btn_rate = QPushButton("Ratings")

        for b in (self.btn_overview, self.btn_chat, self.btn_rate):
            b.setCheckable(True)
            b.setAutoExclusive(True)
            nav.addWidget(b)
        nav.addStretch(1)

        # --- Right sub-stack ---
        self.sub = QStackedWidget()
        self.sub.addWidget(title_page("Ride - Overview"))
        self.sub.addWidget(title_page("Ride - Chat"))
        self.sub.addWidget(title_page("Ride - Ratings"))

        # --- Connect buttons ---
        self.btn_overview.clicked.connect(lambda: self.sub.setCurrentIndex(0))
        self.btn_chat.clicked.connect(lambda: self.sub.setCurrentIndex(1))
        self.btn_rate.clicked.connect(lambda: self.sub.setCurrentIndex(2))

        # Default view
        self.btn_overview.setChecked(True)
        self.sub.setCurrentIndex(0)

        left = QWidget()
        left.setLayout(nav)
        left.setMinimumWidth(160)

        h.addWidget(left)
        h.addWidget(self.sub, 1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AUBus")
        self.resize(1000, 650)

        # Root stack: [Auth Page, App Page]
        self.root = QStackedWidget()
        self.setCentralWidget(self.root)

        # ---- Auth Page ----
        auth_page = QWidget()
        v_auth = QVBoxLayout(auth_page)

        tabs = QTabWidget()
        self.login_tab = LoginForm()
        self.register_tab = RegisterForm()
        tabs.addTab(self.login_tab, "Login")
        tabs.addTab(self.register_tab, "Register")

        # continue_btn = QPushButton("Continue")
        # continue_btn.clicked.connect(self.goto_app)

        v_auth.addWidget(tabs, 1)
        # v_auth.addWidget(continue_btn)
        self.root.addWidget(auth_page)

        # ---- App Page ----
        app_page = QWidget() 
        self.root.addWidget(app_page)
        h = QHBoxLayout(app_page)

        # Left sidebar
        left = QWidget()
        left_l = QVBoxLayout(left)

        self.btn_profile = QPushButton("Profile")
        self.btn_sched = QPushButton("Schedule")
        self.btn_ride = QPushButton("Ride")

        for b in (self.btn_profile, self.btn_sched, self.btn_ride):
            b.setCheckable(True)
            b.setAutoExclusive(True)
            left_l.addWidget(b)
        left_l.addStretch(1)

        # Right stack (Profile / Schedule / Ride)
        self.stack = QStackedWidget()
        self.profile_label = QLabel("Profile Information")
        profile_page = QWidget()
        pv = QVBoxLayout(profile_page)
        pv.addWidget(self.profile_label, 0 , Qt.AlignCenter)
        pv.addStretch(1)
        self.stack.addWidget(profile_page)
        self.stack.addWidget(title_page("Your Schedule"))
        self.stack.addWidget(RidePage())

        # Connect sidebar buttons
        self.btn_profile.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.btn_sched.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.btn_ride.clicked.connect(lambda: self.stack.setCurrentIndex(2))

        # Default page
        self.btn_profile.setChecked(True)
        self.stack.setCurrentIndex(0)

        h.addWidget(left)
        h.addWidget(self.stack, 1)

        self.login_tab.logged_in.connect(self.after_login)

    def goto_app(self):
        """Switch to the main app after clicking 'Continue'."""
        self.root.setCurrentIndex(1)

    def after_login(self, user_preview):
        """called on emitted signal"""
        name = user_preview.get("name", "")
        email = user_preview.get("email", "")
        username = user_preview.get("username", "")
        area = user_preview.get("area", "")
        self.profile_label.setText(f"Welcome, {name}!")
        self.root.setCurrentIndex(1)
        self.btn_profile.setChecked(True)
        self.stack.setCurrentIndex(0)
        #self.profile_label.setText(info)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
