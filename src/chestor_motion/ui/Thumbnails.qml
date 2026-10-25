import QtQuick

// Полоса миниатюр клипа: тайлы шириной tileWidth, у каждого — кадр исходника под его серединой.
// Картинки берутся из сетки-спрайта (см. engine/thumbs.py).
Item {
    id: strip

    property var thumbs  // сетка миниатюр исходника или undefined, пока не готова
    property int inFrame: 0  // кадр исходника у левого края
    property real px: 1  // точек на кадр

    clip: true

    Repeater {
        model: strip.thumbs ? Math.ceil(strip.width / strip.thumbs.tileWidth) : 0
        delegate: Item {
            required property int index
            readonly property int frame: strip.inFrame
                + (index + 0.5) * strip.thumbs.tileWidth / strip.px
            readonly property int tile: Math.max(0, Math.min(strip.thumbs.count - 1,
                Math.floor(frame / strip.thumbs.interval)))
            x: index * strip.thumbs.tileWidth
            width: strip.thumbs.tileWidth
            height: strip.height
            clip: true

            Image {
                source: strip.thumbs.url
                x: -(parent.tile % strip.thumbs.columns) * strip.thumbs.tileWidth
                y: -Math.floor(parent.tile / strip.thumbs.columns) * strip.thumbs.tileHeight
                   + (strip.height - strip.thumbs.tileHeight) / 2
                asynchronous: true
                cache: true
                smooth: false
            }
        }
    }
}
