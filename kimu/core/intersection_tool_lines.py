import decimal
from decimal import Decimal
from typing import List

from qgis import processing
from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
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
        selected_layer = iface.activeLayer()

        if (
            isinstance(selected_layer, QgsVectorLayer)
            and selected_layer.isSpatial()
            and selected_layer.geometryType() == QgsWkbTypes.LineGeometry
        ):
            status = True
        else:
            LOGGER.warning(
                tr("Please select a line layer"),
                extra={"details": ""},
            )
            status = False

        if len(selected_layer.selectedFeatures()) != 2 and status is True:
            LOGGER.warning(
                tr("Please select two line features from same layer"),
                extra={"details": ""},
            )
            status = False

        if (
            QgsWkbTypes.isSingleType(
                list(selected_layer.getFeatures())[0].geometry().wkbType()
            )
            or status is False
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
            status = False

        temp_layer = selected_layer.materialize(
            QgsFeatureRequest().setFilterFids(selected_layer.selectedFeatureIds())
        )
        params1 = {"INPUT": temp_layer, "OUTPUT": "memory:"}
        vertices = processing.run("native:extractvertices", params1)
        vertices_layer = vertices["OUTPUT"]

        if vertices_layer.featureCount() > 4 and status is True:
            LOGGER.warning(
                tr("Please use Explode line(s) tool first!"), extra={"details": ""}
            )
            status = False

        return status

    def _check_not_parallel(self, point_coords: List[Decimal]) -> None:
        """Checks that the selected line features are not parallel."""
        slope1 = (point_coords[3] - point_coords[1]) / (
            point_coords[2] - point_coords[0]
        )
        slope2 = (point_coords[7] - point_coords[5]) / (
            point_coords[6] - point_coords[4]
        )
        if slope1 == slope2:
            LOGGER.warning(
                tr("Lines are parallel; there is no intersection point!"),
                extra={"details": ""},
            )
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
            LOGGER.warning(
                tr("Intersection point lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return  # type: ignore

        return [x, y]

    def run(self) -> None:
        """Main method."""
        self.dlg = IntersectLinesDialog(iface)
        self.dlg.pushButton.clicked.connect(self.select_output_file)
        self.dlg.show()

        # Run the dialog event loop
        result = self.dlg.exec_()

        selected_layer = iface.activeLayer()

        if self._run_initial_checks() is True:
            # See if user wants to save result into a file
            if result:
                line_points = []

                features = selected_layer.selectedFeatures()
                for feat in features:
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

                self._check_not_parallel(line_points)

                coords = self._calculate_coords(line_points)
                layer = QgsVectorLayer("Point", "temp", "memory")
                selected_layer = iface.activeLayer()
                crs = selected_layer.crs()
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
                    LOGGER.warning(
                        tr(f"Error writing output to file, error code {error}"),
                        extra={"details": tr(f"Details: {explanation}")},
                    )
                    return
            else:
                line_points = []

                features = selected_layer.selectedFeatures()
                for feat in features:
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

                self._check_not_parallel(line_points)
                result_layer = QgsVectorLayer("Point", "temp", "memory")
                crs = selected_layer.crs()
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
