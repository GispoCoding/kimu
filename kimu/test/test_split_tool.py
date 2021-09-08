import pytest
from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsGradientColorRamp,
    QgsLineSymbol,
    QgsStyle,
    QgsVectorLayer,
)

from kimu.core.split_tool import SplitTool
from kimu.qgis_plugin_tools.tools.i18n import tr
from kimu.ui.split_tool_dockwidget import SplitToolDockWidget


@pytest.fixture
def split_tool(qgis_iface, mocker):
    dock_widget = SplitToolDockWidget(qgis_iface)
    processing_mock = mocker.patch("kimu.core.split_tool.processing")
    processing_mock.run.return_value = {"OUTPUT": QgsVectorLayer()}
    split_tool = SplitTool(qgis_iface, dock_widget)
    yield split_tool


def test_create_split_line_layer(layer_lines_arcs, split_tool):
    features = [feature for feature in layer_lines_arcs.getFeatures()]
    geometry = features[0].geometry()
    split_tool.layer = layer_lines_arcs
    result = split_tool._create_split_line_layer(geometry)
    assert type(result) == QgsVectorLayer
    assert result.name() == tr("Split line")


def test_color_ramp():
    color_ramps = QgsStyle().defaultStyle().colorRampNames()
    ramp_name = "Turbo"
    if ramp_name not in color_ramps:
        ramp_name = color_ramps[-1]
    ramp = QgsStyle().defaultStyle().colorRamp(ramp_name)
    assert type(ramp) == QgsGradientColorRamp


def test_set_split_layer_style(layer_lines_arcs):
    features = [feature for feature in layer_lines_arcs.getFeatures()]

    SplitTool._set_split_layer_style(layer_lines_arcs)
    renderer = layer_lines_arcs.renderer()
    assert type(renderer) == QgsCategorizedSymbolRenderer
    # assert type(renderer.sourceColorRamp()) == QgsGradientColorRamp
    assert len(renderer.categories()) == len(features)
    symbol = renderer.categories()[0].symbol()
    assert type(symbol) == QgsLineSymbol
