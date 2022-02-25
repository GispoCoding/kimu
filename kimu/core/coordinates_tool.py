from qgis.core import (
    QgsProject,
    QgsSnappingConfig,
    QgsTolerance,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
)
from qgis.utils import iface
from qgis.gui import QgsMapToolEmitPoint, QgsSnapIndicator

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.resources import plugin_name

LOGGER = setup_logger(plugin_name())

class SaveSnappedPoint(QgsMapToolEmitPoint):

    def __init__(self, canvas, transform=False):
        self.canvas = canvas
        QgsMapToolEmitPoint.__init__(self, self.canvas)
        self.transform = transform
        self.project = QgsProject.instance()
        self.l = iface.activeLayer()
        self.i = QgsSnapIndicator(self.canvas)
        self.u = self.canvas.snappingUtils()
        self.c = self.u.config()
        self.c.setEnabled(True)
        self.c.setMode(QgsSnappingConfig.AdvancedConfiguration)
        self.s = QgsSnappingConfig.IndividualLayerSettings(True, QgsSnappingConfig.VertexFlag, 25.00,
                                                           QgsTolerance.Pixels)
        self.c.setIndividualLayerSettings(self.l, self.s)
        self.u.setConfig(self.c)

        # Define source and destination crs's and instantiate QgsCoordinateTransform class
        self.src_crs = self.project.crs()
        # Best to change epsg code below to a local projected crs (e.g. UTM)
        self.dst_crs = QgsCoordinateReferenceSystem('EPSG:3857')
        self.x_form = QgsCoordinateTransform(self.src_crs, self.dst_crs, self.project)

    def canvasMoveEvent(self, e):
        m = self.u.snapToMap(e.pos())
        self.i.setMatch(m)

    def canvasPressEvent(self, e):
        if self.i.match().type():
            pointxy = self.i.match().point()
        else:
            pointxy = None
        if pointxy:
            if self.transform:
                tr = self.x_form.transform(pointxy)
                point = [tr.x(), tr.y()]
            else:
                point = [pointxy.x(), pointxy.y()]
            print('Point snapped to vertex: {}'.format(point))

    def deactivate(self):
        self.s = QgsSnappingConfig.IndividualLayerSettings(False, QgsSnappingConfig.NoSnapFlag, 25.00,
                                                           QgsTolerance.Pixels)
        self.c.setIndividualLayerSettings(self.l, self.s)
        self.u.setConfig(self.c)


canvas = iface.mapCanvas()
# to transform snapped click-points, pass True as 2nd argument to constructor
T = SaveSnappedPoint(canvas, True)
canvas.setMapTool(T)
