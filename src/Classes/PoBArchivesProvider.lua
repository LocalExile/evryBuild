-- Compatibility facade: public-build browsing and recommendations are not part of evryBuild.
local Provider = newClass("PoBArchivesProvider", "ExtBuildListProvider", function(self)
	self.ExtBuildListProvider({})
	self.buildList = {}
end)
function Provider:GetApiUrl() return nil end
function Provider:GetPageUrl() return nil end
function Provider:GetRecommendations() self.statusMsg = "External build browsing is not available in evryBuild." end
function Provider:GetBuilds() self:GetRecommendations() end
