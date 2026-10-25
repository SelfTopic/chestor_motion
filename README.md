# chestor_motion

Видеоредактор для Linux с управлением как в CapCut: шортсы и записи экрана, до 1080p.

## Установка (Manjaro / Arch)

```bash
sudo pacman -S --needed mlt pyside6 ffmpeg libva-utils
sudo pacman -S --needed --asdeps sox movit
poetry install
git config core.hooksPath .githooks
poetry run chestor-motion
```

## Документация

- [План](docs/roadmap.md) — этапы от прототипа до функций уровня CapCut
- [Журнал решений](docs/decisions.md) — почему сделано именно так и что проверяли
