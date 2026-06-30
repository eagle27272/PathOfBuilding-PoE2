#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import tarfile


RUNTIME_PATTERNS = (
    "PathOfBuildingRuntime-*.tar",
    "PathOfBuildingRuntime-*.tar.gz",
    "PathOfBuildingRuntime-*.tgz",
)
RUNTIME_PREFIX = "PathOfBuildingRuntime-"
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


def entry_launcher_for_platform(platform: str) -> str:
    if platform == "win32":
        return "PathOfBuilding-PoE2.exe"
    return "PathOfBuilding-PoE2"


def normalized_member_name(name: str) -> str:
    path = pathlib.PurePosixPath(name)
    parts = [part for part in path.parts if part not in ("", ".")]
    return "/".join(parts)


def verify_archive_members(path: pathlib.Path, entry_launcher: str, platform: str) -> None:
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        link_member_paths = set()
        launchers = [
            member
            for member in members
            if normalized_member_name(member.name) == entry_launcher
        ]
        if len(launchers) != 1:
            fail(f"{path.name} must contain exactly one {entry_launcher}")
        launcher = launchers[0]
        if not launcher.isfile():
            fail(f"{path.name} {entry_launcher} must be a regular file")
        if platform != "win32" and not (launcher.mode & 0o111):
            fail(f"{path.name} {entry_launcher} must be executable")
        for member in members:
            member_path = pathlib.PurePosixPath(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                fail(f"{path.name} contains unsafe member path: {member.name}")
            if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                fail(f"{path.name} contains unsafe member type: {member.name}")
            if member.issym() or member.islnk():
                link_path = pathlib.PurePosixPath(member.linkname)
                if link_path.is_absolute() or ".." in link_path.parts:
                    fail(f"{path.name} contains unsafe link: {member.name} -> {member.linkname}")
                link_member_paths.add(member_path)
        for member in members:
            member_path = pathlib.PurePosixPath(member.name)
            for link_member_path in link_member_paths:
                if link_member_path != member_path and link_member_path in member_path.parents:
                    fail(f"{path.name} contains member that would extract through link {link_member_path}: {member.name}")


def require_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        fail(f"index field {field!r} must be a non-empty string")
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
    if index.get("name") != "PathOfBuilding-PoE2":
        fail("runtime index name must be PathOfBuilding-PoE2")
    return index


def matching_asset_names(asset_dir: pathlib.Path) -> set[str]:
    names: set[str] = set()
    for pattern in RUNTIME_PATTERNS:
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
        fail(f"indexed PathOfBuilding runtime archive is missing: {file_name}")
    actual_size = archive_path.stat().st_size
    if actual_size != expected_size:
        fail(f"{file_name} size mismatch: expected {expected_size}, got {actual_size}")
    actual_sha256 = sha256_file(archive_path)
    if actual_sha256 != expected_sha256:
        fail(f"{file_name} sha256 mismatch: expected {expected_sha256}, got {actual_sha256}")
    return archive_path


def verify_launcher_entry(asset_dir: pathlib.Path, entry: dict, field: str) -> tuple[str, str]:
    file_name = safe_file_name(entry.get("fileName"), f"{field}.fileName")
    target, platform, architecture = split_runtime_archive_target(file_name)
    entry_launcher = entry_launcher_for_platform(platform)
    require_entry_value(entry, field, "target", target)
    require_entry_value(entry, field, "platform", platform)
    require_entry_value(entry, field, "architecture", architecture)
    require_entry_value(entry, field, "layout", "runtime-root")
    require_entry_value(entry, field, "entryLauncher", entry_launcher)
    archive_path = verify_file_checksum(asset_dir, entry, field)
    verify_archive_members(archive_path, entry_launcher, platform)
    return file_name, target


def verify_entries(asset_dir: pathlib.Path, index: dict) -> set[str]:
    entries = index.get("launcherArchives", [])
    if not isinstance(entries, list):
        fail("runtime index field 'launcherArchives' must be a list")
    verified: set[str] = set()
    verified_targets: set[str] = set()
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            fail(f"runtime index field launcherArchives[{idx}] must be an object")
        file_name, target = verify_launcher_entry(asset_dir, entry, f"launcherArchives[{idx}]")
        if file_name in verified:
            fail(f"runtime index contains duplicate archive entry: {file_name}")
        if target in verified_targets:
            fail(f"runtime index contains duplicate runtime target: {target}")
        verified.add(file_name)
        verified_targets.add(target)
    return verified


def reject_unindexed_assets(asset_dir: pathlib.Path, indexed_names: set[str]) -> None:
    extra_names = matching_asset_names(asset_dir) - indexed_names
    if extra_names:
        fail(f"unindexed PathOfBuilding runtime archive(s): {', '.join(sorted(extra_names))}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify PathOfBuilding native launcher archives against the release index")
    parser.add_argument("asset_dir", type=pathlib.Path)
    parser.add_argument("index", type=pathlib.Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.asset_dir.is_dir():
        fail(f"asset directory does not exist: {args.asset_dir}")

    index = load_index(args.index)
    launcher_names = verify_entries(args.asset_dir, index)
    reject_unindexed_assets(args.asset_dir, launcher_names)
    print(f"Verified {len(launcher_names)} PathOfBuilding runtime archive(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
