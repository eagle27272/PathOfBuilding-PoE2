import hashlib
import io
import json
import os
import pathlib
import subprocess
import tarfile
import xml.etree.ElementTree as Et


def _write_tar(path: pathlib.Path, members: dict[str, str]) -> None:
    with tarfile.open(path, "w") as archive:
        for name, content in members.items():
            source = path.parent / name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(content, encoding="utf-8")
            archive.add(source, arcname=name)


def _write_launcher_tar(path: pathlib.Path, launcher_name: str = "PathOfBuilding-PoE2") -> None:
    data = b"#!/bin/sh\n"
    with tarfile.open(path, "w") as archive:
        member = tarfile.TarInfo(launcher_name)
        member.mode = 0o755
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))


def _write_simplegraphic_tar(path: pathlib.Path, entry_content: str = "native runtime") -> None:
    target, platform, architecture = _runtime_target_from_archive(path)
    entry_library = "SimpleGraphic.dll" if platform == "win32" else (
        "libSimpleGraphic.dylib" if platform == "macos" else "libSimpleGraphic.so"
    )
    module_ext = ".dll" if platform == "win32" else ".so"
    lua_modules = [
        f"lcurl{module_ext}",
        f"lua-utf8{module_ext}",
        f"socket{module_ext}",
        f"lzip{module_ext}",
    ]
    manifest = {
        "schemaVersion": 1,
        "name": "SimpleGraphic",
        "target": target,
        "platform": platform,
        "architecture": architecture,
        "buildType": "Release",
        "layout": "flat",
        "entryLibrary": entry_library,
        "entrypoints": ["RunLuaFileAsWin", "RunLuaFileAsConsole"],
        "luaModules": lua_modules,
    }
    members = {
        "SimpleGraphicRuntime.json": json.dumps(manifest),
        entry_library: entry_content,
    }
    members.update({module: f"{module} content" for module in lua_modules})
    _write_tar(path, members)


def _runtime_target_from_archive(archive_path: pathlib.Path) -> tuple[str, str, str]:
    target = archive_path.name.removeprefix("SimpleGraphicRuntime-").removesuffix(".tar")
    platform, architecture = target.rsplit("-", 1)
    return target, platform, architecture


def _pob_runtime_target_from_archive(archive_path: pathlib.Path) -> tuple[str, str, str]:
    target = archive_path.name.removeprefix("PathOfBuildingRuntime-").removesuffix(".tar")
    platform, architecture = target.rsplit("-", 1)
    return target, platform, architecture


def _write_runtime_index(asset_dir: pathlib.Path, *archive_paths: pathlib.Path) -> None:
    runtime_archives = []
    for archive_path in archive_paths:
        content = archive_path.read_bytes()
        target, platform, architecture = _runtime_target_from_archive(archive_path)
        runtime_archives.append(
            {
                "fileName": archive_path.name,
                "target": target,
                "platform": platform,
                "architecture": architecture,
                "buildType": "Release",
                "layout": "flat",
                "entryLibrary": "libSimpleGraphic.dylib",
                "entrypoints": ["RunLuaFileAsWin", "RunLuaFileAsConsole"],
                "luaModules": ["lcurl.so", "lua-utf8.so", "socket.so", "lzip.so"],
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )

    index = {
        "schemaVersion": 1,
        "name": "SimpleGraphic",
        "runtimeArchives": runtime_archives,
    }
    (asset_dir / "SimpleGraphicRuntime-index.json").write_text(
        json.dumps(index),
        encoding="utf-8",
    )


def _write_pob_runtime_index(asset_dir: pathlib.Path, *archive_paths: pathlib.Path) -> None:
    launcher_archives = []
    for archive_path in archive_paths:
        content = archive_path.read_bytes()
        target, platform, architecture = _pob_runtime_target_from_archive(archive_path)
        launcher_archives.append(
            {
                "fileName": archive_path.name,
                "target": target,
                "platform": platform,
                "architecture": architecture,
                "layout": "runtime-root",
                "entryLauncher": "PathOfBuilding-PoE2.exe" if platform == "win32" else "PathOfBuilding-PoE2",
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )

    index = {
        "schemaVersion": 1,
        "name": "PathOfBuilding-PoE2",
        "launcherArchives": launcher_archives,
    }
    (asset_dir / "PathOfBuildingRuntime-index.json").write_text(
        json.dumps(index),
        encoding="utf-8",
    )


def _write_minimal_manifest_repo(
    repo_dir: pathlib.Path,
    target_directories: str = "macos-arm64",
) -> None:
    source_update_manifest = pathlib.Path(__file__).resolve().parents[1] / "update_manifest.py"
    (repo_dir / "update_manifest.py").write_text(
        source_update_manifest.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (repo_dir / "manifest.xml").write_text(
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<PoBVersion>\n"
        "\t<Version number='1.0.0' />\n"
        "</PoBVersion>\n",
        encoding="utf-8",
    )
    (repo_dir / "manifest.cfg").write_text(
        "[runtime]\n"
        "path = runtime\n"
        "architecture = x64\n"
        "discover-targets = true\n"
        f"target-directories = {target_directories}\n",
        encoding="utf-8",
    )


def test_import_simplegraphic_runtime_verifies_installs_and_updates_manifest(
    tmp_path,
) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    import_repo = tmp_path / "repo"
    asset_dir = tmp_path / "assets"
    runtime_target = import_repo / "runtime" / "macos-arm64"
    import_repo.mkdir()
    asset_dir.mkdir()
    runtime_target.mkdir(parents=True)
    (runtime_target / "stale.dylib").write_text("old runtime", encoding="utf-8")
    _write_minimal_manifest_repo(import_repo)
    archive_path = asset_dir / "SimpleGraphicRuntime-macos-arm64.tar"
    _write_simplegraphic_tar(archive_path, "native runtime")
    _write_runtime_index(asset_dir, archive_path)

    env = os.environ.copy()
    env["POB_RUNTIME_REPO_DIR"] = str(import_repo)
    subprocess.run(
        [str(repo_root / "scripts" / "import-simplegraphic-runtime.sh"), str(asset_dir)],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    assert not (runtime_target / "stale.dylib").exists()
    assert (runtime_target / "libSimpleGraphic.dylib").read_text(encoding="utf-8") == "native runtime"

    root = Et.parse(import_repo / "manifest.xml").getroot()
    sources = root.findall("Source")
    files = root.findall("File")
    assert any(
        source.get("part") == "runtime"
        and source.get("platform") == "macos"
        and source.get("architecture") == "arm64"
        and source.get("url", "").endswith("/runtime/macos-arm64/")
        for source in sources
    )
    assert any(
        file.get("name") == "libSimpleGraphic.dylib"
        and file.get("part") == "runtime"
        and file.get("platform") == "macos"
        and file.get("architecture") == "arm64"
        for file in files
    )
    assert not any(file.get("name") == "stale.dylib" for file in files)


def test_import_simplegraphic_runtime_combines_launcher_and_graphics_archives(
    tmp_path,
) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    import_repo = tmp_path / "repo"
    asset_dir = tmp_path / "assets"
    runtime_target = import_repo / "runtime" / "macos-arm64"
    import_repo.mkdir()
    asset_dir.mkdir()
    runtime_target.mkdir(parents=True)
    (runtime_target / "stale.dylib").write_text("old runtime", encoding="utf-8")
    _write_minimal_manifest_repo(import_repo)
    launcher_archive = asset_dir / "PathOfBuildingRuntime-macos-arm64.tar"
    simplegraphic_archive = asset_dir / "SimpleGraphicRuntime-macos-arm64.tar"
    _write_launcher_tar(launcher_archive)
    _write_simplegraphic_tar(simplegraphic_archive, "native runtime")
    _write_runtime_index(asset_dir, simplegraphic_archive)
    _write_pob_runtime_index(asset_dir, launcher_archive)

    env = os.environ.copy()
    env["POB_RUNTIME_REPO_DIR"] = str(import_repo)
    subprocess.run(
        [str(repo_root / "scripts" / "import-simplegraphic-runtime.sh"), str(asset_dir)],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    assert not (runtime_target / "stale.dylib").exists()
    assert (runtime_target / "PathOfBuilding-PoE2").read_text(encoding="utf-8") == "#!/bin/sh\n"
    assert (runtime_target / "libSimpleGraphic.dylib").read_text(encoding="utf-8") == "native runtime"

    root = Et.parse(import_repo / "manifest.xml").getroot()
    files = root.findall("File")
    assert any(
        file.get("name") == "PathOfBuilding-PoE2"
        and file.get("part") == "runtime"
        and file.get("platform") == "macos"
        and file.get("architecture") == "arm64"
        for file in files
    )
    assert any(
        file.get("name") == "libSimpleGraphic.dylib"
        and file.get("part") == "runtime"
        and file.get("platform") == "macos"
        and file.get("architecture") == "arm64"
        for file in files
    )


def test_import_simplegraphic_runtime_requires_launcher_runtime_index(
    tmp_path,
) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    import_repo = tmp_path / "repo"
    asset_dir = tmp_path / "assets"
    import_repo.mkdir()
    asset_dir.mkdir()
    _write_minimal_manifest_repo(import_repo)
    launcher_archive = asset_dir / "PathOfBuildingRuntime-macos-arm64.tar"
    simplegraphic_archive = asset_dir / "SimpleGraphicRuntime-macos-arm64.tar"
    _write_launcher_tar(launcher_archive)
    _write_simplegraphic_tar(simplegraphic_archive, "native runtime")
    _write_runtime_index(asset_dir, simplegraphic_archive)

    env = os.environ.copy()
    env["POB_RUNTIME_REPO_DIR"] = str(import_repo)
    result = subprocess.run(
        [str(repo_root / "scripts" / "import-simplegraphic-runtime.sh"), str(asset_dir)],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "PathOfBuilding runtime archives require PathOfBuildingRuntime-index.json" in result.stderr


def test_import_simplegraphic_runtime_installs_multiple_indexed_targets(
    tmp_path,
) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    import_repo = tmp_path / "repo"
    asset_dir = tmp_path / "assets"
    import_repo.mkdir()
    asset_dir.mkdir()
    _write_minimal_manifest_repo(import_repo, "macos-arm64,macos-x64")

    archives = []
    for target, content in (
        ("macos-arm64", "arm runtime"),
        ("macos-x64", "x64 runtime"),
    ):
        runtime_target = import_repo / "runtime" / target
        runtime_target.mkdir(parents=True)
        (runtime_target / "stale.dylib").write_text("old runtime", encoding="utf-8")
        archive_path = asset_dir / f"SimpleGraphicRuntime-{target}.tar"
        _write_simplegraphic_tar(archive_path, content)
        archives.append(archive_path)

    _write_runtime_index(asset_dir, *archives)

    env = os.environ.copy()
    env["POB_RUNTIME_REPO_DIR"] = str(import_repo)
    subprocess.run(
        [str(repo_root / "scripts" / "import-simplegraphic-runtime.sh"), str(asset_dir)],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    root = Et.parse(import_repo / "manifest.xml").getroot()
    files = root.findall("File")
    for target, architecture, content in (
        ("macos-arm64", "arm64", "arm runtime"),
        ("macos-x64", "x64", "x64 runtime"),
    ):
        runtime_target = import_repo / "runtime" / target
        assert not (runtime_target / "stale.dylib").exists()
        assert (runtime_target / "libSimpleGraphic.dylib").read_text(encoding="utf-8") == content
        assert any(
            file.get("name") == "libSimpleGraphic.dylib"
            and file.get("part") == "runtime"
            and file.get("platform") == "macos"
            and file.get("architecture") == architecture
            for file in files
        )
