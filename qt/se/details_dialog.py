# Copyright 2016 Hardcoded Software (http://www.hardcoded.net)
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from qt.details_dialog import DetailsDialog as DetailsDialogBase


class DetailsDialog(DetailsDialogBase):
    # Standard Edition uses the base dialog as-is (502x186, minimum
    # 200x0); see qt/details_dialog.py for the shared _setupUi.
    pass
