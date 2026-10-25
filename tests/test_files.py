import os
import threading
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer

from chestor_motion.files import FileBrowser, list_dir, obs_recordings_dir, search
from chestor_motion.project.state import State


def _touch(path: Path, mtime: float = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


def test_list_dir_folders_then_newest_videos(tmp_path: Path) -> None:
    (tmp_path / "b_dir").mkdir()
    (tmp_path / "A_dir").mkdir()
    (tmp_path / ".hidden_dir").mkdir()
    _touch(tmp_path / "old.mp4", 1_000)
    _touch(tmp_path / "new.MKV", 2_000)
    _touch(tmp_path / "notes.txt")
    _touch(tmp_path / ".secret.mp4")

    names = [e["name"] for e in list_dir(tmp_path, show_hidden=False, mode="media")]
    assert names == ["A_dir", "b_dir", "new.MKV", "old.mp4"]

    with_hidden = [e["name"] for e in list_dir(tmp_path, show_hidden=True, mode="media")]
    assert ".hidden_dir" in with_hidden and ".secret.mp4" in with_hidden

    only_files = [e["name"] for e in list_dir(tmp_path, False, "media", files_only=True)]
    assert only_files == ["new.MKV", "old.mp4"]


def test_list_dir_projects_mode(tmp_path: Path) -> None:
    _touch(tmp_path / "a.cmproj")
    _touch(tmp_path / "b.mp4")
    assert [e["name"] for e in list_dir(tmp_path, False, "project")] == ["a.cmproj"]


def test_list_dir_missing_folder_is_empty(tmp_path: Path) -> None:
    assert list_dir(tmp_path / "nope", False, "media") == []


def test_search_matches_all_words_in_subfolders(tmp_path: Path) -> None:
    _touch(tmp_path / "games" / "mlbb" / "Ranked Win 2026.mp4")
    _touch(tmp_path / "games" / "ranked loss.mp4")
    _touch(tmp_path / "games" / "win.txt")
    _touch(tmp_path / ".cache" / "ranked win.mp4")  # скрытые папки не ищем
    _touch(tmp_path / "node_modules" / "ranked win.mp4")

    found = search(tmp_path, "win RANKED", "media", threading.Event())
    assert [Path(f["path"]).name for f in found] == ["Ranked Win 2026.mp4"]


def test_search_can_be_cancelled(tmp_path: Path) -> None:
    _touch(tmp_path / "a.mp4")
    cancelled = threading.Event()
    cancelled.set()
    assert search(tmp_path, "a", "media", cancelled) == []


def test_obs_dir_from_config(tmp_path: Path, monkeypatch) -> None:
    recordings = tmp_path / "rec"
    recordings.mkdir()
    ini = tmp_path / ".config/obs-studio/basic/profiles/P/basic.ini"
    ini.parent.mkdir(parents=True)
    ini.write_text(f"[SimpleOutput]\nFilePath={recordings}\n", encoding="utf-8")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert obs_recordings_dir() == recordings


def test_places_and_recent(qapp, tmp_path: Path) -> None:
    drafts = tmp_path / "data" / "drafts"
    drafts.mkdir(parents=True)
    browser = FileBrowser(tmp_path / "data", drafts)
    kinds = {p["title"]: p["kind"] for p in browser.places}
    assert kinds["Черновики"] == "place" and kinds["Домашняя папка"] == "place"

    folders = []
    for i in range(10):
        folder = tmp_path / f"f{i}"
        folder.mkdir()
        folders.append(str(folder))
        browser.remember(str(folder))
    browser.remember(folders[3])  # повтор поднимается наверх, а не дублируется
    recent = [p["path"] for p in browser.places if p["kind"] == "recent"]
    assert recent[0] == folders[3] and len(recent) == 8 and len(set(recent)) == 8


def test_state_keys_do_not_clobber(tmp_path: Path) -> None:
    a, b = State(tmp_path), State(tmp_path)
    a.set("last", "/x.cmproj")
    b.set("recent_dirs", ["/y"])
    assert State(tmp_path).get("last") == "/x.cmproj"


def test_background_search_signal(qapp, tmp_path: Path) -> None:
    _touch(tmp_path / "deep" / "er" / "clip one.mp4")
    browser = FileBrowser(tmp_path / "data", tmp_path / "drafts")
    got: list = []
    loop = QEventLoop()
    browser.searchResults.connect(lambda sid, found, done: (got.append((sid, found)), loop.quit()))
    QTimer.singleShot(5_000, loop.quit)
    sid = browser.startSearch(str(tmp_path), "one", "media")
    loop.exec()
    assert got and got[0][0] == sid and Path(got[0][1][0]["path"]).name == "clip one.mp4"
