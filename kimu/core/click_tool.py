from decimal import Decimal
from typing import List

from qgis.core import QgsProject, QgsSnappingConfig, QgsTolerance
from qgis.gui import QgisInterface, QgsMapCanvas, QgsMapToolEmitPoint, QgsSnapIndicator


class ClickTool(QgsMapToolEmitPoint):
    """Base class for selecting features from canvas."""

    def __init__(self, iface: QgisInterface) -> None:
        self.iface = iface
        self.canvas: QgsMapCanvas = iface.mapCanvas()
        super().__init__(self.canvas)
        # Set suitable snapping settings
        my_snap_config = QgsSnappingConfig()
        my_snap_config.setEnabled(True)
        my_snap_config.setType(QgsSnappingConfig.Vertex)
        my_snap_config.setUnits(QgsTolerance.Pixels)
        my_snap_config.setTolerance(15)
        my_snap_config.setIntersectionSnapping(True)
        my_snap_config.setMode(QgsSnappingConfig.AllLayers)
        QgsProject.instance().setSnappingConfig(my_snap_config)
        self.i = QgsSnapIndicator(self.canvas)

    def activate(self, event: QgsMapToolEmitPoint) -> List[Decimal]:
        """Called when tool is activated."""
        m = self.canvas.snappingUtils().snapToMap(event.pos())
        self.i.setMatch(m)
        point = [Decimal(m.point().x()), Decimal(m.point().y())]
        return point

    def deactivate(self) -> None:
        """Called when tool is deactivated."""
        self.action().setChecked(False)
