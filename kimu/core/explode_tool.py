from qgis import processing
from qgis._core import (
    QgsFeatureRequest,
    QgsProcessingFeatureSourceDefinition,
    QgsProject,
)
from qgis.core import QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgisInterface, QgsMapMouseEvent, QgsMapToolIdentify

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name
from .select_tool import SelectTool
from .split_tool import SplitTool

LOGGER = setup_logger(plugin_name())


class ExplodeTool(SelectTool):
    def __init__(self, iface: QgisInterface, split_tool: SplitTool) -> None:
        super().__init__(iface)
        self.split_tool = split_tool

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
        """Selects clicked polygon feature(s) and explodes them to lines."""
        if self.iface.activeLayer() != self.layer:
            LOGGER.warning(tr("Please select a polygon layer"), extra={"details": ""})
            return
        found_features = self.identify(
            event.x(), event.y(), [self.layer], QgsMapToolIdentify.ActiveLayer
        )
        if not len(found_features):
            return

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

        explode_layer: QgsVectorLayer = explode_result["OUTPUT"]
        explode_layer.setName(tr("Exploded polygon"))
        explode_layer.renderer().symbol().setWidth(2)
        QgsProject.instance().addMapLayer(explode_layer)

        self.layer.removeSelection()
        self.split_tool.manual_activate()
