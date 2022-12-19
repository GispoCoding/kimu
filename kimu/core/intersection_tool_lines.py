from typing import List, Tuple

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.utils import iface

from ..qgis_plugin_tools.tools.i18n import tr
from ..ui.intersect_lines_dialog import IntersectLinesDialog
from .tool_functions import (
    check_within_canvas,
    construct_geodetic_objects_from_selections,
    create_intersecting_object_pairs,
    log_warning,
    select_intersection_point,
    set_and_format_labels,
    solve_all_intersections,
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
            if not (isinstance(layer, QgsVectorLayer) and layer.isSpatial()):
                continue

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

    def _create_result_layer(self) -> QgsVectorLayer:
        result_layer = QgsVectorLayer("Point", "temp", "memory")
        result_layer.setCrs(self.crs)
        result_layer.dataProvider().addAttributes([QgsField("id", QVariant.String)])
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
        point_feature.setAttributes([id])
        layer.dataProvider().addFeature(point_feature)
        layer.updateExtents()
        return point_feature

    def add_all_points(
        self, coords: List[Tuple[float, float]], result_layer: QgsVectorLayer
    ) -> List[QgsFeature]:
        if len(coords) == 1:
            point = self._add_point_to_layer(
                result_layer, coords[0], "Intersection point"
            )
            return [point]
        else:
            point_features = []
            for i, coord in enumerate(coords):
                point = self._add_point_to_layer(result_layer, coord, f"Opt {i+1}")
                point_features.append(point)
            return point_features

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
        if not self._run_initial_checks():
            return

        old_active_layer = iface.activeLayer()
        selected_geodetic_objects = construct_geodetic_objects_from_selections()
        pairs = create_intersecting_object_pairs(selected_geodetic_objects)
        all_i_coords = solve_all_intersections(pairs)
        if len(all_i_coords) == 0:
            log_warning("No intersection points!")
            return

        coords_in_extent = [
            coords for coords in all_i_coords if check_within_canvas(coords)
        ]
        if len(coords_in_extent) == 0:
            log_warning(
                "All potential intersection points lie outside of the map canvas!"
            )
            return

        result_layer = self._create_result_layer()
        added_points = self.add_all_points(coords_in_extent, result_layer)
        set_and_format_labels(result_layer)
        if len(added_points) > 1:
            select_intersection_point(result_layer, len(added_points))

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
