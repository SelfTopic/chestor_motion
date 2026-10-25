import mlt7
from PySide6 import QtCore


def test_system_packages_available() -> None:
    # venv обязан видеть системные mlt7 и PySide6 (poetry.toml: system-site-packages)
    assert mlt7.LIBMLT_VERSION.startswith("7.")
    assert QtCore.qVersion().startswith("6.")
