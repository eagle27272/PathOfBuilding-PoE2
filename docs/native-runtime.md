# Native Runtime

Path of Building's Lua application is platform-neutral, but it needs a small
native host runtime to provide rendering, input, networking, subprocesses, and
Lua module loading.

The repository supports platform- and architecture-specific runtime payloads
under:

```text
runtime/<platform>-<architecture>/
```

Examples:

```text
runtime/macos-arm64/
runtime/macos-x64/
runtime/linux-x64/
runtime/linux-riscv64/
runtime/win32-x64/
```

The native runtime directory must contain:

```text
PathOfBuilding-PoE2
libSimpleGraphic.<so|dylib>
lcurl.<so|dylib>
lzip.<so|dylib>
socket.<so|dylib>
lua-utf8.<so|dylib>
```

Windows keeps using the legacy `runtime/` layout until the installer and release
pipeline move to the same target directory scheme.

The root `Path of Building-PoE2.command` launcher detects the current platform
and CPU architecture, then executes the matching native launcher. Set
`POB_WINE=/path/to/wine` or `POB_ALLOW_WINE=1` to opt into the legacy Windows
runtime while native artifacts are unavailable.

## Building The Native Launcher

The portable launcher source lives in `launcher/` and has no third-party
dependencies.

```sh
cmake -S launcher -B build/launcher -DCMAKE_BUILD_TYPE=Release
cmake --build build/launcher --config Release
```

Install or copy the resulting executable into the matching runtime target
directory as `PathOfBuilding-PoE2`.

The helper script below detects the host platform/architecture and packages the
launcher into the corresponding runtime directory:

```sh
scripts/package-native-runtime.sh
```

The script refuses to label a launcher for a different platform/architecture
than the host it was built on. Set `POB_LAUNCHER_ALLOW_CROSS_TARGET=1` only when
you are using a matching cross compiler or toolchain and intentionally creating
a cross-target artifact. `POB_RUNTIME_TARGET` accepts the same safe
`<platform>-<architecture>` and `<architecture>-<platform>` aliases as release
archives, then packages into the canonical target name.

To overlay native SimpleGraphic artifacts at the same time:

```sh
SIMPLEGRAPHIC_INSTALL_DIR=/path/to/simplegraphic/install scripts/package-native-runtime.sh
```

To create a distributable runtime archive after packaging:

```sh
tar -C runtime/macos-arm64 -cf PathOfBuildingRuntime-macos-arm64.tar .
```

The `Build native launcher runtimes` GitHub Actions workflow builds these
launcher-only archives for macOS, Linux, and Windows x64/arm64 targets. Workflow
runs upload them as artifacts, and published releases attach them as release
assets. Pair the launcher archive with the matching SimpleGraphic runtime
archive before publishing or installing a complete native runtime directory.

The `update-simple-graphic` repository dispatch can also merge launcher runtime
assets from this repository while importing a SimpleGraphic release. Include
`launcher_tag` in the dispatch payload to download `PathOfBuildingRuntime-*`
assets from the current repository, or include both `launcher_tag` and
`launcher_release_repo` to fetch launcher assets from another repository.

Release automation accepts these archive names:

```text
PathOfBuildingRuntime-<platform>-<architecture>.tar
SimpleGraphicRuntime-<platform>-<architecture>.tar
SimpleGraphicDLLs-x64-windows.tar
```

`scripts/install-runtime-assets.sh <asset-directory>` installs those archives
into the correct runtime directory and keeps the historical Windows x64 archive
in the legacy `runtime/` layout. Archive extraction rejects absolute paths,
parent-directory traversal, unsupported special file types, unsafe symlink or
hardlink targets, and members that would resolve outside the target runtime
directory through pre-existing symlinks before installing any files.

Common aliases are normalized before installation or packaging. For example,
`darwin-aarch64` becomes `macos-arm64`, `linux-amd64` becomes `linux-x64`, and
`riscv64-freebsd` becomes `freebsd-riscv64`. ARM hard-float aliases such as
`armhf-linux` normalize to `linux-armv7` instead of the generic `linux-arm`, so
32-bit ARM runtime artifacts keep their ABI-specific target name. Unknown
platforms are accepted as long as the archive target is a safe two-part
`<platform>-<architecture>` name.

`update_manifest.py` discovers any installed `runtime/<platform>-<architecture>/`
directory when `manifest.cfg` has `discover-targets = true` for the runtime
section. New native targets therefore only need matching runtime assets; they do
not need a new manifest section unless their layout differs from the standard
target directory scheme.

## Packaging A Portable App

After installing the matching launcher and SimpleGraphic runtime archives, build
a portable zip for a specific target:

```sh
scripts/package-portable.py --platform macos --architecture arm64 --branch dev
```

The package script copies files from `manifest.xml`, filters runtime files to the
requested platform/architecture, and writes a local manifest stamped with the
package's `branch`, `platform`, and `architecture`. That stamp is required for
the in-app updater to select the correct native runtime source after install.
The portable packager and in-app updater both reject absolute,
parent-traversal, backslash-style, quote-containing, and control-character
manifest file names, plus the reserved `{slash}` token used for update
downloads, before copying or applying files.
New update operation files hex-encode filesystem paths while `UpdateApply.lua`
keeps support for the previous quoted operation format.

To package every runtime target that has files in `manifest.xml`:

```sh
scripts/package-portable.py --all-targets --branch master
```

The `Build native portable packages` GitHub Actions workflow runs the same
all-target packaging path for releases and uploads the generated `Dist/*.zip`
assets. It stamps packaged manifests with `master` by default so released
portable apps continue receiving normal updates.

## Smoke Testing A Native Runtime

Use the smoke script to check that a target runtime directory has a native
launcher and the expected SimpleGraphic library:

```sh
POB_RUNTIME_PLATFORM=macos POB_RUNTIME_ARCHITECTURE=arm64 scripts/smoke-native-runtime.sh
```

Set `POB_SMOKE_RUN=1` to run through the root launcher after the file checks
pass. This is useful for CI or local validation with a test SimpleGraphic library
because it proves the launcher can load the native runtime entry point.

## Building SimpleGraphic

The rendering/runtime library comes from
`PathOfBuildingCommunity/PathOfBuilding-SimpleGraphic`. That project already has
partial non-Windows code paths, but its published releases currently ship only
Windows x64 artifacts. A complete native release needs SimpleGraphic and its Lua
extension modules built for each target platform/architecture and published into
the matching runtime directory described above.
