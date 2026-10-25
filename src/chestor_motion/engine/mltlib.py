"""То, чего нет в SWIG-привязках mlt7: события с Python-колбэком и доступ к буферу кадра.

Указатели берутся из SWIG-объектов через `int(obj.get_consumer())` и т.п.
"""

import ctypes
from collections.abc import Callable

import mlt7 as mlt

_lib = ctypes.CDLL("libmlt-7.so.7")

# void (*mlt_listener)(mlt_properties owner, void *object, mlt_event_data data);
# mlt_event_data — структура из одного union {int; void*}, по ABI передаётся как указатель.
Listener = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)

_lib.mlt_events_listen.restype = ctypes.c_void_p
_lib.mlt_events_listen.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, Listener]
_lib.mlt_event_inc_ref.argtypes = [ctypes.c_void_p]
_lib.mlt_event_close.argtypes = [ctypes.c_void_p]
_lib.mlt_frame_get_image.restype = ctypes.c_int
_lib.mlt_frame_get_image.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
    ctypes.c_int,
]
_lib.mlt_frame_get_position.restype = ctypes.c_int
_lib.mlt_frame_get_position.argtypes = [ctypes.c_void_p]
_lib.mlt_consumer_start.argtypes = [ctypes.c_void_p]
_lib.mlt_consumer_stop.argtypes = [ctypes.c_void_p]
_lib.mlt_consumer_purge.argtypes = [ctypes.c_void_p]
_lib.mlt_producer_seek.argtypes = [ctypes.c_void_p, ctypes.c_int]
_lib.mlt_producer_set_speed.argtypes = [ctypes.c_void_p, ctypes.c_double]
_lib.mlt_properties_set_int.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
_lib.mlt_properties_set.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]

_initialized = False


def init() -> None:
    global _initialized
    if not _initialized:
        mlt.Factory.init()
        _initialized = True


class Subscription:
    """Подписка на событие MLT. Держит ссылку на колбэк, иначе его съест сборщик мусора."""

    def __init__(self, owner_ptr: int, event: str, callback: Callable[[int], None]) -> None:
        self._callback = Listener(lambda _owner, _obj, data: callback(data or 0))
        self._event = _lib.mlt_events_listen(owner_ptr, None, event.encode(), self._callback)
        # Событием владеет owner; своя ссылка — как в Mlt::Event, иначе close освободит чужое
        if self._event:
            _lib.mlt_event_inc_ref(self._event)

    def close(self) -> None:
        if self._event:
            _lib.mlt_event_close(self._event)
            self._event = None


# Управление работающим консьюмером и его источником — только через функции ниже.
# SWIG-вызовы держат GIL, пока ждут мьютексы MLT, а поток консьюмера может держать такой мьютекс
# и ждать GIL в нашем колбэке frame-show — взаимная блокировка (stop, refresh при перемотке).
# ctypes на время C-вызова GIL отпускает.


def consumer_start(consumer_ptr: int) -> None:
    _lib.mlt_consumer_start(consumer_ptr)


def consumer_stop(consumer_ptr: int) -> None:
    _lib.mlt_consumer_stop(consumer_ptr)


def consumer_purge(consumer_ptr: int) -> None:
    """Выбросить кадры, заготовленные наперёд (буфер ~25 кадров): после seek/pause они устарели."""
    _lib.mlt_consumer_purge(consumer_ptr)


def consumer_refresh(consumer_ptr: int) -> None:
    """Перерисовать текущий кадр (после перемотки на паузе). mlt_consumer — это mlt_properties."""
    _lib.mlt_properties_set_int(consumer_ptr, b"refresh", 1)


def properties_set(properties_ptr: int, name: str, value: str) -> None:
    """Свойство работающего фильтра (прямоугольник qtblend, пока клип тащат на превью)."""
    _lib.mlt_properties_set(properties_ptr, name.encode(), value.encode())


def producer_seek(producer_ptr: int, position: int) -> None:
    _lib.mlt_producer_seek(producer_ptr, position)


def producer_set_speed(producer_ptr: int, speed: float) -> None:
    _lib.mlt_producer_set_speed(producer_ptr, speed)


def frame_position(frame_ptr: int) -> int:
    return _lib.mlt_frame_get_position(frame_ptr)


def frame_rgba(frame_ptr: int) -> tuple[bytes, int, int]:
    """Копия кадра в RGBA в размере профиля (без масштабирования — его делает видеокарта)."""
    buf = ctypes.c_void_p()
    fmt = ctypes.c_int(mlt.mlt_image_rgba)
    w = ctypes.c_int(0)
    h = ctypes.c_int(0)
    err = _lib.mlt_frame_get_image(
        frame_ptr, ctypes.byref(buf), ctypes.byref(fmt), ctypes.byref(w), ctypes.byref(h), 0
    )
    if err or not buf.value:
        return b"", 0, 0
    return ctypes.string_at(buf, w.value * h.value * 4), w.value, h.value
