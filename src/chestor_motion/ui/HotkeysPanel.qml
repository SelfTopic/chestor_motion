import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Справка по управлению (F1 или «?» в шапке). Строится из того же списка, что и сами клавиши.
Popup {
    id: panel

    required property var hotkeys

    readonly property var groups: {
        const order = []
        for (const h of hotkeys)
            if (!order.includes(h.group))
                order.push(h.group)
        return order
    }

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(parent ? parent.width - 64 : 980, 980)
    height: Math.min(parent ? parent.height - 64 : 640, content.implicitHeight + 2 * padding)
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

    contentItem: Flickable {
        id: scroller
        clip: true
        contentHeight: content.implicitHeight
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        ColumnLayout {
            id: content
            width: scroller.width
            spacing: 18

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "Управление"
                    color: "#f2f2f4"
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                }
                Text {
                    text: "Esc — закрыть"
                    color: "#8a8a93"
                    font.pixelSize: 12
                }
            }

            // Группы в две колонки, когда хватает ширины: так всё видно без прокрутки
            GridLayout {
                Layout.fillWidth: true
                columns: content.width > 760 ? 2 : 1
                columnSpacing: 32
                rowSpacing: 18

                Repeater {
                    model: panel.groups
                    delegate: ColumnLayout {
                        required property string modelData
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1  // колонки поровну
                        Layout.alignment: Qt.AlignTop
                        spacing: 6

                        Text {
                            text: modelData
                            color: "#22d3c5"
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            Layout.bottomMargin: 2
                        }

                        Repeater {
                            model: panel.hotkeys.filter(h => h.group === modelData)
                            delegate: RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                spacing: 14

                                // Клавиша — «кнопкой», действие мышью — просто текстом
                                Item {
                                    Layout.preferredWidth: 140
                                    Layout.alignment: Qt.AlignTop
                                    implicitHeight: keyCap.implicitHeight

                                    Rectangle {
                                        id: keyCap
                                        readonly property bool isKey: modelData.keys.length > 0
                                        implicitWidth: keyText.implicitWidth + (isKey ? 16 : 0)
                                        implicitHeight: keyText.implicitHeight + 8
                                        width: implicitWidth
                                        height: implicitHeight
                                        radius: 6
                                        color: isKey ? "#2a2a33" : "transparent"
                                        border.color: isKey ? "#3a3a44" : "transparent"

                                        Text {
                                            id: keyText
                                            anchors.centerIn: parent
                                            text: modelData.label
                                            color: "#f2f2f4"
                                            font.pixelSize: 13
                                            font.family: keyCap.isKey ? "monospace" : Qt.application.font.family
                                        }
                                    }
                                }

                                Text {
                                    text: modelData.text
                                    color: "#c8c8d0"
                                    font.pixelSize: 13
                                    wrapMode: Text.WordWrap
                                    Layout.fillWidth: true
                                    Layout.alignment: Qt.AlignVCenter
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
