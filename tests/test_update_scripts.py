import json
import pathlib
import shutil
import stat
import subprocess

import pytest


def _hex_path(path: pathlib.Path) -> str:
    return path.as_posix().encode("utf-8").hex()


def test_update_apply_chmod_operation_marks_file_executable(tmp_path) -> None:
    lua = shutil.which("luajit") or shutil.which("lua")
    if not lua:
        pytest.skip("lua is required to exercise UpdateApply chmod")

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    source = tmp_path / "downloaded-launcher"
    target = tmp_path / "PathOfBuilding-PoE2"
    op_file = tmp_path / "opFile.txt"
    source.write_text("#!/bin/sh\n", encoding="utf-8")
    op_file.write_text(
        f'move "{source}" "{target}"\nchmod "{target}"\n',
        encoding="utf-8",
    )

    subprocess.run(
        [lua, str(repo_root / "src" / "UpdateApply.lua"), str(op_file)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert not source.exists()
    assert not op_file.exists()
    assert target.read_text(encoding="utf-8") == "#!/bin/sh\n"
    assert target.stat().st_mode & stat.S_IXUSR


def test_update_apply_hex_operations_support_quoted_paths(tmp_path) -> None:
    lua = shutil.which("luajit") or shutil.which("lua")
    if not lua:
        pytest.skip("lua is required to exercise UpdateApply encoded operations")

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    source = tmp_path / "downloaded-launcher"
    target = tmp_path / 'Path"OfBuilding-PoE2'
    op_file = tmp_path / "opFile.txt"
    source.write_text("#!/bin/sh\n", encoding="utf-8")
    op_file.write_text(
        f"movehex {_hex_path(source)} {_hex_path(target)}\n"
        f"chmodhex {_hex_path(target)}\n",
        encoding="utf-8",
    )

    subprocess.run(
        [lua, str(repo_root / "src" / "UpdateApply.lua"), str(op_file)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert not source.exists()
    assert not op_file.exists()
    assert target.read_text(encoding="utf-8") == "#!/bin/sh\n"
    assert target.stat().st_mode & stat.S_IXUSR


def test_update_check_generates_native_executable_update_operations() -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    update_check = (repo_root / "src" / "UpdateCheck.lua").read_text(encoding="utf-8")

    assert "PathOfBuilding-PoE2" in update_check
    assert "runtimeExecutable = runtimeExecutable or runtimePath..\"/PathOfBuilding-PoE2\"" in update_check
    assert "shouldMakeExecutable(data, localPlatform)" in update_check
    assert 'appendEncodedOperation(ops, "move", data.updateFileName, data.fullPath)' in update_check
    assert 'appendEncodedOperation(ops, "chmod", data.fullPath)' in update_check
    assert 'name:match("%.command$")' in update_check
    assert "normalizePlatform(node.attrib.platform or node.attrib.runtime)" in update_check
    assert "normalizeArchitecture(node.attrib.architecture or node.attrib.arch)" in update_check
    assert 'platform == "darwin" or platform == "mac" or platform == "macos" or platform == "osx"' in update_check
    assert 'architecture == "arm64" or architecture == "aarch64"' in update_check
    assert 'architecture:match("^armv7")' in update_check
    assert 'return "armv7"' in update_check
    assert "safeManifestFileName(node.attrib.name)" in update_check
    assert "nodeMatchesLocalTarget(filePlatform, fileArchitecture, localPlatform, localArchitecture)" in update_check
    assert "nodeArchitecture and (not localArchitecture or nodeArchitecture ~= localArchitecture)" in update_check


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "../escape.lua",
        'bad"name.lua',
        "bad\nname.lua",
        "C:escape.lua",
        "bad//name.lua",
        "./file.lua",
        "bad{slash}name.lua",
    ],
)
def test_update_check_rejects_unsafe_remote_manifest_file_names(
    tmp_path, unsafe_name
) -> None:
    lua = shutil.which("luajit") or shutil.which("lua")
    if not lua:
        pytest.skip("lua is required to exercise UpdateCheck manifest validation")

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    harness = tmp_path / "update_check_harness.lua"
    lua_unsafe_name = json.dumps(unsafe_name)
    harness.write_text(
        f"""
local localManifest = {{
  {{
    elem = "PoBVersion",
    {{ elem = "Version", attrib = {{ number = "1.0.0", branch = "dev", platform = "macos", architecture = "arm64" }} }},
    {{ elem = "Source", attrib = {{ part = "default", url = "https://example.invalid/{{branch}}/" }} }},
    {{ elem = "File", attrib = {{ name = "Launch.lua", part = "program", sha1 = "old" }} }},
  }}
}}

local remoteManifest = {{
  {{
    elem = "PoBVersion",
    {{ elem = "Version", attrib = {{ number = "1.0.1" }} }},
    {{ elem = "Source", attrib = {{ part = "default", url = "https://example.invalid/dev/" }} }},
    {{ elem = "File", attrib = {{ name = {lua_unsafe_name}, part = "program", sha1 = "new" }} }},
  }}
}}

function ConPrintf(...) end
function GetScriptPath() return "{tmp_path.as_posix()}" end
function GetRuntimePath() return "{(tmp_path / "runtime").as_posix()}" end
function MakeDir(path) end

package.preload["sha1"] = function()
  return function(value) return value end
end

package.preload["lzip"] = function()
  return {{}}
end

package.preload["xml"] = function()
  return {{
    LoadXMLFile = function(path) return localManifest end,
    ParseXML = function(text) return remoteManifest end,
    SaveXMLFile = function(...) error("unexpected SaveXMLFile") end,
  }}
end

package.preload["lcurl.safe"] = function()
  local curl = {{
    OPT_ACCEPT_ENCODING = 1,
    OPT_IPRESOLVE = 2,
    OPT_PROXY = 3,
    OPT_SSL_VERIFYPEER = 4,
    OPT_SSL_VERIFYHOST = 5,
  }}
  local methods = {{}}
  function curl.easy()
    return setmetatable({{ write = function() end }}, {{ __index = methods }})
  end
  function methods:escape(value) return value end
  function methods:setopt_url(url) end
  function methods:setopt(option, value) end
  function methods:setopt_writefunction(write) self.write = write end
  function methods:perform()
    self.write("manifest")
    return true, nil
  end
  function methods:close() end
  return curl
end

local result, err = dofile([[{(repo_root / "src" / "UpdateCheck.lua").as_posix()}]])
if result ~= nil or err ~= "Invalid remote manifest" then
  error("expected invalid remote manifest, got result=" .. tostring(result) .. " err=" .. tostring(err))
end
""",
        encoding="utf-8",
    )

    subprocess.run(
        [lua, str(harness)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_update_check_normalizes_platform_and_architecture_aliases(tmp_path) -> None:
    lua = shutil.which("luajit") or shutil.which("lua")
    if not lua:
        pytest.skip("lua is required to exercise UpdateCheck target normalization")

    repo_root = pathlib.Path(__file__).resolve().parents[1]
    (tmp_path / "Update").mkdir()
    (tmp_path / "Launch.lua").write_text("old", encoding="utf-8")
    harness = tmp_path / "update_check_alias_harness.lua"
    harness.write_text(
        f"""
local localManifest = {{
  {{
    elem = "PoBVersion",
    {{ elem = "Version", attrib = {{ number = "1.0.0", branch = "dev", platform = "Darwin", architecture = "aarch64" }} }},
    {{ elem = "Source", attrib = {{ part = "default", url = "https://example.invalid/{{branch}}/" }} }},
    {{ elem = "File", attrib = {{ name = "Launch.lua", part = "program", sha1 = "old" }} }},
  }}
}}

local remoteManifest = {{
  {{
    elem = "PoBVersion",
    {{ elem = "Version", attrib = {{ number = "1.0.1" }} }},
    {{ elem = "Source", attrib = {{ part = "program", platform = "Darwin", architecture = "aarch64", url = "https://example.invalid/dev/macos/" }} }},
    {{ elem = "File", attrib = {{ name = "Launch.lua", part = "program", platform = "macOS", architecture = "ARM64", sha1 = "new" }} }},
  }}
}}

function ConPrintf(...) end
function GetScriptPath() return "{tmp_path.as_posix()}" end
function GetRuntimePath() return "{(tmp_path / "runtime").as_posix()}" end
function MakeDir(path) end

package.preload["sha1"] = function()
  return function(value) return value end
end

package.preload["lzip"] = function()
  return {{}}
end

package.preload["xml"] = function()
  return {{
    LoadXMLFile = function(path) return localManifest end,
    ParseXML = function(text) return remoteManifest end,
    SaveXMLFile = function(manifest, path)
      local file = assert(io.open(path, "w"))
      file:write("<manifest />")
      file:close()
    end,
  }}
end

package.preload["lcurl.safe"] = function()
  local curl = {{
    OPT_ACCEPT_ENCODING = 1,
    OPT_IPRESOLVE = 2,
    OPT_PROXY = 3,
    OPT_SSL_VERIFYPEER = 4,
    OPT_SSL_VERIFYHOST = 5,
  }}
  local methods = {{}}
  local function writeData(writer, data)
    if type(writer) == "function" then
      writer(data)
    else
      writer:write(data)
    end
  end
  function curl.easy()
    return setmetatable({{ url = "", write = function() end }}, {{ __index = methods }})
  end
  function methods:escape(value) return value end
  function methods:setopt_url(url) self.url = url end
  function methods:setopt(option, value) end
  function methods:setopt_writefunction(write) self.write = write end
  function methods:perform()
    if self.url:match("Launch%.lua$") then
      writeData(self.write, "new")
    elseif self.url:match("changelog%.txt$") then
      writeData(self.write, "changelog")
    else
      writeData(self.write, "manifest")
    end
    return true, nil
  end
  function methods:close() end
  return curl
end

local result, err = dofile([[{(repo_root / "src" / "UpdateCheck.lua").as_posix()}]])
if result ~= "normal" or err ~= nil then
  error("expected normal update, got result=" .. tostring(result) .. " err=" .. tostring(err))
end
""",
        encoding="utf-8",
    )

    subprocess.run(
        [lua, str(harness)],
        check=True,
        capture_output=True,
        text=True,
    )

    op_file = tmp_path / "Update" / "opFile.txt"
    assert op_file.exists()
    assert "movehex" in op_file.read_text(encoding="utf-8")
