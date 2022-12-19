from PyQt5.QtWidgets import QWidget
from qgis.gui import QgisInterface, QgsFileWidget
from qgis.PyQt import QtWidgets

from ..qgis_plugin_tools.tools.resources import load_ui

FORM_CLASS: QWidget = load_ui("intersect_lines_dialog.ui")


class IntersectLinesDialog(QtWidgets.QDialog, FORM_CLASS):  # type: ignore
    def __init__(self, iface: QgisInterface) -> None:
        super().__init__()
        self.setupUi(self)
        self.iface = iface

    def get_output_file_path(self) -> str:
        self.mQgsFileWidget: QgsFileWidget
        return self.mQgsFileWidget.filePath()
