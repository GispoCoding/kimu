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

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name
from ..ui.displacement_dockwidget import DisplacementDockWidget
from .select_tool import SelectTool

LOGGER = setup_logger(plugin_name())


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

    def active_changed(self, layer: QgsVectorLayer) -> None:
        """Triggered when active layer changes."""
        if (
            isinstance(layer, QgsVectorLayer)
            and layer.isSpatial()
            and layer.geometryType() == QgsWkbTypes.LineGeometry
        ):
            self.layer = layer
            self.setLayer(self.layer)

    def canvasPressEvent(self, event: QgsMapMouseEvent) -> None:  # noqa: N802
        """Select the line feature to displace"""
        selected_layer = self.iface.activeLayer()
        if selected_layer != self.layer:
            LOGGER.warning(tr("Please select a line layer"), extra={"details": ""})
            return

        feat = self._identify_and_extract_single_geometry(event)

        if QgsWkbTypes.isSingleType(feat.wkbType()):
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

        new_coord1 = self._calculate_new_coordinates(selected_line_coords, point1)
        new_coord2 = self._calculate_new_coordinates(selected_line_coords, point2)

        # Check that the solution points lie in the
        # map canvas extent
        extent = iface.mapCanvas().extent()

        if (
            new_coord1[0] < extent.xMinimum()
            or new_coord1[0] > extent.xMaximum()
            or new_coord1[1] < extent.yMinimum()
            or new_coord1[1] > extent.yMaximum()
            or new_coord2[0] < extent.xMinimum()
            or new_coord2[0] > extent.xMaximum()
            or new_coord2[1] < extent.yMinimum()
            or new_coord2[1] > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Displaced line lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return

        temp_layer = QgsVectorLayer("Point", "temp", "memory")
        crs = selected_layer.crs()
        temp_layer.setCrs(crs)
        temp_layer_dataprovider = temp_layer.dataProvider()
        temp_layer_dataprovider.addAttributes([QgsField("tunniste", QVariant.Int)])
        temp_layer.updateFields()
        point_feature = QgsFeature()
        point_feature.setGeometry(
            QgsGeometry.fromPointXY(QgsPointXY(new_coord1[0], new_coord1[1]))
        )
        point_feature.setAttributes([1])
        point_feature2 = QgsFeature()
        point_feature2.setGeometry(
            QgsGeometry.fromPointXY(QgsPointXY(new_coord2[0], new_coord2[1]))
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

    def _identify_and_extract_single_geometry(
        self, event: QgsMapMouseEvent
    ) -> QgsGeometry:
        """Identifies clicked feature and extracts its geometry.
        Returns empty geometry if nr. of identified features != 1."""
        found_features: List[QgsMapToolIdentify.IdentifyResult] = self.identify(
            event.x(), event.y(), [self.layer], QgsMapToolIdentify.ActiveLayer
        )
        if len(found_features) != 1:
            LOGGER.info(
                tr("Please select one line"), extra={"details": "", "duration": 1}
            )
            return QgsGeometry()
        self.layer.selectByIds(
            [f.mFeature.id() for f in found_features], QgsVectorLayer.SetSelection
        )
        geometry: QgsGeometry = found_features[0].mFeature.geometry()
        return geometry

    def _calculate_new_coordinates(
        self, line_coords: List[Decimal], old_point: List[Decimal]
    ) -> List[float]:
        """Calculate new coordinates""" ""

        d = Decimal(self.ui.get_displacement())

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

    @staticmethod
    def _generate_question_messagebox() -> QMessageBox:
        message_box = QMessageBox()
        message_box.setText(
            tr(
                "Do you want to create a new combined line layer "
                "with the new displaced line feature?"
            )
        )
        message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        return message_box
