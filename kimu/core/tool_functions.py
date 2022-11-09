from decimal import Decimal
from typing import List, Tuple

from qgis.core import (
    QgsPointXY,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.utils import iface

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name

LOGGER = setup_logger(plugin_name())


class LineCoordinates:
    def __init__(self, x1: Decimal, y1: Decimal, x2: Decimal, y2: Decimal) -> None:
        self.x1 = x1
        self.x2 = x2
        self.y1 = y1
        self.y2 = y2


def check_within_canvas(coords: Tuple[float, float]) -> bool:
    extent = iface.mapCanvas().extent()
    if (
        coords[0] >= extent.xMinimum()
        and coords[0] <= extent.xMaximum()
        and coords[1] >= extent.yMinimum()
        and coords[1] <= extent.yMaximum()
    ):
        return True
    else:
        return False


def extract_points_and_crs() -> Tuple[List, str]:
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

    # CASE LINE
    if all(
        layer.geometryType() == QgsWkbTypes.LineGeometry for layer in selected_layers
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
        layer.geometryType() == QgsWkbTypes.PointGeometry for layer in selected_layers
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


def write_output_to_file(layer: QgsVectorLayer, output_path: str) -> None:
    """Writes the selected layer to a specified file"""
    writer_options = QgsVectorFileWriter.SaveVectorOptions()
    writer_options.actionOnExistingFile = QgsVectorFileWriter.AppendToLayerAddFields
    # PyQGIS documentation doesnt tell what the last 2 str error outputs should be used for
    error, explanation, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer,
        output_path,
        QgsProject.instance().transformContext(),
        writer_options,
    )

    if error:
        log_warning(
            f"Error writing output to file, error code {error}",
            details=tr(f"Details: {explanation}"),
        )


def log_warning(message: str, details: str = "", duration: int = None) -> None:
    if duration is None:
        LOGGER.warning(
            tr(message),
            extra={
                "details": details,
            },
        )
    else:
        LOGGER.warning(
            tr(message),
            extra={"details": details, "duration": duration},
        )
