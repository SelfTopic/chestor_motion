"""Отмена и повтор: модель неизменяемая, поэтому история — просто снимки проекта."""

from chestor_motion.project.model import Project

LIMIT = 200


class History:
    def __init__(self, project: Project) -> None:
        self._undo: list[Project] = []
        self._redo: list[Project] = []
        self.current = project

    def push(self, project: Project) -> None:
        if project == self.current:
            return
        self._undo.append(self.current)
        del self._undo[:-LIMIT]
        self._redo.clear()
        self.current = project

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self.current)
        self.current = self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self.current)
        self.current = self._redo.pop()
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)
