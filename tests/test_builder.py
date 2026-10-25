import shutil
from pathlib import Path

import mlt7 as mlt
import pytest

from chestor_motion.engine.builder import Builder, make_profile
from chestor_motion.project.model import (
    Clip,
    Project,
    add_clip,
    fill_scale,
    set_transform,
    split,
    trim_start,
)


@pytest.fixture
def builder() -> Builder:
    return Builder(make_profile(540, 960))


def _layout(builder: Builder, project: Project) -> list[tuple[int, int, int, str]]:
    """(начало на таймлайне, первый кадр, последний кадр, файл) каждого клипа дорожки."""
    return _track(builder.build(project), 0)


def _track(tractor: mlt.Tractor, index: int) -> list[tuple[int, int, int, str]]:
    playlist = mlt.Playlist(tractor.track(index))
    out = []
    for i in range(playlist.count()):
        info = playlist.clip_info(i)
        if playlist.is_blank(i):
            out.append((info.start, -1, -1, "blank"))
            continue
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


def _render_rms(tractor: mlt.Tractor, profile: mlt.Profile, out: Path) -> list[float]:
    """Отрендерить звук графа в WAV и вернуть громкость (RMS 0..1) по 0.25 с."""
    import array
    import time
    import wave

    consumer = mlt.Consumer(profile, "avformat", str(out))
    for key, value in (("vn", 1), ("acodec", "pcm_s16le"), ("ar", 48000), ("ac", 1),
                       ("real_time", -1), ("terminate_on_pause", 1)):  # fmt: skip
        consumer.set(key, value)
    consumer.connect(tractor)
    consumer.start()
    deadline = time.time() + 20
    while not consumer.is_stopped() and time.time() < deadline:
        time.sleep(0.05)
    consumer.stop()
    with wave.open(str(out)) as w:
        samples = array.array("h", w.readframes(w.getnframes()))
    step = 12000
    return [
        (sum(x * x for x in samples[i : i + step]) / step) ** 0.5 / 32768
        for i in range(0, len(samples) - step + 1, step)
    ]


def test_detached_and_trimmed_sound_is_heard_only_where_it_is(clip: Path, tmp_path: Path) -> None:
    from chestor_motion.project.model import detach_audio, trim_free_end

    profile = make_profile(320, 180)
    builder = Builder(profile)
    n = builder.source_length(str(clip))
    project = add_clip(Project(), Clip(str(clip), n, 0, n, id="v"))
    project = detach_audio(project, "v")
    sound = project.audio[0][0]
    project = trim_free_end(project, sound.id, 30)  # звук только первую секунду

    rms = _render_rms(builder.build(project), profile, tmp_path / "a.wav")
    assert len(rms) >= 7
    assert min(rms[:3]) > 0.05  # первая секунда — тон
    assert max(rms[5:]) < 0.005  # вторая — тишина: видео без звука, звуковой клип кончился


def test_audio_tracks_mix_with_main(clip: Path, tmp_path: Path) -> None:
    from chestor_motion.project.model import AudioClip, add_audio

    profile = make_profile(320, 180)
    builder = Builder(profile)
    n = builder.source_length(str(clip))
    project = add_clip(Project(), Clip(str(clip), n, 0, n))  # свой звук включён
    project = add_audio(project, AudioClip(str(clip), n, 0, 30, start=0))
    both = _render_rms(builder.build(project), profile, tmp_path / "b.wav")
    alone = _render_rms(builder.build(add_clip(Project(), Clip(str(clip), n, 0, n))), profile,
                        tmp_path / "c.wav")  # fmt: skip
    # Где играют оба — громче, чем один основной (складываются, а не заменяют)
    assert both[1] > alone[1] * 1.5
    assert abs(both[6] - alone[6]) < 0.01


def _alpha(tractor: mlt.Tractor, w: int, h: int, x: int, y: int) -> int:
    tractor.seek(5)
    image = bytes(tractor.get_frame().get_image(mlt.mlt_image_rgba, w, h))
    return image[(y * w + x) * 4 + 3]


def test_transform_places_clip_on_canvas(clip: Path) -> None:
    """Клип 642×360 на холсте 9:16: вписан — сверху пусто; заполнить — закрыт весь холст;
    маленький в левом верхнем углу — пусто справа внизу."""
    profile = make_profile(180, 320)
    b = Builder(profile)
    p = add_clip(Project(1080, 1920), Clip(str(clip), 60, 0, 60, id="v"))
    fitted = b.build(p)
    assert not fitted.transforms  # type: ignore[attr-defined]  # вписанному фильтр не нужен
    assert _alpha(fitted, 180, 320, 90, 10) == 0 and _alpha(fitted, 180, 320, 90, 160) == 255

    fill = fill_scale((1080, 1920), (642, 360))
    filled = b.build(set_transform(p, "v", 0, 0, fill))
    assert _alpha(filled, 180, 320, 2, 2) == 255 and _alpha(filled, 180, 320, 177, 317) == 255

    corner = b.build(set_transform(p, "v", -0.25, -0.4, 0.5))
    assert _alpha(corner, 180, 320, 40, 30) == 255 and _alpha(corner, 180, 320, 150, 300) == 0


def test_live_clip_gets_a_filter_to_move(clip: Path) -> None:
    b = Builder(make_profile(180, 320))
    p = add_clip(Project(1080, 1920), Clip(str(clip), 60, 0, 60, id="v"))
    assert set(b.build(p, live="v").transforms) == {"v"}  # type: ignore[attr-defined]


def _rgb(tractor: mlt.Tractor, frame: int, w: int, h: int, x: int, y: int) -> tuple[int, ...]:
    tractor.seek(frame)
    image = bytes(tractor.get_frame().get_image(mlt.mlt_image_rgba, w, h))
    return tuple(image[(y * w + x) * 4 : (y * w + x) * 4 + 3])


def _is_red(rgb: tuple[int, ...]) -> bool:
    return rgb[0] > 200 and rgb[1] < 60 and rgb[2] < 60


def test_overlay_on_top_only_where_and_when_it_is(clip: Path, red: Path, tmp_path: Path) -> None:
    from chestor_motion.project.model import OverlayClip, add_overlay

    profile = make_profile(320, 180)
    b = Builder(profile)
    n = b.source_length(str(clip))
    p = add_clip(Project(640, 360), Clip(str(clip), n, 0, n, id="v"))
    # Красный квадрат на 0.5 с с 10-го кадра, в правом верхнем углу, в 4 раза меньше
    p = add_overlay(p, OverlayClip(str(red), 30, 0, 15, start=10, x=0.3, y=-0.3, scale=0.25))
    tractor = b.build(p)
    assert _is_red(_rgb(tractor, 15, 320, 180, 256, 36))  # в углу — наложение
    assert not _is_red(_rgb(tractor, 15, 320, 180, 60, 120))  # рядом — основное видео
    assert not _is_red(_rgb(tractor, 40, 320, 180, 256, 36))  # после конца — снова основное

    rms = _render_rms(b.build(p), profile, tmp_path / "o.wav")  # свежий граф: тот перемотан
    alone = _render_rms(b.build(add_clip(Project(640, 360), Clip(str(clip), n, 0, n))), profile,
                        tmp_path / "m.wav")  # fmt: skip
    assert rms[1] > alone[1] * 1.2  # 0.25–0.5 с: звук наложения добавился к основному
    assert abs(rms[5] - alone[5]) < 0.01  # после конца наложения — только основной
