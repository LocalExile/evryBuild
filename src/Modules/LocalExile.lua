-- evryBuild - POB for LocalExile.
-- Integration for PathOfBuildingCommunity/PathOfBuilding master.
-- Loaded by the Import/Export Build tab.
local json = require("dkjson")
local M = { }
local attachedTab = ...
local MAX_RESPONSE = 128 * 1024
local BRAND = "evryBuild"
local SUBTITLE = "POB for LocalExile"
local BUTTON = "Forge Character"

local function trim(value)
	return tostring(value or ""):gsub("^%s+", ""):gsub("%s+$", "")
end

function M.ValidateServer(value)
	local url = trim(value):gsub("/+$", "")
	if #url > 2048 or url:find("[%s%c]") or url:find("[?#]") then
		return nil, "Enter a server URL without spaces, query parameters or a fragment."
	end
	local scheme, authority, path = url:match("^(%a+)://([^/]+)(.*)$")
	if not scheme or authority:find("@", 1, true) then
		return nil, "Enter http://127.0.0.1:20496 or an HTTPS server URL without embedded credentials."
	end
	scheme = scheme:lower()
	if scheme ~= "http" and scheme ~= "https" then return nil, "Only HTTP and HTTPS server URLs are supported." end
	local host, port
	if authority:sub(1, 1) == "[" then
		host, port = authority:match("^(%[[%x:]+%]):(%d+)$")
		if not host then host = authority:match("^(%[[%x:]+%])$") end
	else
		host, port = authority:match("^([%w%.%-]+):(%d+)$")
		if not host then host = authority:match("^([%w%.%-]+)$") end
	end
	if not host or port and (tonumber(port) < 1 or tonumber(port) > 65535) then
		return nil, "The server host or port is invalid."
	end
	if path:find("\\", 1, true) or path:find("/../", 1, true) or path:match("/%.%.$") then
		return nil, "The server URL contains an invalid path."
	end
	local loopback = host:lower() == "localhost" or host == "127.0.0.1" or host == "[::1]"
	if scheme == "http" and not loopback then
		return nil, "Remote servers require HTTPS. HTTP is allowed only for localhost, 127.0.0.1 or [::1]."
	end
	return scheme .. "://" .. authority .. path
end

function M.ReadPreferences(path)
	local defaults = { serverUrl = "http://127.0.0.1:20496", account = "", league = "Standard" }
	local file = io.open(path, "rb")
	if not file then return defaults end
	local contents = file:read(16385)
	file:close()
	if not contents or #contents > 16384 then return defaults, "LocalExile preferences are too large; defaults were loaded." end
	local value, _, err = json.decode(contents)
	if err or type(value) ~= "table" then return defaults, "LocalExile preferences could not be read; defaults were loaded." end
	for key, maximum in pairs({ serverUrl = 2048, account = 128, league = 128 }) do
		if type(value[key]) == "string" and #value[key] <= maximum then defaults[key] = value[key] end
	end
	return defaults
end

-- Only nonsecret settings belong in this file. Tokens are intentionally not accepted by this writer.
function M.SavePreferences(path, preferences)
	local contents = json.encode({ serverUrl = preferences.serverUrl, account = preferences.account, league = preferences.league }, { indent = true })
	local temp = path .. ".tmp"
	local file, err = io.open(temp, "wb")
	if not file then return nil, err end
	local written, writeError = file:write(contents .. "\n")
	local closed, closeError = file:close()
	if not written or not closed then os.remove(temp); return nil, writeError or closeError end
	-- Windows rename cannot replace an existing file. Preserve the old preferences until the new file is complete.
	local backup = path .. ".backup"
	local old = io.open(path, "rb")
	if old then
		old:close()
		os.remove(backup)
		local moved, moveError = os.rename(path, backup)
		if not moved then os.remove(temp); return nil, moveError end
	end
	local moved, moveError = os.rename(temp, path)
	if not moved then
		if old then os.rename(backup, path) end
		os.remove(temp)
		return nil, moveError
	end
	if old then os.remove(backup) end
	return true
end

-- A dedicated PoB worker avoids DownloadPage's redirect-following and global disable-TLS option.
-- No body, authorization header or token is written to PoB's console.
M.RequestScript = [[
	local url, authorization, body = ...
	local curl = require("lcurl.safe")
	local easy = curl.easy()
	local chunks, length = {}, 0
	local tooLarge = false
	easy:setopt_url(url)
	easy:setopt(curl.OPT_POST, true)
	easy:setopt(curl.OPT_POSTFIELDS, body)
	easy:setopt(curl.OPT_HTTPHEADER, {
		"Content-Type: application/json", "Accept: application/json", "Authorization: Bearer " .. authorization
	})
	easy:setopt(curl.OPT_FOLLOWLOCATION, 0)
	easy:setopt(curl.OPT_CONNECTTIMEOUT, 10)
	easy:setopt(curl.OPT_TIMEOUT, 60)
	easy:setopt(curl.OPT_SSL_VERIFYPEER, 1)
	easy:setopt(curl.OPT_SSL_VERIFYHOST, 2)
	easy:setopt(curl.OPT_WRITEFUNCTION, function(data)
		length = length + #data
		if length > 131072 then tooLarge = true; return false end
		chunks[#chunks + 1] = data
		return true
	end)
	local _, failure = easy:perform()
	local status = tonumber(easy:getinfo(curl.INFO_RESPONSE_CODE)) or 0
	easy:close()
	if tooLarge then return nil, "The server response exceeded 128 KiB.", status end
	if failure then return nil, failure:msg(), status end
	if status >= 300 and status < 400 then
		return nil, "The server redirected this request. Enter its final HTTPS address; redirects are not followed.", status
	end
	return table.concat(chunks), nil, status
]]

function M.Request(url, token, payload, callback)
	local body, encodeError = json.encode(payload)
	if not body then callback(nil, encodeError); return end
	local id = LaunchSubScript(M.RequestScript, "", "", url, token, body)
	if not id then callback(nil, "PoB could not start the server request."); return end
	-- DOWNLOAD registration also delivers worker errors to the callback instead of leaving the dialog busy.
	launch.subScripts[id] = {
		type = "DOWNLOAD",
		callback = function(responseBody, err, status)
			if err then callback(nil, err); return end
			if type(responseBody) ~= "string" or #responseBody > MAX_RESPONSE then
				callback(nil, "The server returned an invalid response."); return
			end
			local response, _, decodeError = json.decode(responseBody)
			if decodeError or type(response) ~= "table" or type(response.ok) ~= "boolean" then
				callback(nil, "The server did not return LocalExile JSON (HTTP " .. tostring(status or "unknown") .. ")."); return
			end
			if status ~= 200 or not response.ok then
				callback(nil, type(response.error) == "string" and response.error or "The server refused the request (HTTP " .. tostring(status) .. ").")
				return
			end
			callback(response)
		end,
	}
end

local function display(value)
	return tostring(value or ""):gsub("%c", " "):gsub("%^", "")
end

function M.Describe(response)
	local lines = {
		response.preview and "Preview passed. No character was created." or "Character created: " .. display(response.character),
		string.format("%s level %s | League: %s", display(response.class), display(response.level), display(response.league)),
		string.format("%s items, %s socketed gems, %s passives, %s masteries", display(response.items), display(response.gems), display(response.passives), display(response.masteries)),
	}
	if type(response.warnings) == "table" then
		for _, warning in ipairs(response.warnings) do lines[#lines + 1] = "- " .. display(warning) end
	end
	if type(response.next) == "string" then lines[#lines + 1] = display(response.next) end
	return table.concat(lines, "\n")
end

function M.Open(tab)
	local preferencesPath = main.userPath .. "LocalExile.json"
	local preferences, preferencesWarning = M.ReadPreferences(preferencesPath)
	local controls = { }
	local busy, closed = false, false
	local function field(name, label, y, initial, maximum)
		controls[name .. "Label"] = new("LabelControl", { "TOPLEFT", nil, "TOPLEFT" }, { 20, y + 3, 0, 16 }, label)
		controls[name] = new("EditControl", { "TOPLEFT", nil, "TOPLEFT" }, { 160, y, 490, 22 }, initial, nil, "%c", maximum)
		controls[name].enabled = function() return not busy end
	end
	controls.intro = new("LabelControl", { "TOPLEFT", nil, "TOPLEFT" }, { 20, 24, 0, 16 }, SUBTITLE)
	field("serverUrl", "Server URL", 58, preferences.serverUrl, 2048)
	field("account", "Local account", 92, preferences.account, 128)
	field("token", "Account API token", 126, "", 512)
	controls.token:SetProtected(true)
	field("name", "New character", 160, "", 23)
	field("league", "League", 194, preferences.league, 128)
	controls.note = new("LabelControl", { "TOPLEFT", nil, "TOPLEFT" }, { 20, 234, 0, 14 }, "URL, account and league are saved here; the API token stays in this dialog only.")
	controls.results = new("EditControl", { "TOPLEFT", nil, "TOPLEFT" }, { 20, 262, 630, 214 }, preferencesWarning or "Preview first to check compatibility. Forge Character sends this build to your server.", nil, "%z", 32768, nil, 16)
	local function result(text) controls.results:SetText(text) end
	local function submit(preview)
		if busy or closed then return end
		local server, error = M.ValidateServer(controls.serverUrl.buf)
		if not server then result(error); return end
		local account, token = trim(controls.account.buf), trim(controls.token.buf)
		local name, league = trim(controls.name.buf), trim(controls.league.buf)
		if account == "" or token == "" then result("Enter your LocalExile account and its API token supplied by the server owner."); return end
		if token:find("[%s%c]") then result("The API token must not contain whitespace."); return end
		if not preview and (#name < 3 or #name > 23 or name:find("[^%w_%-]")) then
			result("Choose a new character name: 3-23 letters, digits, underscores or hyphens."); return
		end
		if league == "" then result("Enter a league offered by the server, such as Standard."); return end
		local ok, code = pcall(function()
			return common.base64.encode(Deflate(tab.build:SaveDB("code"))):gsub("+", "-"):gsub("/", "_")
		end)
		if not ok or type(code) ~= "string" or code == "" then result("PoB could not export this build: " .. display(code)); return end
		local saved, saveError = M.SavePreferences(preferencesPath, { serverUrl = server, account = account, league = league })
		if not saved then result("Could not save LocalExile connection settings: " .. display(saveError)); return end
		busy = true
		result(preview and "Validating build with the server..." or "Forging character on the server...")
		M.Request(server .. (preview and "/api/pob/preview" or "/api/pob/characters"), token,
			{ code = code, account = account, name = name, league = league }, function(response, requestError)
				busy = false
				if closed then return end
				if requestError then
					local message = "Request failed:\n" .. requestError:gsub("%^", "")
					if not preview then message = message .. "\nIf the connection was interrupted, refresh the character list before retrying. Existing characters are never replaced." end
					result(message)
					return
				end
				result(M.Describe(response))
				if not preview then controls.token:SetText("") end
			end)
	end
	controls.preview = new("ButtonControl", { "TOPLEFT", nil, "TOPLEFT" }, { 20, 498, 130, 26 }, "Preview", function() submit(true) end)
	controls.create = new("ButtonControl", { "TOPLEFT", nil, "TOPLEFT" }, { 166, 498, 180, 26 }, BUTTON, function() submit(false) end)
	controls.close = new("ButtonControl", { "TOPLEFT", nil, "TOPLEFT" }, { 540, 498, 110, 26 }, "Close", function()
		if busy then return end
		closed = true
		controls.token:SetText("")
		main:ClosePopup()
	end)
	for _, name in ipairs({ "preview", "create", "close" }) do controls[name].enabled = function() return not busy end end
	return main:OpenPopup(670, 544, BRAND, controls, "preview", "serverUrl", "close")
end

function M.Attach(tab)
	if tab.controls.localExileSend then return end
	APP_NAME = BRAND .. " - " .. SUBTITLE
	if main.SetWindowTitleSubtext then main:SetWindowTitleSubtext() end
	tab.controls.sectionBuild.height = 222
	tab.controls.localExileSend = new("ButtonControl", { "TOPLEFT", tab.controls.importCodeMode, "BOTTOMLEFT" },
		{ 0, 12, 180, 24 }, BUTTON, function() M.Open(tab) end)
	tab.controls.localExileNote = new("LabelControl", { "LEFT", tab.controls.localExileSend, "RIGHT" },
		{ 12, 0, 0, 14 }, "Preview or create a character on your configured server.")
end

if type(attachedTab) == "table" and attachedTab.controls then M.Attach(attachedTab) end
return M
