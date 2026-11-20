using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using GameServer.Core.Accounts;
using GameServer.Core.Protocol.Instance;
using Microsoft.Data.Sqlite;

internal sealed record SaveLayout(
    string AccountsSchema,
    string? AuthDatabasePath,
    bool ColumnarCharacters,
    bool RelationalSaves);

internal sealed class SaveDatabaseSession(SqliteConnection connection, SaveLayout layout) : IDisposable
{
    public SqliteConnection Connection { get; } = connection;
    public SaveLayout Layout { get; } = layout;
    public void Dispose() => Connection.Dispose();
}

/// <summary>
/// Reads and writes both the legacy pre-split <c>saves.db</c> layout and the split <c>characters.db</c> + <c>auth.db</c>
/// relational save layout without modifying any schema.
/// </summary>
static class SaveDatabase
{
    internal sealed record CharacterSummary(string Name, int Level, string League);
    internal sealed record CharacterTarget(string Name, string League, DateTimeOffset LastPlayed);
    internal sealed record PlacedItem(byte Inventory, uint Id, byte X, byte Y, uint Type);
    internal sealed record CharacterSaveSnapshot(long? SaveId, string SnapshotJson, IReadOnlyList<PlacedItem> Placed, int NextMainOrd);

    static readonly string[] AccountColumns = ["id", "name", "account"];
    static readonly string[] LegacyAccountCharacterColumns = ["id", "account_id", "name", "created_utc", "character"];
    static readonly string[] ColumnarAccountCharacterColumns =
        ["id", "account_id", "name", "class", "level", "league", "area_id", "created_utc", "last_played_utc", "last_town", "portrait"];
    static readonly string[] LegacyCharacterSaveColumns = ["name", "save"];
    static readonly (string Table, string[] Columns)[] RelationalTables =
    [
        ("character_saves", ["id", "name", "deleted_utc", "has_inventories", "experience", "passives", "waypoints", "visited", "extra_passive_points"]),
        ("character_inventories", ["save", "inventory"]),
        ("character_skill_bar", ["save", "slot", "skill"]),
        ("character_masteries", ["save", "node", "effect"]),
        ("character_tattoos", ["save", "node", "tattoo"]),
        ("character_tattoo_keystones", ["save", "node", "keystone"]),
        ("items", ["id", "character", "stash", "inventory", "role", "parent", "ord", "placement", "x", "y",
            "type", "item_level", "quality", "charges", "stack_size", "sockets", "links", "gem_experience",
            "rarity", "identified", "has_mods", "name", "gem_variant", "corrupted", "fractured", "mirrored",
            "gem_flags", "visual", "defence_base_roll", "influences", "split", "synthesised", "foreseeing", "foresee_seed"]),
        ("item_mods", ["item", "ord", "mod", "section", "stat_values"]),
    ];

    public static SaveDatabaseSession Open(string database, bool write)
    {
        var connection = ExportCommand.Open(database, write);
        try
        {
            var layout = ValidateAndAttach(connection, database);
            if (write && layout.RelationalSaves)
            {
                using var fk = connection.CreateCommand();
                fk.CommandText = "PRAGMA foreign_keys=ON";
                fk.ExecuteNonQuery();
            }
            return new SaveDatabaseSession(connection, layout);
        }
        catch
        {
            connection.Dispose();
            throw;
        }
    }

    public static SaveLayout ValidateAndAttach(SqliteConnection connection, string? databasePath = null)
    {
        var accountCharacterCols = TableColumns(connection, "main", "account_characters");
        var mainAccountCols = TableColumns(connection, "main", "accounts");
        if (accountCharacterCols.Count == 0)
        {
            string hint = mainAccountCols.Count > 0 ? " If you selected auth.db, choose characters.db instead." : "";
            throw Incompatible($"missing table 'account_characters'.{hint}");
        }

        bool columnarCharacters = !accountCharacterCols.Contains("character");
        RequireColumns("account_characters", accountCharacterCols,
            columnarCharacters ? ColumnarAccountCharacterColumns : LegacyAccountCharacterColumns);

        string accountsSchema;
        string? authPath = null;
        if (mainAccountCols.Count > 0)
        {
            RequireColumns("accounts", mainAccountCols, AccountColumns);
            accountsSchema = "main";
        }
        else
        {
            var authCols = HasAttachedDatabase(connection, "auth")
                ? TableColumns(connection, "auth", "accounts")
                : new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            if (authCols.Count == 0)
            {
                string source = databasePath ?? connection.DataSource;
                if (string.IsNullOrWhiteSpace(source))
                    throw Incompatible("missing table 'accounts'.");
                authPath = ResolveAuthPath(source);
                AttachReadOnly(connection, authPath, "auth");
                authCols = TableColumns(connection, "auth", "accounts");
                if (authCols.Count == 0)
                    throw Incompatible($"missing table 'auth.accounts' in companion database '{authPath}'.");
            }
            RequireColumns("auth.accounts", authCols, AccountColumns);
            accountsSchema = "auth";
        }

        bool hasCharacters = TableColumns(connection, "main", "characters").Count > 0;
        bool hasCharacterSaves = TableColumns(connection, "main", "character_saves").Count > 0;
        bool hasRelationalMeta = HasRelationalSavesMeta(connection);
        bool relationalSaves = hasRelationalMeta || (!hasCharacters && hasCharacterSaves);

        if (relationalSaves)
        {
            foreach (var (table, required) in RelationalTables)
            {
                var columns = TableColumns(connection, "main", table);
                if (columns.Count == 0)
                    throw Incompatible($"missing table '{table}'.");
                RequireColumns(table, columns, required);
            }
        }
        else
        {
            var characterCols = TableColumns(connection, "main", "characters");
            if (characterCols.Count == 0)
                throw Incompatible("missing table 'characters' (and 'character_saves').");
            RequireColumns("characters", characterCols, LegacyCharacterSaveColumns);
        }

        return new SaveLayout(accountsSchema, authPath, columnarCharacters, relationalSaves);
    }

    internal static string AuthPathFor(string charactersPath)
    {
        string folder = Path.GetDirectoryName(charactersPath) ?? "";
        string name = Path.GetFileNameWithoutExtension(charactersPath);
        return Path.Combine(folder, name.Equals("characters", StringComparison.OrdinalIgnoreCase) ? "auth.db" : name + "-auth.db");
    }

    internal static string ResolveAuthPath(string database)
    {
        string full = Path.GetFullPath(database);
        string folder = Path.GetDirectoryName(full) ?? "";
        string stem = Path.GetFileNameWithoutExtension(full);
        var candidates = new List<string>();
        void AddCandidate(string? candidate)
        {
            if (string.IsNullOrWhiteSpace(candidate)) return;
            if (!candidates.Any(c => c.Equals(candidate, StringComparison.OrdinalIgnoreCase)))
                candidates.Add(candidate);
        }

        string? envChars = Environment.GetEnvironmentVariable("Game_CHARACTERS_DB");
        string? envAuth = Environment.GetEnvironmentVariable("Game_AUTH_DB");
        if (!string.IsNullOrWhiteSpace(envAuth) && !string.IsNullOrWhiteSpace(envChars)
            && Path.IsPathFullyQualified(envChars)
            && string.Equals(Path.GetFullPath(envChars), full, StringComparison.OrdinalIgnoreCase))
        {
            AddCandidate(ResolveEnvAuthCandidate(envAuth, folder));
        }

        AddCandidate(AuthPathFor(full));
        if (!stem.Equals("characters", StringComparison.OrdinalIgnoreCase))
            AddCandidate(Path.Combine(folder, "auth.db"));

        if (!string.IsNullOrWhiteSpace(envAuth))
            AddCandidate(ResolveEnvAuthCandidate(envAuth, folder));

        foreach (string candidate in candidates)
        {
            if (candidate.StartsWith("\\\\", StringComparison.Ordinal))
                throw new ArgumentException("Use a local accounts database, not a network drive.");
            if (File.Exists(candidate))
                return ExportCommand.ExistingLocalFile(candidate);
        }

        throw Incompatible($"table 'accounts' is not in this database and no companion auth database was found (checked: {string.Join(", ", candidates)}; or set Game_AUTH_DB).");
    }

    static string? ResolveEnvAuthCandidate(string envAuth, string folder)
    {
        if (Path.IsPathFullyQualified(envAuth)) return envAuth;
        string inFolder = Path.Combine(folder, envAuth);
        if (File.Exists(inFolder)) return inFolder;
        if (Path.GetDirectoryName(folder) is { Length: > 0 } parent)
        {
            string inParent = Path.Combine(parent, envAuth);
            if (File.Exists(inParent)) return inParent;
        }
        return inFolder;
    }

    internal static string ToFileUri(string path, bool readOnly = false) =>
        FormatFileUri(Path.GetFullPath(path), readOnly);

    internal static string FormatFileUri(string fullPath, bool readOnly = false)
    {
        string normalized = fullPath.Replace('\\', '/');
        string escaped = normalized.Replace("%", "%25", StringComparison.Ordinal)
            .Replace("?", "%3F", StringComparison.Ordinal)
            .Replace("#", "%23", StringComparison.Ordinal);
        string uri = escaped.StartsWith('/') ? $"file://{escaped}" : $"file:///{escaped}";
        return readOnly ? uri + "?mode=ro" : uri;
    }

    static void AttachReadOnly(SqliteConnection connection, string path, string alias)
    {
        using var c = connection.CreateCommand();
        c.CommandText = $"ATTACH DATABASE $uri AS {alias}";
        c.Parameters.AddWithValue("$uri", ToFileUri(path, readOnly: true));
        c.ExecuteNonQuery();
    }

    static bool HasAttachedDatabase(SqliteConnection connection, string alias)
    {
        using var c = connection.CreateCommand();
        c.CommandText = "PRAGMA database_list";
        using var rows = c.ExecuteReader();
        while (rows.Read())
            if (rows.GetString(1).Equals(alias, StringComparison.OrdinalIgnoreCase)) return true;
        return false;
    }

    static HashSet<string> TableColumns(SqliteConnection connection, string schema, string table)
    {
        using var c = connection.CreateCommand();
        c.CommandText = $"PRAGMA {schema}.table_info({table})";
        using var rows = c.ExecuteReader();
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        while (rows.Read()) names.Add(rows.GetString(1));
        return names;
    }

    static bool HasRelationalSavesMeta(SqliteConnection connection)
    {
        var metaCols = TableColumns(connection, "main", "meta");
        if (!metaCols.Contains("key") || !metaCols.Contains("value")) return false;
        using var c = connection.CreateCommand();
        c.CommandText = "SELECT value FROM meta WHERE key = 'relational_saves'";
        return c.ExecuteScalar() is string { Length: > 0 };
    }

    static void RequireColumns(string table, HashSet<string> actual, string[] required)
    {
        var missing = required.Where(c => !actual.Contains(c)).ToArray();
        if (missing.Length > 0)
            throw Incompatible($"table '{table}' is missing column(s): {string.Join(", ", missing)}.");
    }

    static ArgumentException Incompatible(string detail) =>
        new($"This is not a compatible LocalExile save database: {detail} No schema changes were made.");

    public static List<ExportCommand.Destination> Accounts(SqliteConnection connection, SaveLayout layout)
    {
        using var c = connection.CreateCommand();
        c.CommandText = $"SELECT id, name FROM {layout.AccountsSchema}.accounts ORDER BY name";
        using var rows = c.ExecuteReader();
        var result = new List<ExportCommand.Destination>();
        while (rows.Read())
        {
            if (result.Count == 1024) throw new ArgumentException("Too many accounts to inspect.");
            result.Add(new(rows.GetString(0), rows.GetString(1)));
        }
        return result;
    }

    public static bool VerifyAccount(SqliteConnection connection, SaveLayout layout, string accountId, string accountName, SqliteTransaction transaction)
    {
        using var c = connection.CreateCommand();
        c.Transaction = transaction;
        c.CommandText = $"SELECT id FROM {layout.AccountsSchema}.accounts WHERE id = $value AND name = $name COLLATE NOCASE";
        c.Parameters.AddWithValue("$value", accountId);
        c.Parameters.AddWithValue("$name", accountName);
        return c.ExecuteScalar() as string == accountId;
    }

    public static string[] Leagues(SqliteConnection connection, SaveLayout layout)
    {
        var leagues = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "Standard" };
        using var c = connection.CreateCommand();
        if (layout.ColumnarCharacters)
        {
            c.CommandText = "SELECT DISTINCT league FROM account_characters WHERE league IS NOT NULL AND league <> '' LIMIT 10000";
            using var rows = c.ExecuteReader();
            while (rows.Read()) leagues.Add(rows.GetString(0));
        }
        else
        {
            c.CommandText = "SELECT character FROM account_characters LIMIT 10000";
            using var rows = c.ExecuteReader();
            while (rows.Read())
            {
                using var d = JsonDocument.Parse(rows.GetString(0));
                if (d.RootElement.TryGetProperty("League", out var league) && league.GetString() is { Length: > 0 } name)
                    leagues.Add(name);
            }
        }
        return leagues.Order().ToArray();
    }

    public static List<CharacterSummary> Characters(SqliteConnection connection, SaveLayout layout, string accountId)
    {
        var result = new List<CharacterSummary>();
        using var c = connection.CreateCommand();
        if (layout.ColumnarCharacters)
        {
            c.CommandText = "SELECT name, level, league FROM account_characters WHERE account_id = $account ORDER BY name LIMIT 1024";
            c.Parameters.AddWithValue("$account", accountId);
            using var rows = c.ExecuteReader();
            while (rows.Read())
                result.Add(new(rows.GetString(0), rows.IsDBNull(1) ? 0 : rows.GetInt32(1),
                    rows.IsDBNull(2) ? "Standard" : rows.GetString(2)));
        }
        else
        {
            c.CommandText = "SELECT name, character FROM account_characters WHERE account_id = $account ORDER BY name LIMIT 1024";
            c.Parameters.AddWithValue("$account", accountId);
            using var rows = c.ExecuteReader();
            while (rows.Read())
            {
                using var row = JsonDocument.Parse(rows.GetString(1));
                int level = row.RootElement.TryGetProperty("Level", out var l) ? l.GetInt32() : 0;
                string league = row.RootElement.TryGetProperty("League", out var lg) ? lg.GetString() ?? "Standard" : "Standard";
                result.Add(new(rows.GetString(0), level, league));
            }
        }
        return result;
    }

    public static CharacterTarget FindCharacter(SqliteConnection connection, SaveLayout layout, string accountId, string name, SqliteTransaction? transaction)
    {
        using var c = connection.CreateCommand();
        c.Transaction = transaction;
        if (layout.ColumnarCharacters)
        {
            c.CommandText = "SELECT name, league, last_played_utc FROM account_characters WHERE account_id = $account AND name = $name COLLATE NOCASE LIMIT 1";
            c.Parameters.AddWithValue("$account", accountId);
            c.Parameters.AddWithValue("$name", name);
            using var rows = c.ExecuteReader();
            if (!rows.Read()) throw new ArgumentException($"This account has no character named {name}.");
            string found = rows.GetString(0);
            string league = rows.IsDBNull(1) ? "Standard" : rows.GetString(1);
            if (league.Contains("Ruthless", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Ruthless requires a separate native format/rules adapter and is not supported by this exporter.");
            var played = !rows.IsDBNull(2) && DateTimeOffset.TryParse(rows.GetString(2), CultureInfo.InvariantCulture,
                DateTimeStyles.RoundtripKind, out var parsed) ? parsed : DateTimeOffset.MaxValue;
            return new(found, league, played);
        }
        else
        {
            c.CommandText = "SELECT name, character FROM account_characters WHERE account_id = $account AND name = $name COLLATE NOCASE LIMIT 1";
            c.Parameters.AddWithValue("$account", accountId);
            c.Parameters.AddWithValue("$name", name);
            using var rows = c.ExecuteReader();
            if (!rows.Read()) throw new ArgumentException($"This account has no character named {name}.");
            string found = rows.GetString(0);
            using var row = JsonDocument.Parse(rows.GetString(1));
            var character = row.RootElement;
            string league = character.TryGetProperty("League", out var lg) ? lg.GetString() ?? "Standard" : "Standard";
            if (league.Contains("Ruthless", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Ruthless requires a separate native format/rules adapter and is not supported by this exporter.");
            var played = character.TryGetProperty("LastPlayedUtc", out var lp) && lp.ValueKind == JsonValueKind.String
                && lp.TryGetDateTimeOffset(out var parsed) ? parsed : DateTimeOffset.MaxValue;
            return new(found, league, played);
        }
    }

    public static void CheckDestination(SqliteConnection connection, SaveLayout layout, string accountId, string name,
        string database, string data, SqliteTransaction? transaction = null)
    {
        if (Convert.ToInt32(Scalar(connection, "SELECT count(*) FROM account_characters WHERE account_id = $value", accountId, transaction)) >= 24)
            throw new ArgumentException("This account has reached the 24-character limit.");
        string collisionSql = layout.RelationalSaves
            ? "SELECT 1 FROM account_characters WHERE name = $value COLLATE NOCASE UNION ALL SELECT 1 FROM character_saves WHERE name = $value COLLATE NOCASE AND deleted_utc IS NULL LIMIT 1"
            : TableColumns(connection, "main", "character_saves").Count > 0
                ? "SELECT 1 FROM account_characters WHERE name = $value COLLATE NOCASE UNION ALL SELECT 1 FROM characters WHERE name = $value COLLATE NOCASE UNION ALL SELECT 1 FROM character_saves WHERE name = $value COLLATE NOCASE AND deleted_utc IS NULL LIMIT 1"
                : "SELECT 1 FROM account_characters WHERE name = $value COLLATE NOCASE UNION ALL SELECT 1 FROM characters WHERE name = $value COLLATE NOCASE LIMIT 1";
        if (Scalar(connection, collisionSql, name, transaction) is not null)
            throw new ArgumentException("That character name or save already exists. Existing characters are never replaced.");
        foreach (string folder in new[] { Path.Combine(data, "saves"), Path.Combine(Path.GetDirectoryName(database)!, "saves") }.Distinct())
            if (Directory.Exists(folder) && Directory.EnumerateFiles(folder, "*.json").Any(f => Path.GetFileNameWithoutExtension(f).Equals(name, StringComparison.OrdinalIgnoreCase)))
                throw new ArgumentException("A legacy save already uses that name. Let LocalExile migrate it before exporting.");
    }

    public static void WriteNewCharacter(SqliteConnection writer, SaveLayout layout, SqliteTransaction transaction,
        string id, string accountId, string name, CharacterClass charClass, int level, string league, string stamp,
        CharacterSaves.Save saveModel, string saveJson)
    {
        if (layout.ColumnarCharacters)
        {
            using var command = writer.CreateCommand();
            command.Transaction = transaction;
            command.CommandText = "INSERT INTO account_characters(id, account_id, name, class, level, league, area_id, created_utc, last_played_utc, last_town, portrait) " +
                "VALUES($id, $account, $name, $class, $level, $league, $area, $created, $played, $town, 0)";
            command.Parameters.AddWithValue("$id", id);
            command.Parameters.AddWithValue("$account", accountId);
            command.Parameters.AddWithValue("$name", name);
            command.Parameters.AddWithValue("$class", (long)charClass);
            command.Parameters.AddWithValue("$level", (long)level);
            command.Parameters.AddWithValue("$league", league);
            command.Parameters.AddWithValue("$area", "1_1_town");
            command.Parameters.AddWithValue("$created", stamp);
            command.Parameters.AddWithValue("$played", stamp);
            command.Parameters.AddWithValue("$town", "1_1_town");
            command.ExecuteNonQuery();
        }
        else
        {
            var character = new
            {
                Id = id, AccountId = accountId, Name = name, Class = (int)charClass, Level = level,
                League = league, AreaId = "1_1_town", CreatedUtc = stamp, LastPlayedUtc = stamp, LastTown = "1_1_town", Portrait = 0,
            };
            using var command = writer.CreateCommand();
            command.Transaction = transaction;
            command.CommandText = "INSERT INTO account_characters(id, account_id, name, created_utc, character) VALUES($id, $account, $name, $stamp, $json)";
            command.Parameters.AddWithValue("$id", id);
            command.Parameters.AddWithValue("$account", accountId);
            command.Parameters.AddWithValue("$name", name);
            command.Parameters.AddWithValue("$stamp", stamp);
            command.Parameters.AddWithValue("$json", JsonSerializer.Serialize(character));
            command.ExecuteNonQuery();
        }

        if (layout.RelationalSaves)
        {
            WriteRelationalCharacterSave(writer, transaction, name, saveModel);
        }
        else
        {
            using var command = writer.CreateCommand();
            command.Transaction = transaction;
            command.CommandText = "INSERT INTO characters(name, save) VALUES($name, $save)";
            command.Parameters.AddWithValue("$name", name);
            command.Parameters.AddWithValue("$save", saveJson);
            command.ExecuteNonQuery();
        }
    }

    static void WriteRelationalCharacterSave(SqliteConnection writer, SqliteTransaction transaction, string name, CharacterSaves.Save save)
    {
        long saveId;
        using (var command = writer.CreateCommand())
        {
            command.Transaction = transaction;
            command.CommandText = "INSERT INTO character_saves(name, has_inventories, experience, passives, waypoints, visited, extra_passive_points) " +
                "VALUES($name, 1, $experience, $passives, $waypoints, $visited, $extraPassivePoints) RETURNING id";
            command.Parameters.AddWithValue("$name", name);
            command.Parameters.AddWithValue("$experience", DbValue(save.Experience));
            command.Parameters.AddWithValue("$passives", DbValue(JsonOf(save.Passives)));
            command.Parameters.AddWithValue("$waypoints", DbValue(JsonOf(save.Waypoints)));
            command.Parameters.AddWithValue("$visited", DbValue(JsonOf(save.Visited)));
            command.Parameters.AddWithValue("$extraPassivePoints", DbValue(save.ExtraPassivePoints));
            saveId = (long)command.ExecuteScalar()!;
        }

        foreach (byte inventory in save.Inventories.Keys.Order())
        {
            ExecuteNonQuery(writer, transaction, "INSERT INTO character_inventories(save, inventory) VALUES($s, $i)",
                ("$s", saveId), ("$i", (long)inventory));
        }
        foreach (var (slot, skill) in save.SkillBar ?? [])
        {
            ExecuteNonQuery(writer, transaction, "INSERT INTO character_skill_bar(save, slot, skill) VALUES($s, $k, $v)",
                ("$s", saveId), ("$k", (long)slot), ("$v", skill));
        }
        foreach (var (node, effect) in save.MasteryEffects ?? [])
        {
            ExecuteNonQuery(writer, transaction, "INSERT INTO character_masteries(save, node, effect) VALUES($s, $k, $v)",
                ("$s", saveId), ("$k", (long)node), ("$v", (long)effect));
        }
        foreach (var (node, tattoo) in save.Tattoos ?? [])
        {
            ExecuteNonQuery(writer, transaction, "INSERT INTO character_tattoos(save, node, tattoo) VALUES($s, $k, $v)",
                ("$s", saveId), ("$k", (long)node), ("$v", tattoo));
        }
        foreach (var (node, keystone) in save.TattooKeystones ?? [])
        {
            ExecuteNonQuery(writer, transaction, "INSERT INTO character_tattoo_keystones(save, node, keystone) VALUES($s, $k, $v)",
                ("$s", saveId), ("$k", (long)node), ("$v", (long)keystone));
        }
        foreach (var (inventory, list) in save.Inventories.OrderBy(kv => kv.Key))
        {
            for (int i = 0; i < list.Count; i++)
                InsertItem(writer, transaction, saveId, inventory, "placed", null, i, list[i], list[i].Item);
        }
    }

    public static CharacterSaveSnapshot ReadCharacterSave(SqliteConnection connection, SaveLayout layout, string name, SqliteTransaction? transaction)
    {
        if (!layout.RelationalSaves)
        {
            using var c = connection.CreateCommand();
            c.Transaction = transaction;
            c.CommandText = "SELECT save FROM characters WHERE name = $name COLLATE NOCASE";
            c.Parameters.AddWithValue("$name", name);
            string save = c.ExecuteScalar() as string
                ?? throw new ArgumentException($"{name} has no save yet. Log in with it once, then send the item.");
            var placed = ParseLegacyPlacements(save);
            return new CharacterSaveSnapshot(null, save, placed, 0);
        }

        long saveId;
        bool hasInventories;
        JsonObject saveRow;
        using (var c = connection.CreateCommand())
        {
            c.Transaction = transaction;
            c.CommandText = "SELECT * FROM character_saves WHERE name = $name COLLATE NOCASE AND deleted_utc IS NULL";
            c.Parameters.AddWithValue("$name", name);
            using var r = c.ExecuteReader();
            if (!r.Read())
                throw new ArgumentException($"{name} has no save yet. Log in with it once, then send the item.");
            saveRow = ReadRowAsJson(r);
            saveId = Convert.ToInt64(r["id"], CultureInfo.InvariantCulture);
            hasInventories = Convert.ToInt64(r["has_inventories"], CultureInfo.InvariantCulture) != 0;
        }
        if (!hasInventories)
            throw new ArgumentException("The character's save has no inventories. Nothing was sent.");

        var inventories = new JsonArray();
        using (var c = connection.CreateCommand())
        {
            c.Transaction = transaction;
            c.CommandText = "SELECT inventory FROM character_inventories WHERE save = $s ORDER BY inventory";
            c.Parameters.AddWithValue("$s", saveId);
            using var r = c.ExecuteReader();
            while (r.Read()) inventories.Add(r.GetInt64(0));
        }

        var itemsJson = new JsonArray();
        var placedItems = new List<PlacedItem>();
        int maxMainOrd = -1;
        using (var c = connection.CreateCommand())
        {
            c.Transaction = transaction;
            c.CommandText = "SELECT * FROM items WHERE character = $s ORDER BY id";
            c.Parameters.AddWithValue("$s", saveId);
            using var r = c.ExecuteReader();
            while (r.Read())
            {
                itemsJson.Add(ReadRowAsJson(r));
                if (string.Equals(r["role"] as string, "placed", StringComparison.Ordinal) && r["parent"] is DBNull or null)
                {
                    if (r["inventory"] is DBNull || r["placement"] is DBNull || r["x"] is DBNull || r["y"] is DBNull)
                        throw new ArgumentException("The character's save has an unreadable placed item. Nothing was sent.");
                    byte inv = checked((byte)Convert.ToInt64(r["inventory"], CultureInfo.InvariantCulture));
                    uint placementId = checked((uint)Convert.ToInt64(r["placement"], CultureInfo.InvariantCulture));
                    byte x = checked((byte)Convert.ToInt64(r["x"], CultureInfo.InvariantCulture));
                    byte y = checked((byte)Convert.ToInt64(r["y"], CultureInfo.InvariantCulture));
                    uint typeHash = checked((uint)Convert.ToInt64(r["type"], CultureInfo.InvariantCulture));
                    int ord = checked((int)Convert.ToInt64(r["ord"], CultureInfo.InvariantCulture));
                    placedItems.Add(new(inv, placementId, x, y, typeHash));
                    if (inv == 0 && ord > maxMainOrd) maxMainOrd = ord;
                }
            }
        }

        var modsJson = new JsonArray();
        using (var c = connection.CreateCommand())
        {
            c.Transaction = transaction;
            c.CommandText = "SELECT item, ord, mod, section, stat_values FROM item_mods WHERE item IN (SELECT id FROM items WHERE character = $s) ORDER BY item, ord";
            c.Parameters.AddWithValue("$s", saveId);
            using var r = c.ExecuteReader();
            while (r.Read()) modsJson.Add(ReadRowAsJson(r));
        }

        var snapshot = new JsonObject
        {
            ["format"] = "relational",
            ["saveId"] = saveId,
            ["character"] = name,
            ["characterSave"] = saveRow,
            ["inventories"] = inventories,
            ["items"] = itemsJson,
            ["itemMods"] = modsJson,
        };
        return new CharacterSaveSnapshot(saveId, snapshot.ToJsonString(), placedItems, maxMainOrd + 1);
    }

    public static void AddItemToMainInventory(SqliteConnection writer, SaveLayout layout, SqliteTransaction transaction,
        string characterName, CharacterSaveSnapshot snapshot, CharacterSaves.SavedPlacement placement)
    {
        if (!layout.RelationalSaves)
        {
            using var command = writer.CreateCommand();
            command.Transaction = transaction;
            command.CommandText = "UPDATE characters SET save = $save WHERE name = $name COLLATE NOCASE";
            command.Parameters.AddWithValue("$save", ItemSend.WithItem(snapshot.SnapshotJson, placement));
            command.Parameters.AddWithValue("$name", characterName);
            if (command.ExecuteNonQuery() != 1)
                throw new ArgumentException("The character's save disappeared. Nothing was sent.");
            return;
        }

        long saveId = snapshot.SaveId ?? throw new InvalidOperationException("Missing relational save id.");
        ExecuteNonQuery(writer, transaction, "INSERT OR IGNORE INTO character_inventories(save, inventory) VALUES($s, 0)", ("$s", saveId));
        InsertItem(writer, transaction, saveId, 0, "placed", null, snapshot.NextMainOrd, placement, placement.Item);
    }

    static long InsertItem(SqliteConnection writer, SqliteTransaction transaction, long saveId, byte inventory,
        string role, long? parentId, int ord, CharacterSaves.SavedPlacement? placement, CharacterSaves.SavedItem item)
    {
        long itemId;
        using (var command = writer.CreateCommand())
        {
            command.Transaction = transaction;
            command.CommandText =
                "INSERT INTO items(character, stash, inventory, role, parent, ord, placement, x, y, " +
                "type, item_level, quality, charges, stack_size, sockets, links, gem_experience, rarity, identified, " +
                "has_mods, name, gem_variant, corrupted, fractured, mirrored, gem_flags, visual, defence_base_roll, " +
                "influences, split, synthesised, foreseeing, foresee_seed) " +
                "VALUES($character, NULL, $inventory, $role, $parent, $ord, $placement, $x, $y, " +
                "$type, $itemLevel, $quality, $charges, $stackSize, $sockets, $links, $gemExperience, $rarity, $identified, " +
                "$hasMods, $name, $gemVariant, $corrupted, $fractured, $mirrored, $gemFlags, $visual, $defenceBaseRoll, " +
                "0, 0, 0, 0, 0) RETURNING id";
            command.Parameters.AddWithValue("$character", saveId);
            command.Parameters.AddWithValue("$inventory", (long)inventory);
            command.Parameters.AddWithValue("$role", role);
            command.Parameters.AddWithValue("$parent", DbValue(parentId));
            command.Parameters.AddWithValue("$ord", (long)ord);
            command.Parameters.AddWithValue("$placement", DbValue(placement?.Id));
            command.Parameters.AddWithValue("$x", DbValue(placement?.X));
            command.Parameters.AddWithValue("$y", DbValue(placement?.Y));
            command.Parameters.AddWithValue("$type", (long)item.Type);
            command.Parameters.AddWithValue("$itemLevel", (long)item.ItemLevel);
            command.Parameters.AddWithValue("$quality", (long)item.Quality);
            command.Parameters.AddWithValue("$charges", (long)item.Charges);
            command.Parameters.AddWithValue("$stackSize", (long)item.StackSize);
            string? socketsJson = item.Sockets is { Count: > 0 } ? JsonSerializer.Serialize(item.Sockets.Select(s => (byte)s.Colour).ToList()) : null;
            string? linksJson = item.Links is { Count: > 0 } ? JsonSerializer.Serialize(item.Links) : null;
            string? nameJson = item.Name is { Count: > 0 } ? JsonSerializer.Serialize(item.Name) : null;
            command.Parameters.AddWithValue("$sockets", DbValue(socketsJson));
            command.Parameters.AddWithValue("$links", DbValue(linksJson));
            command.Parameters.AddWithValue("$gemExperience", (long)item.GemExperience);
            command.Parameters.AddWithValue("$rarity", (long)item.Rarity);
            command.Parameters.AddWithValue("$identified", item.Identified ? 1L : 0L);
            command.Parameters.AddWithValue("$hasMods", item.Mods is not null ? 1L : 0L);
            command.Parameters.AddWithValue("$name", DbValue(nameJson));
            command.Parameters.AddWithValue("$gemVariant", (long)item.GemVariant);
            command.Parameters.AddWithValue("$corrupted", item.Corrupted ? 1L : 0L);
            command.Parameters.AddWithValue("$fractured", (long)item.Fractured);
            command.Parameters.AddWithValue("$mirrored", item.Mirrored ? 1L : 0L);
            command.Parameters.AddWithValue("$gemFlags", (long)item.GemFlags);
            command.Parameters.AddWithValue("$visual", DbValue(item.Visual));
            command.Parameters.AddWithValue("$defenceBaseRoll", (long)item.DefenceBaseRoll);
            itemId = (long)command.ExecuteScalar()!;
        }

        if (item.Mods is { Count: > 0 } mods)
        {
            using var modCommand = writer.CreateCommand();
            modCommand.Transaction = transaction;
            modCommand.CommandText = "INSERT INTO item_mods(item, ord, mod, section, stat_values) VALUES($item, $ord, $mod, $section, $values)";
            modCommand.Parameters.Add(new SqliteParameter("$item", itemId));
            var pOrd = modCommand.Parameters.Add(new SqliteParameter("$ord", 0L));
            var pMod = modCommand.Parameters.Add(new SqliteParameter("$mod", ""));
            var pSection = modCommand.Parameters.Add(new SqliteParameter("$section", 0L));
            var pValues = modCommand.Parameters.Add(new SqliteParameter("$values", ""));
            for (int i = 0; i < mods.Count; i++)
            {
                var m = mods[i];
                pOrd.Value = (long)i;
                pMod.Value = m.Id;
                pSection.Value = (long)m.Section;
                pValues.Value = JsonSerializer.Serialize(m.Values);
                modCommand.ExecuteNonQuery();
            }
        }

        if (item.Sockets is { Count: > 0 } sockets)
        {
            for (int i = 0; i < sockets.Count; i++)
                if (sockets[i].Gem is { } gem)
                    InsertItem(writer, transaction, saveId, inventory, "socketed", itemId, i, null, gem);
        }

        return itemId;
    }

    public static ItemSend.UniqueDefinition? FindUniqueDefinition(SqliteConnection connection, string? database, string? data, string title, string baseTypeId)
    {
        const string foulborn = "Foulborn ";
        string uniqueName = title.StartsWith(foulborn, StringComparison.Ordinal) ? title[foulborn.Length..] : title;
        if (ReadCatalogEntry(connection, uniqueName, baseTypeId) is { } fromMain) return fromMain;

        foreach (string worldPath in WorldDatabaseCandidates(database, data))
        {
            if (!File.Exists(worldPath)) continue;
            try
            {
                using var world = ExportCommand.Open(ExportCommand.ExistingLocalFile(worldPath), write: false);
                if (ReadRelationalUnique(world, uniqueName, baseTypeId) is { } relational) return relational;
                if (ReadCatalogEntry(world, uniqueName, baseTypeId) is { } catalog) return catalog;
            }
            catch (Exception e) when (e is ArgumentException or IOException or UnauthorizedAccessException or SqliteException or JsonException)
            {
                // World catalogue lookup is optional; if unavailable, fall back to PoB-parsed modifiers.
            }
        }
        return null;
    }

    static IEnumerable<string> WorldDatabaseCandidates(string? database, string? data)
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (Environment.GetEnvironmentVariable("Game_WORLD_DB") is { Length: > 0 } envWorld && Path.IsPathFullyQualified(envWorld) && seen.Add(envWorld))
            yield return envWorld;
        if (!string.IsNullOrWhiteSpace(database) && Path.GetDirectoryName(database) is { Length: > 0 } dbFolder)
        {
            string beside = Path.Combine(dbFolder, "world.db");
            if (seen.Add(beside)) yield return beside;
        }
        if (!string.IsNullOrWhiteSpace(data))
        {
            string inData = Path.Combine(data, "world.db");
            if (seen.Add(inData)) yield return inData;
        }
    }

    static ItemSend.UniqueDefinition? ReadCatalogEntry(SqliteConnection connection, string uniqueName, string baseTypeId)
    {
        using var c = connection.CreateCommand();
        c.CommandText = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'catalog_entries'";
        if (c.ExecuteScalar() is null) return null;
        c.CommandText = "SELECT payload FROM catalog_entries WHERE kind = 'unique_item' AND key = $key AND enabled = 1";
        c.Parameters.AddWithValue("$key", $"{uniqueName}|{baseTypeId}");
        return c.ExecuteScalar() is string payload ? JsonSerializer.Deserialize<ItemSend.UniqueDefinition>(payload) : null;
    }

    static ItemSend.UniqueDefinition? ReadRelationalUnique(SqliteConnection world, string uniqueName, string baseTypeId)
    {
        var itemCols = TableColumns(world, "main", "unique_items");
        var modCols = TableColumns(world, "main", "unique_item_mods");
        if (!itemCols.Contains("name") || !itemCols.Contains("base_type") || !itemCols.Contains("item_level")
            || !itemCols.Contains("corrupted") || !itemCols.Contains("enabled")
            || !modCols.Contains("name") || !modCols.Contains("base_type") || !modCols.Contains("implicit")
            || !modCols.Contains("ord") || !modCols.Contains("mod"))
            return null;

        byte itemLevel;
        bool corrupted;
        using (var c = world.CreateCommand())
        {
            c.CommandText = "SELECT item_level, corrupted FROM unique_items WHERE name = $name AND base_type = $base AND enabled = 1";
            c.Parameters.AddWithValue("$name", uniqueName);
            c.Parameters.AddWithValue("$base", baseTypeId);
            using var r = c.ExecuteReader();
            if (!r.Read()) return null;
            itemLevel = checked((byte)r.GetInt64(0));
            corrupted = r.GetInt64(1) != 0;
        }

        var mods = new List<string>();
        using (var c = world.CreateCommand())
        {
            c.CommandText = "SELECT mod FROM unique_item_mods WHERE name = $name AND base_type = $base AND implicit = 0 ORDER BY ord";
            c.Parameters.AddWithValue("$name", uniqueName);
            c.Parameters.AddWithValue("$base", baseTypeId);
            using var r = c.ExecuteReader();
            while (r.Read()) mods.Add(r.GetString(0));
        }
        return new ItemSend.UniqueDefinition(uniqueName, baseTypeId, mods.ToArray(), itemLevel, corrupted);
    }

    static List<PlacedItem> ParseLegacyPlacements(string save)
    {
        var root = JsonNode.Parse(save) as JsonObject
            ?? throw new ArgumentException("The character's save cannot be read. Nothing was sent.");
        if (root["Inventories"] is not JsonObject inventories)
            throw new ArgumentException("The character's save has no inventories. Nothing was sent.");
        var result = new List<PlacedItem>();
        foreach (var (row, items) in inventories)
        {
            if (!byte.TryParse(row, NumberStyles.None, CultureInfo.InvariantCulture, out byte inv))
                throw new ArgumentException("The character's save has an invalid inventory key. Nothing was sent.");
            foreach (var placement in items?.AsArray() ?? new JsonArray())
                result.Add(new(inv, placement!["Id"]!.GetValue<uint>(), placement["X"]!.GetValue<byte>(),
                    placement["Y"]!.GetValue<byte>(), placement["Item"]!["Type"]!.GetValue<uint>()));
        }
        return result;
    }

    static JsonObject ReadRowAsJson(SqliteDataReader reader)
    {
        var obj = new JsonObject();
        for (int i = 0; i < reader.FieldCount; i++)
        {
            string col = reader.GetName(i);
            obj[col] = reader.IsDBNull(i) ? null : reader.GetValue(i) switch
            {
                long l => JsonValue.Create(l),
                double d => JsonValue.Create(d),
                string s => JsonValue.Create(s),
                byte[] b => JsonValue.Create(Convert.ToBase64String(b)),
                var v => JsonValue.Create(v.ToString()),
            };
        }
        return obj;
    }

    static string? JsonOf<T>(T? value) => value is null ? null : JsonSerializer.Serialize(value);

    static object DbValue(object? value) => value switch
    {
        null => DBNull.Value,
        bool b => b ? 1L : 0L,
        byte or ushort or uint or int or long => Convert.ToInt64(value, CultureInfo.InvariantCulture),
        _ => value,
    };

    static object? Scalar(SqliteConnection connection, string sql, string value, SqliteTransaction? transaction = null)
    {
        using var c = connection.CreateCommand();
        c.Transaction = transaction;
        c.CommandText = sql;
        c.Parameters.AddWithValue("$value", value);
        return c.ExecuteScalar();
    }

    static void ExecuteNonQuery(SqliteConnection connection, SqliteTransaction transaction, string sql, params (string Name, object Value)[] parameters)
    {
        using var c = connection.CreateCommand();
        c.Transaction = transaction;
        c.CommandText = sql;
        foreach (var (name, value) in parameters) c.Parameters.AddWithValue(name, value);
        c.ExecuteNonQuery();
    }
}
