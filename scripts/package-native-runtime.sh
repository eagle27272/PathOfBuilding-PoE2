#!/bin/sh
set -eu

case "$0" in
	/*) SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) ;;
	*) SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$PWD/$0")" && pwd -P) ;;
esac
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)

lower_value() {
	printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

safe_part() {
	lower_value "$1" | sed 's/[^a-z0-9._-]/-/g'
}

normalize_platform() {
	value=$(lower_value "$1")
	case "$value" in
		darwin|mac|macos|osx) printf '%s\n' macos ;;
		windows|win|win32|mingw*|msys*|cygwin*) printf '%s\n' win32 ;;
		*) safe_part "$value" ;;
	esac
}

normalize_architecture() {
	value=$(lower_value "$1")
	case "$value" in
		arm64|aarch64) printf '%s\n' arm64 ;;
		x86_64|amd64|x64) printf '%s\n' x64 ;;
		i386|i486|i586|i686|x86) printf '%s\n' x86 ;;
		armv7*|armhf) printf '%s\n' armv7 ;;
		armv6*) printf '%s\n' armv6 ;;
		armv5*) printf '%s\n' arm ;;
		ppc64el) printf '%s\n' ppc64le ;;
		*) safe_part "$value" ;;
	esac
}

is_known_architecture() {
	case "$(normalize_architecture "$1")" in
		x64|x86|arm64|arm64ec|arm64x|arm|armv6|armv7|riscv32|riscv64|riscv128|ppc|ppc64|ppc64le|mips|mips64|s390|s390x|loongarch32|loongarch64|ia64) return 0 ;;
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
	if [ "$(detect_platform)" = "win32" ]; then
		if [ -n "${PROCESSOR_ARCHITEW6432:-}" ]; then
			normalize_architecture "$PROCESSOR_ARCHITEW6432"
			return
		fi
		if [ -n "${PROCESSOR_ARCHITECTURE:-}" ]; then
			normalize_architecture "$PROCESSOR_ARCHITECTURE"
			return
		fi
	fi
	normalize_architecture "$(uname -m)"
}

HOST_PLATFORM=$(detect_platform)
HOST_ARCHITECTURE=$(detect_architecture)
HOST_TARGET=$HOST_PLATFORM-$HOST_ARCHITECTURE
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
OUT_DIR=${POB_RUNTIME_OUT_DIR:-$REPO_DIR/runtime/$TARGET}
BUILD_DIR=${POB_LAUNCHER_BUILD_DIR:-$REPO_DIR/build/native-launcher-$TARGET}
case "$PLATFORM" in
	win32) DEFAULT_LAUNCHER_NAME=PathOfBuilding-PoE2.exe ;;
	*) DEFAULT_LAUNCHER_NAME=PathOfBuilding-PoE2 ;;
esac
LAUNCHER_NAME=${POB_LAUNCHER_NAME:-$DEFAULT_LAUNCHER_NAME}

if [ "${POB_LAUNCHER_ALLOW_CROSS_TARGET:-}" != "1" ] && [ "$TARGET" != "$HOST_TARGET" ]; then
	printf 'ERROR: Refusing to package %s from host %s.\n' "$TARGET" "$HOST_TARGET" >&2
	printf 'Set POB_LAUNCHER_ALLOW_CROSS_TARGET=1 only when using a matching cross compiler/toolchain.\n' >&2
	exit 1
fi

mkdir -p "$OUT_DIR"

if [ "${POB_LAUNCHER_FORCE_CXX:-}" != "1" ] && command -v cmake >/dev/null 2>&1; then
	cmake -S "$REPO_DIR/launcher" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
	cmake --build "$BUILD_DIR" --config Release
	if [ -x "$BUILD_DIR/$LAUNCHER_NAME" ]; then
		cp "$BUILD_DIR/$LAUNCHER_NAME" "$OUT_DIR/$LAUNCHER_NAME"
	elif [ -x "$BUILD_DIR/Release/$LAUNCHER_NAME" ]; then
		cp "$BUILD_DIR/Release/$LAUNCHER_NAME" "$OUT_DIR/$LAUNCHER_NAME"
	else
		printf 'Built launcher was not found in %s\n' "$BUILD_DIR" >&2
		exit 1
	fi
else
	CXX=${CXX:-c++}
	LIBS=${POB_LAUNCHER_LIBS:-}
	case "$HOST_PLATFORM" in
		linux) LIBS="${LIBS:+$LIBS }-ldl" ;;
	esac
	# shellcheck disable=SC2086
	$CXX -std=c++17 -O2 "$REPO_DIR/launcher/pob_launcher.cpp" -o "$OUT_DIR/$LAUNCHER_NAME" $LIBS
fi
chmod +x "$OUT_DIR/$LAUNCHER_NAME"

if [ "${SIMPLEGRAPHIC_INSTALL_DIR:-}" ]; then
	if [ ! -d "$SIMPLEGRAPHIC_INSTALL_DIR" ]; then
		printf 'SIMPLEGRAPHIC_INSTALL_DIR is not a directory: %s\n' "$SIMPLEGRAPHIC_INSTALL_DIR" >&2
		exit 1
	fi
	find "$SIMPLEGRAPHIC_INSTALL_DIR" -maxdepth 1 -type f \( \
		-name '*.so' -o \
		-name '*.dylib' -o \
		-name '*.dll' \
	\) -exec cp {} "$OUT_DIR/" \;
fi

if [ "$PLATFORM" = "macos" ]; then
	if [ -f "$OUT_DIR/liblibEGL_angle.dylib" ]; then
		cp -p "$OUT_DIR/liblibEGL_angle.dylib" "$OUT_DIR/libEGL.dylib"
	fi
	if [ -f "$OUT_DIR/liblibGLESv2_angle.dylib" ]; then
		cp -p "$OUT_DIR/liblibGLESv2_angle.dylib" "$OUT_DIR/libGLESv2.dylib"
	fi
fi

if [ -d "$REPO_DIR/runtime/lua" ]; then
	rm -rf "$OUT_DIR/lua"
	mkdir -p "$OUT_DIR/lua"
	cp -R "$REPO_DIR/runtime/lua/." "$OUT_DIR/lua/"
fi

if [ -d "$REPO_DIR/runtime/SimpleGraphic" ]; then
	rm -rf "$OUT_DIR/SimpleGraphic"
	mkdir -p "$OUT_DIR/SimpleGraphic"
	cp -R "$REPO_DIR/runtime/SimpleGraphic/." "$OUT_DIR/SimpleGraphic/"
fi

printf 'Packaged native runtime target: %s\n' "$OUT_DIR"
