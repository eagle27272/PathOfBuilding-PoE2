#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import tarfile


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
    if not platform or not architecture:
        fail(f"{file_name} target must include both platform and architecture")
    return f"{platform}-{architecture}", platform, architecture


def entry_launcher_for_platform(platform: str) -> str:
    if platform == "win32":
        return "PathOfBuilding-PoE2.exe"
    return "PathOfBuilding-PoE2"


def normalized_member_name(name: str) -> str:
    path = pathlib.PurePosixPath(name)
    parts = [part for part in path.parts if part not in ("", ".")]
    return "/".join(parts)


def validate_archive_members(path: pathlib.Path, entry_launcher: str, platform: str) -> None:
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


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_entry(path: pathlib.Path) -> dict:
    target, platform, architecture = split_runtime_archive_target(path.name)
    entry_launcher = entry_launcher_for_platform(platform)
    validate_archive_members(path, entry_launcher, platform)
    return {
        "fileName": path.name,
        "target": target,
        "platform": platform,
        "architecture": architecture,
        "layout": "runtime-root",
        "entryLauncher": entry_launcher,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def find_archives(artifact_dir: pathlib.Path) -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for suffix in ("*.tar", "*.tar.gz", "*.tgz"):
        paths.extend(sorted(artifact_dir.glob(f"{RUNTIME_PREFIX}{suffix}")))
    return [path for path in paths if path.is_file()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a PathOfBuilding native launcher runtime index")
    parser.add_argument("archives", nargs="*", type=pathlib.Path)
    parser.add_argument("--artifact-dir", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("PathOfBuildingRuntime-index.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    archive_paths = list(args.archives)
    if args.artifact_dir:
        if not args.artifact_dir.is_dir():
            fail(f"artifact directory does not exist: {args.artifact_dir}")
        archive_paths.extend(find_archives(args.artifact_dir))
    if not archive_paths:
        fail("no PathOfBuilding runtime archives were provided")

    entries = []
    targets = set()
    file_names = set()
    for archive_path in sorted(set(archive_paths)):
        entry = archive_entry(archive_path)
        if entry["fileName"] in file_names:
            fail(f"duplicate runtime archive file name {entry['fileName']}")
        if entry["target"] in targets:
            fail(f"duplicate runtime archive target {entry['target']}")
        file_names.add(entry["fileName"])
        targets.add(entry["target"])
        entries.append(entry)

    index = {
        "schemaVersion": 1,
        "name": "PathOfBuilding-PoE2",
        "launcherArchives": sorted(entries, key=lambda item: item["target"]),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
