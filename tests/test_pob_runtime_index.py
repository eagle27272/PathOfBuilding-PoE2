import hashlib
import io
import json
import pathlib
import subprocess
import sys
import tarfile


def _write_launcher_archive(
    path: pathlib.Path,
    launcher_name: str = "PathOfBuilding-PoE2",
    executable: bool = True,
) -> None:
    data = b"#!/bin/sh\n"
    with tarfile.open(path, "w") as archive:
        member = tarfile.TarInfo(launcher_name)
        member.mode = 0o755 if executable else 0o644
        member.size = len(data)
        archive.addfile(member, io.BytesIO(data))
        lua_member = tarfile.TarInfo("lua/xml.lua")
        lua_data = b"return {}\n"
        lua_member.mode = 0o644
        lua_member.size = len(lua_data)
        archive.addfile(lua_member, io.BytesIO(lua_data))


def _write_launcher_archive_with_members(
    path: pathlib.Path,
    members: list[tarfile.TarInfo | tuple[tarfile.TarInfo, bytes]],
) -> None:
    data = b"#!/bin/sh\n"
    with tarfile.open(path, "w") as archive:
        launcher = tarfile.TarInfo("PathOfBuilding-PoE2")
        launcher.mode = 0o755
        launcher.size = len(data)
        archive.addfile(launcher, io.BytesIO(data))
        for member in members:
            if isinstance(member, tuple):
                member_info, member_data = member
                member_info.size = len(member_data)
                archive.addfile(member_info, io.BytesIO(member_data))
            else:
                archive.addfile(member)


def _symlink_member(name: str, target: str) -> tarfile.TarInfo:
    member = tarfile.TarInfo(name)
    member.type = tarfile.SYMTYPE
    member.linkname = target
    return member


def _launcher_entry(path: pathlib.Path, content: bytes | None = None) -> dict:
    if content is None:
        content = path.read_bytes()
    target = path.name.removeprefix("PathOfBuildingRuntime-").removesuffix(".tar")
    platform, architecture = target.rsplit("-", 1)
    return {
        "fileName": path.name,
        "target": target,
        "platform": platform,
        "architecture": architecture,
        "layout": "runtime-root",
        "entryLauncher": "PathOfBuilding-PoE2.exe" if platform == "win32" else "PathOfBuilding-PoE2",
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _write_index(path: pathlib.Path, entries: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "name": "PathOfBuilding-PoE2",
                "launcherArchives": entries,
            }
        ),
        encoding="utf-8",
    )


def _run_verifier(asset_dir: pathlib.Path, index_path: pathlib.Path) -> subprocess.CompletedProcess[str]:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    return subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "verify-pob-runtime-index.py"),
            str(asset_dir),
            str(index_path),
        ],
        capture_output=True,
        text=True,
    )


def test_write_and_verify_pob_runtime_index(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    _write_launcher_archive(asset_dir / "PathOfBuildingRuntime-macos-arm64.tar")
    _write_launcher_archive(
        asset_dir / "PathOfBuildingRuntime-win32-x64.tar",
        "PathOfBuilding-PoE2.exe",
    )
    index_path = asset_dir / "PathOfBuildingRuntime-index.json"

    write_result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "write-pob-runtime-index.py"),
            "--artifact-dir",
            str(asset_dir),
            "--output",
            str(index_path),
        ],
        capture_output=True,
        text=True,
    )

    assert write_result.returncode == 0, write_result.stderr
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["name"] == "PathOfBuilding-PoE2"
    assert [entry["target"] for entry in index["launcherArchives"]] == [
        "macos-arm64",
        "win32-x64",
    ]

    verify_result = _run_verifier(asset_dir, index_path)
    assert verify_result.returncode == 0, verify_result.stderr
    assert "Verified 2 PathOfBuilding runtime archive(s)" in verify_result.stdout


def test_verify_pob_runtime_index_rejects_unindexed_launcher_archive(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    indexed_archive = asset_dir / "PathOfBuildingRuntime-macos-arm64.tar"
    _write_launcher_archive(indexed_archive)
    _write_launcher_archive(asset_dir / "PathOfBuildingRuntime-linux-x64.tar")
    index_path = asset_dir / "PathOfBuildingRuntime-index.json"
    _write_index(index_path, [_launcher_entry(indexed_archive)])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "unindexed PathOfBuilding runtime archive(s): PathOfBuildingRuntime-linux-x64.tar" in result.stderr


def test_verify_pob_runtime_index_rejects_sha256_mismatch(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    archive_path = asset_dir / "PathOfBuildingRuntime-macos-arm64.tar"
    _write_launcher_archive(archive_path)
    entry = _launcher_entry(archive_path)
    entry["sha256"] = "0" * 64
    index_path = asset_dir / "PathOfBuildingRuntime-index.json"
    _write_index(index_path, [entry])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "PathOfBuildingRuntime-macos-arm64.tar sha256 mismatch" in result.stderr


def test_write_pob_runtime_index_requires_executable_posix_launcher(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    archive_path = tmp_path / "PathOfBuildingRuntime-macos-arm64.tar"
    _write_launcher_archive(archive_path, executable=False)

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "write-pob-runtime-index.py"),
            str(archive_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "PathOfBuilding-PoE2 must be executable" in result.stderr


def test_write_pob_runtime_index_rejects_unsafe_link_target(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    archive_path = tmp_path / "PathOfBuildingRuntime-macos-arm64.tar"
    _write_launcher_archive_with_members(
        archive_path,
        [_symlink_member("linked", "../outside")],
    )

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "write-pob-runtime-index.py"),
            str(archive_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "contains unsafe link: linked -> ../outside" in result.stderr


def test_verify_pob_runtime_index_rejects_archive_member_through_link(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    archive_path = asset_dir / "PathOfBuildingRuntime-macos-arm64.tar"
    nested_file = tarfile.TarInfo("linked/escape.txt")
    _write_launcher_archive_with_members(
        archive_path,
        [
            _symlink_member("linked", "."),
            (nested_file, b"escape\n"),
        ],
    )
    index_path = asset_dir / "PathOfBuildingRuntime-index.json"
    _write_index(index_path, [_launcher_entry(archive_path)])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "would extract through link linked: linked/escape.txt" in result.stderr


def test_verify_pob_runtime_index_rejects_wrong_launcher_name(tmp_path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    archive_path = asset_dir / "PathOfBuildingRuntime-macos-arm64.tar"
    _write_launcher_archive(archive_path, "WrongLauncher")
    index_path = asset_dir / "PathOfBuildingRuntime-index.json"
    _write_index(index_path, [_launcher_entry(archive_path)])

    result = _run_verifier(asset_dir, index_path)

    assert result.returncode == 1
    assert "must contain exactly one PathOfBuilding-PoE2" in result.stderr
