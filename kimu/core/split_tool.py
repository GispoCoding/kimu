from typing import List

from PyQt5.QtCore import Qt
from qgis._core import QgsGeometry, QgsVectorLayer, QgsWkbTypes
from qgis._gui import QgisInterface, QgsMapMouseEvent, QgsMapToolIdentify

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
            self.ui.set_result_value(0)
            return
        geometry: QgsGeometry = found_features[0].mFeature.geometry()

        split_to = self.ui.get_split_value()
        result = geometry.length() / split_to
        self.ui.set_result_value(result)
