#!/bin/sh
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
		printf 'Skipping unrecognized runtime archive: %s\n' "$base" >&2
		continue
	fi
	target=${normalized% *}
	mode=${normalized#* }

	if [ "$mode" = "legacy" ] && [ "${POB_RUNTIME_INSTALL_LEGACY_WINDOWS:-1}" = "1" ]; then
		out_dir=$RUNTIME_ROOT
	else
		out_dir=$RUNTIME_ROOT/$target
	fi

	mkdir -p "$out_dir"
	python3 - "$asset" "$out_dir" <<'PY'
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
    for member in archive.getmembers():
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
    for member in archive.getmembers():
        archive.extract(member, out_dir)
PY
	installed=$((installed + 1))
	printf 'Installed %s into %s\n' "$base" "$out_dir"
done

if [ "$installed" -eq 0 ]; then
	printf 'No recognized runtime archives found in %s\n' "$ASSET_DIR" >&2
	exit 1
fi
