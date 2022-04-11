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
        selected_line_coords = self._get_selected_line_coords(event)
        if not selected_line_coords:
            return

        # Determine parameter values for solving the quadratic equation in hand
        parameters = self._calculate_parameters(selected_line_coords)

        try:
            point_a = self._locate_point_a(selected_line_coords, parameters)
            points_b = self._locate_point_b(selected_line_coords, point_a)
        except IndexError:
            return  # Ensure some error msg is displayed to user by locate_point methods

        option_points_layer = self._create_optional_points_layer()
        QgsProject.instance().addMapLayer(option_points_layer)
        # TODO: consider replacing with List[QgsPointXY] or list of tuples
        # selected_corners: List[List[Decimal]] = []

        option_points_layer.startEditing()
        option_point_ids = self._add_option_points_to_layer(
            points_b, option_points_layer
        )

        message_box = self._generate_option_point_messagebox(1)
        ret = message_box.exec()
        if ret == QMessageBox.Yes:
            selected_corners = [[points_b[0], points_b[1]]]
            option_points_to_delete = [option_point_ids[1]]
        else:
            selected_corners = [[points_b[2], points_b[3]]]
            option_points_to_delete = [option_point_ids[0]]

        point_b = selected_corners[0]
        # c_measures are given in crs units (meters for EPSG: 3067)
        c_measures = [
            Decimal(measure.strip()) for measure in self.ui.get_c_measures().split(",")
        ]

        for i, c_measure in enumerate(c_measures):  # TODO: refactor loop
            if i == 0:
                # Map the second corner point which will be located in the extension
                # of the line feature connecting point_a and point_b
                point_c = self._locate_point_c(c_measure, point_a, point_b)
                option_point_ids += self._add_option_points_to_layer(
                    point_c, option_points_layer, selected_corners
                )
                selected_corners.append([point_c[0], point_c[1]])
                continue

            # TODO: don't ask for corner #5, instead automatically close rectangle

            # Map the rest of the rectangular corner points (they will be located
            # perpendicularly with respect to the line feature connecting two last
            # elements of the selected corners list)
            new_corner_points = self._locate_point_d(c_measure, selected_corners)
            option_point_ids += self._add_option_points_to_layer(
                new_corner_points, option_points_layer, selected_corners
            )

            message_box = self._generate_option_point_messagebox(
                len(selected_corners) + 1
            )
            ret = message_box.exec()
            if ret == QMessageBox.No:
                # Check if point already in selected corners list (avoid duplicates)
                if [new_corner_points[2], new_corner_points[3]] not in selected_corners:
                    if i == 1:
                        selected_corners.append(
                            [new_corner_points[2], new_corner_points[3]]
                        )
                        option_points_to_delete.append(option_point_ids[3])
                    else:
                        selected_corners.append(
                            [new_corner_points[2], new_corner_points[3]]
                        )
                        option_points_to_delete.append(
                            option_point_ids[2 + (i * 2 - 1)]
                        )

            else:
                if [new_corner_points[0], new_corner_points[1]] not in selected_corners:
                    if i == 1:
                        selected_corners.append(
                            [new_corner_points[0], new_corner_points[1]]
                        )
                        option_points_to_delete.append(option_point_ids[4])
                    else:
                        selected_corners.append(
                            [new_corner_points[0], new_corner_points[1]]
                        )
                        option_points_to_delete.append(option_point_ids[2 + (i * 2)])

        option_points_layer.deleteFeatures(option_points_to_delete)
        option_points_layer.commitChanges()
        iface.vectorLayerTools().stopEditing(option_points_layer)

        self._write_output_to_file(option_points_layer)

    def _get_selected_line_coords(self, event: QgsMapToolEmitPoint) -> List[Decimal]:
        if self.iface.activeLayer() != self.layer:
            LOGGER.warning(tr("Please select a line layer"), extra={"details": ""})
            return []

        if not QgsWkbTypes.isSingleType(
            list(self.iface.activeLayer().getFeatures())[0].geometry().wkbType()
        ):
            LOGGER.warning(
                tr(
                    "Please select a line layer with "
                    "LineString geometries (instead "
                    "of MultiLineString geometries)"
                ),
                extra={"details": ""},
            )
            return []

        if len(self.iface.activeLayer().selectedFeatures()) != 1:
            LOGGER.warning(
                tr("Please select exactly one line feature"), extra={"details": ""}
            )
            return []

        # Snap the click to the closest point feature available and get
        # the coordinates of the property boundary line's end point we
        # wish to measure the distance from
        start_point = ClickTool(self.iface).activate(event)
        selected_line_geometry = (
            self.iface.activeLayer().selectedFeatures()[0].geometry().asPolyline()
        )

        # Checks that the coordinate values get stored in the correct order
        # TODO: replace direct coordinate comparisons with QgsGeometry.overlaps()
        if Decimal(QgsPointXY(selected_line_geometry[0]).x()) == start_point[0]:
            point1 = QgsPointXY(selected_line_geometry[0])
            point2 = QgsPointXY(selected_line_geometry[-1])
        elif Decimal(QgsPointXY(selected_line_geometry[-1]).x()) == start_point[0]:
            point1 = QgsPointXY(selected_line_geometry[-1])
            point2 = QgsPointXY(selected_line_geometry[0])
        else:
            LOGGER.warning(
                tr(
                    "Please select start or end point of the "
                    "selected property boundary line."
                ),
                extra={"details": ""},
            )
            return []

        # TODO: consider using two QgsPointXY instead of list of coordinates
        line_coords = [
            Decimal(point1.x()),
            Decimal(point1.y()),
            Decimal(point2.x()),
            Decimal(point2.y()),
        ]
        return line_coords

    def _calculate_parameters(self, line_coords: List[Decimal]) -> List[Decimal]:
        """Calculate values for a, b and c parameters."""
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

    @staticmethod
    def _locate_point_a(
        line_coords: List[Decimal], parameters: List[Decimal]
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
        if bound_x[0] < x_a1 < bound_x[1] and bound_y[0] < y_a1 < bound_y[1]:
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

    def _create_optional_points_layer(self) -> QgsVectorLayer:
        """Creates a QgsVectorLayer for storing optional points."""
        layer = QgsVectorLayer("Point", "temp", "memory")
        crs = self.layer.crs()
        layer.setCrs(crs)
        options_layer_dataprovider = layer.dataProvider()
        options_layer_dataprovider.addAttributes([QgsField("id", QVariant.String)])
        layer.updateFields()
        layer.setName(tr("Corner point options"))
        layer.renderer().symbol().setSize(2)
        layer.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))
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
        layer.setLabelsEnabled(True)
        layer.setLabeling(layer_settings)
        return layer

    @staticmethod
    def _add_option_points_to_layer(
        point_coordinates: List[Decimal],
        options_layer: QgsVectorLayer,
        selected_corners: List[List[Decimal]] = None,
    ) -> List[int]:
        """Adds new option points to option point layer,
        returns list of IDs of added features."""
        if not selected_corners:
            selected_corners = []

        point_geometries: List[QgsPointXY] = []
        point_ids: List[int] = []
        coordinates_iterator = iter(point_coordinates)
        for coordinate in coordinates_iterator:
            point_geometries.append(
                QgsPointXY(float(coordinate), float(next(coordinates_iterator)))
            )

        for i, point in enumerate(point_geometries):
            point_feature = QgsFeature()
            point_feature.setGeometry(QgsGeometry.fromPointXY(point))

            if len(selected_corners) == 0:
                point_feature.setAttributes([f"Point B opt {i + 1}"])
            elif len(selected_corners) == 1:
                point_feature.setAttributes(["Corner 2"])
            else:
                point_feature.setAttributes(
                    [f"Corner {len(selected_corners) + 1} opt {i + 1}"]
                )

            options_layer.addFeature(point_feature)
            point_ids.append(point_feature.id())

        options_layer.updateExtents()
        options_layer.triggerRepaint()
        return point_ids

    @staticmethod
    def _generate_option_point_messagebox(corner_point_idx: int) -> QMessageBox:
        message_box = QMessageBox()
        message_box.setText(
            tr(f"Do you want to choose option 1 for corner point {corner_point_idx}?")
        )
        message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        return message_box

    def _write_output_to_file(self, layer: QgsVectorLayer) -> None:
        output_file_path = self.ui.get_output_file_path()
        writer_options = QgsVectorFileWriter.SaveVectorOptions()
        writer_options.actionOnExistingFile = QgsVectorFileWriter.AppendToLayerAddFields
        error, explanation = QgsVectorFileWriter.writeAsVectorFormatV2(
            layer,
            output_file_path,
            QgsProject.instance().transformContext(),
            writer_options,
        )

        if error:
            LOGGER.warning(
                tr(f"Error writing output to file, error code {error}"),
                extra={"details": tr(f"Details: {explanation}")},
            )

    @staticmethod
    def _locate_point_c(
        c_measure: Decimal, point_a: List[Decimal], point_b: List[Decimal]
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

    @staticmethod
    def _locate_point_d(
        d_measure: Decimal, selected_corners: List[List[Decimal]]
    ) -> List[Decimal]:
        """Determine the coordinates of the corner point belonging to the line
        which is orthogonal to the line determined by two latest corner points."""

        point1 = selected_corners[-2]
        point2 = selected_corners[-1]

        # Analytical geometry: two-point form of a line
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
