from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtWidgets import QPushButton, QWidget
from qgis.core import QgsApplication
from qgis.gui import QgisInterface, QgsSpinBox, QgsDoubleSpinBox
from qgis.PyQt import QtWidgets

from ..qgis_plugin_tools.tools.resources import load_ui

FORM_CLASS: QWidget = load_ui("line_circle_dockwidget.ui")


class LineCircleDockWidget(QtWidgets.QDockWidget, FORM_CLASS):  # type: ignore
    def __init__(self, iface: QgisInterface) -> None:
        super().__init__()
        self.setupUi(self)
        self.iface = iface
        self.qpushbutton_copy: QPushButton
        #self.qpushbutton_copy.clicked.connect(self.__copy_clicked)

    def get_radius(self) -> float:
        self.doublespinbox_sade: QgsDoubleSpinBox
        return self.doublespinbox_sade.value()

    #def set_split_length(self, value: float) -> None:
        #self.iface.addDockWidget(Qt.RightDockWidgetArea, self)
        #result_string = f"{value:.3f}"
        #self.qlabel_value.setText(result_string)

    #@pyqtSlot()
    #def __copy_clicked(self) -> None:
        #"""Copy current value to clipboard."""
        #current_value = self.qlabel_value.text()
        #clipboard = QgsApplication.clipboard()
        #clipboard.setText(current_value)
