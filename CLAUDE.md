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

## Превью

- Воспроизведение, звук и синхронизацию делает консьюмер MLT `rtaudio`; плеер подписан
  через `ctypes` на `consumer-frame-show`, копирует кадр в RGBA и отдаёт его в `QVideoSink`
  через сигнал с очередью (колбэк приходит из потока MLT).
- Пауза — speed 0, перемотка — seek; после обоих `consumer_purge` + `consumer_refresh`.
- `scrub_audio=0`: с ним буфер упреждения (~25 кадров) на паузе и после конца ролика
  заполняется копиями одного кадра со звуком — петля ~0.8 с, при таскании ползунка
  бесконечная. Звук при перемотке, если понадобится, — отдельной короткой выдачей.
- Звук проверяется объективно: null-sink PipeWire (`pactl load-module module-null-sink`),
  `PIPEWIRE_NODE=<sink>` для процесса, запись `parec -d <sink>.monitor`, поиск петли —
  корреляция сигнала со сдвигом на 1 кадр (1600 сэмплов при 48 кГц/30 fps).
- Объекты MLT освобождаются в порядке консьюмер → источник → профиль.
- SWIG-вызовы mlt7 держат GIL, пока ждут мьютексы MLT, а поток консьюмера держит мьютексы
  и ждёт GIL в колбэке `frame-show` — взаимная блокировка. Поэтому к **работающим**
  консьюмеру и источнику — только функции `mltlib` (ctypes, без GIL): start/stop, seek,
  speed, refresh. SWIG — лишь для настройки до `consumer_start`.
- Тесты не трогают звуковое устройство: `Player("sdl2_audio")` + `SDL_AUDIODRIVER=dummy`.
- На `QT_QPA_PLATFORM=offscreen` `VideoOutput` в `grabWindow()` чёрный, хотя кадры приходят:
  кадр проверяй через `sink.videoFrame().toImage()`, вид окна — на настоящем дисплее.

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
