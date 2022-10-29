from decimal import Decimal
from typing import List, Tuple

from qgis.core import QgsPointXY, QgsProject, QgsWkbTypes


class LineCoordinates:
    def __init__(self, x1: Decimal, y1: Decimal, x2: Decimal, y2: Decimal) -> None:
        self.x1 = x1
        self.x2 = x2
        self.y1 = y1
        self.y2 = y2


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
