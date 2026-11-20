using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using GameServer.Core.Imports;
using GameServer.Core.Protocol.Instance;
using Microsoft.Data.Sqlite;

/// <summary>
/// Places one PoB item in an existing character's main inventory. The Gateway keeps a character's items in memory from
/// its first login until it stops, and its next save would write over this change, so the write is refused unless that
/// Gateway cannot hold them. Only Inventories changes in the save's JSON: this exporter models 8 of its fields.
/// </summary>
static class ItemSend
{
    const string MainInventory = "0";
    const byte MainInventoryId = 0;
    const int MainWidth = 12, MainHeight = 5, MaximumItemCharacters = 64 * 1024;
    const uint FirstStashItemId = 0x40000000; // AccountStash.FirstItemId: a character's own item ids stay below it.
    const string RestartCommand = @".\scripts\dev\live.ps1 -Only Gateway -NoBuild";

    public sealed record Character(string Name, int Level, string League);

    public static IReadOnlyList<Character> Characters(SqliteConnection connection, SaveLayout layout,
        IReadOnlyList<ExportCommand.Destination> accounts, string? account)
    {
        var owner = account is { Length: > 0 } ? accounts.SingleOrDefault(a => a.Name.Equals(account, StringComparison.OrdinalIgnoreCase))
            : accounts.Count == 1 ? accounts[0] : null;
        if (owner is null) return [];
        return SaveDatabase.Characters(connection, layout, owner.Id)
            .Select(c => new Character(c.Name, c.Level, c.League)).ToList();
    }

    public static object Execute(ExportCommand.Request request, string database, string data, SqliteConnection connection,
        SaveLayout layout, IReadOnlyList<ExportCommand.Destination> accounts, string version,
        Func<int, GatewayState.Snapshot>? gateway = null)
    {
        if (string.IsNullOrWhiteSpace(request.Item) || request.Item.Length > MaximumItemCharacters)
            throw new ArgumentException("Choose one item in PoB's Items tab first.");
        var account = accounts.SingleOrDefault(a => a.Name.Equals(request.Account, StringComparison.OrdinalIgnoreCase))
            ?? throw new ArgumentException("The selected account does not exist in this database.");
        var catalog = new ItemCatalog(data); var warnings = new List<string>();
        var (type, parsed) = Parse(request.Item, catalog, data, warnings);
        var item = Definition(connection, Title(request.Item), type, parsed, database, data) is { } unique
            ? Completed(parsed, type, unique, catalog.Mods, warnings) : parsed;
        string label = Label(request.Item, type, item);
        var notes = new List<string>();
        var commands = Commands(request.Item, type, item, catalog.Mods, notes);
        bool incompleteUnique = item.Rarity == ItemRarity.Unique && warnings.Any(w => w.StartsWith("Skipped modifier", StringComparison.Ordinal));
        object Preview(string? character, CharacterSaves.SavedPlacement? placement, string? key, string? blocked) => new
        {
            ok = true, preview = true, previewKey = key, character, item = label, x = placement?.X, y = placement?.Y, blocked, incompleteUnique,
            commands, commandNotes = notes, warnings = warnings.Distinct().Take(45).Select(w => w[..Math.Min(w.Length, 240)]),
            warningCount = warnings.Distinct().Count(), next = blocked ?? "Ready. Send places it in the character's main inventory.",
        };
        if (string.IsNullOrWhiteSpace(request.Name))
            return Preview(null, null, null, "Choose a character to send it to. Copy Command works without one.");

        var target = SaveDatabase.FindCharacter(connection, layout, account.Id, request.Name, null);
        var snapshot = SaveDatabase.ReadCharacterSave(connection, layout, target.Name, null);
        var placement = Place(snapshot.Placed, type, item, catalog);
        string json = JsonSerializer.Serialize(placement);
        string key = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new {
            database, data, account.Id, target.Name, request.Item, json, save = snapshot.SnapshotJson, version }))));
        if (request.Operation == "item-preview") return Preview(target.Name, placement, key, Blocked(target, gateway));

        if (request.PreviewKey != key) throw new ArgumentException("The item, character or its save changed. Preview again before sending.");
        using var writerSession = SaveDatabase.Open(database, write: true);
        var writer = writerSession.Connection;
        var writerLayout = writerSession.Layout;
        using var transaction = writer.BeginTransaction(deferred: false);
        // Rechecked under the write lock: a login or an inventory change since the preview ends the send here.
        target = SaveDatabase.FindCharacter(writer, writerLayout, account.Id, target.Name, transaction);
        var current = SaveDatabase.ReadCharacterSave(writer, writerLayout, target.Name, transaction);
        if (current.SnapshotJson != snapshot.SnapshotJson) throw new ArgumentException("The character's save changed. Preview again before sending.");
        if (Blocked(target, gateway) is { } blocked) throw new ArgumentException(blocked);
        string backup = Backup(database, target.Name, current.SnapshotJson);
        SaveDatabase.AddItemToMainInventory(writer, writerLayout, transaction, target.Name, current, placement);
        transaction.Commit();
        return new { ok = true, preview = false, character = target.Name, item = label, x = placement.X, y = placement.Y, backup,
            next = "Log in to the character and press I. The item is in its main inventory." };
    }

    static (ItemCatalog.BaseType Type, Item Item) Parse(string text, ItemCatalog catalog, string data, List<string> warnings)
    {
        if (catalog.Error is { } unavailable) throw new ArgumentException(unavailable);
        try { return PathOfBuildingItems.ParseItem(new PathOfBuildingItem(1, text, null), catalog, data, warnings); }
        catch (PathOfBuildingUnsupportedException e) { throw new ArgumentException($"This item cannot be sent: {e.Message}."); }
    }

    internal sealed record UniqueDefinition(string Name, string BaseTypeId, string[] Mods, byte ItemLevel = 86, bool Corrupted = false);

    // The server's catalogue row: PoB's text cannot name most unique modifiers, this row does. Older databases have no such table.
    internal static UniqueDefinition? Definition(SqliteConnection connection, string title, ItemCatalog.BaseType type, Item item,
        string? database = null, string? data = null)
    {
        if (item.Rarity != ItemRarity.Unique || item.FracturedCount > 0) return null;
        return SaveDatabase.FindUniqueDefinition(connection, database, data, title, type.Id);
    }

    /// <summary>The unique with its catalogue modifiers: PoB's roll where its text matched the same stats, else the top of
    /// the roll. Base implicits PoB's text did not identify are added the same way; other parsed modifiers stay.</summary>
    internal static Item Completed(Item item, ItemCatalog.BaseType type, UniqueDefinition unique, ModCatalog mods, List<string> warnings)
    {
        HashSet<string> Stats(ModCatalog.Mod mod) => [.. mod.Stats.Select(s => s.Id)];
        var parsed = item.Mods.ToList(); int filled = 0;
        ItemMod Resolve(ModCatalog.Mod mod, ModSection section)
        {
            var match = parsed.FirstOrDefault(m => mods.ByHash(m.Hash) is { } native && Stats(native).SetEquals(Stats(mod)));
            if (match is null) { filled++; return new(section, mod.Hash, [.. mod.Stats.Select(s => s.Max)]); }
            parsed.Remove(match);
            var values = mods.ByHash(match.Hash)!.Stats.Select((s, i) => (s.Id, Value: match.Values[i])).ToDictionary(s => s.Id, s => s.Value);
            return new(section, mod.Hash, [.. mod.Stats.Select(s => values[s.Id])]);
        }
        var implicits = (type.Implicits ?? []).Select(m => Resolve(m, ModSection.Implicit)).ToList();
        var explicits = unique.Mods.Select(mods.ById).OfType<ModCatalog.Mod>().Select(m => Resolve(m, ModSection.Explicit)).ToList();
        warnings.RemoveAll(w => w.StartsWith("Skipped modifier", StringComparison.Ordinal));
        if (filled > 0) warnings.Add($"{filled} modifier(s) use the top of their roll from the server's unique catalogue; PoB's text could not identify them.");
        return item with
        {
            Mods = [.. implicits, .. explicits, .. parsed], Corrupted = item.Corrupted || unique.Corrupted,
            ItemLevel = item.ItemLevel > 1 ? item.ItemLevel : unique.ItemLevel,
        };
    }

    /// <summary>What the player must do first for this write to survive, or null when it is safe now.</summary>
    static string? Blocked(SaveDatabase.CharacterTarget target, Func<int, GatewayState.Snapshot>? readGateway)
    {
        var gateway = (readGateway ?? GatewayState.Read)(GatewayState.Port);
        if (gateway.ClientConnected) return "You are in game. Log out to the character screen, then click Check Again.";
        if (!gateway.Running) return null;
        if (gateway.Started is { } started && target.LastPlayed < started) return null;
        // Closing the client does not help: the Gateway keeps the items after a logout, until it stops.
        return $"Restart the Gateway first, then click Check Again. It still holds {target.Name}'s items from this session and would overwrite this one. "
            + $"From the LocalExile folder, run: {RestartCommand}";
    }

    static CharacterSaves.SavedPlacement Place(IReadOnlyList<SaveDatabase.PlacedItem> placed, ItemCatalog.BaseType type, Item item, ItemCatalog catalog)
    {
        var main = new List<(int X, int Y, int Width, int Height)>();
        foreach (var placement in placed)
        {
            if (placement.Inventory != MainInventoryId) continue;
            var existing = catalog.All.FirstOrDefault(t => t.Hash == placement.Type)
                ?? throw new ArgumentException("The character's inventory holds an item this game data does not know. Nothing was sent.");
            main.Add((placement.X, placement.Y, existing.Width, existing.Height));
        }
        for (int x = 0; x + type.Width <= MainWidth; x++)
            for (int y = 0; y + type.Height <= MainHeight; y++)
                if (!main.Any(i => i.X < x + type.Width && x < i.X + i.Width && i.Y < y + type.Height && y < i.Y + i.Height))
                {
                    uint id = placed.Select(p => p.Id).Where(i => i < FirstStashItemId).DefaultIfEmpty(0u).Max() + 1;
                    return new(id, (byte)x, (byte)y, CharacterSaves.ToSaved(item, catalog.Mods));
                }
        throw new ArgumentException($"The main inventory has no free {type.Width}x{type.Height} space. Clear some room in game, then Preview again.");
    }

    internal static string WithItem(string save, CharacterSaves.SavedPlacement placement)
    {
        var root = JsonNode.Parse(save)!.AsObject(); var inventories = root["Inventories"]!.AsObject();
        if (inventories[MainInventory] is not JsonArray main) inventories[MainInventory] = main = new JsonArray();
        main.Add(JsonSerializer.SerializeToNode(placement));
        return root.ToJsonString();
    }

    // One row changes, so its previous JSON is the backup. Copying the whole database per item would fill the disk quickly.
    static string Backup(string database, string name, string save)
    {
        string folder = Path.Combine(Path.GetDirectoryName(database)!, "evryBuild-backups"); Directory.CreateDirectory(folder);
        string path = Path.Combine(folder, $"{name}-{DateTime.UtcNow:yyyyMMdd-HHmmss}-{Guid.NewGuid():N}.save.json");
        using (var file = new FileStream(path, FileMode.CreateNew, FileAccess.Write)) file.Write(Encoding.UTF8.GetBytes(save));
        return path;
    }

    internal static string Title(string text) => text.Replace("\r", "").Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
        .SkipWhile(l => !l.StartsWith("Rarity:", StringComparison.Ordinal)).Skip(1).FirstOrDefault() ?? "";

    static string Label(string text, ItemCatalog.BaseType type, Item item) =>
        item.Rarity is ItemRarity.Rare or ItemRarity.Unique ? $"{Title(text)}, {type.Name}" : type.Name;

    /// <summary>The chat commands that build the item on a running server. A unique comes from the server's own catalogue,
    /// with its rolls; anything else is rebuilt on the held item. Fields no command can set are reported.</summary>
    internal static IReadOnlyList<string> Commands(string text, ItemCatalog.BaseType type, Item item, ModCatalog mods, List<string> notes)
    {
        if (item.Rarity == ItemRarity.Unique)
        {
            notes.Add("This makes the server's own version of the unique, so its rolls can differ from PoB's.");
            return [$"/item {Title(text)}"];
        }
        var commands = new List<string> { $"/item {type.Name}" };
        var missing = new List<string>();
        if (item.Quality > 0) missing.Add("quality");
        if (item.FracturedCount > 0) missing.Add("fractured modifiers");
        if (item.Mirrored) missing.Add("mirrored state");
        if (item.Rarity == ItemRarity.Rare) missing.Add("the rare name");
        missing.Add("item level");
        notes.Add($"Commands cannot set {string.Join(", ", missing)}. Send keeps them.");
        if (item.Mods.Count > 0) commands.Add("/item_mod clear");
        if (item.Rarity != ItemRarity.Normal) commands.Add($"/rarity {item.Rarity.ToString().ToLowerInvariant()}");
        foreach (var mod in item.Mods)
            if (mods.ByHash(mod.Hash) is { } native)
                commands.Add(string.Join(' ', new[] { "/item_mod", mod.Section.ToString().ToLowerInvariant(), native.Id }
                    .Concat(mod.Values.Select(v => v.ToString(CultureInfo.InvariantCulture)))));
        if (Sockets(item) is { } sockets) commands.Add($"/sockets {sockets}");
        if (item.Components.Contains("Armour")) commands.Add($"/base_defence {Math.Min(item.DefenceBaseRoll, Item.MaximumDefenceBaseRoll)}");
        if (item.Corrupted) commands.Add("/corrupt");
        if (commands.Count > 1) notes.Add("Run the first command, pick the new item up on your cursor, then run the rest.");
        return commands;
    }

    // "/sockets RRG B": letters of one word are linked. An Abyss socket has no letter, so the layout cannot be written.
    static string? Sockets(Item item)
    {
        if (item.Sockets.Count == 0 || item.Sockets.Any(s => s.Colour is SocketColour.Abyss or SocketColour.Delve)) return null;
        var words = new List<string>(); int at = 0;
        foreach (int size in item.Links ?? [.. Enumerable.Repeat((byte)1, item.Sockets.Count)])
        {
            words.Add(string.Concat(item.Sockets.Skip(at).Take(size).Select(s => s.Colour switch
                { SocketColour.Red => 'R', SocketColour.Green => 'G', SocketColour.Blue => 'B', _ => 'W' })));
            at += size;
        }
        return string.Join(' ', words);
    }
}
