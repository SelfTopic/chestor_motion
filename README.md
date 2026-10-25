# chestor_motion

Видеоредактор для Linux с управлением как в CapCut: шортсы и записи экрана, до 1080p.

## Установка (Manjaro / Arch)

```bash
sudo pacman -S --needed mlt pyside6 ffmpeg libva-utils
sudo pacman -S --needed --asdeps sox movit
poetry install
git config core.hooksPath .githooks
poetry run chestor-motion                  # прошлый проект
poetry run chestor-motion video.mp4        # новый проект с этим видео
poetry run chestor-motion project.cmproj   # открыть проект
```

## Клавиши

| Клавиша | Действие |
|---|---|
| Пробел | воспроизведение / пауза |
| ← → / Shift+← → | кадр / секунда |
| S | разрезать под плейхедом |
| Delete | удалить выделенный клип (или под плейхедом) |
| Ctrl+Z / Ctrl+Shift+Z | отменить / повторить |
| Ctrl+I | импорт видео |
| Ctrl+N / Ctrl+O | новый / открыть проект |
| Ctrl+S / Ctrl+Shift+S | сохранить / сохранить как |
| Ctrl+колесо / колесо | масштаб / прокрутка таймлайна |

## Документация

- [План](docs/roadmap.md) — этапы от прототипа до функций уровня CapCut
- [Журнал решений](docs/decisions.md) — почему сделано именно так и что проверяли
