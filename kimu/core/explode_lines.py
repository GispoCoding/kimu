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

LOGGER = setup_logger(plugin_name())


class ExplodeLines:
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
        """Explodes selected line features to segment lines."""
        layer = iface.activeLayer()
        if not self.__check_valid_layer(layer):
            LOGGER.warning(tr("Please select a line layer"), extra={"details": ""})
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

        line_result = processing.run("native:explodelines", line_params)
        result_layer = line_result["OUTPUT"]

        result_layer.setName(tr("Exploded line"))
        result_layer.renderer().symbol().setWidth(0.7)
        result_layer.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))
        QgsProject.instance().addMapLayer(result_layer)
