"""Модель проекта — правда о монтаже. MLT только исполняет её (см. engine/builder.py).

Модель неизменяемая: каждая правка возвращает новый Project, старый остаётся как был —
поэтому отмена действий это просто стопка снимков (project/history.py).

Время — целые кадры проекта (FPS). Интервалы полуоткрытые: [in_frame, out_frame).

Дорожки: основная — видео «на магните» (клипы встык); звуковые — клипы в любом месте
таймлайна, с пустотами. Звуковые клипы раскладываются по дорожкам так, чтобы в одной не было
пересечений: не влез в свою — встаёт в следующую, нет свободной — появляется новая.
"""

import uuid
from dataclasses import dataclass, field, replace

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


def _check_range(clip_id: str, in_frame: int, out_frame: int, source_length: int) -> None:
    if not 0 <= in_frame < out_frame <= source_length:
        raise ValueError(
            f"клип {clip_id}: нужно 0 <= in < out <= length, "
            f"а дано {in_frame}, {out_frame}, {source_length}"
        )


Lane = tuple[AudioClip, ...]


@dataclass(frozen=True)
class Project:
    width: int = 1080
    height: int = 1920
    # Основная дорожка «на магните», как в CapCut: клипы идут встык, дыр не бывает,
    # поэтому позиция клипа — сумма длин предыдущих
    main: tuple[Clip, ...] = ()
    # Звуковые дорожки сверху вниз; в каждой клипы по порядку start и не пересекаются
    audio: tuple[Lane, ...] = ()

    @property
    def main_length(self) -> int:
        return sum(c.length for c in self.main)

    @property
    def length(self) -> int:
        """Длина проекта: до конца основной дорожки или последнего звукового клипа."""
        ends = [c.end for lane in self.audio for c in lane]
        return max([self.main_length, *ends])

    def audio_clip(self, clip_id: str) -> tuple[int, AudioClip] | None:
        """(номер дорожки, клип) или None, если это не звуковой клип."""
        for lane_index, lane in enumerate(self.audio):
            for clip in lane:
                if clip.id == clip_id:
                    return lane_index, clip
        return None

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
    if project.audio_clip(clip_id) is not None:
        return replace(project, audio=_without(project.audio, clip_id))
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
    """Положение клипа основной дорожки на холсте; масштаб зажимается в допустимые пределы."""
    index = project.index_of(clip_id)
    scale = min(max(scale, MIN_SCALE), MAX_SCALE)
    return _replace_clip(project, index, replace(project.main[index], x=x, y=y, scale=scale))


def _replace_clip(project: Project, index: int, clip: Clip) -> Project:
    return replace(project, main=project.main[:index] + (clip,) + project.main[index + 1 :])


# --- звук ---


def _without(lanes: tuple[Lane, ...], clip_id: str, compact: bool = True) -> tuple[Lane, ...]:
    """Дорожки без клипа; опустевшие дорожки убираются (compact)."""
    out = tuple(tuple(c for c in lane if c.id != clip_id) for lane in lanes)
    return tuple(lane for lane in out if lane) if compact else out


def _fits(lane: Lane, clip: AudioClip) -> bool:
    return all(clip.end <= c.start or clip.start >= c.end for c in lane)


def _place(lanes: tuple[Lane, ...], clip: AudioClip, preferred: int = 0) -> tuple[Lane, ...]:
    """Поставить клип в первую дорожку от preferred, где он ни с чем не пересекается."""
    order = list(range(preferred, len(lanes))) + list(range(0, min(preferred, len(lanes))))
    for i in order:
        if _fits(lanes[i], clip):
            lane = tuple(sorted((*lanes[i], clip), key=lambda c: c.start))
            return lanes[:i] + (lane,) + lanes[i + 1 :]
    return (*lanes, (clip,))


def add_audio(project: Project, clip: AudioClip, lane: int = 0) -> Project:
    return replace(project, audio=_place(project.audio, clip, lane))


def detach_audio(project: Project, clip_id: str) -> Project:
    """«Отделить звук»: видеоклип замолкает, его звук — отдельный клип на том же месте."""
    index = project.index_of(clip_id)
    clip = project.main[index]
    if not clip.audio:
        return project
    sound = AudioClip(
        source=clip.source,
        source_length=clip.source_length,
        in_frame=clip.in_frame,
        out_frame=clip.out_frame,
        start=project.clip_start(index),
    )
    project = _replace_clip(project, index, replace(clip, audio=False))
    return add_audio(project, sound)


def move_audio(project: Project, clip_id: str, start: int, lane: int | None = None) -> Project:
    """Передвинуть звуковой клип; занято — встанет в другую дорожку."""
    found = project.audio_clip(clip_id)
    if found is None:
        return project
    current_lane, clip = found
    # Пустую дорожку убираем только после перестановки: иначе клип, один в своей дорожке,
    # при сдвиге вбок перепрыгивал бы в верхнюю
    lanes = _without(project.audio, clip_id, compact=False)
    moved = replace(clip, start=max(0, start))
    if lane is not None and lane >= len(lanes):
        placed = (*lanes, (moved,))  # утащили ниже последней дорожки — новая дорожка
    else:
        preferred = max(0, current_lane if lane is None else lane)
        placed = _place(lanes, moved, preferred)
    return replace(project, audio=tuple(lane for lane in placed if lane))


def _neighbours(project: Project, clip_id: str) -> tuple[int, int | None]:
    """Конец соседа слева и начало соседа справа в той же дорожке (None — справа никого)."""
    found = project.audio_clip(clip_id)
    assert found is not None
    lane_index, clip = found
    lane = project.audio[lane_index]
    left = max((c.end for c in lane if c.end <= clip.start and c.id != clip_id), default=0)
    right = min((c.start for c in lane if c.start >= clip.end and c.id != clip_id), default=None)
    return left, right


def trim_audio_start(project: Project, clip_id: str, in_frame: int) -> Project:
    """Подрезать начало: левый край клипа на таймлайне двигается вместе с in."""
    found = project.audio_clip(clip_id)
    if found is None:
        return project
    lane_index, clip = found
    left, _ = _neighbours(project, clip_id)
    lowest = max(0, clip.in_frame - (clip.start - left))  # не залезть на соседа и в минус
    in_frame = max(lowest, min(in_frame, clip.out_frame - 1))
    moved = replace(clip, in_frame=in_frame, start=clip.start + in_frame - clip.in_frame)
    return _replace_audio(project, lane_index, moved)


def trim_audio_end(project: Project, clip_id: str, out_frame: int) -> Project:
    found = project.audio_clip(clip_id)
    if found is None:
        return project
    lane_index, clip = found
    _, right = _neighbours(project, clip_id)
    highest = (
        clip.source_length
        if right is None
        else min(clip.source_length, clip.out_frame + right - clip.end)
    )
    out_frame = max(clip.in_frame + 1, min(out_frame, highest))
    return _replace_audio(project, lane_index, replace(clip, out_frame=out_frame))


def split_audio(project: Project, clip_id: str, frame: int) -> Project:
    """Разрезать звуковой клип в кадре таймлайна; не внутри клипа — без изменений."""
    found = project.audio_clip(clip_id)
    if found is None:
        return project
    lane_index, clip = found
    if not clip.start < frame < clip.end:
        return project
    cut = clip.in_frame + frame - clip.start
    left = replace(clip, out_frame=cut)
    right = replace(clip, in_frame=cut, start=frame, id=new_id())
    lane = tuple(
        sorted((*(c for c in project.audio[lane_index] if c.id != clip_id), left, right),
               key=lambda c: c.start)
    )  # fmt: skip
    return replace(
        project, audio=project.audio[:lane_index] + (lane,) + project.audio[lane_index + 1 :]
    )


def _replace_audio(project: Project, lane_index: int, clip: AudioClip) -> Project:
    lane = tuple(clip if c.id == clip.id else c for c in project.audio[lane_index])
    return replace(
        project, audio=project.audio[:lane_index] + (lane,) + project.audio[lane_index + 1 :]
    )
