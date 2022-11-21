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
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)
from qgis.gui import QgisInterface, QgsMapToolEmitPoint
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont
from qgis.utils import iface

from ..qgis_plugin_tools.tools.i18n import tr
from ..ui.line_circle_dockwidget import LineCircleDockWidget
from .click_tool import ClickTool
from .select_tool import SelectTool
from .tool_functions import (
    LineCoordinates,
    check_within_canvas,
    log_warning,
    write_output_to_file,
)


class IntersectionLineCircle(SelectTool):
    def __init__(self, iface: QgisInterface, dock_widget: LineCircleDockWidget) -> None:
        super().__init__(iface)
        self.ui: LineCircleDockWidget = dock_widget

    def _run_initial_checks(self) -> bool:
        """Checks that the selections made are applicable."""
        all_layers = QgsProject.instance().mapLayers().values()

        points_found = 0
        crs_list: List[str] = []

        points_found = 0
        crs_list = []
        # Check for selected features from all layers
        for layer in all_layers:
            if isinstance(layer, QgsVectorLayer) and layer.isSpatial():
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
        if len(set(crs_list)) != 1:
            log_warning("Please select features only from layers with same CRS")
            return False
        elif points_found != 2:
            log_warning("Please select only either 1 line or 2 points")
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
            result_layer.dataProvider().deleteFeatures([point_2.id()])
        else:
            result_layer.dataProvider().deleteFeatures([point_1.id()])

    def _extract_points(self) -> LineCoordinates:
        """Extract start and end point coordinates which explicitly determine
        the line feature intersecting with the user defined circle."""
        all_layers = QgsProject.instance().mapLayers().values()

        selected_layers = []
        for layer in all_layers:
            if (
                isinstance(layer, QgsVectorLayer)
                and layer.isSpatial()
                and len(layer.selectedFeatures()) > 0
            ):
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
            log_warning("There are no intersection points!")
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
        results_within_canvas = {}
        if check_within_canvas((x_sol1, y_sol1)):
            results_within_canvas['Opt 1'] = (x_sol1, y_sol1)
        if check_within_canvas((x_sol2, y_sol2)):
            results_within_canvas['Opt 2'] = (x_sol2, y_sol2)

        res_count = len(results_within_canvas)

        centroid_x = float(centroid[0])
        centroid_y = float(centroid[1])

        # Add result layer to map canvas
        old_active_layer = iface.activeLayer()
        result_layer = self._create_result_layer()

        if res_count == 0:
            log_warning("Both intersection points lie outside of the map canvas!")
        elif res_count == 1:
            log_warning("One intersection point lies outside of the map canvas!")
        elif x_sol1 == x_sol2:
            del results_within_canvas['Opt 2']

        self._set_and_format_labels(result_layer)
        QgsProject.instance().addMapLayer(result_layer)

        points = []
        for point_name, sol in results_within_canvas.items():
            point = self._add_point_to_layer(
                result_layer, (sol[0], sol[1],  centroid_x, centroid_y), point_name
            )
            points.append(point)

        if len(points) == 2:
            self._select_point(result_layer, points[0], points[1])

        result_layer.commitChanges()
        iface.vectorLayerTools().stopEditing(result_layer)

        output_path = self.ui.get_output_file_path()
        if output_path != "":
            write_output_to_file(result_layer, output_path)
            QgsProject.instance().removeMapLayer(result_layer)

        iface.setActiveLayer(old_active_layer)
