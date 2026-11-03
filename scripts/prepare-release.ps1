<#
.SYNOPSIS
Prepares every file an evryBuild release attaches, from the current clean commit.
The tag defaults to evrybuild-v and the VERSION file (VERSION 1.2.0 releases as evrybuild-v1.2.0).

.DESCRIPTION
Builds a self-updating portable package for the tag, zips it with its SHA-256, and collects the update files the
portable application downloads from the release: evryBuild-update.xml, evryBuild.Export.exe and
evryBuild-package.json. Nothing is pushed or published. Run scripts\build-exporter.ps1 and the tests first.

.EXAMPLE
.\scripts\prepare-release.ps1
#>
param(
    [string]$Tag,
    # Test only: point the package's updates at a local server instead of GitHub.
    [string]$UpdateBase
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (-not $Tag) { $Tag = 'evrybuild-v' + (Get-Content -Raw -LiteralPath (Join-Path $repo 'VERSION')).Trim() }
$root = Join-Path $repo ("dist\release-" + $Tag + '-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $root | Out-Null
$app = Join-Path $root 'evryBuild'
$assets = Join-Path $root 'assets'

$arguments = @((Join-Path $repo 'scripts\package-evrybuild.py'), '--destination', $app, '--release-tag', $Tag, '--assets', $assets)
if ($UpdateBase) { $arguments += @('--update-base', $UpdateBase) }
python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Release packaging failed.' }

$zip = Join-Path $assets 'evryBuild-Portable-Windows-x64.zip'
Compress-Archive -LiteralPath $app -DestinationPath $zip -CompressionLevel Optimal
$hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
$hash + '  evryBuild-Portable-Windows-x64.zip' | Set-Content -LiteralPath ($zip + '.sha256') -Encoding ascii

$commit = (Get-Content -Raw -LiteralPath (Join-Path $app 'evryBuild-package.json') | ConvertFrom-Json).sourceRevision
Write-Output ''
Write-Output "Release $Tag from commit $commit"
Write-Output "Attach every file in: $assets"
Get-ChildItem -LiteralPath $assets | ForEach-Object { Write-Output ('  ' + $_.Name) }
Write-Output "ZIP SHA-256: $hash"
