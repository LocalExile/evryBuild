# Build the one-shot local exporter included with the Windows portable application.
param()
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$output = Join-Path $repo 'runtime\LocalExile'
& dotnet publish (Join-Path $repo 'tools\LocalExile.Export\LocalExile.Export.csproj') `
    --configuration Release --runtime win-x64 --self-contained true --output $output `
    -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:DebugType=None --verbosity minimal
if ($LASTEXITCODE -ne 0) { throw 'Local exporter build failed.' }
$exe = Join-Path $output 'evryBuild.Export.exe'
$sources = @{}
$sourceRoot = Join-Path $repo 'tools\LocalExile.Export'
Get-ChildItem -LiteralPath $sourceRoot -File -Recurse | Where-Object {
    $_.FullName -notmatch '[\\/](bin|obj)[\\/]' -and $_.Extension -in @('.cs', '.csproj', '.json', '.md', '.txt')
} | ForEach-Object {
    $relative = $_.FullName.Substring($sourceRoot.Length + 1).Replace('\', '/')
    $sources[$relative] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
@{ executable = 'evryBuild.Export.exe'; sha256 = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant(); sources = $sources } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $output 'exporter-build.json') -Encoding UTF8
Write-Output "Local exporter ready: $exe"
