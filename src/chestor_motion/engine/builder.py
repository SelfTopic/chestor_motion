"""Сборка графа MLT из модели проекта. Граф — одноразовый: после правки собирается заново.

Дорогое в сборке — открыть файл (разбор контейнера, кодеки), поэтому источники кэшируются
по пути, а пересобирается только раскладка клипов.
"""

from collections.abc import Callable

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


class Builder:
    def __init__(self, profile: mlt.Profile, resolve: Callable[[str], str] = str) -> None:
        """resolve: путь к оригиналу → путь, который реально открыть (прокси для превью)."""
        self._profile = profile
        self._resolve = resolve
        self._cache: dict[str, mlt.Producer] = {}

    def producer(self, source: str) -> mlt.Producer:
        path = self._resolve(source)
        producer = self._cache.get(path)
        if producer is None:
            producer = mlt.Producer(self._profile, path)
            if not producer.is_valid():
                raise OSError(f"MLT не открывает {path}")
            self._cache[path] = producer
        return producer

    def source_length(self, source: str) -> int:
        """Длина исходника в кадрах проекта."""
        return self.producer(source).get_length()

    def forget(self, source: str) -> None:
        """Забыть источник — например, когда для него готов прокси и путь поменялся."""
        self._cache.pop(self._resolve(source), None)
        self._cache.pop(source, None)

    def build(self, project: Project) -> mlt.Playlist:
        playlist = mlt.Playlist(self._profile)
        for clip in project.main:
            producer = self.producer(clip.source)
            # У прокси и оригинала длина может отличаться на пару кадров (переменная
            # частота кадров оригинала) — не выходим за конец того, что открыто
            last = min(clip.out_frame, producer.get_length()) - 1
            # В MLT out включительный, в модели — нет
            playlist.append(producer, clip.in_frame, max(clip.in_frame, last))
        return playlist
