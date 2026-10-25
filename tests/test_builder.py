import shutil
from pathlib import Path

import pytest

from chestor_motion.engine.builder import Builder, make_profile
from chestor_motion.project.model import Clip, Project, add_clip, split, trim_start


@pytest.fixture
def builder() -> Builder:
    return Builder(make_profile(540, 960))


def _layout(builder: Builder, project: Project) -> list[tuple[int, int, int, str]]:
    """(начало на таймлайне, первый кадр, последний кадр, файл) каждого клипа плейлиста."""
    playlist = builder.build(project)
    out = []
    for i in range(playlist.count()):
        info = playlist.clip_info(i)
        out.append((info.start, info.frame_in, info.frame_out, Path(info.resource).name))
    return out


def test_source_length_in_project_frames(builder: Builder, clip: Path) -> None:
    assert 58 <= builder.source_length(str(clip)) <= 62  # 2 с при 30 fps


def test_build_matches_model(builder: Builder, clip: Path) -> None:
    n = builder.source_length(str(clip))
    project = add_clip(Project(), Clip(str(clip), n, 0, n))
    project = trim_start(split(project, 20), project.main[0].id, 5)

    playlist = builder.build(project)
    assert playlist.get_length() == project.length
    # MLT out включительный, модель — полуоткрытая
    assert _layout(builder, project) == [
        (0, 5, 19, clip.name),
        (15, 20, n - 1, clip.name),
    ]


def test_out_clamped_to_shorter_file(builder: Builder, clip: Path) -> None:
    # Модель думает, что исходник длиннее (как оригинал против прокси) — не выходим за конец
    n = builder.source_length(str(clip))
    project = add_clip(Project(), Clip(str(clip), n + 10, 0, n + 10))
    assert builder.build(project).get_length() == n


def test_producers_are_cached(builder: Builder, clip: Path) -> None:
    assert builder.producer(str(clip)) is builder.producer(str(clip))


def test_resolve_and_forget(clip: Path, tmp_path: Path) -> None:
    proxy = tmp_path / "proxy.mp4"
    shutil.copy(clip, proxy)
    proxies: dict[str, str] = {}
    builder = Builder(make_profile(540, 960), resolve=lambda s: proxies.get(s, s))
    n = builder.source_length(str(clip))
    project = add_clip(Project(), Clip(str(clip), n, 0, n))

    assert _layout(builder, project)[0][3] == clip.name
    proxies[str(clip)] = str(proxy)
    builder.forget(str(clip))
    assert _layout(builder, project)[0][3] == proxy.name


def test_missing_file(builder: Builder, tmp_path: Path) -> None:
    with pytest.raises(OSError):
        builder.producer(str(tmp_path / "nope.mp4"))
