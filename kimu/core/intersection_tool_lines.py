from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsFeature,
    QgsField,
    QgsPointXY,
    QgsProject,
    QgsGeometry,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.utils import iface

from ..qgis_plugin_tools.tools.custom_logging import setup_logger
from ..qgis_plugin_tools.tools.i18n import tr
from ..qgis_plugin_tools.tools.resources import plugin_name

LOGGER = setup_logger(plugin_name())


class IntersectionLines:

    @staticmethod
    def __check_valid_layer(layer: QgsVectorLayer) -> bool:
        """Checks if layer is valid"""
        if (
            isinstance(layer, QgsVectorLayer)
            and layer.isSpatial()
            and layer.geometryType() == QgsWkbTypes.LineGeometry
        ):
            return True
        return False

    def run(self) -> None:
        layer = iface.activeLayer()
        if not self.__check_valid_layer(layer):
            LOGGER.warning(tr("Please select a line layer"), extra={"details": ""})
            return

        if len(layer.selectedFeatures()) != 2:
            LOGGER.warning(tr("Please select two line features"), extra={"details": ""})
            return

        vl = QgsVectorLayer("Point", "temp", "memory")
        crs = layer.crs()
        vl.setCrs(crs)
        pr = vl.dataProvider()
        pr.addAttributes([QgsField("xkoord", QVariant.Double), QgsField("ykoord", QVariant.Double)])
        vl.updateFields()

        l = list()

        features = layer.selectedFeatures()
        for feat in features:
            viiva = feat.geometry().asPolyline()
            pxy = QgsPointXY(viiva[0])
            pxy2 = QgsPointXY(viiva[-1])
            l.extend([pxy.x(), pxy.y(), pxy2.x(), pxy2.y()])

        # x1=l[0], y1=l[1], x2=l[2], y2=l[3], x3=l[4], y3=l[5], x4=l[6], y4=l[7]
        x = (l[0]*((l[3]-l[1])/(l[2]-l[0]))-l[4]*((l[7]-l[5])/(l[6]-l[4]))+l[5]-l[1]) / (((l[3]-l[1])/(l[2]-l[0]))-((l[7]-l[5])/(l[6]-l[4])))
        y = ((l[3]-l[1])/(l[2]-l[0]))*(x-l[0])+l[1]

        piste = QgsPointXY(x, y)
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPointXY(piste))
        f.setAttributes([round(x,2), round(y,2)])
        pr.addFeature(f)
        vl.updateExtents()

        vl.setName(tr("Intersection point"))
        vl.renderer().symbol().setSize(2)
        QgsProject.instance().addMapLayer(vl)
