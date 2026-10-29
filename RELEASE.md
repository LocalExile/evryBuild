# Package evryBuild - POB for LocalExile

This guide builds the external SQLite edition and prepares a local Windows x64 portable ZIP.
It does not publish a release, push Git changes or modify a LocalExile installation.
The earlier API-based ZIP is a different implementation; do not label it as the external exporter.

## Build requirements

Use Windows x64 with the .NET 10 SDK, PowerShell, Python 3.10+ and the
[LocalExile/evryBuild source checkout](https://github.com/LocalExile/evryBuild).
The checked-in planner runtime is reused; a separate PoB installation or LocalExile checkout is not needed to package it.
The exporter is self-contained, so users of the resulting ZIP do not need .NET or Python installed.

Open PowerShell in the evryBuild repository root (the folder containing `src`, `runtime`, `tools` and `manifest.xml`).
For example, if you cloned it to `C:\src\evryBuild`, first run:

```powershell
Set-Location 'C:\src\evryBuild'
```

Replace that example path with your actual checkout. Confirm the prerequisites:

```powershell
dotnet --version
python --version
$PSVersionTable.PSVersion
```

The SDK should report `10.x`, and Python should report `3.10` or newer.

## Build and validate

Run these commands from that same PowerShell window, stopping if any command fails:

```powershell
.\scripts\build-exporter.ps1
dotnet test tests/LocalExile.Export.Tests
python tests/evrybuild/test_localexile.py -v
python tests/evrybuild/test_exporter.py -v
python -m unittest discover -s scripts -p test_package_evrybuild.py -v
```

The build writes `runtime/LocalExile/evryBuild.Export.exe` and a receipt containing its SHA-256 and source hashes.
Packaging refuses a missing, changed or stale exporter. Rebuild it after changing the exporter source or notices.
See [validation instructions](tests/evrybuild/README.md) for optional real-data checks and the native game result.
Without explicit real-data paths, that one optional test is skipped; all other checks must pass.

## Create a clean portable ZIP

Run the following in PowerShell from the repository root. It creates a new timestamped folder under `dist`.
Existing applications and profiles are never overwritten. The ZIP has one top-level `evryBuild` folder.

```powershell
$ErrorActionPreference = 'Stop'
$packageRoot = Join-Path (Get-Location).Path ('dist\external-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $packageRoot | Out-Null
$appFolder = Join-Path $packageRoot 'evryBuild'
python scripts/package-evrybuild.py --destination $appFolder
if ($LASTEXITCODE -ne 0) { throw 'Portable packaging failed.' }
$zipPath = Join-Path $packageRoot 'evryBuild-Portable-Windows-x64.zip'
Compress-Archive -LiteralPath $appFolder -DestinationPath $zipPath -CompressionLevel Optimal
$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$zipHash + '  evryBuild-Portable-Windows-x64.zip' | Set-Content -LiteralPath ($zipPath + '.sha256') -Encoding ascii
Write-Output $zipPath
Write-Output $zipHash
```

The package includes the current planner source/runtime, self-contained exporter, setup guide and license notices.
It excludes personal builds, preferences, account tokens, save databases and server/game files.
`evryBuild-package.json` records the source commit and SHA-256 of each copied application file.
Packaging uses current files, including uncommitted source changes, so finalize and review the source before preparing
an artifact intended for distribution. The recorded source commit alone does not describe an uncommitted change.

## Check the extracted package

Extract the ZIP to a new writable folder, open its `evryBuild` folder and run `evryBuild.exe`.
Confirm **Import/Export Build → Export to LocalExile** shows **Save database** and **Game data folder**,
with no URL or token fields. `README.md` and `docs/LocalExile.md` must be present in the extracted package.
Follow [the setup guide](docs/LocalExile.md) against a separate test database before distributing a newly changed converter.
The recorded native acceptance verifies a level-99 Witch on unmodified LocalExile `b2737133`; later converter changes
need their own appropriate regression checks.

Before sharing an artifact, confirm that `Builds/` is empty and there is no `Settings.xml` or `LocalExile.json`.
Use the SHA-256 file to identify the ZIP you validated. Publication is a separate owner action.

## Updating planner game data

Planner data maintenance still follows the relevant GGPK export and tree instructions in [CONTRIBUTING.md](CONTRIBUTING.md).
This does not change the LocalExile native save contract automatically. Keep conversion and compatibility rules tied to
verified server/client revisions, and mark unverified mechanics unknown rather than inferring support from a table entry.
