import decimal
import math
from typing import List

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgisInterface, QgsMapToolEmitPoint, QgsSnapIndicator
from qgis.PyQt.QtCore import QVariant
from qgis.utils import iface

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name
from ..ui.line_circle_dockwidget import LineCircleDockWidget
from .select_tool import SelectTool

LOGGER = setup_logger(plugin_name())


class IntersectionLineCircle(SelectTool):
    def __init__(self, iface: QgisInterface, dock_widget: LineCircleDockWidget) -> None:
        super().__init__(iface)
        self.ui: LineCircleDockWidget = dock_widget
        self.i = QgsSnapIndicator(self.iface.mapCanvas())

    def active_changed(self, layer: QgsVectorLayer) -> None:
        """Triggered when active layer changes."""
        if (
            isinstance(layer, QgsVectorLayer)
            and layer.isSpatial()
            and layer.geometryType() == QgsWkbTypes.LineGeometry
        ):
            self.layer = layer
            self.setLayer(self.layer)

    def canvasPressEvent(self, event: QgsMapToolEmitPoint) -> None:  # fmt: skip noqa: N802
        """Canvas click event for storing centroid point of the circle."""
        if self.iface.activeLayer() != self.layer:
            LOGGER.warning(tr("Please select a line layer"), extra={"details": ""})
            return

        if len(self.iface.activeLayer().selectedFeatures()) != 1:
            LOGGER.warning(tr("Please select only one line"), extra={"details": ""})
            return
        else:
            geometry = self.iface.activeLayer().selectedFeatures()[0].geometry()

        m = self.iface.mapCanvas().snappingUtils().snapToMap(event.pos())
        self.i.setMatch(m)

        # Coordinates of the point to be used as a circle centroid
        centroid = [decimal.Decimal(m.point().x()), decimal.Decimal(m.point().y())]

        self._intersect(geometry, centroid)

    def _parameters(self, line_coords: List, centroid: List) -> List:
        """Calculate values for a, b and c parameters"""
        # In crs units (meters for EPSG: 3067)
        r = decimal.Decimal(self.ui.get_radius())
        # 1. Determine the function of the straight line the selected
        # line feature represents (each line can be seen as a limited
        # representation of a function determining a line which has no
        # start and end points). See e.g.
        # https://www.cuemath.com/geometry/two-point-form/
        # for more information.
        # 2. Determine the function of the circle defined implicitly via
        # the clicked centroid point and given radius.
        # See e.g. Standard Equation of a Circle section from
        # https://www.cuemath.com/geometry/equation-of-circle/
        # for more information.
        # 3. Search for intersection point of these two functions by
        # analytically modifying the resulting equation so that it is
        # possible to solve x (and then y)
        # 4. We end up with quadratic equation and need to solve
        # it with
        # The only exceptions are that the selected line
        # does not intersect with the circle at all or that the line
        # acts as a tangent for the circle.
        print(f"Value of r is {r}")
        a = (
            (line_coords[3]) ** decimal.Decimal("2.0")
            - decimal.Decimal("2.0") * line_coords[1] * line_coords[3]
            + (line_coords[1]) ** decimal.Decimal("2.0")
            + (line_coords[2]) ** decimal.Decimal("2.0")
            - decimal.Decimal("2.0") * line_coords[0] * line_coords[2]
            + (line_coords[0]) ** decimal.Decimal("2.0")
        )
        b = (
            -decimal.Decimal("2.0")
            * (line_coords[3]) ** decimal.Decimal("2.0")
            * line_coords[0]
            + decimal.Decimal("2.0") * line_coords[1] * line_coords[3] * line_coords[2]
            + decimal.Decimal("2.0") * line_coords[1] * line_coords[3] * line_coords[0]
            - decimal.Decimal("2.0")
            * (line_coords[1]) ** decimal.Decimal("2.0")
            * line_coords[2]
            - decimal.Decimal("2.0")
            * centroid[0]
            * (line_coords[2]) ** decimal.Decimal("2.0")
            - decimal.Decimal("2.0")
            * centroid[0]
            * (line_coords[0]) ** decimal.Decimal("2.0")
            + decimal.Decimal("4.0") * centroid[0] * line_coords[0] * line_coords[2]
            - decimal.Decimal("2.0") * line_coords[2] * centroid[1] * line_coords[3]
            + decimal.Decimal("2.0") * centroid[1] * line_coords[1] * line_coords[2]
            + decimal.Decimal("2.0") * centroid[1] * line_coords[3] * line_coords[0]
            - decimal.Decimal("2.0") * centroid[1] * line_coords[1] * line_coords[0]
        )
        c = (
            (line_coords[3]) ** decimal.Decimal("2.0")
            * (line_coords[0]) ** decimal.Decimal("2.0")
            - decimal.Decimal("2.0")
            * line_coords[0]
            * line_coords[1]
            * line_coords[2]
            * line_coords[3]
            + (line_coords[1]) ** decimal.Decimal("2.0")
            * (line_coords[2]) ** decimal.Decimal("2.0")
            + (centroid[0]) ** decimal.Decimal("2.0")
            * (line_coords[2]) ** decimal.Decimal("2.0")
            - decimal.Decimal("2.0")
            * (centroid[0]) ** decimal.Decimal("2.0")
            * line_coords[0]
            * line_coords[2]
            + (centroid[0]) ** decimal.Decimal("2.0")
            * (line_coords[0]) ** decimal.Decimal("2.0")
            + decimal.Decimal("2.0")
            * line_coords[2]
            * centroid[1]
            * line_coords[3]
            * line_coords[0]
            - decimal.Decimal("2.0")
            * (line_coords[2]) ** decimal.Decimal("2.0")
            * centroid[1]
            * line_coords[1]
            - decimal.Decimal("2.0")
            * (line_coords[0]) ** decimal.Decimal("2.0")
            * centroid[1]
            * line_coords[3]
            + decimal.Decimal("2.0")
            * centroid[1]
            * line_coords[1]
            * line_coords[2]
            * line_coords[0]
            + (line_coords[2]) ** decimal.Decimal("2.0")
            * (centroid[1]) ** decimal.Decimal("2.0")
            - (line_coords[2]) ** decimal.Decimal("2.0") * r ** decimal.Decimal("2.0")
            - decimal.Decimal("2.0")
            * line_coords[0]
            * line_coords[2]
            * (centroid[1]) ** decimal.Decimal("2.0")
            + decimal.Decimal("2.0")
            * line_coords[0]
            * line_coords[2]
            * r ** decimal.Decimal("2.0")
            + (line_coords[0]) ** decimal.Decimal("2.0")
            * (centroid[1]) ** decimal.Decimal("2.0")
            - (line_coords[0]) ** decimal.Decimal("2.0") * r ** decimal.Decimal("2.0")
        )
        result = [a, b, c]
        return result

    def _one_layer(
        self, x_sol1: QVariant.Double, y_sol1: QVariant.Double
    ) -> QgsVectorLayer:
        """Triggered when only one intersection point exists."""
        result_layer1 = QgsVectorLayer("Point", "temp", "memory")
        crs = self.layer.crs()
        result_layer1.setCrs(crs)
        result_layer1_dataprovider = result_layer1.dataProvider()
        result_layer1_dataprovider.addAttributes(
            [QgsField("xcoord", QVariant.Double), QgsField("ycoord", QVariant.Double)]
        )
        result_layer1.updateFields()

        intersection_point = QgsPointXY(x_sol1, y_sol1)
        f1 = QgsFeature()
        f1.setGeometry(QgsGeometry.fromPointXY(intersection_point))
        f1.setAttributes([round(x_sol1, 2), round(y_sol1, 2)])
        result_layer1_dataprovider.addFeature(f1)
        result_layer1.updateExtents()

        result_layer1.setName(tr("The only intersection point"))
        result_layer1.renderer().symbol().setSize(2)

        QgsProject.instance().addMapLayer(result_layer1)

    def _two_layers(
        self,
        x_sol1: QVariant.Double,
        y_sol1: QVariant.Double,
        x_sol2: QVariant.Double,
        y_sol2: QVariant.Double,
    ) -> QgsVectorLayer:
        """Triggered when two intersection points exist."""
        result_layer1 = QgsVectorLayer("Point", "temp", "memory")
        crs = self.layer.crs()
        result_layer1.setCrs(crs)
        result_layer1_dataprovider = result_layer1.dataProvider()
        result_layer1_dataprovider.addAttributes(
            [QgsField("xcoord", QVariant.Double), QgsField("ycoord", QVariant.Double)]
        )
        result_layer1.updateFields()

        result_layer2 = QgsVectorLayer("Point", "temp", "memory")
        result_layer2.setCrs(crs)
        result_layer2_dataprovider = result_layer2.dataProvider()
        result_layer2_dataprovider.addAttributes(
            [QgsField("xcoord", QVariant.Double), QgsField("ycoord", QVariant.Double)]
        )
        result_layer2.updateFields()

        intersection_point1 = QgsPointXY(x_sol1, y_sol1)
        f1 = QgsFeature()
        f1.setGeometry(QgsGeometry.fromPointXY(intersection_point1))
        f1.setAttributes([round(x_sol1, 2), round(y_sol1, 2)])
        result_layer1_dataprovider.addFeature(f1)
        result_layer1.updateExtents()

        result_layer1.setName(tr("Intersection point 1"))
        result_layer1.renderer().symbol().setSize(2)

        intersection_point2 = QgsPointXY(x_sol2, y_sol2)
        f2 = QgsFeature()
        f2.setGeometry(QgsGeometry.fromPointXY(intersection_point2))
        f2.setAttributes([round(x_sol2, 2), round(y_sol2, 2)])
        result_layer2_dataprovider.addFeature(f2)
        result_layer2.updateExtents()

        result_layer2.setName(tr("Intersection point 2"))
        result_layer2.renderer().symbol().setSize(2)

        QgsProject.instance().addMapLayer(result_layer1)
        QgsProject.instance().addMapLayer(result_layer2)

    def _intersect(self, geometry: QgsGeometry, centroid: List) -> QgsVectorLayer:
        """Determine intersection point(s) of the selected
        line and implicitly determined circle."""
        result_layer1 = QgsVectorLayer("Point", "temp", "memory")
        crs = self.layer.crs()
        result_layer1.setCrs(crs)
        result_layer1_dataprovider = result_layer1.dataProvider()
        result_layer1_dataprovider.addAttributes(
            [QgsField("xcoord", QVariant.Double), QgsField("ycoord", QVariant.Double)]
        )
        result_layer1.updateFields()

        line_feat = geometry.asPolyline()
        start_point = QgsPointXY(line_feat[0])
        end_point = QgsPointXY(line_feat[-1])
        line_coords = [
            decimal.Decimal(start_point.x()),
            decimal.Decimal(start_point.y()),
            decimal.Decimal(end_point.x()),
            decimal.Decimal(end_point.y()),
        ]

        # Determine the intersection point with the help of analytical geometry
        parameters = self._parameters(line_coords, centroid)

        # Check that the selected line feature and indirectly
        # defined circle intersect.
        sqrt_in = (
            parameters[1] ** decimal.Decimal("2.0")
            - decimal.Decimal("4.0") * parameters[0] * parameters[2]
        )
        print(f"Value of sqrt_in is {sqrt_in}")
        if sqrt_in < 0.0 or parameters[0] == 0.0:
            LOGGER.warning(
                tr("There is no intersection point(s)!"),
                extra={"details": ""},
            )
            return

        # Computing the coordinates for intersection points
        x_sol1 = (-parameters[1] + decimal.Decimal(math.sqrt(sqrt_in))) / (
            decimal.Decimal("2.0") * parameters[0]
        )

        y_sol1 = float(
            (
                x_sol1 * line_coords[3]
                - line_coords[0] * line_coords[3]
                - x_sol1 * line_coords[1]
                + line_coords[2] * line_coords[1]
            )
            / (line_coords[2] - line_coords[0])
        )

        x_sol1 = float(x_sol1)

        x_sol2 = (-parameters[1] - decimal.Decimal(math.sqrt(sqrt_in))) / (
            decimal.Decimal("2.0") * parameters[0]
        )

        y_sol2 = float(
            (
                x_sol2 * line_coords[3]
                - line_coords[0] * line_coords[3]
                - x_sol2 * line_coords[1]
                + line_coords[2] * line_coords[1]
            )
            / (line_coords[2] - line_coords[0])
        )

        x_sol2 = float(x_sol2)

        # Check that the result point lies in the map canvas extent
        extent = iface.mapCanvas().extent()

        if (
            x_sol1 < extent.xMinimum()
            or x_sol1 > extent.xMaximum()
            or y_sol1 < extent.yMinimum()
            or y_sol1 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Intersection point 1 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return

        if (
            x_sol2 < extent.xMinimum()
            or x_sol2 > extent.xMaximum()
            or y_sol2 < extent.yMinimum()
            or y_sol2 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Intersection point 2 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return

        # Check that the line genuinely intersects with a circle.
        # In case the line only touches the circle, only one result
        # layer gets generated since x_sol1 = x_sol2
        if float(sqrt_in) == 0.0:
            self._one_layer(x_sol1, y_sol1)
        else:
            self._two_layers(x_sol1, y_sol1, x_sol2, y_sol2)
