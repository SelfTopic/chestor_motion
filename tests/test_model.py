import json
from pathlib import Path

import pytest

from chestor_motion.project import io
from chestor_motion.project.history import History
from chestor_motion.project.model import (
    Clip,
    Project,
    add_clip,
    delete,
    move,
    split,
    trim_end,
    trim_start,
)


def _clip(length: int = 100, id: str | None = None) -> Clip:
    clip = Clip(source="/media/a.mp4", source_length=length, in_frame=0, out_frame=length)
    return clip if id is None else Clip(clip.source, clip.source_length, 0, length, id=id)


def _project(*lengths: int) -> Project:
    project = Project()
    for i, length in enumerate(lengths):
        project = add_clip(project, _clip(length, id=f"c{i}"))
    return project


def test_clip_rejects_bad_range() -> None:
    with pytest.raises(ValueError):
        Clip(source="x", source_length=10, in_frame=5, out_frame=5)
    with pytest.raises(ValueError):
        Clip(source="x", source_length=10, in_frame=0, out_frame=11)


def test_positions_on_magnetic_track() -> None:
    p = _project(30, 50, 20)
    assert p.length == 100
    assert p.clip_start(2) == 80
    assert p.clip_at(0) == (0, 0)
    assert p.clip_at(29) == (0, 0)
    assert p.clip_at(30) == (1, 30)
    assert p.clip_at(99) == (2, 80)
    assert p.clip_at(100) is None


def test_split_keeps_total_length_and_source_frames() -> None:
    p = trim_start(_project(100), "c0", 10)  # клип показывает кадры 10..100 исходника
    after = split(p, 25)
    left, right = after.main
    assert (left.in_frame, left.out_frame) == (10, 35)
    assert (right.in_frame, right.out_frame) == (35, 100)
    assert left.id == "c0" and right.id != "c0"
    assert after.length == p.length


@pytest.mark.parametrize("frame", [0, 30, 100, -5])
def test_split_on_boundary_or_outside_is_noop(frame: int) -> None:
    p = _project(30, 70)
    assert split(p, frame) == p


def test_delete_closes_gap() -> None:
    p = delete(_project(30, 50, 20), "c1")
    assert [c.id for c in p.main] == ["c0", "c2"]
    assert p.clip_at(30) == (1, 30)


def test_move() -> None:
    p = _project(10, 20, 30)
    assert [c.id for c in move(p, "c0", 2).main] == ["c1", "c2", "c0"]
    assert [c.id for c in move(p, "c2", 0).main] == ["c2", "c0", "c1"]
    assert [c.id for c in move(p, "c1", 99).main] == ["c0", "c2", "c1"]


def test_trim_is_clamped_to_source() -> None:
    p = _project(100)
    assert trim_start(p, "c0", -10).main[0].in_frame == 0
    assert trim_start(p, "c0", 500).main[0].in_frame == 99
    assert trim_end(p, "c0", 500).main[0].out_frame == 100
    assert trim_end(trim_start(p, "c0", 40), "c0", 10).main[0].out_frame == 41


def test_history_undo_redo() -> None:
    h = History(_project(100))
    h.push(split(h.current, 50))
    h.push(delete(h.current, "c0"))
    assert len(h.current.main) == 1
    assert h.undo() and len(h.current.main) == 2
    assert h.undo() and len(h.current.main) == 1 and h.current.main[0].length == 100
    assert not h.undo()
    assert h.redo() and len(h.current.main) == 2
    h.push(split(h.current, 10))  # новая правка обнуляет redo
    assert not h.can_redo


def test_history_ignores_noop() -> None:
    h = History(_project(100))
    h.push(split(h.current, 0))
    assert not h.can_undo


def test_save_load_roundtrip(tmp_path: Path) -> None:
    p = trim_end(split(_project(100, 40), 30), "c1", 25)
    path = tmp_path / f"p{io.SUFFIX}"
    io.save(p, path)
    assert io.load(path) == p
    assert json.loads(path.read_text())["version"] == io.VERSION
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        '{"format": "other", "version": 1}',
        '{"format": "chestor_motion", "version": 999}',
        '{"format": "chestor_motion", "version": 1, "width": 1, "height": 1,'
        ' "main": [{"id": "a"}]}',
    ],
)
def test_load_rejects_broken(tmp_path: Path, text: str) -> None:
    path = tmp_path / "bad.cmproj"
    path.write_text(text)
    with pytest.raises(io.ProjectFormatError):
        io.load(path)
