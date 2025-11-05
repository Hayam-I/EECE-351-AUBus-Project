import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QStackedWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTabWidget
)
from PyQt5.QtCore import Qt


def title_page(text):
    """Utility function to create a centered title page."""
    w = QWidget()
    v = QVBoxLayout(w)
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setObjectName("page_title")
    v.addStretch(1)
    v.addWidget(lbl)
    v.addStretch(1)
    return w


class RidePage(QWidget):
    """Ride page with sub-navigation: Overview | Chat | Ratings"""
    def __init__(self):
        super().__init__()
        h = QHBoxLayout(self)

        # --- Left sub-navigation ---
        nav = QVBoxLayout()
        self.btn_overview = QPushButton("Overview")
        self.btn_chat = QPushButton("Chat")
        self.btn_rate = QPushButton("Ratings")

        for b in (self.btn_overview, self.btn_chat, self.btn_rate):
            b.setCheckable(True)
            b.setAutoExclusive(True)
            nav.addWidget(b)
        nav.addStretch(1)

        # --- Right sub-stack ---
        self.sub = QStackedWidget()
        self.sub.addWidget(title_page("Ride - Overview"))
        self.sub.addWidget(title_page("Ride - Chat"))
        self.sub.addWidget(title_page("Ride - Ratings"))

        # --- Connect buttons ---
        self.btn_overview.clicked.connect(lambda: self.sub.setCurrentIndex(0))
        self.btn_chat.clicked.connect(lambda: self.sub.setCurrentIndex(1))
        self.btn_rate.clicked.connect(lambda: self.sub.setCurrentIndex(2))

        # Default view
        self.btn_overview.setChecked(True)
        self.sub.setCurrentIndex(0)

        left = QWidget()
        left.setLayout(nav)
        left.setMinimumWidth(160)

        h.addWidget(left)
        h.addWidget(self.sub, 1)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AUBus")
        self.resize(1000, 650)

        # Root stack: [Auth Page, App Page]
        self.root = QStackedWidget()
        self.setCentralWidget(self.root)

        # ---- Auth Page ----
        auth_page = QWidget()
        v_auth = QVBoxLayout(auth_page)

        tabs = QTabWidget()
        tabs.addTab(title_page("Login Here"), "Login")
        tabs.addTab(title_page("Register Here"), "Register")

        continue_btn = QPushButton("Continue")
        continue_btn.clicked.connect(self.goto_app)

        v_auth.addWidget(tabs, 1)
        v_auth.addWidget(continue_btn)
        self.root.addWidget(auth_page)

        # ---- App Page ----
        app_page = QWidget() 
        self.root.addWidget(app_page)
        h = QHBoxLayout(app_page)

        # Left sidebar
        left = QWidget()
        left_l = QVBoxLayout(left)

        self.btn_profile = QPushButton("Profile")
        self.btn_sched = QPushButton("Schedule")
        self.btn_ride = QPushButton("Ride")

        for b in (self.btn_profile, self.btn_sched, self.btn_ride):
            b.setCheckable(True)
            b.setAutoExclusive(True)
            left_l.addWidget(b)
        left_l.addStretch(1)

        # Right stack (Profile / Schedule / Ride)
        self.stack = QStackedWidget()
        self.stack.addWidget(title_page("Your Profile"))
        self.stack.addWidget(title_page("Your Schedule"))
        self.stack.addWidget(RidePage())

        # Connect sidebar buttons
        self.btn_profile.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.btn_sched.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.btn_ride.clicked.connect(lambda: self.stack.setCurrentIndex(2))

        # Default page
        self.btn_profile.setChecked(True)
        self.stack.setCurrentIndex(0)

        h.addWidget(left)
        h.addWidget(self.stack, 1)

    def goto_app(self):
        """Switch to the main app after clicking 'Continue'."""
        self.root.setCurrentIndex(1)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
