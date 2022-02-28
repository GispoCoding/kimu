from typing import List
import math

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant
from qgis.utils import iface
from qgis.gui import QgisInterface, QgsMapToolEmitPoint, QgsSnapIndicator

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

    def canvasPressEvent(self, event: QgsMapToolEmitPoint) -> None:
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
        x_coord = event.pos().x()
        y_coord = event.pos().y()
        point = self.canvas.getCoordinateTransform().toMapCoordinates(x_coord, y_coord)
        centroid = [point[0], point[1]]

        self._intersect(geometry, centroid)

    def _intersect(self, geometry: QgsGeometry, centroid: List) -> QgsVectorLayer:
        """Determine intersection point(s) of the selected line and implicitly determined circle."""
        result_layer1 = QgsVectorLayer("Point", "temp", "memory")
        crs = self.layer.crs()
        result_layer1.setCrs(crs)
        result_layer1_dataprovider = result_layer1.dataProvider()
        result_layer1_dataprovider.addAttributes(
            [QgsField("xcoord", QVariant.Double), QgsField("ycoord", QVariant.Double)]
        )
        result_layer1.updateFields()

        result_layer2 = QgsVectorLayer("Point", "temp", "memory")
        crs = self.layer.crs()
        result_layer2.setCrs(crs)
        result_layer2_dataprovider = result_layer2.dataProvider()
        result_layer2_dataprovider.addAttributes(
            [QgsField("xcoord", QVariant.Double), QgsField("ycoord", QVariant.Double)]
        )
        result_layer2.updateFields()

        line_feat = geometry.asPolyline()
        start_point = QgsPointXY(line_feat[0])
        end_point = QgsPointXY(line_feat[-1])
        line_coords = [start_point.x(), start_point.y(), end_point.x(), end_point.y()]

        # In crs units (meters for EPSG: 3067)
        r = self.ui.get_radius()

        # DUMMY TEST
        # x_sol1 = float(centroid[0]) + r * 100.0
        # y_sol1 = float(line_coords[3]) + r * 100.0
        # x_sol2 = float(centroid[0]) - r * 100.0
        # y_sol2 = float(line_coords[3]) - r * 100.0

        # Which coordinate value is stored at which index of the list
        # x1 = line_coords[0]
        # y1 = line_coords[1]
        # x2 = line_coords[2]
        # y2 = line_coords[3]

        # Debug tests
        #print(f"Value of line_coords[3] is {line_coords[3]}")
        #aa = (line_coords[3])**2.0
        #print(f"Value of aa is {aa}")
        #print(f"Value of r is {r}")

        # Determine the intersection point with the help of analytical geometry
        # 1. Determine the function of the straight line the selected line feature represents (each line can
        # be seen as a limited representation of a function determining a line which has no start and end points).
        # See e.g.
        # https://www.cuemath.com/geometry/two-point-form/
        # for more information.
        # 2. Determine the function of the circle defined implicitly via the clicked centroid point and given radius.
        # See e.g. Standard Equation of a Circle section from
        # https://www.cuemath.com/geometry/equation-of-circle/
        # for more information.
        # 3. Search for intersection point of these two functions by analytically modifying the resulting equation so
        # that it is possible to solve x (and then y). Note that we end up with quadratic equation ->> we will end
        # up with two possible solutions. The only exceptions are that the selected line does not intersect
        # with the circle at all or that the line acts as a tangent for the circle.
        a = (line_coords[3])**2.0 - 2.0 * line_coords[1] * line_coords[3] + (line_coords[1])**2.0 \
            + (line_coords[2])**2.0 - 2.0 * line_coords[0] * line_coords[2] + (line_coords[0])**2.0
        #print(f"Value of a is {a}")
        b = -2.0 * (line_coords[3])**2.0 * line_coords[0] + 2.0 * line_coords[1] * line_coords[3] * line_coords[2] \
            + 2.0 * line_coords[1] * line_coords[3] * line_coords[0] - 2.0 * (line_coords[1])**2.0 * line_coords[2] \
            - 2.0 * centroid[0] * (line_coords[2])**2.0 - 2.0 * centroid[0] * (line_coords[0])**2.0 \
            + 4.0 * centroid[0] * line_coords[0] * line_coords[2] - 2.0*line_coords[2]*centroid[1]*line_coords[3] \
            + 2.0 * centroid[1] * line_coords[1] * line_coords[2] + 2.0*centroid[1]*line_coords[3]*line_coords[0] \
            - 2.0 * centroid[1] * line_coords[1] * line_coords[0]
        #print(f"Value of b is {b}")
        c = (line_coords[3])**2.0 * (line_coords[0])**2.0 \
            - 2.0 * line_coords[0] * line_coords[1] * line_coords[2] * line_coords[3] \
            + (line_coords[1])**2.0 * (line_coords[2])**2.0 + (centroid[0])**2.0 * (line_coords[2])**2.0 \
            - 2.0 * (centroid[0])**2.0 * line_coords[0] * line_coords[2] + (centroid[0])**2.0 * (line_coords[0])**2.0 \
            + 2.0 * line_coords[2] * centroid[1] * line_coords[3] * line_coords[0] \
            - 2.0 * (line_coords[2])**2.0 * centroid[1] * line_coords[1] \
            - 2.0 * (line_coords[0])**2.0 * centroid[1] * line_coords[3] \
            + 2.0 * centroid[1] * line_coords[1] * line_coords[2] * line_coords[0] \
            + (line_coords[2])**2.0 * (centroid[1])**2.0 - (line_coords[2])**2.0 * r**2.0 \
            - 2.0*line_coords[0]*line_coords[2] * (centroid[1])**2.0 + 2.0 * line_coords[0] * line_coords[2] * r**2.0 \
            + (line_coords[0])**2.0 * (centroid[1])**2.0 - (line_coords[0])**2.0 * r**2.0
        #print(f"Value of c is {c}")

        # Check that the selected line feature and indirectly defined circle intersect
        # To do: Complains that there is no intersection point of given radius if radius is small (e.g. 10m)?
        # The limit value seems to change according to coordinates of centroid point..
        sqrt_in = b**2.0 - 4.0 * a * c
        print(f"Value of sqrt_in is {sqrt_in}")
        if sqrt_in < 0.0 or a == 0.0:
            LOGGER.warning(
                tr("There is no intersection point(s)!"), extra={"details": ""},
            )
            return

        # Computing the coordinates for intersection points
        x_sol1 = (-b + math.sqrt(sqrt_in)) / (2.0 * a)

        y_sol1 = (x_sol1 * line_coords[3] - line_coords[0] * line_coords[3] - x_sol1 * line_coords[1] \
                   + line_coords[2] * line_coords[1]) / (line_coords[2] - line_coords[0])

        x_sol2 = (-b - math.sqrt(sqrt_in)) / (2.0 * a)

        y_sol2 = (x_sol2 * line_coords[3] - line_coords[0] * line_coords[3] - x_sol2 * line_coords[1] \
                   + line_coords[2] * line_coords[1]) / (line_coords[2] - line_coords[0])

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
        # In case the line only touches the circle, only one result layer gets generated since x_sol1 = x_sol2
        if sqrt_in == 0.0:
            intersection_point = QgsPointXY(x_sol1, y_sol1)
            f1 = QgsFeature()
            f1.setGeometry(QgsGeometry.fromPointXY(intersection_point))
            f1.setAttributes([round(x_sol1, 2), round(y_sol1, 2)])
            result_layer1_dataprovider.addFeature(f1)
            result_layer1.updateExtents()

            result_layer1.setName(tr("The only intersection point"))
            result_layer1.renderer().symbol().setSize(2)

            QgsProject.instance().addMapLayer(result_layer1)
        else:
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
