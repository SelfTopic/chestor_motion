import QtQuick
import QtQuick.Controls

// Таймлайн: линейка, основная дорожка с клипами и плейхед.
// Правки мышью применяются к модели только при отпускании кнопки — граф MLT не пересобирается
// на каждое движение. Пока тянешь, меняется только картинка.
Rectangle {
    id: timeline

    required property var player
    required property var session

    readonly property color accent: "#22d3c5"
    readonly property color textDim: "#8a8a93"
    readonly property int pad: 16
    readonly property int rulerHeight: 26
    readonly property int trackTop: rulerHeight + 10
    readonly property int trackHeight: 84  // миниатюры + полоска звука
    // Звуковые дорожки под основной
    readonly property int laneHeight: 44
    readonly property int laneStep: laneHeight + 6
    readonly property int laneCount: session.audioLanes.length
    readonly property int lanesTop: trackTop + trackHeight + 10
    function laneTop(lane) {
        return lanesTop + lane * laneStep
    }

    // Масштаб: точек на кадр. Ctrl+колесо меняет его вокруг курсора.
    property real pxPerFrame: 1
    readonly property real minPx: Math.max(0.02, (flick.width - 2 * pad) / Math.max(1, player.length))
    readonly property real maxPx: 24
    // Пока масштаб не меняли руками, таймлайн показывает весь проект целиком
    property bool userZoomed: false
    // Видимая часть таймлайна в его координатах: клип рисует звук только в ней
    readonly property real viewX: flick.contentX
    readonly property real viewWidth: flick.width

    function frameAt(x) {
        return Math.max(0, Math.min(player.length - 1, Math.round((x - pad) / pxPerFrame)))
    }
    function xAt(frame) {
        return pad + frame * pxPerFrame
    }
    function zoomAround(factor, viewX) {
        const frame = (flick.contentX + viewX - pad) / pxPerFrame
        userZoomed = true
        pxPerFrame = Math.max(minPx, Math.min(maxPx, pxPerFrame * factor))
        flick.contentX = Math.max(0, Math.min(flick.contentWidth - flick.width,
                                              pad + frame * pxPerFrame - viewX))
    }
    // Колесо: Ctrl — масштаб вокруг курсора, иначе прокрутка. Вызывают MouseArea таймлайна:
    // они принимают колесо сами, и до обработчика снаружи оно не доходит.
    function wheelAt(wheel, viewX) {
        const delta = wheel.angleDelta.y !== 0 ? wheel.angleDelta.y : wheel.angleDelta.x
        if (wheel.modifiers & Qt.ControlModifier)
            zoomAround(delta > 0 ? 1.25 : 0.8, viewX)
        else
            flick.contentX = Math.max(0, Math.min(flick.contentWidth - flick.width, flick.contentX - delta))
        wheel.accepted = true
    }
    function fit() {
        pxPerFrame = minPx
        flick.contentX = 0
    }
    function timecode(frames) {
        const total = Math.floor(frames / player.fps)
        return String(Math.floor(total / 60)).padStart(2, "0") + ":" + String(total % 60).padStart(2, "0")
    }

    color: "#141417"
    radius: 12
    // Снизу — место под ползунок прокрутки
    implicitHeight: lanesTop + laneCount * laneStep + 16

    onWidthChanged: if (!userZoomed) fit()

    // Подгонка под весь проект — только при импорте: после подрезки или удаления масштаб
    // не меняется, иначе клипы прыгают под мышью
    Connections {
        target: timeline.session
        function onImported() {
            if (!timeline.userZoomed)
                timeline.fit()
        }
    }

    Connections {
        target: timeline.player
        function onMediaChanged() {
            if (timeline.player.length === 0)
                timeline.userZoomed = false
        }
        // Во время воспроизведения таймлайн едет за плейхедом
        function onPositionChanged() {
            if (!timeline.player.playing || dragging.active)
                return
            const x = timeline.xAt(timeline.player.position)
            if (x > flick.contentX + flick.width - 40 || x < flick.contentX)
                flick.contentX = Math.max(0, Math.min(flick.contentWidth - flick.width, x - 40))
        }
    }

    QtObject {
        id: dragging
        property bool active: false
    }

    Text {
        anchors.centerIn: parent
        visible: timeline.player.length === 0
        text: "Здесь появятся клипы"
        color: timeline.textDim
        font.pixelSize: 13
    }

    Flickable {
        id: flick
        anchors.fill: parent
        clip: true
        visible: timeline.player.length > 0
        contentWidth: Math.max(width, timeline.xAt(timeline.player.length) + timeline.pad)
        contentHeight: height
        interactive: false
        boundsBehavior: Flickable.StopAtBounds

        // Ползунок прокрутки: виден всегда, когда проект не помещается целиком. В стиле Basic
        // он по умолчанию прозрачный, пока не наведёшь мышь, — поэтому свой вид.
        ScrollBar.horizontal: ScrollBar {
            id: hbar
            objectName: "timelineScrollBar"
            policy: flick.contentWidth > flick.width + 1 ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
            height: 12
            leftPadding: timeline.pad
            rightPadding: timeline.pad
            topPadding: 2
            bottomPadding: 2
            background: Rectangle {
                x: hbar.leftPadding
                width: hbar.availableWidth
                y: hbar.topPadding
                height: hbar.availableHeight
                radius: height / 2
                color: "#202026"
            }
            contentItem: Rectangle {
                implicitHeight: 8
                radius: height / 2
                color: hbar.pressed ? timeline.accent : (hbar.hovered ? "#7a7a85" : "#55555f")
            }
        }

        // Клик и протяжка по пустому месту и линейке — перемотка
        MouseArea {
            width: flick.contentWidth
            height: flick.height
            onPressed: (mouse) => {
                timeline.session.select("")
                timeline.player.seek(timeline.frameAt(mouse.x))
            }
            onPositionChanged: (mouse) => {
                if (pressed)
                    timeline.player.seek(timeline.frameAt(mouse.x))
            }
            onWheel: (wheel) => timeline.wheelAt(wheel, mapToItem(timeline, wheel.x, wheel.y).x)
        }

        // --- линейка ---
        Item {
            id: ruler
            width: flick.contentWidth
            height: timeline.rulerHeight

            // Шаг меток подбирается так, чтобы между ними было не меньше 80 точек
            readonly property int stepFrames: {
                const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
                for (const s of steps)
                    if (s * timeline.player.fps * timeline.pxPerFrame >= 80)
                        return s * timeline.player.fps
                return 600 * timeline.player.fps
            }

            Repeater {
                model: Math.floor(timeline.player.length / ruler.stepFrames) + 1
                delegate: Item {
                    required property int index
                    x: timeline.xAt(index * ruler.stepFrames)
                    height: ruler.height

                    Rectangle {
                        y: ruler.height - 6
                        width: 1
                        height: 6
                        color: timeline.textDim
                    }
                    Text {
                        x: 4
                        y: 4
                        text: timeline.timecode(index * ruler.stepFrames)
                        color: timeline.textDim
                        font.pixelSize: 11
                        font.family: "monospace"
                    }
                }
            }
        }

        // --- основная дорожка ---
        Repeater {
            model: timeline.session.clips
            delegate: ClipItem {
                required property var modelData
                clipData: modelData
                view: timeline
                y: timeline.trackTop
                height: timeline.trackHeight
                selected: timeline.session.selectedClip === modelData.id
                thumbs: timeline.session.thumbs[modelData.source]
                peaks: timeline.session.waves[modelData.source]
                onDragStateChanged: (active) => dragging.active = active
            }
        }

        // --- звуковые дорожки ---
        Repeater {
            model: timeline.laneCount
            delegate: Rectangle {
                required property int index
                x: 0
                y: timeline.laneTop(index) - 2
                width: flick.contentWidth
                height: timeline.laneHeight + 4
                color: "#17171b"
            }
        }
        Repeater {
            model: timeline.session.audioClips
            delegate: AudioClipItem {
                required property var modelData
                clipData: modelData
                view: timeline
                selected: timeline.session.selectedClip === modelData.id
                peaks: timeline.session.waves[modelData.source]
            }
        }

        // --- плейхед ---
        Item {
            id: playhead
            x: timeline.xAt(timeline.player.position) - width / 2
            width: 14
            height: flick.height
            z: 10

            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 4
                width: 2
                height: parent.height - 8
                color: "#ffffff"
            }
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 2
                width: 12
                height: 12
                radius: 3
                color: "#ffffff"
            }
            // Хватать плейхед — только за головку на линейке: линия через дорожку для мыши
            // прозрачна, иначе после клика по клипу (плейхед встаёт под курсор) повторное
            // нажатие хватало плейхед вместо клипа
            MouseArea {
                x: -4
                width: parent.width + 8
                height: timeline.rulerHeight
                cursorShape: Qt.SizeHorCursor
                onPositionChanged: (mouse) => {
                    if (pressed)
                        timeline.player.seek(timeline.frameAt(mapToItem(ruler, mouse.x, 0).x))
                }
            }
        }
    }

    // --- меню клипа по правому клику ---
    function openClipMenu(clipId, isAudio, hasOwnSound, at) {
        clipMenu.clipId = clipId
        clipMenu.isAudio = isAudio
        clipMenu.hasOwnSound = hasOwnSound
        clipMenu.popup(at.x, at.y)
    }

    Menu {
        id: clipMenu
        objectName: "clipMenu"
        property string clipId: ""
        property bool isAudio: false
        property bool hasOwnSound: false
        padding: 6
        background: Rectangle {
            implicitWidth: 230
            color: "#1a1a1e"
            border.color: "#2c2c33"
            radius: 10
        }
        ClipMenuEntry { text: "Разрезать"; shortcutText: "S"; onTriggered: timeline.session.splitAtPlayhead() }
        ClipMenuEntry {
            text: "Отделить звук"
            shortcutText: "D"
            visible: !clipMenu.isAudio && clipMenu.hasOwnSound
            height: visible ? implicitHeight : 0
            onTriggered: timeline.session.detachAudio()
        }
        ClipMenuEntry { text: "Удалить"; shortcutText: "Delete"; onTriggered: timeline.session.deleteSelectedOrAtPlayhead() }
    }

    component ClipMenuEntry: MenuItem {
        id: entry
        property string shortcutText: ""
        implicitWidth: 230
        implicitHeight: 32
        contentItem: Item {
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: entry.text
                color: "#f2f2f4"
                font.pixelSize: 13
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                anchors.right: parent.right
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
}
