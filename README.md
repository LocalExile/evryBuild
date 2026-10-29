# evryBuild - POB for LocalExile

evryBuild is an offline build planner with a dedicated connection to a configured LocalExile server.
It retains local passive-tree, skill, item, gem and calculation tools and adds **Preview / Forge Character**
in the **Import/Export Build** tab.

The application's only HTTP transport is the LocalExile preview/character-creation API.
Official account imports, OAuth, trade searches, public-build browsing, web uploads/downloads,
URL shortening, online updates and external browser launches are unavailable.
Saved build XML, pasted build codes, local tree-link decoding, clipboard items and build comparison continue to work offline.
A compatible LocalExile server determines which planned features can be restored in game; see
[setup and import compatibility](docs/LocalExile.md).

## Portable Windows application

With Python 3.10 or newer, run from this source checkout:

```powershell
python scripts/package-evrybuild.py --destination '..\evryBuild-app'
```

Choose a new destination folder. The package contains the current source, assets, licenses and existing Windows x64 runtime.
It does not copy personal builds, settings or credentials and does not require another PoB installation.
Extract the complete portable package to a writable folder and run **evryBuild.exe** (or **evryBuild.cmd**).
Builds and settings stay inside that folder. Updates are installed by extracting a new evryBuild package.

## Development checks

```powershell
python tests/evrybuild/test_localexile.py -v
python -m unittest discover -s scripts -p test_package_evrybuild.py -v
```

The Lua tests use the bundled runtime and exercise LocalExile requests, offline import/export controls,
blocked external requests, legacy-account credential handling and application module compilation.
The packaging tests cover runtime completeness, profile isolation and destination guards.

## Attribution and license

This fork is based on Path of Building Community Fork master 2.67.2, commit
[b32759ab](https://github.com/PathOfBuildingCommunity/PathOfBuilding/tree/b32759ab0f31a1c8499a0d420cb0f0633d4fe478),
building on Openarl's Path of Building and the work of its community contributors.
These names identify the upstream authors and provenance, not this application's branding.
[LICENSE.md](LICENSE.md) contains the MIT license and third-party notices.
Historical upstream changes remain in [changelog.txt](changelog.txt).
