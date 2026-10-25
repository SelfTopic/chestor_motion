"""Экспорт: граф проекта из оригиналов в полном размере → MLT XML → отдельный процесс melt.

Отдельный процесс — интерфейс не замирает, а падение рендера не роняет программу. Кодирует
видеокарта (h264_vaapi), не вышло — процессор (libx264) с пониженным приоритетом и
ограничением потоков: x264 на все ядра однажды грел ноутбук до 89°C.
"""

import re
import time
from dataclasses import dataclass
from pathlib import Path

import mlt7 as mlt
from PySide6.QtCore import QObject, QProcess, Signal

from chestor_motion.engine.builder import Builder, make_profile
from chestor_motion.engine.proxy import VAAPI_DEVICE
from chestor_motion.project.model import FPS, Project

MAX_SIDE = 3840
CPU_THREADS = "4"
# Битрейт для видеокарты при 1080p и 30 fps; для других размеров и частоты — пропорционально
BITRATE_1080P30 = {"high": 16_000_000, "normal": 8_000_000}
CRF = {"high": "18", "normal": "23"}


@dataclass(frozen=True)
class ExportSettings:
    short_side: int = 1080  # 720 / 1080 / 1440 / 2160 — по короткой стороне холста
    fps: int = 30  # 30 или 60
    quality: str = "high"  # high / normal


def export_size(width: int, height: int, short_side: int) -> tuple[int, int]:
    """Холст проекта в нужном разрешении по короткой стороне; обе стороны чётные."""
    scale = short_side / min(width, height)
    scale = min(scale, MAX_SIDE / max(width, height))
    return max(2, round(width * scale / 2) * 2), max(2, round(height * scale / 2) * 2)


def bitrate(size: tuple[int, int], settings: ExportSettings) -> int:
    pixels = size[0] * size[1] / (1920 * 1080)
    return int(BITRATE_1080P30[settings.quality] * pixels * settings.fps / 30)


def write_mlt(project: Project, settings: ExportSettings, path: Path) -> tuple[int, int]:
    """Граф проекта из оригиналов в файл MLT XML. Возвращает размер кадра."""
    size = export_size(project.width, project.height, settings.short_side)
    profile = make_profile(*size, fps=settings.fps)
    graph = Builder(profile, scale=settings.fps // FPS).build(project)
    consumer = mlt.Consumer(profile, "xml", str(path))
    consumer.connect(graph)
    consumer.start()
    while not consumer.is_stopped():
        time.sleep(0.01)
    return size


def melt_args(mlt_file: Path, out: Path, size: tuple[int, int], settings: ExportSettings,
              gpu: bool) -> list[str]:  # fmt: skip
    args = ["-progress", str(mlt_file), "-consumer", f"avformat:{out}", "real_time=-1"]
    args += ["acodec=aac", "ab=192k", "ar=48000", "channels=2", "movflags=+faststart"]
    if gpu:
        args += [
            "vcodec=h264_vaapi",
            f"vaapi_device={VAAPI_DEVICE}",
            f"vb={bitrate(size, settings)}",
        ]
    else:
        args += ["vcodec=libx264", "preset=medium", f"crf={CRF[settings.quality]}"]
        args += [f"threads={CPU_THREADS}"]
    return args


def unique_path(path: Path) -> Path:
    """«Ролик.mp4» занято — «Ролик (2).mp4» и так далее."""
    if not path.exists():
        return path
    n = 2
    while (candidate := path.with_name(f"{path.stem} ({n}){path.suffix}")).exists():
        n += 1
    return candidate


_PROGRESS = re.compile(r"percentage:\s*(\d+)")


class ExportJob(QObject):
    progress = Signal(float)  # 0..1
    finished = Signal(str)
    failed = Signal(str)

    def __init__(
        self, project: Project, settings: ExportSettings, output: Path,
        parent: QObject | None = None,
    ) -> None:  # fmt: skip
        super().__init__(parent)
        self._project = project
        self._settings = settings
        self.output = output
        self._part = output.with_name(output.stem + ".part" + output.suffix)
        self._mlt = output.with_name("." + output.stem + ".export.mlt")
        self._gpu = True
        self.gpu_used = False
        self._process: QProcess | None = None
        self._size = (0, 0)

    def start(self) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self._size = write_mlt(self._project, self._settings, self._mlt)
        self._run()

    def cancel(self) -> None:
        if self._process is not None:
            self._process.finished.disconnect()
            self._process.kill()
            self._process.waitForFinished(2000)
            self._process = None
        self._cleanup()

    def _run(self) -> None:
        process = QProcess(self)
        process.readyReadStandardError.connect(self._on_stderr)
        process.finished.connect(self._on_finished)
        self._process = process
        args = melt_args(self._mlt, self._part, self._size, self._settings, self._gpu)
        process.start("nice", ["-n", "10", "melt", *args])

    def _on_stderr(self) -> None:
        assert self._process is not None
        text = bytes(self._process.readAllStandardError().data()).decode(errors="replace")
        for match in _PROGRESS.finditer(text):
            self.progress.emit(min(1.0, int(match.group(1)) / 100))

    def _on_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        self._process = None
        ok = code == 0 and status == QProcess.ExitStatus.NormalExit and self._valid(self._part)
        if ok:
            self.gpu_used = self._gpu
            self._part.replace(self.output)
            self._cleanup()
            self.progress.emit(1.0)
            self.finished.emit(str(self.output))
        elif self._gpu and status == QProcess.ExitStatus.NormalExit:
            self._gpu = False  # видеокарта не справилась — процессором
            self._run()
        else:
            self._cleanup()
            self.failed.emit(f"melt завершился с кодом {code}")

    @staticmethod
    def _valid(path: Path) -> bool:
        # melt иногда выходит с кодом 0, ничего не записав (не открылся кодировщик)
        return path.exists() and path.stat().st_size > 1024

    def _cleanup(self) -> None:
        self._part.unlink(missing_ok=True)
        self._mlt.unlink(missing_ok=True)
