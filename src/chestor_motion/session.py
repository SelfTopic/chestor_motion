"""Открытый клип: сразу играет оригинал, а когда готов прокси — тихо переключается на него."""

from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot

from chestor_motion.engine.player import Player
from chestor_motion.engine.proxy import ProxyJob, proxy_size
from chestor_motion.qt import qproperty


class Session(QObject):
    statusChanged = Signal()

    def __init__(self, player: Player, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = player
        self._job: ProxyJob | None = None
        self._title = ""
        self._status = ""
        self._proxy_progress = -1.0

    @qproperty(str, notify=statusChanged)
    def title(self) -> str:
        return self._title

    @qproperty(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @qproperty(float, notify=statusChanged)
    def proxyProgress(self) -> float:
        """-1 — прокси не создаётся, иначе 0..1."""
        return self._proxy_progress

    @Slot(QUrl)
    def open(self, url: QUrl) -> None:
        self.open_path(Path(url.toLocalFile()))

    def open_path(self, path: Path) -> None:
        if self._job is not None:
            self._job.cancel()
            self._job = None
        self._title = path.name
        if not self._player.load(path):
            self._set_status(f"Не удалось открыть {path.name}", -1.0)
            return
        width, height = self._player.size
        job = ProxyJob(path, proxy_size(width, height), self._player.length / self._player.fps)
        job.progress.connect(lambda p: self._set_status("Создаю прокси…", p))
        job.finished.connect(self._on_proxy_ready)
        job.failed.connect(lambda e: self._set_status(f"Прокси не создан: {e}", -1.0))
        self._job = job
        self._set_status("Создаю прокси…", 0.0)
        job.start()

    def _on_proxy_ready(self, proxy: str) -> None:
        self._job = None
        self._player.load(Path(proxy), self._player.position)
        self._set_status("Прокси", -1.0)

    def _set_status(self, status: str, progress: float) -> None:
        self._status = status
        self._proxy_progress = progress
        self.statusChanged.emit()
