from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QImage

from chestor_motion.engine.proxy import ProxyJob
from chestor_motion.engine.thumbs import COLUMNS, TILE_HEIGHT, ThumbJob, tile_width


def _run(job) -> object:
    result: dict[str, object] = {}
    loop = QEventLoop()
    job.finished.connect(lambda r: (result.update(ok=r), loop.quit()))
    job.failed.connect(lambda e: (result.update(error=e), loop.quit()))
    QTimer.singleShot(30_000, loop.quit)
    job.start()
    loop.exec()
    assert "error" not in result, result["error"]
    return result["ok"]


def test_tile_width_keeps_aspect() -> None:
    assert tile_width(1920, 1080) == 100
    assert tile_width(1080, 1920) == 32
    assert tile_width(1278, 590) == 122


def test_sprite_from_intra_proxy(qapp, clip: Path, tmp_path: Path) -> None:
    proxy = Path(str(_run(ProxyJob(clip, (642, 360), 2.0, cache_dir=tmp_path / "p"))))
    info = _run(ThumbJob(proxy, (642, 360), 60, cache_dir=tmp_path / "t"))
    assert isinstance(info, dict)
    assert info["count"] == 2  # 60 кадров, миниатюра раз в 30
    image = QImage(str(next((tmp_path / "t").glob("*.jpg"))))
    assert (image.width(), image.height()) == (COLUMNS * info["tileWidth"], TILE_HEIGHT)
    assert not list((tmp_path / "t").glob("*.part.jpg"))

    # Повторно — из кэша, тот же файл
    again = _run(ThumbJob(proxy, (642, 360), 60, cache_dir=tmp_path / "t"))
    assert again == info
