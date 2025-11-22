# client/map_selector.py

import os
from math import isfinite

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QGraphicsView,
    QGraphicsScene,
    QPushButton,
    QHBoxLayout,
)
from PyQt5.QtGui import QPixmap, QPainter, QPen, QBrush, QColor


class MapView(QGraphicsView):
    """
    QGraphicsView wrapper that supports:
    - Scroll wheel zoom
    - Click to select a point (emits scene x,y)
    - Drag to pan
    """
    clicked = pyqtSignal(float, float)  # scene x, scene y

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._current_scale = 1.0
        self._auto_fit = True  # while True, resize will refit image

        self.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.ScrollHandDrag)  # left-drag to pan
        self.setMouseTracking(True)

    def wheelEvent(self, event):
        # Zoom in/out with mouse wheel
        angle = event.angleDelta().y()
        if angle == 0:
            return

        factor = 1.25 if angle > 0 else 0.8
        self._current_scale *= factor
        self._auto_fit = False  # user is manually zooming now
        self.scale(factor, factor)

    def resizeEvent(self, event):
        # When window resizes, auto-fit image as long as user hasn't zoomed
        super().resizeEvent(event)
        if self._auto_fit and self.scene():
            rect = self.scene().itemsBoundingRect()
            if not rect.isNull():
                self.fitInView(rect, Qt.KeepAspectRatio)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            self.clicked.emit(scene_pos.x(), scene_pos.y())
        super().mousePressEvent(event)


class MapSelector(QWidget):
    """
    Popup-like widget:
    - Shows Beirut map in a zoomable QGraphicsView
    - User can zoom with scroll, pan, and click to drop a pin
    - Confirm button converts pin to (lat, lon) and emits location_selected
    """
    location_selected = pyqtSignal(float, float)  # lat, lon

    def __init__(self, parent=None):
        super().__init__(parent)

        # ---- Instruction label ----
        self.info_label = QLabel(
            "Try to approximately locate your pick up location on the map.\n"
            "Scroll to zoom, drag to move, and click to drop a pin."
        )
        self.info_label.setAlignment(Qt.AlignCenter)

        # Resolve image path relative to THIS file (client/)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        img_path = os.path.join(base_dir, "assets", "beirut_map.png")

        pixmap = QPixmap(img_path)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.info_label)

        self.pixmap = None
        self.view = None
        self.marker_item = None
        self._selected_x = None
        self._selected_y = None

        if pixmap.isNull():
            # If image not found, show a message instead of crashing / freezing
            error_label = QLabel(f"Could not load map image:\n{img_path}")
            error_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(error_label)
        else:
            self.pixmap = pixmap

            scene = QGraphicsScene(self)
            self.pixmap_item = scene.addPixmap(self.pixmap)

            self.view = MapView(scene, self)
            layout.addWidget(self.view, 1)

            # Initial fit; resizeEvent will refit until user zooms
            self.view.setSceneRect(self.pixmap_item.boundingRect())
            self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

            # MapView will emit scene coordinates on click
            self.view.clicked.connect(self.on_scene_clicked)

        # ---- Buttons row ----
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_confirm = QPushButton("Confirm location")
        self.btn_cancel = QPushButton("Cancel")
        self.btn_confirm.setEnabled(False)  # no pin yet

        btn_row.addWidget(self.btn_confirm)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.btn_confirm.clicked.connect(self.on_confirm)
        self.btn_cancel.clicked.connect(self.close)

        # Beirut approx bounding box
        self.min_lat = 33.85
        self.max_lat = 33.93
        self.min_lon = 35.45
        self.max_lon = 35.57

        # Make it feel like a popup
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowStaysOnTopHint
            | Qt.Dialog
        )

    # ------------------------------------------------------------------
    # Click handling: drop / move marker
    # ------------------------------------------------------------------
    def on_scene_clicked(self, sx: float, sy: float):
        if not self.pixmap:
            return

        w = self.pixmap.width()
        h = self.pixmap.height()
        if w <= 0 or h <= 0:
            return

        # Clamp inside image bounds
        x = max(0.0, min(sx, float(w)))
        y = max(0.0, min(sy, float(h)))

        self._selected_x = x
        self._selected_y = y

        # Add or move marker (small red circle)
        if self.marker_item is None:
            radius = 6
            pen = QPen(QColor("#ef4444"))     # red outline
            brush = QBrush(QColor("#f97373")) # softer fill
            self.marker_item = self.view.scene().addEllipse(
                x - radius,
                y - radius,
                radius * 2,
                radius * 2,
                pen,
                brush,
            )
        else:
            rect = self.marker_item.rect()
            radius = rect.width() / 2.0
            self.marker_item.setRect(
                x - radius,
                y - radius,
                radius * 2,
                radius * 2,
            )

        # Now user can confirm
        self.btn_confirm.setEnabled(True)

    # ------------------------------------------------------------------
    # Confirm: compute lat/lon and emit
    # ------------------------------------------------------------------
    def on_confirm(self):
        if self._selected_x is None or self._selected_y is None or not self.pixmap:
            return

        w = self.pixmap.width()
        h = self.pixmap.height()
        if w <= 0 or h <= 0:
            return

        x = self._selected_x
        y = self._selected_y

        # Convert pixel → longitude (left to right)
        lon = self.min_lon + (x / w) * (self.max_lon - self.min_lon)

        # Convert pixel → latitude (top to bottom; y increases downward)
        lat = self.max_lat - (y / h) * (self.max_lat - self.min_lat)

        if isfinite(lat) and isfinite(lon):
            self.location_selected.emit(lat, lon)
            self.close()
