#@
-- Path of Building
--
-- Module: Update Apply
-- Applies updates.
--
local opFileName = ...

local chmod
local isPosix = package.config:sub(1, 1) == "/"
local unpackTable = table.unpack or unpack
local function shellQuote(value)
	return "'"..value:gsub("'", "'\\''").."'"
end

local function hexDecode(value)
	if not value or #value % 2 ~= 0 or value:match("[^%x]") then
		error("invalid encoded update operation path")
	end
	return (value:gsub("(%x%x)", function(byte)
		return string.char(tonumber(byte, 16))
	end))
end

local function hexArgs(args, expected)
	local values = { }
	for value in args:gmatch("%S+") do
		table.insert(values, hexDecode(value))
	end
	assert(#values == expected, "invalid encoded update operation")
	return unpackTable(values)
end

if isPosix and jit and jit.os ~= "Windows" then
	local ok, ffi = pcall(require, "ffi")
	if ok then
		local cdefOk = pcall(ffi.cdef, "int chmod(const char *path, int mode);")
		if cdefOk then
			chmod = function(path)
				assert(ffi.C.chmod(path, 493) == 0, "couldn't chmod "..path)
			end
		end
	end
end
if isPosix and not chmod then
	chmod = function(path)
		local ok = os.execute("chmod +x "..shellQuote(path))
		assert(ok == true or ok == 0, "couldn't chmod "..path)
	end
end

print("Applying update...")
local opFile = io.open(opFileName, "r")
if not opFile then
	print("No operations list present.\n")
	return
end
local lines = { }
for line in opFile:lines() do
	table.insert(lines, line)
end
opFile:close()
os.remove(opFileName)
for _, line in ipairs(lines) do
	local op, args = line:match("(%a+) ?(.*)")
	if op == "move" or op == "movehex" then
		local src, dst
		if op == "movehex" then
			src, dst = hexArgs(args, 2)
		else
			src, dst = args:match('"(.*)" "(.*)"')
			dst = dst:gsub("{space}", " ")
		end
		print("Updating '"..dst.."'")
		local srcFile = io.open(src, "rb")
		assert(srcFile, "couldn't open "..src)
		local dstFile
		while not dstFile do
			dstFile = io.open(dst, "w+b")
		end
		if dstFile then
			dstFile:write(srcFile:read("*a"))
			dstFile:close()
		end
		srcFile:close()
		os.remove(src)
	elseif op == "delete" or op == "deletehex" then
		local file = op == "deletehex" and hexArgs(args, 1) or args:match('"(.*)"')
		print("Deleting '"..file.."'")
		os.remove(file)
	elseif op == "chmod" or op == "chmodhex" then
		local file = op == "chmodhex" and hexArgs(args, 1) or args:match('"(.*)"')
		print("Making executable '"..file.."'")
		if chmod then
			chmod(file)
		end
	elseif op == "start" or op == "starthex" then
		local target = op == "starthex" and hexArgs(args, 1) or args:match('"(.*)"')
		SpawnProcess(target)
	end
end
