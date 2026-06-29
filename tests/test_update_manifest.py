import pathlib
import xml.etree.ElementTree as Et

import pytest

import update_manifest


def test_current_manifest_includes_required_generated_data_files() -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    root = Et.parse(repo_root / "manifest.xml").getroot()
    manifest_files = {
        node.get("name")
        for node in root.findall("File")
        if node.get("part") in {"program", "tree"}
    }

    required_files = {
        "Data/LiquidEmotions.lua",
        "Data/StatDescriptions/Specific_Skill_Stat_Descriptions/abyssal_living_bomb.lua",
        "Data/StatDescriptions/Specific_Skill_Stat_Descriptions/abyssal_pact.lua",
    }

    for name in required_files:
        assert (repo_root / "src" / name).is_file()
        assert name in manifest_files


def _write_minimal_manifest_config(
    root: pathlib.Path, runtime_section: str = "runtime", runtime_path: str = "runtime"
) -> None:
    (root / "manifest.xml").write_text(
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<PoBVersion><Version number='1.0.0' /></PoBVersion>\n",
        encoding="utf-8",
    )
    (root / "manifest.cfg").write_text(
        "[default]\n"
        "path =\n"
        "include-files = changelog.txt\n"
        "\n"
        f"[{runtime_section}]\n"
        f"path = {runtime_path}\n"
        "exclude-files =\n"
        "exclude-directories =\n"
        "\n"
        "[program]\n"
        "path = src\n"
        "exclude-files =\n"
        "exclude-directories =\n",
        encoding="utf-8",
    )


def test_runtime_files_are_platform_scoped_by_default(tmp_path, monkeypatch) -> None:
    (tmp_path / "changelog.txt").write_text("changes\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Launch.lua").write_text("return {}\n", encoding="utf-8")
    (tmp_path / "runtime" / "lua").mkdir(parents=True)
    (tmp_path / "runtime" / "Path{space}of{space}Building-PoE2.exe").write_bytes(b"MZ")
    (tmp_path / "runtime" / "lua" / "base64.lua").write_text("return {}\n", encoding="utf-8")
    _write_minimal_manifest_config(tmp_path)

    monkeypatch.chdir(tmp_path)
    update_manifest.create_manifest(replace=True)

    root = Et.parse(tmp_path / "manifest.xml").getroot()
    runtime_sources = [
        node for node in root.findall("Source") if node.get("part") == "runtime"
    ]
    runtime_files = [node for node in root.findall("File") if node.get("part") == "runtime"]
    default_sources = [
        node for node in root.findall("Source") if node.get("part") == "default"
    ]

    assert default_sources[0].get("url") == (
        "https://raw.githubusercontent.com/PathOfBuildingCommunity/"
        "PathOfBuilding-PoE2/{branch}/"
    )
    assert runtime_sources[0].get("platform") == "win32"
    assert runtime_files
    assert all(node.get("platform") == "win32" for node in runtime_files)
    assert all("runtime" not in node.attrib for node in runtime_files)


def test_manifest_sections_can_target_a_shared_part_with_explicit_platform(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "changelog.txt").write_text("changes\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Launch.lua").write_text("return {}\n", encoding="utf-8")
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "Path of Building").write_text("launcher\n", encoding="utf-8")
    _write_minimal_manifest_config(tmp_path, "runtime-macos")
    manifest_cfg = tmp_path / "manifest.cfg"
    manifest_cfg.write_text(
        manifest_cfg.read_text(encoding="utf-8").replace(
            "[runtime-macos]\n",
            "[runtime-macos]\npart = runtime\nplatform = macos\n",
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    update_manifest.create_manifest(replace=True)

    root = Et.parse(tmp_path / "manifest.xml").getroot()
    runtime_sources = [
        node for node in root.findall("Source") if node.get("part") == "runtime"
    ]
    runtime_files = [node for node in root.findall("File") if node.get("part") == "runtime"]

    assert runtime_sources[0].get("platform") == "macos"
    assert runtime_files[0].get("platform") == "macos"


def test_manifest_sections_can_scope_runtime_by_architecture(tmp_path, monkeypatch) -> None:
    (tmp_path / "changelog.txt").write_text("changes\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Launch.lua").write_text("return {}\n", encoding="utf-8")
    (tmp_path / "runtime-macos-arm64").mkdir()
    (tmp_path / "runtime-macos-arm64" / "PathOfBuilding-PoE2").write_text(
        "launcher\n", encoding="utf-8"
    )
    _write_minimal_manifest_config(
        tmp_path, "runtime-macos-arm64", "runtime-macos-arm64"
    )
    manifest_cfg = tmp_path / "manifest.cfg"
    manifest_cfg.write_text(
        manifest_cfg.read_text(encoding="utf-8").replace(
            "[runtime-macos-arm64]\n",
            "[runtime-macos-arm64]\npart = runtime\nplatform = macos\narchitecture = arm64\n",
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    update_manifest.create_manifest(replace=True)

    root = Et.parse(tmp_path / "manifest.xml").getroot()
    runtime_sources = [
        node for node in root.findall("Source") if node.get("part") == "runtime"
    ]
    runtime_files = [node for node in root.findall("File") if node.get("part") == "runtime"]

    assert runtime_sources[0].get("platform") == "macos"
    assert runtime_sources[0].get("architecture") == "arm64"
    assert runtime_files[0].get("platform") == "macos"
    assert runtime_files[0].get("architecture") == "arm64"


def test_manifest_sections_normalize_explicit_platform_and_architecture_aliases(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "changelog.txt").write_text("changes\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Launch.lua").write_text("return {}\n", encoding="utf-8")
    (tmp_path / "runtime-darwin-arm64").mkdir()
    (tmp_path / "runtime-darwin-arm64" / "PathOfBuilding-PoE2").write_text(
        "launcher\n", encoding="utf-8"
    )
    _write_minimal_manifest_config(
        tmp_path, "runtime-darwin-arm64", "runtime-darwin-arm64"
    )
    manifest_cfg = tmp_path / "manifest.cfg"
    manifest_cfg.write_text(
        manifest_cfg.read_text(encoding="utf-8").replace(
            "[runtime-darwin-arm64]\n",
            "[runtime-darwin-arm64]\npart = runtime\nplatform = Darwin\narchitecture = aarch64\n",
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    update_manifest.create_manifest(replace=True)

    root = Et.parse(tmp_path / "manifest.xml").getroot()
    runtime_sources = [
        node for node in root.findall("Source") if node.get("part") == "runtime"
    ]
    runtime_files = [node for node in root.findall("File") if node.get("part") == "runtime"]

    assert runtime_sources[0].get("platform") == "macos"
    assert runtime_sources[0].get("architecture") == "arm64"
    assert runtime_files[0].get("platform") == "macos"
    assert runtime_files[0].get("architecture") == "arm64"


@pytest.mark.parametrize(
    ("replacement", "message"),
    [
        (
            "[runtime-macos]\npart = runtime\nplatform = ../macos\n",
            "Unsafe manifest platform",
        ),
        (
            "[runtime-macos]\npart = runtime\nplatform = macos\narchitecture = ../arm64\n",
            "Unsafe manifest architecture",
        ),
    ],
)
def test_manifest_rejects_unsafe_explicit_target_labels(
    tmp_path, monkeypatch, replacement, message
) -> None:
    (tmp_path / "changelog.txt").write_text("changes\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Launch.lua").write_text("return {}\n", encoding="utf-8")
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "PathOfBuilding-PoE2").write_text(
        "launcher\n", encoding="utf-8"
    )
    _write_minimal_manifest_config(tmp_path, "runtime-macos")
    manifest_cfg = tmp_path / "manifest.cfg"
    manifest_cfg.write_text(
        manifest_cfg.read_text(encoding="utf-8").replace(
            "[runtime-macos]\n",
            replacement,
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match=message):
        update_manifest.create_manifest(replace=True)


def test_runtime_target_directories_emit_sources_without_files(tmp_path, monkeypatch) -> None:
    (tmp_path / "changelog.txt").write_text("changes\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Launch.lua").write_text("return {}\n", encoding="utf-8")
    (tmp_path / "runtime").mkdir()
    _write_minimal_manifest_config(tmp_path)
    manifest_cfg = tmp_path / "manifest.cfg"
    manifest_cfg.write_text(
        manifest_cfg.read_text(encoding="utf-8").replace(
            "[runtime]\n",
            "[runtime]\ndiscover-targets = true\ntarget-directories = macos-arm64\n",
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    update_manifest.create_manifest(replace=True)

    root = Et.parse(tmp_path / "manifest.xml").getroot()
    runtime_sources = [
        node for node in root.findall("Source") if node.get("part") == "runtime"
    ]
    runtime_files = [node for node in root.findall("File") if node.get("part") == "runtime"]

    assert len(runtime_sources) == 2
    assert runtime_sources[1].get("platform") == "macos"
    assert runtime_sources[1].get("architecture") == "arm64"
    assert runtime_sources[1].get("url").endswith("/runtime/macos-arm64/")
    assert not runtime_files


def test_runtime_targets_are_discovered_from_platform_arch_directories(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "changelog.txt").write_text("changes\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Launch.lua").write_text("return {}\n", encoding="utf-8")
    (tmp_path / "runtime" / "freebsd-riscv64").mkdir(parents=True)
    (tmp_path / "runtime" / "freebsd-riscv64" / "PathOfBuilding-PoE2").write_text(
        "launcher\n", encoding="utf-8"
    )
    _write_minimal_manifest_config(tmp_path)
    manifest_cfg = tmp_path / "manifest.cfg"
    manifest_cfg.write_text(
        manifest_cfg.read_text(encoding="utf-8").replace(
            "[runtime]\n",
            "[runtime]\ndiscover-targets = true\n",
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    update_manifest.create_manifest(replace=True)

    root = Et.parse(tmp_path / "manifest.xml").getroot()
    runtime_sources = [
        node for node in root.findall("Source") if node.get("part") == "runtime"
    ]
    runtime_files = [node for node in root.findall("File") if node.get("part") == "runtime"]

    assert runtime_sources[1].get("platform") == "freebsd"
    assert runtime_sources[1].get("architecture") == "riscv64"
    assert runtime_sources[1].get("url").endswith("/runtime/freebsd-riscv64/")
    assert runtime_files[0].get("platform") == "freebsd"
    assert runtime_files[0].get("architecture") == "riscv64"


def test_runtime_target_directory_aliases_are_normalized(
    tmp_path, monkeypatch
) -> None:
    (tmp_path / "changelog.txt").write_text("changes\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Launch.lua").write_text("return {}\n", encoding="utf-8")
    (tmp_path / "runtime").mkdir()
    _write_minimal_manifest_config(tmp_path)
    manifest_cfg = tmp_path / "manifest.cfg"
    manifest_cfg.write_text(
        manifest_cfg.read_text(encoding="utf-8").replace(
            "[runtime]\n",
            "[runtime]\ndiscover-targets = true\ntarget-directories = armhf-linux\n",
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    update_manifest.create_manifest(replace=True)

    root = Et.parse(tmp_path / "manifest.xml").getroot()
    runtime_sources = [
        node for node in root.findall("Source") if node.get("part") == "runtime"
    ]
    runtime_files = [node for node in root.findall("File") if node.get("part") == "runtime"]

    assert runtime_sources[1].get("platform") == "linux"
    assert runtime_sources[1].get("architecture") == "armv7"
    assert runtime_sources[1].get("url").endswith("/runtime/linux-armv7/")
    assert not runtime_files
