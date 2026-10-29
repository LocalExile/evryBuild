# Export to LocalExile — external SQLite integration

This evryBuild edition creates new characters directly in a local LocalExile save database.
No API, account token, HTTP port, background receiver, or LocalExile source modification is required.
Normal LocalExile server/client setup and its extracted game data are still required to play.
The exporter does not modify the game archive or install server code.

## Run the portable application

Extract the complete ZIP to a writable folder, open its `evryBuild` folder and run `evryBuild.exe`.
The included `evryBuild.cmd` is an alternative launcher. Do not run from inside the ZIP.
The exporter is a self-contained Windows x64 executable included under `LocalExile/`.
No installed .NET runtime, Python, Git, or separate PoB is required by the portable application.
For developer packaging, use the commands in [README](../README.md).

## Export a build

1. Open the build and select its active passive tree, equipment set and skill set.
2. Open **Import/Export Build → Export to LocalExile**.
3. Click **Browse** beside **Save database** and select the server's existing `saves.db`.
   Normally this is `data/saves.db` inside the LocalExile installation.
   Select the database file itself, not a backup, `-wal` or `-shm` sidecar.
4. The **Game data folder** is detected beside the database when it contains `tables/` and `item-types.json`.
   If your database is elsewhere, click its Browse button and choose `item-types.json` in the server's data folder.
   The dialog selects that file's containing folder. These are the normal extracted files from LocalExile setup.
5. Inspect lists the existing account names and leagues found on existing characters.
   Enter the **Existing account** that should own the new character.
   With one account, the first inspected account is filled automatically.
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
   The imported character starts in Lioneye's Watch.

The dialog saves only the database/data paths, account name and league in `LocalExile.json` in the active user folder.
Legacy server URL and token fields are ignored and are removed when preferences are next saved.
If an export loses its response, refresh the character list before trying again.
The new name is refused on retry if the transaction already committed.

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

Unmodified upstream does not store the imported armour-base percentile used by the earlier PoB server branch.
Armour items are retained, with a warning that the server's base roll will be used.
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

## Repository boundary

All conversion, compatibility rules, SQLite writes, file selection and packaging live in evryBuild.
There are no references to a LocalExile project, checkout or running service in the exporter build.
For testing, an independent checkout of an exact upstream revision can consume exported fixture saves.
The earlier Gateway/API branch and previously published API-based ZIP are separate from this external redesign.
No repository transfer or new release is performed by these scripts.
