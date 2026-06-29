#!/bin/sh
set -eu

case "$0" in
	/*) SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) ;;
	*) SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$PWD/$0")" && pwd -P) ;;
esac
if [ "$#" -gt 0 ]; then
	REPO_DIR=$1
	shift
else
	REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)
fi

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

is_known_architecture() {
	case "$(normalize_architecture "$1")" in
		x64|x86|arm64|arm|armv6|armv7|riscv64|ppc64le|s390x|loongarch64) return 0 ;;
		*) return 1 ;;
	esac
}

valid_target_part() {
	case "$1" in
		""|.*|*/*|*\\*|*[!abcdefghijklmnopqrstuvwxyz0123456789_.-]*) return 1 ;;
		*) return 0 ;;
	esac
}

normalize_target() {
	name=$(lower_value "$1")
	case "$name" in
		*-*) ;;
		*) return 1 ;;
	esac

	first=${name%%-*}
	second=${name#*-}
	case "$second" in
		*-*) return 1 ;;
	esac
	valid_target_part "$first" || return 1
	valid_target_part "$second" || return 1

	if is_known_architecture "$first"; then
		platform=$(normalize_platform "$second")
		architecture=$(normalize_architecture "$first")
	else
		platform=$(normalize_platform "$first")
		architecture=$(normalize_architecture "$second")
	fi

	valid_target_part "$platform" || return 1
	valid_target_part "$architecture" || return 1
	printf '%s %s %s\n' "$platform-$architecture" "$platform" "$architecture"
}

detect_platform() {
	normalize_platform "$(uname -s)"
}

detect_architecture() {
	normalize_architecture "$(uname -m)"
}

if [ "${POB_RUNTIME_TARGET:-}" ]; then
	if ! normalized_target=$(normalize_target "$POB_RUNTIME_TARGET"); then
		printf 'ERROR: POB_RUNTIME_TARGET must be a safe <platform>-<architecture> value: %s\n' "$POB_RUNTIME_TARGET" >&2
		exit 2
	fi
	IFS=' ' read -r TARGET PLATFORM ARCHITECTURE <<EOF
$normalized_target
EOF
else
	PLATFORM=$(normalize_platform "${POB_RUNTIME_PLATFORM:-$(detect_platform)}")
	ARCHITECTURE=$(normalize_architecture "${POB_RUNTIME_ARCHITECTURE:-$(detect_architecture)}")
	TARGET=$PLATFORM-$ARCHITECTURE
fi
if ! valid_target_part "$PLATFORM" || ! valid_target_part "$ARCHITECTURE"; then
	printf 'ERROR: Runtime target labels must be safe: %s/%s\n' "$PLATFORM" "$ARCHITECTURE" >&2
	exit 2
fi
RUNTIME_DIR=${POB_RUNTIME_DIR:-$REPO_DIR/runtime/$TARGET}

case "$PLATFORM" in
	win32)
		LAUNCHER_NAMES="PathOfBuilding-PoE2.exe
Path of Building-PoE2.exe
Path{space}of{space}Building-PoE2.exe"
		LIBRARY_NAMES="SimpleGraphic.dll"
		;;
	macos)
		LAUNCHER_NAMES="PathOfBuilding-PoE2
Path of Building-PoE2"
		LIBRARY_NAMES="libSimpleGraphic.dylib
SimpleGraphic.dylib"
		;;
	*)
		LAUNCHER_NAMES="PathOfBuilding-PoE2
Path of Building-PoE2"
		LIBRARY_NAMES="libSimpleGraphic.so
SimpleGraphic.so"
		;;
esac

find_first() {
	dir=$1
	names=$2
	printf '%s\n' "$names" | while IFS= read -r name; do
		[ -n "$name" ] || continue
		if [ -e "$dir/$name" ]; then
			printf '%s\n' "$dir/$name"
			return 0
		fi
	done
}

LAUNCHER_PATH=$(find_first "$RUNTIME_DIR" "$LAUNCHER_NAMES" || true)
LIBRARY_PATH=$(find_first "$RUNTIME_DIR" "$LIBRARY_NAMES" || true)

if [ -z "$LAUNCHER_PATH" ]; then
	printf 'Native launcher was not found for %s/%s in %s\n' "$PLATFORM" "$ARCHITECTURE" "$RUNTIME_DIR" >&2
	exit 1
fi
if [ ! -x "$LAUNCHER_PATH" ]; then
	printf 'Native launcher is not executable: %s\n' "$LAUNCHER_PATH" >&2
	exit 1
fi
if [ -z "$LIBRARY_PATH" ]; then
	printf 'SimpleGraphic runtime library was not found for %s/%s in %s\n' "$PLATFORM" "$ARCHITECTURE" "$RUNTIME_DIR" >&2
	exit 1
fi

printf 'Found native launcher: %s\n' "$LAUNCHER_PATH"
printf 'Found SimpleGraphic library: %s\n' "$LIBRARY_PATH"

if [ "${POB_SMOKE_RUN:-0}" = "1" ]; then
	POB_RUNTIME_PLATFORM=$PLATFORM POB_RUNTIME_ARCHITECTURE=$ARCHITECTURE \
		"$REPO_DIR/Path of Building-PoE2.command" "$@"
fi
