import json
import re
import socket
import uuid
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QFormLayout, QLineEdit, QMessageBox
)
from PyQt5.QtCore import Qt

# validation regex
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,20}$")
PASSWORD_RE = re.compile(r"^.{6,20}$")
EMAIL_RE    = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

# transport config
HOST = "127.0.0.1"
PORT = 6000
SOCKET_TIMEOUT = 4.0
ENCODING = "utf-8"


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

        #rating = self.spin.value()
        # try:
        #     # self.session.request({
        #     #     "type": "RIDE.RATE_REQ",
        #     #     "id": str(uuid.uuid4()),
        #     #     "payload": {
        #     #         #"request_id": self.request_id,  # e.g. "req_7"
        #     #         #"rating": rating,
        #     #     },
        #     # })
        # except Exception as e:
        #     QMessageBox.warning(self, "Rating failed", f"Could not send rating: {e}")
        #     return

        #self.accept()

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
