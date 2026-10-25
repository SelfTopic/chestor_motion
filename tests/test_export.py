import array
import json
import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from chestor_motion.engine.builder import probe
from chestor_motion.engine.export import ExportJob, ExportSettings, export_size, unique_path
from chestor_motion.project.model import (
    AudioClip,
    Clip,
    Project,
    add_audio,
    add_clip,
    detach_audio,
    fill_scale,
    set_canvas,
    set_transform,
    trim_free_end,
)


def test_export_size_by_short_side() -> None:
    assert export_size(1080, 1920, 1080) == (1080, 1920)
    assert export_size(1080, 1920, 720) == (720, 1280)
    assert export_size(1278, 590, 1080) == (2340, 1080)
    assert export_size(1920, 1080, 2160) == (3840, 2160)
    assert export_size(1080, 1920, 2160) == (2160, 3840)
    assert export_size(642, 361, 720)[0] % 2 == 0


def test_unique_path(tmp_path: Path) -> None:
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "a (2).mp4").write_bytes(b"x")
    assert unique_path(tmp_path / "a.mp4").name == "a (3).mp4"
    assert unique_path(tmp_path / "b.mp4").name == "b.mp4"


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout  # fmt: skip
    return json.loads(out)


def _run(job: ExportJob) -> str:
    result: dict[str, str] = {}
    loop = QEventLoop()
    job.finished.connect(lambda p: (result.update(path=p), loop.quit()))
    job.failed.connect(lambda e: (result.update(error=e), loop.quit()))
    QTimer.singleShot(60_000, loop.quit)
    job.start()
    loop.exec()
    assert "error" not in result, result["error"]
    return result["path"]


def _rms_per_quarter(path: Path, tmp: Path) -> list[float]:
    raw = tmp / "a.raw"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(path), "-vn", "-ac", "1", "-ar", "48000",
         "-f", "s16le", str(raw)],
        check=True,
    )  # fmt: skip
    s = array.array("h", raw.read_bytes())
    step = 12000
    return [
        (sum(x * x for x in s[i : i + step]) / step) ** 0.5 / 32768
        for i in range(0, len(s) - step + 1, step)
    ]


@pytest.fixture
def project(clip: Path, music: Path) -> Project:
    """Видео 2 с со звуком, отделённым и подрезанным до 1 с, и после — музыка 1 с."""
    n = probe(str(clip)).length
    p = add_clip(Project(width=642, height=360), Clip(str(clip), n, 0, n, id="v"))
    p = detach_audio(p, "v")
    p = trim_free_end(p, p.audio[0][0].id, 30)
    m = probe(str(music)).length
    return add_audio(p, AudioClip(str(music), m, 0, 30, start=n))  # после видео ещё 1 с звука


def test_export_project(qapp, project: Project, tmp_path: Path) -> None:
    job = ExportJob(project, ExportSettings(short_side=720, fps=30), tmp_path / "out.mp4")
    progress: list[float] = []
    job.progress.connect(progress.append)
    path = Path(_run(job))

    info = _probe(path)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"]) == (1284, 720)  # холст 642×360 → 720p
    assert video["avg_frame_rate"] == "30/1"
    assert video.get("color_space") == "bt709"
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    assert abs(float(info["format"]["duration"]) - project.length / 30) < 0.15
    assert job.gpu_used
    assert progress and progress[-1] == 1.0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.mp4"]  # без .part и .mlt

    rms = _rms_per_quarter(path, tmp_path)
    assert min(rms[:4]) > 0.03  # 1-я секунда: отделённый звук
    assert max(rms[5:7]) < 0.005  # 2-я: видео без звука, звуковой клип кончился
    assert min(rms[9:11]) > 0.03  # 3-я: музыка после видео


def test_export_60fps_keeps_duration(qapp, project: Project, tmp_path: Path) -> None:
    path = Path(
        _run(ExportJob(project, ExportSettings(short_side=360, fps=60), tmp_path / "s.mp4"))
    )
    info = _probe(path)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert video["avg_frame_rate"] == "60/1"
    assert abs(float(info["format"]["duration"]) - project.length / 30) < 0.15


def test_cancel_leaves_nothing(qapp, project: Project, tmp_path: Path) -> None:
    job = ExportJob(project, ExportSettings(short_side=1080), tmp_path / "c.mp4")
    job.start()
    job.cancel()
    assert list(tmp_path.iterdir()) == []


def test_export_vertical_canvas_letterboxes_black(qapp, project: Project, tmp_path: Path) -> None:
    vertical = set_canvas(project, 1080, 1920)
    path = _run(ExportJob(vertical, ExportSettings(short_side=360), tmp_path / "v.mp4"))
    frame = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-frames:v", "1", "-f", "rawvideo",
         "-pix_fmt", "gray", "-"],
        check=True, capture_output=True,
    ).stdout  # fmt: skip
    assert len(frame) == 360 * 640
    assert max(frame[: 360 * 100]) < 24  # верхнее поле чёрное
    assert max(frame[360 * 300 : 360 * 340]) > 60  # посередине — сам клип


def test_export_filled_clip_covers_canvas(qapp, project: Project, tmp_path: Path) -> None:
    vertical = set_canvas(project, 1080, 1920)
    filled = set_transform(vertical, "v", 0, 0, fill_scale((1080, 1920), (642, 360)))
    path = _run(ExportJob(filled, ExportSettings(short_side=360), tmp_path / "f.mp4"))
    frame = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-frames:v", "1", "-f", "rawvideo",
         "-pix_fmt", "gray", "-"],
        check=True, capture_output=True,
    ).stdout  # fmt: skip
    assert (
        min(max(frame[i * 360 : (i + 1) * 360]) for i in range(640)) > 40
    )  # ни одной чёрной строки
