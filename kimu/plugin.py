from typing import Callable, List, Optional

from PyQt5.QtCore import QCoreApplication, Qt, QTranslator
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QWidget
from qgis.gui import QgisInterface

from .core.explode_lines import ExplodeLines
from .core.explode_lines2points import ExplodeLines2points
from .core.explode_tool import ExplodeTool
from .core.intersection_tool_line_circle import IntersectionLineCircle
from .core.intersection_tool_lines import IntersectionLines
from .core.rectangular_tool import RectangularMapping
from .core.split_tool import SplitTool
from .qgis_plugin_tools.tools.custom_logging import setup_logger, teardown_logger
from .qgis_plugin_tools.tools.i18n import setup_translation, tr
from .qgis_plugin_tools.tools.resources import plugin_name
from .ui.line_circle_dockwidget import LineCircleDockWidget
from .ui.rectangular_dockwidget import RectangularDockWidget
from .ui.split_tool_dockwidget import SplitToolDockWidget

LOGGER = setup_logger(plugin_name())


class Plugin:
    """QGIS Plugin Implementation."""

    def __init__(self, iface: QgisInterface) -> None:

        self.iface = iface
        split_tool_dockwidget = SplitToolDockWidget(iface)
        line_circle_dockwidget = LineCircleDockWidget(iface)
        rectangular_dockwidget = RectangularDockWidget(iface)
        self.split_tool = SplitTool(self.iface, split_tool_dockwidget)
        # If you wish to uncomment this line:
        # self.explode_tool = ExplodeTool(self.split_tool)
        # you need to comment out this one:
        self.explode_tool = ExplodeTool()
        self.explode_lines = ExplodeLines()
        self.explode_lines2points = ExplodeLines2points()
        self.intersection_tool_lines = IntersectionLines()
        self.intersection_tool_line_circle = IntersectionLineCircle(
            self.iface, line_circle_dockwidget
        )
        self.rectangular_tool = RectangularMapping(rectangular_dockwidget)

        # Initialize locale
        locale, file_path = setup_translation()
        if file_path:
            self.translator = QTranslator()
            self.translator.load(file_path)
            # noinspection PyCallByClass
            QCoreApplication.installTranslator(self.translator)
        else:
            pass

        self.actions: List[QAction] = []
        self.menu = tr(plugin_name())

    def add_action(
        self,
        icon_path: str,
        text: str,
        callback: Callable,
        enabled_flag: bool = True,
        add_to_menu: bool = True,
        add_to_toolbar: bool = True,
        status_tip: Optional[str] = None,
        whats_this: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> QAction:
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.

        :param text: Text that should be shown in menu items for this action.

        :param callback: Function to be called when the action is triggered.

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.

        :param parent: Parent widget for the new action. Defaults None.

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        # noinspection PyUnresolvedReferences
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)

        return action

    def initGui(self) -> None:  # noqa N802
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        self.add_action(
            "",
            text=tr("Explode polygon"),
            callback=self.activate_explode_tool,
            parent=self.iface.mainWindow(),
            add_to_menu=False,
            add_to_toolbar=True,
        )
        self.add_action(
            "",
            text=tr("Explode line(s)"),
            callback=self.activate_explode_lines,
            parent=self.iface.mainWindow(),
            add_to_menu=False,
            add_to_toolbar=True,
        )
        self.add_action(
            "",
            text=tr("Explode line(s) to points"),
            callback=self.activate_explode_lines2points,
            parent=self.iface.mainWindow(),
            add_to_menu=False,
            add_to_toolbar=True,
        )
        self.add_action(
            "",
            text=tr("Intersect lines"),
            callback=self.activate_intersection_tool_lines,
            parent=self.iface.mainWindow(),
            add_to_menu=False,
            add_to_toolbar=True,
        )
        line_circle_action = self.add_action(
            "",
            text=tr("Intersect line and circle"),
            callback=self.activate_intersection_tool_line_circle,
            parent=self.iface.mainWindow(),
            add_to_menu=False,
            add_to_toolbar=True,
        )
        line_circle_action.setCheckable(True)
        self.intersection_tool_line_circle.setAction(line_circle_action)
        rectangular_action = self.add_action(
            "",
            text=tr("Rectangular mapping"),
            callback=self.activate_rectangular_tool,
            parent=self.iface.mainWindow(),
            add_to_menu=False,
            add_to_toolbar=True,
        )
        rectangular_action.setCheckable(True)
        self.rectangular_tool.setAction(rectangular_action)
        split_action = self.add_action(
            "",
            text=tr("Split"),
            callback=self.activate_split_tool,
            parent=self.iface.mainWindow(),
            add_to_menu=False,
            add_to_toolbar=True,
        )
        split_action.setCheckable(True)
        self.split_tool.setAction(split_action)

    def onClosePlugin(self) -> None:  # noqa N802
        """Cleanup necessary items here when plugin dockwidget is closed"""
        pass

    def unload(self) -> None:
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(tr(plugin_name()), action)
            self.iface.removeToolBarIcon(action)
        teardown_logger(plugin_name())

    def activate_explode_tool(self) -> None:
        self.explode_tool.run()

    def activate_explode_lines(self) -> None:
        self.explode_lines.run()

    def activate_explode_lines2points(self) -> None:
        self.explode_lines2points.run()

    def activate_intersection_tool_lines(self) -> None:
        self.intersection_tool_lines.run()

    def activate_intersection_tool_line_circle(self) -> None:
        self.iface.addDockWidget(
            Qt.RightDockWidgetArea, self.intersection_tool_line_circle.ui
        )
        self.iface.mapCanvas().setMapTool(self.intersection_tool_line_circle)

    def activate_rectangular_tool(self) -> None:
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.rectangular_tool.ui)
        self.iface.mapCanvas().setMapTool(self.rectangular_tool)

    def activate_split_tool(self) -> None:
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.split_tool.ui)
        self.iface.mapCanvas().setMapTool(self.split_tool)
