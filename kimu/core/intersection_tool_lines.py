import decimal
from decimal import Decimal
from typing import List, Tuple

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.utils import iface

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name
from ..ui.intersect_lines_dialog import IntersectLinesDialog

LOGGER = setup_logger(plugin_name())


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
                            "Please select a line layer with LineString \
                            geometries (instead of MultiLineString geometries)"
                        )
                        return False

                # elif layer.geometryType() == QgsWkbTypes.PointGeometry:
                #     if QgsWkbTypes.isSingleType(feature.geometry().wkbType()):
                #         points_found += len(selected_layer.selectedFeatures())
                #     else:
                #         self._log_warning("Please select a point layer with Point \
                #             geometries (instead of MultiPoint geometries)")
                #         return False

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
            # Now the interesecting line is imagined to travel straight from first to last
            # vertex in these cases.
            return True

    def _check_not_parallel(self, point_coords: List[Decimal]) -> None:
        """Checks that the selected line features are not parallel."""
        slope1 = (point_coords[3] - point_coords[1]) / (
            point_coords[2] - point_coords[0]
        )
        slope2 = (point_coords[7] - point_coords[5]) / (
            point_coords[6] - point_coords[4]
        )
        if slope1 == slope2:
            self._log_warning("Lines are parallel; there is no intersection point!")
            return

    def _calculate_coords(self, point_coords: List[Decimal]) -> List[float]:
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
                point_coords[0]
                * (
                    (point_coords[3] - point_coords[1])
                    / (point_coords[2] - point_coords[0])
                )
                - point_coords[4]
                * (
                    (point_coords[7] - point_coords[5])
                    / (point_coords[6] - point_coords[4])
                )
                + point_coords[5]
                - point_coords[1]
            )
            / (
                (
                    (point_coords[3] - point_coords[1])
                    / (point_coords[2] - point_coords[0])
                )
                - (
                    (point_coords[7] - point_coords[5])
                    / (point_coords[6] - point_coords[4])
                )
            )
        )
        y = float(
            ((point_coords[3] - point_coords[1]) / (point_coords[2] - point_coords[0]))
            * (decimal.Decimal(x) - point_coords[0])
            + point_coords[1]
        )

        # Check that the result point lies in the map canvas extent
        extent = iface.mapCanvas().extent()
        if (
            x < extent.xMinimum()
            or x > extent.xMaximum()
            or y < extent.yMinimum()
            or y > extent.yMaximum()
        ):
            self._log_warning("Intersection point lies outside of the map canvas!")
            return  # type: ignore

        return [x, y]

    def _extract_points_and_crs(self) -> Tuple[List, str]:
        line_points = []
        all_layers = QgsProject.instance().mapLayers().values()
        crs_id = ""
        for layer in all_layers:
            for feat in layer.selectedFeatures():
                crs_id = layer.crs().srsid()
                line_feat = feat.geometry().asPolyline()
                start_point = QgsPointXY(line_feat[0])
                end_point = QgsPointXY(line_feat[-1])
                line_points.extend(
                    [
                        decimal.Decimal(start_point.x()),
                        decimal.Decimal(start_point.y()),
                        decimal.Decimal(end_point.x()),
                        decimal.Decimal(end_point.y()),
                    ]
                )
        return line_points, crs_id

    def run(self) -> None:
        """Main method."""
        if self._run_initial_checks() is True:
            line_points, crs_id = self._extract_points_and_crs()
            crs = QgsCoordinateReferenceSystem()
            crs.createFromId(crs_id)
            self._check_not_parallel(line_points)

            self.dlg = IntersectLinesDialog(iface)
            self.dlg.pushButton.clicked.connect(self.select_output_file)
            self.dlg.show()
            result = self.dlg.exec_()
            # See if user wants to save result into a file
            if result:
                coords = self._calculate_coords(line_points)
                layer = QgsVectorLayer("Point", "temp", "memory")
                layer.setCrs(crs)
                options_layer_dataprovider = layer.dataProvider()
                options_layer_dataprovider.addAttributes(
                    [
                        QgsField("xcoord", QVariant.Double),
                        QgsField("ycoord", QVariant.Double),
                    ]
                )
                layer.updateFields()
                layer.startEditing()

                point = QgsPointXY(float(coords[0]), float(coords[1]))
                point_feature = QgsFeature()
                point_feature.setGeometry(QgsGeometry.fromPointXY(point))
                point_feature.setAttributes([round(coords[0], 3), round(coords[1], 3)])
                layer.addFeature(point_feature)

                layer.updateExtents()
                layer.triggerRepaint()
                layer.commitChanges()
                iface.vectorLayerTools().stopEditing(layer)

                filename = self.dlg.lineEdit.text()
                writer_options = QgsVectorFileWriter.SaveVectorOptions()
                writer_options.actionOnExistingFile = (
                    QgsVectorFileWriter.AppendToLayerAddFields
                )
                error, explanation = QgsVectorFileWriter.writeAsVectorFormatV2(
                    layer,
                    filename,
                    QgsProject.instance().transformContext(),
                    writer_options,
                )

                if error:
                    self._log_warning(
                        f"Error writing output to file, error code {error}",
                        tr(f"Details: {explanation}"),
                    )
                    return
            else:
                result_layer = QgsVectorLayer("Point", "temp", "memory")
                result_layer.setCrs(crs)
                result_layer_dataprovider = result_layer.dataProvider()
                result_layer_dataprovider.addAttributes(
                    [
                        QgsField("xcoord", QVariant.Double),
                        QgsField("ycoord", QVariant.Double),
                    ]
                )
                result_layer.updateFields()
                intersection_coords = self._calculate_coords(line_points)
                intersection_point = QgsPointXY(
                    intersection_coords[0], intersection_coords[1]
                )
                f = QgsFeature()
                f.setGeometry(QgsGeometry.fromPointXY(intersection_point))
                f.setAttributes(
                    [round(intersection_coords[0], 3), round(intersection_coords[1], 3)]
                )
                result_layer_dataprovider.addFeature(f)
                result_layer.updateExtents()
                result_layer.setName(tr("Intersection point"))
                result_layer.renderer().symbol().setSize(2)
                result_layer.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))
                QgsProject.instance().addMapLayer(result_layer)

    @staticmethod
    def _log_warning(message: str, details: str = "") -> None:
        LOGGER.warning(
            tr(message),
            extra={"details": details},
        )
