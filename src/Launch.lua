#@ SimpleGraphic
-- Path of Building
--
-- Module: Launch
-- Program entry point; loads and runs the Main module within a protected environment
--

local startTime = GetTime()
APP_NAME = "evryBuild - POB for LocalExile"

-- No feature in this edition opens external websites. Documentation/credits remain readable as text.
function OpenURL() return false end

SetWindowTitle(APP_NAME)
ConExecute("set vid_mode 8")
ConExecute("set vid_resizable 3")

launch = { }
SetMainObject(launch)
jit.opt.start('maxtrace=4000','maxmcode=8192')
collectgarbage("setpause", 400)

function launch:OnInit()
	self.devMode = false
	-- evryBuild updates only from its own releases (UpdateCheck), never from the upstream PoB updater.
	self.evryBuildEdition = true
	self.installedMode = false
	self.versionNumber = "?"
	self.versionBranch = "?"
	self.versionPlatform = "?"
	self.lastUpdateCheck = GetTime()
	self.subScripts = { }
	self.startTime = startTime
	-- Upstream's first-run installer downloads PoB; a portable evryBuild is complete as extracted.
	os.remove("first.run")
	local firstRunFile = nil
	local xml = require("xml")
	local localManXML = xml.LoadXMLFile("manifest.xml") or xml.LoadXMLFile("../manifest.xml")
	if localManXML and localManXML[1].elem == "PoBVersion" then
		for _, node in ipairs(localManXML[1]) do
			if type(node) == "table" then
				if node.elem == "Version" then
					self.versionNumber = node.attrib.number
					self.versionBranch = node.attrib.branch
					self.versionPlatform = node.attrib.platform
					self.versionRelease = node.attrib.release
				elseif node.elem == "Update" then
					-- Only a release package names an update source; copies built from source never check.
					self.updateSource = node.attrib.url
				end
			end
		end
	end
	if self.updateSource then
		-- Remove the files the last update replaced, now that nothing holds them.
		PLoadModule("UpdateApply", nil, true)
	end
	if localManXML and not self.versionBranch and not self.versionPlatform then
		-- Looks like a remote manifest, so we're probably running from a repository
		-- Enable dev mode to disable updates and set user path to be the script path
		self.devMode = true
	end
	local installedFile = io.open("installed.cfg", "r")
	if installedFile then
		self.installedMode = true
		installedFile:close()
	end
	RenderInit("DPI_AWARE")
	ConPrintf("Loading main script...")
	local errMsg
	errMsg, self.main = PLoadModule("Modules/Main")
	if errMsg then
		self:ShowErrMsg("Error loading main script: %s", errMsg)
	elseif not self.main then
		self:ShowErrMsg("Error loading main script: no object returned")
	elseif self.main.Init then
		errMsg = PCall(self.main.Init, self.main)
		if errMsg then
			self:ShowErrMsg("In 'Init': %s", errMsg)
		end
	end

	if not self.devMode and not firstRunFile and self:UpdateChecksEnabled() then
		-- Run a background update check if developer mode is off
		self:CheckForUpdate(true)
	end
end

-- Whether to look for a release at start and every 12 hours (Options: "Check for updates at startup").
function launch:UpdateChecksEnabled()
	return self.updateSource ~= nil and not (self.main and self.main.checkForUpdates == false)
end

function launch:CanExit()
	if self.main and self.main.CanExit and not self.promptMsg then
		local errMsg, ret = PCall(self.main.CanExit, self.main)
		if errMsg then
			self:ShowErrMsg("In 'CanExit': %s", errMsg)
			return false
		else
			return ret
		end
	end
	return true
end

function launch:OnExit()
	if self.main and self.main.Shutdown then
		PCall(self.main.Shutdown, self.main)
	end
end

function launch:OnFrame()
	if self.main then
		if self.main.OnFrame then
			local errMsg = PCall(self.main.OnFrame, self.main)
			if errMsg then
				-- Send user to build list menu if a build crashes on initial load
				if self.main.modes.BUILD.outputRevision == 1 and self.main.modes.BUILD.buildFlag and not self.devMode then
					main:SetMode("LIST")
				end
				self:ShowErrMsg("In 'OnFrame': %s", errMsg)
			end
		end
	end
	self.devModeAlt = self.devMode and IsKeyDown("ALT")
	SetDrawLayer(1000)
	SetViewport()
	if self.promptMsg then
		local r, g, b = unpack(self.promptCol)
		self:DrawPopup(r, g, b, "^0%s", self.promptMsg)
	end
	if self.doRestart then
		local screenW, screenH = GetVirtualScreenSize()
		SetDrawColor(0, 0, 0, 0.75)
		DrawImage(nil, 0, 0, screenW, screenH)
		SetDrawColor(1, 1, 1)
		DrawString(0, screenH/2, "CENTER", 24, "FIXED", self.doRestart)
		Restart()
	end
	if not self.devMode and self:UpdateChecksEnabled() and (GetTime() - self.lastUpdateCheck) > 1000*60*60*12 then
		-- Do an update check every 12 hours if the user keeps the program open
		self:CheckForUpdate(true)
	end
end

function launch:OnKeyDown(key, doubleClick)
	if key == "F5" and self.devMode then
		self.doRestart = "Restarting..."
	elseif key == "F6" and self.devMode then
		local before = collectgarbage("count")
		collectgarbage("collect")
		ConPrintf("%dkB => %dkB", before, collectgarbage("count"))
	elseif key == "PAUSE" and self.devMode and profiler then
		if profiling then
			profiler.stop()
			profiler.report("profiler.log")
			profiling = false
		else
			profiler.start()
			profiling = true
		end
	elseif key == "u" and IsKeyDown("CTRL") then
		if not self.devMode then
			self:CheckForUpdate()
		end
	elseif key == "PRINTSCREEN" and IsKeyDown("CTRL") then
		TakeScreenshot()
	elseif self.promptMsg then
		self:RunPromptFunc(key)
	else
		if self.main and self.main.OnKeyDown then
			local errMsg = PCall(self.main.OnKeyDown, self.main, key, doubleClick)
			if errMsg then
				self:ShowErrMsg("In 'OnKeyDown': %s", errMsg)
			end
		end
	end
end

function launch:OnKeyUp(key)
	if not self.promptMsg then
		if self.main and self.main.OnKeyUp then
			local errMsg = PCall(self.main.OnKeyUp, self.main, key)
			if errMsg then
				self:ShowErrMsg("In 'OnKeyUp': %s", errMsg)
			end
		end
	end
end

function launch:OnChar(key)
	if self.promptMsg then
		self:RunPromptFunc(key)
	else
		if self.main and self.main.OnChar then
			local errMsg = PCall(self.main.OnChar, self.main, key)
			if errMsg then
				self:ShowErrMsg("In 'OnChar': %s", errMsg)
			end
		end
	end
end

function launch:OnSubCall(func, ...)
	if func == "UpdateProgress" then
		self.updateProgress = string.format(...)
	end
	if _G[func] then
		return _G[func](...)
	end
end

function launch:OnSubError(id, errMsg)
	if self.subScripts[id].type == "UPDATE" then
		ConPrintf("Update error: %s", tostring(errMsg))
		if not (self.subScripts[id].background and self.subScripts[id].mode == "check") then
			self.updateErrMsg = tostring(errMsg)
		end
		self.updateCheckRunning = false
	elseif self.subScripts[id].type == "DOWNLOAD" then
		local errMsg = PCall(self.subScripts[id].callback, nil, errMsg)
		if errMsg then
			self:ShowErrMsg("In download callback: %s", errMsg)
		end
	end
	self.subScripts[id] = nil
end

function launch:OnSubFinished(id, ...)
	if self.subScripts[id].type == "UPDATE" then
		local sub = self.subScripts[id]
		local status, a, b, c = ...
		self.updateCheckRunning = false
		if sub.mode == "check" then
			if status == "available" then
				self.updateAvailable = { release = a, files = tonumber(b) or 0, bytes = tonumber(c) or 0 }
			elseif status == "none" then
				self.updateAvailable = not sub.background and "none" or nil
			else
				ConPrintf("Update check failed: %s", tostring(a))
				-- An offline start should not raise an error; a check the user asked for reports it.
				if not sub.background then self.updateErrMsg = tostring(a) end
			end
		elseif status == "ready" then
			self:ApplyUpdate(a == "native")
		else
			self.updateErrMsg = tostring(a)
		end
	elseif self.subScripts[id].type == "DOWNLOAD" then
		local errMsg = PCall(self.subScripts[id].callback, ...)
		if errMsg then
			self:ShowErrMsg("In download callback: %s", errMsg)
		end
	elseif self.subScripts[id].type == "CUSTOM" then
		if self.subScripts[id].callback then
			local errMsg = PCall(self.subScripts[id].callback, ...)
			if errMsg then
				self:ShowErrMsg("In subscript callback: %s", errMsg)
			end
		end
	end
	self.subScripts[id] = nil
end

function launch:RegisterSubScript(id, callback)
	if id then
		self.subScripts[id] = {
			type = "CUSTOM",
			callback = callback,
		}
	end
end

---Download the given page in the background, and calls the provided callback function when done:
---@param url string
---@param callback fun(response:table, errMsg:string) @ response = { header, body }
---@param params? table @ params = { header, body }
function launch:DownloadPage(url, callback, params)
	if callback then callback(nil, "External downloads are not available in evryBuild. Use a local build code or the local database exporter.") end
end

-- Starts UpdateCheck in the background: "check" compares with the latest release, "download" stages its files.
function launch:RunUpdateScript(mode, background)
	if self.updateCheckRunning or not self.updateSource or self.devMode then
		return
	end
	local file = io.open((GetScriptPath() or ".") .. "/UpdateCheck.lua", "r")
	if not file then
		self.updateErrMsg = "UpdateCheck.lua is missing."
		return
	end
	local script = file:read("*a")
	file:close()
	self.updateProgress = mode == "check" and "Checking..." or "Downloading..."
	local id = LaunchSubScript(script, "GetScriptPath,GetRuntimePath,GetWorkDir,MakeDir", "ConPrintf,UpdateProgress",
		mode, self.connectionProtocol)
	if id then
		self.subScripts[id] = { type = "UPDATE", mode = mode, background = background }
		self.updateCheckRunning = true
	end
end

function launch:CheckForUpdate(inBackground)
	if not self.updateSource or self.devMode then
		return
	end
	self.lastUpdateCheck = GetTime()
	self:RunUpdateScript("check", inBackground)
end

-- Downloads the release found by the last check; ApplyUpdate follows when every file arrived intact.
function launch:DownloadUpdate()
	if type(self.updateAvailable) == "table" then
		self:RunUpdateScript("download", false)
	end
end

-- Installs the staged files. Lua and data changes need only a restart of the scripts; a new exe or DLL needs a
-- new process, so this one starts evryBuild again and exits.
function launch:ApplyUpdate(native)
	local errMsg, ok, applyErr = PLoadModule("UpdateApply", "Update/opFile.txt")
	if errMsg or not ok then
		self.updateErrMsg = "The update was not installed: " .. tostring(errMsg or applyErr)
		return
	end
	self.updateAvailable = nil
	if native then
		local runtime = GetRuntimePath() or "."
		SpawnProcess(runtime .. "/evryBuild.exe", '"' .. (GetScriptPath() or runtime) .. '/Launch.lua"')
		Exit()
	else
		Restart()
		self.doRestart = "Updating..."
	end
end

function launch:ShowPrompt(r, g, b, str, func)
	self.promptMsg = str
	self.promptCol = {r, g, b}
	self.promptFunc = func or function(key)
		if key == "RETURN" or key == "ESCAPE" then
			return true
		elseif key == "F4" then
			if self.main then
				self.main.popups = { }
				self.main.inputEvents = { }
				self.main:SetMode("LIST")
			end
			return true
		elseif key == "c" and IsKeyDown("CTRL") then
			local cleanStr = str:gsub("%^%d", "")
			Copy(cleanStr)
		elseif key == "F5" then
			self.doRestart = "Restarting..."
			return true
		end
	end
end

function launch:ShowErrMsg(fmt, ...)
	if not self.promptMsg then
		local version = self.versionNumber and 
			"^8v"..self.versionNumber..(self.versionBranch and " "..self.versionBranch or "")
			or ""
		self:ShowPrompt(1, 0, 0, "^1Error:\n\n^0"..string.format(fmt, ...).."\n"..version.."\n^0Press Enter/Escape to dismiss, F4 to return to build selection, or F5 to restart the application.\nPress CTRL + C to copy error text.")
	end
end

function launch:RunPromptFunc(key)
	local curMsg = self.promptMsg
	local errMsg, ret = PCall(self.promptFunc, key)
	if errMsg then
		self:ShowErrMsg("In prompt func: %s", errMsg)
	elseif ret and self.promptMsg == curMsg then
		self.promptMsg = nil
	end
end

function launch:DrawPopup(r, g, b, fmt, ...)
	local screenW, screenH = GetVirtualScreenSize()
	SetDrawColor(0, 0, 0, 0.5)
	DrawImage(nil, 0, 0, screenW, screenH)
	local txt = string.format(fmt, ...)
	local w = DrawStringWidth(20, "VAR", txt) + 20
	local h = (#txt:gsub("[^\n]","") + 2) * 20
	local ox = (screenW - w) / 2
	local oy = (screenH - h) / 2
	SetDrawColor(1, 1, 1)
	DrawImage(nil, ox, oy, w, h)
	SetDrawColor(r, g, b)
	DrawImage(nil, ox + 2, oy + 2, w - 4, h - 4)
	SetDrawColor(1, 1, 1)
	DrawImage(nil, ox + 4, oy + 4, w - 8, h - 8)
	DrawString(0, oy + 10, "CENTER", 20, "VAR", txt)
end
