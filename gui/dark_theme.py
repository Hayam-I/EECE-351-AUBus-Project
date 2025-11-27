DARK_STYLESHEET = """
/* ===== Global ===== */
QMainWindow#MainWindow, QWidget {
    background-color: #020617;  /* dark navy */
    color: #e5e7eb;
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 10pt;
}

/* Labels */
QLabel {
    color: #e5e7eb;
    background-color: transparent;
    border: none;
}

QLabel#page_title {
    font-size: 18pt;
    font-weight: 600;
    color: #e5e7eb;
}

/* Error / success tint by inline style */
QLabel[style*="color: red"] {
    color: #f97373;
}
QLabel[style*="#0a7a0a"], QLabel[style*="color: #0a7a0a"] {
    color: #4ade80;
}

/* ===== Sidebar ===== */
QWidget#SideBar {
    background-color: #020617;
    border-right: 1px solid #1f2937;
}

QWidget#SideBar QPushButton {
    background-color: transparent;
    border: none;
    color: #9ca3af;
    padding: 8px 14px;
    text-align: left;
    border-radius: 10px;
}

QWidget#SideBar QPushButton:hover {
    background-color: rgba(99,102,241,0.18);
    color: #e5e7eb;
}

QWidget#SideBar QPushButton:checked {
    background-color: #4f46e5;
    color: #f9fafb;
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
    color: #6b7280;             /* default grey on dark */
}



/* When you hover ANY star (preview up to that star) */
QPushButton#StarButton[hover="true"] {
    color: #facc15;             /* bright yellow */
}

/* Locked-in rating (clicked) */
QPushButton#StarButton[active="true"] {
    color: #fbbf24;             /* slightly deeper yellow */
}


/* ===== Auth / cards ===== */
QWidget#login_card,
QWidget#register_card {
    background-color: qradialgradient(
        cx:0.5, cy:0.0, radius:1.4,
        fx:0.5, fy:0.0,
        stop:0  rgba(129,140,248,0.22),
        stop:0.4 rgba(24,31,81,0.96),
        stop:1  #020617
    );
    border-radius: 20px;
    border: 1px solid rgba(148,163,184,0.45);
}

QStackedWidget {
    background-color: #020617;
    border-radius: 18px;
}

/* ===== Inputs ===== */
QLineEdit, QTimeEdit, QDateTimeEdit, QComboBox {
    background-color: rgba(255,255,255,0.04);
    border: 1px solid rgba(148,163,184,0.25);
    border-radius: 8px;
    padding: 6px 10px;
    color: #e5e7eb;
    selection-background-color: #4f46e5;
    selection-color: #f9fafb;
}

QLineEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus, QComboBox:focus {
    border: 1px solid #6366f1;
    background-color: rgba(255,255,255,0.07);
}

QComboBox QAbstractItemView {
    background-color: #020617;
    border: 1px solid #1f2937;
    selection-background-color: #4f46e5;
    selection-color: #f9fafb;
}

/* Profile fields – dark (by id) */
QLineEdit#profileField,
QLineEdit#profileField:disabled,
QLineEdit#profileField:read-only {
    background-color: rgba(255,255,255,0.12);
    border: 1px solid rgba(148,163,184,0.75);
    color: #f9fafb;
    border-radius: 8px;
    padding: 6px 10px;
}

QLineEdit#profileField:focus {
    border: 1px solid #6366f1;
    background-color: rgba(255,255,255,0.18);
}

/* ===== Buttons ===== */
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

QPushButton:disabled {
    background-color: #020617;
    color: #4b5563;
    border-color: #111827;
}

/* ===== Tables ===== */
QTableWidget {
    background-color: #020617;
    border: 1px solid #111827;
    border-radius: 14px;
    gridline-color: #111827;
    selection-background-color: rgba(129,140,248,0.25);
    selection-color: #f9fafb;
}

QHeaderView::section {
    background-color: #020617;
    color: #9ca3af;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid #111827;
}

QTableCornerButton::section {
    background-color: #020617;
    border: none;
}

/* ===== Tabs ===== */
QTabWidget::pane {
    border: 1px solid #111827;
    border-radius: 14px;
    background-color: #020617;
}

QTabBar::tab {
    background-color: transparent;
    color: #9ca3af;
    padding: 6px 16px;
    border-radius: 10px;
    margin: 4px;
}

QTabBar::tab:selected {
    background-color: #4f46e5;
    color: #f9fafb;
}

QTabBar::tab:hover {
    background-color: rgba(79,70,229,0.25);
    color: #e5e7eb;
}

/* ===== Scrollbars ===== */
QScrollBar:vertical, QScrollBar:horizontal {
    background: #020617;
    border-radius: 4px;
    width: 10px;
    height: 10px;
    margin: 2px;
}

QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #111827;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #4b5563;
}

QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
    background: transparent;
}



/* ===== Checkboxes (modern, unified) ===== */
QCheckBox {
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #4b5563;
    background-color: #020617;
}
QCheckBox::indicator:hover {
    border-color: #6366f1;
}
QCheckBox::indicator:checked {
    background-color: #4f46e5;
    border-color: #4f46e5;
}
"""
