import json
import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import QEventLoop, QTimer

from chestor_motion.engine.proxy import (
    CPU_THREADS,
    MODES,
    ProxyJob,
    clean_stale_parts,
    enforce_cache_limit,
    ffmpeg_args,
    proxy_size,
)


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
    key_frames = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "frame=key_frame",
         "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout.split()  # fmt: skip
    assert {k.strip(",") for k in key_frames} == {"1"}, (
        "каждый кадр прокси должен быть ключевым — для перемотки"
    )
    assert not list(tmp_path.glob("*.part.mp4"))


def test_proxy_reused_from_cache(qapp, clip: Path, tmp_path: Path) -> None:
    first = _run(ProxyJob(clip, (320, 180), 2.0, cache_dir=tmp_path))
    inode = Path(first).stat().st_ino
    again = ProxyJob(clip, (320, 180), 2.0, cache_dir=tmp_path)
    second = _run(again)
    assert second == first
    assert again.mode == ""  # ffmpeg не запускался
    assert Path(second).stat().st_ino == inode


def test_args_per_mode() -> None:
    src, out = Path("/in.mp4"), Path("/out.mp4")
    gpu = ffmpeg_args(src, out, (640, 360), "gpu")
    hybrid = ffmpeg_args(src, out, (640, 360), "hybrid")
    cpu = ffmpeg_args(src, out, (640, 360), "cpu")
    assert "-hwaccel" in gpu and "h264_vaapi" in gpu
    assert "-hwaccel" not in hybrid and "hwupload" in " ".join(hybrid) and "h264_vaapi" in hybrid
    assert "libx264" in cpu and "ultrafast" in cpu
    for args in (hybrid, cpu):  # процессорные части ограничены двумя потоками
        assert args[args.index("-threads") + 1] == CPU_THREADS
    assert MODES == ("gpu", "hybrid", "cpu")


def test_10bit_h264_goes_hybrid_not_cpu(qapp, tmp_path: Path) -> None:
    # Radeon 610M не декодирует H.264 10-bit: раньше это сразу уходило в x264 на все ядра
    src = tmp_path / "10bit.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30", "-t", "1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p10le", str(src)],
        check=True,
    )  # fmt: skip
    job = ProxyJob(src, (640, 360), 1.0, cache_dir=tmp_path / "p")
    path = Path(_run(job))
    assert job.mode == "hybrid"
    encoder = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream_tags=encoder", "-of", "csv=p=0",
         str(path)], capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    assert "h264_vaapi" in encoder


def test_stale_parts_cleaned(tmp_path: Path) -> None:
    (tmp_path / "a.part.mp4").write_bytes(b"x")
    (tmp_path / "b.mp4").write_bytes(b"x")
    clean_stale_parts(tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["b.mp4"]


def test_cache_limit_removes_least_recently_used(tmp_path: Path) -> None:
    import os

    files = {}
    for i, name in enumerate(["old", "mid", "new", "kept_old"]):
        f = tmp_path / f"{name}.mp4"
        f.write_bytes(b"x" * 100)
        os.utime(f, (1000 + i, 1000 + i))
        files[name] = f
    os.utime(files["kept_old"], (1, 1))  # самый старый, но в текущем проекте
    (tmp_path / "x.part.mp4").write_bytes(b"x" * 1000)  # недоделанный не считается

    removed = enforce_cache_limit(tmp_path, keep={files["kept_old"]}, limit=250)
    assert sorted(p.name for p in removed) == ["mid.mp4", "old.mp4"]
    assert files["new"].exists() and files["kept_old"].exists()


def test_cached_proxy_use_marks_it_fresh(qapp, clip: Path, tmp_path: Path) -> None:
    import os

    first = Path(_run(ProxyJob(clip, (320, 180), 2.0, cache_dir=tmp_path)))
    os.utime(first, (1, 1))
    _run(ProxyJob(clip, (320, 180), 2.0, cache_dir=tmp_path))
    assert first.stat().st_mtime > 1_000_000
