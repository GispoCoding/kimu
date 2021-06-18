from typing import List

from PyQt5.QtCore import Qt
from qgis import processing
from qgis.core import (
    QgsFeatureRequest,
    QgsGeometry,
    QgsProcessingFeatureSourceDefinition,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgisInterface, QgsMapMouseEvent, QgsMapToolIdentify

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name
from ..ui.split_tool_dockwidget import SplitToolDockWidget
from .select_tool import SelectTool

LOGGER = setup_logger(plugin_name())


class SplitTool(SelectTool):
    def __init__(self, iface: QgisInterface, dock_widget: SplitToolDockWidget) -> None:
        super().__init__(iface)
        self.ui: SplitToolDockWidget = dock_widget

    def manual_activate(self) -> None:
        """Manually activate tool."""
        self.iface.mapCanvas().setMapTool(self)
        self.action().setChecked(True)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.ui)

    def set_dock_widget(self, dock_widget: SplitToolDockWidget) -> None:
        self.__dock_widget = dock_widget

    def active_changed(self, layer: QgsVectorLayer) -> None:
        """Triggered when active layer changes."""
        if (
            isinstance(layer, QgsVectorLayer)
            and layer.isSpatial()
            and layer.geometryType() == QgsWkbTypes.LineGeometry
        ):
            self.layer = layer
            self.setLayer(self.layer)

    def canvasPressEvent(self, event: QgsMapMouseEvent) -> None:  # noqa: N802
        if self.iface.activeLayer() != self.layer:
            LOGGER.warning(tr("Please select a line layer"), extra={"details": ""})
            return
        found_features: List[QgsMapToolIdentify.IdentifyResult] = self.identify(
            event.x(), event.y(), [self.layer], QgsMapToolIdentify.ActiveLayer
        )
        if len(found_features) != 1:
            LOGGER.info(
                tr("Please select one line"), extra={"details": "", "duration": 1}
            )
            self.ui.set_split_length(0)
            return
        self.layer.selectByIds(
            [f.mFeature.id() for f in found_features], QgsVectorLayer.SetSelection
        )
        geometry: QgsGeometry = found_features[0].mFeature.geometry()

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
        split_layer = split_result["OUTPUT"]
        split_layer.setName(tr("Split line"))
        split_layer.renderer().symbol().setWidth(2)
        # TODO: set visualization to categorized with expression rand(1,100)
        QgsProject.instance().addMapLayer(split_layer)

        extract_result = processing.run(
            "native:extractvertices", {"INPUT": split_layer, "OUTPUT": "memory:"}
        )
        extract_layer = extract_result["OUTPUT"]
        extract_layer.setName(tr("Nodes"))
        extract_layer.renderer().symbol().setSize(3)
        QgsProject.instance().addMapLayer(extract_layer)
