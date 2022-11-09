import math
from decimal import Decimal
from typing import List

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMessageBox
from qgis import processing
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgisInterface, QgsMapMouseEvent, QgsMapToolIdentify
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.utils import iface

from ..qgis_plugin_tools.tools.i18n import tr
from ..ui.displacement_dockwidget import DisplacementDockWidget
from .select_tool import SelectTool
from .tool_functions import check_within_canvas, log_warning


class DisplaceLine(SelectTool):
    def __init__(
        self, iface: QgisInterface, dock_widget: DisplacementDockWidget
    ) -> None:
        super().__init__(iface)
        self.ui: DisplacementDockWidget = dock_widget

    def manual_activate(self) -> None:
        """Manually activate tool."""

        self.iface.mapCanvas().setMapTool(self)
        self.action().setChecked(True)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.ui)

    def canvasPressEvent(self, event: QgsMapMouseEvent) -> None:  # noqa: N802
        """Click on the line feature to displace."""

        old_active_layer = iface.activeLayer()

        selected_layer = iface.activeLayer()

        if (
            isinstance(selected_layer, QgsVectorLayer)
            and selected_layer.isSpatial()
            and (selected_layer.geometryType() == QgsWkbTypes.LineGeometry)
        ):
            pass
        else:
            log_warning("Pleaes select a line layer")
            return

        feat = self._identify_and_extract_single_geometry(event)

        if QgsWkbTypes.isSingleType(feat.wkbType()):
            pass
        else:
            log_warning(
                "Please select a line layer with "
                "LineString geometries (instead "
                "of MultiLineString geometries)"
            )
            return

        line_feat = feat.asPolyline()

        start_point = QgsPointXY(line_feat[0])
        end_point = QgsPointXY(line_feat[-1])

        # Determine parameter values for solving the quadratic equation in hand
        selected_line_coords = [
            Decimal(start_point.x()),
            Decimal(start_point.y()),
            Decimal(end_point.x()),
            Decimal(end_point.y()),
        ]

        point1 = [Decimal(start_point.x()), Decimal(start_point.y())]
        point2 = [Decimal(end_point.x()), Decimal(end_point.y())]

        d = Decimal(self.ui.get_displacement())

        new_coord1 = self._calculate_new_coordinates(selected_line_coords, point1, d)
        new_coord2 = self._calculate_new_coordinates(selected_line_coords, point2, d)

        # Check that if d was positive, the y coordinate value of the
        # displaced line's start point is greater than y coordinate value
        # of the original line's start point
        if (new_coord1[1] > start_point.y() and d > 0) or (
            new_coord1[1] == start_point.y()
            and d > 0
            and new_coord1[0] > start_point.x()
        ):
            pass
        else:
            d = Decimal("-1.0") * Decimal(self.ui.get_displacement())
            new_coord1 = self._calculate_new_coordinates(
                selected_line_coords, point1, d
            )
            new_coord2 = self._calculate_new_coordinates(
                selected_line_coords, point2, d
            )

        # Check that the solution points lie in the
        # map canvas extent
        if not check_within_canvas(
            (new_coord1[0], new_coord1[1])
        ) or not check_within_canvas((new_coord2[0], new_coord2[1])):
            log_warning("Displaced line lies outside of the map canvas!")
            return

        result_layer = self._create_temp_layer([new_coord1, new_coord2])

        message_box = self._generate_question_messagebox()
        ret = message_box.exec()
        if ret == QMessageBox.Yes:
            line_params2 = {
                "INPUT": result_layer,
                "OVERLAY": selected_layer,
                "OUTPUT": "memory:",
            }

            line_result2 = processing.run("native:union", line_params2)
            result_layer2 = line_result2["OUTPUT"]

            line_params3 = {
                "INPUT": result_layer2,
                "OUTPUT": "memory:",
            }

            line_result3 = processing.run("native:explodelines", line_params3)
            result_layer3 = line_result3["OUTPUT"]
            result_layer3.setName(tr("New version of the line layer"))
            result_layer3.renderer().symbol().setWidth(0.7)
            result_layer3.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))
            QgsProject.instance().addMapLayer(result_layer3)
            QgsProject.instance().removeMapLayer(result_layer)

        iface.setActiveLayer(old_active_layer)

    def _identify_and_extract_single_geometry(
        self, event: QgsMapMouseEvent
    ) -> QgsGeometry:
        """Identifies clicked feature and extracts its geometry.
        Returns empty geometry if number of identified features != 1."""

        found_features: List[QgsMapToolIdentify.IdentifyResult] = self.identify(
            event.x(), event.y(), [iface.activeLayer()], QgsMapToolIdentify.ActiveLayer
        )
        if len(found_features) != 1:
            log_warning("Please click on one line feature", duration=1)
            return QgsGeometry()

        geometry: QgsGeometry = found_features[0].mFeature.geometry()

        return geometry

    @staticmethod
    def _calculate_new_coordinates(
        line_coords: List[Decimal], old_point: List[Decimal], d: Decimal
    ) -> List[float]:
        """Calculate new coordinate values for the vertex point of the line to be displaced."""

        a = (line_coords[3] - line_coords[1]) / (line_coords[2] - line_coords[0])
        b = Decimal("-1.0")
        c = line_coords[1] - line_coords[0] * (
            (line_coords[3] - line_coords[1]) / (line_coords[2] - line_coords[0])
        )

        x_new1 = (
            d
            * Decimal(math.sqrt(a ** Decimal("2.0") + b ** Decimal("2.0")))
            * (line_coords[3] - line_coords[1])
            - b * old_point[1] * (line_coords[3] - line_coords[1])
            - b * line_coords[2] * old_point[0]
            + b * line_coords[0] * old_point[0]
            - c * (line_coords[3] - line_coords[1])
        ) / (
            a * (line_coords[3] - line_coords[1])
            + b * (line_coords[0] - line_coords[2])
        )

        y_new1 = (
            ((line_coords[2] - line_coords[0]) * (old_point[0] - x_new1))
            / (line_coords[3] - line_coords[1])
        ) + old_point[1]

        new_coords = [float(x_new1), float(y_new1)]

        return new_coords

    def _create_temp_layer(self, new_points: List[List[float]]) -> QgsVectorLayer:
        """Creates a QgsVectorLayer for displaced line feature."""

        temp_layer = QgsVectorLayer("Point", "temp", "memory")
        crs = iface.activeLayer().crs()
        temp_layer.setCrs(crs)
        temp_layer_dataprovider = temp_layer.dataProvider()
        temp_layer_dataprovider.addAttributes([QgsField("tunniste", QVariant.Int)])
        temp_layer.updateFields()
        point_feature = QgsFeature()
        point_feature.setGeometry(
            QgsGeometry.fromPointXY(QgsPointXY(new_points[0][0], new_points[0][1]))
        )
        point_feature.setAttributes([1])
        point_feature2 = QgsFeature()
        point_feature2.setGeometry(
            QgsGeometry.fromPointXY(QgsPointXY(new_points[1][0], new_points[1][1]))
        )
        point_feature2.setAttributes([2])
        temp_layer_dataprovider.addFeature(point_feature)
        temp_layer_dataprovider.addFeature(point_feature2)
        temp_layer.updateExtents()

        line_params = {
            "INPUT": temp_layer,
            "ORDER_FIELD": "tunniste",
            "OUTPUT": "memory:",
        }

        line_result = processing.run("qgis:pointstopath", line_params)

        result_layer = line_result["OUTPUT"]
        result_layer.setName(tr("Displaced line"))
        result_layer.renderer().symbol().setWidth(0.7)
        result_layer.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))
        QgsProject.instance().addMapLayer(result_layer)

        return result_layer

    @staticmethod
    def _generate_question_messagebox() -> QMessageBox:
        """Creates and returns message box object."""
        message_box = QMessageBox()
        message_box.setText(
            tr(
                "Do you want to create a new combined line layer "
                "with the new displaced line feature?"
            )
        )
        message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        return message_box
