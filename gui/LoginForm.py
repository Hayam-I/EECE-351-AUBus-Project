import re
import uuid
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QFormLayout, QLineEdit
)
from PyQt5.QtCore import Qt, pyqtSignal
from gui.session import JsonlSession

# validation regex
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,20}$")
PASSWORD_RE = re.compile(r"^.{6,20}$")
EMAIL_RE    = re.compile(r"^[^@]+@[^@]+\.[^@]+$")


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
        rtype = resp.get("type")
        payload = resp.get("payload",{})
        if rtype == "AUTH.LOGIN_RES":
            user_preview = payload.get("user", {})
            self.logged_in.emit(user_preview)
            self.in_username.clear(); self.in_password.clear()
        elif rtype == "ERROR":
            self.show_error(payload.get("message","Unknown error"))
        else:
            self.show_error(f"Unexpected response: {rtype}")
