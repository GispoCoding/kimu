from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor
from qgis import processing
from qgis.core import (
    QgsFeatureRequest,
    QgsProcessingFeatureSourceDefinition,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
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
        if (
            isinstance(layer, QgsVectorLayer)
            and layer.isSpatial()
            and layer.geometryType() == QgsWkbTypes.PolygonGeometry
        ):
            self.layer = layer
            self.setLayer(self.layer)

    def canvasPressEvent(self, event: QgsMapMouseEvent) -> None:  # noqa: N802
        LOGGER.info("canvas pressed")
        if self.iface.activeLayer() != self.layer:
            LOGGER.info("Please select a polygon layer")
            return
        found_features = self.identify(
            event.x(), event.y(), [self.layer], QgsMapToolIdentify.ActiveLayer
        )
        self.layer.selectByIds(
            [f.mFeature.id() for f in found_features], QgsVectorLayer.SetSelection
        )

        line_params = {
            "INPUT": QgsProcessingFeatureSourceDefinition(
                self.layer.id(),
                selectedFeaturesOnly=True,
                featureLimit=-1,
                geometryCheck=QgsFeatureRequest.GeometryAbortOnInvalid,
            ),
            "OUTPUT": "memory:",
        }
        line_result = processing.run("native:polygonstolines", line_params)
        line_layer = line_result["OUTPUT"]

        explode_params = {"INPUT": line_layer, "OUTPUT": "memory:"}
        explode_result = processing.run("native:explodelines", explode_params)
        explode_layer = explode_result["OUTPUT"]
        QgsProject.instance().addMapLayer(explode_layer)

    def deactivate(self) -> None:
        self.action().setChecked(False)
