"""Своё окно выбора файлов: быстрые места, недавние папки, поиск видео по имени (Ctrl+F).

Список папки — синхронно (это быстро), поиск — в фоновом потоке: os.scandir отпускает GIL на
время системных вызовов, интерфейс не замирает. Результаты приходят сигналом через очередь.
"""

import configparser
import os
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, Signal, Slot

from chestor_motion.project import io
from chestor_motion.project.state import State
from chestor_motion.qt import qproperty

VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".flv", ".ts", ".mts", ".m2ts"}
RECENT_LIMIT = 8
SEARCH_LIMIT = 300
SEARCH_DEPTH = 8
# Папки, где видео не ищем: огромные и не про видео
SEARCH_SKIP = {"node_modules", "__pycache__", "site-packages", ".git", ".venv", "venv", "proc"}


def suffixes(mode: str) -> set[str]:
    """mode: media — видео для импорта, project — файлы проектов."""
    return {io.SUFFIX} if mode == "project" else VIDEO_SUFFIXES


def entry(path: Path, is_dir: bool, stat: os.stat_result | None = None) -> dict:
    stat = stat or path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "isDir": is_dir,
        "size": 0 if is_dir else stat.st_size,
        "modified": stat.st_mtime * 1000,  # миллисекунды — так удобно Date в QML
        "hidden": path.name.startswith("."),
    }


def list_dir(path: Path, show_hidden: bool, mode: str, files_only: bool = False) -> list[dict]:
    """Папки по имени, потом нужные файлы — сначала свежие."""
    wanted = suffixes(mode)
    dirs, files = [], []
    try:
        with os.scandir(path) as it:
            for e in it:
                if e.name.startswith(".") and not show_hidden:
                    continue
                try:
                    if e.is_dir():
                        if not files_only:
                            dirs.append(entry(Path(e.path), True, e.stat()))
                    elif Path(e.name).suffix.lower() in wanted:
                        files.append(entry(Path(e.path), False, e.stat()))
                except OSError:
                    continue  # битая ссылка, нет прав — просто пропустить
    except OSError:
        return []
    dirs.sort(key=lambda d: d["name"].lower())
    files.sort(key=lambda f: f["modified"], reverse=True)
    return dirs + files


def obs_recordings_dir() -> Path | None:
    """Куда OBS пишет записи — из его настроек (первый профиль, где путь задан)."""
    profiles = Path.home() / ".config" / "obs-studio" / "basic" / "profiles"
    for ini in sorted(profiles.glob("*/basic.ini")):
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            parser.read(ini, encoding="utf-8")
        except (OSError, configparser.Error):
            continue
        for section in ("AdvOut", "SimpleOutput"):
            for key in ("RecFilePath", "FilePath"):
                value = parser.get(section, key, fallback="")
                if value and Path(value).is_dir():
                    return Path(value)
    return None


def search(root: Path, query: str, mode: str, cancelled: threading.Event) -> list[dict]:
    """Файлы под root, в имени которых есть все слова запроса (без учёта регистра)."""
    words = query.lower().split()
    wanted = suffixes(mode)
    found: list[dict] = []
    stack = [(root, 0)]
    while stack and not cancelled.is_set() and len(found) < SEARCH_LIMIT:
        folder, depth = stack.pop()
        try:
            with os.scandir(folder) as it:
                for e in it:
                    if e.name.startswith(".") or e.name in SEARCH_SKIP:
                        continue
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if depth < SEARCH_DEPTH:
                                stack.append((Path(e.path), depth + 1))
                        elif Path(e.name).suffix.lower() in wanted:
                            name = e.name.lower()
                            if all(w in name for w in words):
                                found.append(entry(Path(e.path), False, e.stat()))
                    except OSError:
                        continue
        except OSError:
            continue
    found.sort(key=lambda f: f["modified"], reverse=True)
    return found


class FileBrowser(QObject):
    placesChanged = Signal()
    searchResults = Signal(int, list, bool)  # номер поиска, найденное, закончен ли

    def __init__(self, data_dir: Path, drafts_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state = State(data_dir)
        self._drafts = drafts_dir
        drafts_dir.mkdir(parents=True, exist_ok=True)  # чтобы «Черновики» были в местах сразу
        self._search_id = 0
        self._cancel = threading.Event()

    @qproperty(list, notify=placesChanged)
    def places(self) -> list:
        """Быстрые места: стандартные папки, записи OBS, черновики, недавние."""

        def std(location: QStandardPaths.StandardLocation) -> Path:
            return Path(QStandardPaths.writableLocation(location))

        out: list[dict] = []

        def add(title: str, path: Path, kind: str, files_only: bool = False) -> None:
            same = (str(path), kind, files_only)
            if path.is_dir() and not any(
                (p["path"], p["kind"], p["filesOnly"]) == same for p in out
            ):
                out.append(
                    {"title": title, "path": str(path), "kind": kind, "filesOnly": files_only}
                )

        add("Видео", std(QStandardPaths.StandardLocation.MoviesLocation), "place")
        obs = obs_recordings_dir()
        if obs is not None:
            add("Записи OBS", obs, "place", files_only=True)
        add("Загрузки", std(QStandardPaths.StandardLocation.DownloadLocation), "place")
        add("Домашняя папка", Path.home(), "place")
        add("Черновики", self._drafts, "place")
        for recent in self._state.get("recent_dirs", []):
            add(Path(recent).name or recent, Path(recent), "recent")
        return out

    @Slot(str, bool, str, bool, result=list)
    def listDir(self, path: str, show_hidden: bool, mode: str, files_only: bool) -> list:
        return list_dir(Path(path), show_hidden, mode, files_only)

    @Slot(str, result=str)
    def parentDir(self, path: str) -> str:
        return str(Path(path).parent)

    @Slot(str, result=bool)
    def isDir(self, path: str) -> bool:
        return Path(path).is_dir()

    @Slot(str)
    def remember(self, folder: str) -> None:
        """Папка, откуда только что импортировали или открыли, — первой в «Недавних»."""
        recent = [folder] + [r for r in self._state.get("recent_dirs", []) if r != folder]
        self._state.set("recent_dirs", recent[:RECENT_LIMIT])
        self.placesChanged.emit()

    @Slot(str, str, str, result=int)
    def startSearch(self, root: str, query: str, mode: str) -> int:
        """Запустить поиск; предыдущий отменяется. Возвращает номер — по нему QML отличает
        ответ на свой последний запрос от запоздавших."""
        self._cancel.set()
        self._cancel = cancelled = threading.Event()
        self._search_id += 1
        search_id = self._search_id

        def run() -> None:
            found = search(Path(root), query, mode, cancelled)
            if not cancelled.is_set():
                self.searchResults.emit(search_id, found, True)

        threading.Thread(target=run, daemon=True, name="file-search").start()
        return search_id

    @Slot()
    def cancelSearch(self) -> None:
        self._cancel.set()
