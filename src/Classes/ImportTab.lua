-- Path of Building
--
-- Module: Import Tab
-- Import/Export tab for the current build.
--
local ipairs = ipairs
local t_insert = table.insert
local t_remove = table.remove
local b_rshift = bit.rshift
local band = bit.band
local m_max = math.max
local dkjson = require "dkjson"



local influenceInfo = itemLib.influenceInfo.all

local ImportTabClass = newClass("ImportTab", "ControlHost", "Control", function(self, build)
	self.ControlHost()
	self.Control()

	self.build = build

	-- Build import/export
	self.controls.sectionBuild = new("SectionControl",
		{ "TOPLEFT", self, "TOPLEFT" },
		{ 10, 18, 650, 182 }, "Local Build Import / Export")
	self.controls.generateCodeLabel = new("LabelControl", { "TOPLEFT", self.controls.sectionBuild, "TOPLEFT" },
		{ 6, 14, 0, 16 }, "^7Generate a code to copy or save this build locally:")
	self.controls.generateCode = new("ButtonControl", {"LEFT",self.controls.generateCodeLabel,"RIGHT"}, {4, 0, 80, 20}, "Generate", function()
		self.controls.generateCodeOut:SetText(common.base64.encode(Deflate(self.build:SaveDB("code"))):gsub("+","-"):gsub("/","_"))
	end)
	self.controls.enablePartyExportBuffs = new("CheckBoxControl", {"LEFT",self.controls.generateCode,"RIGHT"}, {100, 0, 18}, "Export Support", function(state)
		self.build.partyTab.enableExportBuffs = state
		self.build.buildFlag = true
	end, "This is for party play, to export support character, it enables the exporting of auras, curses and modifiers to the enemy", false)
	self.controls.generateCodeOut = new("EditControl", {"TOPLEFT",self.controls.generateCodeLabel,"BOTTOMLEFT"}, {0, 8, 250, 20}, "", "Code", "%Z")
	self.controls.generateCodeOut.enabled = function()
		return #self.controls.generateCodeOut.buf > 0
	end
	self.controls.generateCodeCopy = new("ButtonControl", {"LEFT",self.controls.generateCodeOut,"RIGHT"}, {8, 0, 60, 20}, "Copy", function()
		Copy(self.controls.generateCodeOut.buf)
		self.controls.generateCodeOut:SetText("")
	end)
	self.controls.generateCodeCopy.enabled = function()
		return #self.controls.generateCodeOut.buf > 0
	end

	self.controls.generateCodeNote = new("LabelControl", {"TOPLEFT",self.controls.generateCodeOut,"BOTTOMLEFT"}, {0, 4, 0, 14}, "^7Build codes work offline. Web uploads and link downloads are not available.")
	self.controls.importCodeHeader = new("LabelControl", {"TOPLEFT",self.controls.generateCodeNote,"BOTTOMLEFT"}, {0, 26, 0, 16}, "^7Paste a build code here (web links are not downloaded):")

	local importCodeHandle = function (buf)
		self.importCodeSite = nil
		self.importCodeDetail = ""
		self.importCodeXML = nil
		self.importCodeValid = false
		self.importCodeJson = nil

		if #buf == 0 then
			return
		end

		if not self.build.dbFileName then
			self.controls.importCodeMode.selIndex = 2
		end

		self.importCodeDetail = colorCodes.NEGATIVE.."Invalid input"
		local urlText = buf:gsub("^[%s?]+", ""):gsub("[%s?]+$", "") -- Quick Trim
		if urlText:match("^%a[%w+.-]*://") then
			self.importCodeDetail = colorCodes.NEGATIVE.."Paste the build code itself; external links are not downloaded."
			return
		end

		-- If we are in dev mode and the string is a json
		if launch.devMode and urlText:match("^%{.*%}$") ~= nil then
			local jsonData, _, errDecode = dkjson.decode(urlText)
			if errDecode then
				self.importCodeDetail = colorCodes.NEGATIVE.."Invalid JSON format (decode error)"
				return
			end
			if not jsonData.character then
				self.importCodeDetail = colorCodes.NEGATIVE.."Invalid JSON format (character missing)"
				return
			end
			jsonData = jsonData.character
			if not jsonData.equipment or not jsonData.passives then
				self.importCodeDetail = colorCodes.NEGATIVE.."Invalid JSON format (equipment or passives missing)"
				return
			end
			self.importCodeJson = jsonData
			self.importCodeDetail = colorCodes.POSITIVE.."JSON is valid"
			self.importCodeValid = true
			return
		end

		local ok, xmlText = pcall(function() return Inflate(common.base64.decode(urlText:gsub("-","+"):gsub("_","/"))) end)
		if not ok or not xmlText then
			return
		end
		if launch.devMode and IsKeyDown("SHIFT") then
			Copy(xmlText)
		end
		self.importCodeValid = true
		self.importCodeDetail = colorCodes.POSITIVE.."Code is valid"
		self.importCodeXML = xmlText
	end

	local importSelectedBuild = function()
		if not self.importCodeValid or self.importCodeFetching then
			return
		end

		if self.controls.importCodeMode.selIndex == 1 then
			main:OpenConfirmPopup("Build Import", colorCodes.WARNING.."Warning:^7 Importing to the current build will erase ALL existing data for this build.", "Import", function()
				self.build:Shutdown()
				self.build:Init(self.build.dbFileName, self.build.buildName, self.importCodeXML, false, self.importCodeSite and self.controls.importCodeIn.buf or nil)
				self.build.viewMode = "TREE"
			end)
		elseif self.controls.importCodeMode.selIndex == 3 then
			-- Import as comparison build
			if self.build.compareTab then
				if self.build.compareTab:ImportBuild(self.importCodeXML, "Imported comparison") then
					self.build.viewMode = "COMPARE"
				else
					main:OpenMessagePopup("Import Error", "Failed to import build for comparison.")
				end
			end
		else
			self.build:Shutdown()
			self.build:Init(false, "Imported build", self.importCodeXML, false, self.importCodeSite and self.controls.importCodeIn.buf or nil)
			self.build.viewMode = "TREE"
		end
	end

	self.controls.importCodeIn = new("EditControl", {"TOPLEFT",self.controls.importCodeHeader,"BOTTOMLEFT"}, {0, 4, 328, 20}, "", nil, nil, nil, importCodeHandle, nil, nil, true)
	self.controls.importCodeIn.enterFunc = function()
		if self.importCodeValid then
			self.controls.importCodeGo.onClick()
		end
	end
	self.controls.importCodeState = new("LabelControl", {"LEFT",self.controls.importCodeIn,"RIGHT"}, {8, 0, 0, 16})
	self.controls.importCodeState.label = function()
		return self.importCodeDetail or ""
	end
	self.controls.importCodeMode = new("DropDownControl", {"TOPLEFT",self.controls.importCodeIn,"BOTTOMLEFT"}, {0, 4, 200, 20}, { "Import to this build", "Import to a new build", "Import as comparison" })
	self.controls.importCodeMode.enabled = function()
		return (self.build.dbFileName or self.controls.importCodeMode.selIndex == 3) and self.importCodeValid
	end
	self.controls.importCodeGo = new("ButtonControl", {"LEFT",self.controls.importCodeMode,"RIGHT"}, {8, 0, 160, 20}, "Import", function()
		if self.importCodeJson then
			self:ImportItemsAndSkills(self.importCodeJson, true, true, false)
			self:ImportPassiveTreeAndJewels(self.importCodeJson, true)
			return
		end

		importSelectedBuild()
	end)
	self.controls.importCodeGo.label = function ()
		return self.importCodeFetching and "Retrieving paste.." or "Import"
	end
	self.controls.importCodeGo.enabled = function()
		return self.importCodeValid and not self.importCodeFetching
	end
	self.controls.importCodeGo.enterFunc = function()
		if self.importCodeValid then
			self.controls.importCodeGo.onClick()
		end
	end

	-- evryBuild previews and character creation use the current build's normal export path.
	LoadModule("Modules/LocalExile", self)


end)

-- Retained for builds created with older versions; no account list is fetched.
function ImportTabClass:TryFetchCharacterList() end

function ImportTabClass:Load(xml, fileName)
	self.lastRealm = xml.attrib.lastRealm
	self.lastLeague = xml.attrib.lastLeague
	self.lastAccountHash = xml.attrib.lastAccountHash
	self.importLink = xml.attrib.importLink
	self.controls.enablePartyExportBuffs.state = xml.attrib.exportParty == "true"
	self.build.partyTab.enableExportBuffs = self.controls.enablePartyExportBuffs.state
	self.lastCharacterHash = xml.attrib.lastCharacterHash
end

function ImportTabClass:Save(xml)
	xml.attrib = {
		lastRealm = self.lastRealm,
		lastLeague = self.lastLeague,
		lastAccountHash = self.lastAccountHash,
		lastCharacterHash = self.lastCharacterHash,
		exportParty = tostring(self.controls.enablePartyExportBuffs.state),
		importLink = self.importLink
	}

	if self.build.importLink then
		xml.attrib.importLink = self.build.importLink
	end
	-- Gets rid of erroneous, potentially infinitely nested full base64 XML stored as an import link
	xml.attrib.importLink = (xml.attrib.importLink and xml.attrib.importLink:len() < 100) and xml.attrib.importLink or nil
end

function ImportTabClass:Draw(viewPort, inputEvents)
	self.x = viewPort.x
	self.y = viewPort.y
	self.width = viewPort.width
	self.height = viewPort.height

	self:ProcessControlsInput(inputEvents, viewPort)

	main:DrawBackground(viewPort)

	self:DrawControls(viewPort)
end

function ImportTabClass:ImportPassiveTreeAndJewels(charData, deleteJewels)
	local charPassives = copyTable(charData.passives)

	-- fix table keys being strings
	local masteries = {}
	for key, value in pairs(charPassives.mastery_effects or {}) do
		masteries[tonumber(key)] = value
	end
	self.build.spec.jewel_data = {}
	for key, value in pairs(charPassives.jewel_data or {}) do
		self.build.spec.jewel_data[tonumber(key)] = value
	end
	local skillOverrides = {}
	for nodeId, override in pairs(charPassives.skill_overrides or {}) do
		-- json keys are strings, not numbers
		local nodeIdNum = tonumber(nodeId)
		self.build.spec:ReplaceNode(override, self.build.spec.tree.tattoo.nodes[override.name])
		override.id = nodeIdNum
		skillOverrides[nodeIdNum] = override
	end

	self.build.spec.extended_hashes = copyTable(charPassives.hashes_ex)
	if deleteJewels then
		for _, slot in pairs(self.build.itemsTab.slots) do
			if slot.selItemId ~= 0 and slot.nodeId then
				self.build.itemsTab.build.spec.ignoreAllocatingSubgraph = true -- ignore allocated cluster nodes on Import when Delete Jewel is true, clean slate
				self.build.itemsTab:DeleteItem(self.build.itemsTab.items[slot.selItemId])
			end
		end
	end
	for _, itemData in ipairs(charData.jewels or {}) do
		self:ImportItem(itemData)
	end
	self.build.itemsTab:PopulateSlots()
	self.build.itemsTab:AddUndoState()

	-- Alternate trees don't have an identifier, so we're forced to look up something that is unique to that tree
	-- Hopefully this changes, because it's totally unmaintainable
	local function isAscendancyInTree(className, treeVersion)
		local classes = main.tree[treeVersion].classes
		for _, class in pairs(classes) do
			if class.name == className then
				return true
			end
			for i = 0, #class.classes do
				local ascendClass = class.classes[i]
				if ascendClass.name == className then
					return true
				end
			end
		end
	end

	local alternateAscendancyId
	if charPassives.alternate_ascendancy then
		-- oauth responses have bloodline names
		if type(charPassives.alternate_ascendancy) == "string" then
			local bloodline = self.build.latestTree.secondaryAscendNameMap[charPassives.alternate_ascendancy]
			alternateAscendancyId = bloodline and bloodline.ascendClassId
		-- site responses have integer ids
		else
			alternateAscendancyId = charPassives.alternate_ascendancy
		end
	else
		alternateAscendancyId = 0
	end
	-- Character import uses current GGG cluster hashes.
	self.build.spec.clusterHashFormatVersion = 2
	local ruthlessSuffix = charData.league:match("Ruthless") and "_ruthless" or ""
	local phreciaSuffix = isAscendancyInTree(charData.class, latestTreeVersion) and "" or "_alternate"
	self.build.spec:ImportFromNodeList(charData.class,
		nil,
		nil,
		alternateAscendancyId,
		charPassives.hashes,
		skillOverrides,
		masteries,
		latestTreeVersion .. ruthlessSuffix .. phreciaSuffix
		)
	self.build.treeTab:SetActiveSpec(self.build.treeTab.activeSpec)
	self.build.spec:BuildClusterJewelGraphs()
	self.build.spec:AddUndoState()
	self.build.characterLevel = charData.level or 100
	self.build.characterLevelAutoMode = false
	self.build.configTab:UpdateLevel()
	self.build.controls.characterLevel:SetText(charData.level)
	self.build:EstimatePlayerProgress()
	local resistancePenaltyIndex = 3
	if self.build.Act then -- Estimate resistance penalty setting based on act progression estimate
		if type(self.build.Act) == "string" and self.build.Act == "Endgame" then resistancePenaltyIndex = 3
		elseif type(self.build.Act) == "number" then
			if self.build.Act < 5 then resistancePenaltyIndex = 1
			elseif self.build.Act > 5 and self.build.Act < 11 then resistancePenaltyIndex = 2
			elseif self.build.Act > 10 then resistancePenaltyIndex = 3 end
		end
	end
	self.build.configTab.varControls["resistancePenalty"]:SetSel(resistancePenaltyIndex)

	local function setSelByVal(dropdown, val)
		for i, v in ipairs(dropdown.list) do
			if v.val == val then
				dropdown:SetSel(i)
			end
		end
	end

	local bandit = (charPassives.bandit_choice == "Eramir" or not charPassives.bandit_choice) and "None" or
		charPassives.bandit_choice
	setSelByVal(self.build.configTab.varControls["bandit"],
		bandit)

	local majorGod = charPassives.pantheon_major or "None"
	setSelByVal(self.build.configTab.varControls["pantheonMajorGod"],
		majorGod)

	local minorGod = charPassives.pantheon_minor or "None"
	setSelByVal(self.build.configTab.varControls["pantheonMinorGod"],
		minorGod)

	main:SetWindowTitleSubtext(string.format("%s (%s, %s, %s)", self.build.buildName, charData.name, charData.class,
		charData.league))
	return colorCodes.POSITIVE.."Passive tree and jewels successfully imported."
end

local SOCKET_GROUP_REIMPORT_KEY_SEPARATOR = "\31"

local function getSocketGroupReimportKey(socketGroup)
	-- Use a rarely-used separator to avoid accidental collisions when concatenating fields.
	local gemNameParts = { }
	for _, gem in ipairs(socketGroup.gemList) do
		t_insert(gemNameParts, (gem.nameSpec or ""):lower())
	end
	return table.concat({
		socketGroup.slot or "",
		socketGroup.source or "",
		tostring(#socketGroup.gemList),
		table.concat(gemNameParts, SOCKET_GROUP_REIMPORT_KEY_SEPARATOR),
	}, SOCKET_GROUP_REIMPORT_KEY_SEPARATOR)
end

local function snapshotSocketGroupReimportState(socketGroup, isMainGroup)
	local gemStates = { }
	for gemIndex, gem in ipairs(socketGroup.gemList) do
		gemStates[gemIndex] = {
			enabled = gem.enabled,
			count = gem.count,
			skillPart = gem.skillPart,
			skillPartCalcs = gem.skillPartCalcs,
			skillStageCount = gem.skillStageCount,
			skillStageCountCalcs = gem.skillStageCountCalcs,
			skillMineCount = gem.skillMineCount,
			skillMineCountCalcs = gem.skillMineCountCalcs,
			skillMinion = gem.skillMinion,
			skillMinionCalcs = gem.skillMinionCalcs,
			skillMinionItemSet = gem.skillMinionItemSet,
			skillMinionItemSetCalcs = gem.skillMinionItemSetCalcs,
			skillMinionSkill = gem.skillMinionSkill,
			skillMinionSkillCalcs = gem.skillMinionSkillCalcs,
			enableGlobal1 = gem.enableGlobal1,
			enableGlobal2 = gem.enableGlobal2,
		}
	end
	return {
		enabled = socketGroup.enabled,
		includeInFullDPS = socketGroup.includeInFullDPS,
		groupCount = socketGroup.groupCount,
		label = socketGroup.label,
		mainActiveSkill = socketGroup.mainActiveSkill,
		mainActiveSkillCalcs = socketGroup.mainActiveSkillCalcs,
		gemStates = gemStates,
		isMainGroup = isMainGroup,
	}
end

local function applyGemReimportState(gem, state)
	gem.enabled = state.enabled
	gem.count = state.count
	gem.skillPart = state.skillPart
	gem.skillPartCalcs = state.skillPartCalcs
	gem.skillStageCount = state.skillStageCount
	gem.skillStageCountCalcs = state.skillStageCountCalcs
	gem.skillMineCount = state.skillMineCount
	gem.skillMineCountCalcs = state.skillMineCountCalcs
	gem.skillMinion = state.skillMinion
	gem.skillMinionCalcs = state.skillMinionCalcs
	gem.skillMinionItemSet = state.skillMinionItemSet
	gem.skillMinionItemSetCalcs = state.skillMinionItemSetCalcs
	gem.skillMinionSkill = state.skillMinionSkill
	gem.skillMinionSkillCalcs = state.skillMinionSkillCalcs
	gem.enableGlobal1 = state.enableGlobal1
	gem.enableGlobal2 = state.enableGlobal2
end

local function applySocketGroupReimportState(socketGroup, state)
	socketGroup.enabled = state.enabled
	socketGroup.includeInFullDPS = state.includeInFullDPS
	socketGroup.groupCount = state.groupCount
	socketGroup.label = state.label
	socketGroup.mainActiveSkill = state.mainActiveSkill
	socketGroup.mainActiveSkillCalcs = state.mainActiveSkillCalcs
	if state.gemStates then
		for gemIndex, gemState in ipairs(state.gemStates) do
			if socketGroup.gemList[gemIndex] then
				applyGemReimportState(socketGroup.gemList[gemIndex], gemState)
			end
		end
	end
end

local GUARD_ITEM_SET = "Animate Guardian"
-- Locates AG's item set from the import
function ImportTabClass:GetOrCreateGuardianItemSet()
	local itemsTab = self.build.itemsTab
	for _, itemSetId in ipairs(itemsTab.itemSetOrderList) do
		local itemSet = itemsTab.itemSets[itemSetId]
		if itemSet.title == GUARD_ITEM_SET then
			return itemSet
		end
	end
	local itemSet = itemsTab:NewItemSet()
	itemSet.title = GUARD_ITEM_SET
	t_insert(itemsTab.itemSetOrderList, itemSet.id)
	return itemSet
end

-- Allocates AG's item set for the AG skill gem.
function ImportTabClass:AssignGuardianItemSet(itemSetId)
	local itemsTab = self.build.itemsTab
	for _, socketGroup in ipairs(self.build.skillsTab.socketGroupList) do
		for _, gem in ipairs(socketGroup.gemList) do
			if gem.grantedEffect and gem.grantedEffect.name == "Animate Guardian" then
				for _, suffix in ipairs({ "", "Calcs" }) do
					local current = gem["skillMinionItemSet"..suffix]
					local currentSet = current and itemsTab.itemSets[current]
					if not current or (currentSet and currentSet.title == GUARD_ITEM_SET) then
						gem["skillMinionItemSet"..suffix] = itemSetId
					end
				end
			end
		end
	end
end

--- @class CharacterItemsData : CharacterBasicData
--- @field equipment Item[]
--- @param charData CharacterItemsData
--- @param clearItems boolean
--- @param clearSkills boolean
--- @param ignoreWeaponSwap boolean
--- @return CharacterItemsData, string
function ImportTabClass:ImportItemsAndSkills(charData, clearItems, clearSkills, ignoreWeaponSwap)
	charData = copyTable(charData)
	if clearItems then
		for _, slot in pairs(self.build.itemsTab.slots) do
			if slot.selItemId ~= 0 and not slot.nodeId then
				self.build.itemsTab:DeleteItem(self.build.itemsTab.items[slot.selItemId])
			end
		end
	end

	local mainSkillEmpty = #self.build.skillsTab.socketGroupList == 0
	local skillOrder
	local preservedSocketGroupStateByKey
	if clearSkills then
		skillOrder = { }
		preservedSocketGroupStateByKey = { }
		for _, socketGroup in ipairs(self.build.skillsTab.socketGroupList) do
			for _, gem in ipairs(socketGroup.gemList) do
				if gem.grantedEffect and not gem.grantedEffect.support then
					t_insert(skillOrder, gem.grantedEffect.name)
				end
			end
		end
		for index, socketGroup in ipairs(self.build.skillsTab.socketGroupList) do
			local key = getSocketGroupReimportKey(socketGroup)
			preservedSocketGroupStateByKey[key] = preservedSocketGroupStateByKey[key] or { }
			t_insert(preservedSocketGroupStateByKey[key], snapshotSocketGroupReimportState(socketGroup, index == self.build.mainSocketGroup))
		end
		wipeTable(self.build.skillsTab.socketGroupList)
		self.build.skillsTab.controls.groupList.selIndex = nil
		self.build.skillsTab.controls.groupList.selValue = nil
		self.build.skillsTab:SetDisplayGroup()
		self.build.skillsTab:RebuildImbuedSupportBySlot()
	end
	for _, itemData in ipairs(charData.equipment) do
		self:ImportItem(itemData, nil, ignoreWeaponSwap)
	end
	if charData.guardian and charData.guardian[1] then
		local guardianSet = self:GetOrCreateGuardianItemSet()
		for _, itemData in ipairs(charData.guardian) do
			self:ImportItem(itemData, nil, ignoreWeaponSwap, guardianSet.id)
		end
		self:AssignGuardianItemSet(guardianSet.id)
	end
	if skillOrder then
		local groupOrder = { }
		for index, socketGroup in ipairs(self.build.skillsTab.socketGroupList) do
			groupOrder[socketGroup] = index
		end
		table.sort(self.build.skillsTab.socketGroupList, function(a, b)
			local orderA
			for _, gem in ipairs(a.gemList) do
				if gem.grantedEffect and not gem.grantedEffect.support then
					local i = isValueInArray(skillOrder, gem.grantedEffect.name)
					if i and (not orderA or i < orderA) then
						orderA = i
					end
				end
			end
			local orderB
			for _, gem in ipairs(b.gemList) do
				if gem.grantedEffect and not gem.grantedEffect.support then
					local i = isValueInArray(skillOrder, gem.grantedEffect.name)
					if i and (not orderB or i < orderB) then
						orderB = i
					end
				end
			end
			if orderA and orderB then
				if orderA ~= orderB then
					return orderA < orderB
				else
					return groupOrder[a] < groupOrder[b]
				end
			elseif not orderA and not orderB then
				return groupOrder[a] < groupOrder[b]
			else
				return orderA
			end
		end)
	end
	if preservedSocketGroupStateByKey then
		local restoredMainSocketGroup
		for index, socketGroup in ipairs(self.build.skillsTab.socketGroupList) do
			local stateList = preservedSocketGroupStateByKey[getSocketGroupReimportKey(socketGroup)]
			if stateList and stateList[1] then
				local state = t_remove(stateList, 1)
				applySocketGroupReimportState(socketGroup, state)
				if state.isMainGroup then
					restoredMainSocketGroup = index
				end
			end
		end
		if restoredMainSocketGroup then
			self.build.mainSocketGroup = restoredMainSocketGroup
		end
	end
	if mainSkillEmpty then
		self.build.mainSocketGroup = self:GuessMainSocketGroup()
	end
	self.build.itemsTab:PopulateSlots()
	self.build.itemsTab:AddUndoState()
	self.build.skillsTab:UpdateSocketGroups()
	self.build.skillsTab:AddUndoState()
	self.build.characterLevel = charData.level
	self.build.configTab:UpdateLevel()
	self.build.controls.characterLevel:SetText(tostring(charData.level))
	self.build.buildFlag = true
	-- charData for the wrapper
	return charData, colorCodes.POSITIVE .. "Items and skills successfully imported."
end

local rarityMap = { [0] = "NORMAL", "MAGIC", "RARE", "UNIQUE", [9] = "RELIC", [10] = "RELIC" }
local slotMap = { ["Weapon"] = "Weapon 1", ["Offhand"] = "Weapon 2", ["Weapon2"] = "Weapon 1 Swap", ["Offhand2"] = "Weapon 2 Swap", ["Helm"] = "Helmet", ["BodyArmour"] = "Body Armour", ["Gloves"] = "Gloves", ["Boots"] = "Boots",
				  ["Amulet"] = "Amulet", ["Ring"] = "Ring 1", ["Ring2"] = "Ring 2", ["Ring3"] = "Ring 3", ["Belt"] = "Belt",  ["BrequelGrafts"] = "Graft 1", ["BrequelGrafts2"] = "Graft 2", }

function ImportTabClass:ImportItem(itemData, slotName, ignoreWeaponSwap, itemSetId)
	if not slotName then
		if itemData.inventoryId == "PassiveJewels" then
			slotName = "Jewel "..self.build.latestTree.jewelSlots[itemData.x + 1]
		elseif itemData.inventoryId == "Flask" then
			slotName = "Flask "..(itemData.x + 1)
		elseif not (ignoreWeaponSwap and (itemData.inventoryId == "Weapon2" or itemData.inventoryId == "Offhand2")) then
			slotName = slotMap[itemData.inventoryId]
		end
	end
	if not slotName then
		-- Ignore any items that won't go into known slots
		return
	end

	local item = new("Item")

	-- Determine rarity, display name and base type of the item
	item.rarity = rarityMap[itemData.frameType]
	if #itemData.name > 0 then
		item.title = sanitiseText(itemData.name)
		item.baseName = sanitiseText(itemData.typeLine):gsub("Synthesised ", ""):gsub("^Vestigial ", "")
		item.name = item.title .. ", " .. item.baseName
		if item.baseName == "Two-Toned Boots" then
			-- Hack for Two-Toned Boots
			item.baseName = "Two-Toned Boots (Armour/Energy Shield)"
		end
		item.base = self.build.data.itemBases[item.baseName]
		if item.base then
			item.type = item.base.type
		else
			ConPrintf("Unrecognised base in imported item: %s", item.baseName)
		end
	else
		item.name = sanitiseText(itemData.typeLine)
		if item.name:match("Energy Blade") then
			local oneHanded = false
			for _, p in ipairs(itemData.properties) do
				if self.build.data.weaponTypeInfo[p.name] and self.build.data.weaponTypeInfo[p.name].oneHand then
					oneHanded = true
					break
				end
			end
			item.name = oneHanded and "Energy Blade One Handed" or "Energy Blade Two Handed"
			item.rarity = "NORMAL"
			itemData.implicitMods = { }
			itemData.explicitMods = { }
		end
		for baseName, baseData in pairs(self.build.data.itemBases) do
			local s, e = item.name:find(baseName, 1, true)
			if s then
				item.baseName = baseName
				item.namePrefix = item.name:sub(1, s - 1)
				item.nameSuffix = item.name:sub(e + 1)
				item.type = baseData.type
				break
			end
		end
		if not item.baseName then
			local s, e = item.name:find("Two-Toned Boots", 1, true)
			if s then
				-- Hack for Two-Toned Boots
				item.baseName = "Two-Toned Boots (Armour/Energy Shield)"
				item.namePrefix = item.name:sub(1, s - 1)
				item.nameSuffix = item.name:sub(e + 1)
				item.type = "Boots"
			end
		end
		item.base = self.build.data.itemBases[item.baseName]
	end
	if not item.base or not item.rarity then
		return
	end

	-- Import item data
	item.uniqueID = itemData.id
	if itemData.influences then
		for _, curInfluenceInfo in ipairs(influenceInfo) do
			item[curInfluenceInfo.key] = itemData.influences[curInfluenceInfo.display:lower()]
		end
	end
	if itemData.searing then
		item.cleansing = true
	end
	if itemData.tangled then
		item.tangle = true
	end
	if itemData.ilvl > 0 then
		item.itemLevel = itemData.ilvl
	end
	if item.base.weapon or item.base.armour or item.base.flask or item.base.tincture then
		item.quality = 0
	end
	if itemData.properties then
		for _, property in pairs(itemData.properties) do
			if property.name == "Quality" then
				item.quality = tonumber(property.values[1][1]:match("%d+"))
			elseif property.name:match("Quality %(") then
				local catalystMap = {
					["Attack"] = 1,
					["Speed"] = 2,
					["Suffix"] = 3,
					["Life and Mana"] = 4,
					["Caster"] = 5,
					["Attribute"] = 6,
					["Physical and Chaos Damage"] = 7,
					["Resistance"] = 8,
					["Prefix"] = 9,
					["Defense"] = 10,
					["Elemental Damage"] = 11,
					["Critical"] = 12,
				}
				item.catalyst = catalystMap[property.name:match("Quality %((.*) Modifiers%)")]
				item.catalystQuality = tonumber(property.values[1][1]:match("%d+"))
			elseif property.name == "Radius" then
				item.jewelRadiusLabel = property.values[1][1]
			elseif property.name == "Limited to" then
				item.limit = tonumber(property.values[1][1])
			elseif property.name == "Evasion Rating" then
				if item.baseName == "Two-Toned Boots (Armour/Energy Shield)" then
					-- Another hack for Two-Toned Boots
					item.baseName = "Two-Toned Boots (Armour/Evasion)"
					item.base = self.build.data.itemBases[item.baseName]
				end
			elseif property.name == "Energy Shield" then
				if item.baseName == "Two-Toned Boots (Armour/Evasion)" then
					-- Yet another hack for Two-Toned Boots
					item.baseName = "Two-Toned Boots (Evasion/Energy Shield)"
					item.base = self.build.data.itemBases[item.baseName]
				end
			elseif property.name:find("Intangibility") then
				item.intangibility = tonumber(property.values[1][1]:match("%d+"))
			elseif property.name == "Memory Strands" then
				item.memoryStrands = tonumber(property.values[1][1])
			end
			if property.name == "Energy Shield" or property.name == "Ward" or property.name == "Armour" or property.name == "Evasion Rating" then
				item.armourData = item.armourData or { }
				for _, value in ipairs(property.values) do
					item.armourData[property.name:gsub(" Rating", ""):gsub(" ", "")] = (item.armourData[property.name:gsub(" Rating", ""):gsub(" ", "")] or 0) + tonumber(value[1])
				end
			end
		end
	end
	item.split = itemData.split
	item.mirrored = itemData.mirrored
	item.corrupted = itemData.corrupted
	item.fractured = itemData.fractured
	item.synthesised = itemData.synthesised
	item.vestigial = itemData.vestigial
	if itemData.sockets and itemData.sockets[1] then
		item.sockets = { }
		for i, socket in pairs(itemData.sockets) do
			if socket.sColour == "A" then
				item.abyssalSocketCount = item.abyssalSocketCount or 0 + 1
			end
			item.sockets[i] = { group = socket.group, color = socket.sColour }
		end
		if item.abyssalSocketCount and item.abyssalSocketCount > 0 and item.name:match("Energy Blade") then
			t_insert(itemData.explicitMods, "Has " .. item.abyssalSocketCount .. " Abyssal Sockets")
		end
	end
	if itemData.socketedItems then
		self:ImportSocketedItems(item, itemData.socketedItems, slotName)
	end
	if itemData.requirements and (not itemData.socketedItems or not itemData.socketedItems[1]) then
		-- Requirements cannot be trusted if there are socketed gems, as they may override the item's natural requirements
		item.requirements = { }
		for _, req in ipairs(itemData.requirements) do
			if req.name == "Level" then
				item.requirements.level = req.values[1][1]
			elseif req.name == "Class:" then
				item.classRestriction = req.values[1][1]
			end
		end
	end
	item.enchantModLines = { }
	item.scourgeModLines = { }
	item.classRequirementModLines = { }
	item.implicitModLines = { }
	item.explicitModLines = { }
	item.crucibleModLines = { }
	if itemData.enchantMods then
		for _, line in ipairs(itemData.enchantMods) do
			for line in line:gmatch("[^\n]+") do
				local modList, extra = modLib.parseMod(line)
				t_insert(item.enchantModLines, { line = line, extra = extra, mods = modList or { }, crafted = true })
			end
		end
	end
	if itemData.scourgeMods then
		for _, line in ipairs(itemData.scourgeMods) do
			for line in line:gmatch("[^\n]+") do
				local modList, extra = modLib.parseMod(line)
				t_insert(item.scourgeModLines, { line = line, extra = extra, mods = modList or { }, scourge = true })
			end
		end
	end
	if itemData.implicitMods then
		for _, itemMod in ipairs(itemData.implicitMods) do
			local modLine = itemMod.description or itemMod
			local flags = itemMod.flags or itemMod
			for line in modLine:gmatch("[^\n]+") do
				local modList, extra = modLib.parseMod(line)
				t_insert(item.implicitModLines, { line = line, extra = extra, mods = modList or { }, vestigial = flags.vestigial })
			end
		end
	end
	-- TODO: Remove once 3.29 releases https://www.pathofexile.com/developer/docs/changelog#3-29-0
	if itemData.fracturedMods then
		for _, line in ipairs(itemData.fracturedMods) do
			for line in line:gmatch("[^\n]+") do
				local modList, extra = modLib.parseMod(line)
				t_insert(item.explicitModLines, { line = line, extra = extra, mods = modList or { }, fractured = true })
			end
		end
	end
	if itemData.explicitMods then
		for _, itemMod in ipairs(itemData.explicitMods) do
			local modLine = itemMod.description or itemMod
			local flags = itemMod.flags or itemMod
			for line in modLine:gmatch("[^\n]+") do
				local modList, extra = modLib.parseMod(line)
				t_insert(item.explicitModLines, { line = line, extra = extra, mods = modList or { },
					fractured = flags.fractured,
					crafted = flags.crafted,
					mutated = flags.mutated,
					vestigial = flags.vestigial })
			end
		end
	end
	if itemData.crucibleMods then
		for _, line in ipairs(itemData.crucibleMods) do
			for line in line:gmatch("[^\n]+") do
				local modList, extra = modLib.parseMod(line)
				t_insert(item.crucibleModLines, { line = line, extra = extra, mods = modList or { }, crucible = true })
			end
		end
	end
	-- TODO: Remove once 3.29 releases https://www.pathofexile.com/developer/docs/changelog#3-29-0
	if itemData.craftedMods then
		for _, line in ipairs(itemData.craftedMods) do
			for line in line:gmatch("[^\n]+") do
				local modList, extra = modLib.parseMod(line)
				t_insert(item.explicitModLines, { line = line, extra = extra, mods = modList or { }, crafted = true })
			end
		end
	end
	-- TODO: Remove once 3.29 releases https://www.pathofexile.com/developer/docs/changelog#3-29-0
	if itemData.mutatedMods then
		for _, line in ipairs(itemData.mutatedMods) do
			for line in line:gmatch("[^\n]+") do
				local modList, extra = modLib.parseMod(line)
				t_insert(item.explicitModLines, { line = line, extra = extra, mods = modList or { }, mutated = true })
			end
		end
	end
	-- Sometimes flavour text has actual mods that PoB cares about
	-- Right now, the only known one is "This item can be anointed by Cassia"
	if itemData.flavourText then
		for _, line in ipairs(itemData.flavourText) do
			for line in line:gmatch("[^\n]+") do
				-- Remove any text outside of curly braces, if they exist.
				-- This fixes lines such as:
				--   "<default>{This item can be anointed by Cassia}"
				-- To now be:
				--   "This item can be anointed by Cassia"
				local startBracket = line:find("{")
				local endBracket = line:find("}")
				if startBracket and endBracket and endBracket > startBracket then
					line = line:sub(startBracket + 1, endBracket - 1)
				end

				-- If the line parses, then it should be included as an explicit mod
				local modList, extra = modLib.parseMod(line)
				if modList then
					t_insert(item.explicitModLines, { line = line, extra = extra, mods = modList or { } })
				end
			end
		end
	end
	if itemData.foilVariation or itemData.isRelic then
		local foilVariants = {
			"Amethyst",
			"Verdant",
			"Ruby",
			"Cobalt",
			"Sunset",
			"Aureate",
			"Celestial Quartz",
			"Celestial Ruby",
			"Celestial Emerald",
			"Celestial Aureate",
			"Celestial Pearl",
			"Celestial Amethyst",
		}
		item.foilType = foilVariants[itemData.foilVariation] or "Rainbow"
	end

	-- Add and equip the new item
	item:BuildAndParseRaw()
	--ConPrintf("%s", item.raw)
	if item.base then
		local repIndex, repItem
		for index, item in pairs(self.build.itemsTab.items) do
			if item.uniqueID == itemData.id then
				repIndex = index
				repItem = item
				break
			end
		end
		if repIndex then
			-- Item already exists in the build, overwrite it
			item.id = repItem.id
			self.build.itemsTab.items[item.id] = item
			item:BuildModList()
		else
			self.build.itemsTab:AddItem(item, true)
		end
		if itemSetId and itemSetId ~= self.build.itemsTab.activeItemSetId then
			self.build.itemsTab.itemSets[itemSetId][slotName].selItemId = item.id
		else
			self.build.itemsTab.slots[slotName]:SetSelItemId(item.id)
		end
	end
end

function ImportTabClass:ImportSocketedItems(item, socketedItems, slotName)
	-- Build socket group list
	local itemSocketGroupList = { }
	local abyssalSocketId = 1
	for _, socketedItem in ipairs(socketedItems) do
		if socketedItem.abyssJewel then
			self:ImportItem(socketedItem, slotName .. " Abyssal Socket "..abyssalSocketId)
			abyssalSocketId = abyssalSocketId + 1
		else
			local normalizedBasename = sanitiseText(socketedItem.typeLine)
			local gemId = self.build.data.gemForBaseName[normalizedBasename:lower()]
			if socketedItem.hybrid then
				-- Used by transfigured gems and dual-skill gems (currently just Stormbind)
				normalizedBasename = sanitiseText(socketedItem.hybrid.baseTypeName)
				gemId = self.build.data.gemForBaseName[normalizedBasename:lower()]
				if gemId and socketedItem.hybrid.isVaalGem then
					gemId = self.build.data.gemGrantedEffectIdForVaalGemId[self.build.data.gems[gemId].grantedEffectId]
				end
			end
			if gemId then
				local gemInstance = { level = 20, quality = 0, enabled = true, enableGlobal1 = true, gemId = gemId }
				gemInstance.nameSpec = self.build.data.gems[gemId].name
				gemInstance.support = socketedItem.support
				for _, property in pairs(socketedItem.properties) do
					if property.name == "Level" then
						gemInstance.level = tonumber(property.values[1][1]:match("%d+"))
					elseif property.name == "Quality" then
						gemInstance.quality = tonumber(property.values[1][1]:match("%d+"))
					end
				end
				local groupID = item.sockets[socketedItem.socket + 1].group
				if not itemSocketGroupList[groupID] then
					itemSocketGroupList[groupID] = { label = "", enabled = true, gemList = { }, slot = slotName }
				end
				local socketGroup = itemSocketGroupList[groupID]
				t_insert(socketGroup.gemList, gemInstance)
				if socketedItem.builtInSupport then
					socketGroup.imbuedSupport = socketedItem.builtInSupport:gsub("Supported by Level 1 ", "")
					self.build.skillsTab.controls.imbuedSupport.gemChangeFunc(data.gems[data.gemForBaseName[socketGroup.imbuedSupport:lower().." support"]], nil, nil, true, slotName)
				end
			end
		end
	end

	-- Import the socket groups
	for _, itemSocketGroup in pairs(itemSocketGroupList) do
		-- Check if this socket group matches an existing one
		local repGroup
		for index, socketGroup in pairs(self.build.skillsTab.socketGroupList) do
			if #socketGroup.gemList == #itemSocketGroup.gemList and (not socketGroup.slot or socketGroup.slot == slotName) then
				local match = true
				for gemIndex, gem in pairs(socketGroup.gemList) do
					if gem.nameSpec:lower() ~= itemSocketGroup.gemList[gemIndex].nameSpec:lower() then
						match = false
						break
					end
				end
				if match then
					repGroup = socketGroup
					break
				end
			end
		end
		if repGroup then
			-- Update the existing one
			for gemIndex, gem in pairs(repGroup.gemList) do
				local itemGem = itemSocketGroup.gemList[gemIndex]
				gem.level = itemGem.level
				gem.quality = itemGem.quality
			end
		else
			t_insert(self.build.skillsTab.socketGroupList, itemSocketGroup)
		end
		self.build.skillsTab:ProcessSocketGroup(itemSocketGroup)
	end
end

-- Return the index of the group with the most gems
function ImportTabClass:GuessMainSocketGroup()
	local largestGroupSize = 0
	local largestGroupIndex = 1
	for i, socketGroup in ipairs(self.build.skillsTab.socketGroupList) do
		if #socketGroup.gemList > largestGroupSize then
			largestGroupSize = #socketGroup.gemList
			largestGroupIndex = i
		end
	end
	return largestGroupIndex
end

function HexToChar(x)
	return string.char(tonumber(x, 16))
end

function UrlDecode(url)
	if url == nil then
		return
	end
	url = url:gsub("+", " ")
	url = url:gsub("%%(%x%x)", HexToChar)
	return url
end

function ImportTabClass:SetPredefinedBuildName()
end
