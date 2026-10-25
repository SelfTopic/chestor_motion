# chestor_motion

Видеоредактор для Linux с управлением как в CapCut: шортсы и записи экрана, до 1080p.

## Установка (Manjaro / Arch)

```bash
sudo pacman -S --needed mlt pyside6 ffmpeg libva-utils
sudo pacman -S --needed --asdeps rtaudio sox movit
poetry install
git config core.hooksPath .githooks
poetry run chestor-motion
```
