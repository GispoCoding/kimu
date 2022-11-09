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
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)
from qgis.gui import QgsMapToolEmitPoint
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont
from qgis.utils import iface

from ..qgis_plugin_tools.tools.i18n import tr
from ..ui.rectangular_dockwidget import RectangularDockWidget
from .click_tool import ClickTool
from .select_tool import SelectTool
from .tool_functions import check_within_canvas, log_warning, write_output_to_file


class RectangularMapping(SelectTool):
    def __init__(self, dock_widget: RectangularDockWidget) -> None:
        super().__init__(iface)
        self.ui: RectangularDockWidget = dock_widget

    def update_layer(self, layer: QgsVectorLayer) -> None:
        layer.updateExtents()
        layer.triggerRepaint()
        layer.commitChanges()
        iface.vectorLayerTools().stopEditing(layer)

    def canvasPressEvent(self, event: QgsMapToolEmitPoint) -> None:  # noqa: N802
        """Canvas click event."""

        if self._run_initial_checks() is True:

            # Snap the click to the closest point feature available and get
            # the coordinates of the property boundary line's end point we
            # wish to measure the distance from
            start_point = ClickTool(self.iface).activate(event)

            selected_line_coords = self._get_line_coords(start_point)
            if not selected_line_coords:
                return

            # a_measure is given in crs units (meters for EPSG: 3067)
            a_measure = Decimal(self.ui.get_a_measure())

            # Determine parameter values for solving the quadratic equation in hand
            parameters = self._calculate_parameters(selected_line_coords, a_measure)

            if a_measure > Decimal(0):
                # Let's locate alternative solutions for point A
                try:
                    points_a = self._locate_point_a(selected_line_coords, parameters)
                except IndexError:
                    return
            else:
                points_a = [selected_line_coords[0], selected_line_coords[1]]

            if points_a == []:
                log_warning("Search of the point A was failed!")
                return

            old_active_layer = iface.activeLayer()

            # Let's show user the solution points and let the user
            # decide which is the desired one
            option_points_layer_a = self._create_temp_layer(0)
            QgsProject.instance().addMapLayer(option_points_layer_a)
            option_points_layer_a.startEditing()

            self._add_points_to_layer(points_a, option_points_layer_a, 0)

            if a_measure > Decimal("0.000"):
                message_box_a = QMessageBox()
                message_box_a.setText(tr("Do you want to choose option 1 for point A?"))
                message_box_a.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                ret_a = message_box_a.exec()
                if ret_a == QMessageBox.Yes:
                    point_a = [points_a[0], points_a[1]]
                else:
                    point_a = [points_a[2], points_a[3]]
            else:
                point_a = [points_a[0], points_a[1]]

            self.update_layer(option_points_layer_a)

            # Let's remove layer scratch layer related to point A alternatives
            # since we have no use for this layer anymore
            QgsProject.instance().removeMapLayer(option_points_layer_a)

            # b_measure is given in crs units (meters for EPSG: 3067)
            b_measure = Decimal(self.ui.get_b_measure())

            if b_measure > Decimal(0):
                # Let's locate alternative solutions for point B
                try:
                    points_b = self._locate_point_b(
                        selected_line_coords, point_a, b_measure
                    )
                except IndexError:
                    return
            else:
                points_b = point_a.copy()

            if points_b == []:
                log_warning("Search of the point B was failed!")
                return

            # Let's show user the solution points and let the user
            # decide which is the desired one
            option_points_layer_b = self._create_temp_layer(1)
            QgsProject.instance().addMapLayer(option_points_layer_b)
            option_points_layer_b.startEditing()

            self._add_points_to_layer(points_b, option_points_layer_b, 1)

            if b_measure > Decimal(0):
                # Let's ask the user which is the desired solution point
                message_box = self._generate_option_point_messagebox(1)
                ret = message_box.exec()
                if ret == QMessageBox.Yes:
                    # Let's add the point user chose to the list of
                    # selected corner points
                    selected_corners = [[points_b[-4], points_b[-3]]]
                else:
                    selected_corners = [[points_b[-2], points_b[-1]]]
            else:
                # Let's add the point user chose to the list of
                # selected corner points
                selected_corners = [[points_b[-2], points_b[-1]]]

            point_b = selected_corners[0]

            self.update_layer(option_points_layer_b)

            # Let's remove layer scratch layer related to point B alternatives
            # since we have no use for this layer anymore
            QgsProject.instance().removeMapLayer(option_points_layer_b)

            # Let's create a temporary layer for displaying the selected
            # point B on map (supports future decisions)
            selected_b = self._create_temp_layer(-1)
            QgsProject.instance().addMapLayer(selected_b)
            selected_b.startEditing()

            self._add_point_to_layer(point_b, selected_b, -1)

            self.update_layer(selected_b)

            layers_to_be_deleted = []
            if self.ui.get_c_measures() != "":
                # c_measures are given in crs units (meters for EPSG: 3067)
                c_measures = [
                    Decimal(measure.strip())
                    for measure in self.ui.get_c_measures().split(",")
                ]

                for i, c_measure in enumerate(c_measures):
                    if i == 0:
                        # Map the second corner point which will be located in the extension
                        # of the line feature connecting point A and point B
                        # Note that we assume that point B is the closest corner point
                        # a building has to the selected boundary line. In practice
                        # this means that we do not have to ask the user which point
                        # he prefers.
                        if point_a == point_b:
                            point_a = [selected_line_coords[2], selected_line_coords[3]]

                        point_c = self._locate_point_c(c_measure, point_a, point_b)

                        if point_c == []:
                            log_warning("Search of the second corner point was failed!")
                            return

                        # Let's show user the solution points and let the user
                        # decide which is the desired one
                        option_points_layer_c = self._create_temp_layer(2)
                        QgsProject.instance().addMapLayer(option_points_layer_c)
                        option_points_layer_c.startEditing()

                        self._add_point_to_layer(point_c, option_points_layer_c, 0)

                        selected_corners.append([point_c[0], point_c[1]])

                        self.update_layer(option_points_layer_c)

                        # Let's initialize variables we will need later on
                        skip = 0
                        QgsProject.instance().removeMapLayer(option_points_layer_c)
                    else:
                        # Map the rest of the rectangular corner points (they will be located
                        # perpendicularly with respect to the line feature connecting two last
                        # elements of the selected corners list)
                        new_corner_points = self._locate_point_d(
                            c_measure, selected_corners
                        )

                        if new_corner_points == []:
                            log_warning(
                                "Search of the corner point related to an element in"
                                " the given building wall width list was failed!"
                            )
                            return

                        # Let's show user the solution points and let the user
                        # decide which is the desired one
                        option_points_layer_d = self._create_temp_layer(2 + i)
                        QgsProject.instance().addMapLayer(option_points_layer_d)
                        option_points_layer_d.startEditing()

                        self._add_points_to_layer(
                            new_corner_points, option_points_layer_d, 2 + i
                        )

                        message_box = self._generate_option_point_messagebox(
                            len(selected_corners) + 1
                        )
                        ret = message_box.exec()
                        # Consider the signal and check if point already exists in selected
                        # corners list in order to avoid duplicates
                        if ret == QMessageBox.No and [
                            round(new_corner_points[-2], 3),
                            round(new_corner_points[-1], 3),
                        ] not in [
                            [round(item, 3) for item in nested]
                            for nested in selected_corners
                        ]:
                            point_d = [new_corner_points[-2], new_corner_points[-1]]
                            selected_corners.append(point_d)
                        elif ret == QMessageBox.Yes and [
                            round(new_corner_points[-4], 3),
                            round(new_corner_points[-3], 3),
                        ] not in [
                            [round(item, 3) for item in nested]
                            for nested in selected_corners
                        ]:
                            point_d = [new_corner_points[-4], new_corner_points[-3]]
                            selected_corners.append(point_d)
                        else:
                            skip = 1

                        self.update_layer(option_points_layer_d)

                        # Let's remove layer scratch layer related to corner point
                        # alternatives since we have no use for this layer anymore
                        QgsProject.instance().removeMapLayer(option_points_layer_d)

                        # Check that the selected corner point does not already exist
                        # in the list of selected corner points
                        if skip != 1:
                            # Let's create a temporary layer for displaying the selected
                            # corner point on map (supports future decisions)
                            selected_d = self._create_temp_layer(-2 - i)

                            # Let's store the layer ids of the temporary layers we add
                            # with the same variable name
                            if i != len(c_measures) - 1:
                                layers_to_be_deleted.append(selected_d.id())

                            QgsProject.instance().addMapLayer(selected_d)
                            selected_d.startEditing()

                            self._add_point_to_layer(point_d, selected_d, -2 - i)

                            self.update_layer(selected_d)

                        QgsProject.instance().removeMapLayer(selected_d)

            # The selection process of the corner points has ended so we
            # no longer have a need for these supporting temporary layers
            QgsProject.instance().removeMapLayer(selected_b)
            QgsProject.instance().removeMapLayers(layers_to_be_deleted)

            # Add a result layer into which the separately selected corner
            # points will be combined
            result_layer = self._create_temp_layer(9999)

            result_layer.startEditing()

            flat_list = [element for sublist in selected_corners for element in sublist]
            self._add_points_to_layer(flat_list, result_layer, 9999)

            self.update_layer(result_layer)

            # Save the corner point features to the file user has chosen.
            # If such file path does not exist, add combined result layer to
            # the map as a temporary scratch layer
            output_path = self.ui.get_output_file_path()
            if output_path == "":
                QgsProject.instance().addMapLayer(result_layer)
            else:
                write_output_to_file(result_layer, output_path)

            iface.setActiveLayer(old_active_layer)

    def _run_initial_checks(self) -> bool:
        """Checks that the selections made are applicable."""

        selected_layer = iface.activeLayer()

        if isinstance(selected_layer, QgsVectorLayer) and selected_layer.isSpatial():
            pass
        else:
            log_warning("Please select a valid vector layer")
            return False

        if selected_layer.geometryType() == QgsWkbTypes.LineGeometry:

            if len(selected_layer.selectedFeatures()) != 1:
                log_warning("Please select one line feature")
                return False

            if QgsWkbTypes.isSingleType(
                list(selected_layer.getFeatures())[0].geometry().wkbType()
            ):
                pass
            else:
                log_warning(
                    "Please select a line layer with "
                    "LineString geometries (instead "
                    "of MultiLineString geometries)"
                )
                return False

            temp_layer = selected_layer.materialize(
                QgsFeatureRequest().setFilterFids(selected_layer.selectedFeatureIds())
            )
            params1 = {"INPUT": temp_layer, "OUTPUT": "memory:"}
            vertices = processing.run("native:extractvertices", params1)
            vertices_layer = vertices["OUTPUT"]

            if vertices_layer.featureCount() > 2:
                log_warning("Please use Explode line(s) tool first!")
                return False

        elif selected_layer.geometryType() == QgsWkbTypes.PointGeometry:

            if len(selected_layer.selectedFeatures()) != 2:
                log_warning(
                    "Please select two points in order to explicitly define a line feature"
                )
                return False

            if QgsWkbTypes.isSingleType(
                list(selected_layer.getFeatures())[0].geometry().wkbType()
            ):
                pass
            else:
                log_warning(
                    "Please select a point layer with "
                    "Point geometries (instead "
                    "of MultiPoint geometries)"
                )
                return False
        else:
            log_warning("Please select a point or line layer")
            return False

        return True

    def _get_line_coords(
        self,
        start_point: QgsMapToolEmitPoint,
    ) -> List[Decimal]:
        """Store the coordinates of the selected line feature."""

        if self.iface.activeLayer().geometryType() == QgsWkbTypes.LineGeometry:
            selected_line_geometry = (
                self.iface.activeLayer().selectedFeatures()[0].geometry().asPolyline()
            )

            # Checks that the coordinate values get stored in the correct order
            if (
                QgsGeometry.fromPointXY(QgsPointXY(selected_line_geometry[0])).equals(
                    QgsGeometry.fromPointXY(
                        QgsPointXY(float(start_point[0]), float(start_point[1]))
                    )
                )
                is True
            ):
                point1 = QgsPointXY(selected_line_geometry[0])
                point2 = QgsPointXY(selected_line_geometry[-1])
            elif (
                QgsGeometry.fromPointXY(QgsPointXY(selected_line_geometry[-1])).equals(
                    QgsGeometry.fromPointXY(
                        QgsPointXY(float(start_point[0]), float(start_point[1]))
                    )
                )
                is True
            ):
                point1 = QgsPointXY(selected_line_geometry[-1])
                point2 = QgsPointXY(selected_line_geometry[0])
            else:
                log_warning(
                    "Please select start or end point of the "
                    "selected property boundary line."
                )
                return []

            line_coords = [
                Decimal(point1.x()),
                Decimal(point1.y()),
                Decimal(point2.x()),
                Decimal(point2.y()),
            ]
        else:
            # Checks which of the selected points the user clicks on
            if (
                self.iface.activeLayer()
                .selectedFeatures()[0]
                .geometry()
                .equals(
                    QgsGeometry.fromPointXY(
                        QgsPointXY(float(start_point[0]), float(start_point[1]))
                    )
                )
                is True
            ):
                point1 = (
                    self.iface.activeLayer().selectedFeatures()[0].geometry().asPoint()
                )
                point2 = (
                    self.iface.activeLayer().selectedFeatures()[1].geometry().asPoint()
                )
            elif (
                self.iface.activeLayer()
                .selectedFeatures()[1]
                .geometry()
                .equals(
                    QgsGeometry.fromPointXY(
                        QgsPointXY(float(start_point[0]), float(start_point[1]))
                    )
                )
                is True
            ):
                point1 = (
                    self.iface.activeLayer().selectedFeatures()[1].geometry().asPoint()
                )
                point2 = (
                    self.iface.activeLayer().selectedFeatures()[0].geometry().asPoint()
                )
            else:
                log_warning(
                    "Please select start or end point of the "
                    "selected property boundary line."
                )
                return []

            line_coords = [
                Decimal(point1.x()),
                Decimal(point1.y()),
                Decimal(point2.x()),
                Decimal(point2.y()),
            ]

        return line_coords

    @staticmethod
    def _calculate_parameters(
        line_coords: List[Decimal],
        a_measure: Decimal,
    ) -> List[Decimal]:
        """Calculate values for a, b and c parameters."""

        a = (
            (line_coords[2]) ** Decimal("2.0")
            - Decimal("2.0") * line_coords[0] * line_coords[2]
            + (line_coords[0]) ** Decimal("2.0")
            + (line_coords[3]) ** Decimal("2.0")
            - Decimal("2.0") * line_coords[1] * line_coords[3]
            + (line_coords[1]) ** Decimal("2.0")
        )
        b = (
            -Decimal("2.0") * (line_coords[2]) ** Decimal("2.0") * line_coords[0]
            + Decimal("4.0") * (line_coords[0]) ** Decimal("2.0") * line_coords[2]
            - Decimal("2.0") * (line_coords[0]) ** Decimal("3.0")
            - Decimal("2.0") * (line_coords[3]) ** Decimal("2.0") * line_coords[0]
            + Decimal("4.0") * line_coords[0] * line_coords[1] * line_coords[3]
            - Decimal("2.0") * (line_coords[1]) ** Decimal("2.0") * line_coords[0]
        )
        c = (
            -(a_measure ** Decimal("2.0")) * (line_coords[2]) ** Decimal("2.0")
            + Decimal("2.0")
            * a_measure ** Decimal("2.0")
            * line_coords[0]
            * line_coords[2]
            - a_measure ** Decimal("2.0") * (line_coords[0]) ** Decimal("2.0")
            + (line_coords[0]) ** Decimal("2.0") * (line_coords[2]) ** Decimal("2.0")
            - Decimal("2.0") * (line_coords[0]) ** Decimal("3.0") * line_coords[2]
            + (line_coords[0]) ** Decimal("4.0")
            + (line_coords[3]) ** Decimal("2.0") * (line_coords[0]) ** Decimal("2.0")
            - Decimal("2.0")
            * line_coords[1]
            * line_coords[3]
            * (line_coords[0]) ** Decimal("2.0")
            + (line_coords[1]) ** Decimal("2.0") * (line_coords[0]) ** Decimal("2.0")
        )
        parameter_values = [a, b, c]

        return parameter_values

    @staticmethod
    def _locate_point_a(
        line_coords: List[Decimal],
        parameters: List[Decimal],
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
            log_warning(
                "Point A cannot be found on the property boundary line (or its extension)!"
            )
            return []

        # Coordinates of the first possible solution for point_a
        x_a1 = (-parameters[1] + Decimal(math.sqrt(sqrt_in))) / (
            Decimal("2.0") * parameters[0]
        )

        y_a1 = (
            x_a1 * line_coords[3]
            - line_coords[0] * line_coords[3]
            - x_a1 * line_coords[1]
            + line_coords[2] * line_coords[1]
        ) / (line_coords[2] - line_coords[0])

        # Coordinates of the second possible solution for point_a
        x_a2 = (-parameters[1] - Decimal(math.sqrt(sqrt_in))) / (
            Decimal("2.0") * parameters[0]
        )

        y_a2 = (
            x_a2 * line_coords[3]
            - line_coords[0] * line_coords[3]
            - x_a2 * line_coords[1]
            + line_coords[2] * line_coords[1]
        ) / (line_coords[2] - line_coords[0])

        # Check that the solution points lie in the
        # map canvas extent
        if not check_within_canvas((float(x_a1), float(y_a1))):
            log_warning("Point A opt 1 lies outside of the map canvas!")
            return []

        if not check_within_canvas((float(x_a2), float(y_a2))):
            log_warning("Point A opt 2 lies outside of the map canvas!")
            return []

        points_a_res = [x_a1, y_a1, x_a2, y_a2]

        return points_a_res

    @staticmethod
    def _locate_point_b(
        line_coords: List[Decimal],
        point_a: List[Decimal],
        b_measure: Decimal,
    ) -> List[Decimal]:
        """Determine the coordinates of point_b belonging to the line which is
        orthogonal to the property boundary line and goes through point_a."""

        # Parameters related to equation of property boundary line in standard form
        a2 = line_coords[1] - line_coords[3]
        b2 = line_coords[2] - line_coords[0]
        c2 = line_coords[3] * line_coords[0] - line_coords[1] * line_coords[2]

        x_a = point_a[0]
        y_a = point_a[1]

        # Coordinates of the first possible solution point
        x_b1 = (
            line_coords[3]
            * b_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            - line_coords[1]
            * b_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            - b2 * y_a * line_coords[3]
            + b2 * y_a * line_coords[1]
            - b2 * x_a * line_coords[2]
            + b2 * x_a * line_coords[0]
            - c2 * line_coords[3]
            + c2 * line_coords[1]
        ) / (
            a2 * line_coords[3]
            - a2 * line_coords[1]
            - b2 * line_coords[2]
            + b2 * line_coords[0]
        )

        y_b1 = (
            y_a * line_coords[3]
            - y_a * line_coords[1]
            - Decimal(x_b1) * line_coords[2]
            + Decimal(x_b1) * line_coords[0]
            + x_a * line_coords[2]
            - x_a * line_coords[0]
        ) / (line_coords[3] - line_coords[1])

        # Coordinates of the second possible solution point
        x_b2 = (
            -line_coords[3]
            * b_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            + line_coords[1]
            * b_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            - b2 * y_a * line_coords[3]
            + b2 * y_a * line_coords[1]
            - b2 * x_a * line_coords[2]
            + b2 * x_a * line_coords[0]
            - c2 * line_coords[3]
            + c2 * line_coords[1]
        ) / (
            a2 * line_coords[3]
            - a2 * line_coords[1]
            - b2 * line_coords[2]
            + b2 * line_coords[0]
        )

        y_b2 = (
            y_a * line_coords[3]
            - y_a * line_coords[1]
            - Decimal(x_b2) * line_coords[2]
            + Decimal(x_b2) * line_coords[0]
            + x_a * line_coords[2]
            - x_a * line_coords[0]
        ) / (line_coords[3] - line_coords[1])

        # Check that the solution points lie in the map canvas extent
        if not check_within_canvas((float(x_b1), float(y_b1))):
            log_warning("Point B opt 1 lies outside of the map canvas!")
            return []

        if not check_within_canvas((float(x_b2), float(y_b2))):
            log_warning("Point B opt 2 lies outside of the map canvas!")
            return []

        points_b_res = [x_b1, y_b1, x_b2, y_b2]

        return points_b_res

    @staticmethod
    def _locate_point_c(
        c_measure: Decimal,
        point_a: List[Decimal],
        point_b: List[Decimal],
    ) -> List[Decimal]:
        """Determine the coordinates of corner point 2."""

        a = Decimal("1.0") + (
            (point_b[1] - point_a[1]) / (point_b[0] - point_a[0])
        ) ** Decimal("2.0")
        b = (
            -Decimal("2.0") * point_b[0]
            - Decimal("2.0")
            * point_a[0]
            * ((point_b[1] - point_a[1]) / (point_b[0] - point_a[0])) ** Decimal("2.0")
            + Decimal("2.0")
            * ((point_b[1] - point_a[1]) / (point_b[0] - point_a[0]))
            * (point_a[1] - point_b[1])
        )
        c = (
            -(c_measure ** Decimal("2.0"))
            + (point_a[1] - point_b[1]) ** Decimal("2.0")
            - Decimal("2.0")
            * ((point_b[1] - point_a[1]) / (point_b[0] - point_a[0]))
            * (point_a[1] - point_b[1])
            * point_a[0]
            + point_b[0] ** Decimal("2.0")
            + point_a[0] ** Decimal("2.0")
            * ((point_b[1] - point_a[1]) / (point_b[0] - point_a[0])) ** Decimal("2.0")
        )

        # Check that the solution exists
        sqrt_in = b ** Decimal("2.0") - Decimal("4.0") * a * c
        if sqrt_in < 0.0 or a == 0.0:
            log_warning("Solution point does not exist!")
            return []

        # Computing the possible coordinates for corner point 2
        x_c1 = (-b + Decimal(math.sqrt(sqrt_in))) / (Decimal("2.0") * a)

        y_c1 = ((point_b[1] - point_a[1]) / (point_b[0] - point_a[0])) * (
            x_c1 - point_a[0]
        ) + point_a[1]

        # Computing the possible coordinates for corner point 2
        x_c2 = (-b - Decimal(math.sqrt(sqrt_in))) / (Decimal("2.0") * a)

        y_c2 = ((point_b[1] - point_a[1]) / (point_b[0] - point_a[0])) * (
            x_c2 - point_a[0]
        ) + point_a[1]

        # Let's find out which solution point has more distance to
        # point_b. Assumption: the corner point located via a and b
        # measures will be the closest to the boundary line
        d1 = math.sqrt(
            (x_c1 - point_a[0]) ** Decimal("2.0")
            + (y_c1 - point_a[1]) ** Decimal("2.0")
        )
        d2 = math.sqrt(
            (x_c2 - point_a[0]) ** Decimal("2.0")
            + (y_c2 - point_a[1]) ** Decimal("2.0")
        )

        if d1 < d2:
            point_c_res = [x_c2, y_c2]
        else:
            point_c_res = [x_c1, y_c1]

        return point_c_res

    @staticmethod
    def _locate_point_d(
        d_measure: Decimal,
        selected_corners: List[List[Decimal]],
    ) -> List[Decimal]:
        """Determine the coordinates of the corner point belonging to the line
        which is orthogonal to the line determined by two latest corner points."""

        point1 = selected_corners[-2]
        point2 = selected_corners[-1]

        # Analytical geometry: two-point form of a line
        a2 = (point2[1] - point1[1]) / (point2[0] - point1[0])
        b2 = Decimal("-1.0")
        c2 = point1[1] - ((point2[1] - point1[1]) / (point2[0] - point1[0])) * point1[0]

        # Coordinates of the first possible solution point
        x_d1 = (
            point2[1]
            * d_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            - point1[1]
            * d_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            - b2 * point2[1] * point2[1]
            + b2 * point2[1] * point1[1]
            - b2 * point2[0] ** Decimal("2.0")
            + b2 * point2[0] * point1[0]
            - c2 * point2[1]
            + c2 * point1[1]
        ) / (a2 * point2[1] - a2 * point1[1] - b2 * point2[0] + b2 * point1[0])

        y_d1 = (
            point2[1] ** Decimal("2.0")
            - point2[1] * point1[1]
            - Decimal(x_d1) * point2[0]
            + Decimal(x_d1) * point1[0]
            + point2[0] ** Decimal("2.0")
            - point2[0] * point1[0]
        ) / (point2[1] - point1[1])

        # Coordinates of the second possible solution point
        x_d2 = (
            -point2[1]
            * d_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            + point1[1]
            * d_measure
            * Decimal(math.sqrt(a2 ** Decimal("2.0") + b2 ** Decimal("2.0")))
            - b2 * point2[1] ** Decimal("2.0")
            + b2 * point2[1] * point1[1]
            - b2 * point2[0] ** Decimal("2.0")
            + b2 * point2[0] * point1[0]
            - c2 * point2[1]
            + c2 * point1[1]
        ) / (a2 * point2[1] - a2 * point1[1] - b2 * point2[0] + b2 * point1[0])

        y_d2 = (
            point2[1] ** Decimal("2.0")
            - point2[1] * point1[1]
            - Decimal(x_d2) * point2[0]
            + Decimal(x_d2) * point1[0]
            + point2[0] ** Decimal("2.0")
            - point2[0] * point1[0]
        ) / (point2[1] - point1[1])

        # Check that the corner points lie in the map canvas extent
        if not check_within_canvas((float(x_d1), float(y_d1))):
            log_warning("Solution point 1 lies outside of the map canvas!")
            return []

        if not check_within_canvas((float(x_d2), float(y_d2))):
            log_warning("Solution point 2 lies outside of the map canvas!")
            return []

        points_d_res = [x_d1, y_d1, x_d2, y_d2]

        return points_d_res

    def _create_temp_layer(
        self,
        temp: int,
    ) -> QgsVectorLayer:
        """Creates a QgsVectorLayer for storing optional points."""

        layer = QgsVectorLayer("Point", "temp", "memory")
        crs = iface.activeLayer().crs()
        layer.setCrs(crs)
        options_layer_dataprovider = layer.dataProvider()
        options_layer_dataprovider.addAttributes([QgsField("id", QVariant.String)])
        layer.updateFields()

        if temp == 9999:
            options_layer_dataprovider.addAttributes(
                [
                    QgsField("xcoord", QVariant.Double),
                    QgsField("ycoord", QVariant.Double),
                ]
            )
            layer.updateFields()
            layer.setName(tr("Corner points"))
        elif temp < -1:
            layer.setName(tr(f"Corner {-1 * temp}"))
        elif temp == -1:
            layer.setName(tr("Corner 1"))
        elif temp == 0:
            layer.setName(tr("Point A options"))
        elif temp == 1:
            layer.setName(tr("Point B options"))
        elif temp == 2:
            layer.setName(tr("Corner 2"))
        else:
            layer.setName(tr(f"Corner {temp} options"))
        layer.renderer().symbol().setSize(2)
        layer.renderer().symbol().setColor(QColor.fromRgb(250, 0, 0))
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

        return layer

    @staticmethod
    def _add_points_to_layer(
        point_coordinates: List[Decimal],
        options_layer: QgsVectorLayer,
        temp: int,
    ) -> None:
        """Adds new optional solution points to option point A
        layer, returns list of IDs of added features."""

        if temp == 9999:
            x_coords = []
            y_coords = []
            for j in range(len(point_coordinates)):
                if j % 2 == 0:
                    x_coords.append(float(point_coordinates[j]))
                else:
                    y_coords.append(float(point_coordinates[j]))
        else:
            if len(point_coordinates) > 2:
                x_coords = [float(point_coordinates[0]), float(point_coordinates[2])]
                y_coords = [float(point_coordinates[1]), float(point_coordinates[3])]
            else:
                x_coords = [float(point_coordinates[0])]
                y_coords = [float(point_coordinates[1])]

        point_geometries: List[QgsPointXY] = []
        coordinates_iterator = iter(point_coordinates)
        for coordinate in coordinates_iterator:
            point_geometries.append(
                QgsPointXY(float(coordinate), float(next(coordinates_iterator)))
            )

        for i, point in enumerate(point_geometries):
            point_feature = QgsFeature()
            point_feature.setGeometry(QgsGeometry.fromPointXY(point))
            if temp == 9999:
                point_feature.setAttributes(
                    [
                        f"Corner point {i + 1}",
                        round(x_coords[i], 3),
                        round(y_coords[i], 3),
                    ]
                )
            elif temp < 0:
                point_feature.setAttributes([f"Corner point {-1 * temp} opt {i + 1}"])
            elif temp == 0:
                point_feature.setAttributes([f"Point A opt {i + 1}"])
            elif temp == 1:
                point_feature.setAttributes([f"Point B opt {i + 1}"])
            else:
                point_feature.setAttributes([f"Corner point {temp} opt {i + 1}"])
            options_layer.addFeature(point_feature)

        return

    @staticmethod
    def _add_point_to_layer(
        point_coordinates: List[Decimal],
        options_layer: QgsVectorLayer,
        temp: int,
    ) -> None:
        """Adds new option points to option point layer,
        returns list of IDs of added features."""

        x_coord = float(point_coordinates[0])
        y_coord = float(point_coordinates[1])

        point_geometry = QgsPointXY(x_coord, y_coord)

        point_feature = QgsFeature()
        point_feature.setGeometry(QgsGeometry.fromPointXY(point_geometry))

        if temp == 0:
            point_feature.setAttributes(["Corner 2"])
        elif temp == -1:
            point_feature.setAttributes(["Corner 1"])
        else:
            point_feature.setAttributes([f"Corner {-1 * temp}"])

        options_layer.addFeature(point_feature)

        return

    @staticmethod
    def _generate_option_point_messagebox(corner_point_idx: int) -> QMessageBox:
        """Creates and returns message box object."""

        message_box = QMessageBox()
        message_box.setText(
            tr(f"Do you want to choose option 1 for corner point {corner_point_idx}?")
        )
        message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        return message_box
