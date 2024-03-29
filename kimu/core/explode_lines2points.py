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

from ..qgis_plugin_tools.tools.i18n import tr
from .tool_functions import log_warning


class ExplodeLines2points:
    @staticmethod
    def __check_valid_layer(layer: QgsVectorLayer) -> bool:
        """Checks if layer is valid"""
        if (
            isinstance(layer, QgsVectorLayer)
            and layer.isSpatial()
            and layer.geometryType() == QgsWkbTypes.LineGeometry
        ):
            return True
        return False

    def run(self) -> None:
        """Explodes selected line features to points."""
        layer = iface.activeLayer()
        if not self.__check_valid_layer(layer):
            log_warning("Please select a line layer")
            return

        point_params = {
            "INPUT": QgsProcessingFeatureSourceDefinition(
                layer.id(),
                selectedFeaturesOnly=True,
                featureLimit=-1,
                geometryCheck=QgsFeatureRequest.GeometryAbortOnInvalid,
            ),
            "OUTPUT": "memory:",
        }

        point_result = processing.run("native:explodelines", point_params)
        point_layer = point_result["OUTPUT"]

        explode_params1 = {"INPUT": point_layer, "OUTPUT": "memory:"}
        explode_result1 = processing.run("native:extractvertices", explode_params1)
        explode_layer1 = explode_result1["OUTPUT"]

        explode_params2 = {"INPUT": explode_layer1, "OUTPUT": "memory:"}
        explode_result2 = processing.run(
            "native:deleteduplicategeometries", explode_params2
        )

        explode_layer: QgsVectorLayer = explode_result2["OUTPUT"]
        explode_layer.setName(tr("Exploded line as points"))
        explode_layer.renderer().symbol().setSize(2)
        explode_layer.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))
        QgsProject.instance().addMapLayer(explode_layer)
