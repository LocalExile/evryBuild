#@
-- evryBuild
--
-- Module: Update Apply
-- Applies the operations UpdateCheck wrote, inside the running application. Windows lets a running exe or a loaded
-- DLL be renamed but not overwritten, so every replaced or deleted file is first renamed to "<name>.old" and the
-- staged file is moved into its place. If any step fails, every step already taken is undone in reverse, so the
-- installation is either the old release or the new one. The .old files are deleted on the next start
-- (CleanUp), once nothing holds them. Returns true, or nil and an error.
--
-- Ops (one per line):  replace "<staged>" "<target>"   delete "<target>"   manifest "<pending>" "<manifest.xml>"
--
local opFileName, cleanUpOnly = ...

local cleanUpList = "Update/cleanup.txt"

local function exists(path)
	local file = io.open(path, "rb")
	if file then file:close() end
	return file ~= nil
end

local function makeParents(path)
	local dir = ""
	for part in path:gmatch("([^/]+)/") do
		dir = dir .. part .. "/"
		if not dir:match("^%a:/$") then MakeDir(dir) end
	end
end

-- Deletes the .old files earlier updates left behind; any still locked are kept for the next start.
local function cleanUp()
	local file = io.open(cleanUpList, "r")
	if not file then return end
	local remaining = { }
	for line in file:lines() do
		if line ~= "" and exists(line) and not os.remove(line) then
			remaining[#remaining + 1] = line
		end
	end
	file:close()
	if #remaining == 0 then
		os.remove(cleanUpList)
	else
		local out = io.open(cleanUpList, "w")
		if out then
			out:write(table.concat(remaining, "\n") .. "\n")
			out:close()
		end
	end
end

if cleanUpOnly then
	cleanUp()
	return true
end

if ConPrintf then ConPrintf("Applying update...") end
local opFile = io.open(opFileName, "r")
if not opFile then
	return nil, "No update is staged."
end
local ops = { }
for line in opFile:lines() do
	local op, args = line:match("^(%a+) ?(.*)$")
	if op == "replace" or op == "manifest" then
		local src, dst = args:match('^"(.-)" "(.-)"$')
		if not src then
			opFile:close()
			return nil, "The staged update is malformed."
		end
		ops[#ops + 1] = { op = op, src = src, dst = dst }
	elseif op == "delete" then
		local dst = args:match('^"(.-)"$')
		if not dst then
			opFile:close()
			return nil, "The staged update is malformed."
		end
		ops[#ops + 1] = { op = op, dst = dst }
	elseif line:match("%S") then
		opFile:close()
		return nil, "The staged update has an unknown step: " .. line
	end
end
opFile:close()
for _, step in ipairs(ops) do
	if step.src and not exists(step.src) then
		return nil, "A staged file is missing: " .. step.src
	end
end

local undo, oldFiles = { }, { }
local function rollback()
	for i = #undo, 1, -1 do
		local step = undo[i]
		if step.placed then
			os.rename(step.dst, step.src)
		end
		if step.moved then
			os.remove(step.dst)
			os.rename(step.dst .. ".old", step.dst)
		end
	end
end

for _, step in ipairs(ops) do
	local done = { src = step.src, dst = step.dst }
	undo[#undo + 1] = done
	if exists(step.dst) then
		os.remove(step.dst .. ".old")
		local moved, err = os.rename(step.dst, step.dst .. ".old")
		if not moved then
			undo[#undo] = nil
			rollback()
			return nil, "Couldn't replace " .. step.dst .. ": " .. tostring(err)
		end
		done.moved = true
		oldFiles[#oldFiles + 1] = step.dst .. ".old"
	end
	if step.op ~= "delete" then
		makeParents(step.dst)
		local placed, err = os.rename(step.src, step.dst)
		if not placed then
			rollback()
			return nil, "Couldn't install " .. step.dst .. ": " .. tostring(err)
		end
		done.placed = true
	end
end

-- Committed: the .old files are only waste now.
local list = io.open(cleanUpList, "a")
if list then
	list:write(table.concat(oldFiles, "\n") .. "\n")
	list:close()
end
os.remove(opFileName)
cleanUp()
return true
