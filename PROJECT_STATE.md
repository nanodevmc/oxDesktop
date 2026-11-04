# oxDesktop - Project State

## Стек и окружение
- Репозиторий: `nanodevmc/oxDesktop` (ветка `main`).
- Брендинг: `@oxDesktop`, `@oxDesktop_Cl`, `@radoqi`, TikTok: `tiktok.com/@oxDesktop` (категорически без WineSquad).
- Стек: C++20 (Qt 6.5.3 / MSVC / GCC CentOS / Ubuntu), Python 3 (плагины и TgWsProxy Flowseal v1.11.4).

## Выполненные задачи и статус

### 1. GitHub Actions CI
- **Windows MSVC**: Устранён каскад ошибок `C2440`/`C3535` в `peer_list_box.cpp:2084` через явные проверки `emojiIconRect()` и `exteraIconRect()`.
- **Linux Docker Cache**: Нативный GitHub Actions Buildx кэш (`type=gha,scope=docker-centos`), устранена инвалидация кэша динамической папкой poetry `.venv`.
- **Авто-скриншоты на Linux**: В `.github/workflows/linux-build.yml` добавлен виртуальный Xvfb фреймбуфер для генерации скриншотов через `--demo-mode`. Скриншоты сохраняются строго в артефакты `oxdesktop-screenshots-linux` (без загрязнения git репозитория).
- **macOS Build**: Отключен по решению пользователя.

### 2. 3D Анимированные бэйджи Extera & Support
- Интегрированы Document ID 3D-эмодзи: Developer (`5395339798430919126`), Bughunter (`5416037430513936515`), Helper (`5415603784845926997`), Donor/Supporter (`5413871448441793380`), Trusted (`5420443203671208138`).
- Добавлена поддержка купленных значков (Boosty/донат) и локальный `badges.json`.
- Зарегистрированы ссылки `tg://support` и `tg://settings/support`.

### 3. Стиль и жизненный цикл плашек BETA / NEW
- Оформление: мини-прямоугольник, яркий голубой/неоновый текст (`#38BDF8`), тонкая рамка (`#00D2FF`, 1px), радиус 3.5px, стеклянная подложка.
- Централизованный реестр `Ui::NewBadge::FeatureTag`:
  - `NEW` снимается централизованно при смене версии по команде пользователя.
  - `BETA` снимается после успешного завершения циклов тестирования и проверок.
- Автоматическое позиционирование плашек в `settings_extera.cpp` рядом с кнопками опций.

### 4. Внедрённые функции
- **CLI Demo Engine (`extera_demo.cpp`)**: параметры `--demo-mode`, `--demo-view`, `--demo-screenshot`, `--demo-delay`, `--demo-exit` для автоматического рендеринга и снимков экранов.
- **Queue Reply (`queue_reply`)**: ответ на отправляемые сообщения с плашкой «Очередь отправки», авто-резолв в `data_histories.cpp` через `itemIdChanged`.
- **Custom Reaction Strip (`static_reactions_enabled`, `static_reactions_list`)**: фиксированная раскладка реакций.
- **Smart Bug Report Helper (`smart_bug_report_helper`)**: анимированная плашка `[ 📎 Вставить тех. информацию ]` над полем ввода при ключевых словах ошибок.
- **Floating Mini-Player**: компактный режим `S(380)` (`mini_player_compact`) и режим поверх окон `Qt::WindowStaysOnTopHint` (`mini_player_always_on_top`).
- **Media Deduplication Cache (`media_deduplication`)**: виртуальный кэш SHA-256 с авто-фоллбэком при устаревании `file_reference`.
- **Polls in PM (`polls_in_pm`)**: создание опросов в личных сообщениях с плашкой BETA.
- **Default Forward Mode (`default_forward_mode`)**: выбор стандартного режима пересылки.
- **Lyrics Quote Card (`lyrics_quote_card`)**: контекстное меню цитирования строк песен с плашкой BETA.
- **Gapless Audio Playback (`gapless_playback`)**: предзагрузка следующего трека за 3 секунды до конца с плашкой BETA.
- **TgWsProxy Flowseal v1.11.4**: отключение перегруженного MLKEM TLS, MTU-защита и вотчдог родительского PID.

## Тестирование
- Тест-сьют плагинов `tests/test_plugin_full_suite.py`: 28/28 тестов пройдено (100% успех).

### 5. Видео и промо
- Видеоэффекты для промо/TikTok: при тыках накладывать наведение камеры на прицел (crosshair / target zoom punch-in), увеличение зоны клика и появление плашек функций.
