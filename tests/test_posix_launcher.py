import os
import pathlib
import shutil
import stat
import subprocess

import pytest


def test_posix_launcher_prefers_native_runtime(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    launcher = tmp_path / "Path of Building-PoE2.command"
    shutil.copy(repo_root / "Path of Building-PoE2.command", launcher)
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

    runtime_dir = tmp_path / "runtime" / "macos-arm64"
    runtime_dir.mkdir(parents=True)
    runtime = runtime_dir / "PathOfBuilding-PoE2"
    runtime.write_text("#!/bin/sh\necho native \"$@\"\n", encoding="utf-8")
    runtime.chmod(runtime.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["POB_RUNTIME_PLATFORM"] = "macos"
    env["POB_RUNTIME_ARCHITECTURE"] = "arm64"
    result = subprocess.run(
        [str(launcher), "--example"],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.stdout.strip() == "native --example"


def test_posix_launcher_sets_dyld_library_path_for_macos_native_runtime(tmp_path) -> None:
    compiler = shutil.which("cc")
    if not compiler:
        pytest.skip("cc is required to build the native environment probe")

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    launcher = tmp_path / "Path of Building-PoE2.command"
    shutil.copy(repo_root / "Path of Building-PoE2.command", launcher)
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

    runtime_dir = tmp_path / "runtime" / "macos-arm64"
    runtime_dir.mkdir(parents=True)
    runtime = runtime_dir / "PathOfBuilding-PoE2"
    probe = tmp_path / "print_dyld.c"
    probe.write_text(
        "#include <stdio.h>\n"
        "#include <stdlib.h>\n"
        "int main(void) { const char* value = getenv(\"DYLD_LIBRARY_PATH\"); puts(value ? value : \"\"); return 0; }\n",
        encoding="utf-8",
    )
    subprocess.run([compiler, str(probe), "-o", str(runtime)], check=True)

    env = os.environ.copy()
    env["POB_RUNTIME_PLATFORM"] = "macos"
    env["POB_RUNTIME_ARCHITECTURE"] = "arm64"
    env.pop("DYLD_LIBRARY_PATH", None)
    result = subprocess.run(
        [str(launcher)],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.stdout.strip() == str(runtime_dir)


def test_posix_launcher_normalizes_platform_and_architecture_aliases(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    launcher = tmp_path / "Path of Building-PoE2.command"
    shutil.copy(repo_root / "Path of Building-PoE2.command", launcher)
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

    runtime_dir = tmp_path / "runtime" / "macos-arm64"
    runtime_dir.mkdir(parents=True)
    runtime = runtime_dir / "PathOfBuilding-PoE2"
    runtime.write_text("#!/bin/sh\necho normalized\n", encoding="utf-8")
    runtime.chmod(runtime.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["POB_RUNTIME_PLATFORM"] = "Darwin"
    env["POB_RUNTIME_ARCHITECTURE"] = "aarch64"
    result = subprocess.run(
        [str(launcher)],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.stdout.strip() == "normalized"


def test_posix_launcher_accepts_generic_platform_targets(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    launcher = tmp_path / "Path of Building-PoE2.command"
    shutil.copy(repo_root / "Path of Building-PoE2.command", launcher)
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

    runtime_dir = tmp_path / "runtime" / "freebsd-riscv64"
    runtime_dir.mkdir(parents=True)
    runtime = runtime_dir / "PathOfBuilding-PoE2"
    runtime.write_text("#!/bin/sh\necho future-target\n", encoding="utf-8")
    runtime.chmod(runtime.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["POB_RUNTIME_PLATFORM"] = "FreeBSD"
    env["POB_RUNTIME_ARCHITECTURE"] = "riscv64"
    result = subprocess.run(
        [str(launcher)],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.stdout.strip() == "future-target"


def test_posix_launcher_normalizes_armv7_alias_to_armv7_target(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    launcher = tmp_path / "Path of Building-PoE2.command"
    shutil.copy(repo_root / "Path of Building-PoE2.command", launcher)
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

    runtime_dir = tmp_path / "runtime" / "linux-armv7"
    runtime_dir.mkdir(parents=True)
    runtime = runtime_dir / "PathOfBuilding-PoE2"
    runtime.write_text("#!/bin/sh\necho armv7-target\n", encoding="utf-8")
    runtime.chmod(runtime.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["POB_RUNTIME_PLATFORM"] = "Linux"
    env["POB_RUNTIME_ARCHITECTURE"] = "armv7a"
    result = subprocess.run(
        [str(launcher)],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.stdout.strip() == "armv7-target"


def test_posix_launcher_accepts_decoded_windows_runtime_fallback(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    launcher = tmp_path / "Path of Building-PoE2.command"
    shutil.copy(repo_root / "Path of Building-PoE2.command", launcher)
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    runtime = runtime_dir / "Path of Building-PoE2.exe"
    runtime.write_text("#!/bin/sh\necho decoded-windows \"$@\"\n", encoding="utf-8")
    runtime.chmod(runtime.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["POB_RUNTIME_PLATFORM"] = "windows"
    env["POB_RUNTIME_ARCHITECTURE"] = "amd64"
    result = subprocess.run(
        [str(launcher), "--example"],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.stdout.strip() == "decoded-windows --example"


def test_posix_launcher_requires_explicit_wine_fallback(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    launcher = tmp_path / "Path of Building-PoE2.command"
    shutil.copy(repo_root / "Path of Building-PoE2.command", launcher)
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["POB_RUNTIME_PLATFORM"] = "macos"
    env["POB_RUNTIME_ARCHITECTURE"] = "arm64"
    env.pop("POB_WINE", None)
    env.pop("POB_ALLOW_WINE", None)
    result = subprocess.run(
        [str(launcher)],
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode == 1
    assert "No native Path of Building runtime was found for macos/arm64" in result.stderr
    assert "Set POB_WINE=/path/to/wine or POB_ALLOW_WINE=1" in result.stderr


def test_posix_launcher_rejects_unsafe_runtime_labels(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    launcher = tmp_path / "Path of Building-PoE2.command"
    shutil.copy(repo_root / "Path of Building-PoE2.command", launcher)
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["POB_RUNTIME_PLATFORM"] = "../macos"
    env["POB_RUNTIME_ARCHITECTURE"] = "arm64"
    result = subprocess.run(
        [str(launcher)],
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode == 2
    assert "Invalid runtime target labels" in result.stderr
