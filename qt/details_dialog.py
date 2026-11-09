# Created By: Virgil Dupras
# Created On: 2010-02-05
# Copyright 2015 Hardcoded Software (http://www.hardcoded.net)
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import QAbstractItemView, QDockWidget, QWidget

from qt.util import move_to_screen_center
from qt.details_table import DetailsModel, DetailsTable
from hscommon.plat import ISLINUX
from hscommon.trans import trget

tr = trget("ui")


class DetailsDialog(QDockWidget):
    # Subclasses override these for their edition's dialog size. The
    # defaults are the Standard Edition's size.
    DEFAULT_SIZE = QSize(502, 186)
    MINIMUM_SIZE = QSize(200, 0)

    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, Qt.Tool, **kwargs)
        self.parent = parent
        self.app = app
        self.model = app.model.details_panel
        self.setAllowedAreas(Qt.AllDockWidgetAreas)
        self._setupUi()
        # To avoid saving uninitialized geometry on appWillSavePrefs, we track whether our dialog
        # has been shown. If it has, we know that our geometry should be saved.
        self._shown_once = False
        self._wasDocked, area = self.app.prefs.restoreGeometry("DetailsWindowRect", self)
        self.tableModel = DetailsModel(self.model, app)
        # tableView is created in _setupUi (the Photo Edition creates its
        # own there)
        self.tableView.setModel(self.tableModel)
        self.model.view = self
        self.app.willSavePrefs.connect(self.appWillSavePrefs)
        # self.setAttribute(Qt.WA_DeleteOnClose)
        parent.addDockWidget(area if self._wasDocked else Qt.BottomDockWidgetArea, self)

    def _setupUi(self):
        # The Standard and Music editions share this layout; only their
        # sizes differ (see DEFAULT_SIZE/MINIMUM_SIZE). The Photo Edition
        # overrides _setupUi entirely (image viewers + splitter).
        self.setWindowTitle(tr("Details"))
        self.resize(self.DEFAULT_SIZE)
        self.setMinimumSize(self.MINIMUM_SIZE)
        self.tableView = DetailsTable(self)
        self.tableView.setAlternatingRowColors(True)
        self.tableView.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableView.setShowGrid(False)
        self.setWidget(self.tableView)

    def show(self):
        if not self._shown_once and self._wasDocked:
            self.setFloating(False)
        self._shown_once = True
        super().show()
        self.update_options()

    def update_options(self):
        # This disables the title bar (if we had not set one before already)
        # essentially making it a simple floating window, not dockable anymore
        if not self.app.prefs.details_dialog_titlebar_enabled:
            if not self.titleBarWidget():  # default title bar
                self.setTitleBarWidget(QWidget())  # disables title bar
                # Windows (and MacOS?) users cannot move a floating window which
                # has no native decoration so we force it to dock for now
                if not ISLINUX:
                    self.setFloating(False)
        elif self.titleBarWidget() is not None:  # title bar is disabled
            self.setTitleBarWidget(None)  # resets to the default title bar
        elif not self.titleBarWidget() and not self.app.prefs.details_dialog_titlebar_enabled:
            self.setTitleBarWidget(QWidget())

        features = self.features()
        if self.app.prefs.details_dialog_vertical_titlebar:
            self.setFeatures(features | QDockWidget.DockWidgetVerticalTitleBar)
        elif features & QDockWidget.DockWidgetVerticalTitleBar:
            self.setFeatures(features ^ QDockWidget.DockWidgetVerticalTitleBar)

    # --- Events
    def appWillSavePrefs(self):
        if self._shown_once:
            self.app.prefs.saveGeometry("DetailsWindowRect", self)

    # --- model --> view
    def refresh(self):
        self.tableModel.beginResetModel()
        self.tableModel.endResetModel()

    def showEvent(self, event):
        if self._wasDocked is False:
            # have to do this here as the frameGeometry is not correct until shown
            move_to_screen_center(self)
        super().showEvent(event)
