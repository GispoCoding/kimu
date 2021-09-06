from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsGradientColorRamp,
    QgsLineSymbol,
    QgsStyle,
)

from kimu.core.split_tool import SplitTool


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
