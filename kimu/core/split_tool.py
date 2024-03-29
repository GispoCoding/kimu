from typing import List

from PyQt5.QtCore import Qt
from qgis import processing
from qgis.core import (
    QgsCategorizedSymbolRenderer,
    QgsFeatureRequest,
    QgsGeometry,
    QgsLineSymbol,
    QgsProcessingFeatureSourceDefinition,
    QgsProject,
    QgsRendererCategory,
    QgsStyle,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgisInterface, QgsMapMouseEvent, QgsMapToolIdentify
from qgis.PyQt.QtGui import QColor

from ..qgis_plugin_tools.tools.i18n import tr
from ..ui.split_tool_dockwidget import SplitToolDockWidget
from .select_tool import SelectTool
from .tool_functions import log_warning


class SplitTool(SelectTool):
    def __init__(self, iface: QgisInterface, dock_widget: SplitToolDockWidget) -> None:
        super().__init__(iface)
        self.ui: SplitToolDockWidget = dock_widget

    def manual_activate(self) -> None:
        """Manually activate tool."""
        self.iface.mapCanvas().setMapTool(self)
        self.action().setChecked(True)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.ui)

    def canvasPressEvent(self, event: QgsMapMouseEvent) -> None:  # noqa: N802
        """Handles split tool canvas click event.
        Splits line to N parts, extracts vertices."""
        self._run(event)

    def _identify_and_extract_single_geometry(
        self, event: QgsMapMouseEvent
    ) -> QgsGeometry:
        """Identifies clicked feature and extracts its geometry.
        Returns empty geometry if nr. of identified features != 1."""
        found_features: List[QgsMapToolIdentify.IdentifyResult] = self.identify(
            event.x(), event.y(), [self.layer], QgsMapToolIdentify.ActiveLayer
        )
        if len(found_features) != 1:
            log_warning("Please select one line", duration=1)
            self.ui.set_split_length(0)
            return QgsGeometry()
        self.layer.selectByIds(
            [f.mFeature.id() for f in found_features], QgsVectorLayer.SetSelection
        )
        geometry: QgsGeometry = found_features[0].mFeature.geometry()
        return geometry

    def _create_split_line_layer(self, geometry: QgsGeometry) -> QgsVectorLayer:
        """Create a QgsVectorLayer containing line split to N parts of equal length."""
        split_to = self.ui.get_split_parts()
        split_length = geometry.length() / split_to
        self.ui.set_split_length(split_length)
        split_params = {
            "INPUT": QgsProcessingFeatureSourceDefinition(
                self.layer.id(),
                selectedFeaturesOnly=True,
                featureLimit=-1,
                geometryCheck=QgsFeatureRequest.GeometryAbortOnInvalid,
            ),
            "LENGTH": split_length,
            "OUTPUT": "memory:",
        }
        split_result = processing.run("native:splitlinesbylength", split_params)
        split_layer: QgsVectorLayer = split_result["OUTPUT"]
        split_layer.setName(tr("Split line"))
        return split_layer

    @staticmethod
    def _set_split_layer_style(split_layer: QgsVectorLayer) -> None:
        """Set a style to given layer making line segments easy to distinguish."""
        split_layer_ids = [feature.id() for feature in split_layer.getFeatures()]
        categories = []
        for id_ in split_layer_ids:
            symbol = QgsLineSymbol.createSimple(properties={"width": "0.7"})
            category = QgsRendererCategory(id_, symbol, str(id_))
            categories.append(category)
        renderer = QgsCategorizedSymbolRenderer("$id", categories)

        color_ramps = QgsStyle().defaultStyle().colorRampNames()
        ramp_name = "Turbo"
        if ramp_name not in color_ramps:
            ramp_name = color_ramps[-1]
        ramp = QgsStyle().defaultStyle().colorRamp(ramp_name)
        renderer.updateColorRamp(ramp)
        split_layer.setRenderer(renderer)

    @staticmethod
    def _create_vertex_layer(split_layer: QgsVectorLayer) -> QgsVectorLayer:
        """Extracts start and end vertices from each line segment.
        Returns a point layer."""
        extract_result = processing.run(
            "native:extractspecificvertices",
            {"INPUT": split_layer, "VERTICES": "0,-1", "OUTPUT": "memory:"},
        )
        vertex_layer = extract_result["OUTPUT"]
        vertex_layer.setName(tr("Nodes"))
        vertex_layer.renderer().symbol().setSize(2)
        vertex_layer.renderer().symbol().setColor(QColor.fromRgb(255, 192, 203))
        return vertex_layer

    def _run(self, event: QgsMapMouseEvent) -> None:
        self.layer = self.iface.activeLayer()
        if (
            isinstance(self.layer, QgsVectorLayer)
            and self.layer.isSpatial()
            and self.layer.geometryType() == QgsWkbTypes.LineGeometry
        ):
            pass
        else:
            log_warning("Please select a line layer")
            return

        geometry = self._identify_and_extract_single_geometry(event)
        if geometry.isEmpty():  # No geometry identified
            return

        split_line_layer = self._create_split_line_layer(geometry)
        self._set_split_layer_style(split_line_layer)
        QgsProject.instance().addMapLayer(split_line_layer)

        vertex_layer = self._create_vertex_layer(split_line_layer)
        QgsProject.instance().addMapLayer(vertex_layer)
