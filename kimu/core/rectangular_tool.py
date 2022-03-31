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
from qgis.gui import QgisInterface, QgsMapToolEmitPoint
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
    def __init__(
        self, iface: QgisInterface, dock_widget: RectangularDockWidget
    ) -> None:
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

    # fmt: off
    def canvasPressEvent(  # noqa: N802
        self, event: QgsMapToolEmitPoint
    ) -> None:
        # fmt: on
        """Canvas click event."""
        if self.iface.activeLayer() != self.layer:
            LOGGER.warning(tr("Please select a line layer"),
                           extra={"details": ""})
            return

        if QgsWkbTypes.isSingleType(
            list(
                self.iface.activeLayer().getFeatures()
            )[0].geometry().wkbType()
        ):
            pass
        else:
            LOGGER.warning(
                tr("Please select a line layer with "
                   "LineString geometries (instead "
                   "of MultiLineString geometries)"),
                extra={"details": ""})
            return

        if len(self.iface.activeLayer().selectedFeatures()) != 1:
            LOGGER.warning(tr("Please select only one line"),
                           extra={"details": ""})
            return

        geometry = self.iface.activeLayer().selectedFeatures()[0].geometry()

        # Snap the click to the closest point feature available and get
        # the coordinates of the property boundary line's end point we
        # wish to measure the distance from
        start_point = ClickTool(self.iface).activate(event)

        # Coordinates of the points implicitly defining the property boundary line
        line_feat = geometry.asPolyline()
        # Checks that the coordinate values get stored in the correct order
        if Decimal(QgsPointXY(line_feat[0]).x()) == start_point[0]:
            point1 = QgsPointXY(line_feat[0])
            point2 = QgsPointXY(line_feat[-1])
        elif Decimal(QgsPointXY(line_feat[-1]).x()) == start_point[0]:
            point1 = QgsPointXY(line_feat[-1])
            point2 = QgsPointXY(line_feat[0])
        else:
            LOGGER.warning(tr("Please select start or end point of the "
                              "selected property boundary line"
                              ), extra={"details": ""})
            return

        line_coords = [
            Decimal(point1.x()),
            Decimal(point1.y()),
            Decimal(point2.x()),
            Decimal(point2.y()),
        ]

        # Call the function capable of determining the parameter values
        # for solving the quadratic equation in hand
        parameters = self._calculate_parameters(line_coords)

        # Call for function capable of determining point_a
        point_a = self._locate_point_a(line_coords, parameters)

        # Call for function capable of determining point_b
        points_b = self._locate_point_b(line_coords, point_a)

        corners: List[List[Decimal]]
        corners = []

        polku = self.ui.get_output_file()

        tasotb = self._add_scratch_layers(points_b, corners)
        scratchb1 = tasotb[0]
        scratchb2 = tasotb[1]
        mb = QMessageBox()
        mb.setText(
            'Do you want to choose alternative 1 for corner point '
            + str(len(corners) + 1) + '?'
        )
        mb.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        ret = mb.exec()
        if ret == QMessageBox.No:
            opt = QgsVectorFileWriter.SaveVectorOptions()
            opt.actionOnExistingFile = QgsVectorFileWriter.AppendToLayerAddFields
            QgsVectorFileWriter.writeAsVectorFormat(scratchb2, polku, opt)
            corners.append([points_b[2], points_b[3]])
        elif ret == QMessageBox.Yes:
            opt = QgsVectorFileWriter.SaveVectorOptions()
            opt.actionOnExistingFile = QgsVectorFileWriter.AppendToLayerAddFields
            QgsVectorFileWriter.writeAsVectorFormat(scratchb1, polku, opt)
            corners.append([points_b[0], points_b[1]])
        else:
            LOGGER.warning(
                tr("Ei haluta tänne!"),
                extra={"details": ""},
            )
            return

        # Crashaa, jos uncommentoidaan nämä
        # QgsProject.instance().removeMapLayer(scratchb1.id())
        # QgsProject.instance().removeMapLayer(scratchb2.id())

        point_b: List[Decimal]
        point_b = corners[0]

        # c_measures are given in crs units (meters for EPSG: 3067)
        c_measure_list = self.ui.get_c_measures().split(",")

        if (len(c_measure_list) % 2) != 0:
            LOGGER.warning(
                tr("Please insert even number of c measures!"),
                extra={"details": ""},
            )
            return

        for i in range(len(c_measure_list)):
            # Määritetään toinen nurkkapiste, joka muista poiketen
            # sijaitsee samalla suoralla kuin ensimmäinen nurkkapiste
            c_measure = Decimal(c_measure_list[i])
            if i == 0:
                point_c = self._locate_point_c(c_measure, point_a, point_b)
                tasot = self._add_scratch_layers(point_c, corners)
                scratch1 = tasot[0]
                opt = QgsVectorFileWriter.SaveVectorOptions()
                opt.actionOnExistingFile = QgsVectorFileWriter.AppendToLayerAddFields
                QgsVectorFileWriter.writeAsVectorFormat(scratch1, polku, opt)
                corners.append([point_c[0], point_c[1]])
                # QgsProject.instance().removeMapLayer(scratch1.id())
            # Aika turha funktio, melkein voisi poistaa tämän
            elif i == (len(c_measure_list) - 1):
                self._check_last_point(c_measure, corners)
            else:
                new_corner_points = self._locate_point_d(c_measure, corners)
                tasot = self._add_scratch_layers(new_corner_points, corners)
                scratch1 = tasot[0]
                scratch2 = tasot[1]
                mb = QMessageBox()
                mb.setText(
                    'Do you want to choose alternative 1 for corner point '
                    + str(len(corners) + 1) + '?'
                )
                mb.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                ret = mb.exec()
                if ret == QMessageBox.No:
                    op = QgsVectorFileWriter.SaveVectorOptions()
                    op.actionOnExistingFile = QgsVectorFileWriter.AppendToLayerAddFields
                    QgsVectorFileWriter.writeAsVectorFormat(scratch2, polku, op)
                    corners.append([new_corner_points[2], new_corner_points[3]])
                elif ret == QMessageBox.Yes:
                    op = QgsVectorFileWriter.SaveVectorOptions()
                    op.actionOnExistingFile = QgsVectorFileWriter.AppendToLayerAddFields
                    QgsVectorFileWriter.writeAsVectorFormat(scratch1, polku, op)
                    corners.append([new_corner_points[0], new_corner_points[1]])
                else:
                    LOGGER.warning(
                        tr("Ei haluta tänne!"),
                        extra={"details": ""},
                    )
                    return
                # Crashaa, jos uncommentoidaan nämä
                # QgsProject.instance().removeMapLayer(scratch1.id())
                # QgsProject.instance().removeMapLayer(scratch2.id())

    def _calculate_parameters(
        self, line_coords: List[Decimal]
    ) -> List[Decimal]:
        """Calculate values for a, b and c parameters"""
        # a_measure is given in crs units (meters for EPSG: 3067)
        a_measure = Decimal(self.ui.get_a_measure())
        # LISAA SELITYS!
        a = (
            (line_coords[2]) ** Decimal("2.0")
            - Decimal("2.0") * line_coords[0] * line_coords[2]
            + (line_coords[0]) ** Decimal("2.0")
            + (line_coords[3]) ** Decimal("2.0")
            - Decimal("2.0") * line_coords[1] * line_coords[3]
            + (line_coords[1]) ** Decimal("2.0")
        )
        b = (
            -Decimal("2.0")
            * (line_coords[2]) ** Decimal("2.0")
            * line_coords[0]
            + Decimal("4.0")
            * (line_coords[0]) ** Decimal("2.0")
            * line_coords[2]
            - Decimal("2.0")
            * (line_coords[0]) ** Decimal("3.0")
            - Decimal("2.0")
            * (line_coords[3]) ** Decimal("2.0")
            * line_coords[0]
            + Decimal("4.0")
            * line_coords[0] * line_coords[1]
            * line_coords[3]
            - Decimal("2.0")
            * (line_coords[1]) ** Decimal("2.0")
            * line_coords[0]
        )
        c = (
            - a_measure ** Decimal("2.0")
            * (line_coords[2]) ** Decimal("2.0")
            + Decimal("2.0")
            * a_measure ** Decimal("2.0")
            * line_coords[0]
            * line_coords[2]
            - a_measure ** Decimal("2.0")
            * (line_coords[0]) ** Decimal("2.0")
            + (line_coords[0]) ** Decimal("2.0")
            * (line_coords[2]) ** Decimal("2.0")
            - Decimal("2.0")
            * (line_coords[0]) ** Decimal("3.0")
            * line_coords[2]
            + (line_coords[0]) ** Decimal("4.0")
            + (line_coords[3]) ** Decimal("2.0")
            * (line_coords[0]) ** Decimal("2.0")
            - Decimal("2.0")
            * line_coords[1]
            * line_coords[3]
            * (line_coords[0]) ** Decimal("2.0")
            + (line_coords[1]) ** Decimal("2.0")
            * (line_coords[0]) ** Decimal("2.0")
        )
        result = [a, b, c]
        return result

    def _locate_point_a(
        self, line_coords: List[Decimal], parameters: List[Decimal]
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

        # Computing the possible coordinates for a point
        x_a1 = (
            (-parameters[1] + Decimal(math.sqrt(sqrt_in)))
            / (Decimal("2.0") * parameters[0])
        )

        y_a1 = (
            (
                x_a1 * line_coords[3]
                - line_coords[0] * line_coords[3]
                - x_a1 * line_coords[1]
                + line_coords[2] * line_coords[1]
            ) / (line_coords[2] - line_coords[0])
        )

        x_a2 = (
            (-parameters[1] - Decimal(math.sqrt(sqrt_in)))
            / (Decimal("2.0") * parameters[0])
        )

        y_a2 = (
            (x_a2 * line_coords[3]
             - line_coords[0] * line_coords[3]
             - x_a2 * line_coords[1]
             + line_coords[2] * line_coords[1])
            / (line_coords[2] - line_coords[0])
        )

        bound_x = sorted([line_coords[0], line_coords[2]])
        bound_y = sorted([line_coords[1], line_coords[3]])

        # Select the correct solution point (the one existing
        # at the property boundary line)
        if (
            x_a1 > bound_x[0] and x_a1 < bound_x[1]
            and y_a1 > bound_y[0] and y_a1 < bound_y[1]
        ):
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

        # Coordinates of the first solution point
        x_b1 = (
            (line_coords[3] * b_measure * Decimal(math.sqrt(
                a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
            ))
              - line_coords[1] * b_measure * Decimal(math.sqrt(
                    a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
                )) - b2 * y_a * line_coords[3]
              + b2 * y_a * line_coords[1]
              - b2 * x_a * line_coords[2] + b2 * x_a * line_coords[0]
              - c2 * line_coords[3] + c2 * line_coords[1]
              )
            / (a2 * line_coords[3] - a2 * line_coords[1]
               - b2 * line_coords[2] + b2 * line_coords[0])
        )

        y_b1 = (
            (y_a * line_coords[3] - y_a * line_coords[1]
             - Decimal(x_b1) * line_coords[2]
             + Decimal(x_b1) * line_coords[0]
             + x_a * line_coords[2] - x_a * line_coords[0])
            / (line_coords[3] - line_coords[1])
        )

        # Coordinates of the second solution point
        x_b2 = (
            (-line_coords[3] * b_measure * Decimal(math.sqrt(
                a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
            ))
             + line_coords[1] * b_measure * Decimal(math.sqrt(
                    a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
                )) - b2 * y_a * line_coords[3]
             + b2 * y_a * line_coords[1]
             - b2 * x_a * line_coords[2] + b2 * x_a * line_coords[0]
             - c2 * line_coords[3] + c2 * line_coords[1]
             )
            / (a2 * line_coords[3] - a2 * line_coords[1]
               - b2 * line_coords[2] + b2 * line_coords[0])
        )

        y_b2 = (
            (y_a * line_coords[3] - y_a * line_coords[1]
             - Decimal(x_b2) * line_coords[2]
             + Decimal(x_b2) * line_coords[0]
             + x_a * line_coords[2] - x_a * line_coords[0])
            / (line_coords[3] - line_coords[1])
        )

        # Check that the intersection point(s) lie(s) in the
        # map canvas extent
        extent = iface.mapCanvas().extent()

        if (
            x_b1 < extent.xMinimum()
            or x_b1 > extent.xMaximum()
            or y_b1 < extent.yMinimum()
            or y_b1 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Solution point 1 lies outside of the map canvas!"),
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
                tr("Solution point 2 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return []

        points_b_res = [x_b1, y_b1, x_b2, y_b2]

        return points_b_res

    def _locate_point_c(
        self, c_measure: Decimal, point_a: List[Decimal], point_b: List[Decimal]
    ) -> List[Decimal]:
        """Determine the coordinates of point_c going through
        two points."""

        a = (
            Decimal("1.0")
            + (
                (point_b[1] - point_a[1]) / (point_b[0] - point_a[0])
            ) ** Decimal("2.0")
        )
        b = (
            - Decimal("2.0") * point_b[0]
            - Decimal("2.0") * point_a[0] * (
                (point_b[1] - point_a[1]) / (point_b[0] - point_a[0])
            ) ** Decimal("2.0")
            + Decimal("2.0") * (
                (point_b[1] - point_a[1]) / (point_b[0] - point_a[0])
            ) * (point_a[1] - point_b[1])
        )
        c = (
            - c_measure ** Decimal("2.0") + (point_a[1] - point_b[1]) ** Decimal("2.0")
            - Decimal("2.0") * (
                (point_b[1] - point_a[1]) / (point_b[0] - point_a[0])
            ) * (point_a[1] - point_b[1]) * point_a[0]
            + point_b[0] ** Decimal("2.0")
            + point_a[0] ** Decimal("2.0") * (
                (point_b[1] - point_a[1]) / (point_b[0] - point_a[0])
            ) ** Decimal("2.0")
        )

        # Check that the solution exists
        sqrt_in = (
            b ** Decimal("2.0")
            - Decimal("4.0") * a * c
        )
        if sqrt_in < 0.0 or a == 0.0:
            LOGGER.warning(
                tr("Solution point does not exist!"),
                extra={"details": ""},
            )
            return []

        # Computing the possible coordinates for a point
        x_c1 = (
            (-b + Decimal(math.sqrt(sqrt_in))) / (Decimal("2.0") * a)
        )

        y_c1 = (
            ((point_b[1] - point_a[1]) / (point_b[0] - point_a[0]))
            * (x_c1 - point_a[0]) + point_a[1]
        )

        # Computing the possible coordinates for a point
        x_c2 = (
            (-b - Decimal(math.sqrt(sqrt_in))) / (Decimal("2.0") * a)
        )

        y_c2 = (
            ((point_b[1] - point_a[1]) / (point_b[0] - point_a[0]))
            * (x_c2 - point_a[0]) + point_a[1]
        )

        # Tunnistetaaan kumpi pisteistä on kauempana point_a:sta
        # oletus: a- ja b-mittojen avulla on paikannettu kiinteistörajaa
        # lähimpänä sijaitseva nurkkapiste
        d1 = (
            math.sqrt((x_c1-point_a[0]) ** Decimal("2.0")
                      + (y_c1-point_a[1]) ** Decimal("2.0"))
        )
        d2 = (
            math.sqrt((x_c2 - point_a[0]) ** Decimal("2.0")
                      + (y_c2 - point_a[1]) ** Decimal("2.0"))
        )

        if d1 < d2:
            point_c_res = [x_c2, y_c2]
        else:
            point_c_res = [x_c1, y_c1]

        return point_c_res

    def _locate_point_d(
        self, d_measure: Decimal, corners: List[List[Decimal]]
    ) -> List[Decimal]:
        """Determine the coordinates of the point belonging to the line which is
        orthogonal to the line determined by two latest corner points."""

        point1 = corners[-2]
        point2 = corners[-1]

        # Suoran yhtälö kahden pisteen kautta
        a2 = (point2[1] - point1[1]) / (point2[0] - point1[0])
        b2 = Decimal("-1.0")
        c2 = point1[1] - ((point2[1] - point1[1]) / (point2[0] - point1[0])) * point1[0]

        # Coordinates of the first solution point
        x_d1 = (
            (point2[1] * d_measure * Decimal(math.sqrt(
                a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
            ))
              - point1[1] * d_measure * Decimal(math.sqrt(
                    a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
                )) - b2 * point2[1] * point2[1]
              + b2 * point2[1] * point1[1]
              - b2 * point2[0] ** Decimal("2.0") + b2 * point2[0] * point1[0]
              - c2 * point2[1] + c2 * point1[1]
              )
            / (a2 * point2[1] - a2 * point1[1]
               - b2 * point2[0] + b2 * point1[0])
        )

        y_d1 = (
            (point2[1] ** Decimal("2.0") - point2[1] * point1[1]
             - Decimal(x_d1) * point2[0]
             + Decimal(x_d1) * point1[0]
             + point2[0] ** Decimal("2.0") - point2[0] * point1[0])
            / (point2[1] - point1[1])
        )

        # Coordinates of the second solution point
        x_d2 = (
            (-point2[1] * d_measure * Decimal(math.sqrt(
                a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
            ))
             + point1[1] * d_measure * Decimal(math.sqrt(
                    a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
                )) - b2 * point2[1] ** Decimal("2.0")
             + b2 * point2[1] * point1[1]
             - b2 * point2[0] ** Decimal("2.0") + b2 * point2[0] * point1[0]
             - c2 * point2[1] + c2 * point1[1]
             )
            / (a2 * point2[1] - a2 * point1[1]
               - b2 * point2[0] + b2 * point1[0])
        )

        y_d2 = (
            (point2[1] ** Decimal("2.0") - point2[1] * point1[1]
             - Decimal(x_d2) * point2[0]
             + Decimal(x_d2) * point1[0]
             + point2[0] ** Decimal("2.0") - point2[0] * point1[0])
            / (point2[1] - point1[1])
        )

        # Check that the intersection point(s) lie(s) in the
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

    def _check_last_point(
        self, last_measure: Decimal, corners: List[List[Decimal]]
    ) -> None:
        """Check that by moving the last disctance orthogonally we end up into the
        point_b (should be first element on corners list)."""

        point1 = corners[-2]
        point2 = corners[-1]

        # Suoran yhtälö kahden pisteen kautta
        a2 = (point2[1] - point1[1]) / (point2[0] - point1[0])
        b2 = Decimal("-1.0")
        c2 = point1[1] - ((point2[1] - point1[1]) / (point2[0] - point1[0])) * point1[0]

        # Coordinates of the first solution point
        x_last1 = (
            (point2[1] * last_measure * Decimal(math.sqrt(
                a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
            ))
              - point1[1] * last_measure * Decimal(math.sqrt(
                    a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
                )) - b2 * point2[1] * point2[1]
              + b2 * point2[1] * point1[1]
              - b2 * point2[0] ** Decimal("2.0") + b2 * point2[0] * point1[0]
              - c2 * point2[1] + c2 * point1[1]
              )
            / (a2 * point2[1] - a2 * point1[1]
               - b2 * point2[0] + b2 * point1[0])
        )

        y_last1 = (
            (point2[1] ** Decimal("2.0") - point2[1] * point1[1]
             - Decimal(x_last1) * point2[0]
             + Decimal(x_last1) * point1[0]
             + point2[0] ** Decimal("2.0") - point2[0] * point1[0])
            / (point2[1] - point1[1])
        )

        # Coordinates of the second solution point
        x_last2 = (
            (-point2[1] * last_measure * Decimal(math.sqrt(
                a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
            ))
             + point1[1] * last_measure * Decimal(math.sqrt(
                    a2 ** Decimal("2.0") + b2 ** Decimal("2.0")
                )) - b2 * point2[1] ** Decimal("2.0")
             + b2 * point2[1] * point1[1]
             - b2 * point2[0] ** Decimal("2.0") + b2 * point2[0] * point1[0]
             - c2 * point2[1] + c2 * point1[1]
             )
            / (a2 * point2[1] - a2 * point1[1]
               - b2 * point2[0] + b2 * point1[0])
        )

        y_last2 = (
            (point2[1] ** Decimal("2.0") - point2[1] * point1[1]
             - Decimal(x_last2) * point2[0]
             + Decimal(x_last2) * point1[0]
             + point2[0] ** Decimal("2.0") - point2[0] * point1[0])
            / (point2[1] - point1[1])
        )

        # Check that the intersection point(s) lie(s) in the
        # map canvas extent
        extent = iface.mapCanvas().extent()

        if (
            x_last1 < extent.xMinimum()
            or x_last1 > extent.xMaximum()
            or y_last1 < extent.yMinimum()
            or y_last1 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Solution point 1 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return

        if (
            x_last2 < extent.xMinimum()
            or x_last2 > extent.xMaximum()
            or y_last2 < extent.yMinimum()
            or y_last2 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Solution point 2 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return

        # Huomaa, että viimeisellä etäisyydellä ei ole mitään väliä,
        # sillä sen mukaista pistettä ei ikinä piirretä kartalle!
        # Oletetaan, että viimeinen syötetty sivun pituus matchaa tarpeisiin
        if (
            (int(x_last1) != int(corners[0][0]) and int(x_last2) != int(corners[0][0]))
            or
            (int(y_last1) != int(corners[0][1]) and int(y_last2) != int(corners[0][1]))
        ):
            LOGGER.warning(
                tr("Rectangular mapping failed!"),
                extra={"details": ""},
            )
            return

        return

    def _add_scratch_layers(
        self,
        points: List[Decimal], corners: List[List[Decimal]]
    ) -> List[QgsVectorLayer]:
        """Triggered when result layer needs to be generated."""
        scratch_layer1 = QgsVectorLayer("Point", "temp", "memory")
        crs = self.layer.crs()
        scratch_layer1.setCrs(crs)
        scratch_layer1_dataprovider = scratch_layer1.dataProvider()
        scratch_layer1_dataprovider.addAttributes(
            [QgsField("id", QVariant.String), QgsField("xcoord", QVariant.Double)]
        )
        scratch_layer1.updateFields()

        point = QgsPointXY(float(points[0]), float(points[1]))
        f1 = QgsFeature()
        f1.setGeometry(QgsGeometry.fromPointXY(point))
        if len(corners) == 0:
            f1.setAttributes(['B1', 111.5])
        elif len(corners) == 1:
            f1.setAttributes(['Corner 2', 111.5])
        else:
            f1.setAttributes(['Corner ' + str(len(corners)+1) + ' V1', 111.5])
        scratch_layer1_dataprovider.addFeature(f1)
        scratch_layer1.updateExtents()

        if len(corners) == 0:
            scratch_layer1.setName(tr("B point alternative 1"))
        elif len(corners) == 1:
            scratch_layer1.setName(tr("Corner point 2"))
        else:
            scratch_layer1.setName(tr("Point alternative 1"))
        scratch_layer1.renderer().symbol().setSize(2)
        scratch_layer1.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))

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

        scratch_layer1.setLabelsEnabled(True)
        scratch_layer1.setLabeling(layer_settings)
        scratch_layer1.triggerRepaint()

        QgsProject.instance().addMapLayer(scratch_layer1)

        if len(points) > 2:
            scratch_layer2 = QgsVectorLayer("Point", "temp", "memory")
            scratch_layer2.setCrs(crs)
            scratch_layer2_dataprovider = scratch_layer2.dataProvider()
            scratch_layer2_dataprovider.addAttributes(
                [QgsField("id", QVariant.String), QgsField("xcoord", QVariant.Double)]
            )
            scratch_layer2.updateFields()

            point2 = QgsPointXY(float(points[2]), float(points[3]))
            f2 = QgsFeature()
            f2.setGeometry(QgsGeometry.fromPointXY(point2))
            if len(corners) == 0:
                f2.setAttributes(['B2', 233.0])
            else:
                f2.setAttributes(['Corner ' + str(len(corners)+1) + ' V2', 233.0])
            scratch_layer2_dataprovider.addFeature(f2)
            scratch_layer2.updateExtents()

            if len(corners) == 0:
                scratch_layer2.setName(tr("B point alternative 2"))
            else:
                scratch_layer2.setName(tr("Point alternative 2"))
            scratch_layer2.renderer().symbol().setSize(2)
            scratch_layer2.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))

            scratch_layer2.setLabelsEnabled(True)
            scratch_layer2.setLabeling(layer_settings)
            scratch_layer2.triggerRepaint()

            QgsProject.instance().addMapLayer(scratch_layer2)

        if len(points) > 2:
            return [scratch_layer1, scratch_layer2]
        else:
            return [scratch_layer1]
