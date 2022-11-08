import math
from decimal import Decimal
from typing import List, Tuple

from PyQt5.QtWidgets import QMessageBox
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
from .tool_functions import LineCoordinates

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
        all_layers = QgsProject.instance().mapLayers().values()

        points_found = 0
        crs_list: List[str] = []

        def loop_features(points_found: int, points_added: int) -> Tuple[bool, int]:
            for feature in layer.selectedFeatures():
                if QgsWkbTypes.isSingleType(feature.geometry().wkbType()):
                    points_found += points_added
                    crs_list.append(layer.crs().toProj())
                else:
                    LOGGER.warning(
                        tr("Please select layers with LineString or Point geometries"),
                        extra={"details": ""},
                    )
                    return False, points_found
            return True, points_found

        for layer in all_layers:
            if (
                isinstance(layer, QgsVectorLayer)
                and layer.isSpatial()
                and layer.geometryType() == QgsWkbTypes.LineGeometry
            ):
                valid_features, points_found = loop_features(points_found, 2)
                if not valid_features:
                    return False
            elif (
                isinstance(layer, QgsVectorLayer)
                and layer.isSpatial()
                and layer.geometryType() == QgsWkbTypes.PointGeometry
            ):
                valid_features, points_found = loop_features(points_found, 1)
                if not valid_features:
                    return False
            else:
                pass

        if len(set(crs_list)) != 1:
            LOGGER.warning(
                tr("Please select only layers with same CRS"),
                extra={"details": ""},
            )
            return False
        elif points_found != 2:
            LOGGER.warning(
                tr("Please select only either 1 line or 2 points"),
                extra={"details": ""},
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
            # line_coords = self._get_line_coords() # OLD!
            line_coords = self._extract_points()

            # Call the functions capable of determining the parameter
            # values needed to find out intersection point(s)
            parameters = self._calculate_intersection_parameters(line_coords, centroid)

            # Call for function determining the intersection point
            self._intersect(line_coords, parameters, centroid)

    def _calculate_intersection_parameters(
        # self, line_coords: List[Decimal], centroid: List[Decimal]
        self, line_coords: LineCoordinates, centroid: List[Decimal]
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
            (line_coords.y2) ** Decimal("2.0")
            - Decimal("2.0") * line_coords.y1 * line_coords.y2
            + (line_coords.y1) ** Decimal("2.0")
            + (line_coords.x2) ** Decimal("2.0")
            - Decimal("2.0") * line_coords.x1 * line_coords.x2
            + (line_coords.x1) ** Decimal("2.0")
        )
        b = (
            -Decimal("2.0") * (line_coords.y2) ** Decimal("2.0") * line_coords.x1
            + Decimal("2.0") * line_coords.y1 * line_coords.y2 * line_coords.x2
            + Decimal("2.0") * line_coords.y1 * line_coords.y2 * line_coords.x1
            - Decimal("2.0") * (line_coords.y1) ** Decimal("2.0") * line_coords.x2
            - Decimal("2.0") * centroid[0] * (line_coords.x2) ** Decimal("2.0")
            - Decimal("2.0") * centroid[0] * (line_coords.x1) ** Decimal("2.0")
            + Decimal("4.0") * centroid[0] * line_coords.x1 * line_coords.x2
            - Decimal("2.0") * line_coords.x2 * centroid[1] * line_coords.y2
            + Decimal("2.0") * centroid[1] * line_coords.y1 * line_coords.x2
            + Decimal("2.0") * centroid[1] * line_coords.y2 * line_coords.x1
            - Decimal("2.0") * centroid[1] * line_coords.y1 * line_coords.x1
        )
        c = (
            (line_coords.y2) ** Decimal("2.0")
            * (line_coords.x1) ** Decimal("2.0")
            - Decimal("2.0")
            * line_coords.x1
            * line_coords.y1
            * line_coords.x2
            * line_coords.y2
            + (line_coords.y1) ** Decimal("2.0")
            * (line_coords.x2) ** Decimal("2.0")
            + (centroid[0]) ** Decimal("2.0")
            * (line_coords.x2) ** Decimal("2.0")
            - Decimal("2.0")
            * (centroid[0]) ** Decimal("2.0")
            * line_coords.x1
            * line_coords.x2
            + (centroid[0]) ** Decimal("2.0")
            * (line_coords.x1) ** Decimal("2.0")
            + Decimal("2.0")
            * line_coords.x2
            * centroid[1]
            * line_coords.y2
            * line_coords.x1
            - Decimal("2.0")
            * (line_coords.x2) ** Decimal("2.0")
            * centroid[1]
            * line_coords.y1
            - Decimal("2.0")
            * (line_coords.x1) ** Decimal("2.0")
            * centroid[1]
            * line_coords.y2
            + Decimal("2.0")
            * centroid[1]
            * line_coords.y1
            * line_coords.x2
            * line_coords.x1
            + (line_coords.x2) ** Decimal("2.0")
            * (centroid[1]) ** Decimal("2.0")
            - (line_coords.x2) ** Decimal("2.0") * r ** Decimal("2.0")
            - Decimal("2.0")
            * line_coords.x1
            * line_coords.x2
            * (centroid[1]) ** Decimal("2.0")
            + Decimal("2.0")
            * line_coords.x1
            * line_coords.x2
            * r ** Decimal("2.0")
            + (line_coords.x1) ** Decimal("2.0")
            * (centroid[1]) ** Decimal("2.0")
            - (line_coords.x1) ** Decimal("2.0") * r ** Decimal("2.0")
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

    def _create_result_layer(self) -> QgsVectorLayer:
        result_layer = QgsVectorLayer("Point", "temp", "memory")
        result_layer.setCrs(self.crs)
        result_layer.dataProvider().addAttributes(
            [QgsField("id", QVariant.String),
             QgsField("xcoord", QVariant.Double),
             QgsField("ycoord", QVariant.Double),
             QgsField("centroid xcoord", QVariant.Double),
             QgsField("centroid ycoord", QVariant.Double)]
        )
        result_layer.updateFields()
        result_layer.setName(tr("Intersection point"))
        result_layer.renderer().symbol().setSize(2)
        result_layer.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))
        return result_layer

    def _add_point_to_layer(
        self, layer: QgsVectorLayer, coords: Tuple[float, float, float, float], id: str
    ) -> QgsFeature:
        intersection_point = QgsPointXY(coords[0], coords[1])
        point_feature = QgsFeature()
        point_feature.setGeometry(QgsGeometry.fromPointXY(intersection_point))
        point_feature.setAttributes([id,
                                     round(coords[0], 3),
                                     round(coords[1], 3),
                                     round(coords[2], 3),
                                     round(coords[3], 3)]
                                    )
        layer.dataProvider().addFeature(point_feature)
        layer.updateExtents()
        layer.triggerRepaint()
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

    def _select_point(
        self, result_layer: QgsVectorLayer, point_1: QgsFeature, point_2: QgsFeature
    ) -> None:
        # Let's decide which solution point is the desired one
        message_box = QMessageBox()
        message_box.setText(
            tr("Do you want to choose option 1 for the intersection point?")
        )
        message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        ret_a = message_box.exec()
        if ret_a == QMessageBox.Yes:
            result_layer.deleteFeature(point_2.id())
        else:
            result_layer.deleteFeature(point_1.id())

    def _add_result_layers(
        self,
        x_sol1: QVariant.Double,
        y_sol1: QVariant.Double,
        x_sol2: QVariant.Double,
        y_sol2: QVariant.Double,
        centroid_x: QVariant.Double,
        centroid_y: QVariant.Double,
    ) -> None:
        """Triggered when result layer needs to be generated."""

        result_layer = self._create_result_layer()
        point_1 = self._add_point_to_layer(
            result_layer, (x_sol1, y_sol1, centroid_x, centroid_y), "Opt 1"
        )
        self._set_and_format_labels(result_layer)
        QgsProject.instance().addMapLayer(result_layer)

        # If the line forms a tangent to the circle (instead
        # of genuinely intersecting with the circle),
        # only one intersection point exists. Thus there is
        # no need for second result layer
        if x_sol1 == x_sol2:
            if self.ui.get_output_file_path() != "":
                self._write_output_to_file(result_layer)
                QgsProject.instance().removeMapLayer(result_layer)
            return

        result_layer.startEditing()
        point_2 = self._add_point_to_layer(
            result_layer, (x_sol2, y_sol2, centroid_x, centroid_y), "Opt 2"
        )
        self._select_point(result_layer, point_1, point_2)

        result_layer.commitChanges()
        iface.vectorLayerTools().stopEditing(result_layer)
        # Save the mapped point features to the file user has chosen
        if self.ui.get_output_file_path() != "":
            self._write_output_to_file(result_layer)
            QgsProject.instance().removeMapLayer(result_layer)

    def _extract_points(self) -> LineCoordinates:
        """Extract start and end point coordinates which explicitly determine
        the line feature intersecting with the user defined circle."""
        all_layers = QgsProject.instance().mapLayers().values()

        selected_layers = []
        for layer in all_layers:
            if len(layer.selectedFeatures()) > 0:
                selected_layers.append(layer)

        # CASE LINE
        if all(
            layer.geometryType() == QgsWkbTypes.LineGeometry
            for layer in selected_layers
        ):
            for layer in selected_layers:
                for feat in layer.selectedFeatures():
                    line_feat = feat.geometry().asPolyline()
                    start_point = QgsPointXY(line_feat[0])
                    end_point = QgsPointXY(line_feat[-1])
                    line_coords = LineCoordinates(
                        x1=Decimal(start_point.x()),
                        x2=Decimal(end_point.x()),
                        y1=Decimal(start_point.y()),
                        y2=Decimal(end_point.y())
                    )

        # CASE POINTS
        else:
            points = []
            for layer in selected_layers:
                for feat in layer.selectedFeatures():
                    points.append(feat.geometry().asPoint())

            # Create a line out of the two lone points
            line_coords = LineCoordinates(
                x1=Decimal(points[0].x()),
                x2=Decimal(points[1].x()),
                y1=Decimal(points[0].y()),
                y2=Decimal(points[1].y())
            )

        return line_coords

    def _intersect(
        self, line_coords: LineCoordinates, parameters: List[Decimal], centroid: List[Decimal]
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
                Decimal(x_sol1) * line_coords.y2
                - line_coords.x1 * line_coords.y2
                - Decimal(x_sol1) * line_coords.y1
                + line_coords.x2 * line_coords.y1
            )
            / (line_coords.x2 - line_coords.x1)
        )

        x_sol2 = float((-parameters[1] - Decimal(math.sqrt(sqrt_in))) / (
            Decimal("2.0") * parameters[0]
        ))

        y_sol2 = float(
            (
                Decimal(x_sol2) * line_coords.y2
                - line_coords.x1 * line_coords.y2
                - Decimal(x_sol2) * line_coords.y1
                + line_coords.x2 * line_coords.y1
            )
            / (line_coords.x2 - line_coords.x1)
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
