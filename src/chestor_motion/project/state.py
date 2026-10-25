"""Маленькое состояние программы между запусками: data_dir/state.json.

Несколько владельцев пишут свои ключи (последний проект, недавние папки) — запись сливает
ключ с тем, что уже лежит в файле, а не затирает чужие.
"""

import json
from pathlib import Path
from typing import Any


class State:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "state.json"

    def get(self, key: str, default: Any = None) -> Any:
        return self._read().get(key, default)

    def set(self, key: str, value: Any) -> None:
        data = self._read()
        data[key] = value
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}
