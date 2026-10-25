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
    title: session.title ? session.title + " — chestor_motion" : "chestor_motion"
    color: bg

    Shortcut { sequence: "Space"; onActivated: player.togglePlay() }
    Shortcut { sequence: "Left"; onActivated: player.step(-1) }
    Shortcut { sequence: "Right"; onActivated: player.step(1) }
    Shortcut { sequence: "Shift+Left"; onActivated: player.step(-player.fps) }
    Shortcut { sequence: "Shift+Right"; onActivated: player.step(player.fps) }
    Shortcut { sequence: "Home"; onActivated: player.seek(0) }
    Shortcut { sequence: "End"; onActivated: player.seek(player.length - 1) }
    Shortcut { sequences: [StandardKey.Open]; onActivated: fileDialog.open() }
    Shortcut { sequence: "S"; onActivated: session.splitAtPlayhead() }
    Shortcut { sequences: [StandardKey.Delete, "Backspace"]; onActivated: session.deleteAtPlayhead() }
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

            Text {
                text: session.title
                color: root.textMain
                font.pixelSize: 14
                elide: Text.ElideMiddle
                Layout.fillWidth: true
            }

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
                    text: "или нажми «Импорт» (Ctrl+O)"
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

            Slider {
                id: scrubber
                Layout.fillWidth: true
                from: 0
                to: Math.max(1, player.length - 1)
                stepSize: 1
                value: player.position
                onMoved: player.seek(Math.round(value))

                background: Rectangle {
                    x: scrubber.leftPadding
                    y: scrubber.topPadding + scrubber.availableHeight / 2 - height / 2
                    width: scrubber.availableWidth
                    height: 4
                    radius: 2
                    color: "#2c2c33"

                    Rectangle {
                        width: scrubber.visualPosition * parent.width
                        height: parent.height
                        radius: 2
                        color: root.accent
                    }
                }
                handle: Rectangle {
                    x: scrubber.leftPadding + scrubber.visualPosition * (scrubber.availableWidth - width)
                    y: scrubber.topPadding + scrubber.availableHeight / 2 - height / 2
                    width: 14
                    height: 14
                    radius: 7
                    color: root.textMain
                }
            }
        }
    }
}
