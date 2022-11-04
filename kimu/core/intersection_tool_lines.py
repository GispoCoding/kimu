from decimal import Decimal
from typing import List, Tuple

from qgis.core import (
    QgsCoordinateReferenceSystem,
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
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
from qgis.utils import iface

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name
from ..ui.intersect_lines_dialog import IntersectLinesDialog

LOGGER = setup_logger(plugin_name())


class LineCoordinates:
    def __init__(self, x1: Decimal, y1: Decimal, x2: Decimal, y2: Decimal) -> None:
        self.x1 = x1
        self.x2 = x2
        self.y1 = y1
        self.y2 = y2


class IntersectionLines:
    def select_output_file(self) -> None:
        """Specifies the output file."""
        filename, _filter = QFileDialog.getOpenFileName(
            self.dlg, "Select file to save the intersection point in", "", "*.*"
        )
        self.dlg.lineEdit.setText(filename)

    def _run_initial_checks(self) -> bool:
        """Checks that the selections made are applicable."""
        all_layers = QgsProject.instance().mapLayers().values()

        points_found = 0
        crs_list = []
        # Check for selected features from all layers
        for layer in all_layers:
            for feature in layer.selectedFeatures():

                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    if QgsWkbTypes.isSingleType(feature.geometry().wkbType()):
                        points_found += 2
                        crs_list.append(layer.crs().srsid())
                    else:
                        self._log_warning(
                            "Please select line layers with LineString \
                            geometries (instead of MultiLineString geometries)"
                        )
                        return False

                elif layer.geometryType() == QgsWkbTypes.PointGeometry:
                    if QgsWkbTypes.isSingleType(feature.geometry().wkbType()):
                        points_found += 1
                        crs_list.append(layer.crs().srsid())
                    else:
                        self._log_warning(
                            "Please select point layers with Point \
                            geometries (instead of MultiPoint geometries)"
                        )
                        return False

                else:
                    self._log_warning("Please select only vector line layers")
                    return False

        if len(set(crs_list)) != 1:
            self._log_warning("Please select only layers with same CRS")
            return False
        elif points_found != 4:
            self._log_warning(
                "Please select only either: 2 lines, 1 line and 2 points, or 4 points"
            )
            return False
        else:
            # NOTE: We are now allowing lines with > 2 vertices. This might be unwanted.
            # Now the interesecting line is imagined to travel straight from first to
            # last vertex in these cases.
            return True

    def _extract_points_and_crs(self) -> Tuple[List, str]:
        # Note that line_points can be either list of 2 LineCoordinates if intersection
        # point is clear, or if 4 separate points were the input line_points is
        # list of 4 QgsPointXY
        line_points = []
        all_layers = QgsProject.instance().mapLayers().values()
        crs_id = ""

        selected_layers = []
        for layer in all_layers:
            if len(layer.selectedFeatures()) > 0:
                selected_layers.append(layer)
                crs_id = layer.crs().srsid()

        # CASE ONLY LINES
        if all(
            layer.geometryType() == QgsWkbTypes.LineGeometry
            for layer in selected_layers
        ):
            for layer in selected_layers:
                for feat in layer.selectedFeatures():
                    line_feat = feat.geometry().asPolyline()
                    start_point = QgsPointXY(line_feat[0])
                    end_point = QgsPointXY(line_feat[-1])
                    line_points.append(
                        LineCoordinates(
                            x1=Decimal(start_point.x()),
                            x2=Decimal(end_point.x()),
                            y1=Decimal(start_point.y()),
                            y2=Decimal(end_point.y()),
                        )
                    )

        # CASE ONLY POINTS
        elif all(
            layer.geometryType() == QgsWkbTypes.PointGeometry
            for layer in selected_layers
        ):
            line_points = [
                feat.geometry().asPoint()
                for layer in selected_layers
                for feat in layer.selectedFeatures()
            ]

        # CASE BOTH LINE AND POINTS
        else:
            points = []
            for layer in selected_layers:
                if layer.geometryType() == QgsWkbTypes.LineGeometry:
                    line_feat = layer.selectedFeatures()[0].geometry().asPolyline()
                    start_point = QgsPointXY(line_feat[0])
                    end_point = QgsPointXY(line_feat[-1])
                    line_points.append(
                        LineCoordinates(
                            x1=Decimal(start_point.x()),
                            x2=Decimal(end_point.x()),
                            y1=Decimal(start_point.y()),
                            y2=Decimal(end_point.y()),
                        )
                    )
                else:  # if point layer
                    for feat in layer.selectedFeatures():
                        points.append(feat.geometry().asPoint())

            # Create a line out of the two lone points
            line_points.append(
                LineCoordinates(
                    x1=Decimal(points[0].x()),
                    x2=Decimal(points[1].x()),
                    y1=Decimal(points[0].y()),
                    y2=Decimal(points[1].y()),
                )
            )

        return line_points, crs_id

    def _check_not_parallel(
        self, line1_coords: LineCoordinates, line2_coords: LineCoordinates
    ) -> bool:
        """Checks that the selected line features are not parallel."""
        slope1 = (line1_coords.y2 - line1_coords.y1) / (
            line1_coords.x2 - line1_coords.x1
        )
        slope2 = (line2_coords.y2 - line2_coords.y1) / (
            line2_coords.x2 - line2_coords.x1
        )
        if slope1 == slope2:
            self._log_warning("Lines are parallel; there is no intersection point!")
            return False
        return True

    def _check_outside_canvas(self, coords: Tuple[float, float]) -> bool:
        extent = iface.mapCanvas().extent()
        if (
            coords[0] < extent.xMinimum()
            or coords[0] > extent.xMaximum()
            or coords[1] < extent.yMinimum()
            or coords[1] > extent.yMaximum()
        ):
            return True
        else:
            return False

    def _calculate_coords(
        self, line1_coords: LineCoordinates, line2_coords: LineCoordinates
    ) -> Tuple[float, float]:
        """Finds out the coordinate values of the intersection point."""
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

        x = float(
            (
                line1_coords.x1
                * (
                    (line1_coords.y2 - line1_coords.y1)
                    / (line1_coords.x2 - line1_coords.x1)
                )
                - line2_coords.x1
                * (
                    (line2_coords.y2 - line2_coords.y1)
                    / (line2_coords.x2 - line2_coords.x1)
                )
                + line2_coords.y1
                - line1_coords.y1
            )
            / (
                (
                    (line1_coords.y2 - line1_coords.y1)
                    / (line1_coords.x2 - line1_coords.x1)
                )
                - (
                    (line2_coords.y2 - line2_coords.y1)
                    / (line2_coords.x2 - line2_coords.x1)
                )
            )
        )
        y = float(
            ((line1_coords.y2 - line1_coords.y1) / (line1_coords.x2 - line1_coords.x1))
            * (Decimal(x) - line1_coords.x1)
            + line1_coords.y1
        )

        return x, y

    def _calculate_multiple_coords(self, line_points: List) -> List:
        # Hard coded for now, later this could be cleaned up
        permutations = []

        permutations.append(
            [
                LineCoordinates(
                    x1=Decimal(line_points[0].x()),
                    x2=Decimal(line_points[1].x()),
                    y1=Decimal(line_points[0].y()),
                    y2=Decimal(line_points[1].y()),
                ),
                LineCoordinates(
                    x1=Decimal(line_points[2].x()),
                    x2=Decimal(line_points[3].x()),
                    y1=Decimal(line_points[2].y()),
                    y2=Decimal(line_points[3].y()),
                ),
            ]
        )
        permutations.append(
            [
                LineCoordinates(
                    x1=Decimal(line_points[0].x()),
                    x2=Decimal(line_points[2].x()),
                    y1=Decimal(line_points[0].y()),
                    y2=Decimal(line_points[2].y()),
                ),
                LineCoordinates(
                    x1=Decimal(line_points[1].x()),
                    x2=Decimal(line_points[3].x()),
                    y1=Decimal(line_points[1].y()),
                    y2=Decimal(line_points[3].y()),
                ),
            ]
        )
        permutations.append(
            [
                LineCoordinates(
                    x1=Decimal(line_points[0].x()),
                    x2=Decimal(line_points[3].x()),
                    y1=Decimal(line_points[0].y()),
                    y2=Decimal(line_points[3].y()),
                ),
                LineCoordinates(
                    x1=Decimal(line_points[2].x()),
                    x2=Decimal(line_points[1].x()),
                    y1=Decimal(line_points[2].y()),
                    y2=Decimal(line_points[1].y()),
                ),
            ]
        )

        all_coords = []
        for line_points in permutations:
            if self._check_not_parallel(line_points[0], line_points[1]):
                all_coords.append(
                    self._calculate_coords(line_points[0], line_points[1])
                )

        return all_coords

    def _create_result_layer(self, crs: QgsCoordinateReferenceSystem) -> QgsVectorLayer:
        result_layer = QgsVectorLayer("Point", "temp", "memory")
        result_layer.setCrs(crs)
        result_layer.dataProvider().addAttributes(
            [
                QgsField("id", QVariant.String),
                QgsField("xcoord", QVariant.Double),
                QgsField("ycoord", QVariant.Double),
            ]
        )
        result_layer.updateFields()
        result_layer.setName(tr("Intersection point"))
        result_layer.renderer().symbol().setSize(2)
        result_layer.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))
        QgsProject.instance().addMapLayer(result_layer)
        return result_layer

    def _add_point_to_layer(
        self, layer: QgsVectorLayer, coords: Tuple[float, float], id: str
    ) -> QgsFeature:
        intersection_point = QgsPointXY(coords[0], coords[1])
        point_feature = QgsFeature()
        point_feature.setGeometry(QgsGeometry.fromPointXY(intersection_point))
        point_feature.setAttributes([id, round(coords[0], 3), round(coords[1], 3)])
        layer.dataProvider().addFeature(point_feature)
        layer.updateExtents()
        return point_feature

    def _set_and_format_labels(self, layer: QgsVectorLayer) -> None:
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
        layer.triggerRepaint()

    def _select_intersection_point(self, layer: QgsVectorLayer, points: List) -> None:
        for point in points:
            message_box = QMessageBox()
            message_box.setText(
                tr(
                    f"Do you want to choose option {point[0]} for the intersection point?"
                )
            )
            message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            choice = message_box.exec()
            if choice == QMessageBox.Yes:
                # Remove all other points left
                for feature in layer.getFeatures():
                    if feature.id() != point.id():
                        layer.dataProvider().deleteFeatures([feature.id()])
                break
            else:
                # Remove this point since it was not chosen
                layer.dataProvider().deleteFeatures([point.id()])
                # If only 1 feature left, stop asking
                if len(list(layer.getFeatures())) == 1:
                    break

    def _write_output_to_file(
        self, layer: QgsVectorLayer, output_file_path: str
    ) -> None:
        """Writes the selected corner points to a specified file"""
        output_file_path = self.dlg.lineEdit.text()
        writer_options = QgsVectorFileWriter.SaveVectorOptions()
        writer_options.actionOnExistingFile = QgsVectorFileWriter.AppendToLayerAddFields
        # PyQGIS documentation doesnt tell what the last 2 str error outputs should be used for
        error, explanation, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
            layer,
            output_file_path,
            QgsProject.instance().transformContext(),
            writer_options,
        )

        if error:
            self._log_warning(
                f"Error writing output to file, error code {error}",
                tr(f"Details: {explanation}"),
            )

    def run(self) -> None:
        """Main method.

        The steps:
        1. Run initial checks (Only point and line features selected,
           correct number of features selected, same crs)
        2. Extract points from selection
        3. Calculate intersection coordinates (all possibilities if points were input data)
        4. Check that lines are not parallel
        5. Create result layer
        6. Populate result layer with intersection point(s)
        7. If multiple options, ask user which one to keep one by one and
           delete unselected points
        8. Ask user if layer should be saved to disk. If yes, remove the temporary layer
        """
        if self._run_initial_checks() is True:
            line_points, crs_id = self._extract_points_and_crs()
            crs = QgsCoordinateReferenceSystem()
            crs.createFromId(crs_id)

            # CASE multiple potential intersection points
            if isinstance(line_points[0], QgsPointXY):
                all_intersection_coords = self._calculate_multiple_coords(line_points)
                coords_in_extent = [
                    coords
                    for coords in all_intersection_coords
                    if not self._check_outside_canvas(coords)
                ]
                if len(coords_in_extent) == 0:
                    self._log_warning(
                        "All potential intersection points lie outside of the map canvas!"
                    )
                    return
                elif len(coords_in_extent) == 1:
                    result_layer = self._create_result_layer(crs)
                    self._add_point_to_layer(
                        result_layer, coords_in_extent[0], "Intersection point"
                    )
                    excluded_points = len(all_intersection_coords) - len(
                        coords_in_extent
                    )
                    self._log_warning(
                        f"{excluded_points} \
                        potential intersection points lie outside of the map canvas!"
                    )
                else:
                    result_layer = self._create_result_layer(crs)
                    i = 1
                    point_features = []
                    for coords in coords_in_extent:
                        point = self._add_point_to_layer(
                            result_layer, coords, f"Opt {i}"
                        )
                        point_features.append(point)
                        i += 1
                    excluded_points = len(all_intersection_coords) - len(
                        coords_in_extent
                    )
                    if excluded_points > 0:
                        self._log_warning(
                            f"{excluded_points} \
                            potential intersection points lie outside of the map canvas!"
                        )
                    self._set_and_format_labels(result_layer)
                    self._select_intersection_point(result_layer, point_features)

            # CASE one intersection point
            else:
                if not self._check_not_parallel(line_points[0], line_points[1]):
                    return
                intersection_coords = self._calculate_coords(
                    line_points[0], line_points[1]
                )
                if self._check_outside_canvas(intersection_coords):
                    self._log_warning(
                        "Intersection point lies outside of the map canvas!"
                    )
                    return
                result_layer = self._create_result_layer(crs)
                self._add_point_to_layer(
                    result_layer, intersection_coords, "Intersection point"
                )

            result_layer.commitChanges()
            iface.vectorLayerTools().stopEditing(result_layer)

            # Ask if user wants to save file
            self.dlg = IntersectLinesDialog(iface)
            self.dlg.pushButton.clicked.connect(self.select_output_file)
            self.dlg.show()
            save_to_file = self.dlg.exec_()

            if save_to_file:
                self._write_output_to_file(result_layer, self.dlg.lineEdit.text())
                QgsProject.instance().removeMapLayer(result_layer.id())

    @staticmethod
    def _log_warning(message: str, details: str = "") -> None:
        LOGGER.warning(
            tr(message),
            extra={"details": details},
        )
