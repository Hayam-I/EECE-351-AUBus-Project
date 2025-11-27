import sys
import traceback
import socket
import uuid
import logging
from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import pyqtSignal, QObject
from client.net import send_json, recv_json

def excepthook(exc_type, exc, tb):
    traceback.print_exception(exc_type, exc, tb)
    QMessageBox.critical(None, "Unhandled Error", f"{exc_type.__name__}: {exc}")
sys.excepthook = excepthook

def set_visible(widget, visible: bool):
    widget.setVisible(visible)


class JsonlSession(QObject):
    
    def send_json(self, obj: dict):
        self.ensure_connected()
        send_json(self.sock, obj)

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
