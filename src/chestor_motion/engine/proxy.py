"""Прокси: лёгкая копия клипа с постоянными 30 fps, где каждый кадр ключевой.

Каждый кадр ключевой — чтобы перемотка в любую сторону стоила одинаково дёшево: с GOP 15
перетаскивание ползунка назад или быстро давало ~13 обновлений картинки в секунду, с intra ~30.
Цена — размер, примерно втрое больше (40 с 1278×590 — 50 МБ), поэтому качество чуть ниже.

Сначала кодирует видеокарта (VA-API), при ошибке — процессор (libx264).
"""

import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QStandardPaths, QTimer, Signal

FPS = 30
MAX_SIDE = 1280
# Менять при смене параметров кодирования: старые прокси в кэше пересоздадутся
FORMAT_VERSION = 2
VAAPI_DEVICE = "/dev/dri/renderD128"


def proxy_size(width: int, height: int, max_side: int = MAX_SIDE) -> tuple[int, int]:
    """Вписывает кадр в max_side по длинной стороне, обе стороны чётные."""
    scale = min(1.0, max_side / max(width, height))
    return max(2, round(width * scale / 2) * 2), max(2, round(height * scale / 2) * 2)


def proxy_path(source: Path, cache_dir: Path) -> Path:
    stat = source.stat()
    key = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{MAX_SIDE}|{FPS}|v{FORMAT_VERSION}"
    return cache_dir / f"{hashlib.sha1(key.encode()).hexdigest()}.mp4"


def ffmpeg_args(source: Path, out: Path, size: tuple[int, int], *, vaapi: bool) -> list[str]:
    w, h = size
    args = ["-v", "error", "-nostats", "-progress", "pipe:1", "-y"]
    if vaapi:
        args += ["-hwaccel", "vaapi", "-hwaccel_device", VAAPI_DEVICE]
        args += ["-hwaccel_output_format", "vaapi", "-i", str(source)]
        args += ["-vf", f"fps={FPS},scale_vaapi=w={w}:h={h}:format=nv12"]
        args += ["-c:v", "h264_vaapi", "-qp", "28"]
    else:
        args += ["-i", str(source), "-vf", f"fps={FPS},scale={w}:{h}", "-pix_fmt", "yuv420p"]
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "26"]
    args += ["-g", "1", "-map", "0:v:0", "-map", "0:a:0?"]
    args += ["-c:a", "aac", "-ar", "48000", "-ac", "2", str(out)]
    return args


def default_cache_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
    return Path(base) / "proxies"


class ProxyJob(QObject):
    progress = Signal(float)  # 0..1
    finished = Signal(str)  # путь к готовому прокси
    failed = Signal(str)

    def __init__(
        self,
        source: Path,
        size: tuple[int, int],
        duration_s: float,
        cache_dir: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.source = source
        self._size = size
        self._duration_us = max(1.0, duration_s * 1_000_000)
        cache_dir = cache_dir or default_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.output = proxy_path(source, cache_dir)
        self._part = self.output.with_suffix(".part.mp4")
        self._vaapi = True
        self._process: QProcess | None = None

    def start(self) -> None:
        """Сигналы всегда приходят асинхронно, даже если прокси уже в кэше."""
        if self.output.exists():
            QTimer.singleShot(0, self, self._emit_cached)
            return
        self._run()

    def _emit_cached(self) -> None:
        self.progress.emit(1.0)
        self.finished.emit(str(self.output))

    def cancel(self) -> None:
        if self._process is not None:
            self._process.kill()

    def _run(self) -> None:
        process = QProcess(self)
        process.readyReadStandardOutput.connect(self._on_output)
        process.finished.connect(self._on_finished)
        self._process = process
        process.start("ffmpeg", ffmpeg_args(self.source, self._part, self._size, vaapi=self._vaapi))

    def _on_output(self) -> None:
        assert self._process is not None
        for line in bytes(self._process.readAllStandardOutput().data()).decode().splitlines():
            key, _, value = line.partition("=")
            if key == "out_time_us" and value.isdigit():
                self.progress.emit(min(1.0, int(value) / self._duration_us))

    def _on_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        assert self._process is not None
        error = bytes(self._process.readAllStandardError().data()).decode().strip()
        self._process = None
        if code == 0 and status == QProcess.ExitStatus.NormalExit:
            self._part.replace(self.output)
            self.progress.emit(1.0)
            self.finished.emit(str(self.output))
        elif self._vaapi and status == QProcess.ExitStatus.NormalExit:
            self._vaapi = False
            self._run()
        else:
            self._part.unlink(missing_ok=True)
            self.failed.emit(error or f"ffmpeg завершился с кодом {code}")
