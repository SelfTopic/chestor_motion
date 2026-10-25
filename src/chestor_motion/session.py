"""Открытый проект: модель + история правок + превью.

После каждой правки граф MLT собирается заново из модели и подменяется в плеере. Пока для
файла нет прокси, играет оригинал; прокси готов — сборщик подставляет его.
"""

from pathlib import Path

import mlt7 as mlt
from PySide6.QtCore import QObject, QUrl, Signal, Slot

from chestor_motion.engine.builder import Builder, make_profile, probe
from chestor_motion.engine.player import Player
from chestor_motion.engine.proxy import ProxyJob, proxy_size
from chestor_motion.project import model
from chestor_motion.project.history import History
from chestor_motion.project.model import Clip, Project
from chestor_motion.qt import qproperty

# Превью собирается в уменьшенном профиле: в 1080×1920 MLT выдаёт ~39 кадров/с, в 540×960 ~46,
# а в окне превью всё равно меньше 960 точек. Экспорт — в полном размере проекта.
PREVIEW_MAX_SIDE = 960


def preview_size(width: int, height: int) -> tuple[int, int]:
    return proxy_size(width, height, PREVIEW_MAX_SIDE)


class Session(QObject):
    statusChanged = Signal()
    projectChanged = Signal()

    def __init__(
        self, player: Player, cache_dir: Path | None = None, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._player = player
        self._cache_dir = cache_dir
        self._history = History(Project())
        self._profile: mlt.Profile | None = None
        self._builder: Builder | None = None
        self._proxies: dict[str, str] = {}
        self._jobs: dict[str, ProxyJob] = {}
        self._progress: dict[str, float] = {}
        self._status = ""

    # --- свойства для QML ---

    @qproperty(str, notify=projectChanged)
    def title(self) -> str:
        main = self._history.current.main
        return Path(main[0].source).name if main else ""

    @qproperty(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @qproperty(float, notify=statusChanged)
    def proxyProgress(self) -> float:
        """-1 — прокси не создаются, иначе общий прогресс 0..1."""
        if not self._progress:
            return -1.0
        return sum(self._progress.values()) / len(self._progress)

    @qproperty(bool, notify=projectChanged)
    def canUndo(self) -> bool:
        return self._history.can_undo

    @qproperty(bool, notify=projectChanged)
    def canRedo(self) -> bool:
        return self._history.can_redo

    @property
    def project(self) -> Project:
        return self._history.current

    # --- импорт ---

    @Slot(QUrl)
    def open(self, url: QUrl) -> None:
        self.import_path(Path(url.toLocalFile()))

    @Slot(list)
    def importUrls(self, urls: list[QUrl]) -> None:
        for url in urls:
            self.import_path(Path(url.toLocalFile()))

    def import_path(self, path: Path) -> None:
        source = str(path.resolve())
        try:
            info = probe(source)
        except OSError:
            self._set_status(f"Не удалось открыть {path.name}")
            return
        project = self.project
        if not project.main:
            # Первый клип задаёт холст, как «Оригинал» в CapCut; выбор сторон — позже
            project = Project(
                width=info.width - info.width % 2, height=info.height - info.height % 2
            )
        clip = Clip(source=source, source_length=info.length, in_frame=0, out_frame=info.length)
        self._apply(model.add_clip(project, clip), position=project.length)
        self._start_proxy(source, info.width, info.height, info.length)

    # --- правки ---

    @Slot()
    def splitAtPlayhead(self) -> None:
        self._apply(model.split(self.project, self._player.position))

    @Slot()
    def deleteAtPlayhead(self) -> None:
        hit = self.project.clip_at(self._player.position)
        if hit is not None:
            index, start = hit
            self._apply(model.delete(self.project, self.project.main[index].id), position=start)

    @Slot()
    def undo(self) -> None:
        if self._history.undo():
            self._rebuild()

    @Slot()
    def redo(self) -> None:
        if self._history.redo():
            self._rebuild()

    # --- внутреннее ---

    def _apply(self, project: Project, position: int | None = None) -> None:
        before = self._history.current
        self._history.push(project)
        if self._history.current is not before:
            self._rebuild(position)

    def _rebuild(self, position: int | None = None) -> None:
        project = self.project
        if not project.main:
            self._player.clear()
            self.projectChanged.emit()
            return
        size = preview_size(project.width, project.height)
        if self._profile is None or (self._profile.width(), self._profile.height()) != size:
            self._profile = make_profile(*size)
            self._builder = Builder(self._profile, resolve=lambda s: self._proxies.get(s, s))
        assert self._builder is not None
        self._player.show(self._builder.build(project), self._profile, position)
        self.projectChanged.emit()

    def _start_proxy(self, source: str, width: int, height: int, length: int) -> None:
        if source in self._proxies or source in self._jobs:
            return
        job = ProxyJob(
            Path(source),
            proxy_size(width, height),
            length / model.FPS,
            cache_dir=self._cache_dir,
            parent=self,
        )
        job.progress.connect(lambda p: self._on_proxy_progress(source, p))
        job.finished.connect(lambda path: self._on_proxy_ready(source, path))
        job.failed.connect(lambda e: self._on_proxy_failed(source, e))
        self._jobs[source] = job
        self._progress[source] = 0.0
        self._set_status("Создаю прокси…")
        job.start()

    def _on_proxy_progress(self, source: str, progress: float) -> None:
        if source in self._progress:
            self._progress[source] = progress
            self.statusChanged.emit()

    def _on_proxy_ready(self, source: str, proxy: str) -> None:
        self._jobs.pop(source, None)
        self._progress.pop(source, None)
        self._proxies[source] = proxy
        if self._builder is not None:
            self._builder.forget(source)
            self._rebuild()
        self._set_status("" if self._jobs else "Прокси")

    def _on_proxy_failed(self, source: str, error: str) -> None:
        self._jobs.pop(source, None)
        self._progress.pop(source, None)
        self._set_status(f"Прокси не создан: {error}")

    def _set_status(self, status: str) -> None:
        self._status = status
        self.statusChanged.emit()
