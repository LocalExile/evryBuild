# External LocalExile exporter validation

Run from the evryBuild source root on Windows with .NET 10 SDK, PowerShell and Python 3.10+:

```powershell
.\scripts\build-exporter.ps1
dotnet test tests/LocalExile.Export.Tests
python tests/evrybuild/test_localexile.py -v
python tests/evrybuild/test_exporter.py -v
python -m unittest discover -s scripts -p test_package_evrybuild.py -v
```

The parser tests retain the bounded XML/zlib and active-set regression suite.
Lua tests use the actual bundled LuaJIT runtime, test the database dialog and preview guard,
compile application modules, confirm all HTTP transports remain disabled, and start the self-contained exporter
through the actual Windows pipe bridge without a shell.
The SQLite tests use synthetic game tables and temporary databases for read-only preview,
atomic creation, account/slot/name checks, duplicate and legacy refusal, failed-save rollback,
SQLite online backup and retention/reporting of an unknown passive effect.
Packaging checks profile isolation, required helper presence/hash, source freshness and destination guards.

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
