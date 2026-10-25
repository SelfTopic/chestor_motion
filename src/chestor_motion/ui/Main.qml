import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtMultimedia

ApplicationWindow {
    id: root

    required property var player
    required property var session
    required property var files

    // Пока открыто окно поверх (файлы, справка), клавиши главного окна молчат: иначе «s»,
    // набранная в поиске, разрезала бы клип
    readonly property bool modalOpen: fileBrowser.visible || hotkeysPanel.visible || exportPanel.visible

    readonly property color bg: "#0f0f11"
    readonly property color panel: "#1a1a1e"
    readonly property color accent: "#22d3c5"
    readonly property color textMain: "#f2f2f4"
    readonly property color textDim: "#8a8a93"

    function timecode(frames) {
        const fps = player.fps
        const total = Math.floor(frames / fps)
        const m = Math.floor(total / 60)
        const s = total % 60
        return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0")
    }

    width: 1280
    height: 800
    minimumWidth: 720
    minimumHeight: 480
    visible: true
    title: session.title + " — chestor_motion"
    color: bg

    // Все клавиши и действия мышью — один список: из него создаются горячие клавиши и
    // панель справки (F1), так справка не разъезжается с тем, что работает на самом деле.
    // keys пустой — действие мышью, только для справки. local — клавиша своего окна (окна
    // файлов): в справке есть, но главное окно её не назначает.
    readonly property var hotkeys: [
        { group: "Воспроизведение", keys: ["Space"], label: "Пробел",
          text: "Воспроизвести / пауза", action: () => player.togglePlay() },
        { group: "Воспроизведение", keys: ["Left"], label: "←",
          text: "На кадр назад", action: () => player.step(-1) },
        { group: "Воспроизведение", keys: ["Right"], label: "→",
          text: "На кадр вперёд", action: () => player.step(1) },
        { group: "Воспроизведение", keys: ["Shift+Left"], label: "Shift+←",
          text: "На секунду назад", action: () => player.step(-player.fps) },
        { group: "Воспроизведение", keys: ["Shift+Right"], label: "Shift+→",
          text: "На секунду вперёд", action: () => player.step(player.fps) },
        { group: "Воспроизведение", keys: ["Home"], label: "Home",
          text: "В начало", action: () => player.seek(0) },
        { group: "Воспроизведение", keys: ["End"], label: "End",
          text: "В конец", action: () => player.seek(player.length - 1) },

        { group: "Монтаж", keys: ["S"], label: "S",
          text: "Разрезать: выделенный звуковой клип, иначе клип основной дорожки под плейхедом",
          action: () => session.splitAtPlayhead() },
        { group: "Монтаж", keys: ["Delete", "Backspace"], label: "Delete",
          text: "Удалить выделенный клип, а если ничего не выделено — клип под плейхедом",
          action: () => session.deleteSelectedOrAtPlayhead() },
        { group: "Монтаж", keys: ["D"], label: "D",
          text: "Отделить звук видеоклипа на звуковую дорожку (выделенного или под плейхедом)",
          action: () => session.detachAudio() },
        { group: "Монтаж", keys: ["F"], label: "F",
          text: "Заполнить холст клипом (выделенным или под плейхедом), ещё раз — вписать",
          action: () => session.toggleFill() },
        { group: "Монтаж", keys: ["Escape"], label: "Esc",
          text: "Снять выделение", action: () => session.select("") },
        { group: "Монтаж", keys: ["Ctrl+Z"], label: "Ctrl+Z",
          text: "Отменить", action: () => session.undo() },
        // Явно, а не StandardKey.Redo: в KDE он уже Ctrl+Shift+Z, и дубль делает сочетание
        // неоднозначным — тогда Qt не вызывает ни один из ярлыков
        { group: "Монтаж", keys: ["Ctrl+Shift+Z", "Ctrl+Y"], label: "Ctrl+Shift+Z",
          text: "Повторить", action: () => session.redo() },

        { group: "Превью", keys: [], label: "Клик по картинке",
          text: "Выделить клип под плейхедом — появится рамка" },
        { group: "Превью", keys: [], label: "Тянуть картинку",
          text: "Двигать клип по холсту; у центра прилипает" },
        { group: "Превью", keys: [], label: "Углы рамки",
          text: "Масштаб; прилипает к «вписать» и «заполнить»" },
        { group: "Превью", keys: [], label: "Колесо",
          text: "Масштаб выделенного клипа" },
        { group: "Превью", keys: [], label: "Двойной щелчок",
          text: "Заполнить холст / вписать обратно (как F)" },

        { group: "Таймлайн", keys: [], label: "Клик по клипу",
          text: "Выделить клип и перемотать в это место" },
        { group: "Таймлайн", keys: [], label: "Тянуть клип",
          text: "Переставить клип, остальные сдвинутся встык" },
        { group: "Таймлайн", keys: [], label: "Правый клик",
          text: "Меню клипа: разрезать, отделить звук, удалить" },
        { group: "Таймлайн", keys: [], label: "Тянуть звук",
          text: "Звуковой клип — по времени и между дорожками; ниже последней — новая дорожка" },
        { group: "Таймлайн", keys: [], label: "Белые ручки",
          text: "Подрезать начало или конец выделенного клипа" },
        { group: "Таймлайн", keys: [], label: "Клик по линейке",
          text: "Перемотать; головку плейхеда можно тянуть" },
        { group: "Таймлайн", keys: [], label: "Ctrl+колесо",
          text: "Масштаб вокруг курсора" },
        { group: "Таймлайн", keys: [], label: "Колесо",
          text: "Прокрутка; при увеличении снизу есть ползунок" },

        // Импорт — Ctrl+I, как в CapCut; Ctrl+O открывает проект
        { group: "Проект", keys: ["Ctrl+I"], label: "Ctrl+I",
          text: "Импорт видео и звука (или перетащи файлы в окно)", action: () => fileBrowser.openFor("media") },
        { group: "Проект", keys: ["Ctrl+N"], label: "Ctrl+N",
          text: "Новый проект", action: () => session.newProject() },
        { group: "Проект", keys: ["Ctrl+O"], label: "Ctrl+O",
          text: "Открыть проект", action: () => fileBrowser.openFor("project") },
        { group: "Проект", keys: ["Ctrl+S"], label: "Ctrl+S",
          text: "Сохранить сейчас (и так сохраняется само)", action: () => session.save() },
        { group: "Проект", keys: ["Ctrl+E"], label: "Ctrl+E",
          text: "Экспорт видео", action: () => exportPanel.openPanel() },
        { group: "Проект", keys: ["Ctrl+Shift+S"], label: "Ctrl+Shift+S",
          text: "Сохранить как…", action: () => saveAsDialog.open() },
        { group: "Проект", keys: ["F1"], label: "F1",
          text: "Эта справка", action: () => hotkeysPanel.visible ? hotkeysPanel.close() : hotkeysPanel.open() },

        { group: "Окно файлов", keys: ["Ctrl+F"], label: "Ctrl+F", local: true,
          text: "Поиск по имени во всех подпапках" },
        { group: "Окно файлов", keys: ["Ctrl+H"], label: "Ctrl+H", local: true,
          text: "Показать скрытые папки и файлы" },
        { group: "Окно файлов", keys: ["Backspace"], label: "Backspace", local: true,
          text: "На уровень вверх" },
        { group: "Окно файлов", keys: ["Return"], label: "Enter", local: true,
          text: "Войти в папку или импортировать" },
        { group: "Окно файлов", keys: [], label: "Ctrl/Shift+клик",
          text: "Выбрать несколько видео" },
        { group: "Окно файлов", keys: ["Escape"], label: "Esc", local: true,
          text: "Очистить поиск, ещё раз — закрыть" },
    ]

    Repeater {
        model: root.hotkeys.filter(h => h.keys.length > 0 && !h.local)
        // Shortcut ищет окно через родительский элемент — поэтому обёртка Item
        delegate: Item {
            required property var modelData
            Shortcut {
                sequences: modelData.keys
                // F1 закрывает справку и поверх неё; остальное — только без окон поверх
                enabled: !root.modalOpen || (modelData.keys.includes("F1") && !fileBrowser.visible)
                onActivated: modelData.action()
            }
        }
    }

    HotkeysPanel {
        id: hotkeysPanel
        objectName: "hotkeysPanel"
        hotkeys: root.hotkeys
    }

    FileBrowser {
        id: fileBrowser
        objectName: "fileBrowser"
        files: root.files
        onAccepted: (paths) => {
            if (mode === "project")
                session.openProjectPath(paths[0])
            else if (mode === "folder")
                exportPanel.folder = paths[0]
            else
                session.importPaths(paths)
        }
    }

    ExportPanel {
        id: exportPanel
        objectName: "exportPanel"
        session: root.session
        onChooseFolder: (current) => fileBrowser.openFor("folder", current)
    }

    FileDialog {
        id: saveAsDialog
        title: "Сохранить проект как"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "cmproj"
        currentFolder: session.saveFolder
        nameFilters: ["Проект chestor_motion (*.cmproj)"]
        onAccepted: session.saveAs(selectedFile)
    }

    // Встроенный компонент не видит id файла (root) — цвета прямо здесь
    component MenuEntry: MenuItem {
        id: entry
        property string shortcutText: ""
        property bool current: false  // выбранный вариант — акцентным цветом
        implicitWidth: 260
        implicitHeight: 34
        contentItem: RowLayout {
            Text {
                text: entry.text
                color: entry.current ? "#22d3c5" : "#f2f2f4"
                font.pixelSize: 14
                font.weight: entry.current ? Font.DemiBold : Font.Normal
                Layout.fillWidth: true
            }
            Text {
                text: entry.shortcutText
                color: "#8a8a93"
                font.pixelSize: 12
            }
        }
        background: Rectangle {
            color: entry.highlighted ? "#2a2a33" : "transparent"
            radius: 6
        }
    }

    header: Rectangle {
        height: 52
        color: root.panel

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            spacing: 12

            Button {
                id: importButton
                text: "＋  Импорт"
                onClicked: fileBrowser.openFor("media")
                contentItem: Text {
                    text: importButton.text
                    color: "#0f0f11"
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    implicitWidth: 112
                    implicitHeight: 34
                    radius: 17
                    color: importButton.down ? Qt.darker(root.accent, 1.2) : root.accent
                }
            }

            // Меню проекта: имя проекта и есть кнопка, как в CapCut
            Button {
                id: projectButton
                objectName: "projectButton"
                Layout.maximumWidth: 420
                onClicked: projectMenu.open()
                ToolTip.visible: hovered && session.projectPath !== ""
                ToolTip.text: session.projectPath
                ToolTip.delay: 600
                contentItem: Text {
                    text: session.title + "  ▾"
                    color: root.textMain
                    font.pixelSize: 14
                    elide: Text.ElideMiddle
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    implicitHeight: 34
                    radius: 8
                    color: projectButton.down || projectMenu.visible ? "#2a2a33"
                         : projectButton.hovered ? "#222228" : "transparent"
                }

                Menu {
                    id: projectMenu
                    objectName: "projectMenu"
                    y: projectButton.height + 4
                    padding: 6
                    background: Rectangle {
                        implicitWidth: 260
                        color: root.panel
                        border.color: "#2c2c33"
                        radius: 10
                    }
                    MenuEntry { text: "Новый проект"; shortcutText: "Ctrl+N"; onTriggered: session.newProject() }
                    MenuEntry { text: "Открыть…"; shortcutText: "Ctrl+O"; onTriggered: fileBrowser.openFor("project") }
                    MenuEntry { text: "Сохранить"; shortcutText: "Ctrl+S"; onTriggered: session.save() }
                    MenuEntry { text: "Сохранить как…"; shortcutText: "Ctrl+Shift+S"; onTriggered: saveAsDialog.open() }
                    MenuSeparator {
                        contentItem: Rectangle { implicitHeight: 1; color: "#2c2c33" }
                    }
                    MenuEntry { text: "Экспорт видео…"; shortcutText: "Ctrl+E"; onTriggered: exportPanel.openPanel() }
                }
            }

            Item { Layout.fillWidth: true }

            // Идёт экспорт, панель свёрнута — процент здесь, клик разворачивает
            Text {
                objectName: "exportBadge"
                visible: session.exportState === "running" && !exportPanel.visible
                text: "Экспорт " + Math.round(session.exportProgress * 100) + "%"
                color: root.accent
                font.pixelSize: 13
                font.weight: Font.DemiBold
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: exportPanel.openPanel()
                }
            }

            Text {
                visible: session.status !== ""
                text: session.proxyProgress >= 0
                      ? session.status + " " + Math.round(session.proxyProgress * 100) + "%"
                      : session.status
                color: root.textDim
                font.pixelSize: 13
            }

            Button {
                id: helpButton
                objectName: "helpButton"
                onClicked: hotkeysPanel.open()
                ToolTip.visible: hovered
                ToolTip.text: "Клавиши и управление (F1)"
                ToolTip.delay: 400
                contentItem: Text {
                    text: "?"
                    color: root.textMain
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    implicitWidth: 34
                    implicitHeight: 34
                    radius: 17
                    color: helpButton.down ? "#2a2a33" : helpButton.hovered ? "#222228" : "transparent"
                    border.color: "#3a3a44"
                }
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 12
            // Холст в кадре чёрный, фон вокруг чуть светлее — видны края холста
            color: "#131317"
            clip: true

            VideoOutput {
                id: video
                anchors.fill: parent
                fillMode: VideoOutput.PreserveAspectFit
                visible: player.hasMedia
                Component.onCompleted: player.videoSink = video.videoSink
            }

            Column {
                anchors.centerIn: parent
                spacing: 8
                visible: !player.hasMedia

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "Перетащи видео сюда"
                    color: root.textMain
                    font.pixelSize: 20
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: "или нажми «Импорт» (Ctrl+I)"
                    color: root.textDim
                    font.pixelSize: 14
                }
            }

            CanvasEditor {
                anchors.fill: parent
                session: root.session
                player: root.player
                canvas: video.contentRect
                visible: player.hasMedia
            }

            Rectangle {
                anchors.fill: parent
                radius: 12
                color: "transparent"
                border.color: root.accent
                border.width: 2
                visible: drop.containsDrag
            }

            DropArea {
                id: drop
                anchors.fill: parent
                onDropped: (event) => {
                    if (event.hasUrls)
                        session.importUrls(event.urls)
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 14
            enabled: player.hasMedia
            opacity: enabled ? 1 : 0.4

            RoundButton {
                id: playButton
                implicitWidth: 44
                implicitHeight: 44
                onClicked: player.togglePlay()
                contentItem: Text {
                    text: player.playing ? "❚❚" : "▶"
                    color: "#0f0f11"
                    font.pixelSize: 16
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    radius: width / 2
                    color: playButton.down ? Qt.darker(root.textMain, 1.3) : root.textMain
                }
            }

            Text {
                text: root.timecode(player.position) + " / " + root.timecode(player.length)
                color: root.textMain
                font.pixelSize: 13
                font.family: "monospace"
            }

            Item { Layout.fillWidth: true }

            Button {
                id: canvasButton
                objectName: "canvasButton"
                onClicked: canvasMenu.open()
                ToolTip.visible: hovered && !canvasMenu.visible
                ToolTip.text: "Соотношение сторон холста"
                ToolTip.delay: 400
                contentItem: Text {
                    text: "Холст: " + (session.canvas === "original" ? "оригинал" : session.canvas) + "  ▾"
                    color: root.textMain
                    font.pixelSize: 13
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    implicitHeight: 34
                    radius: 8
                    color: canvasButton.down || canvasMenu.visible ? "#2a2a33"
                         : canvasButton.hovered ? "#222228" : "transparent"
                    border.color: "#3a3a44"
                }

                Menu {
                    id: canvasMenu
                    objectName: "canvasMenu"
                    x: canvasButton.width - width
                    y: -height - 4
                    padding: 6
                    background: Rectangle {
                        implicitWidth: 260
                        color: root.panel
                        border.color: "#2c2c33"
                        radius: 10
                    }
                    MenuEntry {
                        text: "9:16"; shortcutText: "Shorts, Reels, TikTok"
                        current: session.canvas === "9:16"; onTriggered: session.setCanvas("9:16")
                    }
                    MenuEntry {
                        text: "16:9"; shortcutText: "YouTube"
                        current: session.canvas === "16:9"; onTriggered: session.setCanvas("16:9")
                    }
                    MenuEntry {
                        text: "1:1"; shortcutText: "квадрат"
                        current: session.canvas === "1:1"; onTriggered: session.setCanvas("1:1")
                    }
                    MenuEntry {
                        text: "Оригинал"; shortcutText: "как первое видео"
                        current: session.canvas === "original"; onTriggered: session.setCanvas("original")
                    }
                }
            }
        }

        Timeline {
            objectName: "timeline"
            Layout.fillWidth: true
            player: root.player
            session: root.session
        }
    }
}
