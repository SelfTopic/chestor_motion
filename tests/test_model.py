import json
from dataclasses import replace
from pathlib import Path

import pytest

from chestor_motion.project import io
from chestor_motion.project.history import History
from chestor_motion.project.model import (
    AudioClip,
    Clip,
    Project,
    add_audio,
    add_clip,
    delete,
    detach_audio,
    fill_scale,
    frame_rect,
    move,
    move_audio,
    set_canvas,
    set_transform,
    split,
    split_audio,
    trim_audio_end,
    trim_audio_start,
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


# --- звук ---


def _audio(start: int, length: int = 30, id: str | None = None) -> AudioClip:
    clip = AudioClip(source="/m.mp3", source_length=1000, in_frame=0, out_frame=length, start=start)
    return clip if id is None else replace(clip, id=id)


def test_detach_audio_puts_sound_under_the_clip() -> None:
    p = _project(30, 50)
    p = detach_audio(p, "c1")
    assert p.main[1].audio is False and p.main[0].audio is True
    (sound,) = p.audio[0]
    assert (sound.start, sound.in_frame, sound.out_frame) == (30, 0, 50)
    assert detach_audio(p, "c1") == p  # второй раз нечего отделять


def test_audio_lanes_never_overlap() -> None:
    p = add_audio(Project(), _audio(0, 30, "a"))
    p = add_audio(p, _audio(10, 30, "b"))  # пересекается с a — во вторую дорожку
    p = add_audio(p, _audio(40, 10, "c"))  # свободно в первой
    assert [[c.id for c in lane] for lane in p.audio] == [["a", "c"], ["b"]]
    assert p.length == 50


def test_move_audio_and_empty_lanes_vanish() -> None:
    p = add_audio(add_audio(Project(), _audio(0, 30, "a")), _audio(10, 30, "b"))
    p = move_audio(p, "b", 100)  # в своей дорожке, дальше
    assert [[c.id for c in lane] for lane in p.audio] == [["a"], ["b"]]
    p = move_audio(p, "b", 40, lane=0)  # в первую, там свободно
    assert [[c.id for c in lane] for lane in p.audio] == [["a", "b"]]
    p = move_audio(p, "b", -50)  # не в минус; в 0 занято клипом a — новая дорожка
    assert [[c.id for c in lane] for lane in p.audio] == [["a"], ["b"]]
    assert p.audio_clip("b")[1].start == 0  # type: ignore[index]


def test_trim_audio_respects_neighbours() -> None:
    p = add_audio(add_audio(Project(), _audio(0, 30, "a")), _audio(40, 30, "b"))
    p = trim_audio_end(p, "a", 500)  # упирается в b: конец a не дальше 40
    assert p.audio_clip("a")[1].end == 40  # type: ignore[index]
    p = trim_audio_start(p, "b", 20)  # левый край b едет вправо вместе с in
    b = p.audio_clip("b")[1]  # type: ignore[index]
    assert (b.in_frame, b.start, b.end) == (20, 60, 70)
    p = trim_audio_start(p, "b", 0)  # назад — только до конца a и не в минус in
    b = p.audio_clip("b")[1]  # type: ignore[index]
    assert (b.in_frame, b.start) == (0, 40)


def test_split_audio_and_delete() -> None:
    p = add_audio(Project(), _audio(10, 30, "a"))
    p = split_audio(p, "a", 25)
    left, right = p.audio[0]
    assert (left.start, left.end, right.start, right.in_frame, right.end) == (10, 25, 25, 15, 40)
    assert split_audio(p, "a", 10) == p  # на краю — нечего резать
    p = delete(delete(p, left.id), right.id)
    assert p.audio == ()


def test_split_main_keeps_detached_flag() -> None:
    p = detach_audio(_project(100), "c0")
    assert all(not c.audio for c in split(p, 40).main)


def test_v1_file_is_migrated(tmp_path: Path) -> None:
    path = tmp_path / "old.cmproj"
    path.write_text(json.dumps({
        "format": "chestor_motion", "version": 1, "width": 10, "height": 10,
        "main": [{"id": "x", "source": "/a.mp4", "source_length": 9, "in": 0, "out": 9}],
    }))  # fmt: skip
    p = io.load(path)
    assert p.main[0].audio is True and p.audio == ()


def test_save_load_with_audio(tmp_path: Path) -> None:
    p = add_audio(detach_audio(_project(100, 40), "c0"), _audio(150, 20, "music"))
    path = tmp_path / "p.cmproj"
    io.save(p, path)
    assert io.load(path) == p


def test_move_audio_below_last_lane_makes_new_lane() -> None:
    p = add_audio(add_audio(Project(), _audio(0, 30, "a")), _audio(100, 30, "b"))
    assert len(p.audio) == 1
    p = move_audio(p, "b", 100, lane=1)  # в первой дорожке место есть, но просили новую
    assert [[c.id for c in lane] for lane in p.audio] == [["a"], ["b"]]
    p = move_audio(p, "b", 40, lane=0)  # обратно наверх — нижняя пустеет и исчезает
    assert [[c.id for c in lane] for lane in p.audio] == [["a", "b"]]


def test_set_canvas_keeps_clips_and_evens_size() -> None:
    p = add_clip(Project(width=642, height=360), Clip("a.mp4", 60, 0, 60))
    q = set_canvas(p, 1081, 1921)
    assert (q.width, q.height) == (1080, 1920) and q.main == p.main
    with pytest.raises(ValueError):
        set_canvas(p, 0, 1920)


def test_frame_rect_and_fill() -> None:
    # 16:9 на 9:16: вписан — во всю ширину по центру
    assert frame_rect((1080, 1920), (1920, 1080), 0, 0, 1) == (0, 656.25, 1080, 607.5)
    fill = fill_scale((1080, 1920), (1920, 1080))
    left, top, w, h = frame_rect((1080, 1920), (1920, 1080), 0, 0, fill)
    assert (round(top), round(h)) == (0, 1920) and left < 0 and w > 1080
    # сдвиг в долях холста
    assert frame_rect((1000, 1000), (100, 100), 0.25, -0.5, 0.5)[:2] == (500, -250)


def test_set_transform_keeps_through_split_and_clamps(tmp_path: Path) -> None:
    p = set_transform(_project(100), "c0", 0.1, -0.2, 3.0)
    p = split(p, 50)
    assert all((c.x, c.y, c.scale) == (0.1, -0.2, 3.0) for c in p.main)
    assert set_transform(p, "c0", 0, 0, 1000).main[0].scale == 20.0
    assert not set_transform(p, "c0", 0, 0, 1).main[0].transformed
    path = tmp_path / "t.cmproj"
    io.save(p, path)
    assert io.load(path) == p


def test_v2_file_gets_default_transform(tmp_path: Path) -> None:
    data = io.to_dict(_project(100))
    data["version"] = 2
    for c in data["main"]:
        del c["x"], c["y"], c["scale"]
    path = tmp_path / "v2.cmproj"
    path.write_text(json.dumps(data))
    assert io.load(path) == _project(100)
