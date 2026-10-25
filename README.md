[![exDesktop: put a star on GitHub](docs/banner.png)](https://github.com/metawka/exDesktop/stargazers)

<img src="docs/logo.png" width="150" align="left"/>

## exDesktop
*[Licensed under the GNU General Public License v3.0](LICENSE)*

An unofficial Windows client built from the official [Telegram Desktop](https://github.com/telegramdesktop/tdesktop) sources. It adds a customizable settings suite, channel feed, streamer tools and a Python plugin engine.

[![Channel](https://img.shields.io/badge/Channel-Telegram-blue.svg)](https://t.me/exDesktop)
[![Website](https://img.shields.io/badge/Website-exteradesktop.xyz-blue.svg)](https://exteradesktop.xyz)
[![Developer](https://img.shields.io/badge/Developer-@metawka-blue.svg)](https://t.me/metawka)

![exDesktop settings](docs/screenshots/main.png)

## Features
- Settings for General, Appearance, Chats, Navigation, Plugins and Other.
- Material Design 3 controls, adjustable avatar corners and 33 application icons.
- Channel feed, wide posts, precise timestamps, edit marks and forward counts.
- Streamer mode with per chat settings, exceptions and screen capture protection.
- Update notifications when a new GitHub release is available.
- Python plugin engine with per plugin settings and automatic safe mode after crashes.
- Gemini chat with your own API key.
- User IDs, data center and estimated registration date in profiles.

![Plugin manager](docs/screenshots/plugins.png)

## Downloads
Get the installer or portable archive from the [releases page](https://github.com/metawka/exDesktop/releases). Both packages include the `python` folder needed by plugins. The client installs beside Telegram Desktop and keeps its data separate.

## API credentials
Get your own API ID and hash from [Telegram's API credentials page](https://core.telegram.org/api/obtaining_api_id). Pass them to the configure script when generating the project files:

```
python configure.py x64 -D TDESKTOP_API_ID=123456 -D TDESKTOP_API_HASH=abcdef0123456789abcdef0123456789
```

## Build on Windows
1. Follow the [Telegram Desktop Windows build guide](https://github.com/telegramdesktop/tdesktop/blob/dev/docs/building-win.md).
2. Put the embedded Python 3.11 runtime in `Libraries/win64/python311`. Include the headers, `python311.lib` and the `embed` folder.
3. Generate the project files with your API ID and hash using the command above.
4. Build the `Telegram` target:

```
cmake --build out --config Release --target Telegram
```

The `python` folder next to `Telegram.exe` is required for plugins.

## Localization
Most strings follow Telegram Desktop translations. exDesktop specific strings are available in English and Russian.

## Thanks
- [Telegram Desktop](https://github.com/telegramdesktop/tdesktop)
- [AyuGram Desktop](https://github.com/AyuGram/AyuGramDesktop)
