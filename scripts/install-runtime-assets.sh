#!/bin/sh
# cspell:ignore CDPATH armv armhf riscv simplegraphic pathlib getmembers joinpath isfile issym extractall isinstance
set -eu

case "$0" in
	/*) SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) ;;
	*) SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$PWD/$0")" && pwd -P) ;;
esac
REPO_DIR=${POB_RUNTIME_REPO_DIR:-$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)}
RUNTIME_ROOT=${POB_RUNTIME_ROOT:-$REPO_DIR/runtime}
ASSET_DIR=${1:-${POB_RUNTIME_ASSET_DIR:-}}

if [ -z "$ASSET_DIR" ] || [ ! -d "$ASSET_DIR" ]; then
	printf 'Usage: %s <asset-directory>\n' "$0" >&2
	exit 2
fi

RESET_MARKER_DIR=$(mktemp -d "${TMPDIR:-/tmp}/pob-runtime-install.XXXXXX")
trap 'rm -rf "$RESET_MARKER_DIR"' EXIT HUP INT TERM

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
		i386|i486|i586|i686) printf '%s\n' x86 ;;
		armv7*|armhf) printf '%s\n' armv7 ;;
		armv6*) printf '%s\n' armv6 ;;
		armv5*) printf '%s\n' arm ;;
		ppc64el) printf '%s\n' ppc64le ;;
		*) printf '%s\n' "$value" ;;
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
	name=$1
	case "$name" in
		SimpleGraphicDLLs-x64-windows|SimpleGraphicDLLs-x64-win32) printf '%s legacy\n' win32-x64; return ;;
		SimpleGraphicRuntime-*) name=${name#SimpleGraphicRuntime-} ;;
		PathOfBuildingRuntime-*) name=${name#PathOfBuildingRuntime-} ;;
		*) return 1 ;;
	esac

	name=$(lower_value "$name")
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
	printf '%s-%s native\n' "$platform" "$architecture"
}

archive_component() {
	case "$1" in
		SimpleGraphicDLLs-x64-windows|SimpleGraphicDLLs-x64-win32) printf '%s\n' legacy ;;
		SimpleGraphicRuntime-*) printf '%s\n' simplegraphic ;;
		PathOfBuildingRuntime-*) printf '%s\n' launcher ;;
		*) return 1 ;;
	esac
}

validate_archive() {
	python3 - "$1" "$2" <<'PY'
import pathlib
import sys
import tarfile

archive_path = pathlib.Path(sys.argv[1])
out_dir = pathlib.Path(sys.argv[2]).resolve()

def ensure_within_runtime(path, message):
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(out_dir)
    except ValueError:
        raise SystemExit(message)

with tarfile.open(archive_path) as archive:
    members = archive.getmembers()
    link_member_paths = set()
    for member in members:
        member_path = pathlib.PurePosixPath(member.name)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise SystemExit(f"Unsafe path in {archive_path.name}: {member.name}")
        destination = out_dir.joinpath(*member_path.parts)
        ensure_within_runtime(
            destination,
            f"Unsafe path in {archive_path.name}: {member.name}",
        )
        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise SystemExit(f"Unsafe member type in {archive_path.name}: {member.name}")
        if member.issym() or member.islnk():
            link_path = pathlib.PurePosixPath(member.linkname)
            if link_path.is_absolute() or ".." in link_path.parts:
                raise SystemExit(f"Unsafe link in {archive_path.name}: {member.name} -> {member.linkname}")
            ensure_within_runtime(
                destination.parent.joinpath(*link_path.parts),
                f"Unsafe link in {archive_path.name}: {member.name} -> {member.linkname}",
            )
            link_member_paths.add(member_path)
    for member in members:
        member_path = pathlib.PurePosixPath(member.name)
        for link_member_path in link_member_paths:
            if link_member_path != member_path and link_member_path in member_path.parents:
                raise SystemExit(
                    f"Unsafe path in {archive_path.name}: {member.name} would extract through link {link_member_path}"
                )
PY
}

extract_archive() {
	python3 - "$1" "$2" <<'PY'
import pathlib
import sys
import tarfile

archive_path = pathlib.Path(sys.argv[1])
out_dir = pathlib.Path(sys.argv[2]).resolve()

with tarfile.open(archive_path) as archive:
    archive.extractall(out_dir)
PY
}

reset_native_target_once() {
	target=$1
	out_dir=$2
	marker=$RESET_MARKER_DIR/$target
	if [ ! -e "$marker" ]; then
		rm -rf "$out_dir"
		mkdir -p "$out_dir"
		: > "$marker"
	fi
}

remove_previous_simplegraphic_runtime() {
	python3 - "$1" <<'PY'
import json
import pathlib
import sys

out_dir = pathlib.Path(sys.argv[1]).resolve()
manifest_path = out_dir / "SimpleGraphicRuntime.json"
if not manifest_path.exists():
    raise SystemExit(0)

def ensure_inside(path: pathlib.Path) -> None:
    try:
        path.resolve(strict=False).relative_to(out_dir)
    except ValueError:
        raise SystemExit(f"Unsafe existing SimpleGraphic runtime path: {path}")

def safe_flat_file_name(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise SystemExit(f"Invalid existing SimpleGraphicRuntime.json field {field}")
    path = pathlib.PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or len(path.parts) != 1 or path.name in (".", ".."):
        raise SystemExit(f"Unsafe existing SimpleGraphicRuntime.json field {field}: {value}")
    return path.name

ensure_inside(manifest_path)
try:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
except json.JSONDecodeError as exc:
    raise SystemExit(f"Invalid existing SimpleGraphicRuntime.json: {exc}")
if not isinstance(manifest, dict):
    raise SystemExit("Invalid existing SimpleGraphicRuntime.json: expected object")

owned_names = {"SimpleGraphicRuntime.json"}
for key in ("entryLibrary",):
    if key in manifest:
        owned_names.add(safe_flat_file_name(manifest[key], key))
for key in ("luaModules", "files"):
    value = manifest.get(key, [])
    if value is None:
        value = []
    if not isinstance(value, list):
        raise SystemExit(f"Invalid existing SimpleGraphicRuntime.json field {key}")
    for item in value:
        owned_names.add(safe_flat_file_name(item, key))

for name in sorted(owned_names):
    path = out_dir / name
    ensure_inside(path)
    if not path.exists() and not path.is_symlink():
        continue
    if path.is_dir() and not path.is_symlink():
        raise SystemExit(f"Refusing to remove directory from existing SimpleGraphic runtime: {path}")
    path.unlink()
PY
}

recognized=0
for asset in "$ASSET_DIR"/*.tar "$ASSET_DIR"/*.tar.gz "$ASSET_DIR"/*.tgz; do
	[ -f "$asset" ] || continue
	base=$(basename "$asset")
	case "$base" in
		*.tar.gz) stem=${base%.tar.gz} ;;
		*.tgz) stem=${base%.tgz} ;;
		*.tar) stem=${base%.tar} ;;
		*) continue ;;
	esac

	if ! normalized=$(normalize_target "$stem"); then
		printf 'Skipping unrecognized runtime archive: %s\n' "$base" >&2
		continue
	fi
	component=$(archive_component "$stem")
	target=${normalized% *}
	mode=${normalized#* }
	if [ "$component" = "launcher" ]; then
		: > "$RESET_MARKER_DIR/launcher-$target"
	fi

	if [ "$mode" = "legacy" ] && [ "${POB_RUNTIME_INSTALL_LEGACY_WINDOWS:-1}" = "1" ]; then
		out_dir=$RUNTIME_ROOT
	else
		out_dir=$RUNTIME_ROOT/$target
	fi

	validate_archive "$asset" "$out_dir"
	recognized=$((recognized + 1))
done

if [ "$recognized" -eq 0 ]; then
	printf 'No recognized runtime archives found in %s\n' "$ASSET_DIR" >&2
	exit 1
fi

installed=0
for asset in "$ASSET_DIR"/*.tar "$ASSET_DIR"/*.tar.gz "$ASSET_DIR"/*.tgz; do
	[ -f "$asset" ] || continue
	base=$(basename "$asset")
	case "$base" in
		*.tar.gz) stem=${base%.tar.gz} ;;
		*.tgz) stem=${base%.tgz} ;;
		*.tar) stem=${base%.tar} ;;
		*) continue ;;
	esac

	if ! normalized=$(normalize_target "$stem"); then
		continue
	fi
	component=$(archive_component "$stem")
	target=${normalized% *}
	mode=${normalized#* }

	if [ "$mode" = "legacy" ] && [ "${POB_RUNTIME_INSTALL_LEGACY_WINDOWS:-1}" = "1" ]; then
		out_dir=$RUNTIME_ROOT
		mkdir -p "$out_dir"
	else
		out_dir=$RUNTIME_ROOT/$target
		if [ -e "$RESET_MARKER_DIR/launcher-$target" ]; then
			reset_native_target_once "$target" "$out_dir"
		elif [ "$component" = "simplegraphic" ]; then
			mkdir -p "$out_dir"
			remove_previous_simplegraphic_runtime "$out_dir"
		else
			reset_native_target_once "$target" "$out_dir"
		fi
	fi

	mkdir -p "$out_dir"
	extract_archive "$asset" "$out_dir"
	installed=$((installed + 1))
	printf 'Installed %s into %s\n' "$base" "$out_dir"
done
