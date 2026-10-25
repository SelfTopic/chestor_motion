import faulthandler
import os
import signal
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from chestor_motion.engine.player import Player
from chestor_motion.files import FileBrowser
from chestor_motion.project import io
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
    files = FileBrowser(session.data_dir, session.drafts_dir)
    engine.setInitialProperties({"player": player, "session": session, "files": files})
    engine.load(QML_DIR / "Main.qml")
    if not engine.rootObjects():
        return 1

    # Файл проекта — открыть, видео — импортировать в новый; без аргументов — прошлый проект
    args = [Path(a) for a in sys.argv[1:]]
    for arg in args:
        if arg.suffix == io.SUFFIX:
            session.open_project(arg)
        else:
            session.import_path(arg)
    if not args:
        session.restore_last()

    code = app.exec()
    # Сначала QML: иначе привязки успевают пересчитаться с уже удалёнными player и session
    del engine
    session.close()
    player.shutdown()
    return code


if __name__ == "__main__":
    sys.exit(main())
