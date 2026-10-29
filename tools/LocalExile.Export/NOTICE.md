The bounded PoB parser, item conversion, passive validation and native table readers were adapted from
LocalExile feature/pob-import commit 5394de0a5208bb2407491cf986fab5455714bdc8:
https://github.com/evrydayjunglist/evryPath/tree/5394de0a5208bb2407491cf986fab5455714bdc8

This project is an independent offline exporter. It has no project or runtime dependency on LocalExile,
does not include a game server, and does not distribute extracted game tables or game client files.
Native save contracts are tested against unmodified LocalExile b2737133477b23f27a98b27196189bcad5881bc6.
Microsoft.Data.Sqlite and its SQLite native dependencies retain their upstream license notices in packaged output.

.NET runtime and Microsoft.Data.Sqlite: Copyright Microsoft Corporation and contributors, MIT.
See notices/DOTNET-LICENSE.txt and notices/DOTNET-THIRD-PARTY-NOTICES.txt.
The bundled .NET runtime is 10.0.14; refresh these notices when updating that runtime.
SQLitePCLRaw 2.1.12: Copyright 2014-2024 SourceGear, LLC, Apache License 2.0.
See notices/SQLITEPCLRAW-LICENSE.txt. Source: https://github.com/ericsink/SQLitePCL.raw/tree/v2.1.12
Native SQLite is in the public domain: https://www.sqlite.org/copyright.html
