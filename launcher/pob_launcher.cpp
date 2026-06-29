#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#ifdef _WIN32
#include <Windows.h>
#include <shellapi.h>
#else
#include <dlfcn.h>
#include <limits.h>
#include <unistd.h>
#if defined(__APPLE__) && defined(__MACH__)
#include <libproc.h>
#endif
#endif

namespace fs = std::filesystem;

using RunLuaFileProc = int (*)(int, char**);

struct LaunchScript {
	fs::path path;
	std::string directive;
};

std::string trim(std::string value)
{
	auto notSpace = [](unsigned char ch) { return !std::isspace(ch); };
	value.erase(value.begin(), std::find_if(value.begin(), value.end(), notSpace));
	value.erase(std::find_if(value.rbegin(), value.rend(), notSpace).base(), value.end());
	return value;
}

std::optional<std::string> launcherDirective(fs::path const& path)
{
	std::ifstream file(path, std::ios::binary);
	if (!file) {
		return {};
	}
	char header[256]{};
	file.read(header, sizeof(header) - 1);
	std::string firstBytes(header, static_cast<size_t>(file.gcount()));
	if (firstBytes.rfind("\xEF\xBB\xBF", 0) == 0) {
		firstBytes.erase(0, 3);
	}
	if (firstBytes.rfind("#@", 0) != 0) {
		return {};
	}
	auto newline = firstBytes.find('\n');
	if (newline == std::string::npos) {
		return {};
	}
	return trim(firstBytes.substr(2, newline - 2));
}

bool insertIfLaunchScript(std::vector<std::string>& args, fs::path const& path, std::string& directive)
{
	if (auto parsedDirective = launcherDirective(path)) {
		directive = *parsedDirective;
		args.insert(args.begin() + 1, fs::weakly_canonical(path).u8string());
		return true;
	}
	return false;
}

std::optional<fs::path> executablePath(char const* argv0)
{
#ifdef _WIN32
	(void)argv0;
	std::wstring buf(32768, L'\0');
	auto len = GetModuleFileNameW(nullptr, buf.data(), static_cast<DWORD>(buf.size()));
	if (len == 0) {
		return {};
	}
	buf.resize(len);
	return fs::path(buf);
#elif defined(__linux__)
	(void)argv0;
	char buf[PATH_MAX]{};
	auto len = readlink("/proc/self/exe", buf, sizeof(buf) - 1);
	if (len <= 0) {
		return {};
	}
	buf[len] = '\0';
	return fs::path(buf);
#elif defined(__APPLE__) && defined(__MACH__)
	(void)argv0;
	char buf[PROC_PIDPATHINFO_MAXSIZE]{};
	if (proc_pidpath(getpid(), buf, sizeof(buf)) <= 0) {
		return {};
	}
	return fs::path(buf);
#else
	if (!argv0 || !*argv0) {
		return {};
	}
	return fs::absolute(argv0);
#endif
}

std::vector<fs::path> launchSearchRoots(fs::path const& exeDir)
{
	std::vector<fs::path> roots;
	auto add = [&roots](fs::path path) {
		path = fs::weakly_canonical(path);
		if (std::find(roots.begin(), roots.end(), path) == roots.end()) {
			roots.push_back(std::move(path));
		}
	};

	add(exeDir);
	add(fs::current_path());
	if (exeDir.has_parent_path()) {
		add(exeDir.parent_path());
	}
	if (exeDir.has_parent_path() && exeDir.parent_path().has_parent_path()) {
		add(exeDir.parent_path().parent_path());
	}
	return roots;
}

std::optional<LaunchScript> findLaunchScript(std::vector<std::string>& args, fs::path const& exeDir)
{
	std::string directive;
	if (args.size() > 1 && launcherDirective(args[1])) {
		directive = *launcherDirective(args[1]);
		return LaunchScript{fs::weakly_canonical(args[1]), directive};
	}

	for (auto const& root : launchSearchRoots(exeDir)) {
		for (auto const& candidate : {root / "Launch.lua", root / "src" / "Launch.lua"}) {
			if (insertIfLaunchScript(args, candidate, directive)) {
				return LaunchScript{fs::weakly_canonical(candidate), directive};
			}
		}
	}
	return {};
}

std::string normalizeDirectivePathSeparators(std::string value)
{
#ifndef _WIN32
	std::replace(value.begin(), value.end(), '\\', '/');
#endif
	return value;
}

std::string lower(std::string value)
{
	std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
		return static_cast<char>(std::tolower(ch));
	});
	return value;
}

bool startsWith(std::string const& value, std::string_view prefix)
{
	return value.size() >= prefix.size() && value.compare(0, prefix.size(), prefix) == 0;
}

std::string luaPathList(std::vector<fs::path> const& paths)
{
	std::string value;
	for (auto const& path : paths) {
		if (!value.empty()) {
			value += ';';
		}
		value += path.generic_string();
	}
	return value;
}

#ifdef _WIN32
std::wstring luaPathListWide(std::vector<fs::path> const& paths)
{
	std::wstring value;
	for (auto const& path : paths) {
		if (!value.empty()) {
			value += L';';
		}
		value += path.wstring();
	}
	return value;
}

std::wstring getEnvironmentWide(wchar_t const* name)
{
	auto size = GetEnvironmentVariableW(name, nullptr, 0);
	if (size == 0) {
		return {};
	}
	std::wstring value(size, L'\0');
	auto written = GetEnvironmentVariableW(name, value.data(), size);
	value.resize(written);
	return value;
}

void prependLuaEnvironment(wchar_t const* name, std::wstring value)
{
	auto existing = getEnvironmentWide(name);
	value += existing.empty() ? L";;" : L";" + existing;
	SetEnvironmentVariableW(name, value.c_str());
}
#else
void prependLuaEnvironment(char const* name, std::string value)
{
	if (auto existing = std::getenv(name); existing && *existing) {
		value += ';';
		value += existing;
	} else {
		value += ";;";
	}
	setenv(name, value.c_str(), 1);
}
#endif

void configureLuaEnvironment(fs::path const& runtimeDir)
{
	std::vector<fs::path> luaPaths{
		runtimeDir / "lua" / "?.lua",
		runtimeDir / "lua" / "?" / "init.lua",
	};

#ifdef _WIN32
	std::vector<fs::path> luaCPaths{
		runtimeDir / "?.dll",
		runtimeDir / "lua" / "?.dll",
	};
	prependLuaEnvironment(L"LUA_PATH", luaPathListWide(luaPaths));
	prependLuaEnvironment(L"LUA_CPATH", luaPathListWide(luaCPaths));
#else
	std::vector<fs::path> luaCPaths{
		runtimeDir / "?.so",
		runtimeDir / "lua" / "?.so",
	};
	prependLuaEnvironment("LUA_PATH", luaPathList(luaPaths));
	prependLuaEnvironment("LUA_CPATH", luaPathList(luaCPaths));
#endif
}

std::string nativeSharedLibraryExtension()
{
#ifdef _WIN32
	return ".dll";
#elif defined(__APPLE__) && defined(__MACH__)
	return ".dylib";
#else
	return ".so";
#endif
}

std::string nativeSharedLibraryName(std::string const& baseName)
{
#ifdef _WIN32
	return baseName + ".dll";
#elif defined(__APPLE__) && defined(__MACH__)
	return (startsWith(lower(baseName), "lib") ? baseName : "lib" + baseName) + ".dylib";
#else
	return (startsWith(lower(baseName), "lib") ? baseName : "lib" + baseName) + ".so";
#endif
}

std::vector<fs::path> libraryCandidates(std::string const& directive, fs::path const& exeDir)
{
	std::vector<fs::path> names;
	auto addName = [&names](fs::path path) {
		if (std::find(names.begin(), names.end(), path) == names.end()) {
			names.push_back(std::move(path));
		}
	};

	fs::path requested(normalizeDirectivePathSeparators(directive));
	fs::path parent = requested.parent_path();
	std::string fileName = requested.filename().u8string();
	std::string stem = requested.stem().u8string();
	std::string extension = lower(requested.extension().u8string());

	auto addWithParent = [&](std::string const& name) {
		addName(parent.empty() ? fs::path(name) : parent / name);
	};

	if (extension.empty()) {
		addWithParent(nativeSharedLibraryName(fileName));
#ifndef _WIN32
		addWithParent(fileName + nativeSharedLibraryExtension());
#endif
		addWithParent(fileName);
	} else {
#ifdef _WIN32
		if (extension == ".so" || extension == ".dylib") {
			addWithParent(stem + ".dll");
		}
#else
		if (extension == ".dll") {
			addWithParent(nativeSharedLibraryName(stem));
			addWithParent(stem + nativeSharedLibraryExtension());
		}
#endif
		addName(requested);
	}

	std::vector<fs::path> candidates;
	auto addCandidate = [&candidates](fs::path path) {
		if (std::find(candidates.begin(), candidates.end(), path) == candidates.end()) {
			candidates.push_back(std::move(path));
		}
	};
	for (auto const& name : names) {
		if (name.is_absolute()) {
			addCandidate(name);
		} else {
			addCandidate(exeDir / name);
			addCandidate(name);
		}
	}
	return candidates;
}

class SharedLibrary {
public:
	explicit SharedLibrary(fs::path const& path)
	{
#ifdef _WIN32
		handle = LoadLibraryW(path.wstring().c_str());
#else
		handle = dlopen(path.c_str(), RTLD_NOW);
#endif
	}

	~SharedLibrary()
	{
		if (!handle) {
			return;
		}
#ifdef _WIN32
		FreeLibrary(static_cast<HMODULE>(handle));
#else
		dlclose(handle);
#endif
	}

	explicit operator bool() const { return handle != nullptr; }

	RunLuaFileProc symbol(char const* name) const
	{
#ifdef _WIN32
		return reinterpret_cast<RunLuaFileProc>(GetProcAddress(static_cast<HMODULE>(handle), name));
#else
		return reinterpret_cast<RunLuaFileProc>(dlsym(handle, name));
#endif
	}

private:
#ifdef _WIN32
	HMODULE handle = nullptr;
#else
	void* handle = nullptr;
#endif
};

std::vector<std::string> commandLineUtf8(int argc, char** argv)
{
#ifdef _WIN32
	std::vector<std::string> args;
	int wideArgc = 0;
	auto wideArgv = CommandLineToArgvW(GetCommandLineW(), &wideArgc);
	if (!wideArgv) {
		return args;
	}
	args.reserve(static_cast<size_t>(wideArgc));
	for (int i = 0; i < wideArgc; ++i) {
		int len = WideCharToMultiByte(CP_UTF8, 0, wideArgv[i], -1, nullptr, 0, nullptr, nullptr);
		std::string value(static_cast<size_t>(len - 1), '\0');
		WideCharToMultiByte(CP_UTF8, 0, wideArgv[i], -1, value.data(), len, nullptr, nullptr);
		args.push_back(std::move(value));
	}
	LocalFree(wideArgv);
	return args;
#else
	return std::vector<std::string>(argv, argv + argc);
#endif
}

int main(int argc, char** argv)
{
	auto args = commandLineUtf8(argc, argv);
	if (args.empty()) {
		args.emplace_back("PathOfBuilding-PoE2");
	}

	auto exePath = executablePath(args[0].c_str()).value_or(fs::absolute(args[0]));
	auto exeDir = fs::weakly_canonical(exePath.parent_path());
	configureLuaEnvironment(exeDir);

	auto launchScript = findLaunchScript(args, exeDir);
	if (!launchScript) {
		std::cerr << "ERROR: Could not find a valid Launch.lua file.\n";
		return 1;
	}

	std::vector<std::string> luaArgs(args.begin() + 1, args.end());
	std::vector<char*> luaArgv;
	luaArgv.reserve(luaArgs.size());
	for (auto& arg : luaArgs) {
		luaArgv.push_back(arg.data());
	}

	for (auto const& candidate : libraryCandidates(launchScript->directive, exeDir)) {
		SharedLibrary library(candidate);
		if (!library) {
			continue;
		}
		if (auto runLuaFile = library.symbol("RunLuaFileAsWin")) {
			return runLuaFile(static_cast<int>(luaArgv.size()), luaArgv.data());
		}
		if (auto runLuaFile = library.symbol("RunLuaFileAsConsole")) {
			return runLuaFile(static_cast<int>(luaArgv.size()), luaArgv.data());
		}
		std::cerr << "ERROR: Runtime library '" << candidate.string()
			<< "' does not export a Path of Building entry point.\n";
		return 1;
	}

	std::cerr << "ERROR: Could not load native runtime library for '#@ "
		<< launchScript->directive << "' next to " << exePath.string() << ".\n";
	return 1;
}
