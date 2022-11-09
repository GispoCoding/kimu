from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor
from qgis.gui import QgisInterface, QgsMapCanvas, QgsMapToolIdentifyFeature


class SelectTool(QgsMapToolIdentifyFeature):
    """Base class for selecting features from canvas."""

    def __init__(self, iface: QgisInterface) -> None:
        self.iface = iface
        self.layer = self.iface.activeLayer()
        self.canvas: QgsMapCanvas = iface.mapCanvas()
        super().__init__(self.canvas, self.layer)
        self.cursor = QCursor(Qt.CrossCursor)
        # self.iface.currentLayerChanged.connect(self.active_changed)

    def activate(self) -> None:
        """Called when tool is activated."""
        self.canvas.setCursor(self.cursor)

    def deactivate(self) -> None:
        """Called when tool is deactivated."""
        self.action().setChecked(False)
