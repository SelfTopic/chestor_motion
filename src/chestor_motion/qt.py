"""Типизированная обёртка над Qt Property: pyright видит у атрибута тип значения, а не Property."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Property, Signal


def qproperty[T](
    type_: type[T], *, notify: Signal | None = None, constant: bool = False
) -> Callable[[Callable[[Any], T]], T]:
    def wrap(getter: Callable[[Any], T]) -> T:
        if notify is None:
            return Property(type_, getter, constant=constant)  # type: ignore[return-value]
        return Property(type_, getter, notify=notify, constant=constant)  # type: ignore[return-value]

    return wrap
