import json
import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from chestor_motion.engine.proxy import ProxyJob, proxy_size


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((1920, 1080), (1280, 720)),
        ((1080, 1920), (720, 1280)),
        ((1278, 590), (1278, 590)),
        ((641, 361), (640, 360)),
    ],
)
def test_proxy_size_fits_and_even(size: tuple[int, int], expected: tuple[int, int]) -> None:
    assert proxy_size(*size) == expected


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(out)


def _run(job: ProxyJob) -> str:
    result: dict[str, str] = {}
    loop = QEventLoop()
    job.finished.connect(lambda p: (result.update(path=p), loop.quit()))
    job.failed.connect(lambda e: (result.update(error=e), loop.quit()))
    QTimer.singleShot(60_000, loop.quit)
    job.start()
    loop.exec()
    assert "error" not in result, result["error"]
    return result["path"]


def test_proxy_is_constant_30fps(qapp, clip: Path, tmp_path: Path) -> None:
    job = ProxyJob(clip, proxy_size(642, 360), 2.0, cache_dir=tmp_path)
    path = Path(_run(job))

    streams = {s["codec_type"]: s for s in _probe(path)["streams"]}
    assert streams["video"]["avg_frame_rate"] == "30/1"
    assert (streams["video"]["width"], streams["video"]["height"]) == (642, 360)
    assert streams["audio"]["sample_rate"] == "48000"
    assert not list(tmp_path.glob("*.part.mp4"))


def test_proxy_reused_from_cache(qapp, clip: Path, tmp_path: Path) -> None:
    first = _run(ProxyJob(clip, (320, 180), 2.0, cache_dir=tmp_path))
    mtime = Path(first).stat().st_mtime_ns
    second = _run(ProxyJob(clip, (320, 180), 2.0, cache_dir=tmp_path))
    assert second == first
    assert Path(second).stat().st_mtime_ns == mtime
