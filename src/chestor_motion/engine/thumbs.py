"""Миниатюры для таймлайна: один кадр в секунду, склеенные в одну картинку-сетку на файл.

Делаются из прокси: в нём каждый кадр ключевой, поэтому лишние пакеты выбрасываются ещё до
декодера (bsf noise=drop) и декодируется только каждый 30-й кадр. 82 с видео — 0.3 с вместо
5 с при честном fps=1. Работает отдельный процесс ffmpeg — GIL и интерфейс не задеты.
"""

import hashlib
import math
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QStandardPaths, QTimer, QUrl, Signal

from chestor_motion.project.model import FPS

TILE_HEIGHT = 56
COLUMNS = 20
INTERVAL = FPS  # кадров между миниатюрами
FORMAT_VERSION = 1


def tile_width(width: int, height: int) -> int:
    return max(2, round(width * TILE_HEIGHT / height / 2) * 2)


def default_cache_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
    return Path(base) / "thumbs"


class ThumbJob(QObject):
    finished = Signal(dict)  # описание сетки для QML, см. info()
    failed = Signal(str)

    def __init__(
        self,
        proxy: Path,
        size: tuple[int, int],
        length: int,
        cache_dir: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        """proxy — прокси (каждый кадр ключевой), size — его размер, length — длина в кадрах."""
        super().__init__(parent)
        self._proxy = proxy
        self._tile_width = tile_width(*size)
        self._count = max(1, math.ceil(length / INTERVAL))
        self._rows = math.ceil(self._count / COLUMNS)
        cache_dir = cache_dir or default_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = f"{proxy.resolve()}|{TILE_HEIGHT}|{COLUMNS}|{INTERVAL}|v{FORMAT_VERSION}"
        self.output = cache_dir / f"{hashlib.sha1(key.encode()).hexdigest()}.jpg"
        self._part = self.output.with_suffix(".part.jpg")
        self._process: QProcess | None = None

    def info(self) -> dict:
        return {
            "url": QUrl.fromLocalFile(str(self.output)).toString(),
            "columns": COLUMNS,
            "count": self._count,
            "interval": INTERVAL,
            "tileWidth": self._tile_width,
            "tileHeight": TILE_HEIGHT,
        }

    def start(self) -> None:
        """Сигналы всегда приходят асинхронно, даже если сетка уже в кэше."""
        if self.output.exists():
            QTimer.singleShot(0, self, lambda: self.finished.emit(self.info()))
            return
        process = QProcess(self)
        process.finished.connect(self._on_finished)
        self._process = process
        process.start("ffmpeg", self.ffmpeg_args())

    def cancel(self) -> None:
        if self._process is not None:
            self._process.kill()

    def ffmpeg_args(self) -> list[str]:
        return [
            "-v", "error", "-y",
            # Выбросить все пакеты, кроме каждого INTERVAL-го, ещё до декодера
            "-bsf:v", f"noise=drop=mod(n\\,{INTERVAL})",
            "-i", str(self._proxy), "-an",
            "-vf", f"scale={self._tile_width}:{TILE_HEIGHT},tile={COLUMNS}x{self._rows}",
            "-fps_mode", "passthrough", "-frames:v", "1", "-q:v", "4",
            str(self._part),
        ]  # fmt: skip

    def _on_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        assert self._process is not None
        error = bytes(self._process.readAllStandardError().data()).decode().strip()
        self._process = None
        if code == 0 and status == QProcess.ExitStatus.NormalExit and self._part.exists():
            self._part.replace(self.output)
            self.finished.emit(self.info())
        else:
            self._part.unlink(missing_ok=True)
            self.failed.emit(error or f"ffmpeg завершился с кодом {code}")
