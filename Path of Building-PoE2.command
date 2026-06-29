#!/bin/sh
set -eu

PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export PATH

case "$0" in
	/*) REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) ;;
	*) REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$PWD/$0")" && pwd -P) ;;
esac

RUNTIME_EXE="$REPO_DIR/runtime/Path{space}of{space}Building-PoE2.exe"

if [ ! -f "$RUNTIME_EXE" ]; then
	printf 'Path of Building runtime was not found:\n%s\n' "$RUNTIME_EXE" >&2
	exit 1
fi

if [ "${POB_WINE:-}" ]; then
	WINE_BIN=$POB_WINE
elif command -v wine64 >/dev/null 2>&1; then
	WINE_BIN=$(command -v wine64)
elif command -v wine >/dev/null 2>&1; then
	WINE_BIN=$(command -v wine)
else
	cat >&2 <<'EOF'
Wine was not found.

Install a Windows compatibility layer such as Wine, Whisky, or CrossOver, then
run this launcher again. You can also set POB_WINE to the Wine executable path.
EOF
	exit 127
fi

if [ "$(uname -s)" = "Darwin" ] && [ -z "${WINEPREFIX:-}" ]; then
	WINEPREFIX="$HOME/Library/Application Support/Path of Building-PoE2/WinePrefix"
	export WINEPREFIX
fi

cd "$REPO_DIR"
exec "$WINE_BIN" "$RUNTIME_EXE" "$@"
