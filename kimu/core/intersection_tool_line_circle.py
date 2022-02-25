from typing import List

from PyQt5.QtCore import Qt
from qgis import processing
from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.PyQt.QtCore import QVariant
from qgis.utils import iface
from qgis.gui import QgisInterface, QgsMapMouseEvent, QgsMapToolIdentify, QgsMapToolEmitPoint

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name
from ..ui.line_circle_dockwidget import LineCircleDockWidget
from .select_tool import SelectTool
from .coordinates_tool import SaveSnappedPoint

LOGGER = setup_logger(plugin_name())

class IntersectionLineCircle(SelectTool, SaveSnappedPoint):
    def __init__(self, iface: QgisInterface, dock_widget: LineCircleDockWidget) -> None:
        super().__init__(iface)
        self.ui: LineCircleDockWidget = dock_widget

    def manual_activate(self) -> None:
        """Manually activate tool."""
        self.iface.mapCanvas().setMapTool(self)
        self.action().setChecked(True)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.ui)

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
        """First canvas click event."""

        if self.iface.activeLayer() != self.layer:
            LOGGER.warning(tr("Please select a line layer"), extra={"details": ""})
            return

        geometry = self._identify_and_extract_single_geometry(event)
        # No geometry identified
        if geometry.isEmpty():
            return

        intersection_layer = self._intersect(geometry)

        QgsProject.instance().addMapLayer(intersection_layer)

    def _identify_and_extract_single_geometry(
        self, event: QgsMapMouseEvent
    ) -> QgsGeometry:
        """Identifies clicked feature and extracts its geometry.
        Returns empty geometry if nr. of identified features != 1."""
        found_features: List[QgsMapToolIdentify.IdentifyResult] = self.identify(
            event.x(), event.y(), [self.layer], QgsMapToolIdentify.ActiveLayer
        )
        if len(found_features) != 1:
            LOGGER.info(
                tr("Please select one line"), extra={"details": "", "duration": 1}
            )
            return QgsGeometry()
        self.layer.selectByIds(
            [f.mFeature.id() for f in found_features], QgsVectorLayer.SetSelection
        )
        geometry: QgsGeometry = found_features[0].mFeature.geometry()
        return geometry

    def _intersect(self, geometry: QgsGeometry) -> QgsVectorLayer:

        result_layer = QgsVectorLayer("Point", "temp", "memory")
        crs = self.layer.crs()
        result_layer.setCrs(crs)
        result_layer_dataprovider = result_layer.dataProvider()
        result_layer_dataprovider.addAttributes(
            [QgsField("xcoord", QVariant.Double), QgsField("ycoord", QVariant.Double)]
        )
        result_layer.updateFields()

        line_feat = geometry.asPolyline()
        start_point = QgsPointXY(line_feat[0])
        end_point = QgsPointXY(line_feat[-1])
        viiva = [start_point.x(), start_point.y(), end_point.x(), end_point.y()]

        if len(viiva)==0:
            LOGGER.warning(tr("Vika taalla"), extra={"details": ""})
            return

        #KP COORD!

        # a reference to our map canvas
        #canvas = iface.mapCanvas()
        # this QGIS tool emits as QgsPoint after each click on the map canvas
        #pointTool = QgsMapToolEmitPoint(canvas)
        #lii = [pointTool.pos.x(), pointTool.pos.y()]

        #if len(kpcoord)==0:
            #LOGGER.warning(tr("Vika taalla2"), extra={"details": ""})
            #return

        # Coordinates of the intersection point user chooses
        #x = float(kpcoord[0]) + float(viiva[0])
        #y = float(kpcoord[1]) + float(viiva[3])

        #kpoint = self.toLayerCoordinates(self.layer, event.pos() )

        radius = self.ui.get_radius()
        # Coordinates of the intersection point user chooses
        #x = float(viiva[0]) + radius * 100.0 + lii[0]
        x = float(viiva[0]) + radius * 100.0
        y = float(viiva[3]) + radius * 100.0

        # Check that the result point lies in the map canvas extent
        extent = iface.mapCanvas().extent()

        if (
            x < extent.xMinimum()
            or x > extent.xMaximum()
            or y < extent.yMinimum()
            or y > extent.yMaximum()
        ):
            LOGGER.warning(
                tr("Intersection point(s) lie(s) outside of the map canvas!"),
                extra={"details": ""},
            )
            return

        intersection_point = QgsPointXY(x, y)
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPointXY(intersection_point))
        f.setAttributes([round(x, 2), round(y, 2)])
        result_layer_dataprovider.addFeature(f)
        result_layer.updateExtents()

        result_layer.setName(tr("Intersection points"))
        result_layer.renderer().symbol().setSize(2)
        return result_layer
