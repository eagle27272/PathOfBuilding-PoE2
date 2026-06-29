import pathlib
import xml.etree.ElementTree as Et

import update_manifest


def _write_minimal_manifest_config(root: pathlib.Path, runtime_section: str = "runtime") -> None:
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
        "path = runtime\n"
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
