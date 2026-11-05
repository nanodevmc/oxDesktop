# oxDesktop - Project State

## Стек и окружение
- Репозиторий: `nanodevmc/oxDesktop` (ветка `main`).
- Брендинг: `@oxDesktop`, `@oxDesktop_Cl`, `@radoqi`, TikTok: `tiktok.com/@oxDesktop` (категорически без WineSquad).
- Стек: C++20 (Qt 6.5.3 / MSVC / GCC CentOS / Ubuntu), Python 3 (плагины и TgWsProxy Flowseal v1.11.4).

## Выполненные задачи и статус

### 1. Версионирование и синхронизация
- **Единый источник версии (`version.txt`)**: версия задаётся в корневом `version.txt` (`7.3.3`).
- **Синхронизатор (`tools/sync_version.py`)**: автоматически обновляет `Telegram/build/version`, `Telegram/SourceFiles/core/version.h` (`AppVersion`, `AppVersionStr`) и генерирует `version_generated.h` (`APP_VERSION`).
- **Интеграция в CMake и CI**: `CMakeLists.txt` и GitHub Actions (`linux-build.yml`, `windows-build.yml`) автоматически вызывают синхронизацию перед сборкой.
- **Стандарт User-Agent**: все HTTP-запросы клиента приведены к стандарту `"oxDesktop/" APP_VERSION` (`extera_badges.cpp`, `extera_changelog.cpp`, `extera_lyrics.cpp`, `extera_update.cpp`, `requirements_installer.py`).

### 2. GitHub Actions CI
- **Защита кэша компилятора (ccache / sccache)**: добавлена дельта-проверка размера (порог 100 МБ) — если при отмене или сбое текущий кэш меньше восстановленного более чем на 100 МБ, сохранение блокируется (`should_save=false`), предотвращая затирание рабочего кэша.
- **Авто-отмена старых запусков (`concurrency: cancel-in-progress: true`)**: при новом пуше в `main` устаревшие раннеры отменяются без риска потери кэша.
- **Windows MSVC sccache**: переведён на быстрый локальный дисковый кэш `.sccache` через `actions/cache@v4` вместо медленного GHA HTTP backend. Устранены ошибки C3850, C2039 в `history_widget.cpp` и `checkLoaded` в `media_player_instance.cpp`.
- **Linux Docker Cache**: Устранена ошибка `CCACHE_DISABLE=0` (ccache 4.x), включен `CMAKE_BUILD_WITH_INSTALL_RPATH=ON` для генератора Ninja. Кэш компилятора восстанавливается и валидируется. Авто-скриншоты на виртуальном Xvfb сохраняются в артефакты `oxdesktop-screenshots-linux`.
- **macOS Build**: Отключен по решению пользователя.

### 3. 3D Анимированные бэйджи Extera & Support
- Интегрированы Document ID 3D-эмодзи: Developer (`5395339798430919126`), Bughunter (`5416037430513936515`), Helper (`5415603784845926997`), Donor/Supporter (`5413871448441793380`), Trusted (`5420443203671208138`).
- Добавлена поддержка купленных значков (Boosty/донат) и локальный `badges.json`.
- Зарегистрированы ссылки `tg://support` и `tg://settings/support`.

### 4. Стиль и жизненный цикл плашек BETA / NEW
- Оформление: мини-прямоугольник, яркий голубой/неоновый текст (`#38BDF8`), тонкая рамка (`#00D2FF`, 1px), радиус 3.5px, стеклянная подложка.
- Централизованный реестр `Ui::NewBadge::FeatureTag`:
  - `NEW` снимается централизованно при смене версии по команде пользователя.
  - `BETA` снимается после успешного завершения циклов тестирования и проверок.
- Автоматическое позиционирование плашек в `settings_extera.cpp` рядом с кнопками опций.

### 5. Внедрённые функции
- **HUD Quick Switcher (`Ctrl+K`)**: полноэкранный диалог выбора чатов/тем с фильтрацией.
- **Shadow Drafts (`Ctrl+Shift+Z`)**: локальный кольцевой буфер (10 ревизий, 1.5с дебаунс, тост отмены).
- **Smart Ghost Mode**: гранулярный анти-прочит (Каналы, Группы, ЛС) в `data_histories.cpp`.
- **Audio Looper & Clip Exporter**: зацикливание `[A ⇄ B]` и экспорт отрезка в `media_player_instance.cpp`.
- **Pitch-Preserved Time-Stretch**: сохранение естественной тональности через `atempo`.
- **Mini-Player & Gapless**: компактный режим, поверх всех окон, бесшовный переход.
- **Deduplication, Polls in PM, Default Forward, Bug Helper, Queue Reply, TgWsProxy**.

## Тестирование и CI
- Python тест-сьют `tests/test_plugin_full_suite.py`: 28/28 тестов пройдено (100%).
- Текущий рабочий коммит: `36329e8` (Windows run `41964820225`, Linux run `41964820149`). CI отслеживается строго каждые 7 минут. Подготовлены новые возможности: Local Audio Player, Custom Font Picker, Pure AMOLED Black (#000000), Linux ccache.

### 6. Видео и промо
- Видеоэффекты для промо/TikTok: при тыках накладывать наведение камеры на прицел (crosshair / target zoom punch-in), увеличение зоны клика и появление плашек функций.
