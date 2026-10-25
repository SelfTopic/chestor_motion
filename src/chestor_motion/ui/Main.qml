import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtMultimedia

ApplicationWindow {
    id: root

    required property var player
    required property var session

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

    Shortcut { sequence: "Space"; onActivated: player.togglePlay() }
    Shortcut { sequence: "Left"; onActivated: player.step(-1) }
    Shortcut { sequence: "Right"; onActivated: player.step(1) }
    Shortcut { sequence: "Shift+Left"; onActivated: player.step(-player.fps) }
    Shortcut { sequence: "Shift+Right"; onActivated: player.step(player.fps) }
    Shortcut { sequence: "Home"; onActivated: player.seek(0) }
    Shortcut { sequence: "End"; onActivated: player.seek(player.length - 1) }
    // Импорт — Ctrl+I, как в CapCut; Ctrl+O открывает проект
    Shortcut { sequence: "Ctrl+I"; onActivated: fileDialog.open() }
    Shortcut { sequence: "Ctrl+N"; onActivated: session.newProject() }
    Shortcut { sequence: "Ctrl+O"; onActivated: openProjectDialog.open() }
    Shortcut { sequence: "Ctrl+S"; onActivated: session.save() }
    Shortcut { sequence: "Ctrl+Shift+S"; onActivated: saveAsDialog.open() }
    Shortcut { sequence: "S"; onActivated: session.splitAtPlayhead() }
    Shortcut { sequences: [StandardKey.Delete, "Backspace"]; onActivated: session.deleteSelectedOrAtPlayhead() }
    Shortcut { sequence: "Escape"; onActivated: session.select("") }
    Shortcut { sequence: "Ctrl+Z"; onActivated: session.undo() }
    // Явно, а не StandardKey.Redo: в KDE он уже Ctrl+Shift+Z, и дубль делает сочетание
    // неоднозначным — тогда Qt не вызывает ни один из ярлыков
    Shortcut { sequences: ["Ctrl+Shift+Z", "Ctrl+Y"]; onActivated: session.redo() }

    FileDialog {
        id: fileDialog
        title: "Импорт видео"
        fileMode: FileDialog.OpenFiles
        nameFilters: ["Видео (*.mp4 *.mkv *.mov *.webm *.avi)", "Все файлы (*)"]
        onAccepted: session.importUrls(selectedFiles)
    }

    FileDialog {
        id: openProjectDialog
        title: "Открыть проект"
        nameFilters: ["Проект chestor_motion (*.cmproj)"]
        onAccepted: session.openProject(selectedFile)
    }

    FileDialog {
        id: saveAsDialog
        title: "Сохранить проект как"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "cmproj"
        nameFilters: ["Проект chestor_motion (*.cmproj)"]
        onAccepted: session.saveAs(selectedFile)
    }

    // Встроенный компонент не видит id файла (root) — цвета прямо здесь
    component MenuEntry: MenuItem {
        id: entry
        property string shortcutText: ""
        implicitWidth: 260
        implicitHeight: 34
        contentItem: RowLayout {
            Text {
                text: entry.text
                color: "#f2f2f4"
                font.pixelSize: 14
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
                onClicked: fileDialog.open()
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
                    MenuEntry { text: "Открыть…"; shortcutText: "Ctrl+O"; onTriggered: openProjectDialog.open() }
                    MenuEntry { text: "Сохранить"; shortcutText: "Ctrl+S"; onTriggered: session.save() }
                    MenuEntry { text: "Сохранить как…"; shortcutText: "Ctrl+Shift+S"; onTriggered: saveAsDialog.open() }
                }
            }

            Item { Layout.fillWidth: true }

            Text {
                visible: session.status !== ""
                text: session.proxyProgress >= 0
                      ? session.status + " " + Math.round(session.proxyProgress * 100) + "%"
                      : session.status
                color: root.textDim
                font.pixelSize: 13
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
            color: "#000000"
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
        }

        Timeline {
            objectName: "timeline"
            Layout.fillWidth: true
            player: root.player
            session: root.session
        }
    }
}
