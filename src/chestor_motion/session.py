"""Открытый проект: модель + история правок + превью + файл проекта.

После каждой правки граф MLT собирается заново из модели и подменяется в плеере. Пока для
файла нет прокси, играет оригинал; прокси готов — сборщик подставляет его.

Сохранять руками не нужно, как в CapCut: через AUTOSAVE_MS после правки проект пишется в свой
файл. У нового проекта файл появляется при первой правке — черновик в data_dir/drafts.
"""

from datetime import datetime
from pathlib import Path

import mlt7 as mlt
from PySide6.QtCore import QByteArray, QObject, QStandardPaths, QTimer, QUrl, Signal, Slot

from chestor_motion.engine.builder import Builder, make_profile, probe
from chestor_motion.engine.player import Player
from chestor_motion.engine.proxy import (
    ProxyJob,
    clean_stale_parts,
    enforce_cache_limit,
    proxy_size,
)
from chestor_motion.engine.proxy import default_cache_dir as default_proxy_dir
from chestor_motion.engine.thumbs import ThumbJob
from chestor_motion.engine.waves import WaveJob
from chestor_motion.project import io, model
from chestor_motion.project.history import History
from chestor_motion.project.model import Clip, Project
from chestor_motion.project.state import State
from chestor_motion.qt import qproperty

# Превью собирается в уменьшенном профиле: в 1080×1920 MLT выдаёт ~39 кадров/с, в 540×960 ~46,
# а в окне превью всё равно меньше 960 точек. Экспорт — в полном размере проекта.
PREVIEW_MAX_SIDE = 960
AUTOSAVE_MS = 1500


def default_data_dir() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))


def preview_size(width: int, height: int) -> tuple[int, int]:
    return proxy_size(width, height, PREVIEW_MAX_SIDE)


class Session(QObject):
    statusChanged = Signal()
    projectChanged = Signal()
    selectionChanged = Signal()
    thumbsChanged = Signal()
    wavesChanged = Signal()
    imported = Signal()
    fileChanged = Signal()

    def __init__(
        self,
        player: Player,
        cache_dir: Path | None = None,
        data_dir: Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._player = player
        self._cache_dir = cache_dir
        self._data_dir = data_dir or default_data_dir()
        self._state = State(self._data_dir)
        self._proxy_dir = cache_dir or default_proxy_dir()
        if self._proxy_dir.is_dir():
            clean_stale_parts(self._proxy_dir)
        self._path: Path | None = None
        self._saved = Project()
        self._autosave = QTimer(self)
        self._autosave.setSingleShot(True)
        self._autosave.setInterval(AUTOSAVE_MS)
        self._autosave.timeout.connect(self.flush)
        self._history = History(Project())
        self._profile: mlt.Profile | None = None
        self._builder: Builder | None = None
        self._proxies: dict[str, str] = {}
        self._jobs: dict[str, ProxyJob] = {}
        # Прокси кодируются по одному: пять файлов разом — пять ffmpeg одновременно
        self._proxy_queue: list[ProxyJob] = []
        self._proxy_running: ProxyJob | None = None
        self._progress: dict[str, float] = {}
        self._proxy_sizes: dict[str, tuple[int, int]] = {}
        self._lengths: dict[str, int] = {}
        self._thumb_jobs: dict[str, ThumbJob] = {}
        self._thumbs: dict[str, dict] = {}
        self._wave_jobs: dict[str, WaveJob] = {}
        # QByteArray, а не bytes: байты Python внутри словаря доходят до QML обёрткой
        self._waves: dict[str, QByteArray] = {}
        self._selected = ""
        self._status = ""
        self._closed = False

    # --- свойства для QML ---

    @qproperty(str, notify=fileChanged)
    def title(self) -> str:
        """Имя проекта: имя файла без расширения, у нового — «Новый проект»."""
        return self._path.stem if self._path else "Новый проект"

    @qproperty(str, notify=fileChanged)
    def projectPath(self) -> str:
        return str(self._path) if self._path else ""

    @qproperty(str, notify=fileChanged)
    def saveFolder(self) -> str:
        """Где начинать «Сохранить как»: у проекта — его папка, у нового — «Видео»."""
        if self._path and self._path.parent != self.drafts_dir:
            return QUrl.fromLocalFile(str(self._path.parent)).toString()
        movies = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation)
        return QUrl.fromLocalFile(movies).toString()

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

    @qproperty(list, notify=projectChanged)
    def clips(self) -> list:
        """Клипы основной дорожки для таймлайна: позиции уже посчитаны."""
        out, start = [], 0
        for c in self.project.main:
            out.append(
                {
                    "id": c.id,
                    "source": c.source,
                    "start": start,
                    "length": c.length,
                    "inFrame": c.in_frame,
                    "outFrame": c.out_frame,
                    "sourceLength": c.source_length,
                }
            )
            start += c.length
        return out

    @qproperty(str, notify=selectionChanged)
    def selectedClip(self) -> str:
        return self._selected

    @qproperty(dict, notify=thumbsChanged)
    def thumbs(self) -> dict:
        """Сетки миниатюр по пути к исходнику (см. ThumbJob.info)."""
        return self._thumbs

    @qproperty(dict, notify=wavesChanged)
    def waves(self) -> dict:
        """Пики громкости по пути к исходнику: байт на кадр (см. engine/waves.py)."""
        return self._waves

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def drafts_dir(self) -> Path:
        return self._data_dir / "drafts"

    @property
    def project(self) -> Project:
        return self._history.current

    # --- импорт ---

    @Slot(list)
    def importUrls(self, urls: list[QUrl]) -> None:
        for url in urls:
            self.import_path(Path(url.toLocalFile()))

    @Slot(list)
    def importPaths(self, paths: list[str]) -> None:
        for path in paths:
            self.import_path(Path(path))

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
        self.imported.emit()
        self._start_proxy(source, info.width, info.height, info.length)
        self._start_wave(source)

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
    def deleteSelectedOrAtPlayhead(self) -> None:
        """Delete: выделенный клип, а если ничего не выделено — клип под плейхедом."""
        if not self._has(self._selected):
            self.deleteAtPlayhead()
            return
        index = self.project.index_of(self._selected)
        start = self.project.clip_start(index)
        self._apply(model.delete(self.project, self._selected), position=start)

    @Slot(str)
    def select(self, clip_id: str) -> None:
        if clip_id != self._selected:
            self._selected = clip_id
            self.selectionChanged.emit()

    @Slot(str, int)
    def trimStart(self, clip_id: str, in_frame: int) -> None:
        if self._has(clip_id):
            index = self.project.index_of(clip_id)
            # Начало клипа на таймлайне не двигается — плейхед ставим на него
            start = self.project.clip_start(index)
            self._apply(model.trim_start(self.project, clip_id, in_frame), position=start)

    @Slot(str, int)
    def trimEnd(self, clip_id: str, out_frame: int) -> None:
        if self._has(clip_id):
            project = model.trim_end(self.project, clip_id, out_frame)
            index = project.index_of(clip_id)
            end = project.clip_start(index) + project.main[index].length - 1
            self._apply(project, position=end)

    @Slot(str, int)
    def moveClip(self, clip_id: str, to_index: int) -> None:
        if self._has(clip_id):
            project = model.move(self.project, clip_id, to_index)
            self._apply(project, position=project.clip_start(project.index_of(clip_id)))

    @Slot()
    def undo(self) -> None:
        if self._history.undo():
            self._rebuild()

    @Slot()
    def redo(self) -> None:
        if self._history.redo():
            self._rebuild()

    # --- файл проекта ---

    @Slot()
    def newProject(self) -> None:
        self.flush()
        self._set_project(Project(), None)

    @Slot(str)
    def openProjectPath(self, path: str) -> None:
        self.open_project(Path(path))

    def open_project(self, path: Path) -> bool:
        try:
            project = io.load(path)
        except (OSError, io.ProjectFormatError) as e:
            self._set_status(f"Не удалось открыть проект: {e}")
            return False
        missing = sorted({Path(c.source).name for c in project.main if not Path(c.source).exists()})
        if missing:
            self._set_status("Нет исходных файлов: " + ", ".join(missing))
            return False
        self.flush()
        self._set_project(project, path)
        for source in dict.fromkeys(c.source for c in project.main):
            info = probe(source)
            self._start_proxy(source, info.width, info.height, info.length)
            self._start_wave(source)
        return True

    @Slot()
    def save(self) -> None:
        """Ctrl+S: проект и так сохраняется сам — записать прямо сейчас и сказать куда."""
        self.flush(force=True)
        if self._path:
            self._set_status(f"Сохранено: {self._path}")

    @Slot(QUrl)
    def saveAs(self, url: QUrl) -> None:
        self.save_as(Path(url.toLocalFile()))

    def save_as(self, path: Path) -> None:
        if path.suffix != io.SUFFIX:
            path = path.with_name(path.name + io.SUFFIX)
        self._path = path
        self.flush(force=True)
        self.fileChanged.emit()
        self._set_status(f"Сохранено: {path}")

    def restore_last(self) -> bool:
        """При запуске без файлов — открыть прошлый проект."""
        last = self._state.get("last", "")
        return (
            isinstance(last, str)
            and bool(last)
            and Path(last).exists()
            and self.open_project(Path(last))
        )

    @Slot()
    def flush(self, force: bool = False) -> None:
        """Записать проект, если есть несохранённые правки (или force)."""
        self._autosave.stop()
        project = self.project
        if project == self._saved and not force:
            return
        if not project.main and self._path is None:
            return  # пустой новый проект черновиком не нужен
        if self._path is None:
            self.drafts_dir.mkdir(parents=True, exist_ok=True)
            self._path = self.drafts_dir / f"Черновик {datetime.now():%Y-%m-%d %H-%M-%S}{io.SUFFIX}"
            self.fileChanged.emit()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        io.save(project, self._path)
        self._saved = project
        self._remember(self._path)

    def close(self) -> None:
        """Сохранить и остановить фоновые задачи. Готовый позже прокси иначе пересоберёт граф и
        запустит консьюмер на уже закрытом плеере."""
        self.flush()
        self._closed = True
        for job in [*self._jobs.values(), *self._thumb_jobs.values(), *self._wave_jobs.values()]:
            job.cancel()
        self._jobs.clear()
        self._proxy_queue.clear()
        self._proxy_running = None
        self._thumb_jobs.clear()
        self._wave_jobs.clear()
        self._progress.clear()

    # --- внутреннее ---

    def _set_project(self, project: Project, path: Path | None) -> None:
        self._history = History(project)
        self._saved = project
        self._path = path
        if path is not None:
            self._remember(path)
        self._selected = ""
        self.selectionChanged.emit()
        self.fileChanged.emit()
        self._rebuild(position=0)
        self.imported.emit()  # таймлайн подгоняет масштаб под весь проект

    def _remember(self, path: Path) -> None:
        self._state.set("last", str(path))

    def _has(self, clip_id: str) -> bool:
        return any(c.id == clip_id for c in self.project.main)

    def _apply(self, project: Project, position: int | None = None) -> None:
        before = self._history.current
        self._history.push(project)
        if self._history.current is not before:
            self._rebuild(position)

    def _rebuild(self, position: int | None = None) -> None:
        if self._closed:
            return
        project = self.project
        # Не перезапускать идущий таймер: пересборка бывает и без правки (готов прокси), и она
        # не должна откладывать сохранение
        if project != self._saved and not self._autosave.isActive():
            self._autosave.start()
        if not project.main:
            self._player.clear()
            if self._selected:
                self._selected = ""
                self.selectionChanged.emit()
            self.projectChanged.emit()
            return
        size = preview_size(project.width, project.height)
        if self._profile is None or (self._profile.width(), self._profile.height()) != size:
            self._profile = make_profile(*size)
            self._builder = Builder(self._profile, resolve=lambda s: self._proxies.get(s, s))
        assert self._builder is not None
        self._player.show(self._builder.build(project), self._profile, position)
        if self._selected and not self._has(self._selected):
            self._selected = ""
            self.selectionChanged.emit()
        self.projectChanged.emit()

    def _start_proxy(self, source: str, width: int, height: int, length: int) -> None:
        if source in self._proxies or source in self._jobs:
            return
        self._proxy_sizes[source] = proxy_size(width, height)
        self._lengths[source] = length
        job = ProxyJob(
            Path(source),
            self._proxy_sizes[source],
            length / model.FPS,
            cache_dir=self._cache_dir,
            parent=self,
        )
        job.progress.connect(lambda p: self._on_proxy_progress(source, p))
        job.finished.connect(lambda path: self._on_proxy_ready(source, path))
        job.failed.connect(lambda e: self._on_proxy_failed(source, e))
        self._jobs[source] = job
        self._progress[source] = 0.0
        if job.output.exists():
            job.start()  # готовый из кэша — без очереди, кодировать нечего
            return
        self._proxy_queue.append(job)
        self._next_proxy()
        self._proxy_status()

    def _proxy_status(self) -> None:
        waiting = len(self._proxy_queue)
        self._set_status(
            f"Создаю прокси… (ещё {waiting} в очереди)" if waiting else "Создаю прокси…"
        )

    def _next_proxy(self) -> None:
        if self._proxy_running is not None or self._closed:
            return
        while self._proxy_queue:
            job = self._proxy_queue.pop(0)
            if str(job.source) in self._jobs:  # не отменён, пока ждал
                self._proxy_running = job
                self._proxy_status()
                job.start()
                return

    def _proxy_done(self, source: str) -> None:
        job = self._jobs.pop(source, None)
        self._progress.pop(source, None)
        if job is not None and job is self._proxy_running:
            self._proxy_running = None
            self._next_proxy()

    def _on_proxy_progress(self, source: str, progress: float) -> None:
        if source in self._progress:
            self._progress[source] = progress
            self.statusChanged.emit()

    def _on_proxy_ready(self, source: str, proxy: str) -> None:
        if self._closed:
            return
        self._proxy_done(source)
        self._proxies[source] = proxy
        enforce_cache_limit(self._proxy_dir, keep={Path(p) for p in self._proxies.values()})
        if self._builder is not None:
            self._builder.forget(source)
            self._rebuild()
        if not self._jobs:
            self._set_status("Прокси")
        self._start_thumbs(source, proxy)

    def _start_thumbs(self, source: str, proxy: str) -> None:
        if source in self._thumbs or source in self._thumb_jobs:
            return
        job = ThumbJob(
            Path(proxy),
            self._proxy_sizes[source],
            self._lengths[source],
            cache_dir=self._cache_dir.parent / "thumbs" if self._cache_dir else None,
            parent=self,
        )
        job.finished.connect(lambda info: self._on_thumbs_ready(source, info))
        job.failed.connect(lambda _e: self._thumb_jobs.pop(source, None))
        self._thumb_jobs[source] = job
        job.start()

    def _on_thumbs_ready(self, source: str, info: dict) -> None:
        if self._closed:
            return
        self._thumb_jobs.pop(source, None)
        self._thumbs = {**self._thumbs, source: info}
        self.thumbsChanged.emit()

    def _start_wave(self, source: str) -> None:
        if source in self._waves or source in self._wave_jobs:
            return
        job = WaveJob(
            Path(source),
            cache_dir=self._cache_dir.parent / "waves" if self._cache_dir else None,
            parent=self,
        )
        job.finished.connect(lambda peaks: self._on_wave_ready(source, peaks))
        job.failed.connect(lambda _e: self._wave_jobs.pop(source, None))  # нет звука — нет волны
        self._wave_jobs[source] = job
        job.start()

    def _on_wave_ready(self, source: str, peaks: bytes) -> None:
        if self._closed:
            return
        self._wave_jobs.pop(source, None)
        self._waves = {**self._waves, source: QByteArray(peaks)}
        self.wavesChanged.emit()

    def _on_proxy_failed(self, source: str, error: str) -> None:
        self._proxy_done(source)
        self._set_status(f"Прокси не создан: {error}")

    def _set_status(self, status: str) -> None:
        self._status = status
        self.statusChanged.emit()
