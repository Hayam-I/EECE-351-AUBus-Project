import html
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget, QFormLayout,
    QLineEdit, QMessageBox, QCheckBox, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTimeEdit, QDateTimeEdit, QTextEdit, QDialog, QSpinBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QDateTime, QTimer, QObject
from PyQt5.QtGui import QTextCursor



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
          - outgoing: right, green bubble
          - incoming: left, light/grey bubble
          Colors adapt to dark vs light theme via MainWindow.is_dark_mode.
        """
        if not text:
            return

        safe = html.escape(text).replace("\n", "<br/>")

        mw = self.window()
        other_name = getattr(mw, "other_party_name", "Them") if mw else "Them"
        is_dark = getattr(mw, "is_dark_mode", True)

        if is_dark:
            # Dark theme (navy background)
            out_bg = "#4f46e5"   
            out_fg = "#ffffff"
            out_border = "#4f46e5"

            in_bg = "#111827"   
            in_fg = "#e5e7eb"
            in_border = "#111827"
        else:
            out_bg = "#E6E6E6"  
            out_fg = "#111827"
            out_border = "#E6E6E6"

            in_bg = "#F6FFBF"
            in_fg = "#111827"
            in_border = "#F6FFBF"

        if outgoing:
            side = "right"
            bg = out_bg
            fg = out_fg
            border = out_border
            # tail-ish radius: sharp on top-right
            radius = "18px 4px 18px 18px"
            sender = "You"
        else:
            side = "left"
            bg = in_bg
            fg = in_fg
            border = in_border
            # tail-ish radius: sharp on top-left
            radius = "4px 18px 18px 18px"
            sender = other_name

        if timestamp is None:
            timestamp = QDateTime.currentDateTime()
        ts = timestamp.toString("HH:mm")

       
        html_blob = f"""
        <div style="width:100%; text-align:{side}; margin:4px 0;">
            <div style="
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
                <div style="font-size:8pt; text-align:right; opacity:0.6; margin-top:4px;">
                    {ts}
                </div>
            </div>
        </div>
        """

        cursor = self.chat_box.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(html_blob)
        
        cursor.insertHtml("<br/>")
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
