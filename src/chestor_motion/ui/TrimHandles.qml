import QtQuick

// Ручки подрезки у выделенного клипа (видео и звука). Пока тянешь — меняются только
// clip.trimIn / clip.trimOut (картинка), модель — один раз при отпускании.
Item {
    id: handles

    required property Item clip  // ClipItem или LaneClipItem
    property bool hidden: false  // например, пока клип перетаскивают

    anchors.fill: parent
    z: 3

    Repeater {
        model: [true, false]  // левая, правая
        delegate: Rectangle {
            id: handle
            required property bool modelData
            readonly property bool isLeft: modelData
            x: isLeft ? 0 : handles.width - width
            width: 10
            height: handles.height
            radius: 3
            color: handleArea.pressed ? handles.clip.view.accent : "#ffffff"
            visible: handles.clip.selected && !handles.hidden

            Rectangle {
                anchors.centerIn: parent
                width: 2
                height: Math.min(18, parent.height - 8)
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
                    const clip = handles.clip
                    const frames = Math.round((mapToItem(null, mouse.x, 0).x - startX) / clip.px)
                    const c = clip.clipData
                    if (handle.isLeft)
                        clip.trimIn = Math.max(-c.inFrame, Math.min(c.outFrame - c.inFrame - 1, frames))
                    else
                        clip.trimOut = Math.max(-(c.outFrame - c.inFrame - 1),
                                                Math.min(c.sourceLength - c.outFrame, frames))
                }
                onReleased: {
                    // Сначала сбросить своё состояние: вызов сессии пересоздаёт клипы таймлайна
                    const clip = handles.clip
                    const c = clip.clipData
                    const session = clip.view.session
                    const trimIn = clip.trimIn
                    const trimOut = clip.trimOut
                    clip.trimIn = 0
                    clip.trimOut = 0
                    if (handle.isLeft && trimIn !== 0)
                        session.trimStart(c.id, c.inFrame + trimIn)
                    else if (!handle.isLeft && trimOut !== 0)
                        session.trimEnd(c.id, c.outFrame + trimOut)
                }
            }
        }
    }
}
