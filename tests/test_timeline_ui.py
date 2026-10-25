"""Таймлайн мышью на настоящем QML (offscreen): то, что сломать легче всего незаметно."""

import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QMetaObject, QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QGuiApplication, QWheelEvent
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from chestor_motion.__main__ import QML_DIR
from chestor_motion.engine.player import Player
from chestor_motion.files import FileBrowser
from chestor_motion.session import Session
from tests.conftest import SILENT_AUDIO_OUT

L = Qt.MouseButton.LeftButton
NM = Qt.KeyboardModifier.NoModifier


class Ui:
    def __init__(self, tmp_path: Path) -> None:
        os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
        self.player = Player(SILENT_AUDIO_OUT)
        self.session = Session(
            self.player, cache_dir=tmp_path / "proxies", data_dir=tmp_path / "data"
        )
        self.engine = QQmlApplicationEngine()
        self.warnings: list[str] = []
        self.engine.warnings.connect(lambda ws: self.warnings.extend(w.toString() for w in ws))
        self.files = FileBrowser(self.session.data_dir, self.session.drafts_dir)
        self.engine.setInitialProperties(
            {"player": self.player, "session": self.session, "files": self.files}
        )
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

    def type(self, text: str) -> None:
        """QTest.keyClicks в PySide только для виджетов — печатаем по клавише."""
        for ch in text:
            QTest.keyClick(self.win, Qt.Key(ord(ch.upper())))

    def browser(self) -> QObject:
        browser = self.win.findChild(QObject, "fileBrowser")
        assert browser is not None
        return browser

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


def test_scrollbar_appears_on_zoom_and_scrolls(ui: Ui) -> None:
    bar = ui.tl.findChild(QQuickItem, "timelineScrollBar")
    assert bar is not None
    assert float(bar.property("size")) >= 0.999  # всё помещается — прокручивать нечего
    for _ in range(6):
        ui.wheel(ui.x(10), ui.track_y(), 120, Qt.KeyboardModifier.ControlModifier)
    assert float(bar.property("size")) < 0.5 and bar.isVisible()
    handle = bar.property("contentItem")
    assert handle.width() > 0 and handle.isVisible()
    before = float(ui.flick.property("contentX"))
    centre = handle.mapToScene(QPointF(handle.width() / 2, handle.height() / 2))
    ui.drag(centre.x(), centre.y(), centre.x() + 200)
    assert float(ui.flick.property("contentX")) > before + 100


def test_project_menu(ui: Ui, tmp_path: Path) -> None:
    ui.session.save_as(tmp_path / "menu.cmproj")
    button = ui.win.findChild(QQuickItem, "projectButton")
    assert button is not None
    centre = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
    ui.click(centre.x(), centre.y())
    menu = ui.win.findChild(QObject, "projectMenu")
    assert menu is not None and menu.property("visible")
    QTest.keyClick(ui.win, Qt.Key.Key_Escape)
    QTest.qWait(50)
    assert not menu.property("visible")
    QTest.keyClick(ui.win, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(50)
    assert not ui.session.project.main and ui.session.title == "Новый проект"


def test_hotkeys_panel_lists_every_shortcut(ui: Ui) -> None:
    hotkeys = ui.win.property("hotkeys").toVariant()
    keyed = [h for h in hotkeys if h["keys"] and not h.get("local")]
    assert len(keyed) >= 15 and all(h["text"] for h in hotkeys)
    sequences = [k for h in keyed for k in h["keys"]]
    assert len(sequences) == len(set(sequences)), "одна клавиша — одно действие"

    panel = ui.win.findChild(QObject, "hotkeysPanel")
    assert panel is not None and not panel.property("visible")
    QTest.keyClick(ui.win, Qt.Key.Key_F1)
    QTest.qWait(100)
    assert panel.property("visible")
    QTest.keyClick(ui.win, Qt.Key.Key_Escape)
    QTest.qWait(300)
    assert not panel.property("visible")

    button = ui.win.findChild(QQuickItem, "helpButton")
    assert button is not None
    centre = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
    ui.click(centre.x(), centre.y())
    QTest.qWait(100)
    assert panel.property("visible")


def test_shortcuts_from_the_list_work(ui: Ui) -> None:
    ui.player.seek(20)
    QTest.keyClick(ui.win, Qt.Key.Key_S)
    QTest.qWait(50)
    assert len(ui.session.clips) == 3
    QTest.keyClick(ui.win, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(50)
    assert len(ui.session.clips) == 2
    QTest.keyClick(
        ui.win,
        Qt.Key.Key_Z,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    QTest.qWait(50)
    assert len(ui.session.clips) == 3


def test_file_browser_search_and_import(ui: Ui, clip: Path, tmp_path: Path) -> None:
    media = tmp_path / "media"
    (media / "deep" / "er").mkdir(parents=True)
    shutil.copy(clip, media / "deep" / "er" / "sample shot.mp4")
    (media / ".hidden").mkdir()
    (media / "notes.txt").write_text("x")

    browser = ui.browser()
    QTest.keyClick(ui.win, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(100)
    assert browser.property("visible") and browser.property("mode") == "media"

    browser.setProperty("folder", str(media))
    QMetaObject.invokeMethod(browser, "refresh")
    names = [e["name"] for e in browser.property("entries")]
    assert names == ["deep"]  # скрытое и не-видео не видно

    QTest.keyClick(ui.win, Qt.Key.Key_H, Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(50)
    assert ".hidden" in [e["name"] for e in browser.property("entries")]

    clips_before = len(ui.session.clips)
    QTest.keyClick(ui.win, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    ui.type("sample")  # «s» не должна резать клип на таймлайне
    QTest.qWait(400)  # поиск стартует, когда перестали печатать (250 мс)
    for _ in range(30):
        if not browser.property("busy"):
            break
        QTest.qWait(100)
    assert browser.property("searching")
    found = browser.property("entries")
    assert [e["name"] for e in found] == ["sample shot.mp4"]
    assert len(ui.session.clips) == clips_before

    QTest.keyClick(ui.win, Qt.Key.Key_Down)  # из поиска — в список
    QTest.keyClick(ui.win, Qt.Key.Key_Return)
    QTest.qWait(100)
    assert not browser.property("visible")
    assert len(ui.session.clips) == clips_before + 1
    recent = [p["path"] for p in ui.files.places if p["kind"] == "recent"]
    assert recent[0] == str(media / "deep" / "er")


def test_file_browser_escape_clears_search_then_closes(ui: Ui) -> None:
    browser = ui.browser()
    QTest.keyClick(ui.win, Qt.Key.Key_O, Qt.KeyboardModifier.ControlModifier)
    QTest.qWait(100)
    assert browser.property("mode") == "project"
    QTest.keyClick(ui.win, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    ui.type("x")
    QTest.keyClick(ui.win, Qt.Key.Key_Escape)
    QTest.qWait(50)
    assert browser.property("visible") and not browser.property("searching")
    QTest.keyClick(ui.win, Qt.Key.Key_Escape)
    QTest.qWait(300)
    assert not browser.property("visible")


def test_hotkeys_panel_scrolls_with_keys(ui: Ui) -> None:
    ui.win.resize(1000, 600)  # низкое окно — справка точно не влезает
    QTest.qWait(50)
    QTest.keyClick(ui.win, Qt.Key.Key_F1)
    QTest.qWait(100)
    scroller = ui.win.findChild(QQuickItem, "hotkeysScroller")
    assert scroller is not None
    assert float(scroller.property("contentHeight")) > scroller.height()
    QTest.keyClick(ui.win, Qt.Key.Key_PageDown)
    assert float(scroller.property("contentY")) > 0
    QTest.keyClick(ui.win, Qt.Key.Key_End)
    end = float(scroller.property("contentY"))
    assert abs(end - (float(scroller.property("contentHeight")) - scroller.height())) < 1
    QTest.keyClick(ui.win, Qt.Key.Key_Home)
    assert float(scroller.property("contentY")) == 0
