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
python tests/evrybuild/test_updater.py -v
python -m unittest discover -s scripts -p test_package_evrybuild.py -v
```

The build writes `runtime/LocalExile/evryBuild.Export.exe` and a receipt containing its SHA-256 and source hashes.
Packaging refuses a missing, changed or stale exporter. Rebuild it after changing the exporter source or notices.
See [validation instructions](tests/evrybuild/README.md) for optional real-data checks and the native game result.
Without explicit real-data paths, that one optional test is skipped; all other checks must pass.

## Prepare a release

A release package updates itself from later releases, so it is built from a clean commit that is pushed to
`LocalExile/evryBuild` before anyone can update from it. Choose the tag first: `evrybuild-localexile-external-YYYY.MM.DD`,
with `.2`, `.3` for a second release on the same day. Put the release's notes in a new top section of `CHANGELOG.md`
and commit it; the portable application shows that section when it offers the update.

Then, from the repository root with the exporter built and the tests passing:

```powershell
.\scripts\prepare-release.ps1 -Tag evrybuild-localexile-external-2026.11.10
```

It refuses uncommitted changes, copies every file exactly as that commit stores it, and writes a new
`dist\release-<tag>-<time>` folder with the portable `evryBuild` folder and an `assets` folder holding:

| File | What it is |
|---|---|
| `evryBuild-Portable-Windows-x64.zip` and `.sha256` | The portable download for new users |
| `evryBuild-update.xml` | The update manifest: the commit, every file's source and SHA-256, and the release notes |
| `evryBuild.Export.exe` | The exporter, which is built rather than committed, so updates download it from the release |
| `evryBuild-package.json` | The package record, kept current by updates |

`evryBuild-package.json` records the source commit and the SHA-256 of each copied application file.
A package built without `-Tag` (with `scripts/package-evrybuild.py` alone) copies the working tree, including
uncommitted changes, and never updates itself; use it for local testing only.

## Publish and how updates find it

Push the commit, then create the release with the tag on that commit and attach every file in `assets`:

```powershell
gh release create <tag> --repo LocalExile/evryBuild --target <commit> --title "<title>" --notes-file <notes.md> --latest (Get-ChildItem <assets folder>).FullName
```

A portable copy checks `https://github.com/LocalExile/evryBuild/releases/latest/download/evryBuild-update.xml`
when it starts (Options: **Check for updates at startup**) and with **Check for Update**. It offers a release newer
than its own. **Update Now** downloads only the files whose SHA-256 differs: committed files from
`raw.githubusercontent.com` at the release's commit, and the exporter and package record from the release. Every file
must match the manifest before anything changes. The update then renames each replaced file to `.old`, moves the
new one in, and restarts. It starts a new process when `evryBuild.exe` or a DLL changed. If any step fails, the
earlier steps are undone. `Builds/`, `Settings.xml`, `LocalExile.json` and other personal files are never touched.

Only the release GitHub marks **Latest** is offered. Publish as a pre-release first to test it with a separate copy;
nobody is offered it until it is marked Latest. Copies from releases before 2026.11 have no updater and need one
manual download.

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
