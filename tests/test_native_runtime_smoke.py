import os
import pathlib
import shutil
import stat
import subprocess
import sys

import pytest


def _host_target() -> tuple[str, str, str]:
    if sys.platform == "darwin":
        platform = "macos"
        library = "libSimpleGraphic.dylib"
    elif sys.platform.startswith("linux"):
        platform = "linux"
        library = "libSimpleGraphic.so"
    else:
        pytest.skip("native smoke test currently exercises POSIX launcher targets")
    machine = os.uname().machine.lower()
    if machine in {"x86_64", "amd64", "x64"}:
        architecture = "x64"
    elif machine in {"arm64", "aarch64"}:
        architecture = "arm64"
    elif machine in {"i386", "i686", "x86"}:
        architecture = "x86"
    elif machine.startswith("armv7") or machine == "armhf":
        architecture = "armv7"
    elif machine.startswith("armv6"):
        architecture = "armv6"
    else:
        architecture = machine
    return platform, architecture, library


def _write_dummy_simplegraphic(source: pathlib.Path) -> None:
    source.write_text(
        '#include <cstdlib>\n'
        '#include <cstdio>\n'
        'extern "C" int RunLuaFileAsWin(int argc, char** argv) {\n'
        '    std::printf("dummy simplegraphic argc=%d argv0=%s\\n", argc, argc > 0 ? argv[0] : "");\n'
        '    std::printf("dummy LUA_PATH=%s\\n", std::getenv("LUA_PATH") ? std::getenv("LUA_PATH") : "");\n'
        '    std::printf("dummy LUA_CPATH=%s\\n", std::getenv("LUA_CPATH") ? std::getenv("LUA_CPATH") : "");\n'
        "    return 42;\n"
        "}\n",
        encoding="utf-8",
    )


def _run_dummy_simplegraphic(tmp_path: pathlib.Path, directive: str) -> subprocess.CompletedProcess[str]:
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("c++ is required to build the dummy SimpleGraphic library")

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    platform, architecture, library_name = _host_target()
    runtime_dir = tmp_path / "runtime" / f"{platform}-{architecture}"
    runtime_dir.mkdir(parents=True)
    shutil.copy(repo_root / "Path of Building-PoE2.command", tmp_path / "Path of Building-PoE2.command")
    (tmp_path / "Path of Building-PoE2.command").chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    (tmp_path / "Launch.lua").write_text(f"#@ {directive}\n", encoding="utf-8")

    env = os.environ.copy()
    env["POB_RUNTIME_PLATFORM"] = platform
    env["POB_RUNTIME_ARCHITECTURE"] = architecture
    env["POB_RUNTIME_OUT_DIR"] = str(runtime_dir)
    env["POB_LAUNCHER_BUILD_DIR"] = str(tmp_path / "build")
    subprocess.run(
        [str(repo_root / "scripts" / "package-native-runtime.sh")],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    dummy_source = tmp_path / "dummy_simplegraphic.cpp"
    _write_dummy_simplegraphic(dummy_source)
    if platform == "macos":
        compile_cmd = [compiler, "-std=c++17", "-dynamiclib", str(dummy_source), "-o", str(runtime_dir / library_name)]
    else:
        compile_cmd = [compiler, "-std=c++17", "-shared", "-fPIC", str(dummy_source), "-o", str(runtime_dir / library_name)]
    subprocess.run(compile_cmd, check=True, capture_output=True, text=True)

    smoke_env = os.environ.copy()
    smoke_env["POB_RUNTIME_PLATFORM"] = platform
    smoke_env["POB_RUNTIME_ARCHITECTURE"] = architecture
    smoke_env["POB_SMOKE_RUN"] = "1"
    return subprocess.run(
        [str(repo_root / "scripts" / "smoke-native-runtime.sh"), str(tmp_path), "--smoke-arg"],
        env=smoke_env,
        text=True,
        capture_output=True,
    )


def test_native_runtime_smoke_reports_missing_library(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    platform, architecture, _ = _host_target()
    runtime_dir = tmp_path / "runtime" / f"{platform}-{architecture}"
    runtime_dir.mkdir(parents=True)
    launcher = runtime_dir / "PathOfBuilding-PoE2"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["POB_RUNTIME_PLATFORM"] = platform
    env["POB_RUNTIME_ARCHITECTURE"] = architecture
    result = subprocess.run(
        [str(repo_root / "scripts" / "smoke-native-runtime.sh"), str(tmp_path)],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "SimpleGraphic runtime library was not found" in result.stderr


def test_native_runtime_smoke_normalizes_target_override(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    runtime_dir = tmp_path / "runtime" / "linux-armv7"
    runtime_dir.mkdir(parents=True)
    launcher = runtime_dir / "PathOfBuilding-PoE2"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["POB_RUNTIME_TARGET"] = "armhf-linux"
    result = subprocess.run(
        [str(repo_root / "scripts" / "smoke-native-runtime.sh"), str(tmp_path)],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "SimpleGraphic runtime library was not found for linux/armv7" in result.stderr


def test_native_runtime_smoke_preserves_args_with_target_override(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    runtime_dir = tmp_path / "runtime" / "linux-armv7"
    runtime_dir.mkdir(parents=True)
    launcher = runtime_dir / "PathOfBuilding-PoE2"
    launcher.write_text("#!/bin/sh\necho forwarded \"$@\"\n", encoding="utf-8")
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    (runtime_dir / "libSimpleGraphic.so").write_text("library\n", encoding="utf-8")
    shutil.copy(repo_root / "Path of Building-PoE2.command", tmp_path / "Path of Building-PoE2.command")
    (tmp_path / "Path of Building-PoE2.command").chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    env = os.environ.copy()
    env["POB_RUNTIME_TARGET"] = "armhf-linux"
    env["POB_SMOKE_RUN"] = "1"
    result = subprocess.run(
        [
            str(repo_root / "scripts" / "smoke-native-runtime.sh"),
            str(tmp_path),
            "--smoke-arg",
        ],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "forwarded --smoke-arg" in result.stdout


def test_native_runtime_smoke_accepts_decoded_windows_launcher_name(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    runtime_dir = tmp_path / "runtime" / "win32-x64"
    runtime_dir.mkdir(parents=True)
    launcher = runtime_dir / "Path of Building-PoE2.exe"
    launcher.write_text("windows launcher\n", encoding="utf-8")
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    (runtime_dir / "SimpleGraphic.dll").write_text("library\n", encoding="utf-8")

    env = os.environ.copy()
    env["POB_RUNTIME_TARGET"] = "windows-amd64"
    result = subprocess.run(
        [str(repo_root / "scripts" / "smoke-native-runtime.sh"), str(tmp_path)],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert "Found native launcher" in result.stdout
    assert "Path of Building-PoE2.exe" in result.stdout
    assert "Found SimpleGraphic library" in result.stdout


def test_native_runtime_smoke_rejects_unsafe_direct_target_labels(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["POB_RUNTIME_PLATFORM"] = "../linux"
    env["POB_RUNTIME_ARCHITECTURE"] = "x64"

    result = subprocess.run(
        [str(repo_root / "scripts" / "smoke-native-runtime.sh"), str(tmp_path)],
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "Runtime target labels must be safe" in result.stderr


@pytest.mark.parametrize("directive", ["SimpleGraphic", "SimpleGraphic.dll"])
def test_native_runtime_smoke_executes_dummy_simplegraphic(tmp_path, directive) -> None:
    result = _run_dummy_simplegraphic(tmp_path, directive)
    assert result.returncode == 42
    assert "Found native launcher" in result.stdout
    assert "Found SimpleGraphic library" in result.stdout
    assert "dummy simplegraphic argc=2" in result.stdout
    assert str(tmp_path / "Launch.lua") in result.stdout
    assert f"{tmp_path}/runtime/" in result.stdout
    assert "/lua/?.lua" in result.stdout
    assert "/?.so" in result.stdout


def test_native_runtime_smoke_normalizes_windows_style_runtime_directive(tmp_path) -> None:
    platform, architecture, _ = _host_target()
    result = _run_dummy_simplegraphic(
        tmp_path,
        f"runtime\\{platform}-{architecture}\\SimpleGraphic.dll",
    )

    assert result.returncode == 42
    assert "dummy simplegraphic argc=2" in result.stdout
