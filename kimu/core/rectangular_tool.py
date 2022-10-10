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
from qgis.gui import QgsMapToolEmitPoint
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
    def __init__(self, dock_widget: RectangularDockWidget) -> None:
        super().__init__(iface)
        self.ui: RectangularDockWidget = dock_widget

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

            # Determine parameter values for solving the quadratic equation in hand
            parameters = self._calculate_parameters(selected_line_coords)

            # a_measure is given in crs units (meters for EPSG: 3067)
            if Decimal(self.ui.get_a_measure()) != Decimal("0.000"):
                # Let's locate alternative solutions for point A
                try:
                    points_a = self._locate_point_a(selected_line_coords, parameters)
                except IndexError:
                    return
            else:
                points_a = [selected_line_coords[0], selected_line_coords[1]]

            if points_a == []:
                LOGGER.warning(
                    tr("Search of the point A was failed!"),
                    extra={"details": ""},
                )
                return

            # Let's show user the solution points and let the user
            # to decide which is the desired one
            option_points_layer_a = self._create_optional_points_layer(1)
            QgsProject.instance().addMapLayer(option_points_layer_a)

            option_points_layer_a.startEditing()
            self._add_option_points_to_layer_a(points_a, option_points_layer_a)

            # a_measure is given in crs units (meters for EPSG: 3067)
            if Decimal(self.ui.get_a_measure()) > Decimal("0.000"):
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

            option_points_layer_a.commitChanges()
            iface.vectorLayerTools().stopEditing(option_points_layer_a)
            # Let's remove layer scratch layer related to point A alternatives
            # since we have no use for this layer any more
            QgsProject.instance().removeMapLayer(option_points_layer_a)

            # Let's create a scratch layer for storing options for
            # every mapped corner point
            option_points_layer = self._create_optional_points_layer(0)
            QgsProject.instance().addMapLayer(option_points_layer)

            # b_measure is given in crs units (meters for EPSG: 3067)
            if Decimal(self.ui.get_b_measure()) != Decimal("0.000"):
                # Let's locate alternative solutions for point B
                try:
                    points_b = self._locate_point_b(selected_line_coords, point_a)
                except IndexError:
                    return
            else:
                points_b = point_a.copy()

            if points_b == []:
                LOGGER.warning(
                    tr("Search of the point B was failed!"),
                    extra={"details": ""},
                )
                return

            option_points_layer.startEditing()
            option_point_ids = self._add_option_points_to_layer(
                points_b, option_points_layer
            )

            # b_measure is given in crs units (meters for EPSG: 3067)
            if Decimal(self.ui.get_b_measure()) > Decimal("0.000"):
                # Let's ask the user which is the desired solution point
                message_box = self._generate_option_point_messagebox(1)
                ret = message_box.exec()
                if ret == QMessageBox.Yes:
                    # Let's add the point user chose to the list of
                    # selected corner points
                    selected_corners = [[points_b[0], points_b[1]]]
                    # Let's add the id of not chosen point to the
                    # list of features we will delete later
                    option_points_to_delete = [option_point_ids[1]]
                else:
                    selected_corners = [[points_b[2], points_b[3]]]
                    option_points_to_delete = [option_point_ids[0]]
            else:
                # Let's add the point user chose to the list of
                # selected corner points
                selected_corners = [[points_b[0], points_b[1]]]
                option_points_to_delete = []

            point_b = selected_corners[0]

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
                            LOGGER.warning(
                                tr("Search of the second corner point was failed!"),
                                extra={"details": ""},
                            )
                            return

                        option_point_ids += self._add_option_points_to_layer(
                            point_c, option_points_layer, selected_corners
                        )
                        selected_corners.append([point_c[0], point_c[1]])
                        continue

                    # Map the rest of the rectangular corner points (they will be located
                    # perpendicularly with respect to the line feature connecting two last
                    # elements of the selected corners list)
                    new_corner_points = self._locate_point_d(
                        c_measure, selected_corners
                    )

                    if new_corner_points == []:
                        LOGGER.warning(
                            tr(
                                "Search of the corner point related to an element in"
                                " the given building wall width list was failed!"
                            ),
                            extra={"details": ""},
                        )
                        return

                    option_point_ids += self._add_option_points_to_layer(
                        new_corner_points, option_points_layer, selected_corners
                    )

                    message_box = self._generate_option_point_messagebox(
                        len(selected_corners) + 1
                    )
                    ret = message_box.exec()
                    # Consider the signal and check if point already exists in selected
                    # corners list in order to avoid duplicates
                    if (
                        ret == QMessageBox.No
                        and [new_corner_points[2], new_corner_points[3]]
                        not in selected_corners
                    ):
                        if i == 1:
                            selected_corners.append(
                                [new_corner_points[2], new_corner_points[3]]
                            )
                            if len(points_b) > 2:
                                option_points_to_delete.append(option_point_ids[3])
                            else:
                                option_points_to_delete.append(option_point_ids[2])
                        else:
                            selected_corners.append(
                                [new_corner_points[2], new_corner_points[3]]
                            )
                            if len(points_b) > 2:
                                option_points_to_delete.append(
                                    option_point_ids[2 + (i * 2 - 1)]
                                )
                            else:
                                option_points_to_delete.append(
                                    option_point_ids[1 + (i * 2 - 1)]
                                )
                    elif (
                        ret == QMessageBox.Yes
                        and [new_corner_points[0], new_corner_points[1]]
                        not in selected_corners
                    ):
                        if i == 1:
                            selected_corners.append(
                                [new_corner_points[0], new_corner_points[1]]
                            )
                            if len(points_b) > 2:
                                option_points_to_delete.append(option_point_ids[4])
                            else:
                                option_points_to_delete.append(option_point_ids[3])
                        else:
                            selected_corners.append(
                                [new_corner_points[0], new_corner_points[1]]
                            )
                            if len(points_b) > 2:
                                option_points_to_delete.append(
                                    option_point_ids[2 + (i * 2)]
                                )
                            else:
                                option_points_to_delete.append(
                                    option_point_ids[1 + (i * 2)]
                                )
                    else:
                        pass

            # Delete the features user did not select
            if option_points_to_delete != []:
                option_points_layer.deleteFeatures(option_points_to_delete)
            option_points_layer.commitChanges()
            iface.vectorLayerTools().stopEditing(option_points_layer)

            # Save the mapped point features to the file user has chosen
            if self.ui.get_output_file_path() != "":
                self._write_output_to_file(option_points_layer)
                QgsProject.instance().removeMapLayer(option_points_layer)

    def _get_line_coords(self, start_point: QgsMapToolEmitPoint) -> List[Decimal]:
        """Store the coordinates of the selected line feature"""
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
                LOGGER.warning(
                    tr(
                        "Please select start or end point of the "
                        "selected property boundary line."
                    ),
                    extra={"details": ""},
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
                LOGGER.warning(
                    tr(
                        "Please select start or end point of the "
                        "selected property boundary line."
                    ),
                    extra={"details": ""},
                )
                return []

            line_coords = [
                Decimal(point1.x()),
                Decimal(point1.y()),
                Decimal(point2.x()),
                Decimal(point2.y()),
            ]

        return line_coords

    def _calculate_parameters(self, line_coords: List[Decimal]) -> List[Decimal]:
        """Calculate values for a, b and c parameters."""

        # a_measure is given in crs units (meters for EPSG: 3067)
        a_measure = Decimal(self.ui.get_a_measure())
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
        result = [a, b, c]

        return result

    @staticmethod
    def _locate_point_a(
        line_coords: List[Decimal], parameters: List[Decimal]
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
                tr(
                    "Point A cannot be found on the property boundary"
                    " line (or its extension)!"
                ),
                extra={"details": ""},
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
        extent = iface.mapCanvas().extent()

        if (
            x_a1 < extent.xMinimum()
            or x_a1 > extent.xMaximum()
            or y_a1 < extent.yMinimum()
            or y_a1 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Point A opt 1 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return []

        if (
            x_a2 < extent.xMinimum()
            or x_a2 > extent.xMaximum()
            or y_a2 < extent.yMinimum()
            or y_a2 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Point A opt 2 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return []

        points_a_res = [x_a1, y_a1, x_a2, y_a2]

        return points_a_res

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

        # Check that the solution points lie in the
        # map canvas extent
        extent = iface.mapCanvas().extent()

        if (
            x_b1 < extent.xMinimum()
            or x_b1 > extent.xMaximum()
            or y_b1 < extent.yMinimum()
            or y_b1 > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Point B opt 1 lies outside of the map canvas!"),
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
                tr("Point B opt 2 lies outside of the map canvas!"),
                extra={"details": ""},
            )
            return []

        points_b_res = [x_b1, y_b1, x_b2, y_b2]

        return points_b_res

    def _create_optional_points_layer(self, a_layer: int) -> QgsVectorLayer:
        """Creates a QgsVectorLayer for storing optional points."""
        layer = QgsVectorLayer("Point", "temp", "memory")
        crs = self.layer.crs()
        layer.setCrs(crs)
        options_layer_dataprovider = layer.dataProvider()
        options_layer_dataprovider.addAttributes(
            [
                QgsField("id", QVariant.String),
                QgsField("xcoord", QVariant.Double),
                QgsField("ycoord", QVariant.Double),
            ]
        )
        layer.updateFields()
        if a_layer == 1:
            layer.setName(tr("Point A options"))
        else:
            layer.setName(tr("Corner point options"))
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
    def _add_option_points_to_layer_a(
        point_coordinates_a: List[Decimal],
        options_layer_a: QgsVectorLayer,
    ) -> None:
        """Adds new optional solution points to option point A
        layer, returns list of IDs of added features."""
        if len(point_coordinates_a) > 2:
            x_coords = [float(point_coordinates_a[0]), float(point_coordinates_a[2])]
            y_coords = [float(point_coordinates_a[1]), float(point_coordinates_a[3])]
        else:
            x_coords = [float(point_coordinates_a[0])]
            y_coords = [float(point_coordinates_a[1])]

        point_geometries_a: List[QgsPointXY] = []
        coordinates_iterator_a = iter(point_coordinates_a)
        for coordinate_a in coordinates_iterator_a:
            point_geometries_a.append(
                QgsPointXY(float(coordinate_a), float(next(coordinates_iterator_a)))
            )

        for i, point_a in enumerate(point_geometries_a):
            point_feature_a = QgsFeature()
            point_feature_a.setGeometry(QgsGeometry.fromPointXY(point_a))
            point_feature_a.setAttributes(
                [f"Point A opt {i + 1}", round(x_coords[i], 3), round(y_coords[i], 3)]
            )
            options_layer_a.addFeature(point_feature_a)

        options_layer_a.updateExtents()
        options_layer_a.triggerRepaint()

        return

    @staticmethod
    def _add_option_points_to_layer(
        point_coordinates: List[Decimal],
        options_layer: QgsVectorLayer,
        selected_corners: List[List[Decimal]] = None,
    ) -> List[int]:
        """Adds new option points to option point layer,
        returns list of IDs of added features."""
        if not selected_corners:
            selected_corners = []

        if len(selected_corners) == 1 or len(point_coordinates) <= 2:
            x_coords = [float(point_coordinates[0])]
            y_coords = [float(point_coordinates[1])]
        else:
            x_coords = [float(point_coordinates[0]), float(point_coordinates[2])]
            y_coords = [float(point_coordinates[1]), float(point_coordinates[3])]

        point_geometries: List[QgsPointXY] = []
        point_ids: List[int] = []
        coordinates_iterator = iter(point_coordinates)
        for coordinate in coordinates_iterator:
            point_geometries.append(
                QgsPointXY(float(coordinate), float(next(coordinates_iterator)))
            )

        for i, point in enumerate(point_geometries):
            point_feature = QgsFeature()
            point_feature.setGeometry(QgsGeometry.fromPointXY(point))

            if len(selected_corners) == 0:
                point_feature.setAttributes(
                    [
                        f"Point B opt {i + 1}",
                        round(x_coords[i], 3),
                        round(y_coords[i], 3),
                    ]
                )
            elif len(selected_corners) == 1:
                point_feature.setAttributes(
                    ["Corner 2", round(x_coords[i], 3), round(y_coords[i], 3)]
                )
            else:
                point_feature.setAttributes(
                    [
                        f"Corner {len(selected_corners) + 1} opt {i + 1}",
                        round(x_coords[i], 3),
                        round(y_coords[i], 3),
                    ]
                )

            options_layer.addFeature(point_feature)
            point_ids.append(point_feature.id())

        options_layer.updateExtents()
        options_layer.triggerRepaint()

        return point_ids

    @staticmethod
    def _generate_option_point_messagebox(corner_point_idx: int) -> QMessageBox:
        """Creates and returns message box object"""
        message_box = QMessageBox()
        message_box.setText(
            tr(f"Do you want to choose option 1 for corner point {corner_point_idx}?")
        )
        message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        return message_box

    def _write_output_to_file(self, layer: QgsVectorLayer) -> None:
        """Writes the selected corner points to a spesifed file"""
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

    @staticmethod
    def _locate_point_c(
        c_measure: Decimal, point_a: List[Decimal], point_b: List[Decimal]
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
            LOGGER.warning(
                tr("Solution point does not exist!"),
                extra={"details": ""},
            )
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
        d_measure: Decimal, selected_corners: List[List[Decimal]]
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

        # Check that the corner points lie in the
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
