# type: ignore
# flake8: noqa ANN201
"""
This class contains fixtures and common helper function to keep the test files shorter
"""
import pytest
from qgis.core import QgsVectorLayer

from .utilities import resource_paths


@pytest.fixture
def layer_lines_arcs():
    file_path = resource_paths("lines/lines_and_arcs.geojson")[0]
    layer = QgsVectorLayer(file_path, "lines and arcs")
    yield layer
