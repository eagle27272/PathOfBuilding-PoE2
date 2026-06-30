"""This script requires Python 3.10.0 or higher to run."""

import configparser
import fnmatch
import hashlib
import logging
import pathlib
import re
import xml.etree.ElementTree as Et
from typing import Any, Callable

alphanumeric_pattern = re.compile(r"(\d+)")
target_part_pattern = re.compile(r"^[a-z0-9_.-]+$")
known_architectures = {
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


def _exclude_file(file_patterns: set[str], path: pathlib.Path) -> bool:
    """Whether to exclude a single file. Supports glob patterns (e.g., '*.scm')."""
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in file_patterns)


def _exclude_directory(directory_names: set[str], path: pathlib.Path) -> bool:
    """Whether to exclude a directory. Doesn't consider any files in directories."""
    return any(
        len(path.parts) <= 1
        or all(a == b for a, b in zip(directory.split("/"), path.parts))
        for directory in directory_names
    )


def _parse_list_option(config: configparser.ConfigParser, section: str, option: str) -> set[str]:
    """Split a comma-separated option into a cleaned set of entries."""
    if not config.has_option(section, option):
        return set()
    return {
        entry
        for entry in map(str.strip, config[section][option].split(","))
        if entry
    }


def _parse_ordered_list_option(config: configparser.ConfigParser, section: str, option: str) -> list[str]:
    """Split a comma-separated option into a cleaned list preserving order."""
    if not config.has_option(section, option):
        return []
    return [
        entry
        for entry in map(str.strip, config[section][option].split(","))
        if entry
    ]


def _alphanumeric(key: str) -> list[int | str]:
    """Natural sorting order for numbers, e.g. 10 follows 9."""
    return [
        int(character) if character.isdigit() else character.lower()
        for character in re.split(alphanumeric_pattern, key)
    ]


def _normalize_platform(value: str) -> str:
    """Normalize common platform names into manifest platform labels."""
    value = value.lower()
    if value in {"darwin", "mac", "macos", "osx"}:
        return "macos"
    if value in {"windows", "win", "win32"} or value.startswith(("mingw", "msys", "cygwin")):
        return "win32"
    return value


def _normalize_architecture(value: str) -> str:
    """Normalize common CPU architecture names into manifest architecture labels."""
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


def _is_known_architecture(value: str) -> bool:
    """Whether a target segment is an architecture label we should order first."""
    return _normalize_architecture(value) in known_architectures


def _valid_target_part(value: str) -> bool:
    """Whether a target segment is safe to use in a manifest runtime path."""
    return bool(value) and not value.startswith(".") and bool(target_part_pattern.fullmatch(value))


def _require_target_part(value: str, label: str) -> str:
    """Validate a normalized platform or architecture label."""
    if not _valid_target_part(value):
        raise ValueError(f"Unsafe manifest {label}: {value!r}")
    return value


def _target_from_directory_name(name: str) -> tuple[str, str] | None:
    """Parse a runtime target directory into normalized platform/architecture."""
    name = name.lower()
    parts = name.split("-")
    if len(parts) != 2 or not all(_valid_target_part(part) for part in parts):
        return None
    first, second = parts
    if _is_known_architecture(first):
        platform = _normalize_platform(second)
        architecture = _normalize_architecture(first)
    else:
        platform = _normalize_platform(first)
        architecture = _normalize_architecture(second)
    if not _valid_target_part(platform) or not _valid_target_part(architecture):
        return None
    return platform, architecture


def _target_directory_name(platform: str, architecture: str) -> str:
    """Return the canonical directory name for a normalized runtime target."""
    return f"{platform}-{architecture}"


def _section_part(config: configparser.ConfigParser, section: str) -> str:
    """Return the manifest part represented by a config section."""
    return config[section].get("part", section)


def _section_platform(config: configparser.ConfigParser, section: str) -> str | None:
    """Return the optional platform for a config section.

    The historical [runtime] section contains the Windows runtime, so keep
    generating win32-scoped runtime entries unless manifest.cfg says otherwise.
    """
    platform = config[section].get("platform")
    if platform:
        return _require_target_part(_normalize_platform(platform), "platform")
    if _section_part(config, section) == "runtime":
        return "win32"
    return None


def _section_architecture(config: configparser.ConfigParser, section: str) -> str | None:
    """Return the optional CPU architecture for a config section."""
    architecture = config[section].get("architecture") or config[section].get("arch")
    if architecture:
        return _require_target_part(_normalize_architecture(architecture), "architecture")
    return None


def _section_entries(config: configparser.ConfigParser) -> list[dict[str, str]]:
    """Expand manifest.cfg sections, including discovered runtime target directories."""
    entries: list[dict[str, str]] = []
    for section in config.sections():
        part = _section_part(config, section)
        base_path = pathlib.Path(config[section]["path"])
        entries.append(
            {
                "section": section,
                "part": part,
                "path": base_path.as_posix(),
                "platform": _section_platform(config, section) or "",
                "architecture": _section_architecture(config, section) or "",
                "skip-target-directories": str(
                    config[section].getboolean("discover-targets", fallback=False)
                ),
            }
        )

        if not config[section].getboolean("discover-targets", fallback=False):
            continue

        seen_targets: set[str] = set()
        target_names = _parse_ordered_list_option(config, section, "target-directories")
        if base_path.is_dir():
            target_names.extend(
                path.name
                for path in sorted(base_path.iterdir(), key=lambda path: _alphanumeric(path.name))
                if path.is_dir()
            )
        for target_name in target_names:
            target = _target_from_directory_name(target_name)
            if not target:
                continue
            platform, architecture = target
            canonical_target = _target_directory_name(platform, architecture)
            if canonical_target in seen_targets:
                continue
            seen_targets.add(canonical_target)
            entries.append(
                {
                    "section": section,
                    "part": part,
                    "path": (base_path / canonical_target).as_posix(),
                    "platform": platform,
                    "architecture": architecture,
                    "skip-target-directories": "False",
                }
            )
    return entries


def create_manifest(version: str | None = None, replace: bool = False) -> None:
    """Generate new SHA1 hashes and version number for Path of Building's manifest file.

    :param version: Three-part version number following https://semver.org/.
    :param replace: Whether to overwrite the existing manifest file.
    :return:
    """
    base_path = pathlib.Path().absolute()
    try:
        old_manifest = Et.parse(base_path / "manifest.xml")
    except FileNotFoundError:
        logging.critical(f"Manifest file not found in path '{base_path}'")
        return
    old_root = old_manifest.getroot()
    if (old_version := old_root.find("Version")) is None:
        logging.critical(f"Manifest file in {base_path} has no element 'Version'")
        return
    if (new_version := version or old_version.get("number")) is None:
        logging.critical(f"Manifest file in {base_path} has no attribute 'number'")
        return

    config = configparser.ConfigParser()
    try:
        config.read("manifest.cfg")
    except FileNotFoundError:
        logging.critical(f"Manifest configuration file not found in path '{base_path}'")
        return

    base_url = "https://raw.githubusercontent.com/PathOfBuildingCommunity/PathOfBuilding-PoE2/{branch}/"
    section_entries = _section_entries(config)

    parts: list[dict[str, str]] = []
    for entry in section_entries:
        platform = entry["platform"]
        architecture = entry["architecture"]
        url_path = "" if entry["path"] == "." else entry["path"]
        url = base_url + url_path
        url_with_trailing_slash = url if url.endswith("/") else url + "/"
        attributes = {"part": entry["part"], "url": url_with_trailing_slash}
        if platform:
            attributes["platform"] = platform
        if architecture:
            attributes["architecture"] = architecture
        parts.append(attributes)

    files: list[dict[str, str]] = []
    for entry in section_entries:
        section = entry["section"]
        part = entry["part"]
        platform = entry["platform"]
        architecture = entry["architecture"]
        include_files = _parse_list_option(config, section, "include-files")
        include_dirs = _parse_list_option(config, section, "include-directories")
        exclude_files = _parse_list_option(config, section, "exclude-files")
        exclude_dirs = _parse_list_option(config, section, "exclude-directories")
        source = pathlib.Path(entry["path"])
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            relative_path = path.relative_to(entry["path"])
            if (
                entry["skip-target-directories"] == "True"
                and relative_path.parts
                and _target_from_directory_name(relative_path.parts[0])
            ):
                continue
            if include_files and not _exclude_file(include_files, path):
                continue
            if include_dirs and not _exclude_directory(include_dirs, path):
                continue
            if exclude_files and _exclude_file(exclude_files, path):
                continue
            if exclude_dirs and _exclude_directory(exclude_dirs, path):
                continue
            data = path.read_bytes()
            # Normalize line endings for non-binary files in case they were accidentally mixed
            if b"\0" not in data:
                data = re.sub(rb"\r\n?|\n", b"\r\n", data)
            sha1 = hashlib.sha1(data).hexdigest()
            name = relative_path.as_posix()
            attributes = {"name": name, "part": part, "sha1": sha1}
            if platform:
                attributes["platform"] = platform
            if architecture:
                attributes["architecture"] = architecture
            files.append(attributes)

    files.sort(key=lambda attr: (attr["part"], _alphanumeric(attr["name"])))

    root = Et.Element("PoBVersion")
    Et.SubElement(root, "Version", number=new_version)
    for attributes in parts:
        Et.SubElement(root, "Source", attributes)
    for attributes in files:
        Et.SubElement(root, "File", attributes)
    file_name = "manifest.xml" if replace else "manifest-updated.xml"
    tree = Et.ElementTree(root)
    Et.indent(tree, "\t")
    tree.write(base_path / file_name, encoding="UTF-8", xml_declaration=True)
    if version is not None:
        logging.info(f"Updated to version {version}")


def cli() -> None:
    """CLI for conveniently updating Path of Building's manifest file."""
    import argparse

    parser = argparse.ArgumentParser(
        usage="%(prog)s [options]",
        description="Update Path of Building's manifest file for a new release.",
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="version", version="2.0.0")
    logging_level = parser.add_mutually_exclusive_group()
    logging_level.add_argument(
        "-v", "--verbose", action="store_true", help="Print more logging information"
    )
    logging_level.add_argument(
        "-q", "--quiet", action="store_true", help="Print no logging information"
    )
    parser.add_argument("--in-place", action="store_true", help="Replace original file")
    parser.add_argument(
        "--set-version",
        action="store",
        help="Set manifest version number",
        metavar="SEMVER",
    )
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    elif args.quiet:
        logging.basicConfig(level=logging.CRITICAL + 1)
    create_manifest(args.set_version or None, args.in_place)


if __name__ == "__main__":
    cli()
