"""Сборка графа MLT из модели проекта. Граф — одноразовый: после правки собирается заново.

Дорогое в сборке — открыть файл (разбор контейнера, кодеки), поэтому источники кэшируются
по пути, а пересобирается только раскладка клипов.
"""

from collections.abc import Callable
from dataclasses import dataclass

import mlt7 as mlt

from chestor_motion.engine import mltlib
from chestor_motion.project.model import FPS, Project


def make_profile(width: int, height: int) -> mlt.Profile:
    mltlib.init()
    profile = mlt.Profile()
    profile.set_width(width - width % 2)
    profile.set_height(height - height % 2)
    profile.set_sample_aspect(1, 1)
    profile.set_display_aspect(profile.width(), profile.height())
    profile.set_frame_rate(FPS, 1)
    profile.set_progressive(1)
    profile.set_explicit(1)
    return profile


@dataclass(frozen=True)
class SourceInfo:
    width: int
    height: int
    length: int  # в кадрах проекта


def probe(path: str) -> SourceInfo:
    """Размер и длина исходника. Длина — в кадрах проекта, а не в родных кадрах файла."""
    profile = make_profile(2, 2)  # живёт дольше источника: тот ссылается на профиль
    producer = mlt.Producer(profile, path)
    if not producer.is_valid():
        raise OSError(f"MLT не открывает {path}")
    return SourceInfo(producer.get_int("width"), producer.get_int("height"), producer.get_length())


# Вид источника: обычный, без звука (видеоклип с отделённым звуком), только звук (звуковой
# клип — видео у него не декодируется). Один файл бывает нужен в нескольких видах сразу.
AV, VIDEO_ONLY, AUDIO_ONLY = "av", "video", "audio"


class Builder:
    def __init__(self, profile: mlt.Profile, resolve: Callable[[str], str] = str) -> None:
        """resolve: путь к оригиналу → путь, который реально открыть (прокси для превью).
        Звуковые клипы открываются из оригинала: прокси им не нужен (у mp3 его и нет)."""
        self._profile = profile
        self._resolve = resolve
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

    def build(self, project: Project) -> mlt.Tractor:
        """Дорожка 0 — основная, дальше звуковые; переходы mix складывают звук всех дорожек."""
        tractor = mlt.Tractor(self._profile)
        main = mlt.Playlist(self._profile)
        for clip in project.main:
            producer = self.producer(clip.source, AV if clip.audio else VIDEO_ONLY)
            # У прокси и оригинала длина может отличаться на пару кадров (переменная
            # частота кадров оригинала) — не выходим за конец того, что открыто
            last = min(clip.out_frame, producer.get_length()) - 1
            # В MLT out включительный, в модели — нет
            main.append(producer, clip.in_frame, max(clip.in_frame, last))
        tractor.set_track(main, 0)
        keep: list[object] = [main]

        for index, lane in enumerate(project.audio, start=1):
            playlist = mlt.Playlist(self._profile)
            position = 0
            for clip in lane:
                if clip.start > position:
                    playlist.blank(clip.start - position - 1)  # blank(out): длина out + 1
                producer = self.producer(clip.source, AUDIO_ONLY)
                last = min(clip.out_frame, producer.get_length()) - 1
                playlist.append(producer, clip.in_frame, max(clip.in_frame, last))
                position = clip.end
            playlist.set("hide", 1)  # у звуковой дорожки нет картинки — видна основная
            tractor.set_track(playlist, index)
            mix = mlt.Transition(self._profile, "mix")
            mix.set("always_active", 1)
            mix.set("sum", 1)
            tractor.plant_transition(mix, 0, index)
            keep += [playlist, mix]

        # Дорожки и переходы живут, пока жив трактор: иначе Python освободит их раньше, чем
        # консьюмер перестанет их читать
        tractor.keep_alive = keep  # type: ignore[attr-defined]
        return tractor
