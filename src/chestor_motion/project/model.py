"""Модель проекта — правда о монтаже. MLT только исполняет её (см. engine/builder.py).

Модель неизменяемая: каждая правка возвращает новый Project, старый остаётся как был —
поэтому отмена действий это просто стопка снимков (project/history.py).

Время — целые кадры проекта (FPS). Интервалы полуоткрытые: [in_frame, out_frame).

Дорожки: основная — видео «на магните» (клипы встык). Остальные — «свободные» клипы в любом
месте таймлайна, с пустотами: дорожки наложений (видео поверх основной) и звуковые. Свободные
клипы раскладываются по дорожкам так, чтобы в одной не было пересечений: не влез в свою —
встаёт в следующую, нет свободной — появляется новая.
"""

import uuid
from dataclasses import dataclass, field, replace
from typing import Literal

FPS = 30

# Холсты, как в CapCut: размер в пикселях задаёт только форму — итоговое разрешение выбирается
# при экспорте по короткой стороне. «Оригинал» — размер первого видео, его считает сессия.
CANVASES = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080)}
MIN_SCALE, MAX_SCALE = 0.05, 20.0


def frame_rect(
    canvas: tuple[float, float], source: tuple[float, float], x: float, y: float, scale: float
) -> tuple[float, float, float, float]:
    """Где клип на холсте: (левый край, верхний, ширина, высота) в единицах холста."""
    cw, ch = canvas
    sw, sh = source
    k = min(cw / sw, ch / sh) * scale
    w, h = sw * k, sh * k
    return cw / 2 + x * cw - w / 2, ch / 2 + y * ch - h / 2, w, h


def fill_scale(canvas: tuple[float, float], source: tuple[float, float]) -> float:
    """Масштаб «заполнить холст»: клип закрывает его целиком, лишнее обрезается."""
    cw, ch = canvas
    sw, sh = source
    return max(cw / sw, ch / sh) / min(cw / sw, ch / sh)


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass(frozen=True)
class Clip:
    source: str  # абсолютный путь к оригиналу; прокси подставляет сборщик
    source_length: int  # длина исходника в кадрах проекта — граница для подрезки
    in_frame: int  # первый используемый кадр исходника
    out_frame: int  # кадр исходника сразу после последнего используемого
    id: str = field(default_factory=new_id)
    audio: bool = True  # играет свой звук; после «отделить звук» — нет
    # Положение на холсте: сдвиг центра клипа от центра холста в долях его ширины и высоты,
    # масштаб относительно «вписан целиком» (1.0). Так клип остаётся на месте при смене
    # разрешения экспорта.
    x: float = 0.0
    y: float = 0.0
    scale: float = 1.0

    def __post_init__(self) -> None:
        _check_range(self.id, self.in_frame, self.out_frame, self.source_length)
        if not MIN_SCALE <= self.scale <= MAX_SCALE:
            raise ValueError(f"клип {self.id}: масштаб {self.scale} вне {MIN_SCALE}…{MAX_SCALE}")

    @property
    def transformed(self) -> bool:
        return (self.x, self.y, self.scale) != (0.0, 0.0, 1.0)

    @property
    def length(self) -> int:
        return self.out_frame - self.in_frame


@dataclass(frozen=True)
class AudioClip:
    source: str
    source_length: int
    in_frame: int
    out_frame: int
    start: int  # кадр таймлайна, где начинается клип
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        _check_range(self.id, self.in_frame, self.out_frame, self.source_length)
        if self.start < 0:
            raise ValueError(f"звуковой клип {self.id}: start {self.start} < 0")

    @property
    def length(self) -> int:
        return self.out_frame - self.in_frame

    @property
    def end(self) -> int:
        return self.start + self.length


@dataclass(frozen=True)
class OverlayClip:
    """Видео поверх основной дорожки: место на таймлайне как у звука, на холсте — как у клипа."""

    source: str
    source_length: int
    in_frame: int
    out_frame: int
    start: int
    id: str = field(default_factory=new_id)
    audio: bool = True
    x: float = 0.0
    y: float = 0.0
    scale: float = 1.0

    def __post_init__(self) -> None:
        _check_range(self.id, self.in_frame, self.out_frame, self.source_length)
        if self.start < 0:
            raise ValueError(f"клип наложения {self.id}: start {self.start} < 0")
        if not MIN_SCALE <= self.scale <= MAX_SCALE:
            raise ValueError(f"клип {self.id}: масштаб {self.scale} вне {MIN_SCALE}…{MAX_SCALE}")

    @property
    def transformed(self) -> bool:
        return (self.x, self.y, self.scale) != (0.0, 0.0, 1.0)

    @property
    def length(self) -> int:
        return self.out_frame - self.in_frame

    @property
    def end(self) -> int:
        return self.start + self.length


def _check_range(clip_id: str, in_frame: int, out_frame: int, source_length: int) -> None:
    if not 0 <= in_frame < out_frame <= source_length:
        raise ValueError(
            f"клип {clip_id}: нужно 0 <= in < out <= length, "
            f"а дано {in_frame}, {out_frame}, {source_length}"
        )


Lane = tuple[AudioClip, ...]
OverlayLane = tuple[OverlayClip, ...]
FreeClip = AudioClip | OverlayClip
# Группы свободных дорожок — имена полей Project
Group = Literal["audio", "overlays"]


@dataclass(frozen=True)
class Project:
    width: int = 1080
    height: int = 1920
    # Основная дорожка «на магните», как в CapCut: клипы идут встык, дыр не бывает,
    # поэтому позиция клипа — сумма длин предыдущих
    main: tuple[Clip, ...] = ()
    # Звуковые дорожки сверху вниз; в каждой клипы по порядку start и не пересекаются
    audio: tuple[Lane, ...] = ()
    # Дорожки наложений: 0 — сразу над основной, чем выше номер, тем выше на картинке
    overlays: tuple[OverlayLane, ...] = ()

    @property
    def main_length(self) -> int:
        return sum(c.length for c in self.main)

    @property
    def length(self) -> int:
        """Длина проекта: до конца основной дорожки или последнего свободного клипа."""
        ends = [c.end for lanes in (self.audio, self.overlays) for lane in lanes for c in lane]
        return max([self.main_length, *ends])

    def free_clip(self, clip_id: str) -> tuple[Group, int, FreeClip] | None:
        """(группа, номер дорожки, клип) или None, если клип на основной дорожке или его нет."""
        for group in ("audio", "overlays"):
            for lane_index, lane in enumerate(getattr(self, group)):
                for clip in lane:
                    if clip.id == clip_id:
                        return group, lane_index, clip
        return None

    def audio_clip(self, clip_id: str) -> tuple[int, AudioClip] | None:
        """(номер дорожки, клип) или None, если это не звуковой клип."""
        found = self.free_clip(clip_id)
        if found is None or found[0] != "audio":
            return None
        return found[1], found[2]  # type: ignore[return-value]

    def overlay_clip(self, clip_id: str) -> tuple[int, OverlayClip] | None:
        found = self.free_clip(clip_id)
        if found is None or found[0] != "overlays":
            return None
        return found[1], found[2]  # type: ignore[return-value]

    def visible_at(self, frame: int) -> list[Clip | OverlayClip]:
        """Видеоклипы в кадре сверху вниз: наложения с верхней дорожки, последним — основная."""
        clips: list[Clip | OverlayClip] = [
            c for lane in reversed(self.overlays) for c in lane if c.start <= frame < c.end
        ]
        hit = self.clip_at(frame)
        if hit is not None:
            clips.append(self.main[hit[0]])
        return clips

    def audio_at(self, frame: int, lane: int) -> AudioClip | None:
        if 0 <= lane < len(self.audio):
            for clip in self.audio[lane]:
                if clip.start <= frame < clip.end:
                    return clip
        return None

    def clip_start(self, index: int) -> int:
        return sum(c.length for c in self.main[:index])

    def index_of(self, clip_id: str) -> int:
        for i, clip in enumerate(self.main):
            if clip.id == clip_id:
                return i
        raise KeyError(clip_id)

    def clip_at(self, frame: int) -> tuple[int, int] | None:
        """(индекс клипа, его начало) под кадром таймлайна или None за пределами."""
        start = 0
        for i, clip in enumerate(self.main):
            if start <= frame < start + clip.length:
                return i, start
            start += clip.length
        return None


# --- правки: каждая возвращает новый проект ---


def set_canvas(project: Project, width: int, height: int) -> Project:
    """Сменить холст. Клипы MLT вписывает в него сам, по центру; пустое по краям — чёрное."""
    if width < 2 or height < 2:
        raise ValueError(f"холст {width}×{height} слишком мал")
    return replace(project, width=width - width % 2, height=height - height % 2)


def add_clip(project: Project, clip: Clip, index: int | None = None) -> Project:
    clips = list(project.main)
    clips.insert(len(clips) if index is None else index, clip)
    return replace(project, main=tuple(clips))


def split(project: Project, frame: int) -> Project:
    """Разрезать клип под кадром таймлайна. На границе клипов или за краем — без изменений."""
    hit = project.clip_at(frame)
    if hit is None:
        return project
    index, start = hit
    offset = frame - start
    if offset == 0:
        return project
    clip = project.main[index]
    cut = clip.in_frame + offset
    left = replace(clip, out_frame=cut)
    right = replace(clip, in_frame=cut, id=new_id())
    return replace(project, main=project.main[:index] + (left, right) + project.main[index + 1 :])


def delete(project: Project, clip_id: str) -> Project:
    """Удалить клип любой дорожки."""
    found = project.free_clip(clip_id)
    if found is not None:
        group = found[0]
        return replace(project, **{group: _without(getattr(project, group), clip_id)})
    index = project.index_of(clip_id)
    return replace(project, main=project.main[:index] + project.main[index + 1 :])


def move(project: Project, clip_id: str, to_index: int) -> Project:
    clips = list(project.main)
    clip = clips.pop(project.index_of(clip_id))
    clips.insert(max(0, min(to_index, len(clips))), clip)
    return replace(project, main=tuple(clips))


def trim_start(project: Project, clip_id: str, in_frame: int) -> Project:
    """Подрезать начало клипа; на магнитной дорожке всё, что правее, сдвигается."""
    index = project.index_of(clip_id)
    clip = project.main[index]
    in_frame = max(0, min(in_frame, clip.out_frame - 1))
    return _replace_clip(project, index, replace(clip, in_frame=in_frame))


def trim_end(project: Project, clip_id: str, out_frame: int) -> Project:
    index = project.index_of(clip_id)
    clip = project.main[index]
    out_frame = max(clip.in_frame + 1, min(out_frame, clip.source_length))
    return _replace_clip(project, index, replace(clip, out_frame=out_frame))


def set_transform(project: Project, clip_id: str, x: float, y: float, scale: float) -> Project:
    """Положение видеоклипа (основной дорожки или наложения) на холсте; масштаб зажимается в
    допустимые пределы."""
    scale = min(max(scale, MIN_SCALE), MAX_SCALE)
    found = project.overlay_clip(clip_id)
    if found is not None:
        lane, clip = found
        return _replace_free(project, "overlays", lane, replace(clip, x=x, y=y, scale=scale))
    index = project.index_of(clip_id)
    return _replace_clip(project, index, replace(project.main[index], x=x, y=y, scale=scale))


def _replace_clip(project: Project, index: int, clip: Clip) -> Project:
    return replace(project, main=project.main[:index] + (clip,) + project.main[index + 1 :])


# --- свободные дорожки: звук и наложения ---


def _without[C: FreeClip](
    lanes: tuple[tuple[C, ...], ...], clip_id: str, compact: bool = True
) -> tuple[tuple[C, ...], ...]:
    """Дорожки без клипа; опустевшие дорожки убираются (compact)."""
    out = tuple(tuple(c for c in lane if c.id != clip_id) for lane in lanes)
    return tuple(lane for lane in out if lane) if compact else out


def _fits(lane: tuple[FreeClip, ...], clip: FreeClip) -> bool:
    return all(clip.end <= c.start or clip.start >= c.end for c in lane)


def _place[C: FreeClip](
    lanes: tuple[tuple[C, ...], ...], clip: C, preferred: int = 0
) -> tuple[tuple[C, ...], ...]:
    """Поставить клип в первую дорожку от preferred, где он ни с чем не пересекается."""
    order = list(range(preferred, len(lanes))) + list(range(0, min(preferred, len(lanes))))
    for i in order:
        if _fits(lanes[i], clip):
            lane = tuple(sorted((*lanes[i], clip), key=lambda c: c.start))
            return lanes[:i] + (lane,) + lanes[i + 1 :]
    return (*lanes, (clip,))


def add_audio(project: Project, clip: AudioClip, lane: int = 0) -> Project:
    return replace(project, audio=_place(project.audio, clip, lane))


def add_overlay(project: Project, clip: OverlayClip, lane: int = 0) -> Project:
    return replace(project, overlays=_place(project.overlays, clip, lane))


def detach_audio(project: Project, clip_id: str) -> Project:
    """«Отделить звук»: видеоклип (основной или наложения) замолкает, его звук — отдельный клип
    на том же месте."""
    overlay = project.overlay_clip(clip_id)
    if overlay is not None:
        lane, clip = overlay
        start = clip.start
        if not clip.audio:
            return project
        project = _replace_free(project, "overlays", lane, replace(clip, audio=False))
    else:
        index = project.index_of(clip_id)
        clip = project.main[index]
        start = project.clip_start(index)
        if not clip.audio:
            return project
        project = _replace_clip(project, index, replace(clip, audio=False))
    sound = AudioClip(
        source=clip.source,
        source_length=clip.source_length,
        in_frame=clip.in_frame,
        out_frame=clip.out_frame,
        start=start,
    )
    return add_audio(project, sound)


def move_free(project: Project, clip_id: str, start: int, lane: int | None = None) -> Project:
    """Передвинуть свободный клип в пределах его группы дорожек; занято — встанет в другую."""
    found = project.free_clip(clip_id)
    if found is None:
        return project
    group, current_lane, clip = found
    # Пустую дорожку убираем только после перестановки: иначе клип, один в своей дорожке,
    # при сдвиге вбок перепрыгивал бы в соседнюю
    lanes = _without(getattr(project, group), clip_id, compact=False)
    moved = replace(clip, start=max(0, start))
    if lane is not None and lane >= len(lanes):
        placed = (*lanes, (moved,))  # утащили за последнюю дорожку — новая дорожка
    else:
        preferred = max(0, current_lane if lane is None else lane)
        placed = _place(lanes, moved, preferred)
    return replace(project, **{group: tuple(lane for lane in placed if lane)})


def _neighbours(project: Project, clip_id: str) -> tuple[int, int | None]:
    """Конец соседа слева и начало соседа справа в той же дорожке (None — справа никого)."""
    found = project.free_clip(clip_id)
    assert found is not None
    group, lane_index, clip = found
    lane = getattr(project, group)[lane_index]
    left = max((c.end for c in lane if c.end <= clip.start and c.id != clip_id), default=0)
    right = min((c.start for c in lane if c.start >= clip.end and c.id != clip_id), default=None)
    return left, right


def trim_free_start(project: Project, clip_id: str, in_frame: int) -> Project:
    """Подрезать начало: левый край клипа на таймлайне двигается вместе с in."""
    found = project.free_clip(clip_id)
    if found is None:
        return project
    group, lane_index, clip = found
    left, _ = _neighbours(project, clip_id)
    lowest = max(0, clip.in_frame - (clip.start - left))  # не залезть на соседа и в минус
    in_frame = max(lowest, min(in_frame, clip.out_frame - 1))
    moved = replace(clip, in_frame=in_frame, start=clip.start + in_frame - clip.in_frame)
    return _replace_free(project, group, lane_index, moved)


def trim_free_end(project: Project, clip_id: str, out_frame: int) -> Project:
    found = project.free_clip(clip_id)
    if found is None:
        return project
    group, lane_index, clip = found
    _, right = _neighbours(project, clip_id)
    highest = (
        clip.source_length
        if right is None
        else min(clip.source_length, clip.out_frame + right - clip.end)
    )
    out_frame = max(clip.in_frame + 1, min(out_frame, highest))
    return _replace_free(project, group, lane_index, replace(clip, out_frame=out_frame))


def split_free(project: Project, clip_id: str, frame: int) -> Project:
    """Разрезать свободный клип в кадре таймлайна; не внутри клипа — без изменений."""
    found = project.free_clip(clip_id)
    if found is None:
        return project
    group, lane_index, clip = found
    if not clip.start < frame < clip.end:
        return project
    cut = clip.in_frame + frame - clip.start
    left = replace(clip, out_frame=cut)
    right = replace(clip, in_frame=cut, start=frame, id=new_id())
    lanes = getattr(project, group)
    lane = tuple(
        sorted((*(c for c in lanes[lane_index] if c.id != clip_id), left, right),
               key=lambda c: c.start)
    )  # fmt: skip
    return replace(project, **{group: lanes[:lane_index] + (lane,) + lanes[lane_index + 1 :]})


def _replace_free(project: Project, group: Group, lane_index: int, clip: FreeClip) -> Project:
    lanes = getattr(project, group)
    lane = tuple(clip if c.id == clip.id else c for c in lanes[lane_index])
    return replace(project, **{group: lanes[:lane_index] + (lane,) + lanes[lane_index + 1 :]})
