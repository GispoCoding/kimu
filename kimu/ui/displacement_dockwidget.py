from PyQt5.QtWidgets import QWidget
from qgis.gui import QgisInterface, QgsDoubleSpinBox
from qgis.PyQt import QtWidgets

from ..qgis_plugin_tools.tools.resources import load_ui

FORM_CLASS: QWidget = load_ui("displacement_dockwidget.ui")


class DisplacementDockWidget(QtWidgets.QDockWidget, FORM_CLASS):  # type: ignore
    def __init__(self, iface: QgisInterface) -> None:
        super().__init__()
        self.setupUi(self)
        self.iface = iface

    def get_displacement(self) -> float:
        self.doublespinbox: QgsDoubleSpinBox
        return self.doublespinbox.value()
