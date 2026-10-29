describe("evryBuild offline network policy", function()
	local originalLaunchSubScript, originalDownloadPage
	before_each(function()
		originalLaunchSubScript = _G.LaunchSubScript
		originalDownloadPage = launch.DownloadPage
		_G.LaunchSubScript = function() error("External account access must not start a worker") end
		launch.DownloadPage = function() error("External account access must not send a request") end
	end)
	after_each(function()
		_G.LaunchSubScript = originalLaunchSubScript
		launch.DownloadPage = originalDownloadPage
	end)
	it("does not accept or refresh old official-account credentials", function()
		local api = new("PoEAPI", "old-token", "old-refresh", os.time() + 3600)
		assert.is_nil(api.authToken)
		assert.is_nil(api.refreshToken)
		local called = false
		api:ValidateAuth(function(valid, message)
			called = true
			assert.is_false(valid)
			assert.is_string(message)
		end)
		assert.is_true(called)
	end)
	it("reports unavailable account import without contacting the official services", function()
		local api = new("PoEAPI")
		local calls = 0
		api:FetchAuthToken(function(message)
			assert.is_string(message)
			calls = calls + 1
		end)
		api:DownloadCharacterList("pc", function(value, message)
			assert.is_nil(value)
			assert.is_string(message)
			calls = calls + 1
		end)
		api:DownloadCharacter("pc", "AnyCharacter", function(value, message)
			assert.is_nil(value)
			assert.is_string(message)
			calls = calls + 1
		end)
		assert.are.equal(3, calls)
	end)
end)
