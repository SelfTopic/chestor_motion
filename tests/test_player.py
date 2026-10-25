from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtMultimedia import QVideoSink

from chestor_motion.engine.player import Player
from tests.conftest import SILENT_AUDIO_OUT


def _wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_load_normalizes_to_30fps(qapp, clip: Path) -> None:
    player = Player(SILENT_AUDIO_OUT)
    try:
        assert player.load(clip)
        assert player.size == (642, 360)
        assert 58 <= player.length <= 62  # 2 с при 30 fps, а не при исходных ~60
    finally:
        player.shutdown()


def test_frames_reach_sink_and_position_advances(qapp, clip: Path) -> None:
    player = Player(SILENT_AUDIO_OUT)
    sink = QVideoSink()
    frames = []
    sink.videoFrameChanged.connect(frames.append)
    player.set_video_sink(sink)
    try:
        player.load(clip)
        _wait(300)
        assert frames, "кадр на паузе должен прийти после load"
        assert frames[-1].size().width() == 642

        player.play()
        _wait(700)
        assert player.playing
        assert player.position > 5

        player.seek(45)
        player.pause()
        assert player.position == 45
    finally:
        player.shutdown()


def test_invalid_file(qapp, tmp_path: Path) -> None:
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    player = Player(SILENT_AUDIO_OUT)
    assert not player.load(bad)
    assert not player.hasMedia


def test_stop_while_playing_does_not_deadlock(qapp, clip: Path) -> None:
    # consumer.stop() из SWIG держал GIL, пока поток MLT ждал GIL в колбэке, и вис навсегда
    player = Player(SILENT_AUDIO_OUT)
    for _ in range(15):
        player.load(clip)
        player.play()
        _wait(40)
        player.shutdown()
    assert not player.playing


def test_scrubbing_does_not_deadlock(qapp, clip: Path) -> None:
    # Перемотка на паузе шлёт refresh; SWIG-вызов держал GIL, пока ждал мьютекс консьюмера,
    # а консьюмер держал мьютекс и ждал GIL в колбэке — окно зависало при таскании ползунка
    player = Player(SILENT_AUDIO_OUT)
    player.load(clip)
    try:
        for i in range(20_000):
            player.seek(i * 7 % player.length)
            if i % 50 == 0:
                qapp.processEvents()
        assert player.position == 19_999 * 7 % player.length
    finally:
        player.shutdown()


def test_picture_follows_scrubber_on_pause(qapp, clip: Path) -> None:
    # Таскание ползунка на паузе: seek каждые 16 мс, картинка обязана догнать последний
    player = Player(SILENT_AUDIO_OUT)
    shown: list[int] = []
    player._frameShown.connect(lambda _frame, pos: shown.append(pos))
    player.load(clip, 0)
    target = {"pos": 0}

    def tick() -> None:
        target["pos"] += 1
        player.seek(target["pos"])
        if target["pos"] < 50:
            QTimer.singleShot(16, tick)

    try:
        tick()
        _wait(16 * 50 + 400)
        assert shown[-1] == 50
        assert len(set(shown)) > 15, "картинка должна обновляться и по ходу перетаскивания"
    finally:
        player.shutdown()
