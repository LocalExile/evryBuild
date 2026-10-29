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
	-- evryBuild is updated from its fork rather than the upstream PoB updater.
	self.evryBuildEdition = true
	self.installedMode = false
	self.versionNumber = "?"
	self.versionBranch = "?"
	self.versionPlatform = "?"
	self.lastUpdateCheck = GetTime()
	self.subScripts = { }
	self.startTime = startTime
	local firstRunFile = io.open("first.run", "r")
	if firstRunFile then
		firstRunFile:close()
		os.remove("first.run")
		-- This is a fresh installation
		-- Perform an immediate update to download the latest version
		ConClear()
		ConPrintf("Please wait while we complete installation...\n")
		local updateMode, errMsg = LoadModule("UpdateCheck")
		if not updateMode then
			self.updateErrMsg = errMsg
		elseif updateMode ~= "none" then
			self:ApplyUpdate(updateMode)
			return
		end
	end
	local xml = require("xml")
	local localManXML = xml.LoadXMLFile("manifest.xml") or xml.LoadXMLFile("../manifest.xml")
	if localManXML and localManXML[1].elem == "PoBVersion" then
		for _, node in ipairs(localManXML[1]) do
			if type(node) == "table" then
				if node.elem == "Version" then
					self.versionNumber = node.attrib.number
					self.versionBranch = node.attrib.branch
					self.versionPlatform = node.attrib.platform
				end
			end
		end
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

	if not self.devMode and not firstRunFile then
		-- Run a background update check if developer mode is off
		self:CheckForUpdate(true)
	end
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
	if not self.devMode and (GetTime() - self.lastUpdateCheck) > 1000*60*60*12 then
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
		self:ShowErrMsg("In update thread: %s", errMsg)
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
		self.updateAvailable, self.updateErrMsg = ...
		self.updateCheckRunning = false
		if self.updateCheckBackground and self.updateAvailable == "none" then
			self.updateAvailable = nil
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
	if callback then callback(nil, "External downloads are not available in evryBuild. Use a local build code or LocalExile.") end
end

function launch:ApplyUpdate() end

function launch:CheckForUpdate()
	self.lastUpdateCheck = GetTime()
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
