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
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QPushButton
from qgis.utils import iface

from ..qgis_plugin_tools.tools.i18n import tr
from ..ui.intersect_lines_dialog import IntersectLinesDialog
from .tool_functions import (
    LineCoordinates,
    check_within_canvas,
    log_warning,
    write_output_to_file,
)


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
            if isinstance(layer, QgsVectorLayer) and layer.isSpatial():
                for feature in layer.selectedFeatures():

                    if layer.geometryType() == QgsWkbTypes.LineGeometry:
                        if QgsWkbTypes.isSingleType(feature.geometry().wkbType()):
                            points_found += 2
                            crs_list.append(layer.crs().toProj())
                        else:
                            log_warning(
                                "Please select line features with LineString \
                                geometries (instead of MultiLineString geometries)"
                            )
                            return False

                    elif layer.geometryType() == QgsWkbTypes.PointGeometry:
                        if QgsWkbTypes.isSingleType(feature.geometry().wkbType()):
                            points_found += 1
                            crs_list.append(layer.crs().toProj())
                        else:
                            log_warning(
                                "Please select point features with Point \
                                geometries (instead of MultiPoint geometries)"
                            )
                            return False

                    else:
                        log_warning(
                            "Please select features only from vector line or point layers"
                        )
                        return False

        if len(set(crs_list)) == 0:
            log_warning("No vector features selected")
            return False
        elif len(set(crs_list)) != 1:
            log_warning("Please select features only from layers with same CRS")
            return False
        elif points_found != 4:
            log_warning(
                "Please select only either: 2 lines, 1 line and 2 points, or 4 points"
            )
            return False
        else:
            crs = QgsCoordinateReferenceSystem()
            crs.createFromProj(crs_list[0])
            self.crs = crs
            # NOTE: We are now allowing lines with > 2 vertices. This might be unwanted.
            # Now the interesecting line is imagined to travel straight from first to
            # last vertex in these cases.
            return True

    def _extract_points(self) -> List:
        # Note that line_points can be either list of 2 LineCoordinates if intersection
        # point is clear, or if 4 separate points were the input line_points is
        # list of 4 QgsPointXY
        line_points = []
        all_layers = QgsProject.instance().mapLayers().values()

        selected_layers = []
        for layer in all_layers:
            if (
                isinstance(layer, QgsVectorLayer)
                and layer.isSpatial()
                and len(layer.selectedFeatures()) > 0
            ):
                selected_layers.append(layer)

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

        return line_points

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
            log_warning("Lines are parallel; there is no intersection point!")
            return False
        return True

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

    def _create_result_layer(self) -> QgsVectorLayer:
        result_layer = QgsVectorLayer("Point", "temp", "memory")
        result_layer.setCrs(self.crs)
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

        message_box = QMessageBox()
        message_box.setText(tr("Which point do you want to select?"))

        button_1 = QPushButton("Opt 1")
        message_box.addButton(button_1, QMessageBox.ActionRole)
        button_1.clicked.connect(lambda: whichbtn(button_1))

        button_2 = QPushButton("Opt 2")
        message_box.addButton(button_2, QMessageBox.ActionRole)
        button_2.clicked.connect(lambda: whichbtn(button_2))

        if len(points) == 3:
            button_3 = QPushButton("Opt 3")
            message_box.addButton(button_3, QMessageBox.ActionRole)
            button_3.clicked.connect(lambda: whichbtn(button_3))

        def whichbtn(button: QPushButton) -> None:
            id = button.text()[-1]
            for feature in layer.getFeatures():
                if feature.id() != int(id):
                    layer.dataProvider().deleteFeatures([feature.id()])

        message_box.exec()

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
            line_points = self._extract_points()

            old_active_layer = iface.activeLayer()

            # CASE multiple potential intersection points
            if isinstance(line_points[0], QgsPointXY):
                all_intersection_coords = self._calculate_multiple_coords(line_points)
                coords_in_extent = [
                    coords
                    for coords in all_intersection_coords
                    if check_within_canvas(coords)
                ]
                if len(coords_in_extent) == 0:
                    log_warning(
                        "All potential intersection points lie outside of the map canvas!"
                    )
                else:
                    result_layer = self._create_result_layer()
                    if len(coords_in_extent) == 1:
                        self._add_point_to_layer(
                            result_layer, coords_in_extent[0], "Intersection point"
                        )
                        excluded_points = len(all_intersection_coords) - len(
                            coords_in_extent
                        )
                        log_warning(
                            f"{excluded_points} \
                            potential intersection points lie outside of the map canvas!"
                        )
                    else:
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
                            log_warning(
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
                if not check_within_canvas(intersection_coords):
                    log_warning("Intersection point lies outside of the map canvas!")
                    return
                result_layer = self._create_result_layer()
                self._add_point_to_layer(
                    result_layer, intersection_coords, "Intersection point"
                )

            result_layer.commitChanges()
            iface.vectorLayerTools().stopEditing(result_layer)

            # Ask if user wants to save to file
            self.dlg = IntersectLinesDialog(iface)
            self.dlg.pushButton.clicked.connect(self.select_output_file)
            self.dlg.show()
            save_to_file = self.dlg.exec_()

            if save_to_file:
                output_path = self.dlg.lineEdit.text()
                if output_path != "":
                    write_output_to_file(result_layer, output_path)
                    QgsProject.instance().removeMapLayer(result_layer.id())
                else:
                    log_warning("Please specify an output path")

            iface.setActiveLayer(old_active_layer)
