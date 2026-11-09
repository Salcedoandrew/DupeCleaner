# Copyright 2016 Hardcoded Software (http://www.hardcoded.net)
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import QSize

from qt.details_dialog import DetailsDialog as DetailsDialogBase


class DetailsDialog(DetailsDialogBase):
    # Music Edition only differs from the base dialog by its size; the
    # layout itself lives in qt/details_dialog.py.
    DEFAULT_SIZE = QSize(502, 295)
    MINIMUM_SIZE = QSize(250, 250)
