# cspell:ignore arcname simplegraphic oldmodule riscv armv
import io
import json
import os
import pathlib
import subprocess
import tarfile

import pytest


def _write_tar(path: pathlib.Path, members: dict[str, str]) -> None:
    with tarfile.open(path, "w") as archive:
        for name, content in members.items():
            source = path.parent / name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(content, encoding="utf-8")
            archive.add(source, arcname=name)


def _write_tar_with_member(path: pathlib.Path, member: tarfile.TarInfo) -> None:
    with tarfile.open(path, "w") as archive:
        if member.isfile():
            data = b"unsafe"
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        else:
            archive.addfile(member)


def test_installs_legacy_windows_archive_to_runtime_root(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    asset_dir.mkdir()
    _write_tar(
        asset_dir / "SimpleGraphicDLLs-x64-windows.tar",
        {"SimpleGraphic.dll": "windows runtime"},
    )

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        check=True,
        env=env,
    )

    assert (runtime_root / "SimpleGraphic.dll").read_text(encoding="utf-8") == "windows runtime"


def test_installs_native_platform_arch_archive_to_target_dir(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    asset_dir.mkdir()
    _write_tar(
        asset_dir / "PathOfBuildingRuntime-macos-arm64.tar",
        {"libSimpleGraphic.dylib": "macos runtime"},
    )

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        check=True,
        env=env,
    )

    assert (
        runtime_root / "macos-arm64" / "libSimpleGraphic.dylib"
    ).read_text(encoding="utf-8") == "macos runtime"


def test_installs_launcher_and_simplegraphic_archives_into_same_target(
    tmp_path,
) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    target_dir = runtime_root / "macos-arm64"
    asset_dir.mkdir()
    target_dir.mkdir(parents=True)
    (target_dir / "stale.dylib").write_text("old dependency", encoding="utf-8")
    _write_tar(
        asset_dir / "PathOfBuildingRuntime-macos-arm64.tar",
        {"PathOfBuilding-PoE2": "launcher runtime"},
    )
    _write_tar(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        {"libSimpleGraphic.dylib": "simplegraphic runtime"},
    )

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        check=True,
        env=env,
    )

    assert (
        runtime_root / "macos-arm64" / "PathOfBuilding-PoE2"
    ).read_text(encoding="utf-8") == "launcher runtime"
    assert (
        runtime_root / "macos-arm64" / "libSimpleGraphic.dylib"
    ).read_text(encoding="utf-8") == "simplegraphic runtime"
    assert not (runtime_root / "macos-arm64" / "stale.dylib").exists()


def test_simplegraphic_only_update_preserves_existing_launcher(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    target_dir = runtime_root / "macos-arm64"
    asset_dir.mkdir()
    target_dir.mkdir(parents=True)
    (target_dir / "PathOfBuilding-PoE2").write_text("existing launcher", encoding="utf-8")
    (target_dir / "oldmodule.so").write_text("old module", encoding="utf-8")
    (target_dir / "unowned-cache.dat").write_text("not simplegraphic-owned", encoding="utf-8")
    (target_dir / "SimpleGraphicRuntime.json").write_text(
        json.dumps(
            {
                "entryLibrary": "libSimpleGraphic.dylib",
                "luaModules": ["oldmodule.so"],
                "files": [
                    "SimpleGraphicRuntime.json",
                    "libSimpleGraphic.dylib",
                    "oldmodule.so",
                ],
            }
        ),
        encoding="utf-8",
    )
    (target_dir / "libSimpleGraphic.dylib").write_text("old runtime", encoding="utf-8")
    _write_tar(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        {
            "SimpleGraphicRuntime.json": json.dumps(
                {
                    "entryLibrary": "libSimpleGraphic.dylib",
                    "luaModules": [],
                    "files": ["SimpleGraphicRuntime.json", "libSimpleGraphic.dylib"],
                }
            ),
            "libSimpleGraphic.dylib": "new runtime",
        },
    )

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        check=True,
        env=env,
    )

    assert (target_dir / "PathOfBuilding-PoE2").read_text(encoding="utf-8") == "existing launcher"
    assert (target_dir / "libSimpleGraphic.dylib").read_text(encoding="utf-8") == "new runtime"
    assert not (target_dir / "oldmodule.so").exists()
    assert (target_dir / "unowned-cache.dat").read_text(encoding="utf-8") == "not simplegraphic-owned"


def test_installs_native_arch_platform_archive_to_target_dir(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    asset_dir.mkdir()
    _write_tar(
        asset_dir / "SimpleGraphicRuntime-x64-linux.tar",
        {"libSimpleGraphic.so": "linux runtime"},
    )

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        check=True,
        env=env,
    )

    assert (
        runtime_root / "linux-x64" / "libSimpleGraphic.so"
    ).read_text(encoding="utf-8") == "linux runtime"


def test_installs_native_archive_with_platform_and_arch_aliases(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    asset_dir.mkdir()
    _write_tar(
        asset_dir / "PathOfBuildingRuntime-darwin-aarch64.tar",
        {"libSimpleGraphic.dylib": "aliased runtime"},
    )

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        check=True,
        env=env,
    )

    assert (
        runtime_root / "macos-arm64" / "libSimpleGraphic.dylib"
    ).read_text(encoding="utf-8") == "aliased runtime"


def test_installs_native_archive_for_generic_future_target(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    asset_dir.mkdir()
    _write_tar(
        asset_dir / "SimpleGraphicRuntime-riscv64-freebsd.tar",
        {"libSimpleGraphic.so": "future runtime"},
    )

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        check=True,
        env=env,
    )

    assert (
        runtime_root / "freebsd-riscv64" / "libSimpleGraphic.so"
    ).read_text(encoding="utf-8") == "future runtime"


def test_installs_native_armv7_archive_from_arch_platform_name(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    asset_dir.mkdir()
    _write_tar(
        asset_dir / "SimpleGraphicRuntime-armv7-linux.tar",
        {"libSimpleGraphic.so": "armv7 runtime"},
    )

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        check=True,
        env=env,
    )

    assert (
        runtime_root / "linux-armv7" / "libSimpleGraphic.so"
    ).read_text(encoding="utf-8") == "armv7 runtime"


def test_installs_native_windows_arm64ec_archive_from_arch_platform_name(
    tmp_path,
) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    asset_dir.mkdir()
    _write_tar(
        asset_dir / "SimpleGraphicRuntime-arm64ec-windows.tar",
        {"SimpleGraphic.dll": "windows arm64ec runtime"},
    )

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        check=True,
        env=env,
    )

    assert (
        runtime_root / "win32-arm64ec" / "SimpleGraphic.dll"
    ).read_text(encoding="utf-8") == "windows arm64ec runtime"


def test_installs_native_riscv32_archive_from_arch_platform_name(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    asset_dir.mkdir()
    _write_tar(
        asset_dir / "SimpleGraphicRuntime-riscv32-freebsd.tar",
        {"libSimpleGraphic.so": "riscv32 runtime"},
    )

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        check=True,
        env=env,
    )

    assert (
        runtime_root / "freebsd-riscv32" / "libSimpleGraphic.so"
    ).read_text(encoding="utf-8") == "riscv32 runtime"


def test_rejects_archive_with_parent_directory_member(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    asset_dir.mkdir()
    member = tarfile.TarInfo("../outside.txt")
    member.type = tarfile.REGTYPE
    _write_tar_with_member(asset_dir / "SimpleGraphicRuntime-macos-arm64.tar", member)

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    result = subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "Unsafe path" in result.stderr
    assert not (tmp_path / "outside.txt").exists()


def test_rejects_archive_with_absolute_member(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    asset_dir.mkdir()
    member = tarfile.TarInfo("/tmp/pob-unsafe.txt")
    member.type = tarfile.REGTYPE
    _write_tar_with_member(asset_dir / "SimpleGraphicRuntime-macos-arm64.tar", member)

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    result = subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "Unsafe path" in result.stderr


def test_rejects_archive_with_unsafe_link(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    asset_dir.mkdir()
    member = tarfile.TarInfo("libSimpleGraphic.dylib")
    member.type = tarfile.SYMTYPE
    member.linkname = "../outside.dylib"
    _write_tar_with_member(asset_dir / "SimpleGraphicRuntime-macos-arm64.tar", member)

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    result = subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "Unsafe link" in result.stderr


def test_rejects_archive_that_would_write_through_existing_symlink(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    outside = tmp_path / "outside"
    target_dir = runtime_root / "macos-arm64"
    asset_dir.mkdir()
    outside.mkdir()
    target_dir.mkdir(parents=True)
    try:
        (target_dir / "linked").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")
    _write_tar(
        asset_dir / "SimpleGraphicRuntime-macos-arm64.tar",
        {"linked/escape.txt": "escape"},
    )

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    result = subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "Unsafe path" in result.stderr
    assert not (outside / "escape.txt").exists()
    assert (target_dir / "linked").is_symlink()


def test_rejects_archive_that_would_write_through_archive_symlink(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    asset_dir.mkdir()
    archive_path = asset_dir / "SimpleGraphicRuntime-macos-arm64.tar"
    with tarfile.open(archive_path, "w") as archive:
        link = tarfile.TarInfo("linked")
        link.type = tarfile.SYMTYPE
        link.linkname = "."
        archive.addfile(link)
        nested = tarfile.TarInfo("linked/escape.txt")
        nested.type = tarfile.REGTYPE
        data = b"escape"
        nested.size = len(data)
        archive.addfile(nested, io.BytesIO(data))

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    result = subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "would extract through link linked" in result.stderr
    assert not (runtime_root / "macos-arm64" / "linked" / "escape.txt").exists()


def test_failed_validation_does_not_clear_existing_native_runtime(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    target_dir = runtime_root / "macos-arm64"
    asset_dir.mkdir()
    target_dir.mkdir(parents=True)
    (target_dir / "existing.dylib").write_text("current runtime", encoding="utf-8")
    member = tarfile.TarInfo("../outside.txt")
    member.type = tarfile.REGTYPE
    _write_tar_with_member(asset_dir / "SimpleGraphicRuntime-macos-arm64.tar", member)

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    result = subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "Unsafe path" in result.stderr
    assert (target_dir / "existing.dylib").read_text(encoding="utf-8") == "current runtime"


def test_rejects_archive_with_special_member_type(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    asset_dir = tmp_path / "assets"
    runtime_root = tmp_path / "runtime"
    asset_dir.mkdir()
    member = tarfile.TarInfo("runtime-device")
    member.type = tarfile.FIFOTYPE
    _write_tar_with_member(asset_dir / "SimpleGraphicRuntime-macos-arm64.tar", member)

    env = os.environ.copy()
    env["POB_RUNTIME_ROOT"] = str(runtime_root)
    result = subprocess.run(
        [str(repo_root / "scripts" / "install-runtime-assets.sh"), str(asset_dir)],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "Unsafe member type" in result.stderr
