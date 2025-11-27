import sys
import traceback
import socket
import uuid
import threading
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget, QMessageBox)
from PyQt5.QtCore import pyqtSignal


#page imports
from gui.dark_theme import DARK_STYLESHEET
from gui.light_theme import LIGHT_STYLESHEET
from gui.title_page import title_page
from gui.session import JsonlSession
from gui.RegisterForm import RegisterForm
from gui.LoginForm import LoginForm
from gui.ProfileScreen import ProfileScreen
from gui.ScheduleInfoScreen import ScheduleInfoScreen
from gui.ScheduleScreen import ScheduleScreen
from gui.p2p_chat_endpoint import P2PChatEndpoint
from gui.RideRequestPage import RideRequestPage
from gui.DriverRidePage import DriverRidePage
from gui.CurrentRidePage import CurrentRidePage
from gui.RideDialog import RateRideDialog


# ===== transport config =====
HOST = "127.0.0.1"
PORT = 6000
SOCKET_TIMEOUT = 4.0
ENCODING = "utf-8"

def apply_theme(mode: str = "dark"):
    app = QApplication.instance()
    if app is None:
        return
    app.setStyle("Fusion")
    if mode == "dark":
        app.setStyleSheet(DARK_STYLESHEET)
    else:
        app.setStyleSheet(LIGHT_STYLESHEET)

def excepthook(exc_type, exc, tb):
    traceback.print_exception(exc_type, exc, tb)
    QMessageBox.critical(None, "Unhandled Error", f"{exc_type.__name__}: {exc}")
sys.excepthook = excepthook

def set_visible(widget, visible: bool):
    widget.setVisible(visible)


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

        # ---- Auth Page ----
        self.auth_page = QWidget()
        v_auth = QVBoxLayout(self.auth_page)
        tabs = QTabWidget()
        self.login_tab = LoginForm(self.session)
        self.register_tab = RegisterForm(self.session)
        tabs.addTab(self.login_tab, "Login")
        tabs.addTab(self.register_tab, "Register")
        v_auth.addWidget(tabs, 1)
        self.root.addWidget(self.auth_page)

        # ---- App Page ----
        self.app_page = QWidget()
        self.root.addWidget(self.app_page)
        h = QHBoxLayout(self.app_page)

        left = QWidget()
        left.setObjectName("SideBar")
        left_l = QVBoxLayout(left)
        self.btn_profile = QPushButton("Profile")
        self.btn_sched   = QPushButton("Schedule")
        self.btn_ride    = QPushButton("Ride")
        self.btn_current = QPushButton("Current Ride")
        self.btn_logout = QPushButton("Logout")
        
        for b in (self.btn_profile, self.btn_sched, self.btn_ride, self.btn_current):
            b.setCheckable(True)
            b.setAutoExclusive(True)
            left_l.addWidget(b)
        left_l.addStretch(1)

        

        left_l.addWidget(self.btn_logout)
        self.btn_logout.clicked.connect(self.on_logout)

        

        self.stack = QStackedWidget()

        
        self.profile_page = title_page("Profile (login required)")
        self.stack.addWidget(self.profile_page)

        self.schedule_page = title_page("Your Schedule")
        self.stack.addWidget(self.schedule_page)

        self.ride_page = RideRequestPage(self.session)
        self.stack.addWidget(self.ride_page)

        self.current_ride_page = CurrentRidePage(self.session)
        self.stack.addWidget(self.current_ride_page)
        self.current_ride_page.complete_btn.clicked.connect(self.complete_ride)

        self.btn_profile.clicked.connect(self.show_profile_page)
        self.btn_sched.clicked.connect(lambda: self.stack.setCurrentWidget(self.schedule_page))
        self.btn_ride.clicked.connect(lambda: self.stack.setCurrentWidget(self.ride_page))
        self.btn_current.clicked.connect(lambda: self.stack.setCurrentWidget(self.current_ride_page))

        self.btn_current.setEnabled(False)
        self.btn_profile.setChecked(True)
        self.stack.setCurrentWidget(self.profile_page)
        
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(16,16,16,16)
        center_layout.addWidget(self.stack, 1)
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

    def after_login(self, user_preview: dict):
        self.user_preview = user_preview
        # Profile screen
        profile = ProfileScreen(self.session, user_preview)
        profile.driverModeChanged.connect(self.on_driver_mode_changed)
        user_preview.setdefault("rating_avg", 0.0)
        user_preview.setdefault("rating_count", 0)
        profile.update_from_user_preview(user_preview)
        
        self.stack.removeWidget(self.profile_page)
        self.profile_page.deleteLater()
        self.profile_page = profile
        self.stack.insertWidget(0, self.profile_page)

        is_driver = bool(user_preview.get("is_driver", False))
        self.on_driver_mode_changed(is_driver)

        self.root.setCurrentWidget(self.app_page)
        self.stack.setCurrentWidget(self.profile_page)
        self.btn_profile.setChecked(True)

        
    def show_profile_page(self):
        """
        Whenever the user opens Profile, synchronously ask the server for the
        latest profile (including updated rating) and immediately refresh the UI.
        """
        if self.session is not None:
            req = {
                "type": "PROFILE.GET_REQ",
                "id": str(uuid.uuid4()),
                "payload": {}  # current user
            }
            try:
                # Use request() so we get the response right here
                resp = self.session.request(req)
                if resp.get("type") == "PROFILE.GET_RES":
                    user = (resp.get("payload") or {}).get("user") or {}

                    if self.user_preview is None:
                        self.user_preview = {}

                    # merge fresh data
                    self.user_preview.update(user)

                    # server returns 'rating' = rating_avg from users table
                    rating = user.get("rating")
                    if rating is not None:
                        self.user_preview["rating_avg"] = rating

                    # let ProfileScreen repaint itself
                    if hasattr(self, "profile_page") and self.profile_page is not None:
                        try:
                            self.profile_page.update_from_user_preview(self.user_preview)
                        except Exception as e:
                            print("show_profile_page: failed to update profile screen:", e)

            except Exception as e:
                print("PROFILE.GET_REQ failed:", e)

        # finally, show the profile page
        self.stack.setCurrentWidget(self.profile_page)



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
            self.ride_page.rideAccepted.connect(self.on_driver_ride_accepted)
        else:
            self.ride_page = RideRequestPage(self.session)

        self.stack.addWidget(self.ride_page)
        

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
        self.root.setCurrentWidget(self.auth_page)
        self.btn_profile.setChecked(False)
        self.btn_sched.setChecked(False)
        self.btn_ride.setChecked(False)
        self.btn_current.setEnabled(False)
        self.stack.setCurrentWidget(self.profile_page)

    def _on_incoming_p2p_connection(self, conn, addr):
        """Attach an incoming passenger P2P socket on the GUI thread."""
        # close old chat endpoint if any
        if getattr(self, "chat_endpoint", None) is not None:
            try:
                self.chat_endpoint.close()
            except Exception:
                pass

        # wrap the accepted socket
        self.chat_endpoint = P2PChatEndpoint(conn, self)
        self.chat_endpoint.messageReceived.connect(self.on_p2p_message)
        self.chat_endpoint.disconnected.connect(self.on_p2p_disconnected)

        # let the driver see that the passenger connected
        # if hasattr(self, "current_ride_page") and self.current_ride_page:
        #     self.current_ride_page.chat_box.append(
        #         f"<i>Passenger connected from {addr[0]}:{addr[1]}</i>"
        #     )

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
                        print(f"P2P connection from {addr}")
                        # hand off to GUI thread via signal
                        self.incoming_p2p_connection.emit(conn, addr)
                        # DO NOT close conn here – P2PChatEndpoint owns it now
                except Exception as e:
                    print("p2p_loop error:", e)
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

        ep = getattr(self, "chat_endpoint", None)
        self.chat_endpoint = None  # remove reference first
        if ep:
            try:
                ep.close()
            except:
                pass


    def on_p2p_message(self, text: str):
        page = getattr(self, "current_ride_page", None)
        if page is not None:
            page.append_bubble(text, outgoing = False)
        

    def on_p2p_disconnected(self):
        """Handle P2P disconnect."""
        if hasattr(self, "current_ride_page") and self.current_ride_page is not None:
            self.current_ride_page.append_bubble("<i>Chat disconnected.</i>", outgoing = False)
        if getattr(self, "chat_endpoint", None) is not None:
            self.chat_endpoint = None

    def toggle_theme(self):
        if getattr(self, "current_theme", "dark") == "dark":
            self.current_theme = "light"
            apply_theme("light")
            self.btn_theme.setText("Dark mode")
        else:
            self.current_theme = "dark"
            apply_theme("dark")
            self.btn_theme.setText("Light mode")


    def on_push_received(self, msg: dict):
        t = msg.get("type")
        payload = msg.get("payload", {})

        if t == "RIDE.MATCHED":
            #debug message
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
                self.current_ride_page.load_for_driver(payload)
            else:
                self.current_ride_page.load_for_passenger(payload)
                self.on_ride_matched(msg)
                driver_ip = payload.get("driver_ip")
                driver_port = payload.get("driver_port")

                if driver_ip and driver_port:
                    try:
                        sock  = socket.create_connection((driver_ip, int(driver_port)), timeout = 5.0)
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
                            f"<i>Driver did not provide chat info</i>", outgoing=False
                        )

        elif t == "REQUEST.CLOSED":
            self.on_request_closed(msg)

        elif t == "DRIVER.BROADCAST":
            self.on_driver_broadcast(msg)
        
        elif t == "PROFILE.UPDATED":
            # Update the cached user preview
            if payload:
                if "rating_avg" in payload:
                    self.user_preview["rating_avg"] = payload["rating_avg"]
                if "rating_count" in payload:
                    self.user_preview["rating_count"] = payload["rating_count"]

            # If the profile screen is open, refresh it
            if hasattr(self, "profile_page") and self.profile_page is not None:
                try:
                    self.profile_page.update_from_user_preview(self.user_preview)
                except Exception as e:
                    print("profile update failed:", e)

        elif t == "RIDE.RATE_RES":
            # after rating, ask server for fresh profile
            self.session.send_json({
                "type": "PROFILE.GET_REQ",
                "id": str(uuid.uuid4()),
                "payload": {}  # current user
            })
        
        elif t == "PROFILE.GET_RES":
            # Response to PROFILE.GET_REQ: refresh local preview and profile screen
            user = payload.get("user") or {}
            if not user:
                return

            if self.user_preview is None:
                self.user_preview = {}

            # Update preview with whatever came from the server
            self.user_preview.update(user)

            # PROFILE.GET_RES returns `rating`, but ProfileScreen expects rating_avg
            rating = user.get("rating")
            if rating is not None:
                self.user_preview["rating_avg"] = rating

            if hasattr(self, "profile_page") and self.profile_page is not None:
                try:
                    self.profile_page.update_from_user_preview(self.user_preview)
                except Exception as e:
                    print("PROFILE.GET_RES: failed to update profile screen:", e)

    def on_ride_matched(self, msg: dict):
        payload = msg.get("payload", {})
        if isinstance(self.ride_page, RideRequestPage):
            self.ride_page.handle_matched(payload)

    def on_request_closed(self, msg: dict):
        """Called when server notifies that a ride was closed"""
        payload = msg.get("payload", {})
        reason = payload.get("reason")
        req_id = payload.get("request_id")
        if isinstance(self.ride_page, DriverRidePage):
            self.ride_page.handle_request_closed(payload)

        if isinstance(self.ride_page, RideRequestPage):
        # reset the passenger's request form state
            self.ride_page.set_idle_state()
        
        if reason == "completed" and req_id:
            # passenger rates driver
            dlg = RateRideDialog(req_id, self.session, self)
            dlg.exec()

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

    def complete_ride(self):
        # DRIVER ONLY
        if not self.active_request_id:
            QMessageBox.warning(self, "No active ride", "No active ride to rate")
            return
        
        payload = {"request_id": self.active_request_id}   # store this on match
        try:
            res = self.session.request({"type": "RIDE.COMPLETE_REQ", "payload": payload})
        except Exception as e:
            QMessageBox.warning(self, "Ride Completed", f"Network: {e}")
            return
        
        if res["type"] == "RIDE.COMPLETE_RES":
            QMessageBox.information(self, "Ride Completed", "Ride successfully completed.")

            # Driver rates passenger
            if self.active_request_id:
                dlg = RateRideDialog(self.active_request_id, self.session, self)
                dlg.exec_()

            self.return_to_idle_state()
        
        elif res["type"] == "ERROR":
            p = res.get("payload", {})
            QMessageBox.warning(self, "Ride Completed", p.get("message", "Failed to complete ride."))
        else:
            QMessageBox.warning(self, "Ride Completed", f"Unexpected response: {res.get('type')}")
            
    
    def on_server_message(self, msg: dict):
        t = msg.get("type")
        p = msg.get("payload") or {}

        if t == "PROFILE.GET_RES":
            user = p.get("user") or {}
            self.current_user_profile = user
            self.profile_page.update_from_profile(user)

    
    



    def return_to_idle_state(self):
        # driver or passenger

        # Disable current ride
        self.btn_current.setEnabled(False)

        # Enable ride
        self.btn_ride.setEnabled(True)
        self.btn_ride.setChecked(True)


        # Switch back to ride page
        self.stack.setCurrentWidget(self.ride_page)
        self.active_request_id = None

        # clear chat/info
        self.current_ride_page.chat_box.clear()
        self.current_ride_page.info_label.setText("No active ride")

        ep = getattr(self, "chat_endpoint", None)
        self.chat_endpoint = None  # remove reference first
        if ep:
            try:
                ep.close()
            except:
                pass


    def on_driver_ride_accepted(self, request_id: str, payload: dict):
        """
        Called when THIS driver accepts a ride successfully.
        We immediately go into 'current ride' state for the driver.
        """
        # Disable ride tab, enable Current Ride tab
        self.btn_ride.setEnabled(False)
        self.btn_current.setEnabled(True)

        # Switch UI to Current Ride
        self.btn_current.setChecked(True)
        self.stack.setCurrentWidget(self.current_ride_page)

        # Remember which request this ride is for (used by complete_ride)
        self.active_request_id = request_id

        # Build a payload compatible with load_for_driver
        match_payload = dict(payload)
        match_payload.setdefault("request_id", request_id)

        self.current_ride_page.load_for_driver(match_payload)

    def send_chat_message(self, text: str) -> bool:
        """Send a chat message over the active P2P endpoint.

        Returns True on success, False on failure.
        Also prints the exception so we know what went wrong.
        """
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





def main():
    app = QApplication(sys.argv)
    apply_bento_theme(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()