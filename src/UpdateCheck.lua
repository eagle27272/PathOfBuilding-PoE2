#@
-- Path of Building
--
-- Module: Update Check
-- Checks for updates
--
local connectionProtocol, proxyURL, noSSL = ...

local xml = require("xml")
local sha1 = require("sha1")
local curl = require("lcurl.safe")
local lzip = require("lzip")

local globalRetryLimit = 10
local function normalizePlatform(platform)
	if not platform or platform == "" then
		return nil
	end
	platform = platform:lower()
	if platform == "darwin" or platform == "mac" or platform == "macos" or platform == "osx" then
		return "macos"
	elseif platform == "windows" or platform == "win" or platform == "win32" or platform:match("^mingw") or platform:match("^msys") or platform:match("^cygwin") then
		return "win32"
	end
	return platform
end

local function normalizeArchitecture(architecture)
	if not architecture or architecture == "" then
		return nil
	end
	architecture = architecture:lower()
	if architecture == "x86_64" or architecture == "amd64" or architecture == "x64" then
		return "x64"
	elseif architecture == "arm64" or architecture == "aarch64" then
		return "arm64"
	elseif architecture == "i386" or architecture == "i686" or architecture == "x86" then
		return "x86"
	elseif architecture:match("^armv7") or architecture == "armhf" then
		return "armv7"
	elseif architecture:match("^armv6") then
		return "armv6"
	end
	return architecture
end

local function getNodePlatform(node)
	return normalizePlatform(node.attrib.platform or node.attrib.runtime)
end

local function getNodeArchitecture(node)
	return normalizeArchitecture(node.attrib.architecture or node.attrib.arch)
end

local function nodeMatchesLocalTarget(nodePlatform, nodeArchitecture, localPlatform, localArchitecture)
	if nodePlatform and nodePlatform ~= localPlatform then
		return false
	end
	if nodeArchitecture and (not localArchitecture or nodeArchitecture ~= localArchitecture) then
		return false
	end
	return true
end

local function safeManifestFileName(name)
	if type(name) ~= "string" or name == "" then
		return nil
	end
	name = name:gsub("{space}", " ")
	if name:find('[%c"]') then
		return nil
	end
	if name:find("{slash}", 1, true) then
		return nil
	end
	if name:sub(1, 1) == "/" or name:sub(-1) == "/" or name:find("\\", 1, true) or name:find("//", 1, true) or name:match("^%a:") then
		return nil
	end
	for segment in name:gmatch("[^/]+") do
		if segment == "." or segment == ".." then
			return nil
		end
	end
	return name
end

local function detectLocalPlatform()
	if not jit or not jit.os then
		return nil
	end
	return normalizePlatform(jit.os)
end

local function detectLocalArchitecture()
	if not jit or not jit.arch then
		return nil
	end
	return normalizeArchitecture(jit.arch)
end

local function isRuntimeExecutableName(name)
	name = name:gsub("{space}", " ")
	return name == "Path of Building-PoE2.exe"
		or name == "PathOfBuilding-PoE2.exe"
		or name == "PathOfBuilding-PoE2"
		or name == "Path of Building-PoE2"
		or name:match("%.app/Contents/MacOS/Path of Building%-PoE2$") ~= nil
end

local function shouldMakeExecutable(data, localPlatform)
	if localPlatform == "win32" then
		return false
	end
	local name = data.name:gsub("{space}", " ")
	return name:match("%.command$") ~= nil
		or name:match("%.sh$") ~= nil
		or (data.part == "runtime" and isRuntimeExecutableName(name))
end

local function hexEncode(value)
	local out = { }
	for index = 1, #value do
		out[index] = string.format("%02x", value:byte(index))
	end
	return table.concat(out)
end

local function appendEncodedOperation(ops, op, ...)
	local line = { op.."hex" }
	for index = 1, select("#", ...) do
		table.insert(line, hexEncode(select(index, ...)))
	end
	table.insert(ops, table.concat(line, " "))
end

local function appendMoveOperation(ops, data, localPlatform)
	appendEncodedOperation(ops, "move", data.updateFileName, data.fullPath)
	if shouldMakeExecutable(data, localPlatform) then
		appendEncodedOperation(ops, "chmod", data.fullPath)
	end
end

local function downloadFileText(source, file)
	for i = 1, 5 do
		if i > 1 then
			ConPrintf("Retrying... (%d of 5)", i)
		end
		local text = ""
		local easy = curl.easy()
		local escapedUrl = source..easy:escape(file)
		easy:setopt_url(escapedUrl)
		easy:setopt(curl.OPT_ACCEPT_ENCODING, "")
		if connectionProtocol then
			easy:setopt(curl.OPT_IPRESOLVE, connectionProtocol)
		end
		if proxyURL then
			easy:setopt(curl.OPT_PROXY, proxyURL)
		end
		if noSSL then
			easy:setopt(curl.OPT_SSL_VERIFYPEER, 0)
			easy:setopt(curl.OPT_SSL_VERIFYHOST, 0)
			ConPrintf("SSL verification disabled")
		end
		easy:setopt_writefunction(function(data)
			text = text..data 
			return true
		end)
		local _, error = easy:perform()
		easy:close()
		if not error then
			return text
		end
		ConPrintf("Download failed (%s)", error:msg())
		if globalRetryLimit == 0 or i == 5 then
			return nil, error:msg()
		end
		globalRetryLimit = globalRetryLimit - 1
	end
end
local function downloadFile(source, file, outName)
	for i = 1, 5 do
		if i > 1 then
			ConPrintf("Retrying... (%d of 5)", i)
		end
		local easy = curl.easy()
		local escapedUrl = source..easy:escape(file)
		easy:setopt_url(escapedUrl)
		easy:setopt(curl.OPT_ACCEPT_ENCODING, "")
		if connectionProtocol then
			easy:setopt(curl.OPT_IPRESOLVE, connectionProtocol)
		end
		if proxyURL then
			easy:setopt(curl.OPT_PROXY, proxyURL)
		end
		if noSSL then
			easy:setopt(curl.OPT_SSL_VERIFYPEER, 0)
			easy:setopt(curl.OPT_SSL_VERIFYHOST, 0)
			ConPrintf("SSL verification disabled")
		end
		local file = io.open(outName, "wb+")
		easy:setopt_writefunction(file)
		local _, error = easy:perform()
		easy:close()
		file:close()
		if not error then
			return true
		end
		ConPrintf("Download failed (%s)", error:msg())
		if globalRetryLimit == 0 or i == 5 then
			return nil, error:msg()
		end
		globalRetryLimit = globalRetryLimit - 1
	end
	return true
end

ConPrintf("Checking for update...")

-- Use built-in helpers to obtain absolute paths without spawning a shell.
local scriptPath, scriptFallback = GetScriptPath()
scriptPath = scriptPath or scriptFallback or "."
local runtimePath, runtimeFallback = GetRuntimePath()
runtimePath = runtimePath or runtimeFallback or scriptPath

-- Load and process local manifest
local localVer
local localPlatform, localArchitecture, localBranch
local localFiles = { }
local localManXML = xml.LoadXMLFile(scriptPath.."/manifest.xml")
local localSource
local runtimeExecutable
local invalidLocalManifest = false
if localManXML and localManXML[1].elem == "PoBVersion" then
	for _, node in ipairs(localManXML[1]) do
		if type(node) == "table" then
			if node.elem == "Version" then
				localVer = node.attrib.number
				localPlatform = normalizePlatform(node.attrib.platform)
				localArchitecture = getNodeArchitecture(node)
				localBranch = node.attrib.branch
			elseif node.elem == "Source" then
				if node.attrib.part == "default" then
					localSource = node.attrib.url
				end
			elseif node.elem == "File" then
				local name = safeManifestFileName(node.attrib.name)
				if not name then
					invalidLocalManifest = true
				else
					local fullPath
					local filePlatform = getNodePlatform(node)
					local fileArchitecture = getNodeArchitecture(node)
					if node.attrib.part == "runtime" then
						fullPath = runtimePath .. "/" .. name
					else
						fullPath = scriptPath .. "/" .. name
					end
					localFiles[name] = { sha1 = node.attrib.sha1, part = node.attrib.part, platform = filePlatform, architecture = fileArchitecture, fullPath = fullPath }
					if node.attrib.part == "runtime" and isRuntimeExecutableName(name) then
						runtimeExecutable = fullPath
					end
				end
			end
		end
	end
end
if invalidLocalManifest or not localVer or not localSource or not localBranch or not next(localFiles) then
	ConPrintf("Update check failed: invalid local manifest")
	return nil, "Invalid local manifest"
end
localPlatform = localPlatform or detectLocalPlatform()
localArchitecture = localArchitecture or detectLocalArchitecture()
localSource = localSource:gsub("{branch}", localBranch)

-- Download and process remote manifest
local remoteVer
local remoteFiles = { }
local remoteSources = { }
local invalidRemoteManifest = false
local remoteManText, errMsg = downloadFileText(localSource, "manifest.xml")
if not remoteManText then
	ConPrintf("Update check failed: couldn't download version manifest")
	return nil, "Couldn't download version manifest.\nReason: "..errMsg.."\nCheck your internet connectivity.\nIf you are using a proxy, specify it in Options."
end
local remoteManXML = xml.ParseXML(remoteManText)
if remoteManXML and remoteManXML[1].elem == "PoBVersion" then
	for _, node in ipairs(remoteManXML[1]) do
		if type(node) == "table" then
			if node.elem == "Version" then
				remoteVer = node.attrib.number
			elseif node.elem == "Source" then
				if not remoteSources[node.attrib.part] then
					remoteSources[node.attrib.part] = { }
				end
				local platform = getNodePlatform(node)
				local architecture = getNodeArchitecture(node)
				if platform and architecture then
					remoteSources[node.attrib.part][platform.."/"..architecture] = node.attrib.url
				elseif platform then
					remoteSources[node.attrib.part][platform] = node.attrib.url
				else
					remoteSources[node.attrib.part]["any"] = node.attrib.url
				end
			elseif node.elem == "File" then
				local filePlatform = getNodePlatform(node)
				local fileArchitecture = getNodeArchitecture(node)
				if nodeMatchesLocalTarget(filePlatform, fileArchitecture, localPlatform, localArchitecture) then
					local name = safeManifestFileName(node.attrib.name)
					if not name then
						invalidRemoteManifest = true
					else
						local fullPath
						if node.attrib.part == "runtime" then
							fullPath = runtimePath .. "/" .. name
						else
							fullPath = scriptPath .. "/" .. name
						end
						remoteFiles[name] = { sha1 = node.attrib.sha1, part = node.attrib.part, platform = filePlatform, architecture = fileArchitecture, fullPath = fullPath }
					end
				end
			end
		end
	end
end
if invalidRemoteManifest or not remoteVer or not next(remoteSources) or not next(remoteFiles) then
	ConPrintf("Update check failed: invalid remote manifest")
	return nil, "Invalid remote manifest"
end

-- Build lists of files to be updated or deleted
local updateFiles = { }
for name, data in pairs(remoteFiles) do
	data.name = name
	local sanitizedName = name:gsub("{space}", " ")
	if (not localFiles[name] or localFiles[name].sha1 ~= data.sha1) and (not localFiles[sanitizedName] or localFiles[sanitizedName].sha1 ~= data.sha1) then
		table.insert(updateFiles, data)
	elseif localFiles[name] then
		local file = io.open(localFiles[name].fullPath, "rb")
		if not file then
			ConPrintf("Warning: '%s' doesn't exist, it will be re-downloaded", data.name)
			table.insert(updateFiles, data)
		else
			local content = file:read("*a")
			file:close()
			if data.sha1 ~= sha1(content) and data.sha1 ~= sha1(content:gsub("\n", "\r\n")) then
				ConPrintf("Warning: Integrity check on '%s' failed, it will be replaced", data.name)
				table.insert(updateFiles, data)
			end
		end
	end
end
local deleteFiles = { }
for name, data in pairs(localFiles) do
	data.name = name
	local unSanitizedName = name:gsub(" ", "{space}")
	if not remoteFiles[name] and not remoteFiles[unSanitizedName] then
		table.insert(deleteFiles, data)
	end
end
	
if #updateFiles == 0 and #deleteFiles == 0 then
	ConPrintf("No update available.")
	return "none"
end

MakeDir("Update")
ConPrintf("Downloading update...")

-- Download changelog
downloadFile(localSource, "changelog.txt", scriptPath.."/changelog.txt")

-- Download files that need updating
local failedFile = false
local zipFiles = { }
for index, data in ipairs(updateFiles) do
	if UpdateProgress then
		UpdateProgress("Downloading %d/%d", index, #updateFiles)
	end
	local partSources = remoteSources[data.part]
	if not partSources then
		ConPrintf("Update failed: no source for manifest part '%s'", data.part)
		return nil, "No update source is defined for manifest part '"..data.part.."'."
	end
	local platformArch = localPlatform and localArchitecture and (localPlatform.."/"..localArchitecture)
	local source = (platformArch and partSources[platformArch]) or partSources[localPlatform] or partSources["any"]
	if not source then
		ConPrintf("Update failed: no source for manifest part '%s' on platform '%s' architecture '%s'", data.part, localPlatform or "any", localArchitecture or "any")
		return nil, "No update source is defined for '"..data.part.."' on platform '"..(localPlatform or "any").."' architecture '"..(localArchitecture or "any").."'."
	end
	source = source:gsub("{branch}", localBranch)
	local fileName = scriptPath.."/Update/"..data.name:gsub("[\\/]","{slash}")
	data.updateFileName = fileName
	local zipName = source:match("/([^/]+%.zip)$")
	if zipName then
		if not zipFiles[zipName] then
			ConPrintf("Downloading %s...", zipName)
			local zipFileName = scriptPath.."/Update/"..zipName
			downloadFile(source, "", zipFileName)
			zipFiles[zipName] = lzip.open(zipFileName)
		end
		local zip = zipFiles[zipName]
		if zip then
			local zippedFile = zip:OpenFile(data.name)
			if zippedFile then
				local file = io.open(fileName, "wb+")
				file:write(zippedFile:Read("*a"))
				file:close()
				zippedFile:Close()
			else
				ConPrintf("Couldn't extract '%s' from '%s' (extract failed)", data.name, zipName)
			end
		else
			ConPrintf("Couldn't extract '%s' from '%s' (zip open failed)", data.name, zipName)
		end
	else
		local skipDownload
		local file = io.open(fileName, "rb")
		if file then
			local content = file:read("*all")
			if data.sha1 == sha1(content) or data.sha1 == sha1(content:gsub("\n", "\r\n")) then
				ConPrintf("Using file from previous update attempt '%s'", fileName)
				skipDownload = true
			end
			file:close()
		end
		if not skipDownload then
			ConPrintf("Downloading %s... (%d of %d)", data.name, index, #updateFiles)
			downloadFile(source, data.name, fileName)
		end
	end
	local file = io.open(fileName, "rb")
	if not file then
		failedFile = true
	else
		local content = file:read("*all")
		if data.sha1 ~= sha1(content) and data.sha1 ~= sha1(content:gsub("\n", "\r\n")) then
			ConPrintf("Hash mismatch on '%s'", fileName)
			failedFile = true
		end
		file:close()
	end
end
for name, zip in pairs(zipFiles) do
	zip:Close()
	os.remove(scriptPath.."/Update/"..name)
end
if failedFile then
	ConPrintf("Update failed: one or more files couldn't be downloaded")
	return nil, "One or more files couldn't be downloaded.\nCheck your internet connectivity,\nor try again later."
end

-- Create new manifest
localManXML = { elem = "PoBVersion" }
table.insert(localManXML, { elem = "Version", attrib = { number = remoteVer, platform = localPlatform, architecture = localArchitecture, branch = localBranch } })
for part, sources in pairs(remoteSources) do
	for key, url in pairs(sources) do
		local platform, architecture
		if key ~= "any" then
			platform, architecture = key:match("^([^/]+)/(.+)$")
			if not platform then
				platform = key
			end
		end
		table.insert(localManXML, { elem = "Source", attrib = { part = part, platform = platform, architecture = architecture, url = url } })
	end
end
for name, data in pairs(remoteFiles) do
	table.insert(localManXML, { elem = "File", attrib = { name = data.name, sha1 = data.sha1, part = data.part, platform = data.platform, architecture = data.architecture } })
end 
xml.SaveXMLFile(localManXML, scriptPath.."/Update/manifest.xml")

-- Build list of operations to apply the update
local updateMode = "normal"
local ops = { }
local opsRuntime = { }
for _, data in pairs(updateFiles) do
	-- Ensure that the destination path of this file exists
	local dirStr = data.fullPath:sub(1,1) == "/" and "/" or ""
	for dir in data.fullPath:gmatch("([^/]+/)") do
		dirStr = dirStr .. dir
		MakeDir(dirStr)
	end
	if data.part == "runtime" then
		-- Core runtime file, will need to update from the basic environment
		-- These files will be updated on the second pass of the update script, with the first pass being run within the normal environment
		updateMode = "basic"
		appendMoveOperation(opsRuntime, data, localPlatform)
	else
		appendMoveOperation(ops, data, localPlatform)
	end
end
for _, data in pairs(deleteFiles) do
	appendEncodedOperation(ops, "delete", data.fullPath)
end
appendEncodedOperation(ops, "move", scriptPath.."/Update/manifest.xml", scriptPath.."/manifest.xml")
if updateMode == "basic" then
	-- Update script will need to relaunch the normal environment after updating
	runtimeExecutable = runtimeExecutable or runtimePath.."/PathOfBuilding-PoE2"
	appendEncodedOperation(opsRuntime, "start", runtimeExecutable)
	local opRuntimeFile = io.open(scriptPath.."/Update/opFileRuntime.txt", "w+")
	opRuntimeFile:write(table.concat(opsRuntime, "\n"))
	opRuntimeFile:close()
end

-- Write operations file
local opFile = io.open(scriptPath.."/Update/opFile.txt", "w+")
opFile:write(table.concat(ops, "\n"))
opFile:close()

ConPrintf("Update is ready.")
return updateMode
