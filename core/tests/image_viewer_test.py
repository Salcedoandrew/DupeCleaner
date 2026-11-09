# Tests for qt/pe/image_viewer.py (the picture details dialog's image
# viewers). They live here, in the core suite, because tox only collects
# core/ and hscommon/ -- there is no qt/ test run.
#
# The dialog used to decode full-size photos synchronously on the GUI
# thread in updateView; the decode now happens in a worker thread and the
# pixmaps are applied when the loads finish. These tests run with the
# offscreen platform plugin: updateView must return immediately with
# empty pixmaps, and the images must appear once the event loop pumps
# the load completions.

import os
import time
from pathlib import Path

import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QColor, QImage, QPixmap
from PyQt5.QtCore import QSize

from qt.pe.image_viewer import BaseController


@pytest.fixture(scope="module")
def qapp():
    # Offscreen rendering: the platform is picked when the QApplication
    # is created, so setting the variable here (before construction) is
    # enough -- no need for a module-level environ hack.
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication([])
    yield app


class FakeViewer:
    def __init__(self):
        self._pixmap = QPixmap()
        self.bestFit = True
        self.current_scale = 1.0
        self.ignore_signal = False
        self.enabled = True
        self.set_image_calls = []

    def size(self):
        return QSize(100, 100)

    def setImage(self, pixmap):
        self.set_image_calls.append(pixmap)
        self._pixmap = pixmap

    def connectMouseSignals(self):
        pass

    def resetCenter(self):
        pass

    def scaleAt(self, scale):
        self.current_scale = scale

    def centerViewAndUpdate(self):
        pass


class FakeButton:
    def __init__(self):
        self.enabled = None

    def setEnabled(self, value):
        self.enabled = value


class FakeParent:
    def __init__(self):
        self.verticalToolBar = type(
            "Toolbar",
            (),
            {
                "buttonImgSwap": FakeButton(),
                "buttonZoomIn": FakeButton(),
                "buttonZoomOut": FakeButton(),
                "buttonNormalSize": FakeButton(),
                "buttonBestFit": FakeButton(),
            },
        )()


class FakeFile:
    def __init__(self, path, dimensions=(100, 100)):
        self.path = Path(path)
        self.dimensions = dimensions


def make_image(path, size, color):
    image = QImage(size, size, QImage.Format_RGB32)
    image.fill(QColor(*color))
    assert image.save(str(path))


def pump_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QApplication.processEvents()
    return predicate()


def make_controller():
    controller = BaseController(FakeParent())
    selected = FakeViewer()
    reference = FakeViewer()
    controller.setupViewers(selected, reference)
    return controller, selected, reference


def test_update_view_returns_immediately_then_loads(qapp, tmpdir):
    # updateView must not block on the decode: it returns with empty
    # pixmaps, and the images appear once the loads finish.
    red = tmpdir.join("red.png")
    blue = tmpdir.join("blue.png")
    make_image(str(red), 10, (255, 0, 0))
    make_image(str(blue), 20, (0, 0, 255))
    controller, selected, reference = make_controller()
    controller.updateView(FakeFile(str(blue)), FakeFile(str(red)), "group-a")
    assert controller.selectedPixmap.isNull()  # decode still pending
    assert controller.referencePixmap.isNull()
    assert pump_until(lambda: not controller.selectedPixmap.isNull())
    assert pump_until(lambda: not controller.referencePixmap.isNull())
    assert not selected.set_image_calls[-1].isNull()
    assert not reference.set_image_calls[-1].isNull()
    # The viewer shows the right photos (solid colours survive scaling).
    assert selected._pixmap.toImage().pixelColor(0, 0).red() == 255
    assert reference._pixmap.toImage().pixelColor(0, 0).blue() == 255


def test_stale_load_is_ignored(qapp, tmpdir):
    # A load that arrives for an older selection must not overwrite the
    # current one.
    red = tmpdir.join("red.png")
    make_image(str(red), 10, (255, 0, 0))
    controller, selected, reference = make_controller()
    controller.updateView(FakeFile(str(red)), FakeFile(str(red)), "group-a")
    # Wait for both loads (and the finish step that fills the viewers),
    # not just the selected pixmap.
    assert pump_until(lambda: not controller.selectedPixmap.isNull() and not controller.referencePixmap.isNull())
    stale_token = controller._load_token - 1
    stale_image = QImage(10, 10, QImage.Format_RGB32)
    stale_image.fill(QColor(0, 255, 0))
    controller._apply_loaded_image(stale_token, "selected", stale_image)
    QApplication.processEvents()
    assert selected._pixmap.toImage().pixelColor(0, 0).red() == 255


def test_rapid_selection_change_ends_on_latest(qapp, tmpdir):
    # Two selection changes in a row: whatever arrives first, the view
    # must end up showing the second selection's photos.
    red = tmpdir.join("red.png")
    blue = tmpdir.join("blue.png")
    make_image(str(red), 10, (255, 0, 0))
    make_image(str(blue), 20, (0, 0, 255))
    controller, selected, reference = make_controller()
    controller.updateView(FakeFile(str(red)), FakeFile(str(red)), "group-a")
    controller.updateView(FakeFile(str(blue)), FakeFile(str(blue)), "group-a")
    # Wait for both loads of the latest selection (and the finish step
    # that fills the viewers), not just the selected pixmap.
    assert pump_until(lambda: not controller.selectedPixmap.isNull() and not controller.referencePixmap.isNull())
    assert selected._pixmap.toImage().pixelColor(0, 0).blue() == 255


def test_ref_is_dupe_loads_only_selected(qapp, tmpdir):
    red = tmpdir.join("red.png")
    make_image(str(red), 10, (255, 0, 0))
    controller, selected, reference = make_controller()
    dupe = FakeFile(str(red))
    controller.updateView(dupe, dupe, "group-a")
    assert pump_until(lambda: not controller.selectedPixmap.isNull())
    assert controller.referencePixmap.isNull()
    assert reference._pixmap.isNull()


def test_unreadable_file_leaves_null_pixmap(qapp, tmpdir):
    # A missing file must not crash the dialog: the pixmap stays null,
    # exactly as the old synchronous QPixmap(path) behaved.
    controller, selected, reference = make_controller()
    missing = FakeFile(str(tmpdir.join("nope.png")))
    controller.updateView(missing, missing, "group-a")
    assert pump_until(lambda: not controller._pending_load_roles, timeout=5.0)
    assert controller.selectedPixmap.isNull()
    assert controller.referencePixmap.isNull()
