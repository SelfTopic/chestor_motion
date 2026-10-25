import QtQuick

// Правка положения клипа прямо на превью, как в CapCut: клик по картинке — выделить верхний
// клип под мышью (наложение или основной), тянуть — двигать, угловые ручки и колесо — масштаб, двойной щелчок — заполнить
// холст / вписать. Пока тянут, модель не меняется: session.previewTransform двигает картинку,
// а при отпускании session.setTransform записывает одну правку для отмены.
Item {
    id: editor

    required property var session
    required property var player
    // Где на экране холст (VideoOutput.contentRect)
    property rect canvas: Qt.rect(0, 0, 0, 0)

    readonly property color accent: "#22d3c5"
    readonly property real snapPx: 6

    readonly property var frame: session.frame
    readonly property bool hasFrame: frame.id !== undefined && canvas.width > 0
    readonly property bool selected: hasFrame && session.selectedClip === frame.id
    readonly property bool editing: mover.pressed || wheelCommit.running || handleDrag

    // Положение, которое видно: во время правки — своё, иначе из модели
    property real cx: 0
    property real cy: 0
    property real cs: 1
    property bool handleDrag: false
    property bool snappedX: false
    property bool snappedY: false

    function syncFromModel() {
        // frame.id, а не hasFrame: в onFrameChanged привязка hasFrame ещё может быть старой
        if (!editing && frame.id !== undefined) {
            cx = frame.x
            cy = frame.y
            cs = frame.scale
        }
    }
    onFrameChanged: syncFromModel()
    Component.onCompleted: syncFromModel()

    // Рамка в пикселях экрана при масштабе 1 и при текущем
    readonly property real baseW: hasFrame ? frame.width / frame.scale * canvas.width : 0
    readonly property real baseH: hasFrame ? frame.height / frame.scale * canvas.height : 0
    readonly property real boxW: baseW * cs
    readonly property real boxH: baseH * cs
    readonly property real boxX: canvas.x + canvas.width / 2 + cx * canvas.width - boxW / 2
    readonly property real boxY: canvas.y + canvas.height / 2 + cy * canvas.height - boxH / 2

    function inBox(px, py) {
        return px >= boxX && px <= boxX + boxW && py >= boxY && py <= boxY + boxH
    }

    // Верхний клип кадра, чья рамка под точкой (session.frames — сверху вниз)
    function frameAt(px, py) {
        for (const f of session.frames) {
            const l = canvas.x + f.left * canvas.width, t = canvas.y + f.top * canvas.height
            if (px >= l && px <= l + f.width * canvas.width && py >= t && py <= t + f.height * canvas.height)
                return f
        }
        return null
    }

    // Прилипание: к центру холста и к масштабам «вписать» и «заполнить»
    function snapScale(s) {
        s = Math.min(Math.max(s, 0.05), 20)  // как MIN_SCALE…MAX_SCALE в модели
        if (Math.abs(s - 1) * baseW < snapPx)
            return 1
        if (Math.abs(s - frame.fill) * baseW < snapPx)
            return frame.fill
        return s
    }

    function preview() {
        session.previewTransform(frame.id, cx, cy, cs)
    }

    function commit() {
        session.setTransform(frame.id, cx, cy, cs)
    }

    MouseArea {
        id: mover
        anchors.fill: parent
        enabled: editor.hasFrame && !editor.player.playing
        acceptedButtons: Qt.LeftButton
        cursorShape: editor.selected && editor.inBox(mouseX, mouseY) ? Qt.SizeAllCursor : Qt.ArrowCursor
        hoverEnabled: true

        property real pressX: 0
        property real pressY: 0
        property real startX: 0
        property real startY: 0
        property bool moving: false

        onPressed: (mouse) => {
            // Выделенный клип тащится, даже если сверху другой: иначе маленькое наложение
            // нельзя было бы вытащить из-под большого
            const hit = editor.selected && editor.inBox(mouse.x, mouse.y)
                ? editor.frame : editor.frameAt(mouse.x, mouse.y)
            if (!hit) {
                editor.session.select("")
                mouse.accepted = false
                return
            }
            editor.session.select(hit.id)
            // Кнопка уже нажата (editing) — из модели само не подтянется
            editor.cx = hit.x
            editor.cy = hit.y
            editor.cs = hit.scale
            pressX = mouse.x
            pressY = mouse.y
            startX = editor.cx
            startY = editor.cy
            moving = false
        }
        onPositionChanged: (mouse) => {
            if (!pressed)
                return
            if (!moving && Math.abs(mouse.x - pressX) + Math.abs(mouse.y - pressY) < 3)
                return
            moving = true
            let x = startX + (mouse.x - pressX) / editor.canvas.width
            let y = startY + (mouse.y - pressY) / editor.canvas.height
            editor.snappedX = Math.abs(x * editor.canvas.width) < editor.snapPx
            editor.snappedY = Math.abs(y * editor.canvas.height) < editor.snapPx
            editor.cx = editor.snappedX ? 0 : x
            editor.cy = editor.snappedY ? 0 : y
            editor.preview()
        }
        onReleased: {
            editor.snappedX = editor.snappedY = false
            if (moving)
                editor.commit()
            moving = false
        }
        onDoubleClicked: (mouse) => {
            if (editor.inBox(mouse.x, mouse.y))
                editor.session.fitClip(editor.frame.id, "toggle")
        }
        onWheel: (wheel) => {
            if (!editor.selected) {
                wheel.accepted = false
                return
            }
            editor.cs = editor.snapScale(editor.cs * Math.pow(1.1, wheel.angleDelta.y / 120))
            editor.preview()
            wheelCommit.restart()
        }
    }

    // Колесо крутят щелчками — в историю одна правка, когда перестали
    Timer {
        id: wheelCommit
        interval: 400
        onTriggered: editor.commit()
    }

    // Направляющие по центру холста при прилипании
    Rectangle {
        visible: editor.snappedX
        x: editor.canvas.x + editor.canvas.width / 2
        y: editor.canvas.y
        width: 1
        height: editor.canvas.height
        color: editor.accent
    }
    Rectangle {
        visible: editor.snappedY
        x: editor.canvas.x
        y: editor.canvas.y + editor.canvas.height / 2
        width: editor.canvas.width
        height: 1
        color: editor.accent
    }

    Rectangle {
        objectName: "frameBox"
        visible: editor.selected && !editor.player.playing
        x: editor.boxX
        y: editor.boxY
        width: editor.boxW
        height: editor.boxH
        color: "transparent"
        border.color: editor.accent
        border.width: 2

        Repeater {
            model: [[0, 0], [1, 0], [0, 1], [1, 1]]
            delegate: Rectangle {
                id: handle
                required property var modelData
                width: 14
                height: 14
                radius: 7
                x: modelData[0] * parent.width - width / 2
                y: modelData[1] * parent.height - height / 2
                color: "#ffffff"
                border.color: editor.accent
                border.width: 2

                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -6
                    cursorShape: handle.modelData[0] === handle.modelData[1]
                                 ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor
                    property real startDist: 1
                    property real startScale: 1

                    // Масштаб вокруг центра: во сколько раз дальше от центра ушла мышь
                    function dist(mouse) {
                        const p = mapToItem(editor, mouse.x, mouse.y)
                        return Math.hypot(p.x - (editor.boxX + editor.boxW / 2),
                                          p.y - (editor.boxY + editor.boxH / 2))
                    }
                    onPressed: (mouse) => {
                        editor.handleDrag = true
                        startDist = Math.max(1, dist(mouse))
                        startScale = editor.cs
                    }
                    onPositionChanged: (mouse) => {
                        if (!pressed)
                            return
                        editor.cs = editor.snapScale(startScale * dist(mouse) / startDist)
                        editor.preview()
                    }
                    onReleased: {
                        editor.handleDrag = false
                        editor.commit()
                    }
                }
            }
        }
    }
}
