import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Своё окно выбора файлов: быстрые места, недавние папки, поиск по имени (Ctrl+F).
// mode: "media" — импорт видео и звука (можно несколько), "overlay" — видео наложением,
// "project" — открыть проект, "folder" — выбрать папку (для экспорта).
Popup {
    id: panel

    required property var files  // engine FileBrowser

    property string mode: "media"
    property string folder: ""
    property bool filesOnly: false
    property bool showHidden: false
    property var entries: []
    property var selected: []  // пути
    property int anchorIndex: -1
    property int searchId: 0
    property bool searching: search.text.trim() !== ""
    property bool busy: false
    property var lastFolder: ({})  // последняя папка для каждого режима
    readonly property bool multi: mode === "media" || mode === "overlay"

    signal accepted(var paths)

    readonly property color accent: "#22d3c5"
    readonly property color textMain: "#f2f2f4"
    readonly property color textDim: "#8a8a93"

    function openFor(newMode, startFolder) {
        mode = newMode
        search.text = ""
        selected = []
        const places = files.places
        let start = startFolder || lastFolder[newMode]
        if (!start) {
            const recent = places.find(p => p.kind === "recent")
            const drafts = places.find(p => p.title === "Черновики")
            const videos = places.find(p => p.title === "Видео")
            start = newMode === "project" && drafts ? drafts.path
                  : recent ? recent.path : videos ? videos.path : places[0].path
        }
        goTo(start, false)
        open()
        list.forceActiveFocus()
    }
    function goTo(path, onlyFiles) {
        folder = path
        filesOnly = onlyFiles
        search.text = ""
        refresh()
    }
    function refresh() {
        selected = []
        anchorIndex = -1
        entries = files.listDir(folder, showHidden, mode, filesOnly)
        list.currentIndex = entries.length > 0 ? 0 : -1
    }
    function goUp() {
        if (!searching)
            goTo(files.parentDir(folder), false)
    }
    function isSelected(path) {
        return selected.indexOf(path) >= 0
    }
    function clickEntry(index, modifiers) {
        const path = entries[index].path
        if (entries[index].isDir) {
            selected = []
        } else if ((modifiers & Qt.ShiftModifier) && anchorIndex >= 0 && multi) {
            const lo = Math.min(anchorIndex, index), hi = Math.max(anchorIndex, index)
            selected = entries.slice(lo, hi + 1).filter(e => !e.isDir).map(e => e.path)
        } else if ((modifiers & Qt.ControlModifier) && multi) {
            selected = isSelected(path) ? selected.filter(p => p !== path) : selected.concat([path])
            anchorIndex = index
        } else {
            selected = [path]
            anchorIndex = index
        }
        list.currentIndex = index
    }
    function activate(index) {
        const e = entries[index]
        if (!e)
            return
        if (e.isDir)
            goTo(e.path, false)
        else
            finish(isSelected(e.path) ? selected : [e.path])
    }
    function finish(paths) {
        if (paths.length === 0)
            return
        const from = mode === "folder" ? paths[0] : files.parentDir(paths[0])
        files.remember(from)
        lastFolder[mode] = searching ? folder : from
        close()
        accepted(paths)
    }
    function formatSize(bytes) {
        if (bytes >= 1073741824)
            return (bytes / 1073741824).toFixed(1) + " ГБ"
        return Math.max(0.1, bytes / 1048576).toFixed(1) + " МБ"
    }

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(parent ? parent.width - 48 : 1100, 1100)
    height: Math.min(parent ? parent.height - 48 : 720, 720)
    modal: true
    focus: true
    padding: 20
    // Esc обрабатываем сами: сначала очищает поиск, потом закрывает
    closePolicy: Popup.CloseOnPressOutside

    Overlay.modal: Rectangle { color: "#99000000" }

    background: Rectangle {
        color: "#1a1a1e"
        radius: 14
        border.color: "#2c2c33"
    }

    Shortcut {
        sequence: "Ctrl+F"
        enabled: panel.visible
        onActivated: search.forceActiveFocus()
    }
    Shortcut {
        sequence: "Ctrl+H"
        enabled: panel.visible
        onActivated: {
            panel.showHidden = !panel.showHidden
            panel.refresh()
        }
    }
    Shortcut {
        sequence: "Escape"
        enabled: panel.visible
        onActivated: {
            if (search.text !== "") {
                search.text = ""
                list.forceActiveFocus()
            } else {
                panel.close()
            }
        }
    }

    Connections {
        target: panel.files
        function onSearchResults(id, found, done) {
            if (id !== panel.searchId || !panel.searching)
                return
            panel.entries = found
            panel.busy = false
            list.currentIndex = found.length > 0 ? 0 : -1
        }
    }

    // Поиск запускается, когда перестали печатать
    Timer {
        id: searchDelay
        interval: 250
        onTriggered: {
            if (!panel.searching) {
                panel.files.cancelSearch()
                panel.busy = false
                panel.refresh()
                return
            }
            panel.selected = []
            panel.entries = []
            panel.busy = true
            panel.searchId = panel.files.startSearch(panel.folder, search.text.trim(), panel.mode)
        }
    }

    contentItem: ColumnLayout {
        spacing: 14

        // --- заголовок, поиск, скрытые ---
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Text {
                text: panel.mode === "project" ? "Открыть проект"
                    : panel.mode === "folder" ? "Куда сохранить"
                    : panel.mode === "overlay" ? "Наложение: видео поверх основного" : "Импорт видео и звука"
                color: panel.textMain
                font.pixelSize: 20
                font.weight: Font.DemiBold
            }
            Item { Layout.fillWidth: true }

            TextField {
                id: search
                objectName: "fileSearch"
                Layout.preferredWidth: 320
                placeholderText: "Поиск по имени во всех подпапках (Ctrl+F)"
                placeholderTextColor: panel.textDim
                color: panel.textMain
                font.pixelSize: 13
                leftPadding: 12
                onTextChanged: searchDelay.restart()
                Keys.onDownPressed: list.forceActiveFocus()
                Keys.onReturnPressed: list.forceActiveFocus()
                background: Rectangle {
                    implicitHeight: 34
                    radius: 8
                    color: "#121215"
                    border.color: search.activeFocus ? panel.accent : "#2c2c33"
                }
            }

            Button {
                id: hiddenToggle
                checkable: true
                checked: panel.showHidden
                onToggled: {
                    panel.showHidden = checked
                    panel.refresh()
                }
                ToolTip.visible: hovered
                ToolTip.text: "Показать скрытые папки и файлы (Ctrl+H)"
                contentItem: Text {
                    text: "Скрытые"
                    color: hiddenToggle.checked ? "#0f0f11" : panel.textMain
                    font.pixelSize: 13
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    implicitWidth: 86
                    implicitHeight: 34
                    radius: 8
                    color: hiddenToggle.checked ? panel.accent : (hiddenToggle.hovered ? "#222228" : "transparent")
                    border.color: hiddenToggle.checked ? panel.accent : "#3a3a44"
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 14

            // --- быстрые места ---
            ListView {
                id: placesView
                Layout.preferredWidth: 210
                Layout.fillHeight: true
                clip: true
                model: panel.files.places
                spacing: 2
                section.property: "kind"
                section.delegate: Text {
                    required property string section
                    text: section === "recent" ? "Недавние" : "Места"
                    color: panel.textDim
                    font.pixelSize: 12
                    topPadding: section === "recent" ? 14 : 0
                    bottomPadding: 6
                    leftPadding: 10
                }
                delegate: Rectangle {
                    required property var modelData
                    readonly property bool current: panel.folder === modelData.path
                                                    && panel.filesOnly === modelData.filesOnly
                    width: placesView.width
                    height: 32
                    radius: 8
                    color: current ? "#2a2a33" : placeArea.containsMouse ? "#222228" : "transparent"

                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        x: 10
                        width: parent.width - 20
                        text: modelData.title
                        color: parent.current ? panel.accent : panel.textMain
                        font.pixelSize: 13
                        elide: Text.ElideMiddle
                    }
                    MouseArea {
                        id: placeArea
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            panel.goTo(modelData.path, modelData.filesOnly)
                            list.forceActiveFocus()
                        }
                    }
                    ToolTip.visible: placeArea.containsMouse
                    ToolTip.text: modelData.path
                    ToolTip.delay: 600
                }
            }

            Rectangle {
                Layout.fillHeight: true
                width: 1
                color: "#2c2c33"
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 8

                // --- путь или состояние поиска ---
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Button {
                        id: upButton
                        enabled: !panel.searching
                        onClicked: panel.goUp()
                        ToolTip.visible: hovered
                        ToolTip.text: "На уровень вверх (Backspace)"
                        contentItem: Text {
                            text: "↑"
                            color: upButton.enabled ? panel.textMain : panel.textDim
                            font.pixelSize: 15
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                        background: Rectangle {
                            implicitWidth: 30
                            implicitHeight: 28
                            radius: 6
                            color: upButton.hovered ? "#222228" : "transparent"
                            border.color: "#3a3a44"
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: panel.searching
                              ? (panel.busy ? "Ищу «" + search.text.trim() + "» в " + panel.folder + "…"
                                            : "Найдено: " + panel.entries.length + " в " + panel.folder)
                              : panel.folder + (panel.filesOnly ? "  · только видео" : "")
                        color: panel.textDim
                        font.pixelSize: 12
                        elide: Text.ElideMiddle
                    }
                }

                // --- содержимое папки ---
                ListView {
                    id: list
                    objectName: "fileList"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: panel.entries
                    keyNavigationEnabled: true
                    highlightMoveDuration: 0
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                    Keys.onReturnPressed: panel.activate(currentIndex)
                    Keys.onEnterPressed: panel.activate(currentIndex)
                    Keys.onSpacePressed: if (currentIndex >= 0) panel.clickEntry(currentIndex, Qt.ControlModifier)
                    Keys.onPressed: (event) => {
                        if (event.key === Qt.Key_Backspace) {
                            panel.goUp()
                            event.accepted = true
                        }
                    }
                    onCurrentIndexChanged: {
                        // Стрелками: одиночный выбор следует за курсором
                        const e = panel.entries[currentIndex]
                        if (e && !e.isDir && panel.selected.length <= 1)
                            panel.selected = [e.path]
                    }

                    delegate: Rectangle {
                        id: row
                        required property var modelData
                        required property int index
                        readonly property bool chosen: panel.isSelected(modelData.path)
                        width: list.width
                        height: 40
                        radius: 8
                        color: chosen ? "#22343a" : (ListView.isCurrentItem && list.activeFocus) ? "#24242b"
                             : rowArea.containsMouse ? "#202026" : "transparent"
                        border.color: chosen ? panel.accent : "transparent"

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 12
                            spacing: 12

                            // Значок: папка, видео или проект
                            Rectangle {
                                Layout.preferredWidth: 26
                                Layout.preferredHeight: 18
                                radius: 4
                                color: row.modelData.isDir ? "#2f6fd6" : "#2a2a33"
                                border.color: row.modelData.isDir ? "#4c8cf0" : "#3a3a44"
                                Text {
                                    anchors.centerIn: parent
                                    text: row.modelData.isDir ? "" : panel.mode === "project" ? "◆"
                                        : row.modelData.isAudio ? "♪" : "▶"
                                    color: panel.accent
                                    font.pixelSize: 9
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Text {
                                    Layout.fillWidth: true
                                    text: row.modelData.name
                                    color: row.modelData.hidden ? panel.textDim : panel.textMain
                                    font.pixelSize: 13
                                    elide: Text.ElideMiddle
                                }
                                // В результатах поиска — где лежит файл
                                Text {
                                    Layout.fillWidth: true
                                    visible: panel.searching
                                    text: panel.files.parentDir(row.modelData.path)
                                    color: panel.textDim
                                    font.pixelSize: 11
                                    elide: Text.ElideMiddle
                                }
                            }
                            Text {
                                visible: !row.modelData.isDir
                                text: Qt.formatDateTime(new Date(row.modelData.modified), "dd.MM.yyyy  hh:mm")
                                color: panel.textDim
                                font.pixelSize: 12
                                font.family: "monospace"
                            }
                            Text {
                                visible: !row.modelData.isDir
                                Layout.preferredWidth: 70
                                horizontalAlignment: Text.AlignRight
                                text: panel.formatSize(row.modelData.size)
                                color: panel.textDim
                                font.pixelSize: 12
                            }
                        }

                        MouseArea {
                            id: rowArea
                            anchors.fill: parent
                            hoverEnabled: true
                            onClicked: (mouse) => {
                                panel.clickEntry(row.index, mouse.modifiers)
                                list.forceActiveFocus()
                            }
                            onDoubleClicked: panel.activate(row.index)
                        }
                    }

                    Text {
                        anchors.centerIn: parent
                        visible: panel.entries.length === 0
                        text: panel.busy ? "Ищу…"
                            : panel.searching ? "Ничего не нашлось"
                            : panel.mode === "project" ? "Здесь нет проектов"
                            : panel.mode === "folder" ? "Здесь нет вложенных папок"
                            : panel.mode === "overlay" ? "Здесь нет видео" : "Здесь нет видео и звука"
                        color: panel.textDim
                        font.pixelSize: 13
                    }
                }
            }
        }

        // --- низ: что выбрано и кнопки ---
        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Text {
                text: panel.multi
                      ? "Ctrl/Shift+клик — несколько файлов · двойной клик или Enter — " + "импорт"
                      : panel.mode === "folder" ? "Двойной клик — войти в папку"
                      : "Двойной клик или Enter — открыть"
                color: panel.textDim
                font.pixelSize: 12
            }
            Item { Layout.fillWidth: true }

            Button {
                id: cancelButton
                text: "Отмена"
                onClicked: panel.close()
                contentItem: Text {
                    text: cancelButton.text
                    color: panel.textMain
                    font.pixelSize: 14
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    implicitWidth: 100
                    implicitHeight: 36
                    radius: 18
                    color: cancelButton.hovered ? "#222228" : "transparent"
                    border.color: "#3a3a44"
                }
            }
            Button {
                id: okButton
                objectName: "fileOk"
                enabled: panel.mode === "folder" ? !panel.searching : panel.selected.length > 0
                onClicked: panel.finish(panel.mode === "folder" ? [panel.folder] : panel.selected)
                contentItem: Text {
                    text: panel.mode === "project" ? "Открыть"
                        : panel.mode === "folder" ? "Выбрать эту папку"
                        : panel.mode === "overlay" ? "Наложить"
                        : panel.selected.length > 1 ? "Импортировать (" + panel.selected.length + ")"
                        : "Импортировать"
                    color: "#0f0f11"
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
                background: Rectangle {
                    implicitWidth: 170
                    implicitHeight: 36
                    radius: 18
                    color: okButton.enabled ? (okButton.down ? Qt.darker(panel.accent, 1.2) : panel.accent) : "#2a2a33"
                }
            }
        }
    }
}
