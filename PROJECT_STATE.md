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
- **HUD Quick Switcher (`Ctrl+Shift+K` / `Ctrl+P`)**: глобальный полноэкранный диалог быстрого переключения чатов/тем с фильтрацией (не конфликтует с форматированием ссылок по `Ctrl+K`).
- **Shadow Drafts (`Ctrl+Shift+Z`)**: локальное сохранение редакций текста с поканальным разделением таймстампов и навигацией без отправки на серверы.
- **Инлайн-калькулятор со степенями**: вычисления выражений в поле ввода с поддержкой верхних индексов (`2²=`, `(2)²=`, `2²³=`), конвертации валют и величин.
- **Queue Reply (Ответ в очередь)**: контекстное меню и быстрые действия для отправляемых сообщений.
- **Поиск по числовому ID (`id123...` и `123...`)**: мгновенное нахождение пользователей и каналов в поиске диалогов.
- **3D Значок поддержки и привилегии**: интерактивная 3D-модель значка со звёздами в `tg://support`, разделение контактов (@ExteraOwner для ExteraGram, @radoqi для oxDesktop).
- **Обновлённый tg://welcome**: центрированная кнопка, карточки настроек Liquid Glass и интерактивный просмотр Changelog.
- **Мгновенное обновление трея Windows**: инвалидация кэшей и рендер выбранной иконки приложения в трее без перезапуска.
- **Помощник багрепорта**: минималистичный стеклянный пилл над полем ввода, компактная тех. информация (только клиент и ОС).
- **Авто-цитирование (`quote_reply`)**: интеграция цитирования при ответах в современном `ComposeControls`.
- **Лимит аккаунтов**: строго 5 одновременно подключенных профилей.
- **Встроенный обход TgWsProxy v1.11.4**: кнопка быстрого переключения в `connection_box.cpp` («Встроенный обход (TgWsProxy v1.11.4)») со статусом подключения.

## Тестирование и CI
- Python тест-сьют `tests/test_plugin_full_suite.py`: 56/56 тестов пройдено (100% покрытие реального oxDesktop Python SDK, безопасности, AST анализа и badges.json).
- Устранена ошибка AppStream changelog на Linux CI (Rocky Linux 8) в `Telegram/build/changelog2appstream.py`.
- Полностью исправлены все ошибки сборки: `history_widget.cpp` (eventFilter braces), `extera_welcome.cpp` (FlatLabel & TextTransform), `tray_win.cpp` (Colored map duplicate), `settings_extera.cpp` (QTimer, RoundButtonTextTransform, FlatLabel), `main_window.cpp` (EventFilterResult::Cancel).
- **Windows и Linux сборки завершились 100% SUCCESS** (коммит `10e0dbc`, Windows Run `42190374308`, Linux Run `42190374333`).
- Сформированы и выгружены релизные артефакты:
  - `oxDesktop-windows-x64` (166.41 MB): Inno Setup installer + portable.
  - `oxDesktop-linux-x64` (120.56 MB): Linux x64 bundle.
- Добавлен ручной экшен публикации релизов `.github/workflows/publish-release.yml` (запуск релиза по кнопке с автосборкой артефактов из последних успешных билдов).
- Обновлены монохромные иконки трея (oxDesktop эмблема) и сброс кэша при смене логотипа (`tray_win.cpp`).

### 6. Видео и промо
- Видеоэффекты для промо/TikTok: при тыках накладывать наведение камеры на прицел (crosshair / target zoom punch-in), увеличение зоны клика и появление плашек функций.
