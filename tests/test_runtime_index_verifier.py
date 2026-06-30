# cspell:ignore unindexed simplegraphic riscv
import hashlib
import io
import json
import pathlib
import subprocess
import sys
import tarfile


def _runtime_target_from_archive_name(path: pathlib.Path) -> tuple[str, str, str]:
    name = path.name
    for suffix in (".tar.gz", ".tgz", ".tar"):
        if name.endswith(suffix):
            target = name.removeprefix("SimpleGraphicRuntime-")[: -len(suffix)]
            break
    else:
        target = path.stem.removeprefix("SimpleGraphicRuntime-")
    platform, architecture = target.rsplit("-", 1)
    return target, platform, architecture


def _write_runtime_archive(
    path: pathlib.Path,
    content: bytes,
    manifest_overrides: dict | None = None,
    extra_members: list[tarfile.TarInfo | tuple[tarfile.TarInfo, bytes]] | None = None,
) -> None:
    target, platform, architecture = _runtime_target_from_archive_name(path)
    manifest = {
        "schemaVersion": 1,
        "name": "SimpleGraphic",
        "target": target,
        "platform": platform,
        "architecture": architecture,
        "buildType": "Release",
        "layout": "flat",
        "entryLibrary": "libSimpleGraphic.dylib",
        "entrypoints": ["RunLuaFileAsWin", "RunLuaFileAsConsole"],
        "luaModules": ["lcurl.so", "lua-utf8.so", "socket.so", "lzip.so"],
    }
    member_names = {
        "SimpleGraphicRuntime.json",
        manifest["entryLibrary"],
        *manifest["luaModules"],
    }
    for member in extra_members or []:
        member_info = member[0] if isinstance(member, tuple) else member
        member_names.add(member_info.name)
    manifest["files"] = sorted(member_names)
    if manifest_overrides:
        manifest.update(manifest_overrides)

    mode = "w:gz" if path.name.endswith((".tar.gz", ".tgz")) else "w"
    with tarfile.open(path, mode) as archive:
        manifest_data = json.dumps(manifest).encode("utf-8")
        manifest_member = tarfile.TarInfo("SimpleGraphicRuntime.json")
        manifest_member.size = len(manifest_data)
        archive.addfile(manifest_member, io.BytesIO(manifest_data))

        for file_name in [manifest["entryLibrary"], *manifest["luaModules"]]:
            member = tarfile.TarInfo(file_name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))

        for member in extra_members or []:
            if isinstance(member, tuple):
                member_info, member_data = member
                member_info.size = len(member_data)
                archive.addfile(member_info, io.BytesIO(member_data))
            else:
                archive.addfile(member)


def _write_asset(
    path: pathlib.Path,
    content: bytes,
    manifest_overrides: dict | None = None,
    extra_members: list[tarfile.TarInfo | tuple[tarfile.TarInfo, bytes]] | None = None,
) -> dict:
    if path.name.startswith("SimpleGraphicRuntime-"):
        _write_runtime_archive(path, content, manifest_overrides, extra_members)
    else:
        path.write_bytes(content)
    archive_content = path.read_bytes()
    target, platform, architecture = (
        _runtime_target_from_archive_name(path)
        if path.name.startswith("SimpleGraphicRuntime-")
        else ("macos-arm64", "macos", "arm64")
    )
    return {
        "fileName": path.name,
        "target": target,
        "platform": platform,
        "architecture": architecture,
        "buildType": "Release",
        "layout": "flat",
        "entryLibrary": "libSimpleGraphic.dylib",
        "entrypoints": ["RunLuaFileAsWin", "RunLuaFileAsConsole"],
        "luaModules": ["lcurl.so", "lua-utf8.so", "socket.so", "lzip.so"],
        "files": [
            "SimpleGraphicRuntime.json",
            "lcurl.so",
            "libSimpleGraphic.dylib",
            "lua-utf8.so",
            "lzip.so",
            "socket.so",
        ],
        "size": path.stat().st_size,
        "sha256": hashlib.sha256(archive_content).hexdigest(),
    }


def _write_index(path: pathlib.Path, runtime_entries: list[dict], legacy_entries: list[dict] | None = None) -> None:
    index = {
        "schemaVersion": 1,
        "name": "SimpleGraphic",
        "runtimeArchives": runtime_entries,
    }
    if legacy_entries is not None:
        index["legacyArchives"] = legacy_entries
    path.write_text(json.dumps(index), encoding="utf-8")


def _run_verifier(asset_dir: pathlib.Path, index_path: pathlib.Path) -> subprocess.CompletedProcess[str]:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    return subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "verify-runtime-index.py"),
            str(asset_dir),
            str(index_path),
        ],
        capture_output=True,
        text=True,
    )


def test_verify_runtime_index_accepts_indexed_archives_and_ignores_launcher_assets(
    tmp_path,
) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    runtime_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        b"macos runtime",
    )
    legacy_entry = _write_asset(
        asset_dir / "SimpleGraphicDLLs-x64-windows.tar",
        b"legacy runtime",
    )
    legacy_entry.update(
        {
            "target": "win32-x64",
            "platform": "win32",
            "architecture": "x64",
            "mode": "legacy-windows-runtime",
        }
    )
    (asset_dir / "PathOfBuildingRuntime-macos-arm64.tar").write_bytes(
        b"launcher runtime"
    )
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry], [legacy_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 0, result.stderr
    assert "Verified 1 SimpleGraphic runtime archive(s)" in result.stdout


def test_verify_runtime_index_rejects_sha256_mismatch(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    runtime_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        b"macos runtime",
    )
    runtime_entry["sha256"] = "0" * 64
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "SimpleGraphicRuntime-macos-arm64.tar sha256 mismatch" in result.stderr


def test_verify_runtime_index_rejects_missing_indexed_archive(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(
        index_path,
        [
            {
                "fileName": "SimpleGraphicRuntime-macos-arm64.tar",
                "target": "macos-arm64",
                "platform": "macos",
                "architecture": "arm64",
                "buildType": "Release",
                "layout": "flat",
                "entryLibrary": "libSimpleGraphic.dylib",
                "entrypoints": ["RunLuaFileAsWin", "RunLuaFileAsConsole"],
                "luaModules": ["lcurl.so", "lua-utf8.so", "socket.so", "lzip.so"],
                "files": [
                    "SimpleGraphicRuntime.json",
                    "lcurl.so",
                    "libSimpleGraphic.dylib",
                    "lua-utf8.so",
                    "lzip.so",
                    "socket.so",
                ],
                "size": 10,
                "sha256": "0" * 64,
            }
        ],
    )

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "indexed runtime archive is missing: SimpleGraphicRuntime-macos-arm64.tar" in result.stderr


def test_verify_runtime_index_rejects_unindexed_simplegraphic_archive(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    runtime_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        b"macos runtime",
    )
    (asset_dir / "SimpleGraphicRuntime-linux-x64.tar").write_bytes(b"extra runtime")
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "unindexed SimpleGraphic runtime archive(s): SimpleGraphicRuntime-linux-x64.tar" in result.stderr


def test_verify_runtime_index_rejects_non_flat_file_name(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(
        index_path,
        [
            {
                "fileName": "../SimpleGraphicRuntime-macos-arm64.tar",
                "target": "macos-arm64",
                "platform": "macos",
                "architecture": "arm64",
                "buildType": "Release",
                "layout": "flat",
                "entryLibrary": "libSimpleGraphic.dylib",
                "entrypoints": ["RunLuaFileAsWin", "RunLuaFileAsConsole"],
                "luaModules": ["lcurl.so", "lua-utf8.so", "socket.so", "lzip.so"],
                "size": 10,
                "sha256": "0" * 64,
            }
        ],
    )

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "must be a flat file name" in result.stderr


def test_verify_runtime_index_rejects_runtime_file_name_with_wrong_prefix(
    tmp_path,
) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    bad_name = asset_dir / "PathOfBuildingRuntime-macos-arm64.tar"
    runtime_entry = _write_asset(bad_name, b"not simplegraphic")
    runtime_entry["fileName"] = bad_name.name
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "does not start with SimpleGraphicRuntime-" in result.stderr


def test_verify_runtime_index_rejects_target_mismatch(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    runtime_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        b"macos runtime",
    )
    runtime_entry["target"] = "linux-arm64"
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "index field runtimeArchives[0].'target' expected 'macos-arm64'" in result.stderr


def test_verify_runtime_index_rejects_embedded_manifest_mismatch(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    runtime_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        b"macos runtime",
        manifest_overrides={"target": "linux-x64", "platform": "linux", "architecture": "x64"},
    )
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "manifest field 'target' expected 'macos-arm64'" in result.stderr


def test_verify_runtime_index_rejects_wrong_known_platform_entry_library(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    runtime_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        b"macos runtime",
        manifest_overrides={
            "entryLibrary": "SimpleGraphic.native",
            "files": [
                "SimpleGraphicRuntime.json",
                "SimpleGraphic.native",
                "lcurl.so",
                "lua-utf8.so",
                "socket.so",
                "lzip.so",
            ],
        },
    )
    runtime_entry["entryLibrary"] = "SimpleGraphic.native"
    runtime_entry["files"] = [
        "SimpleGraphicRuntime.json",
        "SimpleGraphic.native",
        "lcurl.so",
        "lua-utf8.so",
        "socket.so",
        "lzip.so",
    ]
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "entryLibrary expected 'libSimpleGraphic.dylib'" in result.stderr


def test_verify_runtime_index_rejects_extra_entrypoint_metadata(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    entrypoints = ["RunLuaFileAsWin", "RunLuaFileAsConsole", "RunExperimental"]
    runtime_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        b"macos runtime",
        manifest_overrides={"entrypoints": entrypoints},
    )
    runtime_entry["entrypoints"] = entrypoints
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "must list only entrypoints" in result.stderr


def test_verify_runtime_index_rejects_wrong_known_platform_lua_modules(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    modules = ["lcurl.dylib", "lua-utf8.so", "socket.so", "lzip.so"]
    runtime_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        b"macos runtime",
        manifest_overrides={
            "luaModules": modules,
            "files": [
                "SimpleGraphicRuntime.json",
                "libSimpleGraphic.dylib",
                *modules,
            ],
        },
    )
    runtime_entry["luaModules"] = modules
    runtime_entry["files"] = [
        "SimpleGraphicRuntime.json",
        "libSimpleGraphic.dylib",
        *modules,
    ]
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "must list Lua modules" in result.stderr


def test_verify_runtime_index_accepts_future_platform_module_file_names(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    modules = ["lcurl.native", "lua-utf8.native", "socket.native", "lzip.native"]
    system_dependencies = ["libc.so.7", "libthr.so.3"]
    runtime_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-freebsd-riscv64.tar",
        b"future runtime",
        manifest_overrides={
            "entryLibrary": "SimpleGraphic.native",
            "luaModules": modules,
            "systemDependencies": ["LibC.SO.7", "libthr.so.3"],
            "files": [
                "SimpleGraphicRuntime.json",
                "SimpleGraphic.native",
                *modules,
            ],
        },
    )
    runtime_entry.update(
        {
            "entryLibrary": "SimpleGraphic.native",
            "luaModules": modules,
            "systemDependencies": system_dependencies,
            "files": [
                "SimpleGraphicRuntime.json",
                "SimpleGraphic.native",
                *modules,
            ],
        }
    )
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 0, result.stderr
    assert "Verified 1 SimpleGraphic runtime archive(s)" in result.stdout


def test_verify_runtime_index_rejects_system_dependency_metadata_mismatch(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    modules = ["lcurl.native", "lua-utf8.native", "socket.native", "lzip.native"]
    runtime_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-freebsd-riscv64.tar",
        b"future runtime",
        manifest_overrides={
            "entryLibrary": "SimpleGraphic.native",
            "luaModules": modules,
            "systemDependencies": ["libc.so.7"],
            "files": [
                "SimpleGraphicRuntime.json",
                "SimpleGraphic.native",
                *modules,
            ],
        },
    )
    runtime_entry.update(
        {
            "entryLibrary": "SimpleGraphic.native",
            "luaModules": modules,
            "files": [
                "SimpleGraphicRuntime.json",
                "SimpleGraphic.native",
                *modules,
            ],
        }
    )
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "systemDependencies metadata does not match index" in result.stderr


def test_verify_runtime_index_rejects_unsafe_system_dependency_name(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    runtime_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        b"macos runtime",
    )
    runtime_entry["systemDependencies"] = ["../libbad.dylib"]
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "must be a flat file name" in result.stderr


def test_verify_runtime_index_rejects_required_symlink_runtime_files(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    archive_path = asset_dir / "SimpleGraphicRuntime-macos-arm64.tar"
    modules = ["lcurl.so", "lua-utf8.so", "socket.so", "lzip.so"]
    manifest = {
        "schemaVersion": 1,
        "name": "SimpleGraphic",
        "target": "macos-arm64",
        "platform": "macos",
        "architecture": "arm64",
        "buildType": "Release",
        "layout": "flat",
        "entryLibrary": "libSimpleGraphic.dylib",
        "entrypoints": ["RunLuaFileAsWin", "RunLuaFileAsConsole"],
        "luaModules": modules,
        "files": [
            "SimpleGraphicRuntime.json",
            "libSimpleGraphic.dylib",
            *modules,
        ],
    }
    with tarfile.open(archive_path, "w") as archive:
        manifest_data = json.dumps(manifest).encode("utf-8")
        manifest_member = tarfile.TarInfo("SimpleGraphicRuntime.json")
        manifest_member.size = len(manifest_data)
        archive.addfile(manifest_member, io.BytesIO(manifest_data))
        link = tarfile.TarInfo("libSimpleGraphic.dylib")
        link.type = tarfile.SYMTYPE
        link.linkname = "libSimpleGraphic.real.dylib"
        archive.addfile(link)
        for module in modules:
            module_data = b"module"
            member = tarfile.TarInfo(module)
            member.size = len(module_data)
            archive.addfile(member, io.BytesIO(module_data))
    content = archive_path.read_bytes()
    runtime_entry = {
        "fileName": archive_path.name,
        "target": "macos-arm64",
        "platform": "macos",
        "architecture": "arm64",
        "buildType": "Release",
        "layout": "flat",
        "entryLibrary": "libSimpleGraphic.dylib",
        "entrypoints": ["RunLuaFileAsWin", "RunLuaFileAsConsole"],
        "luaModules": modules,
        "files": manifest["files"],
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "is missing required regular files: libSimpleGraphic.dylib" in result.stderr


def test_verify_runtime_index_rejects_unsafe_runtime_archive_link(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    link = tarfile.TarInfo("linked")
    link.type = tarfile.SYMTYPE
    link.linkname = "../outside"
    runtime_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        b"macos runtime",
        extra_members=[link],
    )
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "unsafe link in SimpleGraphicRuntime-macos-arm64.tar: linked -> ../outside" in result.stderr


def test_verify_runtime_index_rejects_duplicate_entries(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    runtime_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        b"macos runtime",
    )
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [runtime_entry, dict(runtime_entry)])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "duplicate archive entry: SimpleGraphicRuntime-macos-arm64.tar" in result.stderr


def test_verify_runtime_index_rejects_duplicate_runtime_target(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    tar_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        b"macos runtime tar",
    )
    tgz_entry = _write_asset(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tgz",
        b"macos runtime tgz",
    )
    index_path = asset_dir / "SimpleGraphicRuntime-index.json"
    _write_index(index_path, [tar_entry, tgz_entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "duplicate runtime target: macos-arm64" in result.stderr
