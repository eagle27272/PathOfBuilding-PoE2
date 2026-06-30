#!/usr/bin/env python3
"""Build a platform-scoped portable Path of Building package from manifest.xml."""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import stat
import tempfile
import zipfile
import xml.etree.ElementTree as Et


TARGET_PART_PATTERN = re.compile(r"^[a-z0-9_.-]+$")
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


def normalize_platform(value: str) -> str:
    value = value.lower()
    if value in {"darwin", "mac", "osx", "macos"}:
        return "macos"
    if value in {"windows", "win", "win32"} or value.startswith(("mingw", "msys", "cygwin")):
        return "win32"
    return value


def normalize_architecture(value: str) -> str:
    value = value.lower()
    if value in {"x86_64", "amd64"}:
        return "x64"
    if value in {"arm64", "aarch64"}:
        return "arm64"
    if value in {"i386", "i486", "i586", "i686"}:
        return "x86"
    if value.startswith("armv7") or value == "armhf":
        return "armv7"
    if value.startswith("armv6"):
        return "armv6"
    if value.startswith("armv5"):
        return "arm"
    if value == "ppc64el":
        return "ppc64le"
    return value


def validate_target_part(kind: str, value: str) -> str:
    if not value or value.startswith(".") or not TARGET_PART_PATTERN.fullmatch(value):
        raise ValueError(f"unsafe {kind} target label: {value}")
    return value


def target_name(platform: str, architecture: str) -> str:
    platform = validate_target_part("platform", normalize_platform(platform))
    architecture = validate_target_part("architecture", normalize_architecture(architecture))
    return f"{platform}-{architecture}"


def sort_key(value: str) -> list[int | str]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value)]


def node_platform(node: Et.Element) -> str | None:
    platform = node.get("platform") or node.get("runtime")
    if platform:
        return normalize_platform(platform)
    return None


def node_architecture(node: Et.Element) -> str | None:
    architecture = node.get("architecture") or node.get("arch")
    if architecture:
        return normalize_architecture(architecture)
    return None


def node_matches_target(node: Et.Element, platform: str, architecture: str) -> bool:
    item_platform = node_platform(node)
    item_architecture = node_architecture(node)
    return (
        (not item_platform or item_platform == platform)
        and (not item_architecture or item_architecture == architecture)
    )


def runtime_root(repo_dir: pathlib.Path, platform: str, architecture: str) -> pathlib.Path:
    target = target_name(platform, architecture)
    native_runtime = repo_dir / "runtime" / target
    if native_runtime.exists():
        return native_runtime
    if platform == "win32" and architecture == "x64":
        return repo_dir / "runtime"
    return native_runtime


def manifest_file_path(node: Et.Element, decode_space: bool = False) -> pathlib.Path:
    name = node.get("name")
    if not name:
        raise ValueError("manifest file entry is missing a name")
    if any(ord(character) < 32 or ord(character) == 127 or character == '"' for character in name):
        raise ValueError(f"manifest file entry has an unsafe name: {name}")
    if "{slash}" in name:
        raise ValueError(f"manifest file entry has an unsafe name: {name}")
    if (
        name.startswith("/")
        or name.endswith("/")
        or "\\" in name
        or "//" in name
        or re.match(r"^[A-Za-z]:", name)
        or any(part in {".", ".."} for part in name.split("/"))
    ):
        raise ValueError(f"manifest file entry has an unsafe name: {name}")
    path = pathlib.PurePosixPath(name)
    if path.is_absolute():
        raise ValueError(f"manifest file entry has an unsafe name: {name}")
    if decode_space:
        path = pathlib.PurePosixPath(str(path).replace("{space}", " "))
    return pathlib.Path(*path.parts)


def source_path(repo_dir: pathlib.Path, runtime_dir: pathlib.Path, node: Et.Element) -> pathlib.Path:
    part = node.get("part")
    name = manifest_file_path(node)
    if part == "runtime":
        source = runtime_dir / name
        if source.exists():
            return source
        return runtime_dir / manifest_file_path(node, decode_space=True)
    if part in {"program", "tree"}:
        source = repo_dir / "src" / name
        if source.exists():
            return source
        return repo_dir / "src" / manifest_file_path(node, decode_space=True)
    source = repo_dir / name
    if source.exists():
        return source
    return repo_dir / manifest_file_path(node, decode_space=True)


def destination_path(
    package_dir: pathlib.Path,
    runtime_target_dir: pathlib.Path,
    platform: str,
    node: Et.Element,
) -> pathlib.Path:
    part = node.get("part")
    name = manifest_file_path(node, decode_space=True)
    if part == "runtime":
        if platform != "win32" and name.parts and name.parts[0] == "SimpleGraphic":
            return package_dir / name
        return runtime_target_dir / name
    return package_dir / name


def copy_manifest_file(source: pathlib.Path, destination: pathlib.Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"manifest file is missing from package source: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def make_executable(path: pathlib.Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def should_be_executable(path: pathlib.Path, platform: str) -> bool:
    if platform == "win32":
        return path.suffix.lower() in {".exe", ".command", ".sh"}
    return path.name in {"PathOfBuilding-PoE2", "Path of Building-PoE2"} or path.suffix in {
        ".command",
        ".sh",
    }


def write_local_manifest(
    source_manifest: Et.ElementTree,
    destination: pathlib.Path,
    files: list[Et.Element],
    platform: str,
    architecture: str,
    branch: str,
) -> None:
    old_root = source_manifest.getroot()
    old_version = old_root.find("Version")
    if old_version is None or not old_version.get("number"):
        raise ValueError("manifest.xml is missing a Version number")

    root = Et.Element("PoBVersion")
    Et.SubElement(
        root,
        "Version",
        {
            "number": old_version.get("number", ""),
            "platform": platform,
            "architecture": architecture,
            "branch": branch,
        },
    )
    for source in old_root.findall("Source"):
        if source.get("part") == "runtime" and not node_matches_target(source, platform, architecture):
            continue
        Et.SubElement(root, "Source", dict(source.attrib))
    for file_node in files:
        Et.SubElement(root, "File", dict(file_node.attrib))

    tree = Et.ElementTree(root)
    Et.indent(tree, "\t")
    destination.parent.mkdir(parents=True, exist_ok=True)
    tree.write(destination, encoding="UTF-8", xml_declaration=True)


def zip_directory(source_dir: pathlib.Path, archive_path: pathlib.Path) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if archive_path.exists():
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir.parent))


def manifest_runtime_targets(manifest_tree: Et.ElementTree) -> list[tuple[str, str]]:
    """Return normalized runtime targets that have files in the manifest."""
    targets: dict[str, tuple[str, str]] = {}
    for node in manifest_tree.getroot().findall("File"):
        if node.get("part") != "runtime":
            continue
        platform = node_platform(node)
        architecture = node_architecture(node)
        if not platform or not architecture:
            continue
        platform = normalize_platform(platform)
        architecture = normalize_architecture(architecture)
        targets[target_name(platform, architecture)] = (platform, architecture)
    return [
        targets[name]
        for name in sorted(targets, key=sort_key)
    ]


def package_portable(args: argparse.Namespace) -> pathlib.Path:
    repo_dir = args.repo_dir.resolve()
    platform = normalize_platform(args.platform)
    architecture = normalize_architecture(args.architecture)
    target = target_name(platform, architecture)
    package_name = args.package_name or f"PathOfBuilding-PoE2-{target}"
    manifest_path = args.manifest if args.manifest.is_absolute() else repo_dir / args.manifest
    manifest_tree = Et.parse(manifest_path)
    runtime_dir = runtime_root(repo_dir, platform, architecture)
    runtime_destination = pathlib.Path("runtime") / (target if runtime_dir.name == target else "")

    files = []
    runtime_files = []
    for node in manifest_tree.getroot().findall("File"):
        if node.get("part") == "runtime":
            if not node_matches_target(node, platform, architecture):
                continue
            runtime_files.append(node)
        files.append(node)
    files = [node for node in files if node.get("part") != "runtime"] + runtime_files
    if not runtime_files and not args.allow_missing_runtime:
        raise SystemExit(f"manifest.xml has no runtime files for {target}")

    with tempfile.TemporaryDirectory(prefix="pob-portable-") as tmp:
        package_dir = pathlib.Path(tmp) / package_name
        runtime_target_dir = package_dir / runtime_destination
        for node in files:
            destination = destination_path(package_dir, runtime_target_dir, platform, node)
            copy_manifest_file(source_path(repo_dir, runtime_dir, node), destination)
            if should_be_executable(destination, platform):
                make_executable(destination)
        write_local_manifest(
            manifest_tree,
            package_dir / "manifest.xml",
            files,
            platform,
            architecture,
            args.branch,
        )
        archive_path = args.output_dir.resolve() / f"{package_name}.zip"
        zip_directory(package_dir, archive_path)
    return archive_path


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-dir", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--manifest", type=pathlib.Path, default=pathlib.Path("manifest.xml"))
    parser.add_argument("--output-dir", type=pathlib.Path, default=pathlib.Path("Dist"))
    parser.add_argument("--package-name")
    parser.add_argument("--platform")
    parser.add_argument("--architecture")
    parser.add_argument("--branch", default=os.environ.get("GITHUB_REF_NAME", "dev"))
    parser.add_argument("--allow-missing-runtime", action="store_true")
    parser.add_argument("--all-targets", action="store_true", help="Package every runtime target with files in the manifest")
    args = parser.parse_args()
    repo_dir = args.repo_dir.resolve()
    manifest_path = args.manifest if args.manifest.is_absolute() else repo_dir / args.manifest
    if args.all_targets:
        manifest_tree = Et.parse(manifest_path)
        targets = manifest_runtime_targets(manifest_tree)
        if not targets:
            raise SystemExit("manifest.xml has no platform/architecture runtime targets")
        for platform, architecture in targets:
            target_args = argparse.Namespace(**vars(args))
            target_args.platform = platform
            target_args.architecture = architecture
            target_args.package_name = None
            archive_path = package_portable(target_args)
            print(f"Packaged portable runtime: {archive_path}")
    else:
        if not args.platform or not args.architecture:
            parser.error("--platform and --architecture are required unless --all-targets is set")
        archive_path = package_portable(args)
        print(f"Packaged portable runtime: {archive_path}")


if __name__ == "__main__":
    cli()
