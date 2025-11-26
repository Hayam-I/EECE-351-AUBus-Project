LIGHT_STYLESHEET = """
/* ===== Global ===== */
QMainWindow#MainWindow, QWidget {
    background-color: #FFF5E6;  /* creamy */
    color: #3A2E25;
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 10pt;
}

/* Labels */
QLabel {
    color: #3A2E25;
    background-color: transparent;
    border: none;
}

QLabel#page_title {
    font-size: 18pt;
    font-weight: 600;
    color: #3A2E25;
}

/* Error / success tint */
QLabel[style*="color: red"] {
    color: #b91c1c;
}
QLabel[style*="#0a7a0a"], QLabel[style*="color: #0a7a0a"] {
    color: #166534;
}

/* ===== Sidebar ===== */
QWidget#SideBar {
    background-color: #F4E3CC;
    border-right: 1px solid #D2BFA5;
}

QWidget#SideBar QPushButton {
    background-color: transparent;
    border: none;
    color: #7B5A3A;
    padding: 8px 14px;
    text-align: left;
    border-radius: 10px;
}

QWidget#SideBar QPushButton:hover {
    background-color: rgba(173,133,88,0.15);
    color: #3A2E25;
}

QWidget#SideBar QPushButton:checked {
    background-color: #C49A6C;
    color: #FFF9F0;
}

/* ===== Star rating ===== */
QPushButton#StarButton {
    background-color: transparent;
    border: none;
    padding: 0;
    margin: 0;
    min-width: 0;
    max-width: 28px;
    min-height: 0;
    max-height: 28px;
    text-align: center;
    font-size: 20px;
    color: #9ca3af;             /* neutral grey on light */
}


QPushButton#StarButton[hover="true"] {
    color: #eab308;             /* hover yellow */
}

QPushButton#StarButton[active="true"] {
    color: #f59e0b;             /* selected yellow */
}


/* ===== Auth / cards ===== */
QWidget#login_card,
QWidget#register_card {
    background-color: #FFF5E6;
    border-radius: 20px;
    border: 1px solid #D2BFA5;
}

QStackedWidget {
    background-color: #FFF5E6;
    border-radius: 18px;
}

/* ===== Inputs ===== */
QLineEdit, QTimeEdit, QDateTimeEdit, QComboBox {
    background-color: #FFF9F0;
    border: 1px solid #D3C3AE;
    border-radius: 8px;
    padding: 6px 10px;
    color: #3A2E25;
    selection-background-color: #C49A6C;
    selection-color: #FFF9F0;
}

QLineEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus, QComboBox:focus {
    border: 1px solid #C49A6C;
    background-color: #FFF2DE;
}

QComboBox QAbstractItemView {
    background-color: #FFF5E6;
    border: 1px solid #D2BFA5;
    selection-background-color: #C49A6C;
    selection-color: #FFF9F0;
}

/* Profile fields – light (by id) */
QLineEdit#profileField,
QLineEdit#profileField:disabled,
QLineEdit#profileField:read-only {
    background-color: #FFF3E3;
    border: 1px solid #D3C3AE;
    color: #3A2E25;
    border-radius: 8px;
    padding: 6px 10px;
}

QLineEdit#profileField:focus {
    border: 1px solid #C49A6C;
    background-color: #FFEBD2;
}

/* ===== Buttons ===== */
QPushButton {
    background-color: #E8D4BC;
    color: #3A2E25;
    border-radius: 10px;
    padding: 6px 14px;
    border: 1px solid #D2BFA5;
}

QPushButton:hover {
    background-color: #DEC6A7;
    border-color: #C49A6C;
}

QPushButton:pressed {
    background-color: #C49A6C;
    border-color: #C49A6C;
    color: #FFF9F0;
}

QPushButton:disabled {
    background-color: #F2E3CF;
    color: #B09A82;
    border-color: #E2D2BF;
}

/* ===== Tables ===== */
QTableWidget {
    background-color: #FFF9F0;
    border: 1px solid #D2BFA5;
    border-radius: 14px;
    gridline-color: #E2D2BF;
    selection-background-color: rgba(196,154,108,0.25);
    selection-color: #3A2E25;
}

QHeaderView::section {
    background-color: #F4E3CC;
    color: #7B5A3A;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid #D2BFA5;
}

QTableCornerButton::section {
    background-color: #F4E3CC;
    border: none;
}

/* ===== Tabs ===== */
QTabWidget::pane {
    border: 1px solid #D2BFA5;
    border-radius: 14px;
    background-color: #FFF9F0;
}

QTabBar::tab {
    background-color: transparent;
    color: #7B5A3A;
    padding: 6px 16px;
    border-radius: 10px;
    margin: 4px;
}

QTabBar::tab:selected {
    background-color: #C49A6C;
    color: #FFF9F0;
}

QTabBar::tab:hover {
    background-color: rgba(196,154,108,0.25);
    color: #3A2E25;
}

/* ===== Scrollbars ===== */
QScrollBar:vertical, QScrollBar:horizontal {
    background: #F4E3CC;
    border-radius: 4px;
    width: 10px;
    height: 10px;
    margin: 2px;
}

QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #D2BFA5;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #C49A6C;
}

QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
    background: transparent;
}

/* ===== Chat box ===== */
QTextEdit {
    background-color: transparent;
    color: inherit;
    border: none;
}

/* Chat input */
QLineEdit[objectName="chatInput"] {
    background-color: #FFF3E3;
    border-radius: 999px;
    padding: 8px 12px;
    border: 1px solid #D3C3AE;
    color: #3A2E25;
}

/* ===== Checkboxes (same style family as dark) ===== */
QCheckBox {
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #B89C7A;
    background-color: #FFF9F0;
}
QCheckBox::indicator:hover {
    border-color: #C49A6C;
}
QCheckBox::indicator:checked {
    background-color: #C49A6C;
    border-color: #C49A6C;
}
"""

