-- Legacy build-site interface retained for old builds/protocol associations. No external transport exists.
buildSites = { websiteList = {} }
function buildSites.UploadBuild() return nil, "Web sharing is not available in evryBuild." end
function buildSites.DownloadBuild(link, website, callback)
	callback(false, "Paste a build code or open a local XML file; external links are not downloaded.")
end
function buildSites.ParseImportLinkFromURI() return nil end
