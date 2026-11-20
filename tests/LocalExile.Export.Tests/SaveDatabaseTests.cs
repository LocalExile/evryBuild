using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Data.Sqlite;

[CollectionDefinition("SaveDatabaseEnv", DisableParallelization = true)]
public sealed class SaveDatabaseEnvCollection;

[Collection("SaveDatabaseEnv")]
public sealed class SaveDatabaseTests : IDisposable
{
    const uint RingHash = 1001, VestHash = 1002, GemHash = 2001;
    static readonly GatewayState.Snapshot GatewayStopped = new(false, false, null);

    readonly string _root;
    readonly string _data;
    readonly string _accountId = Guid.NewGuid().ToString();

    public SaveDatabaseTests()
    {
        _root = Directory.CreateTempSubdirectory("evrybuild-savedb-").FullName;
        _data = Path.Combine(_root, "data");
        Directory.CreateDirectory(Path.Combine(_data, "tables"));
        WriteGameData(_data);
    }

    public void Dispose()
    {
        Environment.SetEnvironmentVariable("Game_AUTH_DB", null);
        Environment.SetEnvironmentVariable("Game_CHARACTERS_DB", null);
        Environment.SetEnvironmentVariable("Game_WORLD_DB", null);
        if (Directory.Exists(_root)) Directory.Delete(_root, true);
    }

    static void WriteGameData(string data)
    {
        void WriteTable(string name, object rows) =>
            File.WriteAllText(Path.Combine(data, "tables", name + ".json"), JsonSerializer.Serialize(rows));

        WriteTable("Characters", new[] { new { IntegerId = 3 } });
        WriteTable("ExperienceLevels", new[] { new { Level = 20, Experience = 123000 } });
        WriteTable("Stats", new[]
        {
            new { Id = "additional_strength", IsLocal = false },
            new { Id = "additional_dexterity", IsLocal = false },
            new { Id = "special_unique_stat", IsLocal = false },
        });
        WriteTable("PassiveSkills", new object[]
        {
            new { PassiveSkillGraphId = 10, Id = "WitchStart", Name = "Witch", Characters = new[] { 0 }, Stats = Array.Empty<int>(), Stat1Value = 0,
                SkillPointsGranted = 0, AscendancyKey = (int?)null, IsExpansion = false, IsMultipleChoice = false, MasteryGroup = (int?)null, SkillType = 0, DescendancyKey = (int?)null },
            new { PassiveSkillGraphId = 11, Id = "StrNode", Name = "Strength", Characters = Array.Empty<int>(), Stats = new[] { 0 }, Stat1Value = 10,
                SkillPointsGranted = 0, AscendancyKey = (int?)null, IsExpansion = false, IsMultipleChoice = false, MasteryGroup = (int?)null, SkillType = 0, DescendancyKey = (int?)null },
            new { PassiveSkillGraphId = 12, Id = "MasteryNode", Name = "Mastery", Characters = Array.Empty<int>(), Stats = Array.Empty<int>(), Stat1Value = 0,
                SkillPointsGranted = 0, AscendancyKey = (int?)null, IsExpansion = false, IsMultipleChoice = false, MasteryGroup = (int?)0, SkillType = 0, DescendancyKey = (int?)null },
        });
        WriteTable("PassiveSkillMasteryGroups", new[] { new { MasteryEffects = new[] { 0 } } });
        WriteTable("PassiveSkillMasteryEffects", new[] { new { Id = "MasteryEffect1", HASH16 = 500, Stats = new[] { 0 }, Stat1Value = 5 } });
        File.WriteAllText(Path.Combine(data, "passive-skill-graphs.json"), JsonSerializer.Serialize(new
        {
            revision = "3.29.3b",
            normal = new
            {
                nodes = new object[]
                {
                    new { id = 10, adjacent = new[] { 11 } },
                    new { id = 11, adjacent = new[] { 10, 12 } },
                    new { id = 12, adjacent = new[] { 11 } },
                }
            }
        }));
        WriteTable("ItemClasses", new[]
        {
            new { Id = "Ring", ItemStance = (int?)null },
            new { Id = "Body Armour", ItemStance = (int?)null },
            new { Id = "Active Skill Gem", ItemStance = (int?)null },
        });
        WriteTable("Tags", new[] { new { Id = "default" } });
        WriteTable("BaseItemTypes", new object[]
        {
            new { Id = "Metadata/Items/Ring", Name = "Iron Ring", HASH32 = RingHash, Width = 1, Height = 1, ItemVisualIdentity = 0,
                ItemClassesKey = 0, ItemStance = (int?)null, DropLevel = 1, Implicit_ModsKeys = Array.Empty<int>(), TagsKeys = new[] { 0 }, ModDomain = 1 },
            new { Id = "Metadata/Items/Vest", Name = "Plate Vest", HASH32 = VestHash, Width = 2, Height = 3, ItemVisualIdentity = 0,
                ItemClassesKey = 1, ItemStance = (int?)null, DropLevel = 1, Implicit_ModsKeys = Array.Empty<int>(), TagsKeys = new[] { 0 }, ModDomain = 1 },
            new { Id = "Metadata/Items/Gems/SkillGemFireball", Name = "Fireball", HASH32 = GemHash, Width = 1, Height = 1, ItemVisualIdentity = 0,
                ItemClassesKey = 2, ItemStance = (int?)null, DropLevel = 1, Implicit_ModsKeys = Array.Empty<int>(), TagsKeys = new[] { 0 }, ModDomain = 1 },
        });
        WriteTable("ItemVisualIdentity", new[] { new { HASH16 = 7 } });
        WriteTable("SkillGems", new[]
        {
            new { BaseItemTypesKey = 2, GemVariants = new[] { 0 }, IsSupport = false, GemColour = 3, ItemExperienceType = 0,
                RegularVariant = (int?)null, StrengthRequirementPercent = 0, DexterityRequirementPercent = 0, IntelligenceRequirementPercent = 100, IsVaalVariant = false }
        });
        WriteTable("ItemExperienceTypes", new[] { new { Id = "Normal" } });
        WriteTable("ItemExperiencePerLevel", new[] { new { ItemExperienceType = 0, ItemCurrentLevel = 1, Experience = 0 } });
        WriteTable("GemEffects", new[] { new { Id = "Fireball", Name = "Fireball", GrantedEffect = 0, GrantedEffect2 = (int?)null } });
        WriteTable("GrantedEffects", new[] { new { Id = "Fireball", IsSupport = false, ActiveSkill = 0 } });
        WriteTable("GrantedEffectsPerLevel", new[] { new { GrantedEffect = 0, Level = 1, PlayerLevelReq = 1 } });
        WriteTable("GrantedEffectQualityStats", Array.Empty<object>());
        WriteTable("ActiveSkills", new[] { new { Id = "Fireball", DisplayedName = "Fireball" } });
        WriteTable("Words", new[] { new { Text = "FixtureUnique", HASH32 = 55, Wordlist = 6 } });
        WriteTable("UniqueStashLayout", new[] { new { WordsKey = 0, ItemVisualIdentityKey = 0 } });
        WriteTable("Mods", new object[]
        {
            new Dictionary<string, object?>
            {
                ["Id"] = "Strength1", ["HASH16"] = 101, ["Name"] = "of the Brute", ["Domain"] = 1, ["GenerationType"] = 2, ["Level"] = 1,
                ["StatsKey1"] = 0, ["StatsKey2"] = null, ["Stat1Min"] = 8, ["Stat1Max"] = 20, ["Families"] = Array.Empty<int>(),
                ["SpawnWeight_TagsKeys"] = new[] { 0 }, ["SpawnWeight_Values"] = new[] { 1000 },
                ["GenerationWeight_TagsKeys"] = Array.Empty<int>(), ["GenerationWeight_Values"] = Array.Empty<int>(), ["IsEssenceOnlyModifier"] = false,
            },
            new Dictionary<string, object?>
            {
                ["Id"] = "DexterityUnique", ["HASH16"] = 102, ["Name"] = "DexUnique", ["Domain"] = 1, ["GenerationType"] = 3, ["Level"] = 1,
                ["StatsKey1"] = 1, ["StatsKey2"] = null, ["Stat1Min"] = 10, ["Stat1Max"] = 50, ["Families"] = Array.Empty<int>(),
                ["SpawnWeight_TagsKeys"] = Array.Empty<int>(), ["SpawnWeight_Values"] = Array.Empty<int>(),
                ["GenerationWeight_TagsKeys"] = Array.Empty<int>(), ["GenerationWeight_Values"] = Array.Empty<int>(), ["IsEssenceOnlyModifier"] = false,
            },
            new Dictionary<string, object?>
            {
                ["Id"] = "SpecialUniqueMod", ["HASH16"] = 103, ["Name"] = "SpecialUnique", ["Domain"] = 1, ["GenerationType"] = 3, ["Level"] = 1,
                ["StatsKey1"] = 2, ["StatsKey2"] = null, ["Stat1Min"] = 1, ["Stat1Max"] = 1, ["Families"] = Array.Empty<int>(),
                ["SpawnWeight_TagsKeys"] = Array.Empty<int>(), ["SpawnWeight_Values"] = Array.Empty<int>(),
                ["GenerationWeight_TagsKeys"] = Array.Empty<int>(), ["GenerationWeight_Values"] = Array.Empty<int>(), ["IsEssenceOnlyModifier"] = false,
            },
        });
        File.WriteAllText(Path.Combine(data, "item-types.json"), JsonSerializer.Serialize(new
        {
            types = new object[]
            {
                new { type = "Metadata/Items/Ring", components = new[] { "Base", "Mods" }, read = 2 },
                new { type = "Metadata/Items/Vest", components = new[] { "Base", "Mods", "Armour", "Sockets" }, read = 4 },
                new { type = "Metadata/Items/Gems/SkillGemFireball", components = new[] { "Base", "SkillGem" }, read = 2 },
            }
        }));
    }

    static void WithDb(string path, Action<SqliteConnection> action)
    {
        using var conn = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = path, Pooling = false }.ToString());
        conn.Open();
        action(conn);
    }

    static void Exec(SqliteConnection conn, string sql, params (string Name, object Value)[] parameters)
    {
        using var cmd = conn.CreateCommand();
        cmd.CommandText = sql;
        foreach (var (name, value) in parameters) cmd.Parameters.AddWithValue(name, value);
        cmd.ExecuteNonQuery();
    }

    static object? Scalar(SqliteConnection conn, string sql, params (string Name, object Value)[] parameters)
    {
        using var cmd = conn.CreateCommand();
        cmd.CommandText = sql;
        foreach (var (name, value) in parameters) cmd.Parameters.AddWithValue(name, value);
        return cmd.ExecuteScalar();
    }

    string CreateLegacyDb(string? path = null)
    {
        string dbPath = path ?? Path.Combine(_data, "saves.db");
        WithDb(dbPath, db =>
        {
            Exec(db, """
                PRAGMA journal_mode=WAL;
                CREATE TABLE accounts(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, account TEXT NOT NULL) STRICT;
                CREATE TABLE account_characters(id TEXT PRIMARY KEY, account_id TEXT NOT NULL, name TEXT NOT NULL UNIQUE COLLATE NOCASE, created_utc TEXT NOT NULL, character TEXT NOT NULL) STRICT;
                CREATE TABLE characters(name TEXT PRIMARY KEY COLLATE NOCASE, save TEXT NOT NULL) STRICT;
                """);
            Exec(db, "INSERT INTO accounts VALUES($id, $name, $acct)",
                ("$id", _accountId), ("$name", "alice"), ("$acct", """{"private":"untouched"}"""));
        });
        return dbPath;
    }

    (string CharactersPath, string AuthPath) CreateSplitRelationalDb(string? folder = null, string charactersFile = "characters.db",
        string authFile = "auth.db", bool relationalMeta = true)
    {
        string dir = folder ?? _data;
        Directory.CreateDirectory(dir);
        string charsPath = Path.Combine(dir, charactersFile);
        string authPath = Path.Combine(dir, authFile);

        WithDb(authPath, db =>
        {
            Exec(db, """
                PRAGMA journal_mode=WAL;
                CREATE TABLE accounts(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, account TEXT NOT NULL) STRICT;
                """);
            Exec(db, "INSERT INTO accounts VALUES($id, $name, $acct)",
                ("$id", _accountId), ("$name", "alice"), ("$acct", """{"passwordVerifier":"secret"}"""));
        });

        WithDb(charsPath, db =>
        {
            Exec(db, """
                PRAGMA journal_mode=WAL;
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
                CREATE TABLE characters(name TEXT PRIMARY KEY COLLATE NOCASE, save TEXT NOT NULL) STRICT;
                CREATE TABLE account_characters_json(id TEXT PRIMARY KEY, account_id TEXT NOT NULL, name TEXT NOT NULL UNIQUE COLLATE NOCASE, created_utc TEXT NOT NULL, character TEXT NOT NULL) STRICT;
                CREATE TABLE account_characters(
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    class INTEGER NOT NULL,
                    level INTEGER NOT NULL,
                    league TEXT NOT NULL,
                    area_id TEXT NOT NULL,
                    created_utc TEXT NOT NULL,
                    last_played_utc TEXT NOT NULL,
                    last_town TEXT,
                    portrait INTEGER NOT NULL DEFAULT 0,
                    portrait_frame INTEGER NOT NULL DEFAULT 0,
                    hardcore_death_league TEXT,
                    hardcore_death_utc TEXT,
                    hardcore_death_permanent INTEGER CHECK (hardcore_death_permanent IN (0, 1))
                ) STRICT;
                CREATE TABLE character_saves(
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL COLLATE NOCASE,
                    deleted_utc TEXT,
                    has_inventories INTEGER NOT NULL CHECK (has_inventories IN (0, 1)),
                    experience INTEGER,
                    passives TEXT CHECK (passives IS NULL OR json_valid(passives)),
                    waypoints TEXT CHECK (waypoints IS NULL OR json_valid(waypoints)),
                    visited TEXT CHECK (visited IS NULL OR json_valid(visited)),
                    quest_flags TEXT CHECK (quest_flags IS NULL OR json_valid(quest_flags)),
                    extra_passive_points INTEGER,
                    gold INTEGER,
                    refund_points INTEGER,
                    portal_cosmetic INTEGER,
                    active_auras TEXT CHECK (active_auras IS NULL OR json_valid(active_auras)),
                    petrified_blood INTEGER CHECK (petrified_blood IN (0, 1)),
                    selected_hideout TEXT,
                    life INTEGER,
                    mana INTEGER,
                    vitals_character TEXT,
                    vitals_session TEXT,
                    vitals_retired INTEGER CHECK (vitals_retired IN (0, 1)),
                    cluster_passives TEXT CHECK (cluster_passives IS NULL OR json_valid(cluster_passives)),
                    sulphite INTEGER,
                    atlas_passive_presets TEXT CHECK (atlas_passive_presets IS NULL OR json_valid(atlas_passive_presets)),
                    atlas_passive_points INTEGER,
                    selected_atlas_layout TEXT,
                    quest_refunds_credited TEXT CHECK (quest_refunds_credited IS NULL OR json_valid(quest_refunds_credited)),
                    pantheon_major TEXT,
                    pantheon_minor TEXT,
                    attack_in_place_slots INTEGER,
                    skill_bar_mask52 INTEGER,
                    stance TEXT,
                    descendancy INTEGER,
                    descendancy_nodes TEXT,
                    unknown TEXT CHECK (unknown IS NULL OR json_valid(unknown))
                ) STRICT;
                CREATE UNIQUE INDEX character_saves_name ON character_saves (name) WHERE deleted_utc IS NULL;
                CREATE TABLE character_inventories(save INTEGER NOT NULL REFERENCES character_saves(id), inventory INTEGER NOT NULL, PRIMARY KEY(save, inventory)) STRICT;
                CREATE TABLE character_skill_bar(save INTEGER NOT NULL REFERENCES character_saves(id), slot INTEGER NOT NULL, skill TEXT NOT NULL, PRIMARY KEY(save, slot)) STRICT;
                CREATE TABLE character_masteries(save INTEGER NOT NULL REFERENCES character_saves(id), node INTEGER NOT NULL, effect INTEGER NOT NULL, PRIMARY KEY(save, node)) STRICT;
                CREATE TABLE character_tattoos(save INTEGER NOT NULL REFERENCES character_saves(id), node INTEGER NOT NULL, tattoo TEXT NOT NULL, PRIMARY KEY(save, node)) STRICT;
                CREATE TABLE character_tattoo_keystones(save INTEGER NOT NULL REFERENCES character_saves(id), node INTEGER NOT NULL, keystone INTEGER NOT NULL, PRIMARY KEY(save, node)) STRICT;
                CREATE TABLE items(
                    id INTEGER PRIMARY KEY,
                    character INTEGER REFERENCES character_saves(id),
                    stash INTEGER,
                    inventory INTEGER,
                    role TEXT NOT NULL CHECK (role IN ('placed', 'socketed', 'original', 'start_weapon', 'tutorial_skill', 'tutorial_support')),
                    parent INTEGER REFERENCES items(id),
                    ord INTEGER NOT NULL,
                    placement INTEGER,
                    x INTEGER,
                    y INTEGER,
                    type INTEGER NOT NULL,
                    item_level INTEGER NOT NULL,
                    quality INTEGER NOT NULL,
                    charges INTEGER NOT NULL,
                    stack_size INTEGER NOT NULL,
                    sockets TEXT CHECK (sockets IS NULL OR json_valid(sockets)),
                    links TEXT CHECK (links IS NULL OR json_valid(links)),
                    gem_experience INTEGER NOT NULL,
                    rarity INTEGER NOT NULL,
                    identified INTEGER NOT NULL CHECK (identified IN (0, 1)),
                    has_mods INTEGER NOT NULL CHECK (has_mods IN (0, 1)),
                    name TEXT CHECK (name IS NULL OR json_valid(name)),
                    gem_variant INTEGER NOT NULL,
                    corrupted INTEGER NOT NULL CHECK (corrupted IN (0, 1)),
                    fractured INTEGER NOT NULL,
                    mirrored INTEGER NOT NULL CHECK (mirrored IN (0, 1)),
                    gem_flags INTEGER NOT NULL,
                    visual INTEGER,
                    defence_base_roll INTEGER NOT NULL,
                    influences INTEGER NOT NULL,
                    split INTEGER NOT NULL CHECK (split IN (0, 1)),
                    synthesised INTEGER NOT NULL CHECK (synthesised IN (0, 1)),
                    foreseeing INTEGER NOT NULL CHECK (foreseeing IN (0, 1)),
                    foresee_seed INTEGER NOT NULL,
                    alternate_quality_type INTEGER,
                    vestigial INTEGER NOT NULL DEFAULT 0,
                    heist_blueprint TEXT,
                    memory_strands INTEGER NOT NULL DEFAULT 0 CHECK (memory_strands BETWEEN 0 AND 255),
                    intangibility INTEGER NOT NULL DEFAULT 0 CHECK (intangibility BETWEEN 0 AND 100),
                    required_level INTEGER CHECK (required_level BETWEEN 0 AND 255),
                    relic_style INTEGER CHECK (relic_style BETWEEN 0 AND 255),
                    CHECK ((character IS NULL) <> (stash IS NULL))
                ) STRICT;
                CREATE TABLE item_mods(
                    item INTEGER NOT NULL REFERENCES items(id),
                    ord INTEGER NOT NULL,
                    mod TEXT NOT NULL,
                    section INTEGER NOT NULL,
                    stat_values TEXT NOT NULL CHECK (json_valid(stat_values)),
                    PRIMARY KEY(item, ord)
                ) STRICT;
                """);
            if (relationalMeta)
                Exec(db, "INSERT INTO meta VALUES('relational_saves', '2026-11-12T16:15:57Z')");
        });

        return (charsPath, authPath);
    }

    static JsonElement RunRequest(object payload, out int exitCode, Func<int, GatewayState.Snapshot>? gateway = null)
    {
        using var input = new StringReader(JsonSerializer.Serialize(payload));
        using var output = new StringWriter();
        exitCode = ExportCommand.Run(input, output, gateway ?? (_ => GatewayStopped));
        using var doc = JsonDocument.Parse(output.ToString());
        return doc.RootElement.Clone();
    }

    static string Sha256(string path) => Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path)));

    // ---------------------------------------------------------------- Schema & Auth Attachment Tests

    [Fact]
    public void Legacy_saves_db_layout_is_detected_and_validated()
    {
        string db = CreateLegacyDb();
        using var session = SaveDatabase.Open(db, write: false);
        Assert.Equal("main", session.Layout.AccountsSchema);
        Assert.Null(session.Layout.AuthDatabasePath);
        Assert.False(session.Layout.ColumnarCharacters);
        Assert.False(session.Layout.RelationalSaves);
    }

    [Fact]
    public void Split_relational_characters_and_auth_db_layout_is_detected_and_attached_read_only()
    {
        var (charsPath, authPath) = CreateSplitRelationalDb();
        using var session = SaveDatabase.Open(charsPath, write: true);
        Assert.Equal("auth", session.Layout.AccountsSchema);
        Assert.Equal(Path.GetFullPath(authPath), session.Layout.AuthDatabasePath);
        Assert.True(session.Layout.ColumnarCharacters);
        Assert.True(session.Layout.RelationalSaves);

        // Verify auth is strictly read-only even on a write connection.
        var ex = Assert.Throws<SqliteException>(() =>
            Exec(session.Connection, "INSERT INTO auth.accounts VALUES('x', 'bob', '{}')"));
        Assert.Equal(8, ex.SqliteErrorCode); // SQLITE_READONLY

        // Verify BEGIN IMMEDIATE on characters.db does not lock auth.db for writes.
        WithDb(authPath, otherAuth =>
        {
            using var otherTx = otherAuth.BeginTransaction(deferred: false);
            Exec(otherAuth, "INSERT INTO accounts VALUES('other', 'bob', '{}')");
            using var charTx = session.Connection.BeginTransaction(deferred: false);
            charTx.Rollback();
            otherTx.Rollback();
        });
    }

    [Fact]
    public void Copied_characters_db_finds_stem_auth_db_and_falls_back_to_sibling_auth_db()
    {
        string sub1 = Path.Combine(_root, "copy #1");
        var (copiedChars, copiedAuth) = CreateSplitRelationalDb(sub1, "scratch.db", "scratch-auth.db");
        using (var s1 = SaveDatabase.Open(copiedChars, write: false))
        {
            Assert.Equal("auth", s1.Layout.AccountsSchema);
            Assert.Equal(Path.GetFullPath(copiedAuth), s1.Layout.AuthDatabasePath);
        }

        string sub2 = Path.Combine(_root, "copy-fallback");
        var (fallbackChars, fallbackAuth) = CreateSplitRelationalDb(sub2, "characters-backup.db", "auth.db");
        using (var s2 = SaveDatabase.Open(fallbackChars, write: false))
        {
            Assert.Equal("auth", s2.Layout.AccountsSchema);
            Assert.Equal(Path.GetFullPath(fallbackAuth), s2.Layout.AuthDatabasePath);
        }
    }

    [Fact]
    public void Game_AUTH_DB_environment_variable_resolves_companion_auth_database()
    {
        string charsDir = Path.Combine(_root, "only-chars");
        string authDir = Path.Combine(_root, "separate-auth");
        var (charsPath, _) = CreateSplitRelationalDb(charsDir, "characters.db", "unused.db");
        File.Delete(Path.Combine(charsDir, "unused.db"));
        string envAuthPath = Path.Combine(authDir, "custom-auth.db");
        Directory.CreateDirectory(authDir);
        WithDb(envAuthPath, db =>
        {
            Exec(db, "CREATE TABLE accounts(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, account TEXT NOT NULL) STRICT;");
            Exec(db, "INSERT INTO accounts VALUES($id, 'envuser', '{}')", ("$id", _accountId));
        });
        Environment.SetEnvironmentVariable("Game_AUTH_DB", envAuthPath);

        using var session = SaveDatabase.Open(charsPath, write: false);
        Assert.Equal(Path.GetFullPath(envAuthPath), session.Layout.AuthDatabasePath);
        Assert.Equal(["envuser"], SaveDatabase.Accounts(session.Connection, session.Layout).Select(a => a.Name));
    }

    [Fact]
    public void Schema_validation_names_missing_tables_columns_and_auth_db_without_modifying_files()
    {
        // Unrelated DB -> names account_characters
        string wrong = Path.Combine(_root, "wrong.db");
        WithDb(wrong, db => Exec(db, "CREATE TABLE unrelated(value TEXT)"));
        string wrongHash = Sha256(wrong);
        var reply = RunRequest(new { operation = "inspect", database = wrong }, out int code);
        Assert.Equal(1, code);
        Assert.Contains("account_characters", reply.GetProperty("error").GetString());
        Assert.Equal(wrongHash, Sha256(wrong));

        // Selecting auth.db -> hints to select characters.db
        var (_, authPath) = CreateSplitRelationalDb(Path.Combine(_root, "auth-hint"));
        reply = RunRequest(new { operation = "inspect", database = authPath }, out code);
        Assert.Equal(1, code);
        Assert.Contains("account_characters", reply.GetProperty("error").GetString());
        Assert.Contains("characters.db", reply.GetProperty("error").GetString());

        // Missing companion auth.db -> names accounts and expected auth path
        string noAuthDir = Path.Combine(_root, "no-auth");
        var (noAuthChars, noAuthFile) = CreateSplitRelationalDb(noAuthDir);
        File.Delete(noAuthFile);
        reply = RunRequest(new { operation = "inspect", database = noAuthChars }, out code);
        Assert.Equal(1, code);
        Assert.Contains("accounts", reply.GetProperty("error").GetString());
        Assert.Contains("auth.db", reply.GetProperty("error").GetString());

        // Missing column in columnar account_characters -> names table and column
        string badColDir = Path.Combine(_root, "bad-col");
        var (badColChars, _) = CreateSplitRelationalDb(badColDir);
        WithDb(badColChars, db =>
        {
            Exec(db, "DROP TABLE account_characters");
            Exec(db, "CREATE TABLE account_characters(id TEXT PRIMARY KEY, account_id TEXT, name TEXT, class INTEGER) STRICT");
        });
        reply = RunRequest(new { operation = "inspect", database = badColChars }, out code);
        Assert.Equal(1, code);
        Assert.Contains("account_characters", reply.GetProperty("error").GetString());
        Assert.Contains("last_played_utc", reply.GetProperty("error").GetString());

        // Missing relational table -> names exact table
        string missingRelDir = Path.Combine(_root, "missing-rel");
        var (missingRelChars, _) = CreateSplitRelationalDb(missingRelDir);
        WithDb(missingRelChars, db => Exec(db, "DROP TABLE item_mods"));
        reply = RunRequest(new { operation = "inspect", database = missingRelChars }, out code);
        Assert.Equal(1, code);
        Assert.Contains("item_mods", reply.GetProperty("error").GetString());

        // Missing column in auth.accounts -> names auth.accounts and column
        string badAuthDir = Path.Combine(_root, "bad-auth");
        var (badAuthChars, badAuthFile) = CreateSplitRelationalDb(badAuthDir);
        WithDb(badAuthFile, db =>
        {
            Exec(db, "DROP TABLE accounts");
            Exec(db, "CREATE TABLE accounts(id TEXT PRIMARY KEY, name TEXT) STRICT");
        });
        reply = RunRequest(new { operation = "inspect", database = badAuthChars }, out code);
        Assert.Equal(1, code);
        Assert.Contains("auth.accounts", reply.GetProperty("error").GetString());
        Assert.Contains("account", reply.GetProperty("error").GetString());
    }

    // ---------------------------------------------------------------- Inspect Tests

    [Fact]
    public void Inspect_works_on_split_relational_layout_and_ignores_stale_json_mirrors()
    {
        var (charsPath, _) = CreateSplitRelationalDb();
        WithDb(charsPath, db =>
        {
            Exec(db, """
                INSERT INTO account_characters(id, account_id, name, class, level, league, area_id, created_utc, last_played_utc, last_town, portrait)
                VALUES($id, $acct, 'RelWitch', 3, 92, 'Keepers', '1_1_town', '2026-11-12T00:00:00Z', '2026-11-12T01:00:00Z', '1_1_town', 0)
                """, ("$id", Guid.NewGuid().ToString()), ("$acct", _accountId));
            // Stale mirror with outdated character must not be read.
            Exec(db, "INSERT INTO account_characters_json VALUES($id, $acct, 'StaleChar', '2026-01-01', '{\"Level\":1,\"League\":\"StaleLeague\"}')",
                ("$id", Guid.NewGuid().ToString()), ("$acct", _accountId));
        });

        var reply = RunRequest(new { operation = "inspect", database = charsPath, account = "alice" }, out int code);
        Assert.Equal(0, code);
        Assert.True(reply.GetProperty("ok").GetBoolean());
        Assert.Equal(_data, reply.GetProperty("dataFolder").GetString());
        Assert.Equal(["alice"], reply.GetProperty("accounts").EnumerateArray().Select(e => e.GetString()));
        Assert.DoesNotContain("passwordVerifier", reply.GetRawText());
        var chars = reply.GetProperty("characters").EnumerateArray().ToList();
        var ch = Assert.Single(chars);
        Assert.Equal("RelWitch", ch.GetProperty("name").GetString());
        Assert.Equal(92, ch.GetProperty("level").GetInt32());
        Assert.Equal("Keepers", ch.GetProperty("league").GetString());
        var leagues = reply.GetProperty("leagues").EnumerateArray().Select(e => e.GetString()).ToList();
        Assert.Contains("Standard", leagues);
        Assert.Contains("Keepers", leagues);
        Assert.DoesNotContain("StaleLeague", leagues);
    }

    // ---------------------------------------------------------------- Item Preview, Copy Command & Item Send Tests

    [Fact]
    public void Item_preview_copy_command_and_send_work_on_split_relational_layout()
    {
        var (charsPath, authPath) = CreateSplitRelationalDb();
        string authBefore = Sha256(authPath);
        long saveId = 0;
        WithDb(charsPath, db =>
        {
            Exec(db, """
                INSERT INTO account_characters(id, account_id, name, class, level, league, area_id, created_utc, last_played_utc, last_town, portrait)
                VALUES($id, $acct, 'RelWitch', 3, 90, 'Standard', '1_1_town', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '1_1_town', 0)
                """, ("$id", Guid.NewGuid().ToString()), ("$acct", _accountId));
            // Stale legacy characters table row must be ignored.
            Exec(db, "INSERT INTO characters VALUES('RelWitch', '{\"Inventories\":{\"0\":[]}}')");
            // Deleted save with same name must be ignored.
            Exec(db, "INSERT INTO character_saves(name, deleted_utc, has_inventories) VALUES('RelWitch', '2026-01-01T00:00:00Z', 1)");
            // Active relational save with newer columns populated.
            saveId = (long)Scalar(db, """
                INSERT INTO character_saves(name, has_inventories, experience, passives, descendancy, unknown)
                VALUES('RelWitch', 1, 123000, '[11]', 2, '{"future":true}') RETURNING id
                """)!;
            Exec(db, "INSERT INTO character_inventories VALUES($s, 0), ($s, 2)", ("$s", saveId));
            // Existing item in main inventory at (0,0) with placement id 4, plus equipped item with placement id 9, plus stash-id item 0x40000005.
            Exec(db, """
                INSERT INTO items(character, inventory, role, ord, placement, x, y, type, item_level, quality, charges, stack_size,
                    gem_experience, rarity, identified, has_mods, gem_variant, corrupted, fractured, mirrored, gem_flags,
                    defence_base_roll, influences, split, synthesised, foreseeing, foresee_seed, vestigial, memory_strands, relic_style)
                VALUES($s, 0, 'placed', 0, 4, 0, 0, $ring, 1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 12, 3),
                      ($s, 2, 'placed', 0, 9, 0, 0, $ring, 1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL),
                      ($s, 0, 'placed', 1, $stashId, 1, 0, $ring, 1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, NULL)
                """, ("$s", saveId), ("$ring", (long)RingHash), ("$stashId", (long)0x40000005u));
        });

        string rareRing = "Rarity: RARE\nDoom Loop\nIron Ring\nItem Level: 75\nQuality: 20\n+15 to Strength\nCorrupted";

        // Copy Command works even without selecting a character.
        var noCharPreview = RunRequest(new { operation = "item-preview", database = charsPath, account = "alice", name = "", item = rareRing }, out int code);
        Assert.Equal(0, code);
        Assert.True(noCharPreview.GetProperty("ok").GetBoolean());
        Assert.Contains("Choose a character", noCharPreview.GetProperty("blocked").GetString());
        Assert.Contains("/item Iron Ring", noCharPreview.GetProperty("commands").EnumerateArray().Select(c => c.GetString()));

        // Preview with character succeeds and reports Ready + placement (0, 1).
        var preview = RunRequest(new { operation = "item-preview", database = charsPath, account = "alice", name = "RelWitch", item = rareRing }, out code);
        Assert.Equal(0, code);
        Assert.True(preview.GetProperty("ok").GetBoolean());
        Assert.Equal(JsonValueKind.Null, preview.GetProperty("blocked").ValueKind);
        Assert.Equal(0, preview.GetProperty("x").GetInt32());
        Assert.Equal(1, preview.GetProperty("y").GetInt32());
        string previewKey = preview.GetProperty("previewKey").GetString()!;
        Assert.NotEmpty(previewKey);

        // Blocked states are respected using columnar last_played_utc.
        var inGame = RunRequest(new { operation = "item-preview", database = charsPath, account = "alice", name = "RelWitch", item = rareRing },
            out _, _ => new GatewayState.Snapshot(true, true, DateTimeOffset.UtcNow));
        Assert.Contains("Log out", inGame.GetProperty("blocked").GetString());

        var needsRestart = RunRequest(new { operation = "item-preview", database = charsPath, account = "alice", name = "RelWitch", item = rareRing },
            out _, _ => new GatewayState.Snapshot(true, false, new DateTimeOffset(2025, 1, 1, 0, 0, 0, TimeSpan.Zero)));
        Assert.Contains("Restart the Gateway", needsRestart.GetProperty("blocked").GetString());

        // Send writes into relational tables and creates a JSON rollback backup.
        var sent = RunRequest(new { operation = "item-send", database = charsPath, account = "alice", name = "RelWitch", item = rareRing, previewKey }, out code);
        Assert.Equal(0, code);
        Assert.True(sent.GetProperty("ok").GetBoolean());
        Assert.False(sent.GetProperty("preview").GetBoolean());
        string backupPath = sent.GetProperty("backup").GetString()!;
        Assert.True(File.Exists(backupPath));
        using (var backupDoc = JsonDocument.Parse(File.ReadAllText(backupPath)))
        {
            Assert.Equal("relational", backupDoc.RootElement.GetProperty("format").GetString());
            Assert.Equal(saveId, backupDoc.RootElement.GetProperty("saveId").GetInt64());
            Assert.Equal(3, backupDoc.RootElement.GetProperty("items").GetArrayLength());
            Assert.Equal("""{"future":true}""", backupDoc.RootElement.GetProperty("characterSave").GetProperty("unknown").GetString());
        }

        // Verify relational rows written cleanly and existing rows untouched.
        WithDb(charsPath, db =>
        {
            // Stale legacy characters table remained untouched.
            Assert.Equal("""{"Inventories":{"0":[]}}""", Scalar(db, "SELECT save FROM characters WHERE name='RelWitch'"));
            // Existing character_saves row untouched.
            Assert.Equal("""{"future":true}""", Scalar(db, "SELECT unknown FROM character_saves WHERE id=$s", ("$s", saveId)));
            // Existing item's newer columns preserved.
            Assert.Equal(12L, Scalar(db, "SELECT memory_strands FROM items WHERE character=$s AND placement=4", ("$s", saveId)));
            // New item row has placement id 10 (max below 0x40000000 was 9), ord 2, x=0, y=1, item_level=75, corrupted=1.
            using var cmd = db.CreateCommand();
            cmd.CommandText = "SELECT id, ord, placement, x, y, type, item_level, quality, rarity, identified, has_mods, corrupted FROM items WHERE character=$s AND placement=10";
            cmd.Parameters.AddWithValue("$s", saveId);
            using var r = cmd.ExecuteReader();
            Assert.True(r.Read());
            long newItemId = r.GetInt64(0);
            Assert.Equal(2L, r.GetInt64(1));
            Assert.Equal(10L, r.GetInt64(2));
            Assert.Equal(0L, r.GetInt64(3));
            Assert.Equal(1L, r.GetInt64(4));
            Assert.Equal((long)RingHash, r.GetInt64(5));
            Assert.Equal(75L, r.GetInt64(6));
            Assert.Equal(20L, r.GetInt64(7));
            Assert.Equal(2L, r.GetInt64(8)); // Rare
            Assert.Equal(1L, r.GetInt64(9));
            Assert.Equal(1L, r.GetInt64(10));
            Assert.Equal(1L, r.GetInt64(11));

            // Mod row written to item_mods.
            using var modCmd = db.CreateCommand();
            modCmd.CommandText = "SELECT mod, section, stat_values FROM item_mods WHERE item=$id ORDER BY ord";
            modCmd.Parameters.AddWithValue("$id", newItemId);
            using var mr = modCmd.ExecuteReader();
            Assert.True(mr.Read());
            Assert.Equal("Strength1", mr.GetString(0));
            Assert.Equal(5L, mr.GetInt64(1)); // Explicit
            Assert.Equal("[15]", mr.GetString(2));
            Assert.False(mr.Read());
        });
        Assert.Equal(authBefore, Sha256(authPath));
    }

    [Fact]
    public void Relational_item_send_creates_main_inventory_row_detects_concurrent_changes_and_rolls_back_on_error()
    {
        var (charsPath, _) = CreateSplitRelationalDb();
        long saveId = 0;
        WithDb(charsPath, db =>
        {
            Exec(db, """
                INSERT INTO account_characters(id, account_id, name, class, level, league, area_id, created_utc, last_played_utc, last_town, portrait)
                VALUES($id, $acct, 'FreshChar', 3, 20, 'Standard', '1_1_town', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '1_1_town', 0)
                """, ("$id", Guid.NewGuid().ToString()), ("$acct", _accountId));
            // Save has inventory 2 only (no main inventory 0 row yet).
            saveId = (long)Scalar(db, "INSERT INTO character_saves(name, has_inventories) VALUES('FreshChar', 1) RETURNING id")!;
            Exec(db, "INSERT INTO character_inventories VALUES($s, 2)", ("$s", saveId));
        });

        string item = "Rarity: MAGIC\nIron Ring of the Brute\n+12 to Strength";
        var preview = RunRequest(new { operation = "item-preview", database = charsPath, account = "alice", name = "FreshChar", item }, out int code);
        Assert.Equal(0, code);
        string key = preview.GetProperty("previewKey").GetString()!;

        // Concurrent modification to character_saves is caught.
        WithDb(charsPath, db => Exec(db, "UPDATE character_saves SET experience = 999 WHERE id = $s", ("$s", saveId)));
        var stale = RunRequest(new { operation = "item-send", database = charsPath, account = "alice", name = "FreshChar", item, previewKey = key }, out code);
        Assert.Equal(1, code);
        Assert.Contains("Preview again", stale.GetProperty("error").GetString());

        // Re-preview and test atomic rollback on item_mods failure.
        preview = RunRequest(new { operation = "item-preview", database = charsPath, account = "alice", name = "FreshChar", item }, out code);
        key = preview.GetProperty("previewKey").GetString()!;
        WithDb(charsPath, db => Exec(db, "CREATE TRIGGER fail_mod BEFORE INSERT ON item_mods BEGIN SELECT RAISE(FAIL, 'intentional'); END"));
        var failed = RunRequest(new { operation = "item-send", database = charsPath, account = "alice", name = "FreshChar", item, previewKey = key }, out code);
        Assert.Equal(1, code);
        Assert.DoesNotContain("intentional", failed.GetProperty("error").GetString());
        WithDb(charsPath, db =>
        {
            Assert.Equal(0L, Scalar(db, "SELECT count(*) FROM items WHERE character = $s", ("$s", saveId)));
            Assert.Equal(0L, Scalar(db, "SELECT count(*) FROM character_inventories WHERE save = $s AND inventory = 0", ("$s", saveId)));
            Exec(db, "DROP TRIGGER fail_mod");
        });

        // Now send succeeds and inserts (saveId, 0) into character_inventories.
        var sent = RunRequest(new { operation = "item-send", database = charsPath, account = "alice", name = "FreshChar", item, previewKey = key }, out code);
        Assert.Equal(0, code);
        Assert.True(sent.GetProperty("ok").GetBoolean());
        WithDb(charsPath, db =>
        {
            Assert.Equal(1L, Scalar(db, "SELECT count(*) FROM character_inventories WHERE save = $s AND inventory = 0", ("$s", saveId)));
            Assert.Equal(1L, Scalar(db, "SELECT count(*) FROM items WHERE character = $s AND inventory = 0", ("$s", saveId)));
            Assert.Equal(1L, Scalar(db, "SELECT count(*) FROM item_mods"));
        });
    }

    [Fact]
    public void Legacy_saves_db_item_send_still_works_end_to_end()
    {
        string dbPath = CreateLegacyDb();
        WithDb(dbPath, db =>
        {
            Exec(db, "INSERT INTO account_characters VALUES($id, $acct, 'OldWitch', '2026-01-01', $json)",
                ("$id", Guid.NewGuid().ToString()), ("$acct", _accountId),
                ("$json", """{"Name":"OldWitch","Level":85,"League":"Standard","LastPlayedUtc":"2026-01-01T00:00:00Z"}"""));
            Exec(db, "INSERT INTO characters VALUES('OldWitch', $save)",
                ("$save", "{\"Inventories\":{\"0\":[{\"Id\":4,\"X\":0,\"Y\":0,\"Item\":{\"Type\":" + RingHash + "}}]},\"Passives\":[11],\"FutureField\":true}"));
        });

        var preview = RunRequest(new { operation = "item-preview", database = dbPath, account = "alice", name = "OldWitch", item = "Rarity: NORMAL\nIron Ring" }, out int code);
        Assert.Equal(0, code);
        Assert.Equal(0, preview.GetProperty("x").GetInt32());
        Assert.Equal(1, preview.GetProperty("y").GetInt32());

        var sent = RunRequest(new { operation = "item-send", database = dbPath, account = "alice", name = "OldWitch", item = "Rarity: NORMAL\nIron Ring",
            previewKey = preview.GetProperty("previewKey").GetString() }, out code);
        Assert.Equal(0, code);
        Assert.True(sent.GetProperty("ok").GetBoolean());
        WithDb(dbPath, db =>
        {
            string saved = (string)Scalar(db, "SELECT save FROM characters WHERE name='OldWitch'")!;
            using var doc = JsonDocument.Parse(saved);
            Assert.Equal(2, doc.RootElement.GetProperty("Inventories").GetProperty("0").GetArrayLength());
            Assert.True(doc.RootElement.GetProperty("FutureField").GetBoolean());
        });
    }

    [Fact]
    public void Unique_item_catalogue_is_read_from_world_db_when_present_beside_characters_db()
    {
        var (charsPath, _) = CreateSplitRelationalDb();
        WithDb(Path.Combine(_data, "world.db"), db =>
        {
            Exec(db, """
                CREATE TABLE unique_items(name TEXT NOT NULL, base_type TEXT NOT NULL, item_level INTEGER NOT NULL DEFAULT 86,
                    corrupted INTEGER NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(name, base_type)) STRICT;
                CREATE TABLE unique_item_mods(name TEXT NOT NULL, base_type TEXT NOT NULL, implicit INTEGER NOT NULL,
                    ord INTEGER NOT NULL, mod TEXT NOT NULL, PRIMARY KEY(name, base_type, implicit, ord)) STRICT;
                INSERT INTO unique_items VALUES('FixtureUnique', 'Metadata/Items/Ring', 70, 0, 1);
                INSERT INTO unique_item_mods VALUES('FixtureUnique', 'Metadata/Items/Ring', 0, 0, 'DexterityUnique');
                INSERT INTO unique_item_mods VALUES('FixtureUnique', 'Metadata/Items/Ring', 0, 1, 'SpecialUniqueMod');
                """);
        });
        WithDb(charsPath, db =>
        {
            Exec(db, """
                INSERT INTO account_characters(id, account_id, name, class, level, league, area_id, created_utc, last_played_utc, last_town, portrait)
                VALUES($id, $acct, 'RelWitch', 3, 90, 'Standard', '1_1_town', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '1_1_town', 0)
                """, ("$id", Guid.NewGuid().ToString()), ("$acct", _accountId));
            long saveId = (long)Scalar(db, "INSERT INTO character_saves(name, has_inventories) VALUES('RelWitch', 1) RETURNING id")!;
            Exec(db, "INSERT INTO character_inventories VALUES($s, 0)", ("$s", saveId));
        });

        string uniqueRing = "Rarity: UNIQUE\nFixtureUnique\nIron Ring\n+33 to Dexterity\nUnrecognized unique line";
        var preview = RunRequest(new { operation = "item-preview", database = charsPath, account = "alice", name = "RelWitch", item = uniqueRing }, out int code);
        Assert.Equal(0, code);
        Assert.False(preview.GetProperty("incompleteUnique").GetBoolean());
        var sent = RunRequest(new { operation = "item-send", database = charsPath, account = "alice", name = "RelWitch", item = uniqueRing,
            previewKey = preview.GetProperty("previewKey").GetString() }, out code);
        Assert.Equal(0, code);

        WithDb(charsPath, db =>
        {
            using var cmd = db.CreateCommand();
            cmd.CommandText = "SELECT mod, stat_values FROM item_mods ORDER BY ord";
            using var r = cmd.ExecuteReader();
            Assert.True(r.Read());
            Assert.Equal("DexterityUnique", r.GetString(0));
            Assert.Equal("[33]", r.GetString(1));
            Assert.True(r.Read());
            Assert.Equal("SpecialUniqueMod", r.GetString(0));
            Assert.Equal("[1]", r.GetString(1));
            Assert.False(r.Read());
        });
    }

    // ---------------------------------------------------------------- Export to LocalExile Tests

    const string BuildXml = """
        <PathOfBuilding>
          <Build level="20" className="Witch"/>
          <Tree activeSpec="1">
            <Spec nodes="11,12" masteryEffects="{12,500}" classId="3" ascendClassId="0" treeVersion="3_29"/>
          </Tree>
          <Items activeItemSet="1">
            <Item id="1">
        Rarity: MAGIC
        Plate Vest of the Brute
        Sockets: B-B
        +15 to Strength
            </Item>
            <ItemSet id="1">
              <Slot name="Body Armour" itemId="1"/>
            </ItemSet>
          </Items>
          <Skills activeSkillSet="1">
            <SkillSet id="1">
              <Skill slot="Body Armour" enabled="true">
                <Gem nameSpec="Fireball" level="1" quality="0" enabled="true"/>
              </Skill>
            </SkillSet>
          </Skills>
        </PathOfBuilding>
        """;

    [Fact]
    public void Export_to_LocalExile_writes_relational_tables_and_preserves_backups_and_rollback()
    {
        var (charsPath, authPath) = CreateSplitRelationalDb();
        string authBefore = Sha256(authPath);
        // A deleted save + stale legacy row with the same name must not block exporting a new character of that name.
        WithDb(charsPath, db =>
        {
            Exec(db, "INSERT INTO character_saves(name, deleted_utc, has_inventories) VALUES('NewRelWitch', '2026-01-01T00:00:00Z', 1)");
            Exec(db, "INSERT INTO characters VALUES('NewRelWitch', '{}')");
        });

        var preview = RunRequest(new { operation = "preview", database = charsPath, account = "alice", name = "NewRelWitch", league = "Standard", code = BuildXml }, out int code);
        Assert.Equal(0, code);
        Assert.True(preview.GetProperty("preview").GetBoolean());
        Assert.Equal(1, preview.GetProperty("items").GetInt32());
        Assert.Equal(1, preview.GetProperty("gems").GetInt32());
        Assert.Equal(2, preview.GetProperty("passives").GetInt32());
        Assert.Equal(1, preview.GetProperty("masteries").GetInt32());
        string previewKey = preview.GetProperty("previewKey").GetString()!;

        // Trigger failure on item_mods rolls back account_characters, character_saves, and items atomically.
        WithDb(charsPath, db => Exec(db, "CREATE TRIGGER fail_export_mod BEFORE INSERT ON item_mods BEGIN SELECT RAISE(FAIL, 'intentional'); END"));
        var failed = RunRequest(new { operation = "export", database = charsPath, account = "alice", name = "NewRelWitch", league = "Standard", code = BuildXml, previewKey }, out code);
        Assert.Equal(1, code);
        Assert.DoesNotContain("intentional", failed.GetProperty("error").GetString());
        WithDb(charsPath, db =>
        {
            Assert.Equal(0L, Scalar(db, "SELECT count(*) FROM account_characters"));
            Assert.Equal(0L, Scalar(db, "SELECT count(*) FROM character_saves WHERE deleted_utc IS NULL"));
            Assert.Equal(0L, Scalar(db, "SELECT count(*) FROM items"));
            Exec(db, "DROP TRIGGER fail_export_mod");
        });

        // Successful export commits all relational tables and writes backup + report.
        var exported = RunRequest(new { operation = "export", database = charsPath, account = "alice", name = "NewRelWitch", league = "Standard", code = BuildXml, previewKey }, out code);
        Assert.Equal(0, code);
        Assert.True(exported.GetProperty("ok").GetBoolean());
        Assert.False(exported.GetProperty("preview").GetBoolean());
        string backupPath = exported.GetProperty("backup").GetString()!;
        Assert.True(File.Exists(backupPath));
        Assert.True(File.Exists(exported.GetProperty("compatibilityReport").GetString()!));

        // Backup has prior state without the new character.
        WithDb(backupPath, backup =>
        {
            Assert.Equal(0L, Scalar(backup, "SELECT count(*) FROM account_characters"));
            Assert.Equal(0L, Scalar(backup, "SELECT count(*) FROM character_saves WHERE deleted_utc IS NULL"));
        });

        // Live characters.db has columnar account_characters + relational character_saves + children + items + socketed gem + mods.
        WithDb(charsPath, db =>
        {
            using (var c = db.CreateCommand())
            {
                c.CommandText = "SELECT account_id, name, class, level, league, area_id, last_town, portrait, portrait_frame FROM account_characters";
                using var r = c.ExecuteReader();
                Assert.True(r.Read());
                Assert.Equal(_accountId, r.GetString(0));
                Assert.Equal("NewRelWitch", r.GetString(1));
                Assert.Equal(3L, r.GetInt64(2)); // Witch
                Assert.Equal(20L, r.GetInt64(3));
                Assert.Equal("Standard", r.GetString(4));
                Assert.Equal("1_1_town", r.GetString(5));
                Assert.Equal("1_1_town", r.GetString(6));
                Assert.Equal(0L, r.GetInt64(7));
                Assert.Equal(0L, r.GetInt64(8));
            }

            long saveId = (long)Scalar(db, "SELECT id FROM character_saves WHERE name='NewRelWitch' AND deleted_utc IS NULL")!;
            Assert.Equal(123000L, Scalar(db, "SELECT experience FROM character_saves WHERE id=$s", ("$s", saveId)));
            Assert.Equal("[11,12]", Scalar(db, "SELECT passives FROM character_saves WHERE id=$s", ("$s", saveId)));
            Assert.Equal("[\"1_1_town\"]", Scalar(db, "SELECT waypoints FROM character_saves WHERE id=$s", ("$s", saveId)));
            Assert.Equal(1L, Scalar(db, "SELECT count(*) FROM character_inventories WHERE save=$s AND inventory=1", ("$s", saveId)));
            Assert.Equal(500L, Scalar(db, "SELECT effect FROM character_masteries WHERE save=$s AND node=12", ("$s", saveId)));
            Assert.Equal("Action/Move", Scalar(db, "SELECT skill FROM character_skill_bar WHERE save=$s AND slot=0", ("$s", saveId)));
            Assert.Equal(1L, Scalar(db, "SELECT count(*) FROM character_skill_bar WHERE save=$s AND skill='Fireball'", ("$s", saveId)));

            long vestId = (long)Scalar(db, "SELECT id FROM items WHERE character=$s AND role='placed' AND inventory=1", ("$s", saveId))!;
            Assert.Equal((long)VestHash, Scalar(db, "SELECT type FROM items WHERE id=$id", ("$id", vestId)));
            Assert.Equal("[3,3]", Scalar(db, "SELECT sockets FROM items WHERE id=$id", ("$id", vestId)));
            Assert.Equal("[2]", Scalar(db, "SELECT links FROM items WHERE id=$id", ("$id", vestId)));

            // Socketed gem linked via parent = vestId, ord = 0.
            Assert.Equal((long)GemHash, Scalar(db, "SELECT type FROM items WHERE character=$s AND role='socketed' AND parent=$p AND ord=0",
                ("$s", saveId), ("$p", vestId)));
            // Vest modifier persisted in item_mods.
            Assert.Equal("Strength1", Scalar(db, "SELECT mod FROM item_mods WHERE item=$id AND ord=0", ("$id", vestId)));
        });

        // Duplicate name is now refused case-insensitively.
        var dup = RunRequest(new { operation = "preview", database = charsPath, account = "alice", name = "newrelwitch", league = "Standard", code = BuildXml }, out code);
        Assert.Equal(1, code);
        Assert.Contains("already exists", dup.GetProperty("error").GetString());

        // auth.db was never modified.
        Assert.Equal(authBefore, Sha256(authPath));
    }

    [Fact]
    public void Split_database_before_relational_migration_writes_columnar_metadata_and_json_save()
    {
        var (charsPath, _) = CreateSplitRelationalDb(Path.Combine(_root, "pre-migrate"), relationalMeta: false);
        var preview = RunRequest(new { operation = "preview", database = charsPath, dataFolder = _data, account = "alice", name = "PreMigrateWitch", league = "Standard", code = BuildXml }, out int code);
        Assert.Equal(0, code);
        var exported = RunRequest(new { operation = "export", database = charsPath, dataFolder = _data, account = "alice", name = "PreMigrateWitch", league = "Standard", code = BuildXml,
            previewKey = preview.GetProperty("previewKey").GetString() }, out code);
        Assert.Equal(0, code);

        WithDb(charsPath, db =>
        {
            Assert.Equal(1L, Scalar(db, "SELECT count(*) FROM account_characters WHERE name='PreMigrateWitch' AND level=20"));
            Assert.Equal(1L, Scalar(db, "SELECT count(*) FROM characters WHERE name='PreMigrateWitch'"));
            Assert.Equal(0L, Scalar(db, "SELECT count(*) FROM character_saves"));
        });
    }

    [Fact]
    public void Legacy_saves_db_export_still_works_end_to_end()
    {
        string dbPath = CreateLegacyDb();
        var preview = RunRequest(new { operation = "preview", database = dbPath, account = "alice", name = "LegacyWitch", league = "Standard", code = BuildXml }, out int code);
        Assert.Equal(0, code);
        var exported = RunRequest(new { operation = "export", database = dbPath, account = "alice", name = "LegacyWitch", league = "Standard", code = BuildXml,
            previewKey = preview.GetProperty("previewKey").GetString() }, out code);
        Assert.Equal(0, code);

        WithDb(dbPath, db =>
        {
            Assert.Equal(1L, Scalar(db, "SELECT count(*) FROM account_characters WHERE name='LegacyWitch'"));
            Assert.Equal(1L, Scalar(db, "SELECT count(*) FROM characters WHERE name='LegacyWitch'"));
        });
    }

    [Fact]
    public void FormatFileUri_escapes_special_characters_for_windows_and_unix_paths()
    {
        Assert.Equal("file:///C:/Users/Test %231/100%25%3F/auth.db?mode=ro",
            SaveDatabase.FormatFileUri(@"C:\Users\Test #1\100%?\auth.db", readOnly: true));
        Assert.Equal("file:///home/user/copy %231/auth.db?mode=ro",
            SaveDatabase.FormatFileUri("/home/user/copy #1/auth.db", readOnly: true));
        Assert.Equal("file:///C:/LocalExile/data/characters.db",
            SaveDatabase.FormatFileUri(@"C:\LocalExile\data\characters.db", readOnly: false));
    }

    [Fact]
    public void Relational_item_send_refuses_ruthless_deleted_only_and_full_inventory_characters()
    {
        var (charsPath, _) = CreateSplitRelationalDb();
        WithDb(charsPath, db =>
        {
            Exec(db, """
                INSERT INTO account_characters(id, account_id, name, class, level, league, area_id, created_utc, last_played_utc, last_town, portrait)
                VALUES($id1, $acct, 'RuthlessChar', 3, 50, 'Ruthless Standard', '1_1_town', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '1_1_town', 0),
                      ($id2, $acct, 'DeletedOnly', 3, 50, 'Standard', '1_1_town', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '1_1_town', 0),
                      ($id3, $acct, 'FullBag', 3, 50, 'Standard', '1_1_town', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '1_1_town', 0)
                """, ("$id1", Guid.NewGuid().ToString()), ("$id2", Guid.NewGuid().ToString()), ("$id3", Guid.NewGuid().ToString()), ("$acct", _accountId));
            Exec(db, "INSERT INTO character_saves(name, deleted_utc, has_inventories) VALUES('DeletedOnly', '2026-01-01T00:00:00Z', 1)");
            long fullId = (long)Scalar(db, "INSERT INTO character_saves(name, has_inventories) VALUES('FullBag', 1) RETURNING id")!;
            Exec(db, "INSERT INTO character_inventories VALUES($s, 0)", ("$s", fullId));
            for (int i = 0; i < 60; i++)
            {
                Exec(db, """
                    INSERT INTO items(character, inventory, role, ord, placement, x, y, type, item_level, quality, charges, stack_size,
                        gem_experience, rarity, identified, has_mods, gem_variant, corrupted, fractured, mirrored, gem_flags,
                        defence_base_roll, influences, split, synthesised, foreseeing, foresee_seed)
                    VALUES($s, 0, 'placed', $ord, $pl, $x, $y, $ring, 1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
                    """, ("$s", fullId), ("$ord", i), ("$pl", i + 1), ("$x", i % 12), ("$y", i / 12), ("$ring", (long)RingHash));
            }
        });

        var ruthless = RunRequest(new { operation = "item-preview", database = charsPath, account = "alice", name = "RuthlessChar", item = "Rarity: NORMAL\nIron Ring" }, out int code);
        Assert.Equal(1, code);
        Assert.Contains("Ruthless", ruthless.GetProperty("error").GetString());

        var deletedOnly = RunRequest(new { operation = "item-preview", database = charsPath, account = "alice", name = "DeletedOnly", item = "Rarity: NORMAL\nIron Ring" }, out code);
        Assert.Equal(1, code);
        Assert.Contains("no save yet", deletedOnly.GetProperty("error").GetString());

        var fullBag = RunRequest(new { operation = "item-preview", database = charsPath, account = "alice", name = "FullBag", item = "Rarity: NORMAL\nIron Ring" }, out code);
        Assert.Equal(1, code);
        Assert.Contains("no free 1x1", fullBag.GetProperty("error").GetString());
    }

    [Fact]
    public void Relational_write_persists_tattoos_and_tattoo_keystones()
    {
        var (charsPath, _) = CreateSplitRelationalDb();
        using var session = SaveDatabase.Open(charsPath, write: true);
        using var tx = session.Connection.BeginTransaction(deferred: false);
        var save = new CharacterSaves.Save(
            Inventories: new Dictionary<byte, List<CharacterSaves.SavedPlacement>>(),
            SkillBar: new Dictionary<int, string> { [0] = "Action/Move" },
            Experience: 123000,
            Passives: [11],
            Waypoints: ["1_1_town"],
            Visited: ["1_1_town"],
            ExtraPassivePoints: 2,
            MasteryEffects: new Dictionary<ushort, ushort>(),
            Tattoos: new Dictionary<ushort, string> { [11] = "Tattoo of the Ramako Shaman" },
            TattooKeystones: new Dictionary<ushort, ushort> { [11] = 4200 });
        SaveDatabase.WriteNewCharacter(session.Connection, session.Layout, tx, Guid.NewGuid().ToString(), _accountId,
            "TattooWitch", GameServer.Core.Accounts.CharacterClass.Witch, 20, "Standard", "2026-11-20T00:00:00Z", save, "{}");
        tx.Commit();

        WithDb(charsPath, db =>
        {
            long saveId = (long)Scalar(db, "SELECT id FROM character_saves WHERE name='TattooWitch' AND deleted_utc IS NULL")!;
            Assert.Equal(2L, Scalar(db, "SELECT extra_passive_points FROM character_saves WHERE id=$s", ("$s", saveId)));
            Assert.Equal("Tattoo of the Ramako Shaman", Scalar(db, "SELECT tattoo FROM character_tattoos WHERE save=$s AND node=11", ("$s", saveId)));
            Assert.Equal(4200L, Scalar(db, "SELECT keystone FROM character_tattoo_keystones WHERE save=$s AND node=11", ("$s", saveId)));
        });
    }
}
