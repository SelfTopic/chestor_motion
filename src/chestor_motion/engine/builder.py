"""Сборка графа MLT из модели проекта. Граф — одноразовый: после правки собирается заново.

Дорогое в сборке — открыть файл (разбор контейнера, кодеки), поэтому источники кэшируются
по пути, а пересобирается только раскладка клипов.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import mlt7 as mlt

from chestor_motion.engine import mltlib
from chestor_motion.project.model import (
    FPS,
    AudioClip,
    Clip,
    FreeClip,
    OverlayClip,
    Project,
    frame_rect,
)


def make_profile(width: int, height: int, fps: int = FPS) -> mlt.Profile:
    mltlib.init()
    profile = mlt.Profile()
    profile.set_width(width - width % 2)
    profile.set_height(height - height % 2)
    profile.set_sample_aspect(1, 1)
    profile.set_display_aspect(profile.width(), profile.height())
    profile.set_frame_rate(fps, 1)
    profile.set_progressive(1)
    profile.set_colorspace(709)  # HD; по умолчанию MLT пишет 601 (старое ТВ) — цвета съезжают
    profile.set_explicit(1)
    return profile


AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma"}


@dataclass(frozen=True)
class SourceInfo:
    width: int
    height: int
    length: int  # в кадрах проекта
    has_video: bool  # False — звуковой файл (обложка mp3 видео не считается)


def probe(path: str) -> SourceInfo:
    """Размер и длина исходника. Длина — в кадрах проекта, а не в родных кадрах файла."""
    profile = make_profile(2, 2)  # живёт дольше источника: тот ссылается на профиль
    producer = mlt.Producer(profile, path)
    if not producer.is_valid():
        raise OSError(f"MLT не открывает {path}")
    has_video = (
        producer.get_int("video_index") >= 0 and Path(path).suffix.lower() not in AUDIO_SUFFIXES
    )
    return SourceInfo(
        producer.get_int("width"), producer.get_int("height"), producer.get_length(), has_video
    )


# Вид источника: обычный, без звука (видеоклип с отделённым звуком), только звук (звуковой
# клип — видео у него не декодируется). Один файл бывает нужен в нескольких видах сразу.
AV, VIDEO_ONLY, AUDIO_ONLY = "av", "video", "audio"


class Builder:
    def __init__(
        self, profile: mlt.Profile, resolve: Callable[[str], str] = str, scale: int = 1
    ) -> None:
        """resolve: путь к оригиналу → путь, который реально открыть (прокси для превью).
        Звуковые клипы открываются из оригинала: прокси им не нужен (у mp3 его и нет).
        scale: во сколько раз частота профиля выше FPS модели (экспорт в 60 fps — 2): все
        позиции модели умножаются на него."""
        self._profile = profile
        self._resolve = resolve
        self._k = scale
        self._cache: dict[tuple[str, str], mlt.Producer] = {}

    def producer(self, source: str, kind: str = AV) -> mlt.Producer:
        path = source if kind == AUDIO_ONLY else self._resolve(source)
        producer = self._cache.get((path, kind))
        if producer is None:
            producer = mlt.Producer(self._profile, path)
            if not producer.is_valid():
                raise OSError(f"MLT не открывает {path}")
            if kind == VIDEO_ONLY:
                producer.set("audio_index", -1)
            elif kind == AUDIO_ONLY:
                producer.set("video_index", -1)
            self._cache[(path, kind)] = producer
        return producer

    def source_length(self, source: str) -> int:
        """Длина исходника в кадрах проекта."""
        return self.producer(source).get_length()

    def forget(self, source: str) -> None:
        """Забыть источник — например, когда для него готов прокси и путь поменялся."""
        paths = {source, self._resolve(source)}
        for key in [k for k in self._cache if k[0] in paths]:
            del self._cache[key]

    def rect(self, clip: Clip | OverlayClip, x: float, y: float, scale: float) -> str:
        """Прямоугольник для qtblend в пикселях профиля. Только целые: дробное вроде «-0.00»
        qtblend не разбирает и молча не рисует кадр."""
        producer = self.producer(clip.source, AV if clip.audio else VIDEO_ONLY)
        source = (producer.get_int("width") or 1, producer.get_int("height") or 1)
        canvas = (self._profile.width(), self._profile.height())
        left, top, w, h = frame_rect(canvas, source, x, y, scale)
        return f"{round(left)} {round(top)} {round(w)} {round(h)} 1"

    def build(self, project: Project, live: str = "") -> mlt.Tractor:
        """Дорожка 0 — основная, над ней наложения (qtblend кладёт каждую поверх всего, что
        ниже), дальше звуковые. Переходы mix складывают звук всех дорожек.

        live: id клипа, который сейчас двигают на превью, — ему фильтр положения нужен, даже
        если клип пока на месте, чтобы менять прямоугольник на лету (`tractor.transforms`)."""
        tractor = mlt.Tractor(self._profile)
        self._keep: list[object] = []
        self._transforms: dict[str, mlt.Filter] = {}
        self._live = live

        main = mlt.Playlist(self._profile)
        for clip in project.main:
            self._append(main, clip, AV if clip.audio else VIDEO_ONLY)
        tractor.set_track(main, 0)
        self._keep.append(main)

        index = 1
        for lane in project.overlays:
            playlist = self._lane(
                lane, lambda c: AV if isinstance(c, OverlayClip) and c.audio else VIDEO_ONLY
            )
            tractor.set_track(playlist, index)
            blend = mlt.Transition(self._profile, "qtblend")
            blend.set("always_active", 1)
            tractor.plant_transition(blend, 0, index)
            self._keep.append(blend)
            self._mix(tractor, index)
            index += 1
        for lane in project.audio:
            playlist = self._lane(lane, lambda _c: AUDIO_ONLY)
            playlist.set("hide", 1)  # у звуковой дорожки нет картинки
            tractor.set_track(playlist, index)
            self._mix(tractor, index)
            index += 1

        # Дорожки и переходы живут, пока жив трактор: иначе Python освободит их раньше, чем
        # консьюмер перестанет их читать
        tractor.keep_alive = self._keep  # type: ignore[attr-defined]
        tractor.transforms = self._transforms  # type: ignore[attr-defined]
        return tractor

    def _append(self, playlist: mlt.Playlist, clip: Clip | FreeClip, kind: str) -> None:
        producer = self.producer(clip.source, kind)
        k = self._k
        # У прокси и оригинала длина может отличаться на пару кадров (переменная
        # частота кадров оригинала) — не выходим за конец того, что открыто
        last = min(clip.out_frame * k, producer.get_length()) - 1
        # В MLT out включительный, в модели — нет
        playlist.append(producer, clip.in_frame * k, max(clip.in_frame * k, last))
        if isinstance(clip, AudioClip):
            return
        # Вписанный по центру клип MLT ставит сам; qtblend на нём стоил бы 10–20% скорости
        if clip.transformed or clip.id == self._live:
            transform = mlt.Filter(self._profile, "qtblend")
            transform.set("rect", self.rect(clip, clip.x, clip.y, clip.scale))
            cut = playlist.get_clip(playlist.count() - 1)
            cut.attach(transform)
            self._transforms[clip.id] = transform
            self._keep += [cut, transform]

    def _lane(self, lane: tuple[FreeClip, ...], kind: Callable[[FreeClip], str]) -> mlt.Playlist:
        """Свободная дорожка: клипы на своих местах, между ними пустоты."""
        playlist = mlt.Playlist(self._profile)
        k = self._k
        position = 0
        for clip in lane:
            if clip.start * k > position:
                playlist.blank(clip.start * k - position - 1)  # blank(out): длина out + 1
            self._append(playlist, clip, kind(clip))
            position = clip.end * k
        self._keep.append(playlist)
        return playlist

    def _mix(self, tractor: mlt.Tractor, index: int) -> None:
        mix = mlt.Transition(self._profile, "mix")
        mix.set("always_active", 1)
        mix.set("sum", 1)
        tractor.plant_transition(mix, 0, index)
        self._keep.append(mix)
