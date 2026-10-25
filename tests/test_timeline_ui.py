"""Таймлайн мышью на настоящем QML (offscreen): то, что сломать легче всего незаметно."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QGuiApplication, QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from chestor_motion.__main__ import QML_DIR
from chestor_motion.engine.player import Player
from chestor_motion.session import Session
from tests.conftest import SILENT_AUDIO_OUT

L = Qt.MouseButton.LeftButton
NM = Qt.KeyboardModifier.NoModifier


class Ui:
    def __init__(self, tmp_path: Path) -> None:
        os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
        self.player = Player(SILENT_AUDIO_OUT)
        self.session = Session(self.player, cache_dir=tmp_path / "proxies")
        self.engine = QQmlApplicationEngine()
        self.warnings: list[str] = []
        self.engine.warnings.connect(lambda ws: self.warnings.extend(w.toString() for w in ws))
        self.engine.setInitialProperties({"player": self.player, "session": self.session})
        self.engine.load(QML_DIR / "Main.qml")
        window = self.engine.rootObjects()[0]
        assert isinstance(window, QQuickWindow)
        self.win = window
        timeline = window.findChild(QQuickItem, "timeline")
        assert timeline is not None
        self.tl = timeline
        self.flick = next(
            c for c in timeline.childItems() if c.metaObject().className() == "QQuickFlickable"
        )

    @property
    def px(self) -> float:
        return float(self.tl.property("pxPerFrame"))

    def x(self, frame: float) -> float:
        origin = self.tl.mapToScene(QPointF(0, 0))
        return origin.x() + 16 + frame * self.px - float(self.flick.property("contentX"))

    def track_y(self) -> float:
        return self.tl.mapToScene(QPointF(0, 0)).y() + float(self.tl.property("trackTop")) + 32

    def ruler_y(self) -> float:
        return self.tl.mapToScene(QPointF(0, 0)).y() + 12

    def click(self, x: float, y: float) -> None:
        QTest.mouseClick(self.win, L, NM, QPoint(round(x), round(y)))
        QTest.qWait(50)

    def drag(self, x0: float, y: float, x1: float, steps: int = 10) -> None:
        QTest.mousePress(self.win, L, NM, QPoint(round(x0), round(y)))
        for i in range(1, steps + 1):
            QTest.mouseMove(self.win, QPoint(round(x0 + (x1 - x0) * i / steps), round(y)))
            QTest.qWait(10)
        QTest.mouseRelease(self.win, L, NM, QPoint(round(x1), round(y)))
        QTest.qWait(50)

    def wheel(self, x: float, y: float, delta: int, mods=NM) -> None:
        event = QWheelEvent(
            QPointF(x, y), QPointF(x, y), QPoint(0, 0), QPoint(0, delta),
            Qt.MouseButton.NoButton, mods, Qt.ScrollPhase.NoScrollPhase, False,
        )  # fmt: skip
        QGuiApplication.sendEvent(self.win, event)
        QTest.qWait(30)

    def close(self) -> None:
        del self.engine
        self.session.close()
        self.player.shutdown()


@pytest.fixture
def ui(qapp, clip: Path, tmp_path: Path) -> Iterator[Ui]:
    ui = Ui(tmp_path)
    ui.session.import_path(clip)
    ui.session.import_path(clip)
    QTest.qWait(100)
    yield ui
    ui.close()
    assert not ui.warnings, ui.warnings


def test_import_fits_whole_project(ui: Ui) -> None:
    assert ui.x(ui.session.project.length) <= ui.tl.mapToScene(QPointF(ui.tl.width(), 0)).x()


def test_click_selects_and_seeks(ui: Ui) -> None:
    second = ui.session.clips[1]
    ui.click(ui.x(second["start"] + 10), ui.track_y())
    assert ui.session.selectedClip == second["id"]
    assert abs(ui.player.position - (second["start"] + 10)) <= 2


def test_drag_from_playhead_spot_moves_clip(ui: Ui) -> None:
    # После клика плейхед стоит под курсором — повторная протяжка из той же точки должна
    # тащить клип, а не плейхед
    second = ui.session.clips[1]
    x = ui.x(second["start"] + second["length"] / 2)
    ui.click(x, ui.track_y())
    ui.drag(x, ui.track_y(), ui.x(2))
    assert ui.session.clips[0]["id"] == second["id"]


def test_trim_handles(ui: Ui) -> None:
    first = ui.session.clips[0]
    ui.click(ui.x(first["length"] / 2), ui.track_y())
    end = ui.x(first["length"]) - 4
    ui.drag(end, ui.track_y(), end - 20 * ui.px)
    assert abs(ui.session.clips[0]["length"] - (first["length"] - 20)) <= 1
    start = ui.x(0) + 4
    ui.drag(start, ui.track_y(), start + 10 * ui.px)
    assert abs(ui.session.clips[0]["inFrame"] - 10) <= 1


def test_trim_keeps_zoom(ui: Ui) -> None:
    px = ui.px
    ui.session.trimEnd(ui.session.clips[0]["id"], 30)
    QTest.qWait(50)
    assert ui.px == px


def test_ctrl_wheel_zooms_and_ruler_seeks(ui: Ui) -> None:
    px = ui.px
    ui.wheel(ui.x(30), ui.track_y(), 120, Qt.KeyboardModifier.ControlModifier)
    assert ui.px > px
    ui.click(ui.x(40), ui.ruler_y())
    assert abs(ui.player.position - 40) <= 1
    assert ui.session.selectedClip == ""


def test_delete_selected_and_undo(ui: Ui) -> None:
    first = ui.session.clips[0]
    ui.click(ui.x(5), ui.track_y())
    QTest.keyClick(ui.win, Qt.Key.Key_Delete)
    QTest.qWait(50)
    assert [c["id"] for c in ui.session.clips] != [first["id"]] and len(ui.session.clips) == 1
    QTest.keyClick(ui.win, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(50)
    assert ui.session.clips[0]["id"] == first["id"]
