from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor
from qgis.core import QgsVectorLayer
from qgis.gui import (
    QgisInterface,
    QgsMapCanvas,
    QgsMapMouseEvent,
    QgsMapToolIdentify,
    QgsMapToolIdentifyFeature,
)

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.resources import plugin_name

LOGGER = setup_logger(plugin_name())


class SelectTool(QgsMapToolIdentifyFeature):
    def __init__(self, iface: QgisInterface) -> None:
        self.iface = iface
        self.layer = self.iface.activeLayer()
        self.canvas: QgsMapCanvas = iface.mapCanvas()
        super().__init__(self.canvas, self.layer)
        self.cursor = QCursor(Qt.CrossCursor)
        self.iface.currentLayerChanged.connect(self.active_changed)

    def activate(self) -> None:
        self.canvas.setCursor(self.cursor)
        LOGGER.info("select tool activated")

    def active_changed(self, layer: QgsVectorLayer) -> None:
        """Triggered when active layer changes."""
        try:
            self.layer.removeSelection()

        except AttributeError:
            pass
        except RuntimeError:
            pass

        if isinstance(layer, QgsVectorLayer) and layer.isSpatial():
            self.layer = layer
            self.setLayer(self.layer)

    def canvasPressEvent(self, event: QgsMapMouseEvent) -> None:  # noqa: N802
        LOGGER.info("canvas pressed")
        found_features = self.identify(
            event.x(), event.y(), [self.layer], QgsMapToolIdentify.TopDownAll
        )
        self.layer.selectByIds(
            [f.mFeature.id() for f in found_features], QgsVectorLayer.AddToSelection
        )

    def deactivate(self) -> None:
        self.layer.removeSelection()
        self.action().setChecked(False)
