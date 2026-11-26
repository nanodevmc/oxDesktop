#!/bin/sh
set -eu

# Usage:
#   curl -fsSL https://raw.githubusercontent.com/nanodevmc/oxDesktop/main/install.sh | sh

REPO="nanodevmc/oxDesktop"
PREFIX=""
FORCE_YES=1
PORTABLE=0
SILENT=0

# Parse optional arguments
for arg in "$@"; do
	case "$arg" in
		--prefix=*) PREFIX="${arg#--prefix=}" ;;
		--portable) PORTABLE=1 ;;
		--quiet|-q) SILENT=1 ;;
		-h|--help)
			echo "oxDesktop Universal Installer"
			echo "Usage: install.sh [--prefix=DIR] [--portable] [--quiet]"
			exit 0
			;;
		*) ;;
	esac
done

# Language auto-detection
case "${LANG:-}${LC_ALL:-}" in
	*ru*|*RU*) RU=1 ;;
	*) RU=0 ;;
esac

# Colorized output helpers (disabled in pipes or non-tty)
if [ -t 1 ] && [ "$SILENT" = 0 ]; then
	C_BOLD="\033[1m"
	C_GREEN="\033[32m"
	C_CYAN="\033[36m"
	C_FLAME="\033[38;2;224;58;27m"
	C_RESET="\033[0m"
else
	C_BOLD=""
	C_GREEN=""
	C_CYAN=""
	C_FLAME=""
	C_RESET=""
fi

log_info() {
	if [ "$SILENT" = 0 ]; then
		if [ "$RU" = 1 ]; then
			printf "${C_FLAME}✦${C_RESET} ${C_BOLD}%s${C_RESET}\n" "$2"
		else
			printf "${C_FLAME}✦${C_RESET} ${C_BOLD}%s${C_RESET}\n" "$1"
		fi
	fi
}

log_step() {
	if [ "$SILENT" = 0 ]; then
		if [ "$RU" = 1 ]; then
			printf "  ${C_GREEN}✔${C_RESET} %s\n" "$2"
		else
			printf "  ${C_GREEN}✔${C_RESET} %s\n" "$1"
		fi
	fi
}

log_fail() {
	if [ "$RU" = 1 ]; then
		printf "  \033[31m✖ Ошибка:${C_RESET} %s\n" "$2" >&2
	else
		printf "  \033[31m✖ Error:${C_RESET} %s\n" "$1" >&2
	fi
	exit 1
}

# Fetch utility (curl or wget)
fetch() {
	url="$1"
	out="$2"
	if command -v curl >/dev/null 2>&1; then
		curl -fsSL "$url" -o "$out"
	elif command -v wget >/dev/null 2>&1; then
		wget -qO "$out" "$url"
	else
		log_fail "Neither curl nor wget is installed" "Не найдены curl или wget"
	fi
}

log_info "oxDesktop Installer" "Установщик oxDesktop"

# OS and Architecture Detection
OS="$(uname -s 2>/dev/null || echo Unknown)"
ARCH="$(uname -m 2>/dev/null || echo Unknown)"

IS_WIN=0
IS_MAC=0
IS_LINUX=0

case "$OS" in
	Linux*)
		IS_LINUX=1
		[ "$ARCH" = "x86_64" ] || [ "$ARCH" = "amd64" ] || log_fail "Linux builds currently support x86_64 only" "Сборки под Linux поддерживают только x86_64"
		PATTERN='oxDesktop-linux-x64\.[0-9.]*\.tar\.gz'
		[ -n "$PREFIX" ] || PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/oxDesktop/app"
		DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/oxDesktop"
		;;
	Darwin*)
		IS_MAC=1
		PATTERN='oxDesktop-macos-(arm64|x64)\.[0-9.]*\.zip'
		[ -n "$PREFIX" ] || PREFIX="/Applications"
		DATA_DIR="$HOME/Library/Application Support/oxDesktop"
		;;
	MINGW*|MSYS*|CYGWIN*|Windows_NT)
		IS_WIN=1
		if [ "$PORTABLE" = 1 ]; then
			PATTERN='oxDesktop-portable-x64\.[0-9.]*\.zip'
		else
			PATTERN='oxDesktop-setup-x64\.[0-9.]*\.exe'
		fi
		[ -n "$PREFIX" ] || PREFIX="${LOCALAPPDATA:-$HOME/AppData/Local}/oxDesktop"
		DATA_DIR="$PREFIX"
		;;
	*)
		log_fail "Unsupported operating system: $OS" "Неподдерживаемая операционная система: $OS"
		;;
esac

log_step "Detected: $OS ($ARCH)" "Определено: $OS ($ARCH)"

# Detect currently installed version
INSTALLED_VER=""
if [ "$IS_LINUX" = 1 ]; then
	if command -v oxdesktop >/dev/null 2>&1; then
		INSTALLED_VER="$(oxdesktop --version 2>/dev/null | head -n 1 || true)"
	fi
	if [ -z "$INSTALLED_VER" ] && [ -f "$PREFIX/changelog.txt" ]; then
		INSTALLED_VER="$(head -n 1 "$PREFIX/changelog.txt" 2>/dev/null || true)"
	fi
elif [ "$IS_WIN" = 1 ]; then
	if [ -f "$PREFIX/changelog.txt" ]; then
		INSTALLED_VER="$(head -n 1 "$PREFIX/changelog.txt" 2>/dev/null || true)"
	fi
elif [ "$IS_MAC" = 1 ]; then
	if [ -f "$PREFIX/oxDesktop.app/Contents/Info.plist" ]; then
		INSTALLED_VER="$(defaults read "$PREFIX/oxDesktop.app/Contents/Info.plist" CFBundleShortVersionString 2>/dev/null || true)"
	fi
fi

if [ -n "$INSTALLED_VER" ]; then
	log_step "Current installation: $INSTALLED_VER" "Текущая установленная версия: $INSTALLED_VER"
else
	log_step "Clean install: no previous version detected" "Чистая установка: предыдущая версия не найдена"
fi

# Temporary working directory
TMP="$(mktemp -d 2>/dev/null || mktemp -d -t 'oxd_inst')"
trap 'rm -rf "$TMP"' EXIT INT TERM

log_step "Checking latest release on GitHub..." "Поиск последнего релиза на GitHub..."
RELEASE_JSON="$TMP/release.json"
fetch "https://api.github.com/repos/$REPO/releases/latest" "$RELEASE_JSON" || log_fail "Failed to query GitHub API" "Не удалось получить данные с GitHub API"

# Parse download URL matching pattern
URL="$(grep -E -o "https://[^\"]*($PATTERN)" "$RELEASE_JSON" | head -n 1 || true)"

# Fallback: search assets list
if [ -z "$URL" ]; then
	URL="$(grep -o "\"browser_download_url\": *\"[^\"]*\"" "$RELEASE_JSON" | grep -E -o "https://[^\"]*($PATTERN)" | head -n 1 || true)"
fi

if [ -z "$URL" ]; then
	log_fail "Release asset not found for $OS ($ARCH)" "Файл релиза для $OS ($ARCH) не найден в последнем выпуске"
fi

FILENAME="${URL##*/}"

# Version comparison helpers for downgrade / beta check
parse_ver_nums() {
	v="$1"
	v="${v#oxDesktop}"
	v="${v# }"
	v="${v#v}"
	v="${v#V}"
	v="${v%%-*}"
	v="${v%%_*}"
	v="${v%%(*}"
	v="${v%% *}"
	p1="$(echo "$v" | cut -d. -f1 2>/dev/null || echo 0)"
	p2="$(echo "$v" | cut -d. -f2 2>/dev/null || echo 0)"
	p3="$(echo "$v" | cut -d. -f3 2>/dev/null || echo 0)"
	p4="$(echo "$v" | cut -d. -f4 2>/dev/null || echo 0)"
	case "$p1" in ''|*[!0-9]*) p1=0 ;; esac
	case "$p2" in ''|*[!0-9]*) p2=0 ;; esac
	case "$p3" in ''|*[!0-9]*) p3=0 ;; esac
	case "$p4" in ''|*[!0-9]*) p4=0 ;; esac
	echo "$p1 $p2 $p3 $p4"
}

is_ver_greater() {
	v1_nums="$(parse_ver_nums "$1")"
	v2_nums="$(parse_ver_nums "$2")"
	set -- $v1_nums $v2_nums
	if [ "$1" -gt "$5" ]; then return 0; elif [ "$1" -lt "$5" ]; then return 1; fi
	if [ "$2" -gt "$6" ]; then return 0; elif [ "$2" -lt "$6" ]; then return 1; fi
	if [ "$3" -gt "$7" ]; then return 0; elif [ "$3" -lt "$7" ]; then return 1; fi
	if [ "$4" -gt "$8" ]; then return 0; elif [ "$4" -lt "$8" ]; then return 1; fi
	return 1
}

# Check downgrade / pre-release conflict
if [ -n "$INSTALLED_VER" ]; then
	REL_TAG="$(grep -m 1 '"tag_name":' "$RELEASE_JSON" 2>/dev/null | sed -E 's/.*"tag_name":[[:space:]]*"([^"]+)".*/\1/' || true)"
	TARGET_LABEL="${REL_TAG:-$FILENAME}"
	IS_DOWNGRADE=0
	case "$INSTALLED_VER" in
		*[bB][eE][tT][aA]*|*[dD][eE][vV]*|*[aA][lL][pP][hH][aA]*|*[pP][rR][eE][vV][iI][eE][wW]*|*[rR][cC]*)
			if ! is_ver_greater "$TARGET_LABEL" "$INSTALLED_VER"; then
				IS_DOWNGRADE=1
			fi
			;;
		*)
			if is_ver_greater "$INSTALLED_VER" "$TARGET_LABEL"; then
				IS_DOWNGRADE=1
			fi
			;;
	esac

	if [ "$IS_DOWNGRADE" = 1 ] && [ "$SILENT" = 0 ]; then
		if [ "$RU" = 1 ]; then
			printf "Обнаружена более новая или предварительная (бета/dev) версия oxDesktop (%s).\nВы действительно хотите установить версию %s? [Y/N Д/Н]: " "$INSTALLED_VER" "$TARGET_LABEL"
		else
			printf "A newer or pre-release (beta/dev) version of oxDesktop is installed (%s).\nDo you really want to install version %s? [Y/N D/N]: " "$INSTALLED_VER" "$TARGET_LABEL"
		fi
		read -r answer || answer=""
		case "$answer" in
			[yY]|[yY][eE][sS]|[дД]|[дД][аА])
				;;
			*)
				if [ "$RU" = 1 ]; then
					printf "Установка отменена пользователем.\n"
				else
					printf "Installation canceled by user.\n"
				fi
				exit 0
				;;
		esac
	fi
fi

log_step "Downloading $FILENAME..." "Загрузка $FILENAME..."
PKG_FILE="$TMP/$FILENAME"
fetch "$URL" "$PKG_FILE"

# Installation procedure per OS
if [ "$IS_LINUX" = 1 ]; then
	log_step "Extracting Linux package..." "Распаковка пакета Linux..."
	mkdir -p "$TMP/unpack"
	tar -xzf "$PKG_FILE" -C "$TMP/unpack"

	APP_SRC=""
	if [ -x "$TMP/unpack/oxDesktop/oxDesktop" ]; then
		APP_SRC="$TMP/unpack/oxDesktop"
	elif [ -x "$TMP/unpack/exDesktop/exDesktop" ]; then
		APP_SRC="$TMP/unpack/exDesktop"
	else
		# Search binary in unpacked tree
		APP_SRC="$(dirname "$(find "$TMP/unpack" -type f -name "*Desktop" -perm -111 | head -n 1)")"
	fi

	[ -n "$APP_SRC" ] || log_fail "Package archive is damaged or missing binary" "Архив повреждён или не содержит исполняемого файла"

	rm -rf "$PREFIX"
	mkdir -p "$(dirname "$PREFIX")"
	mv "$APP_SRC" "$PREFIX"

	# Binary symlink in ~/.local/bin
	mkdir -p "$HOME/.local/bin"
	BIN_PATH="$PREFIX/oxDesktop"
	[ -x "$BIN_PATH" ] || BIN_PATH="$PREFIX/exDesktop"
	ln -sf "$BIN_PATH" "$HOME/.local/bin/oxdesktop"

	# Desktop entry and MIME integration
	APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
	ICONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"
	MIME_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/mime/packages"
	mkdir -p "$APPS_DIR" "$ICONS_DIR" "$MIME_DIR"

	ICON_SRC="$PREFIX/oxDesktop.png"
	[ -f "$ICON_SRC" ] || ICON_SRC="$PREFIX/exDesktop.png"
	if [ -f "$ICON_SRC" ]; then
		cp -f "$ICON_SRC" "$ICONS_DIR/oxdesktop.png"
	fi

	cat > "$APPS_DIR/oxdesktop.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=oxDesktop
Comment=Aero Delta Telegram Client
Exec="$BIN_PATH" -- %u
Icon=oxdesktop
Terminal=false
Categories=Network;InstantMessaging;Chat;
MimeType=x-scheme-handler/tg;application/x-oxdesktop-plugin;
StartupWMClass=oxDesktop
EOF

	cat > "$MIME_DIR/oxdesktop-plugin.xml" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-oxdesktop-plugin">
    <comment>oxDesktop Plugin</comment>
    <glob pattern="*.plugin"/>
  </mime-type>
</mime-info>
EOF

	command -v update-mime-database >/dev/null 2>&1 && update-mime-database "${XDG_DATA_HOME:-$HOME/.local/share}/mime" >/dev/null 2>&1 || true
	command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true

	# TGWS dependencies auto-setup if python3 is available
	TGWS_DIR="$PREFIX/python/tgws/lib"
	if command -v python3 >/dev/null 2>&1; then
		mkdir -p "$TGWS_DIR"
		python3 -m pip install --quiet --disable-pip-version-check --target "$TGWS_DIR" cryptography h2 httpx certifi >/dev/null 2>&1 || true
	fi

	mkdir -p "$DATA_DIR"
	printf 'tgws=1\n' > "$DATA_DIR/oxd_install.conf"

	log_step "Installation complete!" "Установка успешно завершена!"
	if [ "$RU" = 1 ]; then
		printf "\n${C_BOLD}▶ Запуск:${C_RESET} ${C_CYAN}oxdesktop${C_RESET} (установлен в $PREFIX)\n\n"
	else
		printf "\n${C_BOLD}▶ Run:${C_RESET} ${C_CYAN}oxdesktop${C_RESET} (installed to $PREFIX)\n\n"
	fi

elif [ "$IS_MAC" = 1 ]; then
	log_step "Extracting macOS bundle..." "Распаковка пакета macOS..."
	command -v ditto >/dev/null 2>&1 || log_fail "ditto utility is required on macOS" "Не найдена утилита ditto"

	mkdir -p "$TMP/unpack"
	ditto -x -k "$PKG_FILE" "$TMP/unpack"

	APP_SRC="$(find "$TMP/unpack" -maxdepth 2 -name "*Desktop.app" | head -n 1)"
	[ -d "$APP_SRC" ] || log_fail "macOS bundle not found in archive" "Бандл приложения не найден в архиве"

	TARGET="$PREFIX/oxDesktop.app"
	if [ ! -w "$PREFIX" ]; then
		PREFIX="$HOME/Applications"
		TARGET="$PREFIX/oxDesktop.app"
		mkdir -p "$PREFIX"
	fi

	rm -rf "$TARGET"
	ditto "$APP_SRC" "$TARGET"
	xattr -dr com.apple.quarantine "$TARGET" 2>/dev/null || true

	TGWS_DIR="$DATA_DIR/tgws-lib"
	if command -v python3 >/dev/null 2>&1; then
		mkdir -p "$TGWS_DIR"
		python3 -m pip install --quiet --disable-pip-version-check --target "$TGWS_DIR" cryptography h2 httpx certifi >/dev/null 2>&1 || true
	fi

	mkdir -p "$DATA_DIR"
	printf 'tgws=1\n' > "$DATA_DIR/oxd_install.conf"

	log_step "Installation complete!" "Установка успешно завершена!"
	if [ "$RU" = 1 ]; then
		printf "\n${C_BOLD}▶ Приложение установлено в:${C_RESET} ${C_CYAN}$TARGET${C_RESET}\n\n"
	else
		printf "\n${C_BOLD}▶ Application installed to:${C_RESET} ${C_CYAN}$TARGET${C_RESET}\n\n"
	fi

elif [ "$IS_WIN" = 1 ]; then
	if [ "$PORTABLE" = 1 ]; then
		log_step "Extracting Windows portable..." "Распаковка Windows portable..."
		mkdir -p "$PREFIX"
		if command -v unzip >/dev/null 2>&1; then
			unzip -q -o "$PKG_FILE" -d "$PREFIX"
		elif command -v 7z >/dev/null 2>&1; then
			7z x -y -o"$PREFIX" "$PKG_FILE" >/dev/null
		fi
		log_step "Installed to $PREFIX" "Установлено в $PREFIX"
		if [ "$RU" = 1 ]; then
			printf "\n${C_BOLD}▶ Готово:${C_RESET} ${C_CYAN}$PREFIX/oxDesktop.exe${C_RESET}\n\n"
		else
			printf "\n${C_BOLD}▶ Ready:${C_RESET} ${C_CYAN}$PREFIX/oxDesktop.exe${C_RESET}\n\n"
		fi
	else
		log_step "Launching Windows silent installer..." "Запуск тихого установщика Windows..."
		chmod +x "$PKG_FILE" 2>/dev/null || true
		cmd.exe /c start "" /wait "$PKG_FILE" /SILENT /NORESTART /SP-
		log_step "Installation complete!" "Установка завершена!"
	fi
fi
