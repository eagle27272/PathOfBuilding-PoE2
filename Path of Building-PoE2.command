#!/bin/sh
set -eu

PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export PATH

lower_value() {
	printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

normalize_platform() {
	value=$(lower_value "$1")
	case "$value" in
		darwin|mac|macos|osx) printf '%s\n' macos ;;
		windows|win|win32|mingw*|msys*|cygwin*) printf '%s\n' win32 ;;
		*) printf '%s\n' "$value" ;;
	esac
}

normalize_architecture() {
	value=$(lower_value "$1")
	case "$value" in
		arm64|aarch64) printf '%s\n' arm64 ;;
		x86_64|amd64) printf '%s\n' x64 ;;
		i386|i686) printf '%s\n' x86 ;;
		armv7*|armhf) printf '%s\n' armv7 ;;
		armv6*) printf '%s\n' armv6 ;;
		*) printf '%s\n' "$value" ;;
	esac
}

valid_target_part() {
	case "$1" in
		""|.*|*/*|*\\*|*[!abcdefghijklmnopqrstuvwxyz0123456789_.-]*) return 1 ;;
		*) return 0 ;;
	esac
}

case "$0" in
	/*) REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) ;;
	*) REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$PWD/$0")" && pwd -P) ;;
esac

if [ "${POB_RUNTIME_PLATFORM:-}" ]; then
	POB_PLATFORM=$(normalize_platform "$POB_RUNTIME_PLATFORM")
else
	POB_PLATFORM=$(normalize_platform "$(uname -s)")
fi

if [ "${POB_RUNTIME_ARCHITECTURE:-}" ]; then
	POB_ARCH=$(normalize_architecture "$POB_RUNTIME_ARCHITECTURE")
else
	POB_ARCH=$(normalize_architecture "$(uname -m)")
fi

if ! valid_target_part "$POB_PLATFORM" || ! valid_target_part "$POB_ARCH"; then
	printf 'Invalid runtime target labels: %s/%s\n' "$POB_PLATFORM" "$POB_ARCH" >&2
	exit 2
fi

for target in "$POB_PLATFORM-$POB_ARCH" "$POB_PLATFORM"; do
	for name in \
		"PathOfBuilding-PoE2" \
		"PathOfBuilding-PoE2.exe" \
		"Path of Building-PoE2" \
		"Path of Building-PoE2.exe" \
		"Path{space}of{space}Building-PoE2.exe" \
		"Path of Building-PoE2.app/Contents/MacOS/Path of Building-PoE2"
	do
		RUNTIME_EXE="$REPO_DIR/runtime/$target/$name"
		if [ -x "$RUNTIME_EXE" ]; then
			if [ "$POB_PLATFORM" = "macos" ]; then
				RUNTIME_DIR=$(CDPATH= cd -- "$(dirname -- "$RUNTIME_EXE")" && pwd -P)
				DYLD_LIBRARY_PATH="$RUNTIME_DIR${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
				export DYLD_LIBRARY_PATH
			fi
			cd "$REPO_DIR"
			exec "$RUNTIME_EXE" "$@"
		fi
	done
done

if [ "$POB_PLATFORM" = "win32" ]; then
	for name in \
		"PathOfBuilding-PoE2.exe" \
		"Path of Building-PoE2.exe" \
		"Path{space}of{space}Building-PoE2.exe"
	do
		RUNTIME_EXE="$REPO_DIR/runtime/$name"
		if [ -f "$RUNTIME_EXE" ]; then
			cd "$REPO_DIR"
			exec "$RUNTIME_EXE" "$@"
		fi
	done
fi

if [ "${POB_WINE:-}" ] || [ "${POB_ALLOW_WINE:-}" = "1" ]; then
	if [ "${POB_WINE:-}" ]; then
		WINE_BIN=$POB_WINE
	elif command -v wine64 >/dev/null 2>&1; then
		WINE_BIN=$(command -v wine64)
	elif command -v wine >/dev/null 2>&1; then
		WINE_BIN=$(command -v wine)
	else
		printf 'POB_ALLOW_WINE is set, but Wine was not found on PATH.\n' >&2
		exit 127
	fi

	RUNTIME_EXE=
	for name in \
		"PathOfBuilding-PoE2.exe" \
		"Path of Building-PoE2.exe" \
		"Path{space}of{space}Building-PoE2.exe"
	do
		if [ -f "$REPO_DIR/runtime/$name" ]; then
			RUNTIME_EXE="$REPO_DIR/runtime/$name"
			break
		fi
	done
	if [ ! -f "$RUNTIME_EXE" ]; then
		printf 'Windows fallback runtime was not found under:\n%s\n' "$REPO_DIR/runtime" >&2
		exit 1
	fi

	if [ "$POB_PLATFORM" = "macos" ] && [ -z "${WINEPREFIX:-}" ]; then
		WINEPREFIX="$HOME/Library/Application Support/Path of Building-PoE2/WinePrefix"
		export WINEPREFIX
	fi

	cd "$REPO_DIR"
	exec "$WINE_BIN" "$RUNTIME_EXE" "$@"
fi

cat >&2 <<EOF
No native Path of Building runtime was found for $POB_PLATFORM/$POB_ARCH.

Expected one of:
  runtime/$POB_PLATFORM-$POB_ARCH/PathOfBuilding-PoE2
  runtime/$POB_PLATFORM-$POB_ARCH/Path of Building-PoE2
  runtime/$POB_PLATFORM/PathOfBuilding-PoE2

Set POB_WINE=/path/to/wine or POB_ALLOW_WINE=1 to use the legacy Windows runtime.
EOF
exit 1
