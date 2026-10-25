# chestor_motion

Видеоредактор для Linux с управлением как в CapCut. Цель — шортсы (9:16) и записи экрана,
до 1080p. Целевая машина слабая: Radeon 610M (VA-API), ~7 ГБ RAM, KDE Wayland.

## Стек

- Python 3.14 (системный), интерфейс — PySide6 + QML, движок — MLT 7, ffmpeg для прокси.
- `mlt7` и `PySide6` — системные пакеты (`pacman -S mlt pyside6 rtaudio sox movit`), не pip:
  привязки mlt7 собраны под системный Python. `.venv` создаётся с system-site-packages
  (`poetry.toml`), в нём только dev-инструменты.
- SWIG-привязки `mlt7` неполные: `Frame.get_audio` не вызывается из Python, `listen` ждёт
  указатель на C-функцию. Недостающее — через `ctypes` к `libmlt-7.so`.

## Производительность

- Исходники с переменной частотой кадров (записи экрана) — норма. Монтаж идёт по прокси
  с постоянными 30 fps, экспорт — из оригиналов.
- Масштабирование кадра в MLT дорогое: превью получает кадр в размере профиля,
  уменьшает его QML на видеокарте.
- Всё тяжёлое (декодирование, прокси, превью-картинки, waveform) — не в GUI-потоке.

## Проверки

```bash
poetry install
poetry run ruff check src tests && poetry run ruff format --check src tests
poetry run pyright
poetry run pytest
```

Pre-commit-хук `.githooks/pre-commit` гоняет их же (`git config core.hooksPath .githooks`
после клона).

## Git

- `main` всегда рабочий. Работа — в ветках `feature/<что>`, `fix/<что>`; в `main` вливается
  `git merge --no-ff` с сообщением `merge: <что сделано>`.
- Коммить логичными шагами, каждый коммит проходит проверки. Сообщения — conventional commits
  на английском (`feat(preview): ...`, `fix(proxy): ...`, `chore: ...`, `docs: ...`).
- Медиафайлы (`*.mp4` и т.п.) в git не кладутся; тестовые ролики тесты генерируют сами.
