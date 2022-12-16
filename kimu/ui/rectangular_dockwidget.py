from PyQt5.QtWidgets import QTextEdit, QWidget
from qgis.gui import QgisInterface, QgsDoubleSpinBox, QgsFileWidget
from qgis.PyQt import QtWidgets

from ..qgis_plugin_tools.tools.resources import load_ui

FORM_CLASS: QWidget = load_ui("rectangular_dockwidget.ui")


class RectangularDockWidget(QtWidgets.QDockWidget, FORM_CLASS):  # type: ignore
    def __init__(self, iface: QgisInterface) -> None:
        super().__init__()
        self.setupUi(self)
        self.iface = iface

    def get_a_measure(self) -> float:
        self.doublespinbox_a: QgsDoubleSpinBox
        return self.doublespinbox_a.value()

    def get_b_measure(self) -> float:
        self.doublespinbox_b: QgsDoubleSpinBox
        return self.doublespinbox_b.value()

    def get_c_measures(self) -> str:
        self.textEdit: QTextEdit
        return self.textEdit.toPlainText()

    def get_output_file_path(self) -> str:
        self.mQgsFileWidget: QgsFileWidget
        return self.mQgsFileWidget.filePath()
