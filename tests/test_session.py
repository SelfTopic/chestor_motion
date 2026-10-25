from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtTest import QTest

from chestor_motion.engine.player import Player
from chestor_motion.session import Session, preview_size
from tests.conftest import SILENT_AUDIO_OUT


def _wait_proxies(session: Session) -> None:
    loop = QEventLoop()
    timer = QTimer()
    timer.timeout.connect(lambda: session.proxyProgress < 0 and loop.quit())
    timer.start(20)
    QTimer.singleShot(30_000, loop.quit)
    loop.exec()


def _session(tmp_path: Path) -> tuple[Session, Player]:
    player = Player(SILENT_AUDIO_OUT)
    return Session(player, cache_dir=tmp_path / "proxies"), player


def test_preview_size_fits_960() -> None:
    assert preview_size(1080, 1920) == (540, 960)
    assert preview_size(1278, 590) == (960, 444)
    assert preview_size(640, 360) == (640, 360)


def test_import_sets_canvas_and_switches_to_proxy(qapp, clip: Path, tmp_path: Path) -> None:
    session, player = _session(tmp_path)
    try:
        session.import_path(clip)
        assert (session.project.width, session.project.height) == (642, 360)
        assert player.hasMedia and player.length == session.project.length
        _wait_proxies(session)
        assert list((tmp_path / "proxies").glob("*.mp4"))
        assert player.length == session.project.length
    finally:
        session.close()
        player.shutdown()


def test_split_delete_undo_redo(qapp, clip: Path, tmp_path: Path) -> None:
    session, player = _session(tmp_path)
    try:
        session.import_path(clip)
        session.import_path(clip)
        total = session.project.length
        player.seek(10)
        session.splitAtPlayhead()
        assert len(session.project.main) == 3
        session.deleteAtPlayhead()  # удаляет правую половину первого клипа
        assert len(session.project.main) == 2
        assert session.project.length == total - (session.project.main[1].length - 10)
        assert player.length == session.project.length
        session.undo()
        assert len(session.project.main) == 3 and player.length == total
        session.redo()
        assert len(session.project.main) == 2
    finally:
        session.close()
        player.shutdown()


def test_import_broken_file_reports(qapp, tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    session, player = _session(tmp_path)
    session.import_path(bad)
    assert not session.project.main
    assert "Не удалось открыть" in session.status
    session.close()
    player.shutdown()


def test_mouse_edits_and_selection(qapp, clip: Path, tmp_path: Path) -> None:
    session, player = _session(tmp_path)
    try:
        session.import_path(clip)
        session.import_path(clip)
        a, b = (c["id"] for c in session.clips)
        session.select(b)
        session.moveClip(b, 0)
        assert [c["id"] for c in session.clips] == [b, a]
        assert player.position == 0
        session.trimEnd(b, 20)
        assert session.clips[0]["length"] == 20
        assert player.position == 19  # плейхед на конце подрезанного клипа
        session.trimStart(b, 5)
        assert (session.clips[0]["inFrame"], session.clips[0]["length"]) == (5, 15)
        session.deleteSelectedOrAtPlayhead()
        assert [c["id"] for c in session.clips] == [a]
        assert session.selectedClip == ""  # удалённый клип снимает выделение
    finally:
        session.close()
        player.shutdown()


def test_thumbs_after_proxy(qapp, clip: Path, tmp_path: Path) -> None:
    session, player = _session(tmp_path)
    try:
        session.import_path(clip)
        loop = QEventLoop()
        session.thumbsChanged.connect(loop.quit)
        QTimer.singleShot(30_000, loop.quit)
        loop.exec()
        info = session.thumbs[str(clip.resolve())]
        assert info["count"] == 2 and Path(QUrl(info["url"]).toLocalFile()).exists()
    finally:
        session.close()
        player.shutdown()


def test_late_proxy_does_not_revive_closed_player(qapp, clip: Path, tmp_path: Path) -> None:
    # Прокси, готовый после закрытия плеера, раньше пересобирал граф и запускал консьюмер на
    # закрытом плеере — второй sdl2_audio в процессе ронял следующий тест
    session, player = _session(tmp_path)
    session.import_path(clip)
    player.shutdown()  # сессию не закрываем — прокси доделается и сообщит о готовности
    _wait_proxies(session)
    assert not player.hasMedia
    session.close()


def test_close_cancels_background_jobs(qapp, clip: Path, tmp_path: Path) -> None:
    session, player = _session(tmp_path)
    session.import_path(clip)
    session.close()
    player.shutdown()
    QTest.qWait(1500)  # дольше, чем делается прокси для 2-секундного ролика
    assert not list((tmp_path / "proxies").glob("*.mp4"))
