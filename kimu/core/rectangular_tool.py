import math
from decimal import Decimal
from typing import List

from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsSnappingConfig,
    QgsTolerance,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgisInterface, QgsMapToolEmitPoint, QgsSnapIndicator
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.utils import iface

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name
from ..ui.rectangular_dockwidget import RectangularDockWidget
from .select_tool import SelectTool

LOGGER = setup_logger(plugin_name())


class RectangularMapping(SelectTool):
    def __init__(
        self, iface: QgisInterface, dock_widget: RectangularDockWidget
    ) -> None:
        super().__init__(iface)
        self.ui: RectangularDockWidget = dock_widget
        # Set suitable snapping settings
        my_snap_config = QgsSnappingConfig()
        my_snap_config.setEnabled(True)
        my_snap_config.setType(QgsSnappingConfig.Vertex)
        my_snap_config.setUnits(QgsTolerance.Pixels)
        my_snap_config.setTolerance(15)
        my_snap_config.setIntersectionSnapping(True)
        my_snap_config.setMode(QgsSnappingConfig.AllLayers)
        QgsProject.instance().setSnappingConfig(my_snap_config)
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

    # fmt: off
    def canvasPressEvent(  # noqa: N802
        self, event: QgsMapToolEmitPoint
    ) -> None:
        # fmt: on
        """Canvas click event."""
        if self.iface.activeLayer() != self.layer:
            LOGGER.warning(tr("Please select a line layer"),
                           extra={"details": ""})
            return

        check = 0
        for test_feature in self.iface.activeLayer().getFeatures():
            if check == 0:
                test_geom = test_feature.geometry()
                if QgsWkbTypes.isSingleType(test_geom.wkbType()):
                    pass
                else:
                    LOGGER.warning(
                        tr("Please select a line layer with "
                           "LineString geometries (instead "
                           "of MultiLineString geometries)"),
                        extra={"details": ""})
                    return
                check = 1
            else:
                pass

        if len(self.iface.activeLayer().selectedFeatures()) != 1:
            LOGGER.warning(tr("Please select only one line"),
                           extra={"details": ""})
            return
        else:
            geometry = self.iface.activeLayer().selectedFeatures()[0].geometry()

        # Snap the click to the closest point feature available
        m = self.iface.mapCanvas().snappingUtils().snapToMap(event.pos())
        self.i.setMatch(m)

        # Coordinates of the property boundary line's end point we
        # wish to measure the distance from
        start_point = [Decimal(m.point().x()), Decimal(m.point().y())]

        # Coordinates of the points implicitly defining the property boundary line
        line_feat = geometry.asPolyline()
        # Checks that the coordinate values get stored in the correct order
        if Decimal(QgsPointXY(line_feat[0]).x()) == start_point[0]:
            point1 = QgsPointXY(line_feat[0])
            point2 = QgsPointXY(line_feat[-1])
        elif Decimal(QgsPointXY(line_feat[-1]).x()) == start_point[0]:
            point1 = QgsPointXY(line_feat[-1])
            point2 = QgsPointXY(line_feat[0])
        else:
            LOGGER.warning(tr("Please select start or end point of the "
                              "selected property boundary line"
                              ), extra={"details": ""})
            return

        line_coords = [
            Decimal(point1.x()),
            Decimal(point1.y()),
            Decimal(point2.x()),
            Decimal(point2.y()),
        ]

        # Call the function capable of determining the parameter values
        # for solving the quadratic equation in hand
        parameters = self._calculate_parameters(line_coords)

        # Call for function capable of determining point_a
        point_a = self._locate_point_a(line_coords, parameters)

        # Call for function capable of determining point_b
        self._locate_point_b(line_coords, point_a)

    def _calculate_parameters(
        self, line_coords: List[Decimal]
    ) -> List[Decimal]:
        """Calculate values for a, b and c parameters"""
        # a_measure is given in crs units (meters for EPSG: 3067)
        a_measure = Decimal(self.ui.get_a_measure())
        # ADD DESCRIPTION OF THE IDEA!
        a = (
            (line_coords[2]) ** Decimal("2.0")
            - Decimal("2.0") * line_coords[0] * line_coords[2]
            + (line_coords[0]) ** Decimal("2.0")
            + (line_coords[3]) ** Decimal("2.0")
            - Decimal("2.0") * line_coords[1] * line_coords[3]
            + (line_coords[1]) ** Decimal("2.0")
        )
        b = (
            -Decimal("2.0")
            * (line_coords[2]) ** Decimal("2.0")
            * line_coords[0]
            + Decimal("4.0")
            * (line_coords[0]) ** Decimal("2.0")
            * line_coords[2]
            - Decimal("2.0")
            * (line_coords[0]) ** Decimal("3.0")
            - Decimal("2.0")
            * (line_coords[3]) ** Decimal("2.0")
            * line_coords[0]
            + Decimal("4.0")
            * line_coords[0] * line_coords[1]
            * line_coords[3]
            - Decimal("2.0")
            * (line_coords[1]) ** Decimal("2.0")
            * line_coords[0]
        )
        c = (
            - a_measure ** Decimal("2.0")
            * (line_coords[2]) ** Decimal("2.0")
            + Decimal("2.0")
            * a_measure ** Decimal("2.0")
            * line_coords[0]
            * line_coords[2]
            - a_measure ** Decimal("2.0")
            * (line_coords[0]) ** Decimal("2.0")
            + (line_coords[0]) ** Decimal("2.0")
            * (line_coords[2]) ** Decimal("2.0")
            - Decimal("2.0")
            * (line_coords[0]) ** Decimal("3.0")
            * line_coords[2]
            + (line_coords[0]) ** Decimal("4.0")
            + (line_coords[3]) ** Decimal("2.0")
            * (line_coords[0]) ** Decimal("2.0")
            - Decimal("2.0")
            * line_coords[1]
            * line_coords[3]
            * (line_coords[0]) ** Decimal("2.0")
            + (line_coords[1]) ** Decimal("2.0")
            * (line_coords[0]) ** Decimal("2.0")
        )
        result = [a, b, c]
        return result

    def _add_result_layers(
        self,
        x_b1: QVariant.Double,
        y_b1: QVariant.Double,
        x_b2: QVariant.Double,
        y_b2: QVariant.Double,
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

        point_b1 = QgsPointXY(x_b1, y_b1)
        f1 = QgsFeature()
        f1.setGeometry(QgsGeometry.fromPointXY(point_b1))
        f1.setAttributes([round(x_b1, 2), round(y_b1, 2)])
        result_layer1_dataprovider.addFeature(f1)
        result_layer1.updateExtents()

        result_layer1.setName(tr("Solution point 1"))
        result_layer1.renderer().symbol().setSize(2)
        result_layer1.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))

        QgsProject.instance().addMapLayer(result_layer1)

        result_layer2 = QgsVectorLayer("Point", "temp", "memory")
        result_layer2.setCrs(crs)
        result_layer2_dataprovider = result_layer2.dataProvider()
        result_layer2_dataprovider.addAttributes(
            [QgsField("xcoord", QVariant.Double), QgsField("ycoord", QVariant.Double)]
        )
        result_layer2.updateFields()
        point_b2 = QgsPointXY(x_b2, y_b2)
        f2 = QgsFeature()
        f2.setGeometry(QgsGeometry.fromPointXY(point_b2))
        f2.setAttributes([round(x_b2, 2), round(y_b2, 2)])
        result_layer2_dataprovider.addFeature(f2)
        result_layer2.updateExtents()

        result_layer2.setName(tr("Solution point 2"))
        result_layer2.renderer().symbol().setSize(2)
        result_layer2.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))

        QgsProject.instance().addMapLayer(result_layer2)

    def _locate_point_a(
        self, line_coords: List[Decimal], parameters: List[Decimal]
    ) -> List[Decimal]:
        """Determine the coordinates of point_a belonging to the property
        boundary line with distance corresponding to the given a_measure
        from the selected start point."""

        # Check that the solution exists
        sqrt_in = (
            parameters[1] ** Decimal("2.0")
            - Decimal("4.0") * parameters[0] * parameters[2]
        )
        if sqrt_in < 0.0 or parameters[0] == 0.0:
            LOGGER.warning(
                tr("Point A cannot be found on the property boundary line!"),
                extra={"details": ""},
            )
            return []

        # Computing the possible coordinates for a point
        x_a1 = (
            (-parameters[1] + Decimal(math.sqrt(sqrt_in)))
            / (Decimal("2.0") * parameters[0])
        )

        y_a1 = (
            (
                x_a1 * line_coords[3]
                - line_coords[0] * line_coords[3]
                - x_a1 * line_coords[1]
                + line_coords[2] * line_coords[1]
            ) / (line_coords[2] - line_coords[0])
        )

        x_a2 = (
            (-parameters[1] - Decimal(math.sqrt(sqrt_in)))
            / (Decimal("2.0") * parameters[0])
        )

        y_a2 = (
            (x_a2 * line_coords[3]
             - line_coords[0] * line_coords[3]
             - x_a2 * line_coords[1]
             + line_coords[2] * line_coords[1])
            / (line_coords[2] - line_coords[0])
        )

        bound_x = sorted([line_coords[0], line_coords[2]])
        bound_y = sorted([line_coords[1], line_coords[3]])

        # Select the correct solution point (the one existing
        # at the property boundary line)
        if (
            x_a1 > bound_x[0] and x_a1 < bound_x[1]
            and y_a1 > bound_y[0] and y_a1 < bound_y[1]
        ):
            x_a = x_a1
            y_a = y_a1
        else:
            x_a = x_a2
            y_a = y_a2

        point_res = [x_a, y_a]

        return point_res

    def _locate_point_b(
        self, line_coords: List[Decimal], point_a: List[Decimal]
    ) -> None:
        """Determine the coordinates of point_b belonging to the line which is
        orthogonal to the property boundary line and goes through point_a."""

        # b_measure is given in crs units (meters for EPSG: 3067)
        b_measure = Decimal(self.ui.get_b_measure())

        # Parameters related to equation of property boundary line in standard form
        a2 = line_coords[1] - line_coords[3]
        b2 = line_coords[2] - line_coords[0]
        c2 = line_coords[3] * line_coords[0] - line_coords[1] * line_coords[2]

        x_a = point_a[0]
        y_a = point_a[1]

        # Coordinates of the first solution point
        x_b1 = float(
            (line_coords[3] * b_measure * Decimal(math.sqrt(
                a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
            ))
              - line_coords[1] * b_measure * Decimal(math.sqrt(
                    a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
                )) - b2 * y_a * line_coords[3]
              + b2 * y_a * line_coords[1]
              - b2 * x_a * line_coords[2] + b2 * x_a * line_coords[0]
              - c2 * line_coords[3] + c2 * line_coords[1]
              )
            / (a2 * line_coords[3] - a2 * line_coords[1]
               - b2 * line_coords[2] + b2 * line_coords[0])
        )

        y_b1 = float(
            (y_a * line_coords[3] - y_a * line_coords[1]
             - Decimal(x_b1) * line_coords[2]
             + Decimal(x_b1) * line_coords[0]
             + x_a * line_coords[2] - x_a * line_coords[0])
            / (line_coords[3] - line_coords[1])
        )

        # Coordinates of the second solution point
        x_b2 = float(
            (-line_coords[3] * b_measure * Decimal(math.sqrt(
                a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
            ))
             + line_coords[1] * b_measure * Decimal(math.sqrt(
                    a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
                )) - b2 * y_a * line_coords[3]
             + b2 * y_a * line_coords[1]
             - b2 * x_a * line_coords[2] + b2 * x_a * line_coords[0]
             - c2 * line_coords[3] + c2 * line_coords[1]
             )
            / (a2 * line_coords[3] - a2 * line_coords[1]
               - b2 * line_coords[2] + b2 * line_coords[0])
        )

        y_b2 = float(
            (y_a * line_coords[3] - y_a * line_coords[1]
             - Decimal(x_b2) * line_coords[2]
             + Decimal(x_b2) * line_coords[0]
             + x_a * line_coords[2] - x_a * line_coords[0])
            / (line_coords[3] - line_coords[1])
        )

        # Check that the intersection point(s) lie(s) in the
        # map canvas extent
        extent = iface.mapCanvas().extent()

        if (
            x_b1 < extent.xMinimum()
            or x_b1 > extent.xMaximum()
            or y_b1 < extent.yMinimum()
            or y_b1 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Solution point 1 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return

        if (
            x_b2 < extent.xMinimum()
            or x_b2 > extent.xMaximum()
            or y_b2 < extent.yMinimum()
            or y_b2 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Solution point 2 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return

        # Add result layers to map canvas
        self._add_result_layers(x_b1, y_b1, x_b2, y_b2)
