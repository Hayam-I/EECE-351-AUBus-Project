import sys
import traceback
import uuid
import random
from client.map_selector import MapSelector
from PyQt5.QtWidgets import (
    QWidget, QFrame,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFormLayout,
    QLineEdit, QMessageBox, QComboBox, QTimeEdit, QGraphicsOpacityEffect
)
from PyQt5.QtCore import Qt, QDateTime, QTimer, QDate, QEasingCurve, QPropertyAnimation

from gui.session import JsonlSession

def excepthook(exc_type, exc, tb):
    traceback.print_exception(exc_type, exc, tb)
    QMessageBox.critical(None, "Unhandled Error", f"{exc_type.__name__}: {exc}")
sys.excepthook = excepthook

def set_visible(widget, visible: bool):
    widget.setVisible(visible)


class TrueFalseQuizWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        card = QFrame(self)
        card.setFrameShape(QFrame.StyledPanel)
        card.setObjectName("QuizCard") 

        outer = QVBoxLayout(self)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # score / streak
        self.score_label = QLabel("Score: 0/0  •  Streak: 0")
        self.score_label.setObjectName("QuizScore")
        self.score_label.setAlignment(Qt.AlignCenter)

        self.title = QLabel("A Networking Game: True or False?")
        self.title.setObjectName("QuizTitle")
        self.title.setAlignment(Qt.AlignCenter)

        self.question_label = QLabel("")
        self.question_label.setObjectName("QuizQuestion")
        self.question_label.setWordWrap(True)
        self.question_label.setAlignment(Qt.AlignCenter)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_true = QPushButton("True")
        self.btn_false = QPushButton("False")

        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_true)
        btn_row.addWidget(self.btn_false)
        btn_row.addStretch(1)

        self.feedback = QLabel("")
        self.feedback.setObjectName("QuizFeedback")
        self.feedback.setWordWrap(True)
        self.feedback.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.score_label)
        layout.addWidget(self.title)
        layout.addWidget(self.question_label)
        layout.addLayout(btn_row)
        layout.addWidget(self.feedback)

        self.questions = [
            {"text": "Wi-Fi is short for 'Wireless Fidelity'.", "answer": False,
             "explanation": "It's just a brand name, it doesn’t officially stand for anything."},
            {"text": "TCP is designed to provide reliable, ordered delivery of data between applications.", "answer": True,
             "explanation": "TCP handles acknowledgements, retransmissions, and ordering."},
            {"text": "UDP guarantees that packets arrive in the correct order.", "answer": False,
             "explanation": "UDP is connectionless and doesn’t guarantee delivery or order."},
            {"text": "DNS is used to translate human-readable names like example.com into IP addresses.", "answer": True,
             "explanation": "Exactly – it’s basically the Internet’s phonebook."},
            {"text": "IPv4 has more available addresses than IPv6.", "answer": False,
             "explanation": "IPv6 has an astronomically larger address space than IPv4."},
            {"text": "A MAC address operates at Layer 2 of the OSI model.", "answer": True,
             "explanation": "MAC addresses belong to the Data Link layer."},
            {"text": "The loopback IP address 127.0.0.1 always refers to the local machine.", "answer": True,
             "explanation": "Loopback lets a host send packets to itself."},
            {"text": "HTTP by itself encrypts all web traffic.", "answer": False,
             "explanation": "Only HTTPS (HTTP over TLS) provides encryption."},
            {"text": "Port 443 is the default port for HTTPS.", "answer": True,
             "explanation": "HTTP usually uses 80, HTTPS uses 443."},
            {"text": "Ping is typically implemented using the ICMP protocol.", "answer": True,
             "explanation": "Ping sends ICMP Echo Request and listens for Echo Reply."},
            {"text": "NAT allows multiple devices to share one public IPv4 address.", "answer": True,
             "explanation": "That’s how most home routers work today."},
            {"text": "A switch normally works at the same OSI layer as a router.", "answer": False,
             "explanation": "A switch is Layer 2; a router is Layer 3 (in classic terms)."},
            {"text": "VLANs let you logically split one physical network into multiple virtual networks.", "answer": True,
             "explanation": "They isolate broadcast domains and traffic."},
            {"text": "Traceroute can show the sequence of routers a packet passes through.", "answer": True,
             "explanation": "Each hop along the path can respond with an ICMP message."},
            {"text": "2.4 GHz Wi-Fi usually has longer range than 5 GHz Wi-Fi.", "answer": True,
             "explanation": "Lower frequencies penetrate walls better but offer less throughput."},
            {"text": "Packet loss will never affect real-time voice or gaming traffic.", "answer": False,
             "explanation": "Even small packet loss can cause lag, glitches, and stutter."},
            {"text": "A default gateway is typically a switch on the network.", "answer": False,
             "explanation": "The default gateway is usually a router, not a switch."},
            {"text": "ARP is used to map IP addresses to MAC addresses on a local network.", "answer": True,
             "explanation": "It’s how hosts learn each other’s MAC addresses."},
            {"text": "VPNs create encrypted tunnels that can make remote networks appear local.", "answer": True,
             "explanation": "Your device behaves like it is inside that remote network."},
            {"text": "A higher bandwidth link always means lower latency.", "answer": False,
             "explanation": "Bandwidth is capacity; latency is delay. They are related but different."},
            {"text": "BGP is the routing protocol that connects large networks and ISPs together.", "answer": True,
             "explanation": "BGP is the backbone protocol of the global Internet."},
            {"text": "Firewalls can filter traffic based on ports, IPs, and protocols.", "answer": True,
             "explanation": "They enforce security policies at network boundaries."},
            {"text": "Undersea fiber-optic cables carry most long-distance Internet traffic.", "answer": True,
             "explanation": "Satellite is used too, but the majority is via undersea cables."},
            {"text": "QoS (Quality of Service) is used to make downloads faster at all costs.", "answer": False,
             "explanation": "QoS is about prioritization, e.g., giving voice higher priority than bulk transfers."},
            {"text": "An SSID is the visible “name” of a Wi-Fi network.", "answer": True,
             "explanation": "That’s what you see when you scan for networks on your phone."},
            {"text": "Mesh Wi-Fi systems use multiple nodes to improve coverage in larger spaces.", "answer": True,
             "explanation": "They help avoid dead zones in big apartments or houses."},
            {"text": "MAC addresses are always globally unique in practice, with no exceptions.", "answer": False,
             "explanation": "They are designed to be unique, but collisions and spoofing can happen."},
            {"text": "DHCP is responsible for dynamically assigning IP addresses to clients.", "answer": True,
             "explanation": "It saves you from configuring every IP manually."},
            {"text": "CDNs (Content Delivery Networks) typically slow down website loading times.", "answer": False,
             "explanation": "They speed things up by serving content from closer locations."},
            {"text": "The OSI model has 7 layers, including Application, Transport, and Network.", "answer": True,
             "explanation": "It’s a conceptual framework used to understand networking."},
        ]

        self._last_index = None
        self._current_question = None

        self.score = 0
        self.total = 0
        self.streak = 0

        self.opacity_effect = QGraphicsOpacityEffect(self.feedback)
        self.feedback.setGraphicsEffect(self.opacity_effect)

        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.fade_anim.setDuration(350)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.OutQuad)

        self.btn_true.clicked.connect(lambda: self.check_answer(True))
        self.btn_false.clicked.connect(lambda: self.check_answer(False))

        
        self.next_question()

    def update_score_label(self):
        self.score_label.setText(
            f"Score: {self.score}/{self.total}  •  Streak: {self.streak}"
        )

    def next_question(self):
        if not self.questions:
            self.question_label.setText("No questions loaded.")
            self.feedback.setText("")
            return

        if len(self.questions) == 1:
            idx = 0
        else:
            while True:
                idx = random.randint(0, len(self.questions) - 1)
                if idx != self._last_index:
                    break

        self._last_index = idx
        self._current_question = self.questions[idx]
        self.question_label.setText(self._current_question["text"])
        self.feedback.setStyleSheet("") 
        self.feedback.setText("Lock in your answer")

    def check_answer(self, user_answer: bool):
        if not self._current_question:
            return

        correct = self._current_question["answer"]
        explanation = self._current_question.get("explanation", "")

        self.total += 1
        if user_answer == correct:
            self.score += 1
            self.streak += 1
            self.feedback.setStyleSheet("color: #22c55e;")
            msg_prefix = random.choice(["Nice!", "Correct!", "Nailed it!"])
        else:
            self.streak = 0
            self.feedback.setStyleSheet("color: #ef4444;")
            msg_prefix = random.choice(["Not quite.", "Nope.", "Close!"])

        self.update_score_label()
        self.feedback.setText(f"{msg_prefix} {explanation}")

        self.fade_anim.stop()
        self.opacity_effect.setOpacity(0.0)
        self.fade_anim.start()

        QTimer.singleShot(2000, self.next_question)


class RideRequestPage(QWidget):
    def __init__(self, session: JsonlSession, parent=None):
        super().__init__(parent)
        self.session = session

        self.selected_lat = None
        self.selected_lon = None

        self.btn_pick_location = QPushButton("Pick location on map")
        self.btn_pick_location.clicked.connect(self.open_map)

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(3000)
        self.poll_timer.timeout.connect(self._poll_for_match)

        self.current_request_id: str | None = None

        self.in_area = QLineEdit()
        self.in_area.setPlaceholderText("e.g Hamra")

        self.cb_direction = QComboBox()
        self.cb_direction.addItems(["to_AUB", "from_AUB"])
        self.cb_direction.currentTextChanged.connect(self._update_direction_hints)


        now = QDateTime.currentDateTime()
        self.time_edit = QTimeEdit(now.time())
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setKeyboardTracking(False)

        self.btn_submit = QPushButton("Request Ride")
        self.btn_submit.clicked.connect(self.on_submit)

        self.btn_cancel = QPushButton("Cancel request")
        set_visible(self.btn_cancel, False)
        self.btn_cancel.clicked.connect(self.on_cancel_clicked)
        self._update_direction_hints()

        self.min_driver_rating_combo = QComboBox(self)
        self.min_driver_rating_combo.addItem("Any rating", 0.0)
        self.min_driver_rating_combo.addItem("1 ★ and up", 1.0)
        self.min_driver_rating_combo.addItem("2 ★ and up", 2.0)
        self.min_driver_rating_combo.addItem("3 ★ and up", 3.0)
        self.min_driver_rating_combo.addItem("4 ★ and up", 4.0)
        self.min_driver_rating_combo.addItem("5 ★ only", 5.0)


        # ---- Layout ----
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignCenter | Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        form.addRow("Area:", self.in_area)
        form.addRow("", self.btn_pick_location)       
        form.addRow("Direction:", self.cb_direction)
        form.addRow("Departure Time:", self.time_edit)
        form.addRow(QLabel("Min driver rating:"), self.min_driver_rating_combo)

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

        self.quiz = TrueFalseQuizWidget(self)
        self.quiz.setVisible(False)

        root = QVBoxLayout(self)
        root.addLayout(form)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.btn_submit)
        row.addWidget(self.btn_cancel)
        root.addWidget(self.quiz)
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
        self.err.setText(msg)
        self.err.setVisible(True)
        self.ok.setVisible(False)

    def show_ok(self, msg):
        self.ok.setText(msg)
        self.ok.setVisible(True)
        self.err.setVisible(False)

    def _iso_string(self) -> str:
        """Return departure time as ISO string: today's date + chosen time."""
        today = QDate.currentDate()
        t = self.time_edit.time()
        dt = QDateTime(today, t)
        return dt.toString("yyyy-MM-dd HH:mm")

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

        now = QDateTime.currentDateTime()
        selected_dt = QDateTime(QDate.currentDate(), self.time_edit.time())
        delta_secs = now.secsTo(selected_dt)

        # if time is in the past or more than 60 minutes ahead, reject
        if delta_secs < -60 or delta_secs > 61 * 60:
            self.show_error(
                "Departure time must be within the next Hour.\n"
                "Please choose a time today that is no more than 1 Hour from now."
            )
            return

        min_driver_rating = float(self.min_driver_rating_combo.currentData() or 0.0)


        payload = {
            "area": area,
            "direction": self.cb_direction.currentText(),
            "time_iso": self._iso_string(),
            "lat":  float(self.selected_lat),
            "lon": float(self.selected_lon),
        }

        if min_driver_rating > 0.0:
            payload["min_driver_rating"] = min_driver_rating



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
            set_visible(self.btn_cancel, True)
            set_visible(self.btn_submit, False)

            self.lbl_request_id.setText(f"Request ID: {req_id}")
            self.lbl_status.setText(f"Status: open — compatible drivers found: {found}")
            self.show_ok("Ride request created.")
            self.poll_timer.start()
            self.quiz.setVisible(True)

        elif rtype == "ERROR":
            code = p.get("code")
            msg = p.get("message", "Failed to create ride request")
            if code == "PASSENGER_BUSY":
                self.current_request_id = None
                set_visible(self.btn_cancel, False)
                set_visible(self.btn_submit, True)
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


    def handle_matched(self, payload):
        self.lbl_status.setText("Status: A driver has accepted your request!")
        set_visible(self.btn_cancel, False)
        self.quiz.setVisible(False)

    def set_idle_state(self):
        self.current_request_id = None

        try: self.poll_timer.stop()
        except: pass

        set_visible(self.btn_cancel, False)
        set_visible(self.btn_submit, True)

        self.lbl_request_id.setText("Request ID: —")
        self.lbl_status.setText("Status: —")
        self.quiz.setVisible(False)

    def _poll_for_match(self):
        if not self.current_request_id:
            return
        try:
            req = {"type": "PING", "id": str(uuid.uuid4()), "payload": {}}
            self.session.request(req)
        except Exception as e:
            print(f"poll_for_match error: {e}")

