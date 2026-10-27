# ExileForge — Path of Building for LocalExile

ExileForge adds **Forge Character** to PoB's **Import/Export Build** tab, below Build Sharing.
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
python scripts/package-exileforge.py --destination 'F:\evry\evryPath\ExileForge-new'
```

The example uses a new folder so it does not overwrite the existing application at
`F:\evry\evryPath\ExileForge`.
Choose another destination if needed; its parent folder must already exist and the destination must not exist.
The optional `--source-root` selects another checkout and otherwise defaults to the repository containing the script.
No installed PoB or LocalExile checkout is needed for packaging.

The package contains this checkout's current Lua and assets, the existing compiled runtime renamed to
**ExileForge.exe**, licenses, and an explicit **ExileForge.cmd** launcher.
Packaging does not compile a new native runtime executable.
The application's source, packaged application and live PoB installation should remain separate, for example:

| Purpose | Example folder |
|---|---|
| This fork's Git source checkout | `F:\evry\evryPath\ExileForge-src` |
| Existing portable ExileForge application | `F:\evry\evryPath\ExileForge` |
| New package for validation | `F:\evry\evryPath\ExileForge-new` |
| Normal PoB for live PoE 1 | `C:\Path of Building Community (POE1)` |

The package starts with its own portable settings and empty `Builds` folder.
Personal builds, settings, remembered connection preferences, credentials and downloaded updates are not copied.
ExileForge's upstream updater is disabled, so it cannot replace the fork's code with unmodified PoB files.
Your separate live PoB installation keeps its normal update behavior.

Open the destination in **File Explorer** and double-click **ExileForge.exe**.
If using a launcher or shortcut that needs explicit paths, use the included **ExileForge.cmd**, or run:

```powershell
$exileForgeFolder = 'F:\evry\evryPath\ExileForge-new'
Start-Process -FilePath (Join-Path $exileForgeFolder 'ExileForge.exe') -ArgumentList ('"' + (Join-Path $exileForgeFolder 'Launch.lua') + '"') -WorkingDirectory $exileForgeFolder
```

## Start a compatible LocalExile receiver

The receiver is required in addition to the normal game services.
Use a LocalExile checkout containing the companion PoB receiver, with extracted client data and an existing local account.
The receiver's scripts and C# implementation are maintained in that server repository, not here.

For the existing local setup, open a separate PowerShell window and run:

```powershell
Set-Location F:\evry\evryPath\LocalExile
.\scripts\dev\pob-server.ps1
```

For another setup, replace the first path with that LocalExile checkout's root.
The receiver's default address is `http://127.0.0.1:20496`.
Its first run creates `config\pob-server.json` from its example and builds a separate receiver copy.
Keep that window running while sending builds; Ctrl+C stops the receiver.
The normal Auth, Patch and Gateway processes can keep running.

In a second PowerShell window in the same LocalExile checkout, issue a token for your existing local account:

```powershell
Set-Location F:\evry\evryPath\LocalExile
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

1. Open the build in ExileForge.
   Select the tree, equipment set and skill set you want to import.
2. Click **Import/Export Build → Forge Character**.
3. Enter the receiver's **Server URL**, your **Local account**, and its **Account API token**.
   For the local setup, use `http://127.0.0.1:20496`.
4. Enter a new character name and an offered league such as `Standard`.
   Names use 3–23 letters, digits, underscores or hyphens.
   Existing characters and saves cannot be replaced.
5. Click **Preview** and read its result.
   If it passes and the warnings are acceptable, click **Forge Character**.
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

Change **Server URL** in the ExileForge dialog to use another receiver.
Remote connections require a valid HTTPS address and certificate.
Plain HTTP is accepted only for `localhost`, `127.0.0.1`, or `[::1]`.
Requests do not follow redirects, so enter the final server address.

The receiver administrator configures its filesystem separately in its `config/pob-server.json`:

| Receiver setting | Purpose |
|---|---|
| `listenUrl` | Listener address and port |
| `repositoryRoot` | Base for relative server paths; itself relative to the configuration file |
| `dataFolder` | Extracted game data, including `tables` |
| `databasePath` | Existing save database shared with the game services |
| `clientGgpk` | Copied client archive used to validate passive connectivity |
| `oozWorker` | Node decompression worker |
| `nodeExecutable` | Node command or executable path |
| `leagues` | Base leagues offered for imports |

These folders belong to the server machine and are never sent by PoB.
Absolute paths are supported by the receiver, and other paths resolve against its configured root.
A TLS reverse proxy may forward a public HTTPS URL to a loopback receiver.
If the public URL contains a path prefix, the proxy must remove that prefix before forwarding the API route.
Direct receiver HTTPS additionally supports `certificatePath` and `certificatePasswordEnvironment`.

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
counts, `warnings`, and a `next` message.
Refused requests have `ok: false` and an `error` string.
The dialog displays the result without logging the token or build contents.

## Current import compatibility

PoB can plan more features than LocalExile can currently restore in the game client.
Successful planning or export does not guarantee that a build is importable.
The companion importer validates the selected active sets, native item modifiers, gem identities, levels, sockets,
ordinary passives, mastery choices and passive connectivity against its pinned 3.29 client data.

The current receiver refuses builds that require unsupported ascendancies or secondary ascendancies, tree jewels and
cluster expansions, passive overrides, named bandit/Pantheon rewards, Ruthless rules, or unsupported item modifiers.
It also refuses incompatible tree versions, invalid equipment/gems and existing character names.
These refusals happen before creation; unsupported parts are not silently discarded.
Quest completion and PoB's calculated totals, enemy assumptions and configuration conditions are not imported as game state.
The server reports any extra ordinary passive points it grants for the selected allocation.

The receiver remains responsible for authentication, account limits, item compatibility and all-or-nothing database saves.
ExileForge does not bypass those rules or edit the database directly.

## Development checks

Run from this fork's source root with Python 3.10 or newer:

```powershell
python tests/exileforge/test_localexile.py -v
python -m unittest discover -s scripts -p test_package_exileforge.py -v
```

The first command tests this fork's Lua module using the bundled runtime and JSON/curl libraries.
An alternate runtime can be supplied with `--runtime-dir 'F:\evry\evryPath\ExileForge'`.
See [the integration test notes](../tests/exileforge/README.md) for details.
The packaging tests use synthetic files and check runtime preservation, profile isolation and destination guards.
These checks do not require a LocalExile installation or a live game client.
