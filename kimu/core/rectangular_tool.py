import math
from decimal import Decimal
from typing import List

from PyQt5.QtWidgets import QMessageBox
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPalLayerSettings,
    QgsPointXY,
    QgsProject,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)
from qgis.gui import QgsMapToolEmitPoint
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont
from qgis.utils import iface

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name
from ..ui.rectangular_dockwidget import RectangularDockWidget
from .click_tool import ClickTool
from .select_tool import SelectTool

LOGGER = setup_logger(plugin_name())


class RectangularMapping(SelectTool):
    def __init__(self, dock_widget: RectangularDockWidget) -> None:
        super().__init__(iface)
        self.ui: RectangularDockWidget = dock_widget

    def active_changed(self, layer: QgsVectorLayer) -> None:
        """Triggered when active layer changes."""
        if (
            isinstance(layer, QgsVectorLayer)
            and layer.isSpatial()
            and layer.geometryType() == QgsWkbTypes.LineGeometry
        ):
            self.layer = layer
            self.setLayer(self.layer)

    def canvasPressEvent(self, event: QgsMapToolEmitPoint) -> None:  # noqa: N802
        """Canvas click event."""
        if self.iface.activeLayer() != self.layer:
            LOGGER.warning(tr("Please select a line layer"), extra={"details": ""})
            return

        if QgsWkbTypes.isSingleType(
            list(self.iface.activeLayer().getFeatures())[0].geometry().wkbType()
        ):
            pass
        else:
            LOGGER.warning(
                tr(
                    "Please select a line layer with "
                    "LineString geometries (instead "
                    "of MultiLineString geometries)"
                ),
                extra={"details": ""},
            )
            return

        if len(self.iface.activeLayer().selectedFeatures()) != 1:
            LOGGER.warning(tr("Please select only one line"), extra={"details": ""})
            return

        geometry = self.iface.activeLayer().selectedFeatures()[0].geometry()

        # Snap the click to the closest point feature available and get
        # the coordinates of the property boundary line's end point we
        # wish to measure the distance from
        start_point = ClickTool(self.iface).activate(event)

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
            LOGGER.warning(
                tr(
                    "Please select start or end point of the "
                    "selected property boundary line."
                ),
                extra={"details": ""},
            )
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
        points_b = self._locate_point_b(line_coords, point_a)

        corners: List[List[Decimal]]
        corners = []

        path = self.ui.get_output_file()

        options_layer = QgsVectorLayer("Point", "temp", "memory")
        crs = self.layer.crs()
        options_layer.setCrs(crs)
        options_layer_dataprovider = options_layer.dataProvider()
        options_layer_dataprovider.addAttributes([QgsField("id", QVariant.String)])
        options_layer.updateFields()

        opt_ids: List[int]
        opt_ids = []
        to_be_deleted: List[int]
        to_be_deleted = []

        self._add_points(points_b, corners, options_layer, opt_ids)

        QgsProject.instance().addMapLayer(options_layer)

        options_layer.startEditing()

        mb = QMessageBox()
        mb.setText(
            "Do you want to choose option 1 for corner point "
            + str(len(corners) + 1)
            + "?"
        )
        mb.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        ret = mb.exec()
        if ret == QMessageBox.No:
            to_be_deleted.append(opt_ids[0])
            corners.append([points_b[2], points_b[3]])
        # i.e. when ret == QMessageBox.Yes:
        else:
            to_be_deleted.append(opt_ids[1])
            corners.append([points_b[0], points_b[1]])

        point_b: List[Decimal]
        point_b = corners[0]

        # c_measures are given in crs units (meters for EPSG: 3067)
        c_measure_list = self.ui.get_c_measures().split(",")

        for i in range(len(c_measure_list)):
            c_measure = Decimal(c_measure_list[i])
            # Let's map the second corner point which will be
            # located in the extension of the line feature
            # connecting point_a and point_b
            if i == 0:
                point_c = self._locate_point_c(c_measure, point_a, point_b)
                self._add_points(point_c, corners, options_layer, opt_ids)
                corners.append([point_c[0], point_c[1]])
            # Let's map the rest of the rectangular corner points
            # (they will be located perpendicularly with respect to
            # the line feature connecting two last elements of
            # the corners list)
            else:
                new_corner_points = self._locate_point_d(c_measure, corners)
                self._add_points(new_corner_points, corners, options_layer, opt_ids)
                mb = QMessageBox()
                mb.setText(
                    "Do you want to choose option 1 for corner point "
                    + str(len(corners) + 1)
                    + "?"
                )
                mb.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                ret = mb.exec()
                if ret == QMessageBox.No:
                    # Let's check that we point we are going to add to corners
                    # list is a new one (we do not want to generate duplicates)
                    if [new_corner_points[2], new_corner_points[3]] not in corners:
                        if i == 1:
                            to_be_deleted.append(opt_ids[3])
                            corners.append([new_corner_points[2], new_corner_points[3]])
                        else:
                            to_be_deleted.append(opt_ids[2 + (i * 2 - 1)])
                            corners.append([new_corner_points[2], new_corner_points[3]])
                # i.e. when ret == QMessageBox.Yes:
                else:
                    if [new_corner_points[0], new_corner_points[1]] not in corners:
                        if i == 1:
                            to_be_deleted.append(opt_ids[4])
                            corners.append([new_corner_points[0], new_corner_points[1]])
                        else:
                            to_be_deleted.append(opt_ids[2 + (i * 2)])
                            corners.append([new_corner_points[0], new_corner_points[1]])

        options_layer.deleteFeatures(to_be_deleted)
        options_layer.commitChanges()
        iface.vectorLayerTools().stopEditing(options_layer)

        op = QgsVectorFileWriter.SaveVectorOptions()
        op.actionOnExistingFile = QgsVectorFileWriter.AppendToLayerAddFields
        QgsVectorFileWriter.writeAsVectorFormat(options_layer, path, op)

    def _calculate_parameters(self, line_coords: List[Decimal]) -> List[Decimal]:
        """Calculate values for a, b and c parameters"""
        # a_measure is given in crs units (meters for EPSG: 3067)
        a_measure = Decimal(self.ui.get_a_measure())
        a = (
            (line_coords[2]) ** Decimal("2.0")
            - Decimal("2.0") * line_coords[0] * line_coords[2]
            + (line_coords[0]) ** Decimal("2.0")
            + (line_coords[3]) ** Decimal("2.0")
            - Decimal("2.0") * line_coords[1] * line_coords[3]
            + (line_coords[1]) ** Decimal("2.0")
        )
        b = (
            -Decimal("2.0") * (line_coords[2]) ** Decimal("2.0") * line_coords[0]
            + Decimal("4.0") * (line_coords[0]) ** Decimal("2.0") * line_coords[2]
            - Decimal("2.0") * (line_coords[0]) ** Decimal("3.0")
            - Decimal("2.0") * (line_coords[3]) ** Decimal("2.0") * line_coords[0]
            + Decimal("4.0") * line_coords[0] * line_coords[1] * line_coords[3]
            - Decimal("2.0") * (line_coords[1]) ** Decimal("2.0") * line_coords[0]
        )
        c = (
            -(a_measure ** Decimal("2.0")) * (line_coords[2]) ** Decimal("2.0")
            + Decimal("2.0")
            * a_measure ** Decimal("2.0")
            * line_coords[0]
            * line_coords[2]
            - a_measure ** Decimal("2.0") * (line_coords[0]) ** Decimal("2.0")
            + (line_coords[0]) ** Decimal("2.0") * (line_coords[2]) ** Decimal("2.0")
            - Decimal("2.0") * (line_coords[0]) ** Decimal("3.0") * line_coords[2]
            + (line_coords[0]) ** Decimal("4.0")
            + (line_coords[3]) ** Decimal("2.0") * (line_coords[0]) ** Decimal("2.0")
            - Decimal("2.0")
            * line_coords[1]
            * line_coords[3]
            * (line_coords[0]) ** Decimal("2.0")
            + (line_coords[1]) ** Decimal("2.0") * (line_coords[0]) ** Decimal("2.0")
        )
        result = [a, b, c]
        return result

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

        # Coordinates of the first possible solution for point_a
        x_a1 = (-parameters[1] + Decimal(math.sqrt(sqrt_in))) / (
            Decimal("2.0") * parameters[0]
        )

        y_a1 = (
            x_a1 * line_coords[3]
            - line_coords[0] * line_coords[3]
            - x_a1 * line_coords[1]
            + line_coords[2] * line_coords[1]
        ) / (line_coords[2] - line_coords[0])

        # Coordinates of the second possible solution for point_a
        x_a2 = (-parameters[1] - Decimal(math.sqrt(sqrt_in))) / (
            Decimal("2.0") * parameters[0]
        )

        y_a2 = (
            x_a2 * line_coords[3]
            - line_coords[0] * line_coords[3]
            - x_a2 * line_coords[1]
            + line_coords[2] * line_coords[1]
        ) / (line_coords[2] - line_coords[0])

        bound_x = sorted([line_coords[0], line_coords[2]])
        bound_y = sorted([line_coords[1], line_coords[3]])

        # Select the correct solution point (the one existing
        # at the property boundary line selected by the user)
        if (
            x_a1 > bound_x[0]
            and x_a1 < bound_x[1]
            and y_a1 > bound_y[0]
            and y_a1 < bound_y[1]
        ):
            x_a = x_a1
            y_a = y_a1
        else:
            x_a = x_a2
            y_a = y_a2

        point_a_res = [x_a, y_a]

        return point_a_res

    def _locate_point_b(
        self, line_coords: List[Decimal], point_a: List[Decimal]
    ) -> List[Decimal]:
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

        # Coordinates of the first possible solution point
        x_b1 = (
            line_coords[3]
            * b_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            - line_coords[1]
            * b_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            - b2 * y_a * line_coords[3]
            + b2 * y_a * line_coords[1]
            - b2 * x_a * line_coords[2]
            + b2 * x_a * line_coords[0]
            - c2 * line_coords[3]
            + c2 * line_coords[1]
        ) / (
            a2 * line_coords[3]
            - a2 * line_coords[1]
            - b2 * line_coords[2]
            + b2 * line_coords[0]
        )

        y_b1 = (
            y_a * line_coords[3]
            - y_a * line_coords[1]
            - Decimal(x_b1) * line_coords[2]
            + Decimal(x_b1) * line_coords[0]
            + x_a * line_coords[2]
            - x_a * line_coords[0]
        ) / (line_coords[3] - line_coords[1])

        # Coordinates of the second possible solution point
        x_b2 = (
            -line_coords[3]
            * b_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            + line_coords[1]
            * b_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            - b2 * y_a * line_coords[3]
            + b2 * y_a * line_coords[1]
            - b2 * x_a * line_coords[2]
            + b2 * x_a * line_coords[0]
            - c2 * line_coords[3]
            + c2 * line_coords[1]
        ) / (
            a2 * line_coords[3]
            - a2 * line_coords[1]
            - b2 * line_coords[2]
            + b2 * line_coords[0]
        )

        y_b2 = (
            y_a * line_coords[3]
            - y_a * line_coords[1]
            - Decimal(x_b2) * line_coords[2]
            + Decimal(x_b2) * line_coords[0]
            + x_a * line_coords[2]
            - x_a * line_coords[0]
        ) / (line_coords[3] - line_coords[1])

        # Check that the solution points lie in the
        # map canvas extent
        extent = iface.mapCanvas().extent()

        if (
            x_b1 < extent.xMinimum()
            or x_b1 > extent.xMaximum()
            or y_b1 < extent.yMinimum()
            or y_b1 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Point B opt 1 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return []

        if (
            x_b2 < extent.xMinimum()
            or x_b2 > extent.xMaximum()
            or y_b2 < extent.yMinimum()
            or y_b2 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Point B opt 2 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return []

        points_b_res = [x_b1, y_b1, x_b2, y_b2]

        return points_b_res

    def _locate_point_c(
        self, c_measure: Decimal, point_a: List[Decimal], point_b: List[Decimal]
    ) -> List[Decimal]:
        """Determine the coordinates of corner point 2."""

        a = Decimal("1.0") + (
            (point_b[1] - point_a[1]) / (point_b[0] - point_a[0])
        ) ** Decimal("2.0")
        b = (
            -Decimal("2.0") * point_b[0]
            - Decimal("2.0")
            * point_a[0]
            * ((point_b[1] - point_a[1]) / (point_b[0] - point_a[0])) ** Decimal("2.0")
            + Decimal("2.0")
            * ((point_b[1] - point_a[1]) / (point_b[0] - point_a[0]))
            * (point_a[1] - point_b[1])
        )
        c = (
            -(c_measure ** Decimal("2.0"))
            + (point_a[1] - point_b[1]) ** Decimal("2.0")
            - Decimal("2.0")
            * ((point_b[1] - point_a[1]) / (point_b[0] - point_a[0]))
            * (point_a[1] - point_b[1])
            * point_a[0]
            + point_b[0] ** Decimal("2.0")
            + point_a[0] ** Decimal("2.0")
            * ((point_b[1] - point_a[1]) / (point_b[0] - point_a[0])) ** Decimal("2.0")
        )

        # Check that the solution exists
        sqrt_in = b ** Decimal("2.0") - Decimal("4.0") * a * c
        if sqrt_in < 0.0 or a == 0.0:
            LOGGER.warning(
                tr("Solution point does not exist!"),
                extra={"details": ""},
            )
            return []

        # Computing the possible coordinates for corner point 2
        x_c1 = (-b + Decimal(math.sqrt(sqrt_in))) / (Decimal("2.0") * a)

        y_c1 = ((point_b[1] - point_a[1]) / (point_b[0] - point_a[0])) * (
            x_c1 - point_a[0]
        ) + point_a[1]

        # Computing the possible coordinates for corner point 2
        x_c2 = (-b - Decimal(math.sqrt(sqrt_in))) / (Decimal("2.0") * a)

        y_c2 = ((point_b[1] - point_a[1]) / (point_b[0] - point_a[0])) * (
            x_c2 - point_a[0]
        ) + point_a[1]

        # Let's find out which solution point has more distance to
        # point_b. Assumption: the corner point located via a and b
        # measures will be the closest to the boundary line
        d1 = math.sqrt(
            (x_c1 - point_a[0]) ** Decimal("2.0")
            + (y_c1 - point_a[1]) ** Decimal("2.0")
        )
        d2 = math.sqrt(
            (x_c2 - point_a[0]) ** Decimal("2.0")
            + (y_c2 - point_a[1]) ** Decimal("2.0")
        )

        if d1 < d2:
            point_c_res = [x_c2, y_c2]
        else:
            point_c_res = [x_c1, y_c1]

        return point_c_res

    def _locate_point_d(
        self, d_measure: Decimal, corners: List[List[Decimal]]
    ) -> List[Decimal]:
        """Determine the coordinates of the corner point belonging to the line
        which is orthogonal to the line determined by two latest corner points."""

        point1 = corners[-2]
        point2 = corners[-1]

        # Analytical goemetry: two-point form of a line
        a2 = (point2[1] - point1[1]) / (point2[0] - point1[0])
        b2 = Decimal("-1.0")
        c2 = point1[1] - ((point2[1] - point1[1]) / (point2[0] - point1[0])) * point1[0]

        # Coordinates of the first possible solution point
        x_d1 = (
            point2[1]
            * d_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            - point1[1]
            * d_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            - b2 * point2[1] * point2[1]
            + b2 * point2[1] * point1[1]
            - b2 * point2[0] ** Decimal("2.0")
            + b2 * point2[0] * point1[0]
            - c2 * point2[1]
            + c2 * point1[1]
        ) / (a2 * point2[1] - a2 * point1[1] - b2 * point2[0] + b2 * point1[0])

        y_d1 = (
            point2[1] ** Decimal("2.0")
            - point2[1] * point1[1]
            - Decimal(x_d1) * point2[0]
            + Decimal(x_d1) * point1[0]
            + point2[0] ** Decimal("2.0")
            - point2[0] * point1[0]
        ) / (point2[1] - point1[1])

        # Coordinates of the second possible solution point
        x_d2 = (
            -point2[1]
            * d_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            + point1[1]
            * d_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            - b2 * point2[1] ** Decimal("2.0")
            + b2 * point2[1] * point1[1]
            - b2 * point2[0] ** Decimal("2.0")
            + b2 * point2[0] * point1[0]
            - c2 * point2[1]
            + c2 * point1[1]
        ) / (a2 * point2[1] - a2 * point1[1] - b2 * point2[0] + b2 * point1[0])

        y_d2 = (
            point2[1] ** Decimal("2.0")
            - point2[1] * point1[1]
            - Decimal(x_d2) * point2[0]
            + Decimal(x_d2) * point1[0]
            + point2[0] ** Decimal("2.0")
            - point2[0] * point1[0]
        ) / (point2[1] - point1[1])

        # Check that the corner points lie in the
        # map canvas extent
        extent = iface.mapCanvas().extent()

        if (
            x_d1 < extent.xMinimum()
            or x_d1 > extent.xMaximum()
            or y_d1 < extent.yMinimum()
            or y_d1 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Solution point 1 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return []

        if (
            x_d2 < extent.xMinimum()
            or x_d2 > extent.xMaximum()
            or y_d2 < extent.yMinimum()
            or y_d2 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Solution point 2 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return []

        points_d_res = [x_d1, y_d1, x_d2, y_d2]

        return points_d_res

    def _add_points(
        self,
        points: List[Decimal],
        corners: List[List[Decimal]],
        options_layer: QgsVectorLayer,
        opt_ids: List[int],
    ) -> None:
        """Triggered when scratch layers need to be generated."""

        point = QgsPointXY(float(points[0]), float(points[1]))
        f1 = QgsFeature()
        f1.setGeometry(QgsGeometry.fromPointXY(point))
        if len(corners) == 0:
            f1.setAttributes(["Point B opt 1"])
        elif len(corners) == 1:
            f1.setAttributes(["Corner 2"])
        else:
            f1.setAttributes(["Corner " + str(len(corners) + 1) + " opt 1"])

        options_layer_dataprovider = options_layer.dataProvider()
        options_layer_dataprovider.addFeature(f1)
        options_layer.updateExtents()
        opt_ids.append(f1.id())

        options_layer.setName(tr("Corner point options"))
        options_layer.renderer().symbol().setSize(2)
        options_layer.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))

        layer_settings = QgsPalLayerSettings()
        text_format = QgsTextFormat()

        text_format.setFont(QFont("FreeMono", 10))
        text_format.setSize(10)

        buffer_settings = QgsTextBufferSettings()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(0.1)
        buffer_settings.setColor(QColor("black"))

        text_format.setBuffer(buffer_settings)
        layer_settings.setFormat(text_format)

        layer_settings.fieldName = "id"

        layer_settings.placement = 0
        layer_settings.dist = 2.0

        layer_settings.enabled = True

        layer_settings = QgsVectorLayerSimpleLabeling(layer_settings)

        options_layer.setLabelsEnabled(True)
        options_layer.setLabeling(layer_settings)
        options_layer.triggerRepaint()

        if len(points) > 2:
            point2 = QgsPointXY(float(points[2]), float(points[3]))
            f2 = QgsFeature()
            f2.setGeometry(QgsGeometry.fromPointXY(point2))
            if len(corners) == 0:
                f2.setAttributes(["Point B opt 2"])
            else:
                f2.setAttributes(["Corner " + str(len(corners) + 1) + " opt 2"])
            options_layer_dataprovider.addFeature(f2)
            options_layer.updateExtents()
            opt_ids.append(f2.id())
