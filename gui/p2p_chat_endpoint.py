# gui/p2p_chat_endpoint.py
import socket
import threading

from PyQt5.QtCore import QObject, pyqtSignal


class P2PChatEndpoint(QObject):
    """
    Minimal, robust text chat endpoint over a TCP socket.

    Protocol: UTF-8 lines separated by '\n'.
    - send("hello") -> b"hello\n"
    - reader thread buffers until '\n', then emits messageReceived(str)
    """

    messageReceived = pyqtSignal(str)
    disconnected = pyqtSignal()

    def __init__(self, sock: socket.socket, parent=None):
        super().__init__(parent)
        self._sock = sock
        try:
            # make sure it's in blocking mode (no timeouts)
            self._sock.settimeout(None)
        except Exception:
            pass

        self._sock_lock = threading.Lock()
        self._closed = False

        # Start reader thread
        self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    # -----------------
    # Public API
    # -----------------
    def send(self, text: str) -> None:
        """Send one line of text. Raises on error."""
        if self._closed:
            raise RuntimeError("Socket already closed in P2PChatEndpoint.send")

        data = (text + "\n").encode("utf-8", errors="replace")
        with self._sock_lock:
            self._sock.sendall(data)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass
        self.disconnected.emit()

    # -----------------
    # Internal
    # -----------------
    def _reader_loop(self):
        buf = b""
        try:
            while not self._closed:
                chunk = self._sock.recv(4096)
                if not chunk:
                    # Remote closed
                    break
                buf += chunk

                # Emit complete lines
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        text = line.decode("utf-8", errors="replace")
                    except Exception:
                        text = ""
                    if text != "":
                        self.messageReceived.emit(text)
        except Exception as e:
            print("P2PChatEndpoint reader error:", e)
        finally:
            # Reader loop is ending; close socket and emit disconnected
            if not self._closed:
                self.close()
