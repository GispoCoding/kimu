from qgis import processing
from qgis.core import (
    QgsFeatureRequest,
    QgsProcessingFeatureSourceDefinition,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtGui import QColor
from qgis.utils import iface

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name
from .split_tool import SplitTool

LOGGER = setup_logger(plugin_name())


class ExplodeTool:
    def __init__(self, split_tool: SplitTool) -> None:
        self.split_tool = split_tool

    @staticmethod
    def __check_valid_layer(layer: QgsVectorLayer) -> bool:
        """Checks if layer is valid"""
        if (
            isinstance(layer, QgsVectorLayer)
            and layer.isSpatial()
            and layer.geometryType() == QgsWkbTypes.PolygonGeometry
        ):
            return True
        return False

    def run(self) -> None:
        """Explodes selected polygon feature to lines."""
        layer = iface.activeLayer()
        if not self.__check_valid_layer(layer):
            LOGGER.warning(tr("Please select a polygon layer"), extra={"details": ""})
            return

        if len(layer.selectedFeatures()) != 1:
            LOGGER.warning(tr("Please select a single feature"), extra={"details": ""})
            return

        line_params = {
            "INPUT": QgsProcessingFeatureSourceDefinition(
                layer.id(),
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
        explode_layer.setName(tr("Exploded polygon to lines"))
        explode_layer.renderer().symbol().setWidth(0.7)
        explode_layer.renderer().symbol().setColor(QColor.fromRgb(135, 206, 250))
        QgsProject.instance().addMapLayer(explode_layer)

        # If wanted, can be launched automatically
        # self.split_tool.manual_activate()
