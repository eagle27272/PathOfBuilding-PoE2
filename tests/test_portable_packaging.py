import pathlib
import stat
import subprocess
import zipfile
import xml.etree.ElementTree as Et

import pytest


def _write_minimal_package_repo(root: pathlib.Path) -> None:
    (root / "src").mkdir()
    (root / "runtime" / "macos-arm64").mkdir(parents=True)
    (root / "runtime" / "linux-x64").mkdir(parents=True)
    (root / "changelog.txt").write_text("changes\n", encoding="utf-8")
    (root / "Path of Building-PoE2.command").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / "src" / "Launch.lua").write_text("return {}\n", encoding="utf-8")
    (root / "runtime" / "macos-arm64" / "PathOfBuilding-PoE2").write_text(
        "#!/bin/sh\n", encoding="utf-8"
    )
    (root / "runtime" / "linux-x64" / "PathOfBuilding-PoE2").write_text(
        "#!/bin/sh\n", encoding="utf-8"
    )
    (root / "manifest.xml").write_text(
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<PoBVersion>\n"
        "\t<Version number='9.8.7' />\n"
        "\t<Source part='default' url='https://example.invalid/{branch}/' />\n"
        "\t<Source part='runtime' platform='macos' architecture='arm64' url='https://example.invalid/runtime/macos-arm64/' />\n"
        "\t<Source part='runtime' platform='linux' architecture='x64' url='https://example.invalid/runtime/linux-x64/' />\n"
        "\t<Source part='program' url='https://example.invalid/src/' />\n"
        "\t<File name='changelog.txt' part='default' sha1='default-hash' />\n"
        "\t<File name='Path of Building-PoE2.command' part='default' sha1='command-hash' />\n"
        "\t<File name='Launch.lua' part='program' sha1='launch-hash' />\n"
        "\t<File name='PathOfBuilding-PoE2' part='runtime' platform='macos' architecture='arm64' sha1='macos-hash' />\n"
        "\t<File name='PathOfBuilding-PoE2' part='runtime' platform='linux' architecture='x64' sha1='linux-hash' />\n"
        "</PoBVersion>\n",
        encoding="utf-8",
    )


def test_package_portable_filters_runtime_and_stamps_local_manifest(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    package_repo = tmp_path / "repo"
    output_dir = tmp_path / "dist"
    package_repo.mkdir()
    _write_minimal_package_repo(package_repo)

    subprocess.run(
        [
            str(repo_root / "scripts" / "package-portable.py"),
            "--repo-dir",
            str(package_repo),
            "--output-dir",
            str(output_dir),
            "--platform",
            "Darwin",
            "--architecture",
            "aarch64",
            "--branch",
            "beta",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    archive_path = output_dir / "PathOfBuilding-PoE2-macos-arm64.zip"
    assert archive_path.is_file()
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "PathOfBuilding-PoE2-macos-arm64/changelog.txt" in names
        assert "PathOfBuilding-PoE2-macos-arm64/Launch.lua" in names
        assert "PathOfBuilding-PoE2-macos-arm64/runtime/macos-arm64/PathOfBuilding-PoE2" in names
        assert "PathOfBuilding-PoE2-macos-arm64/runtime/linux-x64/PathOfBuilding-PoE2" not in names

        manifest = Et.fromstring(
            archive.read("PathOfBuilding-PoE2-macos-arm64/manifest.xml")
        )
        version = manifest.find("Version")
        assert version is not None
        assert version.get("number") == "9.8.7"
        assert version.get("platform") == "macos"
        assert version.get("architecture") == "arm64"
        assert version.get("branch") == "beta"
        runtime_files = [
            node for node in manifest.findall("File") if node.get("part") == "runtime"
        ]
        assert len(runtime_files) == 1
        assert runtime_files[0].get("platform") == "macos"
        assert runtime_files[0].get("architecture") == "arm64"


def test_package_portable_includes_shared_runtime_files(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    package_repo = tmp_path / "repo"
    output_dir = tmp_path / "dist"
    package_repo.mkdir()
    _write_minimal_package_repo(package_repo)
    shared_lua = package_repo / "runtime" / "macos-arm64" / "lua" / "xml.lua"
    shared_lua.parent.mkdir(parents=True)
    shared_lua.write_text("return {}\n", encoding="utf-8")
    manifest = package_repo / "manifest.xml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "\t<File name='PathOfBuilding-PoE2' part='runtime' platform='macos' architecture='arm64' sha1='macos-hash' />\n",
            "\t<File name='PathOfBuilding-PoE2' part='runtime' platform='macos' architecture='arm64' sha1='macos-hash' />\n"
            "\t<File name='lua/xml.lua' part='runtime' sha1='shared-hash' />\n",
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            str(repo_root / "scripts" / "package-portable.py"),
            "--repo-dir",
            str(package_repo),
            "--output-dir",
            str(output_dir),
            "--platform",
            "macos",
            "--architecture",
            "arm64",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    archive_path = output_dir / "PathOfBuilding-PoE2-macos-arm64.zip"
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "PathOfBuilding-PoE2-macos-arm64/runtime/macos-arm64/lua/xml.lua" in names
        manifest = Et.fromstring(
            archive.read("PathOfBuilding-PoE2-macos-arm64/manifest.xml")
        )
        shared_nodes = [
            node
            for node in manifest.findall("File")
            if node.get("part") == "runtime" and node.get("name") == "lua/xml.lua"
        ]
        assert len(shared_nodes) == 1
        assert shared_nodes[0].get("platform") is None
        assert shared_nodes[0].get("architecture") is None


def test_package_portable_places_simplegraphic_assets_at_native_package_root(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    package_repo = tmp_path / "repo"
    output_dir = tmp_path / "dist"
    package_repo.mkdir()
    _write_minimal_package_repo(package_repo)
    font = package_repo / "runtime" / "macos-arm64" / "SimpleGraphic" / "Fonts" / "Fontin.tgf"
    font.parent.mkdir(parents=True)
    font.write_text("font\n", encoding="utf-8")
    manifest = package_repo / "manifest.xml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "\t<File name='PathOfBuilding-PoE2' part='runtime' platform='macos' architecture='arm64' sha1='macos-hash' />\n",
            "\t<File name='PathOfBuilding-PoE2' part='runtime' platform='macos' architecture='arm64' sha1='macos-hash' />\n"
            "\t<File name='SimpleGraphic/Fonts/Fontin.tgf' part='runtime' sha1='font-hash' />\n",
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            str(repo_root / "scripts" / "package-portable.py"),
            "--repo-dir",
            str(package_repo),
            "--output-dir",
            str(output_dir),
            "--platform",
            "macos",
            "--architecture",
            "arm64",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    archive_path = output_dir / "PathOfBuilding-PoE2-macos-arm64.zip"
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "PathOfBuilding-PoE2-macos-arm64/SimpleGraphic/Fonts/Fontin.tgf" in names
        assert (
            "PathOfBuilding-PoE2-macos-arm64/runtime/macos-arm64/SimpleGraphic/Fonts/Fontin.tgf"
            not in names
        )


def test_package_portable_normalizes_manifest_target_aliases(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    package_repo = tmp_path / "repo"
    output_dir = tmp_path / "dist"
    package_repo.mkdir()
    _write_minimal_package_repo(package_repo)
    manifest = package_repo / "manifest.xml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        .replace("platform='macos'", "platform='Darwin'")
        .replace("architecture='arm64'", "architecture='aarch64'"),
        encoding="utf-8",
    )

    subprocess.run(
        [
            str(repo_root / "scripts" / "package-portable.py"),
            "--repo-dir",
            str(package_repo),
            "--output-dir",
            str(output_dir),
            "--platform",
            "macOS",
            "--architecture",
            "ARM64",
            "--branch",
            "beta",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    archive_path = output_dir / "PathOfBuilding-PoE2-macos-arm64.zip"
    assert archive_path.is_file()
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "PathOfBuilding-PoE2-macos-arm64/runtime/macos-arm64/PathOfBuilding-PoE2" in names
        assert "PathOfBuilding-PoE2-macos-arm64/runtime/linux-x64/PathOfBuilding-PoE2" not in names
        manifest = Et.fromstring(
            archive.read("PathOfBuilding-PoE2-macos-arm64/manifest.xml")
        )
        runtime_files = [
            node for node in manifest.findall("File") if node.get("part") == "runtime"
        ]
        assert len(runtime_files) == 1


def test_package_portable_preserves_executable_bits(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    package_repo = tmp_path / "repo"
    output_dir = tmp_path / "dist"
    package_repo.mkdir()
    _write_minimal_package_repo(package_repo)

    subprocess.run(
        [
            str(repo_root / "scripts" / "package-portable.py"),
            "--repo-dir",
            str(package_repo),
            "--output-dir",
            str(output_dir),
            "--platform",
            "macos",
            "--architecture",
            "arm64",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    archive_path = output_dir / "PathOfBuilding-PoE2-macos-arm64.zip"
    with zipfile.ZipFile(archive_path) as archive:
        command_mode = archive.getinfo(
            "PathOfBuilding-PoE2-macos-arm64/Path of Building-PoE2.command"
        ).external_attr >> 16
        runtime_mode = archive.getinfo(
            "PathOfBuilding-PoE2-macos-arm64/runtime/macos-arm64/PathOfBuilding-PoE2"
        ).external_attr >> 16

    assert command_mode & stat.S_IXUSR
    assert runtime_mode & stat.S_IXUSR


def test_package_portable_decodes_space_tokens_in_package_layout(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    package_repo = tmp_path / "repo"
    output_dir = tmp_path / "dist"
    package_repo.mkdir()
    _write_minimal_package_repo(package_repo)
    (package_repo / "runtime" / "Path{space}of{space}Building-PoE2.exe").write_text(
        "windows launcher\n", encoding="utf-8"
    )
    manifest = package_repo / "manifest.xml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "\t<File name='PathOfBuilding-PoE2' part='runtime' platform='linux' architecture='x64' sha1='linux-hash' />\n",
            "\t<File name='PathOfBuilding-PoE2' part='runtime' platform='linux' architecture='x64' sha1='linux-hash' />\n"
            "\t<File name='Path{space}of{space}Building-PoE2.exe' part='runtime' platform='win32' architecture='x64' sha1='win-hash' />\n",
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            str(repo_root / "scripts" / "package-portable.py"),
            "--repo-dir",
            str(package_repo),
            "--output-dir",
            str(output_dir),
            "--platform",
            "windows",
            "--architecture",
            "amd64",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    archive_path = output_dir / "PathOfBuilding-PoE2-win32-x64.zip"
    assert archive_path.is_file()
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "PathOfBuilding-PoE2-win32-x64/runtime/Path of Building-PoE2.exe" in names
        assert "PathOfBuilding-PoE2-win32-x64/runtime/Path{space}of{space}Building-PoE2.exe" not in names
        manifest = Et.fromstring(
            archive.read("PathOfBuilding-PoE2-win32-x64/manifest.xml")
        )
        runtime_files = [
            node for node in manifest.findall("File") if node.get("part") == "runtime"
        ]
        assert len(runtime_files) == 1
        assert runtime_files[0].get("name") == "Path{space}of{space}Building-PoE2.exe"


@pytest.mark.parametrize(
    "name",
    [
        "../escape.txt",
        "./file.txt",
        ".",
        "/tmp/escape.txt",
        "runtime\\escape.txt",
        "bad//name.txt",
        "C:escape.txt",
        "trailing/",
        'bad"name.txt',
        "bad&#10;name.txt",
        "bad{slash}name.txt",
    ],
)
def test_package_portable_rejects_unsafe_manifest_file_names(
    tmp_path, name
) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    package_repo = tmp_path / "repo"
    output_dir = tmp_path / "dist"
    package_repo.mkdir()
    _write_minimal_package_repo(package_repo)
    manifest = package_repo / "manifest.xml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "\t<File name='changelog.txt' part='default' sha1='default-hash' />\n",
            "\t<File name='changelog.txt' part='default' sha1='default-hash' />\n"
            f"\t<File name='{name}' part='default' sha1='bad-hash' />\n",
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            str(repo_root / "scripts" / "package-portable.py"),
            "--repo-dir",
            str(package_repo),
            "--output-dir",
            str(output_dir),
            "--platform",
            "macos",
            "--architecture",
            "arm64",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "unsafe name" in result.stderr


@pytest.mark.parametrize(
    ("option", "value", "message"),
    [
        ("--platform", "../macos", "unsafe platform target label"),
        ("--platform", "mac/os", "unsafe platform target label"),
        ("--architecture", ".x64", "unsafe architecture target label"),
        ("--architecture", "x64/linux", "unsafe architecture target label"),
    ],
)
def test_package_portable_rejects_unsafe_target_labels(
    tmp_path, option, value, message
) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    package_repo = tmp_path / "repo"
    output_dir = tmp_path / "dist"
    package_repo.mkdir()
    _write_minimal_package_repo(package_repo)

    platform = "macos"
    architecture = "arm64"
    if option == "--platform":
        platform = value
    else:
        architecture = value
    result = subprocess.run(
        [
            str(repo_root / "scripts" / "package-portable.py"),
            "--repo-dir",
            str(package_repo),
            "--output-dir",
            str(output_dir),
            "--platform",
            platform,
            "--architecture",
            architecture,
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert message in result.stderr


def test_package_portable_normalizes_armhf_architecture_alias(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    package_repo = tmp_path / "repo"
    output_dir = tmp_path / "dist"
    package_repo.mkdir()
    _write_minimal_package_repo(package_repo)
    (package_repo / "runtime" / "linux-armv7").mkdir()
    (package_repo / "runtime" / "linux-armv7" / "PathOfBuilding-PoE2").write_text(
        "#!/bin/sh\n", encoding="utf-8"
    )
    manifest = package_repo / "manifest.xml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "\t<File name='PathOfBuilding-PoE2' part='runtime' platform='linux' architecture='x64' sha1='linux-hash' />\n",
            "\t<File name='PathOfBuilding-PoE2' part='runtime' platform='linux' architecture='x64' sha1='linux-hash' />\n"
            "\t<File name='PathOfBuilding-PoE2' part='runtime' platform='linux' architecture='armv7' sha1='linux-armv7-hash' />\n",
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            str(repo_root / "scripts" / "package-portable.py"),
            "--repo-dir",
            str(package_repo),
            "--output-dir",
            str(output_dir),
            "--platform",
            "linux",
            "--architecture",
            "armhf",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    archive_path = output_dir / "PathOfBuilding-PoE2-linux-armv7.zip"
    assert archive_path.is_file()
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert "PathOfBuilding-PoE2-linux-armv7/runtime/linux-armv7/PathOfBuilding-PoE2" in names
        manifest = Et.fromstring(
            archive.read("PathOfBuilding-PoE2-linux-armv7/manifest.xml")
        )
        version = manifest.find("Version")
        assert version is not None
        assert version.get("architecture") == "armv7"


def test_package_portable_all_targets_packages_each_runtime_target(tmp_path) -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    package_repo = tmp_path / "repo"
    output_dir = tmp_path / "dist"
    package_repo.mkdir()
    _write_minimal_package_repo(package_repo)
    (package_repo / "runtime" / "win32-arm64ec").mkdir()
    (package_repo / "runtime" / "win32-arm64ec" / "PathOfBuilding-PoE2.exe").write_text(
        "windows arm64ec launcher\n", encoding="utf-8"
    )
    manifest = package_repo / "manifest.xml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "\t<File name='PathOfBuilding-PoE2' part='runtime' platform='linux' architecture='x64' sha1='linux-hash' />\n",
            "\t<File name='PathOfBuilding-PoE2' part='runtime' platform='linux' architecture='x64' sha1='linux-hash' />\n"
            "\t<File name='PathOfBuilding-PoE2.exe' part='runtime' platform='windows' architecture='arm64ec' sha1='win-arm64ec-hash' />\n",
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            str(repo_root / "scripts" / "package-portable.py"),
            "--repo-dir",
            str(package_repo),
            "--output-dir",
            str(output_dir),
            "--all-targets",
            "--branch",
            "master",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert (output_dir / "PathOfBuilding-PoE2-linux-x64.zip").is_file()
    assert (output_dir / "PathOfBuilding-PoE2-macos-arm64.zip").is_file()
    assert (output_dir / "PathOfBuilding-PoE2-win32-arm64ec.zip").is_file()

    with zipfile.ZipFile(output_dir / "PathOfBuilding-PoE2-linux-x64.zip") as archive:
        manifest = Et.fromstring(
            archive.read("PathOfBuilding-PoE2-linux-x64/manifest.xml")
        )
        version = manifest.find("Version")
        assert version is not None
        assert version.get("platform") == "linux"
        assert version.get("architecture") == "x64"
        assert version.get("branch") == "master"
        names = set(archive.namelist())
        assert "PathOfBuilding-PoE2-linux-x64/runtime/linux-x64/PathOfBuilding-PoE2" in names
        assert "PathOfBuilding-PoE2-linux-x64/runtime/macos-arm64/PathOfBuilding-PoE2" not in names

    with zipfile.ZipFile(output_dir / "PathOfBuilding-PoE2-win32-arm64ec.zip") as archive:
        manifest = Et.fromstring(
            archive.read("PathOfBuilding-PoE2-win32-arm64ec/manifest.xml")
        )
        version = manifest.find("Version")
        assert version is not None
        assert version.get("platform") == "win32"
        assert version.get("architecture") == "arm64ec"
        names = set(archive.namelist())
        assert "PathOfBuilding-PoE2-win32-arm64ec/runtime/win32-arm64ec/PathOfBuilding-PoE2.exe" in names


def test_native_portable_workflow_packages_discovered_targets() -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    workflow = (
        repo_root / ".github" / "workflows" / "native-portable.yml"
    ).read_text(encoding="utf-8")

    assert "scripts/package-portable.py --all-targets" in workflow
    assert "manifest_branch" in workflow
    assert "--branch \"${{ github.event.inputs.manifest_branch || 'master' }}\"" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "Dist/*.zip" in workflow
    assert "gh release upload" in workflow
