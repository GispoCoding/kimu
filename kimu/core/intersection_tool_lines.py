from qgis import processing
from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant
from qgis.utils import iface

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name

LOGGER = setup_logger(plugin_name())


class IntersectionLines:
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
        """Determines the intersection point of the selected line features."""
        selected_layer = iface.activeLayer()
        if not self.__check_valid_layer(selected_layer):
            LOGGER.warning(tr("Please select a line layer"), extra={"details": ""})
            return

        if len(selected_layer.selectedFeatures()) != 2:
            LOGGER.warning(
                tr("Please select two line features from same layer"),
                extra={"details": ""},
            )
            return

        temp_layer = selected_layer.materialize(
            QgsFeatureRequest().setFilterFids(selected_layer.selectedFeatureIds())
        )
        params1 = {"INPUT": temp_layer, "OUTPUT": "memory:"}
        vertices = processing.run("native:extractvertices", params1)
        vertices_layer = vertices["OUTPUT"]

        if vertices_layer.featureCount() > 4:
            LOGGER.warning(
                tr("Please use Explode line(s) tool first!"), extra={"details": ""}
            )
            return

        result_layer = QgsVectorLayer("Point", "temp", "memory")
        crs = selected_layer.crs()
        result_layer.setCrs(crs)
        result_layer_dataprovider = result_layer.dataProvider()
        result_layer_dataprovider.addAttributes(
            [QgsField("xcoord", QVariant.Double), QgsField("ycoord", QVariant.Double)]
        )
        result_layer.updateFields()

        line_points = []

        features = selected_layer.selectedFeatures()
        for feat in features:
            line_feat = feat.geometry().asPolyline()
            start_point = QgsPointXY(line_feat[0])
            end_point = QgsPointXY(line_feat[-1])
            line_points.extend(
                [start_point.x(), start_point.y(), end_point.x(), end_point.y()]
            )

        # 1. Determine the functions of the straight lines each
        # of the selected line features represent (each line can
        # be seen as a limited representation of a function determining
        # a line which has no start and end points).
        # See e.g.
        # https://www.cuemath.com/geometry/two-point-form/
        # for more information.
        # 2. Search for intersection point of these two functions
        # by analytically modifying the resulting equation so
        # that it is possible to solve x (and then y).
        x = (
            line_points[0]
            * ((line_points[3] - line_points[1]) / (line_points[2] - line_points[0]))
            - line_points[4]
            * ((line_points[7] - line_points[5]) / (line_points[6] - line_points[4]))
            + line_points[5]
            - line_points[1]
        ) / (
            ((line_points[3] - line_points[1]) / (line_points[2] - line_points[0]))
            - ((line_points[7] - line_points[5]) / (line_points[6] - line_points[4]))
        )
        y = ((line_points[3] - line_points[1]) / (line_points[2] - line_points[0])) * (
            x - line_points[0]
        ) + line_points[1]

        intersection_point = QgsPointXY(x, y)
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPointXY(intersection_point))
        f.setAttributes([round(x, 2), round(y, 2)])
        result_layer_dataprovider.addFeature(f)
        result_layer.updateExtents()

        result_layer.setName(tr("Intersection point"))
        result_layer.renderer().symbol().setSize(2)
        QgsProject.instance().addMapLayer(result_layer)
