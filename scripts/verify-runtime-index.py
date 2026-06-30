#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import tarfile


RUNTIME_PATTERNS = (
    "SimpleGraphicRuntime-*.tar",
    "SimpleGraphicRuntime-*.tar.gz",
    "SimpleGraphicRuntime-*.tgz",
)
LEGACY_PATTERNS = (
    "SimpleGraphicDLLs-*.tar",
    "SimpleGraphicDLLs-*.tar.gz",
    "SimpleGraphicDLLs-*.tgz",
)
RUNTIME_PREFIX = "SimpleGraphicRuntime-"
LEGACY_WINDOWS_ARCHIVE = "SimpleGraphicDLLs-x64-windows.tar"
MANIFEST_NAME = "SimpleGraphicRuntime.json"
SUPPORTED_SUFFIXES = (".tar.gz", ".tgz", ".tar")
KNOWN_ARCHITECTURES = {
    "x64",
    "x86",
    "arm64",
    "arm64ec",
    "arm64x",
    "arm",
    "armv6",
    "armv7",
    "riscv32",
    "riscv64",
    "riscv128",
    "ppc",
    "ppc64",
    "ppc64le",
    "mips",
    "mips64",
    "s390",
    "s390x",
    "loongarch32",
    "loongarch64",
    "ia64",
}


def fail(message: str) -> None:
    raise SystemExit(f"error: {message}")


def safe_file_name(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        fail(f"index field {field!r} must be a non-empty string")
    path = pathlib.PurePosixPath(value)
    if "\\" in value or path.is_absolute() or len(path.parts) != 1 or path.name in (".", ".."):
        fail(f"index field {field!r} must be a flat file name: {value}")
    return path.name


def normalize_platform_label(platform: str) -> str:
    platform = platform.lower()
    if platform in {"darwin", "mac", "macos", "osx"}:
        return "macos"
    if platform in {"windows", "win", "win32"} or platform.startswith(("mingw", "msys", "cygwin")):
        return "win32"
    return platform


def normalize_architecture_label(architecture: str) -> str:
    architecture = architecture.lower()
    aliases = {
        "amd64": "x64",
        "x86_64": "x64",
        "aarch64": "arm64",
        "armhf": "armv7",
        "i386": "x86",
        "i486": "x86",
        "i586": "x86",
        "i686": "x86",
        "ppc64el": "ppc64le",
    }
    if architecture.startswith("armv7"):
        return "armv7"
    if architecture.startswith("armv6"):
        return "armv6"
    if architecture.startswith("armv5"):
        return "arm"
    return aliases.get(architecture, architecture)


def is_known_architecture(architecture: str) -> bool:
    return normalize_architecture_label(architecture) in KNOWN_ARCHITECTURES


def split_runtime_archive_target(file_name: str) -> tuple[str, str, str]:
    for suffix in SUPPORTED_SUFFIXES:
        if file_name.endswith(suffix):
            stem = file_name[: -len(suffix)]
            break
    else:
        fail(f"{file_name} is not a supported runtime archive")

    if not stem.startswith(RUNTIME_PREFIX):
        fail(f"{file_name} does not start with {RUNTIME_PREFIX}")

    target = stem[len(RUNTIME_PREFIX) :]
    if target.count("-") != 1:
        fail(f"{file_name} target must be a two-part <platform>-<architecture> value")

    first, second = target.split("-", 1)
    if is_known_architecture(first):
        platform = normalize_platform_label(second)
        architecture = normalize_architecture_label(first)
    else:
        platform = normalize_platform_label(first)
        architecture = normalize_architecture_label(second)
    return f"{platform}-{architecture}", platform, architecture


def require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        fail(f"index field {field!r} must be a non-empty string")
    return value


def require_string_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        fail(f"index field {field!r} must be a non-empty string list")
    return value


def require_int(value: object, field: str) -> int:
    if not isinstance(value, int) or value < 0:
        fail(f"index field {field!r} must be a non-negative integer")
    return value


def require_sha256(value: object, field: str) -> str:
    digest = require_string(value, field)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        fail(f"index field {field!r} must be a lowercase SHA-256 hex digest")
    return digest


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_member_name(member: tarfile.TarInfo, archive_path: pathlib.Path) -> str:
    member_path = pathlib.PurePosixPath(member.name)
    if member_path.is_absolute() or ".." in member_path.parts:
        fail(f"unsafe path in {archive_path.name}: {member.name}")
    clean = member.name
    while clean.startswith("./"):
        clean = clean[2:]
    return "" if clean in ("", ".") else clean.rstrip("/")


def load_runtime_archive_manifest(archive_path: pathlib.Path) -> tuple[dict, set[str]]:
    names: set[str] = set()
    file_data: dict[str, bytes] = {}
    link_member_paths: set[pathlib.PurePosixPath] = set()

    with tarfile.open(archive_path) as archive:
        members = archive.getmembers()
        for member in members:
            member_path = pathlib.PurePosixPath(member.name)
            clean = clean_member_name(member, archive_path)
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                fail(f"unsafe member type in {archive_path.name}: {member.name}")
            if member.issym() or member.islnk():
                link_path = pathlib.PurePosixPath(member.linkname)
                if link_path.is_absolute() or ".." in link_path.parts:
                    fail(f"unsafe link in {archive_path.name}: {member.name} -> {member.linkname}")
                if "/" in member.linkname.strip("/"):
                    fail(f"runtime archive links must stay flat: {member.name} -> {member.linkname}")
                link_member_paths.add(member_path)
            if not clean:
                continue
            if member.isdir():
                fail(f"runtime archive must not contain directories: {member.name}")
            if "/" in clean:
                fail(f"runtime archive must be flat: {member.name}")
            names.add(clean)
            if member.isfile():
                extracted = archive.extractfile(member)
                if extracted is None:
                    fail(f"{archive_path.name} member is not readable: {member.name}")
                file_data[clean] = extracted.read()

        for member in members:
            member_path = pathlib.PurePosixPath(member.name)
            for link_member_path in link_member_paths:
                if link_member_path != member_path and link_member_path in member_path.parents:
                    fail(
                        f"{archive_path.name} contains member that would extract through "
                        f"link {link_member_path}: {member.name}"
                    )

    manifest_data = file_data.get(MANIFEST_NAME)
    if manifest_data is None:
        fail(f"{archive_path.name} must contain {MANIFEST_NAME}")
    try:
        manifest = json.loads(manifest_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{archive_path.name} has invalid {MANIFEST_NAME}: {exc}")
    if not isinstance(manifest, dict):
        fail(f"{archive_path.name} {MANIFEST_NAME} must be a JSON object")
    return manifest, names


def load_index(index_path: pathlib.Path) -> dict:
    if not index_path.is_file():
        fail(f"runtime index does not exist: {index_path}")
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"runtime index is invalid JSON: {exc}")
    if not isinstance(index, dict):
        fail("runtime index must be a JSON object")
    if index.get("schemaVersion") != 1:
        fail("runtime index schemaVersion must be 1")
    if index.get("name") != "SimpleGraphic":
        fail("runtime index name must be SimpleGraphic")
    return index


def matching_asset_names(asset_dir: pathlib.Path, patterns: tuple[str, ...]) -> set[str]:
    names: set[str] = set()
    for pattern in patterns:
        names.update(path.name for path in asset_dir.glob(pattern) if path.is_file())
    return names


def require_entry_value(entry: dict, field: str, key: str, expected: str) -> None:
    actual = require_string(entry.get(key), f"{field}.{key}")
    if actual != expected:
        fail(f"index field {field}.{key!r} expected {expected!r}, got {actual!r}")


def verify_file_checksum(asset_dir: pathlib.Path, entry: dict, field: str) -> pathlib.Path:
    file_name = safe_file_name(entry.get("fileName"), f"{field}.fileName")
    expected_size = require_int(entry.get("size"), f"{field}.size")
    expected_sha256 = require_sha256(entry.get("sha256"), f"{field}.sha256")
    archive_path = asset_dir / file_name
    if not archive_path.is_file():
        fail(f"indexed runtime archive is missing: {file_name}")
    actual_size = archive_path.stat().st_size
    if actual_size != expected_size:
        fail(f"{file_name} size mismatch: expected {expected_size}, got {actual_size}")
    actual_sha256 = sha256_file(archive_path)
    if actual_sha256 != expected_sha256:
        fail(f"{file_name} sha256 mismatch: expected {expected_sha256}, got {actual_sha256}")
    return archive_path


def require_manifest_value(manifest: dict, archive_path: pathlib.Path, key: str, expected: object) -> None:
    actual = manifest.get(key)
    if actual != expected:
        fail(f"{archive_path.name} manifest field {key!r} expected {expected!r}, got {actual!r}")


def verify_runtime_archive_manifest(
    archive_path: pathlib.Path,
    entry: dict,
    target: str,
    platform: str,
    architecture: str,
) -> None:
    manifest, names = load_runtime_archive_manifest(archive_path)
    require_manifest_value(manifest, archive_path, "schemaVersion", 1)
    require_manifest_value(manifest, archive_path, "name", "SimpleGraphic")
    require_manifest_value(manifest, archive_path, "target", target)
    require_manifest_value(manifest, archive_path, "platform", platform)
    require_manifest_value(manifest, archive_path, "architecture", architecture)
    for key in ("buildType", "layout", "entryLibrary", "entrypoints", "luaModules"):
        require_manifest_value(manifest, archive_path, key, entry[key])
    if entry["entryLibrary"] not in names:
        fail(f"{archive_path.name} is missing entry library {entry['entryLibrary']}")
    for module_name in entry["luaModules"]:
        if module_name not in names:
            fail(f"{archive_path.name} is missing Lua module {module_name}")


def verify_runtime_entry(asset_dir: pathlib.Path, entry: dict, field: str) -> tuple[str, str]:
    file_name = safe_file_name(entry.get("fileName"), f"{field}.fileName")
    target, platform, architecture = split_runtime_archive_target(file_name)
    require_entry_value(entry, field, "target", target)
    require_entry_value(entry, field, "platform", platform)
    require_entry_value(entry, field, "architecture", architecture)
    require_entry_value(entry, field, "layout", "flat")
    require_string(entry.get("buildType"), f"{field}.buildType")
    require_string(entry.get("entryLibrary"), f"{field}.entryLibrary")
    require_string_list(entry.get("entrypoints"), f"{field}.entrypoints")
    require_string_list(entry.get("luaModules"), f"{field}.luaModules")
    archive_path = verify_file_checksum(asset_dir, entry, field)
    verify_runtime_archive_manifest(archive_path, entry, target, platform, architecture)
    return file_name, target


def verify_legacy_entry(asset_dir: pathlib.Path, entry: dict, field: str) -> str:
    file_name = safe_file_name(entry.get("fileName"), f"{field}.fileName")
    if file_name != LEGACY_WINDOWS_ARCHIVE:
        fail(f"index field {field}.fileName must be {LEGACY_WINDOWS_ARCHIVE}")
    require_entry_value(entry, field, "target", "win32-x64")
    require_entry_value(entry, field, "platform", "win32")
    require_entry_value(entry, field, "architecture", "x64")
    require_entry_value(entry, field, "mode", "legacy-windows-runtime")
    verify_file_checksum(asset_dir, entry, field)
    return file_name


def verify_entries(asset_dir: pathlib.Path, index: dict, key: str, legacy: bool = False) -> set[str]:
    entries = index.get(key, [])
    if not isinstance(entries, list):
        fail(f"runtime index field {key!r} must be a list")
    verified: set[str] = set()
    verified_targets: set[str] = set()
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            fail(f"runtime index field {key}[{idx}] must be an object")
        if legacy:
            file_name = verify_legacy_entry(asset_dir, entry, f"{key}[{idx}]")
            target = None
        else:
            file_name, target = verify_runtime_entry(asset_dir, entry, f"{key}[{idx}]")
        if file_name in verified:
            fail(f"runtime index contains duplicate archive entry: {file_name}")
        if target is not None:
            if target in verified_targets:
                fail(f"runtime index contains duplicate runtime target: {target}")
            verified_targets.add(target)
        verified.add(file_name)
    return verified


def reject_unindexed_assets(
    asset_dir: pathlib.Path,
    patterns: tuple[str, ...],
    indexed_names: set[str],
    label: str,
) -> None:
    extra_names = matching_asset_names(asset_dir, patterns) - indexed_names
    if extra_names:
        fail(f"unindexed {label} archive(s): {', '.join(sorted(extra_names))}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify SimpleGraphic runtime archives against the release index")
    parser.add_argument("asset_dir", type=pathlib.Path)
    parser.add_argument("index", type=pathlib.Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.asset_dir.is_dir():
        fail(f"asset directory does not exist: {args.asset_dir}")

    index = load_index(args.index)
    runtime_names = verify_entries(args.asset_dir, index, "runtimeArchives")
    legacy_names = verify_entries(args.asset_dir, index, "legacyArchives", legacy=True)
    reject_unindexed_assets(args.asset_dir, RUNTIME_PATTERNS, runtime_names, "SimpleGraphic runtime")
    reject_unindexed_assets(args.asset_dir, LEGACY_PATTERNS, legacy_names, "legacy SimpleGraphic")
    print(f"Verified {len(runtime_names)} SimpleGraphic runtime archive(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
