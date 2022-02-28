from PyQt5.QtWidgets import QWidget
from qgis.gui import QgisInterface, QgsDoubleSpinBox
from qgis.PyQt import QtWidgets

from ..qgis_plugin_tools.tools.resources import load_ui

FORM_CLASS: QWidget = load_ui("line_circle_dockwidget.ui")


class LineCircleDockWidget(QtWidgets.QDockWidget, FORM_CLASS):
    def __init__(self, iface: QgisInterface) -> None:
        super().__init__()
        self.setupUi(self)
        self.iface = iface

    def get_radius(self) -> float:
        self.doublespinbox_sade: QgsDoubleSpinBox
        return self.doublespinbox_sade.value()