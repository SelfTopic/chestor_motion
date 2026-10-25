import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Экспорт (Ctrl+E): настройки → прогресс → «Показать в папке». Во время экспорта панель можно
// свернуть — процент виден в шапке, по клику панель открывается снова.
Popup {
    id: panel

    required property var session
    signal chooseFolder(string current)

    property int shortSide: 1080
    property int fps: 30
    property string quality: "high"
    property string folder: ""
    readonly property string exportState: session.exportState

    readonly property color accent: "#22d3c5"
    readonly property color textMain: "#f2f2f4"
    readonly property color textDim: "#8a8a93"

    function openPanel() {
        if (exportState !== "running") {
            const d = session.exportDefaults
            shortSide = d.shortSide
            fps = d.fps
            quality = d.quality
            folder = d.folder
            nameField.text = d.name
        }
        open()
    }

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(parent ? parent.width - 64 : 560, 560)
    modal: true
    focus: true
    padding: 24
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    Overlay.modal: Rectangle { color: "#99000000" }

    background: Rectangle {
        color: "#1a1a1e"
        radius: 14
        border.color: "#2c2c33"
    }

    // Выбор из нескольких вариантов кнопками-сегментами
    component Segments: Row {
        id: seg
        property var options: []  // [{ value, label }]
        property var value
        signal picked(var value)
        spacing: 6
        Repeater {
            model: seg.options
            delegate: Rectangle {
                required property var modelData
                readonly property bool on: seg.value === modelData.value
                width: label.implicitWidth + 24
                height: 32
                radius: 8
                color: on ? "#22d3c5" : (area.containsMouse ? "#24242b" : "#1f1f25")
                border.color: on ? "#22d3c5" : "#33333b"
                Text {
                    id: label
                    anchors.centerIn: parent
                    text: modelData.label
                    color: parent.on ? "#0f0f11" : "#f2f2f4"
                    font.pixelSize: 13
                    font.weight: parent.on ? Font.DemiBold : Font.Normal
                }
                MouseArea {
                    id: area
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: seg.picked(modelData.value)
                }
            }
        }
    }

    component Caption: Text {
        color: "#8a8a93"
        font.pixelSize: 12
    }

    component PillButton: Button {
        id: pill
        property bool primary: false
        contentItem: Text {
            text: pill.text
            color: pill.primary ? "#0f0f11" : "#f2f2f4"
            font.pixelSize: 14
            font.weight: pill.primary ? Font.DemiBold : Font.Normal
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            implicitWidth: 120
            implicitHeight: 36
            radius: 18
            color: pill.primary ? (pill.down ? "#1aa89d" : "#22d3c5")
                                : (pill.hovered ? "#24242b" : "transparent")
            border.color: pill.primary ? "transparent" : "#3a3a44"
        }
    }

    contentItem: ColumnLayout {
        spacing: 16

        Text {
            text: panel.exportState === "running" ? "Экспорт…" : panel.exportState === "done" ? "Готово"
                : panel.exportState === "failed" ? "Экспорт не удался" : "Экспорт"
            color: panel.textMain
            font.pixelSize: 20
            font.weight: Font.DemiBold
        }

        // --- настройки ---
        ColumnLayout {
            visible: panel.exportState === "idle"
            Layout.fillWidth: true
            spacing: 14

            ColumnLayout {
                spacing: 6
                Caption { text: "Разрешение" }
                Segments {
                    objectName: "exportResolution"
                    options: [{ value: 720, label: "720p" }, { value: 1080, label: "1080p" },
                              { value: 1440, label: "2K" }, { value: 2160, label: "4K" }]
                    value: panel.shortSide
                    onPicked: (v) => panel.shortSide = v
                }
            }
            ColumnLayout {
                spacing: 6
                Caption { text: "Частота кадров" }
                Segments {
                    options: [{ value: 30, label: "30 fps" }, { value: 60, label: "60 fps" }]
                    value: panel.fps
                    onPicked: (v) => panel.fps = v
                }
            }
            ColumnLayout {
                spacing: 6
                Caption { text: "Качество" }
                Segments {
                    options: [{ value: "normal", label: "Обычное" }, { value: "high", label: "Высокое" }]
                    value: panel.quality
                    onPicked: (v) => panel.quality = v
                }
            }
            Text {
                objectName: "exportSummary"
                text: panel.visible ? panel.session.exportSummary(panel.shortSide, panel.fps, panel.quality) : ""
                color: panel.accent
                font.pixelSize: 13
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6
                Caption { text: "Имя файла" }
                TextField {
                    id: nameField
                    objectName: "exportName"
                    Layout.fillWidth: true
                    color: panel.textMain
                    font.pixelSize: 13
                    leftPadding: 12
                    rightPadding: 48
                    background: Rectangle {
                        implicitHeight: 34
                        radius: 8
                        color: "#121215"
                        border.color: nameField.activeFocus ? panel.accent : "#2c2c33"
                    }
                    Text {
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        text: ".mp4"
                        color: panel.textDim
                        font.pixelSize: 13
                    }
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6
                Caption { text: "Папка" }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10
                    Text {
                        Layout.fillWidth: true
                        text: panel.folder
                        color: panel.textMain
                        font.pixelSize: 13
                        elide: Text.ElideMiddle
                    }
                    PillButton {
                        text: "Изменить…"
                        onClicked: panel.chooseFolder(panel.folder)
                    }
                }
            }
        }

        // --- идёт экспорт ---
        ColumnLayout {
            visible: panel.exportState === "running"
            Layout.fillWidth: true
            spacing: 8
            Text {
                Layout.fillWidth: true
                text: panel.session.exportPath
                color: panel.textDim
                font.pixelSize: 12
                elide: Text.ElideMiddle
            }
            Rectangle {
                Layout.fillWidth: true
                height: 8
                radius: 4
                color: "#24242b"
                Rectangle {
                    width: parent.width * panel.session.exportProgress
                    height: parent.height
                    radius: 4
                    color: panel.accent
                }
            }
            Text {
                text: Math.round(panel.session.exportProgress * 100) + "% · можно свернуть и монтировать дальше"
                color: panel.textDim
                font.pixelSize: 12
            }
        }

        // --- результат ---
        Text {
            visible: panel.exportState === "done" || panel.exportState === "failed"
            Layout.fillWidth: true
            text: panel.exportState === "done" ? panel.session.exportPath : panel.session.exportError
            color: panel.exportState === "done" ? panel.textMain : "#ff7b7b"
            font.pixelSize: 13
            wrapMode: Text.WrapAnywhere
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 6
            spacing: 10
            Item { Layout.fillWidth: true }

            PillButton {
                text: panel.exportState === "running" ? "Свернуть" : "Закрыть"
                onClicked: panel.close()
            }
            PillButton {
                visible: panel.exportState === "running"
                text: "Отменить"
                onClicked: panel.session.cancelExport()
            }
            PillButton {
                visible: panel.exportState === "done"
                text: "Показать в папке"
                onClicked: Qt.openUrlExternally(panel.session.folderUrl(panel.session.exportPath))
            }
            PillButton {
                visible: panel.exportState === "done"
                primary: true
                text: "Открыть видео"
                onClicked: Qt.openUrlExternally("file://" + panel.session.exportPath)
            }
            PillButton {
                objectName: "exportStart"
                visible: panel.exportState === "idle" || panel.exportState === "failed"
                primary: true
                text: panel.exportState === "failed" ? "Ещё раз" : "Экспортировать"
                onClicked: {
                    if (panel.exportState === "failed")
                        panel.session.cancelExport()  // сбросить в idle и показать настройки
                    else
                        panel.session.startExport(panel.shortSide, panel.fps, panel.quality,
                                                  panel.folder, nameField.text)
                }
            }
        }
    }

    // После «Готово» следующий экспорт — снова с настроек
    onClosed: if (exportState === "done") session.cancelExport()
}
