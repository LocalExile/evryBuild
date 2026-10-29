-- Compatibility facade: official account authentication/import is not part of evryBuild.
local message = "Official account access is not available in evryBuild. Use LocalExile or local build files."
local PoEAPIClass = newClass("PoEAPI", function(self) self.ERROR_NO_AUTH = message end)
function PoEAPIClass:ResetDetails()
	self.authToken, self.refreshToken, self.tokenExpiry = nil, nil, nil
end
function PoEAPIClass:UpdateMain() self:ResetDetails() end
function PoEAPIClass:ValidateAuth(callback) callback(false, message) end
function PoEAPIClass:FetchAuthToken(callback) callback(message) end
function PoEAPIClass:DownloadWithRefresh(endpoint, callback) callback(nil, message) end
function PoEAPIClass:DownloadWithRateLimit(policy, url, callback) callback(nil, message) end
function PoEAPIClass:DownloadCharacterList(realm, callback) callback(nil, message) end
function PoEAPIClass:DownloadCharacter(realm, name, callback) callback(nil, message) end
