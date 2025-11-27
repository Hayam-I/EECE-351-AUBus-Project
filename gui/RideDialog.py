import uuid
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QMessageBox, QDialog
from PyQt5.QtCore import Qt, pyqtSignal, QEvent, QSize, QPointF, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPolygonF, QIcon




class StarRatingWidget(QWidget):
    rating_changed = pyqtSignal(int)

    def __init__(self, max_stars=5, parent=None):
        super().__init__(parent)
        self.max_stars = max_stars
        self._rating = 0
        self._hover = 0

        self._size = 28

        # Generate pixmaps
        empty_color = self.property("emptyColor") or QColor("#4b5563")
        hover_color = self.property("hoverColor") or QColor("#facc15")
        filled_color = self.property("filledColor") or QColor("#fbbf24")

        self._pix_empty = self._make_star_pixmap(self._size, empty_color)
        self._pix_hover = self._make_star_pixmap(self._size, hover_color)
        self._pix_filled = self._make_star_pixmap(self._size, filled_color)

        layout = QHBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        self.buttons = []
        for i in range(1, max_stars + 1):
            btn = QPushButton()
            btn.setObjectName("StarBtn")
            btn.setIcon(QIcon(self._pix_empty))
            btn.setIconSize(QSize(self._size, self._size))
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setFixedSize(self._size + 4, self._size + 4)

            btn.installEventFilter(self)
            btn.clicked.connect(lambda _, idx=i: self.set_rating(idx))

            self.buttons.append(btn)
            layout.addWidget(btn)

        self._update_icons()

    # -----------------------------
    # Create crisp render star
    # -----------------------------
    def _make_star_pixmap(self, size: int, color: QColor) -> QPixmap:
        import math
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)

        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)

        cx = cy = size / 2
        outer_r = size * 0.45
        inner_r = size * 0.20

        points = []
        for i in range(10):
            angle = math.pi / 2 + i * math.pi / 5
            r = outer_r if i % 2 == 0 else inner_r
            x = cx + r * math.cos(angle)
            y = cy - r * math.sin(angle)
            points.append(QPointF(x, y))

        painter.drawPolygon(QPolygonF(points))
        painter.end()
        return pm

    # -----------------------------
    # Hover + click logic
    # -----------------------------
    def _update_icons(self):
        for i, btn in enumerate(self.buttons, start=1):
            if i <= (self._hover or self._rating):
                # hover takes priority
                btn.setIcon(QIcon(self._pix_hover if self._hover else self._pix_filled))
            else:
                btn.setIcon(QIcon(self._pix_empty))

    def eventFilter(self, obj, event):
        if obj in self.buttons:
            idx = self.buttons.index(obj) + 1

            if event.type() == QEvent.Enter:
                self._hover = idx
                self._update_icons()

            elif event.type() == QEvent.Leave:
                self._hover = 0
                self._update_icons()

        return super().eventFilter(obj, event)

    def set_rating(self, r: int):
        self._rating = r
        self.rating_changed.emit(r)
        self._update_icons()

    def rating(self) -> int:
        return self._rating


class RateRideDialog(QDialog):
    def __init__(self, request_id: str, session, parent=None):
        super().__init__(parent)
        self.request_id = request_id
        self.session = session

        self.setWindowTitle("Rate your ride")
        self.setModal(True)

        # Title / prompt
        lbl = QLabel("How would you rate your ride?")
        lbl.setAlignment(Qt.AlignCenter)
        

        # --- Star rating widget ---
        self.rating_widget = StarRatingWidget(max_stars=5)

       
        self.rating_label = QLabel("0 / 5")
        self.rating_label.setAlignment(Qt.AlignCenter)

        self.rating_widget.rating_changed.connect(
            lambda val: self.rating_label.setText(f"{val} / 5")
        )

        stars_row = QVBoxLayout()
        stars_row.setSpacing(4)
        stars_row.addWidget(self.rating_widget, alignment=Qt.AlignCenter)
        stars_row.addWidget(self.rating_label, alignment=Qt.AlignCenter)

        # Buttons
        btn_ok = QPushButton("Submit")
        btn_cancel = QPushButton("Skip")

        btn_ok.clicked.connect(self.on_submit)
        btn_cancel.clicked.connect(self.reject)

        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_cancel.setCursor(Qt.PointingHandCursor)

       
        

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)

        # Main layout
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        layout.addWidget(lbl)
        layout.addLayout(stars_row)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def on_submit(self):
        rating = self.rating_widget.rating()

        if rating == 0:
            QMessageBox.warning(
                self,
                "No rating selected",
                "Please choose a star rating, or press Skip if you don't want to rate."
            )
            return

        self.session.send_json({
            "type": "RIDE.RATE_REQ",
            "id": str(uuid.uuid4()),
            "payload": {
                "request_id": self.request_id,
                "rating": rating,
            },
        })
        self.accept()
