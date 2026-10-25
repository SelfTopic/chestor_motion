import faulthandler
import os
import signal
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from chestor_motion.engine.player import Player
from chestor_motion.session import Session

QML_DIR = Path(__file__).parent / "ui"


def main() -> int:
    # Зависло окно — `kill -USR1 <pid>` печатает стеки Python всех потоков в терминал
    faulthandler.register(signal.SIGUSR1, all_threads=True)
    # Свой тёмный дизайн: стиль Basic, а не системный стиль KDE
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("chestor_motion")
    app.setOrganizationName("chestor_motion")

    player = Player()
    session = Session(player)
    engine = QQmlApplicationEngine()
    engine.setInitialProperties({"player": player, "session": session})
    engine.load(QML_DIR / "Main.qml")
    if not engine.rootObjects():
        return 1

    if len(sys.argv) > 1:
        session.open_path(Path(sys.argv[1]))

    code = app.exec()
    player.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
