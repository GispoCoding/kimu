from decimal import Decimal
from typing import List, Tuple

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsField,
    QgsFillSymbol,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgisInterface, QgsMapToolEmitPoint
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.utils import iface

from ..qgis_plugin_tools.tools.i18n import tr
from ..ui.line_circle_dockwidget import LineCircleDockWidget
from .click_tool import ClickTool
from .geodetic_objects import Circle
from .select_tool import SelectTool
from .tool_functions import (
    check_within_canvas,
    construct_geodetic_objects_from_selections,
    create_intersecting_object_pairs,
    log_warning,
    select_intersection_point,
    set_and_format_labels,
    solve_all_intersections,
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
            if not (isinstance(layer, QgsVectorLayer) and layer.isSpatial()):
                continue

            for feature in layer.selectedFeatures():

                # Line geometries
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

                # Point geometry
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
        self.run(event)

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
        QgsProject.instance().addMapLayer(result_layer)
        return result_layer

    def _create_buffer(self, centroid: List[Decimal]) -> QgsVectorLayer:
        buffer_layer = QgsVectorLayer("Polygon", "pointbuffer", "memory")
        buffer_layer.setCrs(self.crs)
        geom = QgsGeometry.fromPointXY(QgsPointXY(centroid[0], centroid[1]))
        buffer_feat = QgsFeature()
        buffer_geom = geom.buffer(self.ui.get_radius(), 10)
        buffer_feat.setGeometry(buffer_geom)
        buffer_layer.startEditing()
        buffer_layer.dataProvider().addFeature(buffer_feat)

        buffer_layer.setName(tr("Intersecting circle"))
        symbol = QgsFillSymbol.createSimple(
            {
                'color': 'transparent',
                'outline_color': 'blue',
                'outline_width': 0.5,
                'outline_style': 'dot'
            }
        )
        buffer_layer.renderer().setSymbol(symbol)
        buffer_layer.triggerRepaint()
        buffer_layer.commitChanges()
        QgsProject.instance().addMapLayer(buffer_layer)
        return buffer_layer

    def _add_point_to_layer(
        self, layer: QgsVectorLayer, coords: Tuple[float, float],
        circle: Circle, id: str
    ) -> QgsFeature:
        intersection_point = QgsPointXY(coords[0], coords[1])
        point_feature = QgsFeature()
        point_feature.setGeometry(QgsGeometry.fromPointXY(intersection_point))
        x0, y0 = float(circle.x0), float(circle.y0)
        point_feature.setAttributes([id,
                                     round(coords[0], 3),
                                     round(coords[1], 3),
                                     round(x0, 3),
                                     round(y0, 3)]
                                    )
        layer.dataProvider().addFeature(point_feature)
        layer.updateExtents()
        layer.triggerRepaint()
        return point_feature

    def _add_all_points(
        self, coords: List[Tuple[float, float]],
        circle: Circle, result_layer: QgsVectorLayer
    ) -> List[QgsFeature]:
        if len(coords) == 1:
            point = self._add_point_to_layer(
                result_layer, coords[0], circle, "Intersection point"
            )
            return [point]
        else:
            point_features = []
            for i, coord in enumerate(coords):
                point = self._add_point_to_layer(result_layer, coord, circle, f"Opt {i+1}")
                point_features.append(point)
            return point_features

    def run(self, event: QgsMapToolEmitPoint) -> None:
        if not self._run_initial_checks():
            return

        old_active_layer = iface.activeLayer()
        # Snap the click to the closest point feature available.
        # Note that your QGIS's snapping options have on effect
        # on which objects / vertexes the tool will snap and
        # get the coordinates of the point to be used as a circle centroid
        centroid = ClickTool(self.iface).activate(event)
        x0, y0 = centroid[0], centroid[1]
        r = Decimal(self.ui.get_radius())
        circle = Circle(x0, y0, r)

        # Call for function extracting coordinate values attached to
        # the line feature to be intersected with a circle
        selected_geodetic_objects = construct_geodetic_objects_from_selections()
        selected_geodetic_objects.append(circle)

        pairs = create_intersecting_object_pairs(selected_geodetic_objects)
        all_i_coords = solve_all_intersections(pairs)
        if len(all_i_coords) == 0:
            log_warning("No intersection points!")
            return

        coords_in_extent = [
            coords for coords in all_i_coords if check_within_canvas(coords)
        ]
        if len(coords_in_extent) == 0:
            log_warning(
                "All potential intersection points lie outside of the map canvas!"
            )
            return

        result_layer = self._create_result_layer()
        added_points = self._add_all_points(coords_in_extent, circle, result_layer)
        set_and_format_labels(result_layer)
        if len(added_points) > 1:
            buffer_layer = self._create_buffer(centroid)
            select_intersection_point(result_layer, len(added_points))
            QgsProject.instance().removeMapLayer(buffer_layer)

        result_layer.commitChanges()
        iface.vectorLayerTools().stopEditing(result_layer)

        # Ask if user wants to save to file
        output_path = self.ui.get_output_file_path()
        if output_path != "":
            write_output_to_file(result_layer, output_path)
            QgsProject.instance().removeMapLayer(result_layer)

        iface.setActiveLayer(old_active_layer)
