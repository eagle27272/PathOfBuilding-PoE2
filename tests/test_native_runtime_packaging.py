# cspell:ignore simplegraphic SIMPLEGRAPHIC liblib gles riscv ARCHITEW RUNNER builddocker
import os
import pathlib
import stat
import subprocess


def _write_fake_compiler(path: pathlib.Path, body: str = "echo fake launcher") -> None:
    path.write_text(
        "#!/bin/sh\n"
        "out=\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = \"-o\" ]; then\n"
        "    shift\n"
        "    out=$1\n"
        "  fi\n"
        "  shift || true\n"
        "done\n"
        f"printf '#!/bin/sh\\n{body}\\n' > \"$out\"\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_package_native_runtime_uses_windows_exe_name_with_aliases(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    out_dir = tmp_path / "runtime"
    build_dir = tmp_path / "build"
    compiler = tmp_path / "fake-cxx"
    _write_fake_compiler(compiler)

    env = os.environ.copy()
    env["CXX"] = str(compiler)
    env["POB_LAUNCHER_ALLOW_CROSS_TARGET"] = "1"
    env["POB_LAUNCHER_FORCE_CXX"] = "1"
    env["POB_RUNTIME_PLATFORM"] = "windows"
    env["POB_RUNTIME_ARCHITECTURE"] = "amd64"
    env["POB_RUNTIME_OUT_DIR"] = str(out_dir)
    env["POB_LAUNCHER_BUILD_DIR"] = str(build_dir)

    subprocess.run(
        [str(repo_root / "scripts" / "package-native-runtime.sh")],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    launcher = out_dir / "PathOfBuilding-PoE2.exe"
    assert launcher.read_text(encoding="utf-8") == "#!/bin/sh\necho fake launcher\n"
    assert launcher.stat().st_mode & stat.S_IXUSR
    assert (out_dir / "lua" / "xml.lua").is_file()


def test_package_native_runtime_adds_macos_angle_aliases_and_assets(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    out_dir = tmp_path / "runtime"
    build_dir = tmp_path / "build"
    simplegraphic_install = tmp_path / "simplegraphic-install"
    simplegraphic_install.mkdir()
    (simplegraphic_install / "liblibEGL_angle.dylib").write_text("egl\n", encoding="utf-8")
    (simplegraphic_install / "liblibGLESv2_angle.dylib").write_text("gles\n", encoding="utf-8")
    compiler = tmp_path / "fake-cxx"
    _write_fake_compiler(compiler)

    env = os.environ.copy()
    env["CXX"] = str(compiler)
    env["POB_LAUNCHER_ALLOW_CROSS_TARGET"] = "1"
    env["POB_LAUNCHER_FORCE_CXX"] = "1"
    env["POB_RUNTIME_TARGET"] = "macos-arm64"
    env["POB_RUNTIME_OUT_DIR"] = str(out_dir)
    env["POB_LAUNCHER_BUILD_DIR"] = str(build_dir)
    env["SIMPLEGRAPHIC_INSTALL_DIR"] = str(simplegraphic_install)

    subprocess.run(
        [str(repo_root / "scripts" / "package-native-runtime.sh")],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    assert (out_dir / "libEGL.dylib").read_text(encoding="utf-8") == "egl\n"
    assert (out_dir / "libGLESv2.dylib").read_text(encoding="utf-8") == "gles\n"
    assert (out_dir / "SimpleGraphic" / "Fonts" / "Fontin.tgf").is_file()


def test_package_native_runtime_rejects_mismatched_target_without_override(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["POB_RUNTIME_OUT_DIR"] = str(tmp_path / "runtime")
    env["POB_RUNTIME_PLATFORM"] = "FreeBSD"
    env["POB_RUNTIME_ARCHITECTURE"] = "riscv64"

    result = subprocess.run(
        [str(repo_root / "scripts" / "package-native-runtime.sh")],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Refusing to package freebsd-riscv64" in result.stderr
    assert "POB_LAUNCHER_ALLOW_CROSS_TARGET=1" in result.stderr


def test_package_native_runtime_detects_windows_arm64_under_emulation(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_uname = bin_dir / "uname"
    fake_uname.write_text(
        "#!/bin/sh\n"
        "if [ \"${1:-}\" = \"-m\" ]; then\n"
        "  printf 'x86_64\\n'\n"
        "else\n"
        "  printf 'MINGW64_NT-10.0\\n'\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_uname.chmod(fake_uname.stat().st_mode | stat.S_IXUSR)
    compiler = tmp_path / "fake-cxx"
    _write_fake_compiler(compiler, "echo fake arm64 launcher")
    out_dir = tmp_path / "runtime"

    env = os.environ.copy()
    env["CXX"] = str(compiler)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["POB_LAUNCHER_FORCE_CXX"] = "1"
    env["POB_RUNTIME_OUT_DIR"] = str(out_dir)
    env["POB_RUNTIME_PLATFORM"] = "win32"
    env["POB_RUNTIME_ARCHITECTURE"] = "arm64"
    env["PROCESSOR_ARCHITECTURE"] = "AMD64"
    env["PROCESSOR_ARCHITEW6432"] = "ARM64"

    subprocess.run(
        [str(repo_root / "scripts" / "package-native-runtime.sh")],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    launcher = out_dir / "PathOfBuilding-PoE2.exe"
    assert launcher.read_text(encoding="utf-8") == "#!/bin/sh\necho fake arm64 launcher\n"


def test_package_native_runtime_detects_windows_arm64_from_runner_arch(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_uname = bin_dir / "uname"
    fake_uname.write_text(
        "#!/bin/sh\n"
        "if [ \"${1:-}\" = \"-m\" ]; then\n"
        "  printf 'x86_64\\n'\n"
        "else\n"
        "  printf 'MINGW64_NT-10.0\\n'\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_uname.chmod(fake_uname.stat().st_mode | stat.S_IXUSR)
    compiler = tmp_path / "fake-cxx"
    _write_fake_compiler(compiler, "echo fake runner arch launcher")
    out_dir = tmp_path / "runtime"

    env = os.environ.copy()
    env["CXX"] = str(compiler)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["POB_LAUNCHER_FORCE_CXX"] = "1"
    env["POB_RUNTIME_OUT_DIR"] = str(out_dir)
    env["POB_RUNTIME_PLATFORM"] = "win32"
    env["POB_RUNTIME_ARCHITECTURE"] = "arm64"
    env["PROCESSOR_ARCHITECTURE"] = "AMD64"
    env.pop("PROCESSOR_ARCHITEW6432", None)
    env["RUNNER_ARCH"] = "ARM64"

    subprocess.run(
        [str(repo_root / "scripts" / "package-native-runtime.sh")],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    launcher = out_dir / "PathOfBuilding-PoE2.exe"
    assert launcher.read_text(encoding="utf-8") == (
        "#!/bin/sh\necho fake runner arch launcher\n"
    )


def test_package_native_runtime_target_override_sets_platform_and_architecture(
    tmp_path,
) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    out_dir = tmp_path / "runtime"
    compiler = tmp_path / "fake-cxx"
    _write_fake_compiler(compiler, "echo target override")

    env = os.environ.copy()
    env["CXX"] = str(compiler)
    env["POB_LAUNCHER_ALLOW_CROSS_TARGET"] = "1"
    env["POB_LAUNCHER_FORCE_CXX"] = "1"
    env["POB_RUNTIME_OUT_DIR"] = str(out_dir)
    env["POB_RUNTIME_TARGET"] = "amd64-windows"

    subprocess.run(
        [str(repo_root / "scripts" / "package-native-runtime.sh")],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    launcher = out_dir / "PathOfBuilding-PoE2.exe"
    assert launcher.read_text(encoding="utf-8") == "#!/bin/sh\necho target override\n"


def test_package_native_runtime_target_override_recognizes_arm64ec_windows(
    tmp_path,
) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    out_dir = tmp_path / "runtime"
    compiler = tmp_path / "fake-cxx"
    _write_fake_compiler(compiler, "echo arm64ec target override")

    env = os.environ.copy()
    env["CXX"] = str(compiler)
    env["POB_LAUNCHER_ALLOW_CROSS_TARGET"] = "1"
    env["POB_LAUNCHER_FORCE_CXX"] = "1"
    env["POB_RUNTIME_OUT_DIR"] = str(out_dir)
    env["POB_RUNTIME_TARGET"] = "arm64ec-windows"

    subprocess.run(
        [str(repo_root / "scripts" / "package-native-runtime.sh")],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    launcher = out_dir / "PathOfBuilding-PoE2.exe"
    assert launcher.read_text(encoding="utf-8") == "#!/bin/sh\necho arm64ec target override\n"


def test_package_native_runtime_rejects_unsafe_target_override(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["POB_LAUNCHER_ALLOW_CROSS_TARGET"] = "1"
    env["POB_RUNTIME_OUT_DIR"] = str(tmp_path / "runtime")
    env["POB_RUNTIME_TARGET"] = "../linux-x64"

    result = subprocess.run(
        [str(repo_root / "scripts" / "package-native-runtime.sh")],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "POB_RUNTIME_TARGET must be a safe" in result.stderr


def test_package_native_runtime_rejects_unsafe_direct_target_labels(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["POB_LAUNCHER_ALLOW_CROSS_TARGET"] = "1"
    env["POB_RUNTIME_OUT_DIR"] = str(tmp_path / "runtime")
    env["POB_RUNTIME_PLATFORM"] = "../linux"
    env["POB_RUNTIME_ARCHITECTURE"] = "x64"

    result = subprocess.run(
        [str(repo_root / "scripts" / "package-native-runtime.sh")],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Runtime target labels must be safe" in result.stderr


def test_native_runtime_workflow_builds_expected_artifact_matrix() -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    workflow = (
        repo_root / ".github" / "workflows" / "native-runtime.yml"
    ).read_text(encoding="utf-8")

    for target in [
        "macos-arm64",
        "macos-x64",
        "linux-arm64",
        "linux-x64",
        "win32-arm64",
        "win32-x64",
    ]:
        assert f"target: {target}" in workflow
        assert f"PathOfBuildingRuntime-${{{{ matrix.target }}}}.tar" in workflow

    for runner in [
        "macos-15",
        "macos-15-intel",
        "ubuntu-24.04-arm",
        "ubuntu-24.04",
        "windows-11-arm",
        "windows-2025",
    ]:
        assert f"runner: {runner}" in workflow

    assert "actions/upload-artifact@v4" in workflow
    assert "gh release upload" in workflow
    assert "'scripts/verify-pob-runtime-index.py'" in workflow
    assert "'scripts/write-pob-runtime-index.py'" in workflow
    assert "scripts/write-pob-runtime-index.py --artifact-dir runtime-artifacts --output runtime-artifacts/PathOfBuildingRuntime-index.json" in workflow
    assert "scripts/verify-pob-runtime-index.py runtime-artifacts runtime-artifacts/PathOfBuildingRuntime-index.json" in workflow
    assert "name: PathOfBuildingRuntime-index" in workflow
    assert "runtime-artifacts/PathOfBuildingRuntime-index.json" in workflow
    assert "needs: index" in workflow
    assert "for archive in release-artifacts/PathOfBuildingRuntime-*.tar; do" in workflow
    assert "release-artifacts/PathOfBuildingRuntime-index.json" in workflow


def test_simplegraphic_update_workflow_can_download_launcher_runtime_assets() -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    workflow = (
        repo_root / ".github" / "workflows" / "update-simple-graphic.yml"
    ).read_text(encoding="utf-8")

    assert "runs-on: ubuntu-24.04" in workflow
    assert "ubuntu-latest" not in workflow
    assert "workflow_dispatch:" in workflow
    assert "simplegraphic_tag:" in workflow
    assert "simplegraphic_release_repo:" in workflow
    assert "launcher_tag:" in workflow
    assert "launcher_runtime_index:" in workflow
    assert "SIMPLEGRAPHIC_RELEASE_REPO" in workflow
    assert "'eagle27272/PathOfBuilding-SimpleGraphic'" in workflow
    assert "SIMPLEGRAPHIC_RUNTIME_INDEX" in workflow
    assert "POB_RUNTIME_RELEASE_TAG" in workflow
    assert "POB_RUNTIME_RELEASE_REPO" in workflow
    assert "POB_RUNTIME_INDEX" in workflow
    assert "github.event.client_payload.tag || inputs.simplegraphic_tag" in workflow
    assert "github.event.client_payload.release_repo || inputs.simplegraphic_release_repo" in workflow
    assert "https://github.com/{0}/releases/tag/{1}" in workflow
    assert "github.event.client_payload.runtime_index || inputs.runtime_index" in workflow
    assert "github.event.client_payload.launcher_tag" in workflow
    assert "inputs.launcher_tag" in workflow
    assert "github.event.client_payload.launcher_release_repo" in workflow
    assert "inputs.launcher_release_repo" in workflow
    assert "github.event.client_payload.launcher_runtime_index" in workflow
    assert "inputs.launcher_runtime_index" in workflow
    assert (
        'gh release download "$SIMPLEGRAPHIC_RELEASE_TAG" --repo "$SIMPLEGRAPHIC_RELEASE_REPO" --pattern "$SIMPLEGRAPHIC_RUNTIME_INDEX" --dir runtime-assets --clobber'
        in workflow
    )
    assert (
        "run: scripts/import-simplegraphic-runtime.sh runtime-assets"
        in workflow
    )
    assert "title: Update SimpleGraphic runtime to ${{ env.SIMPLEGRAPHIC_RELEASE_TAG }}" in workflow
    assert "branch: simple-graphic-${{ env.SIMPLEGRAPHIC_RELEASE_TAG }}" in workflow
    assert (
        "SimpleGraphicDLLs-x64-windows.tar' --dir runtime-assets --clobber || true"
        in workflow
    )
    assert "PathOfBuildingRuntime-*.tar" in workflow
    assert "PathOfBuildingRuntime-*.tar.gz" in workflow
    assert "PathOfBuildingRuntime-*.tgz" in workflow
    assert (
        'gh release download "$POB_RUNTIME_RELEASE_TAG" --repo "$POB_RUNTIME_RELEASE_REPO" --pattern "$POB_RUNTIME_INDEX" --dir runtime-assets --clobber'
        in workflow
    )
    assert "SimpleGraphicRuntime-*.tar.gz" in workflow
    assert "SimpleGraphicRuntime-*.tgz" in workflow


def test_workflows_reference_eagle_owned_cross_repositories() -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    workflows = {
        path.name: path.read_text(encoding="utf-8")
        for path in (repo_root / ".github" / "workflows").glob("*.yml")
    }

    old_owner = "PathOfBuilding" + "Community"
    assert all(old_owner not in source for source in workflows.values())
    assert "repository: eagle27272/PathOfBuilding" in workflows["backport.yml"]
    assert "repository: 'eagle27272/PathOfBuilding-Installer'" in workflows["installer.yml"]
    assert "https://github.com/eagle27272/PathOfBuilding/blob/dev/CONTRIBUTING.md" in workflows["builddocker.yml"]
    assert "'eagle27272/PathOfBuilding-SimpleGraphic'" in workflows["update-simple-graphic.yml"]
