from abc import ABC
from decimal import Decimal

import numpy as np


class GeodeticObject(ABC):
    pass


class Point(GeodeticObject):
    def __init__(self, x: Decimal, y: Decimal) -> None:
        self.x = x  # X coordinate
        self.y = y  # Y Coordinate


class Line(GeodeticObject):
    def __init__(self, x1: Decimal, x2: Decimal, y1: Decimal, y2: Decimal) -> None:
        self.x1 = x1  # Start x coordinate
        self.x2 = x2  # End x coordinate
        self.y1 = y1  # Start y coordinate
        self.y2 = y2  # End y coordinate

    def __str__(self) -> str:
        return f"x1: {round(self.x1, 3)},x2: {round(self.x2, 3)}, \
            y1: {round(self.y1, 3)}, y2: {round(self.y2, 3)}"

    def __repr__(self) -> str:
        return self.__str__()


class Circle(GeodeticObject):
    def __init__(self, x0: Decimal, y0: Decimal, r: Decimal) -> None:
        self.x0 = x0  # Center x coordinate
        self.y0 = y0  # Center y coordinate
        self.r = r  # Radius

    def tangent_at(self, x: Decimal, y: Decimal) -> Line:
        tangent_slope = -1 * (self.x0 - x) / (self.y0 - y)
        b = y - tangent_slope * x
        x1 = x + 2
        y1 = tangent_slope * x1 + b
        return Line(x, y, x1, y1)

    def __str__(self) -> str:
        return (
            f"x0: {round(self.x0, 3)}, y0: {round(self.y0, 3)}, r: {round(self.r, 3)}"
        )

    def __repr__(self) -> str:
        return self.__str__()


class Arc(GeodeticObject):
    def __init__(
        self,
        x1: Decimal,
        x2: Decimal,
        x3: Decimal,
        y1: Decimal,
        y2: Decimal,
        y3: Decimal,
    ) -> None:
        self.x1 = x1  # Start x coordinate
        self.x2 = x2  # Middle x coordinate
        self.x3 = x3  # End x coordinate
        self.y1 = y1  # Start y coordinate
        self.y2 = y2  # Middle y coordinate
        self.y3 = y3  # End y coordinate

        self.circle = self.define_circle(x1, x2, x3, y1, y2, y3)

    def define_circle(
        self,
        x1: Decimal,
        x2: Decimal,
        x3: Decimal,
        y1: Decimal,
        y2: Decimal,
        y3: Decimal,
    ) -> Circle:
        temp = x2 ** Decimal(2) + y2 ** Decimal(2)
        bc = (x1 ** Decimal(2) + y1 ** Decimal(2) - temp) / 2
        cd = (temp - x3 ** Decimal(2) - y3 ** Decimal(2)) / 2
        det = (x1 - x2) * (y2 - y3) - (x2 - x3) * (y1 - y2)

        if abs(det) < 1.0e-6:
            raise Exception("Cannot create circle from the curve")

        x0 = (bc * (y2 - y3) - cd * (y1 - y2)) / det
        y0 = ((x1 - x2) * cd - (x2 - x3) * bc) / det
        r = np.sqrt((x0 - x1) ** Decimal(2) + (y0 - y1) ** Decimal(2))
        return Circle(x0, y0, r)

    def tangent_at(self, x: Decimal, y: Decimal) -> Line:
        return self.circle.tangent_at(x, y)

    def start_point_tangent(self) -> Line:
        return self.tangent_at(self.x1, self.y1)

    def end_point_tangent(self) -> Line:
        return self.tangent_at(self.x3, self.y3)

    def as_circle(self) -> Circle:
        return self.circle

    def __str__(self) -> str:
        return f"x1: {round(self.x1, 3)}, x2: {round(self.x2, 3)}, x3: {round(self.x3, 3)}, \
            y1: {round(self.y1, 3)}, y2: {round(self.y2, 3)}, y3: {round(self.y3, 3)},"

    def __repr__(self) -> str:
        return self.__str__()
