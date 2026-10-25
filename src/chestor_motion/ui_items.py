"""Свои QML-элементы, нарисованные на Python. В QML: import ChestorMotion.

Регистрируются декоратором @QmlElement при импорте модуля — register_qml_types() только
гарантирует, что модуль импортирован до загрузки QML.
"""

from PySide6.QtCore import Property, QByteArray, QLineF, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtQml import QmlElement
from PySide6.QtQuick import QQuickItem, QQuickPaintedItem

QML_IMPORT_NAME = "ChestorMotion"
QML_IMPORT_MAJOR_VERSION = 1


@QmlElement
class Waveform(QQuickPaintedItem):
    """Форма волны участка клипа. Рисует только себя — QML ставит элемент на видимую часть
    клипа: при сильном увеличении клип бывает в миллион точек шириной.

    firstFrame — кадр исходника у левого края элемента, pxPerFrame — масштаб таймлайна.
    """

    changed = Signal()

    def __init__(self, parent: QQuickItem | None = None) -> None:
        super().__init__(parent)
        self._peaks = b""
        self._first = 0.0
        self._px = 1.0
        self._color = QColor("#22d3c5")
        self.changed.connect(self.update)

    def _get_peaks(self) -> QByteArray:
        return QByteArray(self._peaks)

    def _set_peaks(self, value: QByteArray) -> None:
        data = bytes(value.data()) if isinstance(value, QByteArray) else bytes(value or b"")
        if data != self._peaks:
            self._peaks = data
            self.changed.emit()

    def _get_first(self) -> float:
        return self._first

    def _set_first(self, value: float) -> None:
        if value != self._first:
            self._first = value
            self.changed.emit()

    def _get_px(self) -> float:
        return self._px

    def _set_px(self, value: float) -> None:
        if value > 0 and value != self._px:
            self._px = value
            self.changed.emit()

    def _get_color(self) -> QColor:
        return self._color

    def _set_color(self, value: QColor) -> None:
        if value != self._color:
            self._color = QColor(value)
            self.changed.emit()

    peaks = Property(QByteArray, _get_peaks, _set_peaks, notify=changed)  # type: ignore[arg-type]
    firstFrame = Property(float, _get_first, _set_first, notify=changed)  # type: ignore[arg-type]
    pxPerFrame = Property(float, _get_px, _set_px, notify=changed)  # type: ignore[arg-type]
    color = Property(QColor, _get_color, _set_color, notify=changed)  # type: ignore[arg-type]

    def paint(self, painter: QPainter) -> None:
        peaks, n = self._peaks, len(self._peaks)
        width, height = int(self.width()), self.height()
        if not n or width <= 0:
            return
        mid = height / 2
        painter.setPen(QPen(self._color, 1))
        lines = []
        for x in range(width):
            # Кадры исходника под этим столбцом точек; при увеличении столбец — часть кадра
            f0 = int(self._first + x / self._px)
            f1 = max(f0 + 1, int(self._first + (x + 1) / self._px))
            if f0 >= n:
                break
            if f0 < 0:
                continue
            half = max(peaks[f0:f1]) / 255 * mid
            if half >= 0.5:
                lines.append(QLineF(x + 0.5, mid - half, x + 0.5, mid + half))
        painter.drawLines(lines)


def register_qml_types() -> None:
    """Типы уже зарегистрированы импортом этого модуля."""
