-- evryBuild - POB for LocalExile. Entirely local SQLite exporter.
local json = require("dkjson")
local M = { }
local attachedTab = ...
local BUTTON = "Export to LocalExile"
local function trim(value) return tostring(value or ""):gsub("^%s+", ""):gsub("%s+$", "") end
function M.ReadPreferences(path)
	local defaults = { database = "", dataFolder = "", account = "", league = "Standard" }
	local file = io.open(path, "rb")
	if not file then return defaults end
	local contents = file:read(16385)
	file:close()
	if not contents or #contents > 16384 then return defaults, "LocalExile preferences are too large; defaults were loaded." end
	local value, _, err = json.decode(contents)
	if err or type(value) ~= "table" then return defaults, "LocalExile preferences could not be read; defaults were loaded." end
	for key, maximum in pairs({ database = 32768, dataFolder = 32768, account = 128, league = 128 }) do
		if type(value[key]) == "string" and #value[key] <= maximum then defaults[key] = value[key] end
	end
	return defaults
end

-- Only nonsecret settings belong in this file. Tokens are intentionally not accepted by this writer.
function M.SavePreferences(path, preferences)
	local contents = json.encode({ database = preferences.database, dataFolder = preferences.dataFolder, account = preferences.account, league = preferences.league }, { indent = true })
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

local function display(value) return tostring(value or ""):gsub("%c", " "):gsub("%^", "") end
M.WorkerScript = [[
    local modulePath, executable, body = ...
    local native = assert(loadfile(modulePath))()
    return native.Run(executable, body, 60000)
]]
function M.Request(payload, callback)
    local body, encodeError = json.encode(payload)
    if not body then callback(nil, encodeError); return end
    local root = GetRuntimePath():gsub("[/\\]+$", "")
    local id = LaunchSubScript(M.WorkerScript, "", "", GetScriptPath() .. "/Modules/LocalExileNative.lua",
        root .. "/LocalExile/evryBuild.Export.exe", body)
    if not id then callback(nil, "Could not start the local export worker."); return end
    launch.subScripts[id] = { type = "DOWNLOAD", callback = function(text, err)
        if err then callback(nil, err); return end
        if type(text) ~= "string" or #text > 128*1024 then callback(nil, "Invalid exporter result."); return end
        local reply, _, decodeError = json.decode(text)
        if decodeError or type(reply) ~= "table" or type(reply.ok) ~= "boolean" then callback(nil, "The bundled exporter did not return valid JSON."); return end
        if not reply.ok then callback(nil, reply.error or "Export failed."); return end
        callback(reply)
    end }
end
function M.Describe(reply)
    local lines = { reply.preview and "Preview complete. No character was created." or "Character created: " .. display(reply.character),
        string.format("%s level %s | %s",display(reply.class),display(reply.level),display(reply.league)),
        string.format("%s items, %s gems, %s passives, %s masteries",display(reply.items),display(reply.gems),display(reply.passives),display(reply.masteries)),
        string.format("Omitted encoding: %s items, %s enabled gems",display(reply.skippedItems),display(reply.skippedGems)) }
    lines[#lines+1]=display(reply.next)
    if reply.backup then lines[#lines+1]="SQLite backup: "..display(reply.backup) end
    if reply.compatibilityReport then lines[#lines+1]="Full compatibility report: "..display(reply.compatibilityReport) end
    for _, warning in ipairs(reply.warnings or {}) do lines[#lines+1]="- "..display(warning) end
    lines[#lines+1]="Gameplay compatibility (valid entries are kept):"
    for _, finding in ipairs(reply.compatibility or {}) do
        lines[#lines+1]=string.format("[%s] %s: %s — %s",display(finding.status),display(finding.source),display(finding.effect),display(finding.reason))
    end
    if reply.warningsTruncated or (reply.compatibilityCount or 0)>#(reply.compatibility or {}) then
        lines[#lines+1]="Details shortened; counts cover the complete export."
    end
    local text=table.concat(lines,"\n")
    if #text>32768 then return text:sub(1,32500).."\nDisplay shortened. Export saves the full compatibility report beside the backup." end
    return text
end
function M.Open(tab)
    local path=main.userPath.."LocalExile.json"
    local preferences,warning=M.ReadPreferences(path)
    local controls={}; local busy=false; local closed=false; local previewKey; local checkedBuild
    local function field(name,label,y,value,width)
        controls[name.."Label"]=new("LabelControl",{"TOPLEFT",nil,"TOPLEFT"},{20,y+3,0,16},label)
        controls[name]=new("EditControl",{"TOPLEFT",nil,"TOPLEFT"},{160,y,width or 490,22},value,nil,"%c",32768)
        controls[name].enabled=function() return not busy end
    end
    field("database","Save database",42,preferences.database,395)
    field("dataFolder","Game data folder",76,preferences.dataFolder,395)
    field("account","Existing account",110,preferences.account)
    field("name","New character",144,"")
    field("league","League",178,preferences.league)
    controls.note=new("LabelControl",{"TOPLEFT",nil,"TOPLEFT"},{20,214,0,14},"Local export: no API or token. Missing gameplay effects are kept when loadable.")
    controls.results=new("EditControl",{"TOPLEFT",nil,"TOPLEFT"},{20,240,630,265},warning or "Choose saves.db. Game data is detected beside it; Browse if stored elsewhere.",nil,"%z",32768,nil,16)
    local function result(text) controls.results:SetText(text) end
    local function inspect()
        if busy then return end
        previewKey=nil; busy=true
        M.Request({operation="inspect",database=trim(controls.database.buf),dataFolder=trim(controls.dataFolder.buf)},function(reply,err)
            busy=false; if closed then return end
            if err then result(err); return end
            if reply.dataFolder then controls.dataFolder:SetText(reply.dataFolder) end
            local accounts=reply.accounts or {}
            local selected=trim(controls.account.buf):lower()
            local matched
            for _,account in ipairs(accounts) do if account:lower()==selected then matched=account; break end end
            -- A database can belong to several people. Never silently choose its first account.
            controls.account:SetText(matched or (#accounts==1 and accounts[1]) or "")
            result("Accounts: "..table.concat(reply.accounts or {},", ").."\nExisting leagues: "..table.concat(reply.leagues or {},", ")..
                "\nServer version: "..display(reply.serverVersion).."\n"..display(reply.next))
        end)
    end
    local function browse(kind)
        if busy then return end
        local ok,native=pcall(function() return assert(loadfile(GetScriptPath().."/Modules/LocalExileNative.lua"))() end)
        if not ok then result(native); return end
        local chosen,err=native.PickFile(kind)
        if err then result(err); return end
        if chosen then
            if kind=="data" then controls.dataFolder:SetText(chosen:match("^(.*)[/\\]"))
            else controls.database:SetText(chosen); controls.dataFolder:SetText("") end
            previewKey=nil; inspect()
        end
    end
    controls.databaseBrowse=new("ButtonControl",{"TOPLEFT",nil,"TOPLEFT"},{565,42,85,22},"Browse...",function() browse("database") end)
    controls.dataBrowse=new("ButtonControl",{"TOPLEFT",nil,"TOPLEFT"},{565,76,85,22},"Browse...",function() browse("data") end)
    local function submit(preview)
        if busy then return end
        local ok,code=pcall(function() return tab.build:SaveDB("code") end)
        if not ok or type(code)~="string" then result("Could not export the active build."); return end
        local request={operation=preview and "preview" or "export", database=trim(controls.database.buf),dataFolder=trim(controls.dataFolder.buf),
            account=trim(controls.account.buf),name=trim(controls.name.buf),league=trim(controls.league.buf),code=code}
        local fingerprint=json.encode({request.database,request.dataFolder,request.account,request.name,request.league,code})
        if not preview and (not previewKey or checkedBuild~=fingerprint) then previewKey=nil; result("Preview the current build and destination before exporting."); return end
        request.previewKey=preview and nil or previewKey; previewKey=nil
        M.SavePreferences(path,request)
        busy=true; result(preview and "Checking the local build and database..." or "Backing up SQLite and exporting the character...")
        M.Request(request,function(reply,err)
            busy=false; if closed then return end
            if err then result(err); return end
            if preview then previewKey=reply.previewKey; checkedBuild=fingerprint end
            result(M.Describe(reply))
        end)
    end
    controls.inspect=new("ButtonControl",{"TOPLEFT",nil,"TOPLEFT"},{20,525,105,26},"Inspect DB",inspect)
    controls.preview=new("ButtonControl",{"TOPLEFT",nil,"TOPLEFT"},{140,525,110,26},"Preview",function() submit(true) end)
    controls.create=new("ButtonControl",{"TOPLEFT",nil,"TOPLEFT"},{265,525,220,26},BUTTON,function() submit(false) end)
    controls.close=new("ButtonControl",{"TOPLEFT",nil,"TOPLEFT"},{540,525,110,26},"Close",function() if not busy then closed=true; main:ClosePopup() end end)
    for _,name in ipairs({"inspect","preview","create","close","databaseBrowse","dataBrowse"}) do controls[name].enabled=function() return not busy end end
    controls.create.enabled=function() return not busy and previewKey~=nil end
    return main:OpenPopup(670,570,"evryBuild - Export to LocalExile",controls,"databaseBrowse","database","close")
end
function M.Attach(tab)
    if tab.controls.localExileSend then return end
    tab.controls.sectionBuild.height=222
    tab.controls.localExileSend=new("ButtonControl",{"TOPLEFT",tab.controls.importCodeMode,"BOTTOMLEFT"},{0,12,190,24},BUTTON,function() M.Open(tab) end)
    tab.controls.localExileNote=new("LabelControl",{"LEFT",tab.controls.localExileSend,"RIGHT"},{12,0,0,14},"Export to a local saves.db; no API required.")
end
if type(attachedTab)=="table" and attachedTab.controls then M.Attach(attachedTab) end
return M
