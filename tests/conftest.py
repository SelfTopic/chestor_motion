import os
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Тесты не должны звучать из колонок и занимать звуковое устройство
os.environ["SDL_AUDIODRIVER"] = "dummy"
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
