"""Форма волны для таймлайна: пик громкости на каждый кадр проекта, один байт, в децибелах.

ffmpeg отдельным процессом достаёт звук моно с частотой RATE, пики считаются в фоновом
потоке (на 24-минутную серию ~0.3 с — в GUI-потоке это рывок). Делается из исходника: звук
декодировать дёшево, ждать прокси не нужно.
"""

import array
import hashlib
import math
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QStandardPaths, QTimer, Signal

from chestor_motion.project.model import FPS

RATE = 4800
SAMPLES_PER_FRAME = RATE // FPS
# Шкала в децибелах: всё тише -48 дБ — ноль. В линейной шкале речь — едва заметная полоска
RANGE_DB = 48.0
FORMAT_VERSION = 1


def peaks_from_samples(samples: array.array) -> bytes:
    """Пик каждого кадра → байт 0..255 по шкале RANGE_DB."""
    n = len(samples) // SAMPLES_PER_FRAME
    out = bytearray(n)
    for i in range(n):
        chunk = samples[i * SAMPLES_PER_FRAME : (i + 1) * SAMPLES_PER_FRAME]
        peak = max(max(chunk), -min(chunk)) / 32768
        if peak > 0:
            db = 20 * math.log10(peak)
            out[i] = round(max(0.0, 1 + db / RANGE_DB) * 255)
    return bytes(out)


def default_cache_dir() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
    return Path(base) / "waves"


class WaveJob(QObject):
    finished = Signal(bytes)
    failed = Signal(str)
    _computed = Signal(bytes)  # из фонового потока

    def __init__(
        self, source: Path, cache_dir: Path | None = None, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._source = source
        cache_dir = cache_dir or default_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        stat = source.stat()
        key = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|{RATE}|{FPS}|v{FORMAT_VERSION}"
        self.output = cache_dir / f"{hashlib.sha1(key.encode()).hexdigest()}.peaks"
        self._raw = self.output.with_suffix(".raw")
        self._process: QProcess | None = None
        self._computed.connect(self._on_computed)

    def start(self) -> None:
        """Сигналы всегда асинхронно, даже из кэша."""
        if self.output.exists():
            data = self.output.read_bytes()
            QTimer.singleShot(0, self, lambda: self.finished.emit(data))
            return
        process = QProcess(self)
        process.finished.connect(self._on_finished)
        self._process = process
        process.start(
            "nice",
            ["-n", "10", "ffmpeg", "-v", "error", "-y", "-i", str(self._source), "-vn",
             "-ac", "1", "-ar", str(RATE), "-f", "s16le", str(self._raw)],
        )  # fmt: skip

    def cancel(self) -> None:
        if self._process is not None:
            self._process.kill()

    def _on_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        assert self._process is not None
        error = bytes(self._process.readAllStandardError().data()).decode().strip()
        self._process = None
        if code != 0 or status != QProcess.ExitStatus.NormalExit or not self._raw.exists():
            self._raw.unlink(missing_ok=True)
            # Нет звуковой дорожки — тоже сюда: волны просто не будет
            self.failed.emit(error or f"ffmpeg завершился с кодом {code}")
            return

        def compute() -> None:
            samples = array.array("h")
            samples.frombytes(self._raw.read_bytes())
            self._raw.unlink(missing_ok=True)
            peaks = peaks_from_samples(samples)
            self.output.write_bytes(peaks)
            self._computed.emit(peaks)

        threading.Thread(target=compute, daemon=True, name="waveform").start()

    def _on_computed(self, peaks: bytes) -> None:
        self.finished.emit(peaks)
