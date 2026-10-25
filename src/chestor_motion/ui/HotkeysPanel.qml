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

    onOpened: scroller.forceActiveFocus()

    // Затемнение у нижнего края, пока ниже есть ещё
    Rectangle {
        parent: panel.contentItem
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.rightMargin: vbar.visible ? 22 : 0
        anchors.bottom: parent.bottom
        height: 48
        z: 2
        visible: scroller.contentY + scroller.height < scroller.contentHeight - 2
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#001a1a1e" }
            GradientStop { position: 1.0; color: "#ff1a1a1e" }
        }
    }

    // Прокрутка: видимая полоса (в стиле Basic она прозрачна без наведения), затемнение у края,
    // за которым есть ещё, и клавиши
    contentItem: Flickable {
        id: scroller
        objectName: "hotkeysScroller"
        clip: true
        focus: true
        contentHeight: content.implicitHeight
        boundsBehavior: Flickable.StopAtBounds

        function scrollBy(dy) {
            contentY = Math.max(0, Math.min(contentHeight - height, contentY + dy))
        }
        Keys.onUpPressed: scrollBy(-40)
        Keys.onDownPressed: scrollBy(40)
        Keys.onPressed: (event) => {
            if (event.key === Qt.Key_PageDown) scrollBy(height - 60)
            else if (event.key === Qt.Key_PageUp) scrollBy(-(height - 60))
            else if (event.key === Qt.Key_Home) contentY = 0
            else if (event.key === Qt.Key_End) contentY = Math.max(0, contentHeight - height)
            else return
            event.accepted = true
        }

        ScrollBar.vertical: ScrollBar {
            id: vbar
            policy: scroller.contentHeight > scroller.height + 1 ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
            width: 12
            contentItem: Rectangle {
                implicitWidth: 8
                radius: width / 2
                color: vbar.pressed ? "#22d3c5" : (vbar.hovered ? "#7a7a85" : "#55555f")
            }
            background: Rectangle {
                implicitWidth: 8
                radius: width / 2
                color: "#202026"
            }
        }

        ColumnLayout {
            id: content
            width: scroller.width - (vbar.visible ? 22 : 0)  // не залезать под полосу
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
                    text: "↑↓ PgUp PgDn — прокрутка · Esc — закрыть"
                    color: "#8a8a93"
                    font.pixelSize: 12
                }
            }

            // Две просторные колонки; что не влезло по высоте — прокруткой
            GridLayout {
                Layout.fillWidth: true
                columns: content.width > 700 ? 2 : 1
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
