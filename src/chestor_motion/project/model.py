"""Модель проекта — правда о монтаже. MLT только исполняет её (см. engine/builder.py).

Модель неизменяемая: каждая правка возвращает новый Project, старый остаётся как был —
поэтому отмена действий это просто стопка снимков (project/history.py).

Время — целые кадры проекта (FPS). Интервалы полуоткрытые: [in_frame, out_frame).
"""

import uuid
from dataclasses import dataclass, field, replace

FPS = 30


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass(frozen=True)
class Clip:
    source: str  # абсолютный путь к оригиналу; прокси подставляет сборщик
    source_length: int  # длина исходника в кадрах проекта — граница для подрезки
    in_frame: int  # первый используемый кадр исходника
    out_frame: int  # кадр исходника сразу после последнего используемого
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        if not 0 <= self.in_frame < self.out_frame <= self.source_length:
            raise ValueError(
                f"клип {self.id}: нужно 0 <= in < out <= length, "
                f"а дано {self.in_frame}, {self.out_frame}, {self.source_length}"
            )

    @property
    def length(self) -> int:
        return self.out_frame - self.in_frame


@dataclass(frozen=True)
class Project:
    width: int = 1080
    height: int = 1920
    # Основная дорожка «на магните», как в CapCut: клипы идут встык, дыр не бывает,
    # поэтому позиция клипа — сумма длин предыдущих
    main: tuple[Clip, ...] = ()

    @property
    def length(self) -> int:
        return sum(c.length for c in self.main)

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


def _replace_clip(project: Project, index: int, clip: Clip) -> Project:
    return replace(project, main=project.main[:index] + (clip,) + project.main[index + 1 :])
