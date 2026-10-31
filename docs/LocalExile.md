# Export to LocalExile — external SQLite integration

This evryBuild edition creates new characters directly in a local LocalExile save database.
No API, account token, HTTP port, background receiver, or LocalExile source modification is required.
Normal LocalExile server/client setup and its extracted game data are still required to play.
The exporter does not modify the game archive or install server code.

## Run the portable application

Download the Windows portable ZIP from [LocalExile/evryBuild releases](https://github.com/LocalExile/evryBuild/releases/latest).
Extract the complete ZIP to a writable folder, open the extracted folder containing `evryBuild.exe`, and run it.
The included `evryBuild.cmd` is an alternative launcher. Do not run from inside the ZIP.
The exporter is a self-contained Windows x64 executable included under `LocalExile/`.
No installed .NET runtime, Python, Git, or separate PoB is required by the portable application.
For developer packaging, use the commands in [README](../README.md).

## Before the first export

- Use a normal, working local LocalExile installation and its supported game client (the tested reference uses 3.29.3b).
  Follow that installation's `Agents/GettingStarted.md` for server setup, data extraction and account registration.
  evryBuild does not create accounts or replace LocalExile's normal startup procedure.
- Start LocalExile normally and identify the database it actually uses. The Gateway startup log prints
  `[gateway] saves: ...`; in a source installation using `scripts/dev/live.ps1`, look in `logs/live-gateway.log`.
  The default is `data/saves.db`, but `Game_SAVES_DB` can point elsewhere. Select the path from the running server,
  especially if you have several installations or save databases.
- Keep the database on a local disk with write access. Also allow creation of `evryBuild-backups/` beside it.
  The extracted game data should come from the same installation and client version as the server.
- You may leave the server running. Finish the current play session and return to character selection before
  testing a new export. No extra PoB process, listener or server configuration is needed.

The export dialog has **Save database**, **Game data folder**, **Existing account**, **New character** and **League**.
If it asks for a server URL or API token, you are running the older API-based portable.
Extract a new external build to a separate folder; the published API-era ZIP does not update itself to this design.

## Export a build

1. Open the build and select its active passive tree, equipment set and skill set.
2. Open **Import/Export Build → Export to LocalExile**.
3. Click **Browse** beside **Save database** and select the server's existing `saves.db`.
   Normally this is `data/saves.db` inside the LocalExile installation.
   Select the database file itself, not a backup, `-wal` or `-shm` sidecar.
4. The **Game data folder** is detected beside the database when it contains `tables/` and `item-types.json`.
   If your database is elsewhere, click its Browse button and choose `item-types.json` in the server's data folder.
   The dialog selects that file's containing folder. These are the normal extracted files from LocalExile setup.
5. Choosing a database runs inspection; **Inspect DB** repeats it if you entered the path manually.
   Inspection lists the existing account names and leagues found on existing characters.
   Enter the **Existing account** that should own the new character.
   With one account, it is filled automatically. With several accounts, type the intended name from the list.
   A previously selected name is retained only if it exists in the chosen database.
   Account passwords and API tokens are neither needed nor read.
6. Enter an unused **New character** name: 3–23 ASCII letters, digits, underscores or hyphens.
   Enter the exact **League** offered by your running game server, normally `Standard`.
   A database cannot advertise the server's configured leagues; existing league names are suggestions only.
7. Click **Preview**. No character, backup or schema change is written by preview.
   Read the item/gem/passive counts, omitted native encodings and gameplay compatibility findings.
   Missing gameplay support does not remove an otherwise loadable entry.
8. Click **Export to LocalExile**. A SQLite backup is created first; both new-character records then commit together.
   A changed build, account, destination, league or prepared save requires another preview.
9. Return to the game's character screen to refresh its list.
   If the character does not appear, log out to the login screen and log in again.
   Select the new character and click **Play**. The imported character starts in Lioneye's Watch.
   Press **I** to inspect equipment and socketed gems, **P** to inspect passives, and click the ground to check movement.

For example, if the Gateway log shows `C:\LocalExile\data\saves.db`, choose that file. Normally the data folder
will become `C:\LocalExile\data`. Use your existing account name, an unused name such as `ImportedWitch`,
and `Standard` if that is the league offered by your server. Your password is used only at the game's login screen.

The dialog saves only the database/data paths, account name and league in `LocalExile.json` in the active user folder.
Legacy server URL and token fields are ignored and are removed when preferences are next saved.
If an export loses its response, refresh the character list before trying again.
The new name is refused on retry if the transaction already committed.

## Send an item to a character

Open or create an item in the **Items** tab so it shows on the right, then click **Send to LocalExile...**.
The dialog reuses your last database and account, and checks the item and the character as soon as it opens.
Click **Send** when it says ready, then log in. The item is in the character's main inventory.
Items, the stash and gold stay in the Gateway's memory from a character's first login until the Gateway stops.
Logging out or closing the client does not clear them, so the dialog tells you what to do when it matters:

| The dialog says | What to do |
|---|---|
| Ready | Click **Send**. |
| You are in game | Log out to the character screen, then click **Check Again**. |
| Restart the Gateway first | From the LocalExile folder, run `.\scripts\dev\live.ps1 -Only Gateway -NoBuild`, then click **Check Again**. |

You only need the restart when the character has played since the Gateway started, and it clears that session's
instances and ground items. The send is refused until it is safe, so no item is written and then overwritten.
It changes only the character's inventory, keeps the rest of the save, and keeps the previous save as
`evryBuild-backups/<character>-<time>.save.json`. The database itself is not copied for a send.

**Copy Command** works while you play, with no logout, and needs no character. Paste it into the game's chat.
A unique is one command, `/item <name>`, which makes the server's own version with its own rolls.
Anything else is several commands: run the first, pick the new item up on your cursor, then run the rest.
Click **Copy Command** again for each next line. Commands cannot set quality, item level, a rare's name,
fractured modifiers or the mirrored state; **Send** keeps those.

Modifiers are matched to the client's data, and a line PoB's text cannot identify is skipped and listed as a warning.
For a unique, **Send** uses the server's catalogue in the save database for its exact modifiers,
keeping PoB's roll where the stats match and the top of the roll otherwise.
Ruthless characters are refused, and a character needs a save first, so log in with it once.

## Troubleshooting

Report reproducible problems or feature suggestions in the [evryBuild issue tracker](https://github.com/LocalExile/evryBuild/issues).
Include the release/version, reproduction steps and relevant export warnings, with private account/save data removed.

| What you see | What to do |
|---|---|
| No accounts listed | Check the Gateway's database path and select that exact file. If it has no accounts yet, register one using LocalExile's normal account setup, then click **Inspect DB**. |
| Game data folder is empty or rejected | Click its **Browse** button and select `item-types.json` in the server's extracted `data` folder. The folder must also contain `tables/` and the files produced by normal LocalExile data extraction. |
| The save database is busy | Wait for the server's save to finish and retry. If it remains busy, close any SQLite editor holding a write transaction. Do not delete `-wal` or `-shm` files. |
| Preview is required again | Click **Preview** after changing the build, account, character name, league, database or data folder, review the result, then export. |
| Character does not appear | Return to the login screen, log in to the selected account again, and select the exact league used for export. If still absent, compare the selected database with the Gateway log. |
| Export response was lost or timed out | Refresh the character list before retrying. A successful write may already have committed; duplicate names are refused. |
| Items load but effects or skills do not work | Read the compatibility summary and full `.export.json` report beside the backup. Loadable entries remain even when gameplay support is partial, missing or unknown. |
| The bundled exporter cannot start | Extract the complete portable ZIP again to a writable local folder. Keep `LocalExile/evryBuild.Export.exe` with the application; a source checkout must run `scripts/build-exporter.ps1` before use. |

## Database safety

The selected database must exist on a local drive and have the expected LocalExile tables and columns.
The exporter never creates an empty server database, registers accounts or migrates a schema.
Network shares are refused because SQLite locking/WAL must remain local.
Inspection reads account IDs/names only, not stored password hashes or credentials.

Creation refuses existing character metadata, native saves and legacy JSON saves, including case-only name collisions.
The default 24-character account limit is checked again inside the write transaction.
Both `account_characters` and `characters` are inserted using parameters in a single immediate transaction.
A failed write rolls back both records; existing characters are never replaced.
SQLite waits briefly for another writer and reports busy databases without forcing locks or stopping services.

Backups use SQLite's online backup API, including committed WAL data, rather than copying an open database file.
They are stored beside the selected database in `evryBuild-backups/` with unique timestamped names.
They contain the server's complete accounts/saves and should stay private like the original database.
No automatic restore or overwrite is performed.
The backup also has a `.export.json` report with the complete prepared warnings and compatibility findings.
The dialog shows a bounded summary, prioritising known missing/partial effects.
A report records a prepared export; if creation fails, it does not imply that the character was committed.

## Gameplay compatibility

Native encoding and gameplay implementation are separate checks.
An item can load correctly while one of its modifiers does nothing; a gem can exist without its entire skill executor.
A passive can be allocated while one of its effects is unimplemented.
Those entries are retained and reported.

The exporter reads the local Gateway DLL's version metadata when it can locate it beside the selected data folder.
It uses bundled, version-specific rules for player stats and skill mechanics.
The initial reference profile targets unmodified LocalExile `b2737133477b23f27a98b27196189bcad5881bc6` and client `3.29.3b`.
A version match describes that reference implementation, not a guarantee about custom uncommitted changes.
Other builds and unlisted mechanics are **unknown**, with available reference notes shown.
The initial profile intentionally covers a small verified subset; it is not a complete catalogue of server support.

- **Implemented:** a matching reference rule covers the effect.
- **Partial:** some effects work and others do not; the finding explains the gap.
- **Not implemented:** a known capability is missing in the exporter/upstream contract.
- **Unknown:** no verified rule, an unrecognised build, or insufficient evidence. This does not mean broken.

For example, the reference implementation supports Frostblink movement but not its damage or chilled ground.
An ordinary native stat or gem appearing in extracted tables is not proof that its gameplay mechanic is implemented.
Rules and evidence are maintained in `tools/LocalExile.Export/compatibility.json`; users need no server API to read them.

Armour items keep their defence base roll. A server older than that save field ignores it and uses its own roll.
No compensating modifiers or invented stats are added to force PoB totals.

## Current encoding limits

The converter preserves supported native classes/levels, ordinary passives/masteries, equipment/flasks,
modifier IDs and rolls, item identities, sockets/links and native gems from the active build sets.
Unsupported gameplay effects remain when their native IDs/values are representable.
Unresolvable modifier descriptions are reported separately as encoding omissions.

The current save adapter creates unascended characters; ascendancy selections/nodes, jewels/cluster expansions,
passive overrides, unsupported special/disconnected nodes, bandit/Pantheon rewards and item-granted skill groups
may be omitted because this exporter cannot yet encode them in the upstream character contract.
Unavailable native bases, identities or gem records are omitted with explicit warnings.
Unavailable gems leave empty sockets without shifting retained gems or changing links.
PoB calculations, enemy assumptions, configuration and campaign completion are not imported as game state.
Extra ordinary passive points required by a valid retained tree are reported.

Malformed builds, incompatible tree/class versions, invalid native layouts, impossible gem values, excessive passive
budgets, Ruthless imports and name/account failures remain errors before creation.
The exporter targets the server's 3.29.3b extracted data; PoB calculation parity is not promised.

## Validated native result

On 2026-10-29, an isolated database was populated through the packaged evryBuild Lua worker and the bundled exporter,
then opened by a clean, unmodified LocalExile checkout at `b2737133477b23f27a98b27196189bcad5881bc6`.
The exported level-99 Witch contained 16 items, 30 gems, 100 ordinary passives and 9 masteries.
The owner confirmed in the native game client that the character loaded, items and gems appeared, and movement worked.
This is a loading/equipment/movement acceptance result for that build; it does not certify every imported effect,
passive interaction, skill or PoB calculation. The automated and manual checks are described in
`tests/evrybuild/README.md` in the source repository.

## Repository boundary

All conversion, compatibility rules, SQLite writes, file selection and packaging live in evryBuild.
There are no references to a LocalExile project, checkout or running service in the exporter build.
For testing, an independent checkout of an exact upstream revision can consume exported fixture saves.
The earlier Gateway/API branch and previously published API-based ZIP are separate from this external redesign.
No repository transfer or new release is performed by these scripts.
