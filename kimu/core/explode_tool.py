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

# from .split_tool import SplitTool

LOGGER = setup_logger(plugin_name())


class ExplodeTool:
    # def __init__(self, split_tool: SplitTool) -> None:
    # self.split_tool = split_tool

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
        explode_layer.setName(tr("Vertices of the exploded polygon"))
        explode_layer.renderer().symbol().setWidth(0.7)
        explode_layer.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))
        QgsProject.instance().addMapLayer(explode_layer)

        point_result = processing.run("native:extractvertices", line_params)
        point_layer = point_result["OUTPUT"]

        point_params = {"INPUT": point_layer, "OUTPUT": "memory:"}
        point_result2 = processing.run("native:deleteduplicategeometries", point_params)

        point_layer2: QgsVectorLayer = point_result2["OUTPUT"]
        point_layer2.setName(tr("Vertex points of the exploded polygon"))
        point_layer2.renderer().symbol().setSize(2)
        point_layer2.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))
        QgsProject.instance().addMapLayer(point_layer2)

        # If wanted, can be launched automatically by removing
        # the comments in this and plugin.py file
        # self.split_tool.manual_activate()
