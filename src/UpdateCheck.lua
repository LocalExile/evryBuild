#@
-- evryBuild
--
-- Module: Update Check
-- Runs as a background subscript in two modes:
--   "check"    downloads the latest release's update manifest and compares it with the installed one.
--              It writes the manifest to Update/pending.xml and returns
--              "available", release, files, bytes  or  "none", release  or  nil, error.
--   "download" downloads every changed file from Update/pending.xml into Update/files, checks each SHA-256,
--              and writes Update/opFile.txt for UpdateApply. It returns "ready", "native"|"normal"  or  nil, error.
--
-- The installed manifest.xml names where updates come from (its Update element). A release manifest lists every
-- application file with the SHA-256 of the bytes its source serves, so nothing is applied unless all of it arrived
-- intact. A copy built from source has no Update element and never checks.
--
local mode, connectionProtocol = ...

local xml = require("xml")
local sha2 = require("sha2")
local curl = require("lcurl.safe")

-- Only these hosts may serve files, plus the origin the installed manifest's own Update URL names (a test server).
local trustedPrefixes = {
	"https://github.com/LocalExile/evryBuild/releases/",
	"https://raw.githubusercontent.com/LocalExile/evryBuild/",
}
-- Never written, replaced or deleted by an update: personal data and the updater's own state.
local privateNames = {
	["builds"] = true, ["settings.xml"] = true, ["localexile.json"] = true, ["imgui.ini"] = true, ["update"] = true,
	["installed.cfg"] = true, ["first.run"] = true, [".git"] = true, ["logs"] = true, ["evrybuild-backups"] = true,
	["manifest.xml"] = true,
}

local scriptPath = GetScriptPath() or "."
local function report(...)
	if UpdateProgress then UpdateProgress(...) end
end

local function readFile(path)
	local file = io.open(path, "rb")
	if not file then return nil end
	local content = file:read("*a")
	file:close()
	return content
end

local function writeFile(path, content)
	local file, err = io.open(path, "wb")
	if not file then return nil, err end
	file:write(content)
	file:close()
	return true
end

-- A path relative to the application folder that cannot leave it or touch personal data.
local function safeName(name)
	if type(name) ~= "string" or name == "" or #name > 260 then return false end
	if name:find('[%c:\\"*?<>|]') or name:sub(1, 1) == "/" or name:sub(-1) == "/" or name:find("//", 1, true) then
		return false
	end
	for part in name:gmatch("[^/]+") do
		local lower = part:lower()
		if part == "." or part == ".." or privateNames[lower] or lower:match("%.old$") or lower:match("[ %.]$") then
			return false
		end
	end
	return true
end

local function origin(url)
	return type(url) == "string" and url:match("^(https?://[^/]+/)") or nil
end

local function trustedUrl(url, localOrigin)
	if type(url) ~= "string" or url:find("[%s%c\"]") then return false end
	for _, prefix in ipairs(trustedPrefixes) do
		if url:sub(1, #prefix) == prefix then return true end
	end
	return localOrigin ~= nil and url:sub(1, #localOrigin) == localOrigin
end

-- Each path segment is escaped on its own: an escaped "/" is not a path separator to every server.
local function escapePath(easy, path)
	local parts = { }
	for part in path:gmatch("[^/]+") do
		parts[#parts + 1] = easy:escape(part)
	end
	return table.concat(parts, "/")
end

local userAgent = "evryBuild-updater"

-- Downloads url into a file (when outName is given) or a string. Three attempts; HTTP errors fail.
local function download(url, outName)
	local lastError
	for attempt = 1, 3 do
		if attempt > 1 then ConPrintf("Retrying %s (%d of 3)", url, attempt) end
		local easy = curl.easy()
		easy:setopt_url(url)
		easy:setopt(curl.OPT_USERAGENT, userAgent)
		easy:setopt(curl.OPT_FOLLOWLOCATION, 1)
		easy:setopt(curl.OPT_MAXREDIRS, 5)
		easy:setopt(curl.OPT_FAILONERROR, 1)
		easy:setopt(curl.OPT_CONNECTTIMEOUT, 20)
		easy:setopt(curl.OPT_LOW_SPEED_LIMIT, 1)
		easy:setopt(curl.OPT_LOW_SPEED_TIME, 60)
		if connectionProtocol then easy:setopt(curl.OPT_IPRESOLVE, connectionProtocol) end
		local chunks, file = { }, nil
		if outName then
			file = io.open(outName, "wb")
			if not file then
				easy:close()
				return nil, "Cannot write " .. outName
			end
			easy:setopt_writefunction(file)
		else
			easy:setopt_writefunction(function(data)
				chunks[#chunks + 1] = data
				return true
			end)
		end
		local ok, err = easy:perform()
		local code = tonumber(easy:getinfo(curl.INFO_RESPONSE_CODE)) or 0
		easy:close()
		if file then file:close() end
		if ok then
			return outName and true or table.concat(chunks)
		end
		lastError = code >= 400 and ("the server answered HTTP " .. code) or (err and err:msg()) or "download failed"
		ConPrintf("Download failed: %s (%s)", url, lastError)
		if code >= 400 and code < 500 then
			-- Missing or refused: asking again will not help.
			break
		end
	end
	return nil, lastError
end

local function sha256(content)
	return sha2.sha256(content)
end

-- Reads a manifest: its version, sources, update URL, notes and files (by name).
local function parseManifest(root)
	if not root or root.elem ~= "PoBVersion" then return nil end
	local manifest = { sources = { }, files = { }, notes = "" }
	for _, node in ipairs(root) do
		if type(node) == "table" then
			if node.elem == "Version" then
				manifest.version = node.attrib
			elseif node.elem == "Update" then
				manifest.updateUrl = node.attrib.url
			elseif node.elem == "Source" and node.attrib.part then
				manifest.sources[node.attrib.part] = node.attrib.url
			elseif node.elem == "Notes" then
				manifest.notes = type(node[1]) == "string" and node[1] or ""
			elseif node.elem == "File" and node.attrib.name then
				manifest.files[node.attrib.name] = node.attrib
			end
		end
	end
	return manifest
end

-- A semantic version ("1.2.0", "1.3.0-rc.1"): its three numbers and its pre-release identifiers, or nil.
local function parseVersion(text)
	text = tostring(text or "")
	local major, minor, patch, pre = text:match("^(%d+)%.(%d+)%.(%d+)%-([0-9A-Za-z%-%.]+)$")
	if not major then
		major, minor, patch = text:match("^(%d+)%.(%d+)%.(%d+)$")
	end
	if not major then return nil end
	local version = { tonumber(major), tonumber(minor), tonumber(patch), pre = { } }
	if pre then
		for identifier in (pre .. "."):gmatch("([^%.]*)%.") do
			if identifier == "" then return nil end
			version.pre[#version.pre + 1] = identifier:match("^%d+$") and tonumber(identifier) or identifier
		end
	end
	return version
end

-- Semantic Versioning precedence: numbers first; a pre-release comes before its release; pre-release identifiers
-- compare numerically when both are numbers, a number before a word, words by ASCII; more identifiers come later.
local function compareVersions(a, b)
	for i = 1, 3 do
		if a[i] ~= b[i] then return a[i] < b[i] and -1 or 1 end
	end
	if #a.pre == 0 or #b.pre == 0 then
		return #a.pre == #b.pre and 0 or (#a.pre == 0 and 1 or -1)
	end
	for i = 1, math.max(#a.pre, #b.pre) do
		local x, y = a.pre[i], b.pre[i]
		if x == nil or y == nil then return x == nil and -1 or 1 end
		if x ~= y then
			if type(x) ~= type(y) then return type(x) == "number" and -1 or 1 end
			return x < y and -1 or 1
		end
	end
	return 0
end

-- Whether the release is newer than the installed copy. A copy whose version cannot be read takes any release.
local function newerRelease(remote, installed)
	local a, b = parseVersion(remote), parseVersion(installed)
	if not a then return false end
	return not b or compareVersions(a, b) > 0
end

local localManifest = parseManifest((xml.LoadXMLFile(scriptPath .. "/manifest.xml") or { })[1])
if not localManifest or not localManifest.updateUrl or not localManifest.version then
	return nil, "This copy of evryBuild has no update source. Download a release package to update it."
end
local localOrigin = origin(localManifest.updateUrl)
if not trustedUrl(localManifest.updateUrl, localOrigin) then
	return nil, "The installed update source is not trusted."
end
local installedRelease = localManifest.version.release or "?"
userAgent = "evryBuild/" .. installedRelease

-- Checks a downloaded manifest before anything from it is used.
local function validRemote(remote)
	if not remote or not remote.version or not parseVersion(remote.version.release) then
		return nil, "The release's update manifest is invalid."
	end
	if not remote.updateUrl or not trustedUrl(remote.updateUrl, localOrigin) then
		return nil, "The release's update manifest names an untrusted update source."
	end
	local count = 0
	for name, file in pairs(remote.files) do
		if not safeName(name) then
			return nil, "The release's update manifest lists an unsafe file: " .. tostring(name)
		end
		local source = remote.sources[file.part or ""]
		if not source or not trustedUrl(source, localOrigin) or type(file.source) ~= "string" or file.source == ""
				or file.source:find("%.%.") or not (file.sha256 or ""):match("^%x+$") or #file.sha256 ~= 64 then
			return nil, "The release's update manifest has an invalid entry for " .. name
		end
		count = count + 1
	end
	if count == 0 then
		return nil, "The release's update manifest lists no files."
	end
	return true
end

-- The files whose content changed or that are missing here, and the installed files the release no longer has.
local function plan(remote)
	local changed, removed, bytes = { }, { }, 0
	for name, file in pairs(remote.files) do
		local installed = localManifest.files[name]
		local present = io.open(scriptPath .. "/" .. name, "rb")
		if present then present:close() end
		if not installed or installed.sha256 ~= file.sha256 or not present then
			changed[#changed + 1] = name
			bytes = bytes + (tonumber(file.size) or 0)
		end
	end
	for name in pairs(localManifest.files) do
		if not remote.files[name] and safeName(name) then
			removed[#removed + 1] = name
		end
	end
	table.sort(changed)
	table.sort(removed)
	return changed, removed, bytes
end

MakeDir(scriptPath .. "/Update")
local pendingPath = scriptPath .. "/Update/pending.xml"

if mode == "check" then
	ConPrintf("Checking for an evryBuild update...")
	report("Checking...")
	local text, err = download(localManifest.updateUrl)
	if not text then
		return nil, "Couldn't download the update manifest.\n" .. tostring(err)
	end
	local parsed = xml.ParseXML(text)
	local remote = parseManifest(parsed and parsed[1])
	local ok, invalid = validRemote(remote)
	if not ok then return nil, invalid end
	if not newerRelease(remote.version.release, installedRelease) then
		os.remove(pendingPath)
		return "none", installedRelease
	end
	local changed, removed, bytes = plan(remote)
	local saved, writeErr = writeFile(pendingPath, text)
	if not saved then return nil, "Couldn't save the update manifest: " .. tostring(writeErr) end
	ConPrintf("Update %s available: %d file(s) to download, %d to remove", remote.version.release, #changed, #removed)
	return "available", remote.version.release, #changed, bytes
end

if mode == "download" then
	local text = readFile(pendingPath)
	local parsed = text and xml.ParseXML(text)
	local remote = parseManifest(parsed and parsed[1])
	local ok, invalid = validRemote(remote)
	if not ok then return nil, invalid end
	local changed, removed = plan(remote)
	local staging = scriptPath .. "/Update/files"
	MakeDir(staging)
	local ops, native = { }, false
	for index, name in ipairs(changed) do
		local file = remote.files[name]
		local staged = staging .. "/" .. name:gsub("/", "{slash}")
		local content = readFile(staged)
		if content and sha256(content) == file.sha256 then
			ConPrintf("Using %s from an earlier attempt", name)
		else
			report("Downloading %d/%d", index, #changed)
			local easy = curl.easy()
			local url = remote.sources[file.part] .. escapePath(easy, file.source)
			easy:close()
			local done, err = download(url, staged)
			if not done then
				return nil, "Couldn't download " .. name .. ".\n" .. tostring(err)
			end
			content = readFile(staged)
			if not content or sha256(content) ~= file.sha256 then
				os.remove(staged)
				return nil, "The downloaded " .. name .. " does not match the release. Nothing was changed."
			end
		end
		content = nil
		ops[#ops + 1] = 'replace "' .. staged .. '" "' .. scriptPath .. "/" .. name .. '"'
		if file.native == "true" then native = true end
	end
	for _, name in ipairs(removed) do
		ops[#ops + 1] = 'delete "' .. scriptPath .. "/" .. name .. '"'
		if (localManifest.files[name] or { }).native == "true" then native = true end
	end
	ops[#ops + 1] = 'manifest "' .. pendingPath .. '" "' .. scriptPath .. '/manifest.xml"'
	local saved, err = writeFile(scriptPath .. "/Update/opFile.txt", table.concat(ops, "\n") .. "\n")
	if not saved then return nil, "Couldn't write the update plan: " .. tostring(err) end
	report("Ready")
	return "ready", native and "native" or "normal"
end

return nil, "Unknown update mode: " .. tostring(mode)
