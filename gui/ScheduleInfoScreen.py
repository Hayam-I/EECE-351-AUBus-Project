from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel)
from PyQt5.QtCore import Qt


class ScheduleInfoScreen(QWidget):
    """Shown to passengers: explains that schedule is driver-only."""
    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        lbl = QLabel(
            "Schedule is available only for drivers.\n\n"
            "To add a weekly schedule:\n"
            "1. Go to the Profile tab.\n"
            "2. Enable 'Driver Mode' and fill in your car details.\n"
            "3. Save your profile.\n\n"
            "Once Driver Mode is on, you'll see the schedule editor here."
        )
        lbl.setWordWrap(True)
        v.addStretch(1)
        v.addWidget(lbl, 0, Qt.AlignCenter)
        v.addStretch(1)

