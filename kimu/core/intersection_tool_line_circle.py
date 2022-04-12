import math
from decimal import Decimal
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
from qgis.gui import QgisInterface, QgsMapToolEmitPoint
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.utils import iface

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name
from ..ui.line_circle_dockwidget import LineCircleDockWidget
from .click_tool import ClickTool
from .select_tool import SelectTool

LOGGER = setup_logger(plugin_name())


class IntersectionLineCircle(SelectTool):
    def __init__(self, iface: QgisInterface, dock_widget: LineCircleDockWidget) -> None:
        super().__init__(iface)
        self.ui: LineCircleDockWidget = dock_widget

    def active_changed(self, layer: QgsVectorLayer) -> None:
        """Triggered when active layer changes."""
        if (
            isinstance(layer, QgsVectorLayer)
            and layer.isSpatial()
            and layer.geometryType() == QgsWkbTypes.LineGeometry
        ):
            self.layer = layer
            self.setLayer(self.layer)

    # fmt: off
    def canvasPressEvent(  # noqa: N802
        self, event: QgsMapToolEmitPoint
    ) -> None:
        # fmt: on
        """Canvas click event for storing centroid
        point of the circle."""
        if self.iface.activeLayer() != self.layer:
            LOGGER.warning(tr("Please select a line layer"), extra={"details": ""})
            return

        if QgsWkbTypes.isSingleType(
            list(
                self.iface.activeLayer().getFeatures()
            )[0].geometry().wkbType()
        ):
            pass
        else:
            LOGGER.warning(
                tr("Please select a line layer with "
                   "LineString geometries (instead "
                   "of MultiLineString geometries)"),
                extra={"details": ""})
            return

        if len(self.iface.activeLayer().selectedFeatures()) != 1:
            LOGGER.warning(tr("Please select only one line"), extra={"details": ""})
            return

        geometry = self.iface.activeLayer().selectedFeatures()[0].geometry()

        # Snap the click to the closest point feature available.
        # Note that your QGIS's snapping options have on effect
        # on which objects / vertexes the tool will snap and
        # get the coordinates of the point to be used as a circle centroid
        centroid = ClickTool(self.iface).activate(event)

        # Call for function determining the intersection point
        self._intersect(geometry, centroid)

    def _calculate_intersection_parameters(
        self, line_coords: List[Decimal], centroid: List[Decimal]
    ) -> List[Decimal]:
        """Calculate values for a, b and c parameters"""
        # Radius is given in crs units (meters for EPSG: 3067)
        r = Decimal(self.ui.get_radius())
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
        # 3. Search for intersection point of the line and circle
        # by setting there functions equal and analytically modifying
        # the resulting equation so that it is possible to solve x
        # (and then, after figuring out suitable value for x, y).
        # 4. After some analytical simplifying of the particular
        # equation you will see that it is needed to solve the
        # quadratic equation in order to find suitable values for x.
        # The parameters a, b and c to be solved come from the
        # quadratic formula. See e.g.
        # https://www.mathsisfun.com/algebra/quadratic-equation.html
        # for more information.
        a = (
            (line_coords[3]) ** Decimal("2.0")
            - Decimal("2.0") * line_coords[1] * line_coords[3]
            + (line_coords[1]) ** Decimal("2.0")
            + (line_coords[2]) ** Decimal("2.0")
            - Decimal("2.0") * line_coords[0] * line_coords[2]
            + (line_coords[0]) ** Decimal("2.0")
        )
        b = (
            -Decimal("2.0")
            * (line_coords[3]) ** Decimal("2.0")
            * line_coords[0]
            + Decimal("2.0") * line_coords[1] * line_coords[3] * line_coords[2]
            + Decimal("2.0") * line_coords[1] * line_coords[3] * line_coords[0]
            - Decimal("2.0")
            * (line_coords[1]) ** Decimal("2.0")
            * line_coords[2]
            - Decimal("2.0")
            * centroid[0]
            * (line_coords[2]) ** Decimal("2.0")
            - Decimal("2.0")
            * centroid[0]
            * (line_coords[0]) ** Decimal("2.0")
            + Decimal("4.0") * centroid[0] * line_coords[0] * line_coords[2]
            - Decimal("2.0") * line_coords[2] * centroid[1] * line_coords[3]
            + Decimal("2.0") * centroid[1] * line_coords[1] * line_coords[2]
            + Decimal("2.0") * centroid[1] * line_coords[3] * line_coords[0]
            - Decimal("2.0") * centroid[1] * line_coords[1] * line_coords[0]
        )
        c = (
            (line_coords[3]) ** Decimal("2.0")
            * (line_coords[0]) ** Decimal("2.0")
            - Decimal("2.0")
            * line_coords[0]
            * line_coords[1]
            * line_coords[2]
            * line_coords[3]
            + (line_coords[1]) ** Decimal("2.0")
            * (line_coords[2]) ** Decimal("2.0")
            + (centroid[0]) ** Decimal("2.0")
            * (line_coords[2]) ** Decimal("2.0")
            - Decimal("2.0")
            * (centroid[0]) ** Decimal("2.0")
            * line_coords[0]
            * line_coords[2]
            + (centroid[0]) ** Decimal("2.0")
            * (line_coords[0]) ** Decimal("2.0")
            + Decimal("2.0")
            * line_coords[2]
            * centroid[1]
            * line_coords[3]
            * line_coords[0]
            - Decimal("2.0")
            * (line_coords[2]) ** Decimal("2.0")
            * centroid[1]
            * line_coords[1]
            - Decimal("2.0")
            * (line_coords[0]) ** Decimal("2.0")
            * centroid[1]
            * line_coords[3]
            + Decimal("2.0")
            * centroid[1]
            * line_coords[1]
            * line_coords[2]
            * line_coords[0]
            + (line_coords[2]) ** Decimal("2.0")
            * (centroid[1]) ** Decimal("2.0")
            - (line_coords[2]) ** Decimal("2.0") * r ** Decimal("2.0")
            - Decimal("2.0")
            * line_coords[0]
            * line_coords[2]
            * (centroid[1]) ** Decimal("2.0")
            + Decimal("2.0")
            * line_coords[0]
            * line_coords[2]
            * r ** Decimal("2.0")
            + (line_coords[0]) ** Decimal("2.0")
            * (centroid[1]) ** Decimal("2.0")
            - (line_coords[0]) ** Decimal("2.0") * r ** Decimal("2.0")
        )
        result = [a, b, c]
        return result

    def _add_result_layers(
        self,
        x_sol1: QVariant.Double,
        y_sol1: QVariant.Double,
        x_sol2: QVariant.Double,
        y_sol2: QVariant.Double,
    ) -> None:
        """Triggered when result layer needs to be generated."""
        result_layer1 = QgsVectorLayer("Point", "temp", "memory")
        crs = self.layer.crs()
        result_layer1.setCrs(crs)
        result_layer1_dataprovider = result_layer1.dataProvider()
        result_layer1_dataprovider.addAttributes(
            [QgsField("xcoord", QVariant.Double), QgsField("ycoord", QVariant.Double)]
        )
        result_layer1.updateFields()

        intersection_point1 = QgsPointXY(x_sol1, y_sol1)
        f1 = QgsFeature()
        f1.setGeometry(QgsGeometry.fromPointXY(intersection_point1))
        f1.setAttributes([round(x_sol1, 2), round(y_sol1, 2)])
        result_layer1_dataprovider.addFeature(f1)
        result_layer1.updateExtents()

        result_layer1.setName(tr("Intersection point 1"))
        result_layer1.renderer().symbol().setSize(2)
        result_layer1.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))

        QgsProject.instance().addMapLayer(result_layer1)

        # If the line forms a tangent to the circle (instead
        # of genuinely intersecting with the circle),
        # only one intersection point exists. Thus there is
        # no need for second result layer
        if x_sol1 == x_sol2:
            return

        result_layer2 = QgsVectorLayer("Point", "temp", "memory")
        result_layer2.setCrs(crs)
        result_layer2_dataprovider = result_layer2.dataProvider()
        result_layer2_dataprovider.addAttributes(
            [QgsField("xcoord", QVariant.Double), QgsField("ycoord", QVariant.Double)]
        )
        result_layer2.updateFields()
        intersection_point2 = QgsPointXY(x_sol2, y_sol2)
        f2 = QgsFeature()
        f2.setGeometry(QgsGeometry.fromPointXY(intersection_point2))
        f2.setAttributes([round(x_sol2, 2), round(y_sol2, 2)])
        result_layer2_dataprovider.addFeature(f2)
        result_layer2.updateExtents()

        result_layer2.setName(tr("Intersection point 2"))
        result_layer2.renderer().symbol().setSize(2)
        result_layer2.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))

        QgsProject.instance().addMapLayer(result_layer2)

    def _intersect(self, geometry: QgsGeometry, centroid: List[Decimal]) -> None:
        """Determine the intersection point(s) of the selected
        line and implicitly determined (centroid+radius) circle."""

        line_feat = geometry.asPolyline()
        start_point = QgsPointXY(line_feat[0])
        end_point = QgsPointXY(line_feat[-1])
        line_coords = [
            Decimal(start_point.x()),
            Decimal(start_point.y()),
            Decimal(end_point.x()),
            Decimal(end_point.y()),
        ]

        # Call the functions capable of determining the parameter
        # values needed to find out intersection point(s)
        parameters = self._calculate_intersection_parameters(line_coords, centroid)

        # Check that the selected line feature and indirectly
        # defined circle intersect
        sqrt_in = (
            parameters[1] ** Decimal("2.0")
            - Decimal("4.0") * parameters[0] * parameters[2]
        )
        if sqrt_in < 0.0 or parameters[0] == 0.0:
            LOGGER.warning(
                tr("There is no intersection point(s)!"),
                extra={"details": ""},
            )
            return

        # Computing the coordinates for the intersection point(s)
        x_sol1 = float((-parameters[1] + Decimal(math.sqrt(sqrt_in))) / (
            Decimal("2.0") * parameters[0]
        ))

        y_sol1 = float(
            (
                Decimal(x_sol1) * line_coords[3]
                - line_coords[0] * line_coords[3]
                - Decimal(x_sol1) * line_coords[1]
                + line_coords[2] * line_coords[1]
            )
            / (line_coords[2] - line_coords[0])
        )

        x_sol2 = float((-parameters[1] - Decimal(math.sqrt(sqrt_in))) / (
            Decimal("2.0") * parameters[0]
        ))

        y_sol2 = float(
            (
                Decimal(x_sol2) * line_coords[3]
                - line_coords[0] * line_coords[3]
                - Decimal(x_sol2) * line_coords[1]
                + line_coords[2] * line_coords[1]
            )
            / (line_coords[2] - line_coords[0])
        )

        # Check that the intersection point(s) lie(s) in the
        # map canvas extent
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

        # Add result layer to map canvas
        self._add_result_layers(x_sol1, y_sol1, x_sol2, y_sol2)
