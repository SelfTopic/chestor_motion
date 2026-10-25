"""Плеер на MLT: воспроизведение, звук и синхронизацию делает консьюмер sdl2_audio,
мы только забираем показанный кадр и отдаём его в QVideoSink (масштабирует видеокарта)."""

import mlt7 as mlt
from PySide6.QtCore import Property, QObject, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtMultimedia import QVideoFrame, QVideoFrameFormat, QVideoSink

from chestor_motion.engine import mltlib
from chestor_motion.qt import qproperty

FPS = 30
# Если кадр после перемотки так и не пришёл (например, тот же самый кадр), не ждём вечно
SEEK_TIMEOUT_MS = 250


def _to_video_frame(rgba: bytes, w: int, h: int) -> QVideoFrame:
    fmt = QVideoFrameFormat(QSize(w, h), QVideoFrameFormat.PixelFormat.Format_RGBA8888)
    frame = QVideoFrame(fmt)
    frame.map(QVideoFrame.MapMode.WriteOnly)
    dst = memoryview(frame.bits(0))  # type: ignore[arg-type]
    stride = frame.bytesPerLine(0)
    row = w * 4
    if stride == row:
        dst[: len(rgba)] = rgba
    else:
        for y in range(h):
            dst[y * stride : y * stride + row] = rgba[y * row : (y + 1) * row]
    frame.unmap()
    return frame


class Player(QObject):
    # Испускаются из потока MLT, доходят до GUI-потока через очередь сигналов
    _frameShown = Signal(QVideoFrame, int)

    positionChanged = Signal()
    mediaChanged = Signal()
    playingChanged = Signal()
    videoSinkChanged = Signal()

    def __init__(self, audio_out: str = "sdl2_audio", parent: QObject | None = None) -> None:
        """audio_out — консьюмер MLT, который выводит звук и задаёт темп воспроизведения.

        Не rtaudio: на паузе он перестаёт обновлять картинку после нескольких перемоток подряд.
        """
        super().__init__(parent)
        mltlib.init()
        self._audio_out = audio_out
        self._profile: mlt.Profile | None = None
        self._producer: mlt.Producer | None = None
        self._consumer: mlt.Consumer | None = None
        self._subscription: mltlib.Subscription | None = None
        # Сырые указатели работающих объектов: управление ими — только через mltlib (без GIL)
        self._producer_ptr = 0
        self._consumer_ptr = 0
        self._sink: QVideoSink | None = None
        self._position = 0
        self._length = 0
        self._playing = False
        self._width = 0
        self._height = 0
        # Перемотка не перебивает кадр, который ещё декодируется: иначе при таскании ползунка
        # (особенно назад — там каждый кадр декодируется от ключевого) каждый seek выбрасывает
        # недоделанный кадр и картинка стоит до остановки мыши. Пока кадр в пути — запоминаем
        # последнюю цель и едем к ней, когда он покажется.
        self._seek_in_flight: int | None = None
        self._seek_queued: int | None = None
        self._seek_timeout = QTimer(self)
        self._seek_timeout.setSingleShot(True)
        self._seek_timeout.setInterval(SEEK_TIMEOUT_MS)
        self._seek_timeout.timeout.connect(self._finish_seek)
        self._frameShown.connect(self._on_frame_shown, Qt.ConnectionType.QueuedConnection)

    # --- свойства для QML ---

    def _get_sink(self) -> QVideoSink | None:
        return self._sink

    def set_video_sink(self, sink: QVideoSink | None) -> None:
        if sink is not self._sink:
            self._sink = sink
            self.videoSinkChanged.emit()

    videoSink = Property(QObject, _get_sink, set_video_sink, notify=videoSinkChanged)  # type: ignore[arg-type]

    @qproperty(int, notify=positionChanged)
    def position(self) -> int:
        return self._position

    @qproperty(int, notify=mediaChanged)
    def length(self) -> int:
        return self._length

    @qproperty(bool, notify=mediaChanged)
    def hasMedia(self) -> bool:
        return self._producer is not None and self._length > 0

    @qproperty(int, constant=True)
    def fps(self) -> int:
        return FPS

    @qproperty(bool, notify=playingChanged)
    def playing(self) -> bool:
        return self._playing

    @property
    def size(self) -> tuple[int, int]:
        return self._width, self._height

    # --- управление ---

    def show(
        self, producer: mlt.Producer, profile: mlt.Profile, position: int | None = None
    ) -> None:
        """Показать собранный граф. Позиция и воспроизведение сохраняются, если не задана новая.

        Граф пересобирается после каждой правки, поэтому подмена должна быть дешёвой: консьюмер
        пересоздаётся только при смене профиля, иначе — остановка, подключение, запуск.
        """
        was_playing = self._playing
        keep = self._position if position is None else position
        if self._profile is not profile:
            self._close()
            self._profile = profile
            self._open_consumer(profile)
        elif self._consumer_ptr:
            mltlib.consumer_stop(self._consumer_ptr)
        assert self._consumer is not None
        # Консьюмер остановлен — можно трогать через SWIG
        self._consumer.connect(producer)
        self._producer = producer
        self._producer_ptr = int(producer.get_producer())
        self._width, self._height = profile.width(), profile.height()
        self._length = producer.get_length()
        self._seek_timeout.stop()
        self._seek_in_flight = self._seek_queued = None
        self._position = max(0, min(keep, self._length - 1))
        mltlib.producer_set_speed(self._producer_ptr, 0)
        mltlib.producer_seek(self._producer_ptr, self._position)
        mltlib.consumer_start(self._consumer_ptr)
        self.mediaChanged.emit()
        self.positionChanged.emit()
        self._playing = False
        if was_playing and self._length > 0:
            self.play()
        else:
            self._refresh()
            self.playingChanged.emit()

    def clear(self) -> None:
        self._close()
        self.mediaChanged.emit()

    def _open_consumer(self, profile: mlt.Profile) -> None:
        consumer = mlt.Consumer(profile, self._audio_out)
        consumer.set("terminate_on_pause", 0)
        consumer.set("real_time", 1)
        # Без звука на паузе: иначе буфер упреждения забивается копиями одного кадра со звуком
        # и он звучит петлёй (после перемотки на паузе и в конце ролика)
        consumer.set("scrub_audio", 0)
        self._consumer = consumer
        self._consumer_ptr = int(consumer.get_consumer())
        self._subscription = mltlib.Subscription(
            self._consumer_ptr, "consumer-frame-show", self._on_mlt_frame
        )

    @Slot()
    def play(self) -> None:
        if not self._producer_ptr:
            return
        if self._position >= self._length - 1:
            mltlib.producer_seek(self._producer_ptr, 0)
        mltlib.producer_set_speed(self._producer_ptr, 1)
        self._refresh()
        self._set_playing(True)

    @Slot()
    def pause(self) -> None:
        if not self._producer_ptr:
            return
        mltlib.producer_set_speed(self._producer_ptr, 0)
        self._seek_queued = None
        self._start_seek(self._position)
        self._set_playing(False)

    @Slot()
    def togglePlay(self) -> None:
        self.pause() if self._playing else self.play()

    @Slot(int)
    def seek(self, frame: int) -> None:
        if not self._producer_ptr:
            return
        frame = max(0, min(frame, self._length - 1))
        self._set_position(frame)
        if self._seek_in_flight is None:
            self._start_seek(frame)
        else:
            self._seek_queued = frame

    @Slot(int)
    def step(self, frames: int) -> None:
        if self._playing:
            self.pause()
        self.seek(self._position + frames)

    def shutdown(self) -> None:
        self._close()

    # --- внутреннее ---

    def _start_seek(self, frame: int) -> None:
        mltlib.producer_seek(self._producer_ptr, frame)
        mltlib.consumer_purge(self._consumer_ptr)
        self._refresh()
        self._seek_in_flight = frame
        self._seek_timeout.start()

    def _finish_seek(self) -> None:
        self._seek_timeout.stop()
        self._seek_in_flight = None
        queued, self._seek_queued = self._seek_queued, None
        if queued is not None and self._producer_ptr:
            self._start_seek(queued)

    def _refresh(self) -> None:
        if self._consumer_ptr:
            mltlib.consumer_refresh(self._consumer_ptr)

    def _set_playing(self, playing: bool) -> None:
        if playing != self._playing:
            self._playing = playing
            self.playingChanged.emit()

    def _set_position(self, position: int) -> None:
        if position != self._position:
            self._position = position
            self.positionChanged.emit()

    def _close(self) -> None:
        if self._consumer_ptr:
            mltlib.consumer_stop(self._consumer_ptr)
        if self._subscription is not None:
            self._subscription.close()
        # Порядок важен: консьюмер ссылается на источник, оба — на профиль
        self._consumer = None
        self._producer = None
        self._profile = None
        self._subscription = None
        self._producer_ptr = self._consumer_ptr = 0
        self._seek_timeout.stop()
        self._seek_in_flight = self._seek_queued = None
        self._length = 0
        self._set_playing(False)

    def _on_mlt_frame(self, frame_ptr: int) -> None:
        # Поток консьюмера MLT: только копия кадра, никакого Qt-GUI
        if not frame_ptr:
            return
        rgba, w, h = mltlib.frame_rgba(frame_ptr)
        if rgba:
            self._frameShown.emit(_to_video_frame(rgba, w, h), mltlib.frame_position(frame_ptr))

    @Slot(QVideoFrame, int)
    def _on_frame_shown(self, frame: QVideoFrame, position: int) -> None:
        if self._sink is not None:
            self._sink.setVideoFrame(frame)
        if self._seek_in_flight is not None and position == self._seek_in_flight:
            self._finish_seek()
        seeking = self._seek_in_flight is not None or self._seek_queued is not None
        if self._playing and not seeking:
            self._set_position(position)
            if position >= self._length - 1:
                self.pause()
