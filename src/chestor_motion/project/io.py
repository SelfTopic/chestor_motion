"""Файл проекта: JSON с версией формата. Старые версии поднимаются миграциями при чтении."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from chestor_motion.project.model import Clip, Project

FORMAT = "chestor_motion"
VERSION = 1
SUFFIX = ".cmproj"

# MIGRATIONS[n] переводит данные версии n в версию n + 1
MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


class ProjectFormatError(ValueError):
    pass


def to_dict(project: Project) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "version": VERSION,
        "width": project.width,
        "height": project.height,
        "main": [
            {
                "id": c.id,
                "source": c.source,
                "source_length": c.source_length,
                "in": c.in_frame,
                "out": c.out_frame,
            }
            for c in project.main
        ],
    }


def from_dict(data: dict[str, Any]) -> Project:
    if data.get("format") != FORMAT:
        raise ProjectFormatError("это не проект chestor_motion")
    version = data.get("version")
    if not isinstance(version, int) or version > VERSION:
        raise ProjectFormatError(f"версия проекта {version} новее этой программы ({VERSION})")
    while version < VERSION:
        data = MIGRATIONS[version](data)
        version += 1
    try:
        return Project(
            width=int(data["width"]),
            height=int(data["height"]),
            main=tuple(
                Clip(
                    id=str(c["id"]),
                    source=str(c["source"]),
                    source_length=int(c["source_length"]),
                    in_frame=int(c["in"]),
                    out_frame=int(c["out"]),
                )
                for c in data["main"]
            ),
        )
    except (KeyError, TypeError, ValueError) as e:
        raise ProjectFormatError(f"повреждённый проект: {e}") from e


def save(project: Project, path: Path) -> None:
    """Пишет во временный файл и подменяет: сбой посреди записи не портит старый проект."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(to_dict(project), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load(path: Path) -> Project:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ProjectFormatError(f"повреждённый проект: {e}") from e
    if not isinstance(data, dict):
        raise ProjectFormatError("повреждённый проект: ожидался объект JSON")
    return from_dict(data)
