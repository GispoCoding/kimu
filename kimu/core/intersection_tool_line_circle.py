import math
from decimal import Decimal
from typing import List

from PyQt5.QtWidgets import QMessageBox
from qgis import processing
from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
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
from ..ui.line_circle_dockwidget import LineCircleDockWidget
from .click_tool import ClickTool
from .select_tool import SelectTool

LOGGER = setup_logger(plugin_name())


class IntersectionLineCircle(SelectTool):
    def __init__(self, iface: QgisInterface, dock_widget: LineCircleDockWidget) -> None:
        super().__init__(iface)
        self.ui: LineCircleDockWidget = dock_widget

    def active_changed(self, layer: QgsVectorLayer) -> None:
        """Triggered when active layer changes."""
        self.layer = layer
        self.setLayer(self.layer)

    def _run_initial_checks(self) -> bool:
        """Checks that the selections made are applicable."""
        selected_layer = iface.activeLayer()

        if isinstance(selected_layer, QgsVectorLayer) and selected_layer.isSpatial():
            pass
        else:
            LOGGER.warning(
                tr("Please select a valid vector layer"),
                extra={"details": ""},
            )
            return False

        if selected_layer.geometryType() == QgsWkbTypes.LineGeometry:

            if len(selected_layer.selectedFeatures()) != 1:
                LOGGER.warning(
                    tr("Please select one line feature"),
                    extra={"details": ""},
                )
                return False

            if QgsWkbTypes.isSingleType(
                list(selected_layer.getFeatures())[0].geometry().wkbType()
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
                return False

            temp_layer = selected_layer.materialize(
                QgsFeatureRequest().setFilterFids(selected_layer.selectedFeatureIds())
            )
            params1 = {"INPUT": temp_layer, "OUTPUT": "memory:"}
            vertices = processing.run("native:extractvertices", params1)
            vertices_layer = vertices["OUTPUT"]

            if vertices_layer.featureCount() > 2:
                LOGGER.warning(
                    tr("Please use Explode line(s) tool first!"), extra={"details": ""}
                )
                return False

        elif selected_layer.geometryType() == QgsWkbTypes.PointGeometry:

            if len(selected_layer.selectedFeatures()) != 2:
                LOGGER.warning(
                    tr(
                        "Please select two points in order to explicitly "
                        "define a line feature"
                    ),
                    extra={"details": ""},
                )
                return False

            if QgsWkbTypes.isSingleType(
                list(selected_layer.getFeatures())[0].geometry().wkbType()
            ):
                pass
            else:
                LOGGER.warning(
                    tr(
                        "Please select a point layer with "
                        "Point geometries (instead "
                        "of MultiPoint geometries)"
                    ),
                    extra={"details": ""},
                )
                return False
        else:
            LOGGER.warning(
                tr("Please select a point or line layer"),
                extra={"details": ""},
            )
            return False

        return True

    # fmt: off
    def canvasPressEvent(  # noqa: N802
        self, event: QgsMapToolEmitPoint
    ) -> None:
        # fmt: on
        """Canvas click event for storing centroid
        point of the circle."""
        if self._run_initial_checks() is True:
            # Snap the click to the closest point feature available.
            # Note that your QGIS's snapping options have on effect
            # on which objects / vertexes the tool will snap and
            # get the coordinates of the point to be used as a circle centroid
            centroid = ClickTool(self.iface).activate(event)

            # Call for function extracting coordinate values attached to
            # the line feature to be intersected with a circle
            line_coords = self._get_line_coords()

            # Call the functions capable of determining the parameter
            # values needed to find out intersection point(s)
            parameters = self._calculate_intersection_parameters(line_coords, centroid)

            # Call for function determining the intersection point
            self._intersect(line_coords, parameters, centroid)

    def _calculate_intersection_parameters(
        self, line_coords: List[Decimal], centroid: List[Decimal]
    ) -> List[Decimal]:
        """Calculate values for a, b and c parameters"""
        # Radius is given in crs units (meters for EPSG: 3067)
        r = Decimal(self.ui.get_radius())
        # 1. Determine the function of the straight line the selected
        # line feature represents (each line can be seen as a limited
        # representation of a function determining a line which has no
        # start and end points). See e.g.
        # https://www.cuemath.com/geometry/two-point-form/
        # for more information.
        # 2. Determine the function of the circle defined implicitly via
        # the clicked centroid point and given radius.
        # See e.g. Standard Equation of a Circle section from
        # https://www.cuemath.com/geometry/equation-of-circle/
        # for more information.
        # 3. Search for intersection point of the line and circle
        # by setting there functions equal and analytically modifying
        # the resulting equation so that it is possible to solve x
        # (and then, after figuring out suitable value for x, y).
        # 4. After some analytical simplifying of the particular
        # equation you will see that it is needed to solve the
        # quadratic equation in order to find suitable values for x.
        # The parameters a, b and c to be solved come from the
        # quadratic formula. See e.g.
        # https://www.mathsisfun.com/algebra/quadratic-equation.html
        # for more information.
        a = (
            (line_coords[3]) ** Decimal("2.0")
            - Decimal("2.0") * line_coords[1] * line_coords[3]
            + (line_coords[1]) ** Decimal("2.0")
            + (line_coords[2]) ** Decimal("2.0")
            - Decimal("2.0") * line_coords[0] * line_coords[2]
            + (line_coords[0]) ** Decimal("2.0")
        )
        b = (
            -Decimal("2.0")
            * (line_coords[3]) ** Decimal("2.0")
            * line_coords[0]
            + Decimal("2.0") * line_coords[1] * line_coords[3] * line_coords[2]
            + Decimal("2.0") * line_coords[1] * line_coords[3] * line_coords[0]
            - Decimal("2.0")
            * (line_coords[1]) ** Decimal("2.0")
            * line_coords[2]
            - Decimal("2.0")
            * centroid[0]
            * (line_coords[2]) ** Decimal("2.0")
            - Decimal("2.0")
            * centroid[0]
            * (line_coords[0]) ** Decimal("2.0")
            + Decimal("4.0") * centroid[0] * line_coords[0] * line_coords[2]
            - Decimal("2.0") * line_coords[2] * centroid[1] * line_coords[3]
            + Decimal("2.0") * centroid[1] * line_coords[1] * line_coords[2]
            + Decimal("2.0") * centroid[1] * line_coords[3] * line_coords[0]
            - Decimal("2.0") * centroid[1] * line_coords[1] * line_coords[0]
        )
        c = (
            (line_coords[3]) ** Decimal("2.0")
            * (line_coords[0]) ** Decimal("2.0")
            - Decimal("2.0")
            * line_coords[0]
            * line_coords[1]
            * line_coords[2]
            * line_coords[3]
            + (line_coords[1]) ** Decimal("2.0")
            * (line_coords[2]) ** Decimal("2.0")
            + (centroid[0]) ** Decimal("2.0")
            * (line_coords[2]) ** Decimal("2.0")
            - Decimal("2.0")
            * (centroid[0]) ** Decimal("2.0")
            * line_coords[0]
            * line_coords[2]
            + (centroid[0]) ** Decimal("2.0")
            * (line_coords[0]) ** Decimal("2.0")
            + Decimal("2.0")
            * line_coords[2]
            * centroid[1]
            * line_coords[3]
            * line_coords[0]
            - Decimal("2.0")
            * (line_coords[2]) ** Decimal("2.0")
            * centroid[1]
            * line_coords[1]
            - Decimal("2.0")
            * (line_coords[0]) ** Decimal("2.0")
            * centroid[1]
            * line_coords[3]
            + Decimal("2.0")
            * centroid[1]
            * line_coords[1]
            * line_coords[2]
            * line_coords[0]
            + (line_coords[2]) ** Decimal("2.0")
            * (centroid[1]) ** Decimal("2.0")
            - (line_coords[2]) ** Decimal("2.0") * r ** Decimal("2.0")
            - Decimal("2.0")
            * line_coords[0]
            * line_coords[2]
            * (centroid[1]) ** Decimal("2.0")
            + Decimal("2.0")
            * line_coords[0]
            * line_coords[2]
            * r ** Decimal("2.0")
            + (line_coords[0]) ** Decimal("2.0")
            * (centroid[1]) ** Decimal("2.0")
            - (line_coords[0]) ** Decimal("2.0") * r ** Decimal("2.0")
        )
        result = [a, b, c]
        return result

    def _write_output_to_file(self, layer: QgsVectorLayer) -> None:
        """Writes the selected corner points to a specified file"""
        output_file_path = self.ui.get_output_file_path()
        writer_options = QgsVectorFileWriter.SaveVectorOptions()
        writer_options.actionOnExistingFile = QgsVectorFileWriter.AppendToLayerAddFields
        error, explanation = QgsVectorFileWriter.writeAsVectorFormatV2(
            layer,
            output_file_path,
            QgsProject.instance().transformContext(),
            writer_options,
        )

        if error:
            LOGGER.warning(
                tr(f"Error writing output to file, error code {error}"),
                extra={"details": tr(f"Details: {explanation}")},
            )

    def _add_result_layers(
        self,
        x_sol1: QVariant.Double,
        y_sol1: QVariant.Double,
        x_sol2: QVariant.Double,
        y_sol2: QVariant.Double,
        centroid_x: QVariant.Double,
        centroid_y: QVariant.Double
    ) -> None:
        """Triggered when result layer needs to be generated."""
        result_layer1 = QgsVectorLayer("Point", "temp", "memory")
        crs = self.layer.crs()
        result_layer1.setCrs(crs)

        result_layer1_dataprovider = result_layer1.dataProvider()
        result_layer1_dataprovider.addAttributes(
            [QgsField("id", QVariant.String),
             QgsField("xcoord", QVariant.Double),
             QgsField("ycoord", QVariant.Double),
             QgsField("centroid xcoord", QVariant.Double),
             QgsField("centroid ycoord", QVariant.Double)]
        )
        result_layer1.updateFields()

        intersection_point1 = QgsPointXY(x_sol1, y_sol1)
        f1 = QgsFeature()
        f1.setGeometry(QgsGeometry.fromPointXY(intersection_point1))
        f1.setAttributes(
            ["Opt 1",
             round(x_sol1, 3), round(y_sol1, 3),
             round(centroid_x, 3), round(centroid_y, 3)]
        )
        result_layer1_dataprovider.addFeature(f1)
        result_layer1.updateExtents()
        result_layer1.triggerRepaint()

        result_layer1.setName(tr("Intersection point"))
        result_layer1.renderer().symbol().setSize(2)
        result_layer1.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))

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
        result_layer1.setLabelsEnabled(True)
        result_layer1.setLabeling(layer_settings)

        QgsProject.instance().addMapLayer(result_layer1)

        # If the line forms a tangent to the circle (instead
        # of genuinely intersecting with the circle),
        # only one intersection point exists. Thus there is
        # no need for second result layer
        if x_sol1 == x_sol2:
            # Save the mapped point features to the file user has chosen
            if self.ui.get_output_file_path() != "":
                self._write_output_to_file(result_layer1)
                QgsProject.instance().removeMapLayer(result_layer1)
            return

        result_layer1.startEditing()

        intersection_point2 = QgsPointXY(x_sol2, y_sol2)
        f2 = QgsFeature()
        f2.setGeometry(QgsGeometry.fromPointXY(intersection_point2))
        f2.setAttributes(
            ["Opt 2",
             round(x_sol2, 3), round(y_sol2, 3),
             round(centroid_x, 3), round(centroid_y, 3)]
        )
        result_layer1_dataprovider.addFeature(f2)
        result_layer1.updateExtents()

        # Let's decide which solution point is the desired one
        message_box = QMessageBox()
        message_box.setText(
            tr("Do you want to choose option 1 for the intersection point?")
        )
        message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        ret_a = message_box.exec()
        if ret_a == QMessageBox.Yes:
            # Let's remove the not-selected solution point
            result_layer1.deleteFeature(f2.id())
        else:
            # Let's remove the not-selected solution point
            result_layer1.deleteFeature(f1.id())
        result_layer1.commitChanges()
        iface.vectorLayerTools().stopEditing(result_layer1)
        # Save the mapped point features to the file user has chosen
        if self.ui.get_output_file_path() != "":
            self._write_output_to_file(result_layer1)
            QgsProject.instance().removeMapLayer(result_layer1)

    def _get_line_coords(self) -> List[Decimal]:
        """Extract start and end point coordinates which explicitly determine
        the line feature intersecting with the user defined circle."""
        if self.iface.activeLayer().geometryType() == QgsWkbTypes.LineGeometry:
            geometry = self.iface.activeLayer().selectedFeatures()[0].geometry()
            line_feat = geometry.asPolyline()
            start_point = QgsPointXY(line_feat[0])
            end_point = QgsPointXY(line_feat[-1])
            line_coords = [
                Decimal(start_point.x()),
                Decimal(start_point.y()),
                Decimal(end_point.x()),
                Decimal(end_point.y()),
            ]
        else:
            line_coords = [
                Decimal(
                    self.iface.activeLayer().selectedFeatures()[0].geometry().asPoint().x()
                ),
                Decimal(
                    self.iface.activeLayer().selectedFeatures()[0].geometry().asPoint().y()
                ),
                Decimal(
                    self.iface.activeLayer().selectedFeatures()[1].geometry().asPoint().x()
                ),
                Decimal(
                    self.iface.activeLayer().selectedFeatures()[1].geometry().asPoint().y()
                ),
            ]

        return line_coords

    def _intersect(
        self, line_coords: List[Decimal], parameters: List[Decimal], centroid: List[Decimal]
    ) -> None:
        """Determine the intersection point(s) of the selected
        line and implicitly determined (centroid+radius) circle."""

        # Check that the selected line feature and indirectly
        # defined circle intersect
        sqrt_in = (
            parameters[1] ** Decimal("2.0")
            - Decimal("4.0") * parameters[0] * parameters[2]
        )
        if sqrt_in < 0.0 or parameters[0] == 0.0:
            LOGGER.warning(
                tr("There is no intersection point(s)!"),
                extra={"details": ""},
            )
            return

        # Computing the coordinates for the intersection point(s)
        x_sol1 = float((-parameters[1] + Decimal(math.sqrt(sqrt_in))) / (
            Decimal("2.0") * parameters[0]
        ))

        y_sol1 = float(
            (
                Decimal(x_sol1) * line_coords[3]
                - line_coords[0] * line_coords[3]
                - Decimal(x_sol1) * line_coords[1]
                + line_coords[2] * line_coords[1]
            )
            / (line_coords[2] - line_coords[0])
        )

        x_sol2 = float((-parameters[1] - Decimal(math.sqrt(sqrt_in))) / (
            Decimal("2.0") * parameters[0]
        ))

        y_sol2 = float(
            (
                Decimal(x_sol2) * line_coords[3]
                - line_coords[0] * line_coords[3]
                - Decimal(x_sol2) * line_coords[1]
                + line_coords[2] * line_coords[1]
            )
            / (line_coords[2] - line_coords[0])
        )

        # Check that the intersection point(s) lie(s) in the
        # map canvas extent
        extent = iface.mapCanvas().extent()

        if (
            x_sol1 < extent.xMinimum()
            or x_sol1 > extent.xMaximum()
            or y_sol1 < extent.yMinimum()
            or y_sol1 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Intersection point 1 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return

        if (
            x_sol2 < extent.xMinimum()
            or x_sol2 > extent.xMaximum()
            or y_sol2 < extent.yMinimum()
            or y_sol2 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Intersection point 2 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return

        centroid_x = float(centroid[0])
        centroid_y = float(centroid[1])

        # Add result layer to map canvas
        self._add_result_layers(x_sol1, y_sol1, x_sol2, y_sol2, centroid_x, centroid_y)
