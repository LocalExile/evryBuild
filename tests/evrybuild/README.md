# External LocalExile exporter validation

Run from the evryBuild source root on Windows with .NET 10 SDK, PowerShell and Python 3.10+:

```powershell
.\scripts\build-exporter.ps1
dotnet test tests/LocalExile.Export.Tests
python tests/evrybuild/test_localexile.py -v
python tests/evrybuild/test_exporter.py -v
python tests/evrybuild/test_parity.py -v
python -m unittest discover -s scripts -p test_package_evrybuild.py -v
```

The parser tests retain the bounded XML/zlib and active-set regression suite.
Lua tests use the actual bundled LuaJIT runtime, test the database dialog and preview guard,
compile application modules, confirm all HTTP transports remain disabled, and start the self-contained exporter
through the actual Windows pipe bridge without a shell.
The SQLite tests use synthetic game tables and temporary databases for read-only preview,
atomic creation, account/slot/name checks, duplicate and legacy refusal, failed-save rollback,
SQLite online backup and retention/reporting of an unknown passive effect.
Item-send tests simulate the Gateway on a private port through `Game_GATEWAY_PORT`, so a running server cannot affect them.
They cover the free cell and item id, unknown save fields, the row backup, and refusal while in game or before a restart.
Packaging checks profile isolation, required helper presence/hash, source freshness and destination guards.
They also require the current README and database setup guide in the portable output.
Account-selection tests cover single-account defaults, explicit selection between multiple accounts and case-insensitive names.

To also test a saved build against your normal extracted game data, supply explicit paths:

```powershell
python tests/evrybuild/test_exporter.py --data-folder 'C:\LocalExile\data' --build 'C:\Builds\Example.xml' -v
```

Replace those two paths with your actual data folder and saved PoB XML.
The test reads that data/build, but still exports only into its temporary test database.
It never opens your production save database.

A full native acceptance check uses an unmodified, pinned LocalExile installation and an isolated test database.
After export, return to the character list and verify character level, equipment, sockets/gems and movement.
Keep this result separate from automated save decoding: a valid serialized save alone is not native gameplay proof.

## Native acceptance recorded 2026-10-29

- Server: unmodified LocalExile `b2737133477b23f27a98b27196189bcad5881bc6`, clean tracked files;
  solution build succeeded with zero warnings/errors. No PoB API or server modifications.
- Destination: isolated SQLite database with a temporary local account, independent client copy and profile.
- Export path: the packaged Lua worker and bundled Windows x64 exporter, directly into SQLite.
- Exported character: level-99 Witch; 16 items, 30 gems, 100 ordinary passives, 9 masteries.
- Automated native contract check: the stock server decoded/serialized all 16 items and 30 gems and accepted the
  passive/mastery state; SQLite integrity and read-only preview checks passed.
- Owner's native-client result: **character loads, items and gems are present, movement works**.

The owner did not report an exhaustive passive-tree or skill-mechanic test. Gameplay support remains governed by
the documented partial/unimplemented/unknown compatibility findings; the in-game result is specific to the tested build.

To repeat manually on your own normal LocalExile installation:

1. Start the server/client with LocalExile's `scripts/dev/live.ps1` from its repository root.
2. In evryBuild, open a saved build, choose its active equipment/skill/tree sets and open **Export to LocalExile**.
3. Browse to the database printed by the Gateway's `saves:` startup line, select its extracted data folder if necessary,
   enter an existing account, an unused character name and the server's league, then **Preview** and **Export**.
4. In the game, return to login, log in to that account, select the new character and click **Play**.
5. Check name/level, **I** for equipment/socketed gems, **P** for the passive tree, and movement in town.
   Record any omitted encodings separately from gameplay effects that load but do not function.

For isolated regression testing, use a separate LocalExile checkout, client copy/profile and database, as in the
recorded run. The exporter tests above already isolate their own temporary databases and never use normal saves.
