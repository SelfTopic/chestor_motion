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
