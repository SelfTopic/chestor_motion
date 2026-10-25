import QtQuick
import ChestorMotion

// Клип свободной дорожки: звук (форма волны) или наложение (миниатюры). Тянется по времени и
// между дорожками своей группы; за крайнюю — новая дорожка. Правый клик — меню клипа.
// Звуковые дорожки идут вниз от основной, наложения — вверх: у наложений «дальше» — выше.
Item {
    id: item

    required property var clipData
    required property var view  // Timeline
    property bool overlay: false
    property bool selected: false
    property var peaks
    property var thumbs

    // Пока тянешь ручку (см. TrimHandles): левая двигает и начало клипа на таймлайне
    property int trimIn: 0
    property int trimOut: 0
    readonly property int inFrame: clipData.inFrame + trimIn
    readonly property int outFrame: clipData.outFrame + trimOut
    readonly property real px: view.pxPerFrame

    x: view.xAt(clipData.start + trimIn) + (moveArea.dragging ? moveArea.dragX : 0)
    y: (overlay ? view.overlayTop(clipData.lane) : view.laneTop(clipData.lane))
       + (moveArea.dragging ? moveArea.dragY : 0)
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
        color: item.overlay ? "#2a2433" : "#14353a"
        clip: true

        Thumbnails {
            anchors.fill: parent
            visible: item.overlay
            thumbs: item.thumbs
            inFrame: item.inFrame
            px: item.px
        }

        Waveform {
            readonly property real visibleFrom: Math.max(0, item.view.viewX - item.x)
            readonly property real visibleTo: Math.min(item.width, item.view.viewX + item.view.viewWidth - item.x)
            x: visibleFrom
            width: Math.max(0, visibleTo - visibleFrom)
            height: parent.height
            visible: !item.overlay && item.peaks !== undefined && width > 0
            peaks: item.peaks ?? new ArrayBuffer(0)
            firstFrame: item.inFrame + visibleFrom / item.px
            pxPerFrame: item.px
            color: "#22d3c5"
        }

        // Имя — на тёмной плашке: поверх яркой волны и миниатюр иначе не читается
        Rectangle {
            x: 5
            y: 4
            width: Math.min(nameText.implicitWidth + 10, parent.width - 10)
            height: nameText.implicitHeight + 2
            radius: 4
            color: item.overlay ? "#cc1b1626" : "#cc0f2226"
            visible: width > 20

            Text {
                id: nameText
                x: 5
                y: 1
                width: parent.width - 10
                text: (item.overlay ? "▣ " : "♪ ") + item.clipData.name
                      + (item.overlay && !item.clipData.audio ? " · без звука" : "")
                color: item.overlay ? "#f0e8ff" : "#e6fffb"
                font.pixelSize: 11
                elide: Text.ElideRight
            }
        }

        Rectangle {
            anchors.fill: parent
            radius: body.radius
            color: "transparent"
            border.width: item.selected ? 2 : 1
            border.color: item.selected ? "#ffffff" : item.overlay ? "#5b4a78" : "#24555c"
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
                item.view.openClipMenu(item.clipData.id, !item.overlay,
                                       item.overlay && item.clipData.audio,
                                       mapToItem(item.view, mouse.x, mouse.y))
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
            const steps = Math.round(dragY / item.view.laneStep)
            const lane = Math.max(0, c.lane + (item.overlay ? -steps : steps))
            dragging = false
            // Последний вызов: сессия пересоздаёт клипы таймлайна
            item.view.session.moveFree(c.id, start, lane)
        }
        onCanceled: dragging = false
        onWheel: (wheel) => item.view.wheelAt(wheel, mapToItem(item.view, wheel.x, wheel.y).x)
    }

    TrimHandles {
        clip: item
        hidden: moveArea.dragging
    }
}
