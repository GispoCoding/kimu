import math
from decimal import Decimal
from itertools import combinations
from typing import List, Tuple

from qgis.core import (
    QgsPalLayerSettings,
    QgsProject,
    QgsTextBufferSettings,
    QgsTextFormat,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
    QgsWkbTypes,
)
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtWidgets import QMessageBox, QPushButton
from qgis.utils import iface

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name
from .geodetic_objects import Arc, Circle, GeodeticObject, Line, Point

LOGGER = setup_logger(plugin_name())


def check_within_canvas(coords: Tuple[float, float]) -> bool:
    extent = iface.mapCanvas().extent()
    if (
        coords[0] >= extent.xMinimum()
        and coords[0] <= extent.xMaximum()
        and coords[1] >= extent.yMinimum()
        and coords[1] <= extent.yMaximum()
    ):
        return True
    else:
        return False


def check_not_parallel(line1_coords: Line, line2_coords: Line) -> bool:
    """Checks that the selected line features are not parallel."""
    slope1 = (line1_coords.y2 - line1_coords.y1) / (line1_coords.x2 - line1_coords.x1)
    slope2 = (line2_coords.y2 - line2_coords.y1) / (line2_coords.x2 - line2_coords.x1)
    if slope1 == slope2:
        log_warning("Lines are parallel; there is no intersection point!")
        return False
    return True


def four_points_to_lines(
    p: List[Point],
) -> List[Tuple[Line, Line]]:
    pair1 = (
        Line(p[0].x, p[1].x, p[0].y, p[1].y),
        Line(p[2].x, p[3].x, p[2].y, p[3].y),
    )
    pair2 = (
        Line(p[0].x, p[2].x, p[0].y, p[2].y),
        Line(p[1].x, p[3].x, p[1].y, p[3].y),
    )
    pair3 = (
        Line(p[0].x, p[3].x, p[0].y, p[3].y),
        Line(p[2].x, p[1].x, p[2].y, p[1].y),
    )
    return [pair1, pair2, pair3]


def create_intersecting_object_pairs(
    geodetic_objects: List[GeodeticObject], tangets: bool = False
) -> List[Tuple[GeodeticObject, GeodeticObject]]:

    intersecting_objects: List[GeodeticObject] = []
    points: List[Point] = []
    for geodetic_object in geodetic_objects:
        if isinstance(geodetic_object, Arc):
            if tangets:
                intersecting_objects.append(geodetic_object.start_point_tangent())
                intersecting_objects.append(geodetic_object.end_point_tangent())
            else:
                intersecting_objects.append(geodetic_object.as_circle())
        elif isinstance(geodetic_object, Line) or isinstance(geodetic_object, Circle):
            intersecting_objects.append(geodetic_object)
        elif isinstance(geodetic_object, Point):
            points.append(geodetic_object)
        else:
            raise Exception(f"Unknown object encountered: {type(geodetic_object)}")

    if len(points) == 2:
        new_line = Line(points[0].x, points[1].x, points[0].y, points[1].y)
        intersecting_objects.append(new_line)
    intersecting_object_pairs = list(combinations(intersecting_objects, 2))

    if len(points) == 4:
        points_to_lines = four_points_to_lines(points)
        intersecting_object_pairs += points_to_lines

    return intersecting_object_pairs


def solve_all_intersections(
    intersecting_object_pairs: List[Tuple[GeodeticObject, GeodeticObject]],
) -> List[Tuple[float, float]]:
    intersection_coords_list: List[Tuple[float, float]] = []
    for pair in intersecting_object_pairs:
        if isinstance(pair[0], Line) and isinstance(pair[1], Line):
            coords = solve_line_intersection(pair[0], pair[1])

        elif isinstance(pair[0], Circle) and isinstance(pair[1], Line):
            coords = solve_circle_and_line_intersections(pair[0], pair[1])

        elif isinstance(pair[0], Line) and isinstance(pair[1], Circle):
            coords = solve_circle_and_line_intersections(pair[1], pair[0])

        elif isinstance(pair[0], Circle) and isinstance(pair[1], Circle):
            coords = solve_circle_intersections(pair[0], pair[1])

        else:
            raise Exception(
                f"Unknown object encountered: {type(pair[0])} or {type(pair[1])}"
            )

        if coords is not None:
            intersection_coords_list += [
                (float(coord[0]), float(coord[1]))
                for coord in coords
                if coord is not None
            ]

    return intersection_coords_list


def solve_line_intersection(line1: Line, line2: Line) -> List[Tuple[Decimal, Decimal]]:
    xdiff = (line1.x1 - line1.x2, line2.x1 - line2.x2)
    ydiff = (line1.y1 - line1.y2, line2.y1 - line2.y2)

    def det_line(line: Line) -> Decimal:
        return line.x1 * line.y2 - line.y1 * line.x2

    def det(a: Tuple[Decimal, Decimal], b: Tuple[Decimal, Decimal]) -> Decimal:
        return a[0] * b[1] - a[1] * b[0]

    div = det(xdiff, ydiff)
    if div == 0:
        log_warning("Lines are parallel; there is no intersection point!")
        return []
        # raise Exception('lines do not intersect')

    d = (det_line(line1), det_line(line2))
    x = det(d, xdiff) / div
    y = det(d, ydiff) / div
    return [(x, y)]


def solve_circle_and_line_intersections(
    circle: Circle, line: Line, tangent_tolerance: float = 1e-9
) -> List[Tuple[Decimal, Decimal]]:

    (p1x, p1y, p2x, p2y) = (line.x1, line.y1, line.x2, line.y2)
    (cx, cy) = (circle.x0, circle.y0)
    (x1, y1), (x2, y2) = (p1x - cx, p1y - cy), (p2x - cx, p2y - cy)
    dx, dy = (x2 - x1), (y2 - y1)

    dr = (dx ** Decimal(2) + dy ** Decimal(2)) ** Decimal(0.5)
    big_d = x1 * y2 - x2 * y1
    discriminant = circle.r ** Decimal(2) * dr ** Decimal(2) - big_d ** Decimal(2)

    if discriminant < 0:  # No intersection between circle and line
        log_warning("Curve/circle does not intersect with the line!")
        return []

    # There may be 0, 1, or 2 intersections
    intersections = [
        (
            cx
            + (
                big_d * dy
                + sign * (-1 if dy < 0 else 1) * dx * discriminant ** Decimal(0.5)
            )
            / dr ** Decimal(2),
            cy
            + (-big_d * dx + sign * abs(dy) * discriminant ** Decimal(0.5))
            / dr ** Decimal(2),
        )
        for sign in ((1, -1) if dy < 0 else (-1, 1))
    ]
    if (
        len(intersections) == 2 and abs(discriminant) <= tangent_tolerance
    ):  # If line is tangent to circle, return just one point
        return [intersections[0]]
    else:
        return intersections


def solve_circle_intersections(
    circle1: Circle, circle2: Circle
) -> List[Tuple[Decimal, Decimal]]:
    d2 = Decimal(2)
    d = Decimal(
        math.sqrt((circle2.x0 - circle1.x0) ** d2 + (circle2.y0 - circle1.y0) ** d2)
    )

    # non intersecting, or one circle within other, or coincident circles
    if (
        (d > circle1.r + circle2.r)
        or (d < abs(circle1.r - circle2.r))
        or (d == 0 and circle1.r == circle2.r)
    ):
        log_warning("Curves/circles don't intersect with each other!")
        return []

    a = (circle1.r**d2 - circle2.r**d2 + d**d2) / (d2 * d)
    h = Decimal(math.sqrt(circle1.r**d2 - a**d2))
    x2 = circle1.x0 + a * (circle2.x0 - circle1.x0) / d
    y2 = circle1.y0 + a * (circle2.y0 - circle1.y0) / d

    x3 = x2 + h * (circle2.y0 - circle1.y0) / d
    y3 = y2 - h * (circle2.x0 - circle1.x0) / d
    x4 = x2 - h * (circle2.y0 - circle1.y0) / d
    y4 = y2 + h * (circle2.x0 - circle1.x0) / d

    return [(x3, y3), (x4, y4)]


def select_intersection_point(layer: QgsVectorLayer, nr_points: int) -> None:
    message_box = QMessageBox()
    message_box.setText(tr("Which point do you want to select?"))
    button_1 = QPushButton("Opt 1")
    message_box.addButton(button_1, QMessageBox.ActionRole)
    button_1.clicked.connect(lambda: whichbtn(button_1))

    button_2 = QPushButton("Opt 2")
    message_box.addButton(button_2, QMessageBox.ActionRole)
    button_2.clicked.connect(lambda: whichbtn(button_2))

    if nr_points == 3:
        button_3 = QPushButton("Opt 3")
        message_box.addButton(button_3, QMessageBox.ActionRole)
        button_3.clicked.connect(lambda: whichbtn(button_3))
    elif nr_points == 4:
        button_4 = QPushButton("Opt 4")
        message_box.addButton(button_4, QMessageBox.ActionRole)
        button_4.clicked.connect(lambda: whichbtn(button_4))
    elif nr_points == 5:
        button_5 = QPushButton("Opt 5")
        message_box.addButton(button_5, QMessageBox.ActionRole)
        button_5.clicked.connect(lambda: whichbtn(button_5))

    def whichbtn(button: QPushButton) -> None:
        id = button.text()[-1]
        for feature in layer.getFeatures():
            if feature.id() != int(id):
                layer.dataProvider().deleteFeatures([feature.id()])

    message_box.exec()


def construct_geodetic_objects_from_selections() -> List[GeodeticObject]:
    geodetic_objects: List[GeodeticObject] = []

    all_layers = QgsProject.instance().mapLayers().values()
    for layer in all_layers:
        if (
            isinstance(layer, QgsVectorLayer)
            and layer.isSpatial()
            and len(layer.selectedFeatures()) > 0
        ):

            if layer.wkbType() == QgsWkbTypes.LineString:
                for feat in layer.selectedFeatures():
                    vertices = [vertex for vertex in feat.geometry().vertices()]
                    line = Line(
                        Decimal(vertices[0].x()),
                        Decimal(vertices[1].x()),
                        Decimal(vertices[0].y()),
                        Decimal(vertices[1].y()),
                    )
                    geodetic_objects.append(line)

            elif layer.wkbType() == QgsWkbTypes.CompoundCurve:
                for feat in layer.selectedFeatures():
                    vertices = [vertex for vertex in feat.geometry().vertices()]
                    arc = Arc(
                        Decimal(vertices[0].x()),
                        Decimal(vertices[1].x()),
                        Decimal(vertices[2].x()),
                        Decimal(vertices[0].y()),
                        Decimal(vertices[1].y()),
                        Decimal(vertices[2].y()),
                    )
                    geodetic_objects.append(arc)

            elif layer.wkbType() == QgsWkbTypes.Point:
                for feat in layer.selectedFeatures():
                    vertices = [vertex for vertex in feat.geometry().vertices()]
                    point = Point(Decimal(vertices[0].x()), Decimal(vertices[0].y()))
                    geodetic_objects.append(point)

            else:
                raise Exception("Unsupported geometry typed")

    return geodetic_objects


def set_and_format_labels(layer: QgsVectorLayer) -> None:
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


def write_output_to_file(layer: QgsVectorLayer, output_path: str) -> None:
    """Writes the selected layer to a specified file"""
    writer_options = QgsVectorFileWriter.SaveVectorOptions()
    writer_options.actionOnExistingFile = QgsVectorFileWriter.AppendToLayerAddFields
    # PyQGIS documentation doesnt tell what the last 2 str error outputs should be used for
    error, explanation = QgsVectorFileWriter.writeAsVectorFormatV2(
        layer,
        output_path,
        QgsProject.instance().transformContext(),
        writer_options,
    )

    if error:
        log_warning(
            f"Error writing output to file, error code {error}",
            details=tr(f"Details: {explanation}"),
        )


def log_warning(message: str, details: str = "", duration: int = None) -> None:
    if duration is None:
        LOGGER.warning(
            tr(message),
            extra={
                "details": details,
            },
        )
    else:
        LOGGER.warning(
            tr(message),
            extra={"details": details, "duration": duration},
        )
