# evryBuild - POB for LocalExile

evryBuild adds **Forge Character** to PoB's **Import/Export Build** tab, below Build Sharing.
It exports the active build in memory and sends it to a configured LocalExile receiver.
**Preview** checks compatibility without creating a character.
**Forge Character** asks the receiver to create a new character under your local account.
The result, warnings and any refusal appear in the dialog.

This fork starts from Community Fork **master**, release **2.67.2**, commit
[`b32759ab`](https://github.com/PathOfBuildingCommunity/PathOfBuilding/tree/b32759ab0f31a1c8499a0d420cb0f0633d4fe478).
The integration is part of the fork's source, so an overlay installer is not needed.
The receiver and game server remain in a separate LocalExile project; this repository contains the PoB client side.

## Package the runnable application

Use Windows and Python 3.10 or newer.
Open PowerShell in this source checkout's root, then run:

```powershell
python scripts/package-evrybuild.py --destination '..\evryBuild-app'
```

The example creates a new application folder next to the source checkout.
Choose another destination if needed; its parent folder must already exist and the destination must not exist.
The optional `--source-root` selects another checkout and otherwise defaults to the repository containing the script.
No installed PoB or LocalExile checkout is needed for packaging.

The package contains this checkout's current Lua and assets, the existing compiled runtime renamed to
**evryBuild.exe**, licenses, and an explicit **evryBuild.cmd** launcher.
Packaging does not compile a new native runtime executable.
The application's source, packaged application and live PoB installation should remain separate, for example:

| Purpose | Example folder |
|---|---|
| This fork's Git source checkout | `evryBuild` |
| Portable evryBuild application | `evryBuild-app` |
| Another new package for validation | `evryBuild-validation` |
| Normal PoB for live PoE 1 | `C:\Path of Building Community (POE1)` |

The package starts with its own portable settings and empty `Builds` folder.
Personal builds, settings, remembered connection preferences, credentials and downloaded updates are not copied.
evryBuild's upstream updater is disabled, so it cannot replace the fork's code with unmodified PoB files.
Your separate live PoB installation keeps its normal update behavior.

Open the destination in **File Explorer** and double-click **evryBuild.exe**.
If using a launcher or shortcut that needs explicit paths, use the included **evryBuild.cmd**, or run:

```powershell
$evryBuildFolder = (Resolve-Path -LiteralPath '..\evryBuild-app').Path
Start-Process -FilePath (Join-Path $evryBuildFolder 'evryBuild.exe') -ArgumentList ('"' + (Join-Path $evryBuildFolder 'Launch.lua') + '"') -WorkingDirectory $evryBuildFolder
```

## Start a compatible LocalExile receiver

Use a LocalExile checkout containing the companion importer, with its normal client/data setup and an existing local account.
Gateway hosts the optional import listener on its own port; it starts and stops with the game server.
The receiver implementation and its administrator scripts belong to that server repository.

Open the LocalExile checkout in File Explorer. Click its address bar, type `powershell`, and press Enter.
From that server checkout's root, enable the listener and start the normal services:

```powershell
if (-not (Test-Path -LiteralPath 'config\pob-server.json')) {
    Copy-Item -LiteralPath 'config\pob-server.example.json' -Destination 'config\pob-server.json'
}
.\scripts\dev\live.ps1 -NoClient
```

The default import address is `http://127.0.0.1:20496`; game traffic keeps its separate port.
`logs/live-gateway.log` should show `[pob] listening on http://127.0.0.1:20496`.
No extra receiver process/window is needed.
A missing config or `"enabled": false` disables imports.
After editing the config, use `.\scripts\dev\live.ps1 -Only Gateway` to rebuild and restart it.
If migrating the old standalone receiver, stop its window with Ctrl+C and replace its old path-heavy config with the current example.

In the same PowerShell window, issue a token for your existing local account:

```powershell
$accountName = Read-Host 'Existing LocalExile account name'
.\scripts\dev\pob-server.ps1 -IssueToken -Account $accountName -NoBuild
```

Success returns `"ok":true` and a `token` value.
Copy the token value without its quotation marks.
It authorizes new-character imports only for that local account.
It is separate from your game login password and the official PoE account authorization shown elsewhere in PoB.
Issuing another token replaces the previous one.
The server owner supplies the account and token when connecting to a remotely managed receiver.

## Forge a character

1. Open the build in evryBuild.
   Select the tree, equipment set and skill set you want to import.
2. Click **Import/Export Build → Forge Character**.
3. Enter the receiver's **Server URL**, your **Local account**, and its **Account API token**.
   For the local setup, use `http://127.0.0.1:20496`.
4. Enter a new character name and an offered league such as `Standard`.
   Names use 3–23 letters, digits, underscores or hyphens.
   Existing characters and saves cannot be replaced.
5. Click **Preview** and read its result.
   “Ready with omissions” means supported parts can be imported but some features will be missing.
   Check active-equipment and inactive-weapon-set counts, omitted item/enabled-gem counts and modifier/passive warnings.
   If that result is acceptable, click **Forge Character**.
   Changing the build, name or connection details requires another preview.
6. After successful creation, log out to the game's login screen and log in again to refresh the character list.
   The imported character starts in Lioneye's Watch.

If creation loses its connection, refresh the character list before retrying.
The server may have completed the save before the response was interrupted.
An existing name is refused rather than replaced.

The dialog remembers only server URL, account and league in `LocalExile.json` in PoB's active user-data folder.
For a portable package, that folder is the package root alongside `Settings.xml` and `Builds`.
The token remains in the dialog's memory and is cleared after successful creation or closing.
The export uses the active build directly; it does not use the clipboard or a temporary build file.

[LocalExile.example.json](LocalExile.example.json) shows the nonsecret preference format:

```json
{
  "serverUrl": "http://127.0.0.1:20496",
  "account": "",
  "league": "Standard"
}
```

The dialog normally creates this file when submitting a request.
To preconfigure a new profile, copy the example into that profile as `LocalExile.json` and fill in its nonsecret fields.
Never add an API token or password to this file or to a saved build.

## Other servers and server folders

Change **Server URL** in the evryBuild dialog to use another receiver.
Remote connections require a valid HTTPS address and certificate.
Plain HTTP is accepted only for `localhost`, `127.0.0.1`, or `[::1]`.
Requests do not follow redirects, so enter the final server address.

The receiver shares the game's `data/` tree, `Game_SAVES_DB` database and `Game_LEAGUES` catalog.
Administrators set those normal environment overrides before starting all services and issuing tokens.
`Game_GGPK` selects the copied archive; by default it is beside `Game_CLIENT_EXE`, or `Client/Content.ggpk`.
The UI never supplies server file paths.

`config/pob-server.json` contains only `enabled`, `listenUrl`, optional `allowedLeagues` (full names already offered by the game),
and optional `certificatePath` / `certificatePasswordEnvironment` for direct HTTPS.
Paths for certificates resolve from the server repository root.
The listener defaults to loopback independently of the game's `Game_BIND` setting.
A TLS reverse proxy can forward a public HTTPS URL to it; remove any public prefix before forwarding `/api/pob/...`.
Old independent database/data/root/client/league JSON settings are rejected so imports cannot silently go to the wrong installation.
Ruthless imports remain unsupported.

## Receiver API

The integration uses this contract with the companion receiver:

| Request | Result |
|---|---|
| `POST /api/pob/preview` | Validate the selected build without saving a character |
| `POST /api/pob/characters` | Validate and save a new character and its progress together |

Both requests include:

```http
Authorization: Bearer ACCOUNT_TOKEN
Content-Type: application/json
Accept: application/json
```

```json
{
  "account": "local-account-name",
  "code": "POB_EXPORT_CODE",
  "name": "NewCharacter",
  "league": "Standard"
}
```

The client generates `code` with PoB's native XML export, Deflate and URL-safe Base64 encoding.
Successful JSON replies have `ok: true`, `preview`, character/class/level/league information, item/gem/passive/mastery
counts, `activeItems`, `inactiveWeaponItems`, `activeGems`, `inactiveWeaponGems`, `skippedItems`, `skippedGems`,
`partial`, `warnings`, `warningCount`, `warningsTruncated`, and a `next` message.
Counts cover the complete import even when warning details are shortened.
The server renders bounded success replies before committing, below 64 KiB (the client transport limit is 128 KiB).
Preview checks an entered name and account capacity without reserving either.
Refused requests have `ok: false` and an `error` string.
The dialog displays the result without logging the token or build contents.

## Current import compatibility

PoB can plan more features than LocalExile can currently restore in the game client.
Successful planning or export does not guarantee that a build is importable.
The companion importer validates the selected active sets, native item modifiers, gem identities, levels, sockets,
ordinary passives, mastery choices and passive connectivity against its pinned 3.29 client data.

Unsupported ascendancies/secondary ascendancies, jewels and cluster expansions, overrides, special passive nodes,
bandit/Pantheon rewards, unrepresentable items/modifiers and unavailable gems are skipped with warnings.
The character remains unascended; disconnected tree branches are omitted and extra passive points are recomputed.
Unavailable gems leave empty sockets without shifting the remaining gems or links.
Normal saved modifier-roll records retain representable equipment; approximated native defence rolls are reported.
PoB's planned effects can still differ from the server's implemented gameplay mechanics.

Malformed exports, incompatible classes/tree versions, invalid native item or socket/gem layouts, excessive passive
budgets, Ruthless rules, authentication errors and existing character names still prevent creation.
The import never overwrites existing characters or saves.
Quest completion and PoB's calculated totals, enemy assumptions and configuration conditions are not imported as game state.
The server reports any extra ordinary passive points it grants for the selected allocation.

The receiver remains responsible for authentication, account limits, item compatibility and all-or-nothing database saves.
evryBuild does not bypass those rules or edit the database directly.

## Development checks

Run from this fork's source root with Python 3.10 or newer:

```powershell
python tests/evrybuild/test_localexile.py -v
python -m unittest discover -s scripts -p test_package_evrybuild.py -v
```

The first command tests this fork's Lua module using the bundled runtime and JSON/curl libraries.
An alternate complete runtime can be supplied with `--runtime-dir '..\evryBuild-app'`.
See [the integration test notes](../tests/evrybuild/README.md) for details.
The packaging tests use synthetic files and check runtime preservation, profile isolation and destination guards.
These checks do not require a LocalExile installation or a live game client.
