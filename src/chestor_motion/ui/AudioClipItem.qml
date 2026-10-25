import QtQuick
import ChestorMotion

// Клип звуковой дорожки: форма волны, имя, выделение, ручки подрезки. Тянется по времени и
// между дорожками (ниже последней — новая дорожка). Правый клик — меню клипа.
Item {
    id: item

    required property var clipData
    required property var view  // Timeline
    property bool selected: false
    property var peaks

    // Пока тянешь ручку (см. TrimHandles): левая двигает и начало клипа на таймлайне
    property int trimIn: 0
    property int trimOut: 0
    readonly property int inFrame: clipData.inFrame + trimIn
    readonly property int outFrame: clipData.outFrame + trimOut
    readonly property real px: view.pxPerFrame

    x: view.xAt(clipData.start + trimIn) + (moveArea.dragging ? moveArea.dragX : 0)
    y: view.laneTop(clipData.lane) + (moveArea.dragging ? moveArea.dragY : 0)
    width: Math.max(2, (outFrame - inFrame) * px)
    height: view.laneHeight
    z: moveArea.dragging ? 5 : (selected ? 2 : 1)
    opacity: moveArea.dragging ? 0.85 : 1

    Rectangle {
        id: body
        anchors.fill: parent
        anchors.leftMargin: 1
        anchors.rightMargin: 1
        radius: 6
        color: "#14353a"
        clip: true

        Waveform {
            readonly property real visibleFrom: Math.max(0, item.view.viewX - item.x)
            readonly property real visibleTo: Math.min(item.width, item.view.viewX + item.view.viewWidth - item.x)
            x: visibleFrom
            width: Math.max(0, visibleTo - visibleFrom)
            height: parent.height
            visible: item.peaks !== undefined && width > 0
            peaks: item.peaks ?? new ArrayBuffer(0)
            firstFrame: item.inFrame + visibleFrom / item.px
            pxPerFrame: item.px
            color: "#22d3c5"
        }

        // Имя — на тёмной плашке: поверх яркой волны иначе не читается
        Rectangle {
            x: 5
            y: 4
            width: Math.min(nameText.implicitWidth + 10, parent.width - 10)
            height: nameText.implicitHeight + 2
            radius: 4
            color: "#cc0f2226"
            visible: width > 20

            Text {
                id: nameText
                x: 5
                y: 1
                width: parent.width - 10
                text: "♪ " + item.clipData.name
                color: "#e6fffb"
                font.pixelSize: 11
                elide: Text.ElideRight
            }
        }

        Rectangle {
            anchors.fill: parent
            radius: body.radius
            color: "transparent"
            border.width: item.selected ? 2 : 1
            border.color: item.selected ? "#ffffff" : "#24555c"
        }
    }

    MouseArea {
        id: moveArea
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        property point pressScene
        property real dragX: 0
        property real dragY: 0
        property bool dragging: false
        cursorShape: dragging ? Qt.ClosedHandCursor : Qt.PointingHandCursor

        onPressed: (mouse) => {
            const p = mapToItem(null, mouse.x, mouse.y)
            pressScene = Qt.point(p.x, p.y)
            dragX = 0
            dragY = 0
            item.view.session.select(item.clipData.id)
            item.view.player.seek(item.clipData.start + Math.floor(mouse.x / item.px))
            if (mouse.button === Qt.RightButton)
                item.view.openClipMenu(item.clipData.id, true, false, mapToItem(item.view, mouse.x, mouse.y))
        }
        onPositionChanged: (mouse) => {
            if (!pressed || pressedButtons !== Qt.LeftButton)
                return
            const p = mapToItem(null, mouse.x, mouse.y)
            const dx = p.x - pressScene.x
            const dy = p.y - pressScene.y
            if (!dragging && Math.abs(dx) + Math.abs(dy) > 6)
                dragging = true
            if (dragging) {
                dragX = dx
                dragY = dy
            }
        }
        onReleased: {
            if (!dragging)
                return
            const c = item.clipData
            const start = Math.max(0, c.start + Math.round(dragX / item.px))
            const lane = Math.max(0, c.lane + Math.round(dragY / item.view.laneStep))
            dragging = false
            // Последний вызов: сессия пересоздаёт клипы таймлайна
            item.view.session.moveAudio(c.id, start, lane)
        }
        onCanceled: dragging = false
        onWheel: (wheel) => item.view.wheelAt(wheel, mapToItem(item.view, wheel.x, wheel.y).x)
    }

    TrimHandles {
        clip: item
        hidden: moveArea.dragging
    }
}
