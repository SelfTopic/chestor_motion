import os
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Тесты не должны звучать из колонок и занимать звуковое устройство
os.environ["SDL_AUDIODRIVER"] = "dummy"
# Иначе Qt кладёт кэш QML в ~/.cache/conftest.py (имя приложения в тестах не задано)
os.environ["QML_DISABLE_DISK_CACHE"] = "1"
SILENT_AUDIO_OUT = "sdl2_audio"


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.instance() or QGuiApplication([])


@pytest.fixture(scope="session")
def clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """2 секунды 642×360 с тоном и переменной частотой кадров, как у записи экрана."""
    path = tmp_path_factory.mktemp("media") / "vfr.mp4"
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=642x360:rate=60",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
            "-t", "2", "-vf", "setpts='PTS+0.01*sin(N)/TB'", "-fps_mode", "vfr",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )  # fmt: skip
    return path


@pytest.fixture(scope="session")
def music(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """3 секунды «музыки» — тон 660 Гц в mp3."""
    path = tmp_path_factory.mktemp("media") / "music.mp3"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=660:duration=3",
         str(path)],
        check=True,
    )  # fmt: skip
    return path


@pytest.fixture(scope="session")
def red(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """1 секунда сплошного красного 320×240 со своим тоном — для наложений."""
    path = tmp_path_factory.mktemp("media") / "red.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:size=320x240:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000", "-t", "1",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", str(path)],
        check=True,
    )  # fmt: skip
    return path
