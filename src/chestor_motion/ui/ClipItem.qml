import QtQuick
import ChestorMotion

// Клип на основной дорожке: миниатюры, выделение, ручки подрезки, перетаскивание.
Item {
    id: item

    required property var clipData
    required property var view  // Timeline
    property bool selected: false
    property var thumbs  // сетка миниатюр исходника или undefined, пока не готова
    property var peaks  // пики громкости исходника (байт на кадр) или undefined
    readonly property int waveHeight: 22

    signal dragStateChanged(bool active)

    // Пока тянешь ручку — на сколько кадров сдвинуты начало и конец (модель ещё не тронута)
    property int trimIn: 0
    property int trimOut: 0
    readonly property int inFrame: clipData.inFrame + trimIn
    readonly property int outFrame: clipData.outFrame + trimOut
    readonly property real px: view.pxPerFrame

    x: view.xAt(clipData.start) + (moveArea.dragging ? moveArea.dragOffset : 0)
    width: Math.max(2, (outFrame - inFrame) * px)
    z: moveArea.dragging ? 5 : (selected ? 2 : 1)
    opacity: moveArea.dragging ? 0.85 : 1

    Rectangle {
        id: body
        anchors.fill: parent
        anchors.leftMargin: 1
        anchors.rightMargin: 1
        radius: 6
        color: "#2a2a33"
        clip: true

        // Миниатюры: тайлы шириной tileWidth, у каждого — кадр исходника под его серединой
        Item {
            id: thumbArea
            width: body.width
            height: body.height - item.waveHeight
            clip: true

            Repeater {
                model: item.thumbs ? Math.ceil(body.width / item.thumbs.tileWidth) : 0
                delegate: Item {
                    required property int index
                    readonly property int frame: item.inFrame
                        + (index + 0.5) * item.thumbs.tileWidth / item.px
                    readonly property int tile: Math.max(0, Math.min(item.thumbs.count - 1,
                        Math.floor(frame / item.thumbs.interval)))
                    x: index * item.thumbs.tileWidth
                    width: item.thumbs.tileWidth
                    height: thumbArea.height
                    clip: true

                    Image {
                        source: item.thumbs.url
                        x: -(parent.tile % item.thumbs.columns) * item.thumbs.tileWidth
                        y: -Math.floor(parent.tile / item.thumbs.columns) * item.thumbs.tileHeight
                           + (thumbArea.height - item.thumbs.tileHeight) / 2
                        asynchronous: true
                        cache: true
                        smooth: false
                    }
                }
            }
        }

        // Звук: полоска под миниатюрами. Рисуется только видимая часть клипа
        Rectangle {
            y: thumbArea.height
            width: body.width
            height: item.waveHeight
            color: "#16262a"

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
        }

        Rectangle {
            anchors.fill: parent
            radius: body.radius
            color: "transparent"
            border.width: item.selected ? 2 : 1
            border.color: item.selected ? "#ffffff" : "#3a3a44"
        }
    }

    // Тело клипа: клик — выделить и перемотать, протяжка — переставить.
    // Смещение считается в координатах окна: клип сам едет за мышью, и в его собственных
    // координатах мышь почти не двигается.
    MouseArea {
        id: moveArea
        anchors.fill: parent
        property real pressSceneX: 0
        property real dragOffset: 0
        property bool dragging: false
        cursorShape: dragging ? Qt.ClosedHandCursor : Qt.PointingHandCursor

        onPressed: (mouse) => {
            pressSceneX = mapToItem(null, mouse.x, 0).x
            dragOffset = 0
            item.view.session.select(item.clipData.id)
            item.view.player.seek(item.clipData.start + Math.floor(mouse.x / item.px))
        }
        onPositionChanged: (mouse) => {
            if (!pressed)
                return
            const offset = mapToItem(null, mouse.x, 0).x - pressSceneX
            if (!dragging && Math.abs(offset) > 6) {
                dragging = true
                item.dragStateChanged(true)
            }
            if (dragging)
                dragOffset = offset
        }
        onReleased: {
            if (!dragging)
                return
            const center = item.x + item.width / 2
            dragging = false
            item.dragStateChanged(false)
            item.dropAt(center)
        }
        onCanceled: {
            dragging = false
            dragOffset = 0
            item.dragStateChanged(false)
        }
        onWheel: (wheel) => item.view.wheelAt(wheel, mapToItem(item.view, wheel.x, wheel.y).x)
    }

    // Куда встанет клип: индекс по центрам остальных клипов. Последний вызов — после него
    // таймлайн пересоздаёт клипы, и этот объект может уже не существовать.
    function dropAt(centerX) {
        let index = 0
        for (const c of item.view.session.clips) {
            if (c.id === item.clipData.id)
                continue
            if (centerX > item.view.xAt(c.start + c.length / 2))
                index++
        }
        moveArea.dragOffset = 0
        item.view.session.moveClip(item.clipData.id, index)
    }

    // --- ручки подрезки у выделенного клипа ---
    Repeater {
        model: [true, false]  // левая, правая
        delegate: Rectangle {
            id: handle
            required property bool modelData
            readonly property bool isLeft: modelData
            x: isLeft ? 0 : item.width - width
            width: 10
            height: item.height
            radius: 3
            color: handleArea.pressed ? item.view.accent : "#ffffff"
            visible: item.selected && !moveArea.dragging
            z: 3

            Rectangle {
                anchors.centerIn: parent
                width: 2
                height: 18
                radius: 1
                color: "#141417"
            }

            MouseArea {
                id: handleArea
                anchors.fill: parent
                anchors.margins: -4
                cursorShape: Qt.SizeHorCursor
                property real startX: 0
                onPressed: (mouse) => startX = mapToItem(null, mouse.x, 0).x
                onPositionChanged: (mouse) => {
                    if (!pressed)
                        return
                    const frames = Math.round((mapToItem(null, mouse.x, 0).x - startX) / item.px)
                    const c = item.clipData
                    if (handle.isLeft)
                        item.trimIn = Math.max(-c.inFrame, Math.min(c.outFrame - c.inFrame - 1, frames))
                    else
                        item.trimOut = Math.max(-(c.outFrame - c.inFrame - 1),
                                                Math.min(c.sourceLength - c.outFrame, frames))
                }
                onReleased: {
                    // Сначала сбросить своё состояние: вызов сессии пересоздаёт клипы таймлайна
                    const c = item.clipData
                    const session = item.view.session
                    const trimIn = item.trimIn
                    const trimOut = item.trimOut
                    item.trimIn = 0
                    item.trimOut = 0
                    if (handle.isLeft && trimIn !== 0)
                        session.trimStart(c.id, c.inFrame + trimIn)
                    else if (!handle.isLeft && trimOut !== 0)
                        session.trimEnd(c.id, c.outFrame + trimOut)
                }
            }
        }
    }
}
