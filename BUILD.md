# Сборка exDesktop / exDesktop Build Guide

## Ускорение сборки: Кэширование объектных файлов (.obj / .o)
В проекте реализована нативная поддержка компиляторного кэша (`sccache` / `ccache`) через параметр CMake `-DDESKTOP_APP_USE_COMPILER_CACHE=ON` для всех поддерживаемых операционных систем (Windows, Linux, macOS).

При повторных сборках компилятор пропускает повторную трансляцию неизменённых единиц трансляции C++, что ускоряет пересборку в **2–5 раз**.

---

### Установка компиляторного кэша

#### Windows
Рекомендуется **sccache** (поддерживает MSVC cl.exe и clang-cl с форматом отладочной информации `/Z7`):
```cmd
:: Через Scoop:
scoop install sccache

:: Или через Cargo (Rust):
cargo install sccache

:: Или через Chocolatey:
choco install sccache
```

#### Linux
```bash
# Ubuntu / Debian
sudo apt-get install ccache
# или установить sccache через cargo:
cargo install sccache

# Arch Linux / Manjaro
sudo pacman -S ccache sccache
```

#### macOS
```bash
brew install sccache ccache
```

---

### Сборка по платформам

#### 1. Windows (`build_win.bat`)
Скрипт автоматически обнаруживает `sccache` или `ccache`, настраивает переменные окружения кэша (`SCCACHE_DIR`, `SCCACHE_CACHE_SIZE=15G`) и конфигурирует CMake:
```cmd
:: Конфигурация CMake с кэшем:
build_win.bat configure out Release

:: Сборка:
build_win.bat build out Release
```

#### 2. Linux (`build_linux.sh`)
```bash
chmod +x build_linux.sh

# Конфигурация:
./build_linux.sh configure

# Сборка:
./build_linux.sh build
```

#### 3. macOS (`build_mac.sh`)
```bash
chmod +x build_mac.sh

# Конфигурация:
./build_mac.sh configure

# Сборка:
./build_mac.sh build
```

---

### Ручная конфигурация CMake
```bash
cmake -B out -DCMAKE_BUILD_TYPE=Release -DDESKTOP_APP_USE_COMPILER_CACHE=ON
cmake --build out --config Release --target Telegram
```
