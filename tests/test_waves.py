import array
import subprocess
from pathlib import Path

from PySide6.QtCore import QByteArray, QEventLoop, QTimer
from PySide6.QtGui import QColor, QImage, QPainter

from chestor_motion.engine.waves import SAMPLES_PER_FRAME, WaveJob, peaks_from_samples
from chestor_motion.ui_items import Waveform


def _frames(*amplitudes: float) -> array.array:
    """Кадры звука: в каждом один пик заданной амплитуды (доля от полной шкалы)."""
    samples = array.array("h")
    for a in amplitudes:
        frame = [0] * SAMPLES_PER_FRAME
        frame[10] = round(a * 32767)
        samples.extend(frame)
    return samples


def test_peaks_are_in_decibels() -> None:
    peaks = peaks_from_samples(_frames(0.0, 1.0, 10 ** (-24 / 20), 10 ** (-60 / 20)))
    assert peaks[0] == 0  # тишина
    assert peaks[1] == 255  # полная шкала
    assert abs(peaks[2] - 128) <= 1  # -24 дБ — середина шкалы в 48 дБ
    assert peaks[3] == 0  # тише -48 дБ
    assert len(peaks_from_samples(array.array("h", [1] * (SAMPLES_PER_FRAME + 5)))) == 1


def _run(job: WaveJob) -> bytes | str:
    result: dict[str, object] = {}
    loop = QEventLoop()
    job.finished.connect(lambda p: (result.update(ok=p), loop.quit()))
    job.failed.connect(lambda e: (result.update(error=e), loop.quit()))
    QTimer.singleShot(20_000, loop.quit)
    job.start()
    loop.exec()
    return result.get("ok", result.get("error", ""))  # type: ignore[return-value]


def test_wave_of_clip_with_tone(qapp, clip: Path, tmp_path: Path) -> None:
    peaks = _run(WaveJob(clip, cache_dir=tmp_path))
    assert isinstance(peaks, bytes)
    assert 58 <= len(peaks) <= 62  # 2 с при 30 кадрах
    assert min(peaks[2:-2]) > 150  # тон громкий всё время
    assert list(tmp_path.glob("*.peaks")) and not list(tmp_path.glob("*.raw"))
    again = WaveJob(clip, cache_dir=tmp_path)
    assert _run(again) == peaks  # из кэша


def test_no_audio_fails_quietly(qapp, tmp_path: Path) -> None:
    silent = tmp_path / "video_only.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=30", "-t", "1",
         "-c:v", "libx264", str(silent)],
        check=True,
    )  # fmt: skip
    result = _run(WaveJob(silent, cache_dir=tmp_path / "w"))
    assert isinstance(result, str) and not list((tmp_path / "w").glob("*.peaks"))


def test_waveform_paints_visible_part(qapp) -> None:
    item = Waveform()
    item.setWidth(100)
    item.setHeight(20)
    item.setProperty("peaks", QByteArray(bytes([0] * 50 + [255] * 50)))
    item.setProperty("pxPerFrame", 2.0)  # 100 точек — 50 кадров
    item.setProperty("firstFrame", 25.0)  # видна вторая половина тишины и начало громкого
    item.setProperty("color", QColor("#ffffff"))
    image = QImage(100, 20, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    item.paint(painter)
    painter.end()
    assert image.pixelColor(20, 10).alpha() == 0  # кадр 35 — тишина
    assert image.pixelColor(80, 10).alpha() > 0  # кадр 65 — громко
    assert image.pixelColor(80, 0).alpha() > 0  # пик на всю высоту
