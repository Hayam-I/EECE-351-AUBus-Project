# client/map_selector.py

import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QPainter, QPen, QBrush
from PyQt5.QtWidgets import (
    QDialog,
    QGraphicsView,
    QGraphicsScene,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QMessageBox,
)


class MapGraphicsView(QGraphicsView):
    """
    Custom graphics view that supports:
      - Smooth rendering
      - Scroll-hand panning
      - Wheel zoom with min zoom limit (relative to fitted size)
      - Emitting click coordinates in scene space
    """
    clicked_on_map = pyqtSignal(float, float)  # scene x, scene y

    def __init__(self, parent=None):
        super().__init__(parent)

        # Render quality
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)

        # Panning
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)

        # Hide scrollbars
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Zoom control (relative to base transform)
        self._base_m11 = 1.0   # scale after initial fit
        self._max_factor = 8.0 # you can zoom in up to 8×
        self._user_zoomed = False

    def set_base_transform_from_current(self):
        """
        Called after we do fitInView once, when the widget
        already has its final (maximized) size.
        """
        m11 = self.transform().m11()
        if m11 <= 0:
            m11 = 1.0
        self._base_m11 = m11
        self._user_zoomed = False

    def _zoom(self, factor: float):
        """
        Zoom but don't allow zooming out smaller than the fitted size.
        """
        cur = self.transform().m11()
        if cur <= 0:
            cur = self._base_m11

        # current factor relative to fitted size
        rel = cur / self._base_m11
        new_rel = rel * factor

        # clamp between 1× and max_factor
        if new_rel < 1.0:
            new_rel = 1.0
        if new_rel > self._max_factor:
            new_rel = self._max_factor

        # convert back to scale factor for this step
        if rel <= 0:
            rel = 1.0
        step_factor = new_rel / rel

        self.scale(step_factor, step_factor)
        self._user_zoomed = True

    def wheelEvent(self, event):
        # Mouse wheel zoom
        if event.angleDelta().y() > 0:
            self._zoom(1.25)
        else:
            self._zoom(0.8)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            self.clicked_on_map.emit(scene_pos.x(), scene_pos.y())
        super().mousePressEvent(event)


class MapSelector(QDialog):
    """
    Fullscreen map selector dialog.

    - Shows Beirut map image.
    - User can pan, zoom with + / − (and wheel).
    - Cannot zoom out smaller than the initial fitted size.
    - Click to place a pin.
    - Confirm to emit location_selected(lat, lon).
    - Has a .label attribute for instructions (used from main.py).
    """
    location_selected = pyqtSignal(float, float)  # lat, lon

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select location on map")
        self.setModal(True)

        # We'll fit the image AFTER the dialog is shown (see showEvent)
        self._did_initial_fit = False

        # ----- Top instruction label -----
        self.label = QLabel("Try to approximately locate your pickup location.")
        self.label.setWordWrap(True)

        # ----- Graphics view / scene -----
        self.view = MapGraphicsView(self)
        self.scene = QGraphicsScene(self)
        self.view.setScene(self.scene)

        # Load map image
        map_path = os.path.join(os.path.dirname(__file__), "assets", "beirut_map.png")
        pix = QPixmap(map_path)

        if pix.isNull():
            # Fallback: show an error message if the file isn't found
            self.label.setText(
                f"Map image not found at:\n{map_path}\n\n"
                "Please check the file path / name."
            )
            self.pixmap_item = None
        else:
            self.pixmap_item = self.scene.addPixmap(pix)
            self.scene.setSceneRect(self.pixmap_item.boundingRect())

        # ----- Buttons (zoom + confirm/cancel) -----
        btn_zoom_out = QPushButton("−")
        btn_zoom_in = QPushButton("+")
        btn_cancel = QPushButton("Cancel")
        btn_confirm = QPushButton("Confirm location")

        btn_zoom_in.clicked.connect(lambda: self.view._zoom(1.25))
        btn_zoom_out.clicked.connect(lambda: self.view._zoom(0.8))
        btn_cancel.clicked.connect(self.reject)
        btn_confirm.clicked.connect(self._on_confirm)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_zoom_out)
        btn_row.addWidget(btn_zoom_in)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_confirm)

        # ----- Main layout -----
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.view, 1)
        layout.addLayout(btn_row)

        # State for selected point
        self.pin_item = None
        self.selected_lat = None
        self.selected_lon = None

        # Connect click signal
        self.view.clicked_on_map.connect(self.on_map_clicked)

    # ------------------------------------------------------------------
    # Fit-to-window happens here, when we actually know the window size
    # ------------------------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)

        if self.pixmap_item and not self._did_initial_fit:
            # Now the dialog is shown (and if you called showMaximized(),
            # it's already maximized), so we can fit to the real size.
            self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
            self.view.set_base_transform_from_current()
            self._did_initial_fit = True

    # ------------------------------------------------------------------
    # Map click handling + fake geo mapping
    # ------------------------------------------------------------------
    def on_map_clicked(self, x: float, y: float):
        if not self.pixmap_item:
            return

        # Remove old pin if any
        if self.pin_item:
            self.scene.removeItem(self.pin_item)

        r = 6
        pen = QPen(Qt.red)
        brush = QBrush(Qt.red)
        self.pin_item = self.scene.addEllipse(x - r, y - r, 2 * r, 2 * r, pen, brush)

        rect = self.pixmap_item.boundingRect()
        nx = (x - rect.left()) / rect.width()
        ny = (y - rect.top()) / rect.height()

        nx = max(0.0, min(1.0, nx))
        ny = max(0.0, min(1.0, ny))

        # Rough bounding box around Beirut (tweak if you want better alignment)
        lat_top = 33.95
        lat_bottom = 33.85
        lon_left = 35.45
        lon_right = 35.55

        # y grows downward → invert for latitude
        self.selected_lat = lat_top + (lat_bottom - lat_top) * ny
        self.selected_lon = lon_left + (lon_right - lon_left) * nx

        self.label.setText(
            f"Location selected ✓  (approx lat={self.selected_lat:.5f}, lon={self.selected_lon:.5f})"
        )

    def _on_confirm(self):
        if self.selected_lat is None or self.selected_lon is None:
            QMessageBox.warning(self, "No location selected", "Please click on the map first.")
            return
        self.location_selected.emit(self.selected_lat, self.selected_lon)
        self.accept()
