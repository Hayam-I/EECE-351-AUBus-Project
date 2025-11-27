import html
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget, QFormLayout,
    QLineEdit, QMessageBox, QCheckBox, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTimeEdit, QDateTimeEdit, QTextEdit, QDialog, QSpinBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QDateTime, QTimer, QObject
from PyQt5.QtGui import QTextCursor, QTextBlockFormat



class CurrentRidePage(QWidget):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session

        v = QVBoxLayout(self)

        # Top info label (who you're riding with)
        self.info_label = QLabel("No active ride")
        self.info_label.setWordWrap(True)
        v.addWidget(self.info_label)

        # Chat area
        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)
        self.chat_box.setStyleSheet("QTextEdit, QTextEdit * { background: transparent; }")

        v.addWidget(self.chat_box, 1)

        # Chat input
        self.chat_input = QLineEdit()
        self.chat_input.setObjectName("chatInput")  # so stylesheet can target it
        self.chat_input.setPlaceholderText("Type a message...")
        v.addWidget(self.chat_input)

        # Buttons row
        h = QHBoxLayout()
        self.send_btn = QPushButton("Send")
        self.complete_btn = QPushButton("Complete Ride")
        h.addWidget(self.send_btn)
        h.addStretch(1)
        h.addWidget(self.complete_btn)
        v.addLayout(h)

        # hide complete button by default (passenger view)
        self.complete_btn.hide()

        self.send_btn.clicked.connect(self.on_send_clicked)



    # ===== Chat bubbles =====


    def append_bubble(self, text: str, outgoing: bool, timestamp=None):
        """
        Chat bubbles with proper left/right alignment using QTextBlockFormat.
        """
        if not text:
            return

        safe = html.escape(text).replace("\n", "<br/>")

        mw = self.window()
        other_name = getattr(mw, "other_party_name", "Them") if mw else "Them"
        is_dark = getattr(mw, "is_dark_mode", True)

        # Colors (same as you had)
        if outgoing:
            align = Qt.AlignRight
            bg = "#4f46e5"
            fg = "#ffffff"
            border = "#4f46e5"
            radius = "18px 4px 18px 18px"
            sender = "You"
        else:
            align = Qt.AlignLeft
            bg = "#e5e7eb" if not is_dark else "#1f2937"
            fg = "#111827" if not is_dark else "#e5e7eb"
            border = "#e5e7eb" if not is_dark else "#111827"
            radius = "4px 18px 18px 18px"
            sender = other_name

        if timestamp is None:
            timestamp = QDateTime.currentDateTime()
        ts = timestamp.toString("HH:mm")

        # Inner bubble HTML (no outer div controlling alignment)
        bubble_html = f"""
        <span style="
            display:inline-block;
            max-width:70%;
            background:{bg};
            color:{fg};
            padding:8px 12px;
            border-radius:{radius};
            border: 1px solid {border};
            font-size:10pt;
            line-height:1.4;
            word-wrap:break-word;
            box-shadow:0 1px 2px rgba(0,0,0,0.18);
        ">
            {safe}
            <span style="font-size:8pt; opacity:0.6; margin-left:8px;">
                {ts}
            </span>
        </span>
        """

        cursor = self.chat_box.textCursor()
        cursor.movePosition(QTextCursor.End)

        # New paragraph for this message
        cursor.insertBlock()
        block_fmt = QTextBlockFormat()
        block_fmt.setAlignment(align)
        cursor.setBlockFormat(block_fmt)

        # Insert the bubble in this block
        cursor.insertHtml(bubble_html)

        # Extra blank block as spacing
        cursor.insertBlock()

        self.chat_box.setTextCursor(cursor)
        self.chat_box.ensureCursorVisible()




    # ===== Sending =====
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

    # ===== Load ride state  =====
    def load_for_passenger(self, payload: dict):
        """
        Configure the 'current ride' view when we are the PASSENGER.
        MainWindow passes the full RIDE.MATCHED payload.
        """
        # Clear previous chat
        self.chat_box.clear()
        self.chat_input.clear()

        driver = (payload or {}).get("driver_info") or {}
        name = driver.get("name") or driver.get("username") or "Driver"

        # Build a nice one-line info text
        parts = [f"Ride with {name}"]

        rating_avg = driver.get("rating_avg")
        rating_count = driver.get("rating_count")
        if isinstance(rating_avg, (int, float)) and isinstance(rating_count, int) and rating_count > 0:
            parts.append(f"— {rating_avg:.1f} ★ ")

        vehicle = driver.get("vehicle") or {}
        if isinstance(vehicle, dict):
            make = vehicle.get("make")
            model = vehicle.get("model")
            color = vehicle.get("color")
            plate = vehicle.get("plate")
            veh_bits = [b for b in [make, model] if b]
            if color:
                veh_bits.append(f"({color})")
            veh_str = " ".join(veh_bits)
            if veh_str:
                parts.append(f"— {veh_str}")
            if plate:
                parts.append(f"[{plate}]")

        self.info_label.setText(" ".join(parts))

        # Passenger cannot complete the ride directly
        self.complete_btn.hide()

    def load_for_driver(self, payload: dict):
        """
        Configure the 'current ride' view when we are the DRIVER.
        MainWindow will call this with the driver-side match payload
        (usually has passenger_info instead of driver_info).
        """
        # Clear previous chat
        self.chat_box.clear()
        self.chat_input.clear()

        passenger = (payload or {}).get("passenger_info") or {}
        name = passenger.get("name") or passenger.get("username") or "Passenger"

        parts = [f"Ride with {name}"]
        self.info_label.setText(" ".join(parts))

        
        self.complete_btn.show()
