using System.Text.Json;
using System.Text.Json.Nodes;
using GameServer.Core.Accounts;
using GameServer.Core.Imports;
using GameServer.Core.Protocol.Instance;

public class ItemSendTests
{
    static readonly ItemCatalog.BaseType Ring = new(0, "Metadata/Items/Ring", "Iron Ring", 5, 1, 1, 0, ["Base", "Mods"], 0);
    static readonly ItemCatalog.BaseType Vest = new(1, "Metadata/Items/Vest", "Plate Vest", 6, 2, 3, 0, ["Base", "Mods", "Armour", "Sockets"], 0);
    static Item Create(ItemCatalog.BaseType type) => ItemCatalog.Create(type);

    [Fact]
    public void Saved_items_keep_their_defence_base_roll()
    {
        var saved = CharacterSaves.ToSaved(Create(Vest) with { DefenceBaseRoll = 17 }, new ModCatalog("missing"));
        Assert.Equal((byte)17, saved.DefenceBaseRoll);
    }

    [Fact]
    public void Adding_an_item_keeps_every_other_save_field()
    {
        const string save = """{"Inventories":{"2":[]},"Passives":[1],"NewerField":{"a":1}}""";
        var placed = new CharacterSaves.SavedPlacement(3, 1, 2, new(5));
        var root = JsonNode.Parse(ItemSend.WithItem(save, placed))!;
        Assert.Equal(3u, root["Inventories"]!["0"]![0]!["Id"]!.GetValue<uint>());
        Assert.Equal(1, root["NewerField"]!["a"]!.GetValue<int>());
        Assert.Equal(1, root["Passives"]![0]!.GetValue<int>());
    }

    [Fact]
    public void A_unique_uses_the_servers_catalogue()
    {
        var notes = new List<string>();
        var commands = ItemSend.Commands("Rarity: UNIQUE\nMageblood\nHeavy Belt", Ring, Create(Ring) with { Rarity = ItemRarity.Unique }, new ModCatalog("missing"), notes);
        Assert.Equal(["/item Mageblood"], commands);
        Assert.Contains("rolls can differ", Assert.Single(notes));
    }

    [Fact]
    public void A_rare_is_rebuilt_on_the_held_item_in_order()
    {
        var notes = new List<string>();
        var item = Create(Vest) with
        {
            Rarity = ItemRarity.Rare, Corrupted = true, DefenceBaseRoll = 12, Quality = 20,
            Sockets = [new(SocketColour.Red), new(SocketColour.Red), new(SocketColour.Blue)], Links = [2, 1],
        };
        Assert.Equal(["/item Plate Vest", "/rarity rare", "/sockets RR B", "/base_defence 12", "/corrupt"],
            ItemSend.Commands("Rarity: RARE\nDoom Coat\nPlate Vest", Vest, item, new ModCatalog("missing"), notes));
        Assert.Contains(notes, n => n.Contains("quality") && n.Contains("the rare name"));
        Assert.Contains(notes, n => n.Contains("cursor"));
    }

    [Fact]
    public void A_catalogued_unique_keeps_pob_rolls_and_gains_the_modifiers_its_text_lost()
    {
        string folder = Directory.CreateTempSubdirectory("evrybuild-unique-").FullName;
        try
        {
            Directory.CreateDirectory(Path.Combine(folder, "tables"));
            File.WriteAllText(Path.Combine(folder, "tables/Stats.json"), JsonSerializer.Serialize(new[] {
                new { Id = "additional_dexterity", IsLocal = false }, new { Id = "special_mechanic", IsLocal = false } }));
            object Mod(int row, string id, int stat, int min, int max) => new Dictionary<string, object?>
            {
                ["Id"] = id, ["HASH16"] = 100 + row, ["Name"] = id, ["Domain"] = 1, ["GenerationType"] = 3, ["Level"] = 1,
                ["StatsKey1"] = stat, ["StatsKey2"] = null, ["Stat1Min"] = min, ["Stat1Max"] = max, ["Families"] = Array.Empty<int>(),
                ["SpawnWeight_TagsKeys"] = Array.Empty<int>(), ["SpawnWeight_Values"] = Array.Empty<int>(),
                ["GenerationWeight_TagsKeys"] = Array.Empty<int>(), ["GenerationWeight_Values"] = Array.Empty<int>(), ["IsEssenceOnlyModifier"] = false,
            };
            File.WriteAllText(Path.Combine(folder, "tables/Mods.json"), JsonSerializer.Serialize(new[] {
                Mod(0, "ParsedAsThis", 0, 1, 50), Mod(1, "DexterityUnique", 0, 40, 50), Mod(2, "SpecialUnique", 1, 1, 1) }));
            var mods = new ModCatalog(folder); var warnings = new List<string> { "Skipped modifier on Belt: unknown text." };
            var parsed = Create(Ring) with { Rarity = ItemRarity.Unique, Mods = [new(ModSection.Explicit, 100, [44])] };
            var item = ItemSend.Completed(parsed, Ring, new("Fixture", Ring.Id, ["DexterityUnique", "SpecialUnique"], 70), mods, warnings);
            Assert.Equal(new[] { (ushort)101, (ushort)102 }, item.Mods.Select(m => m.Hash));
            Assert.Equal([44], item.Mods[0].Values);
            Assert.Equal([1], item.Mods[1].Values);
            Assert.Equal((byte)70, item.ItemLevel);
            Assert.Contains("1 modifier(s)", Assert.Single(warnings));
        }
        finally { Directory.Delete(folder, true); }
    }

    [Fact]
    public void Abyss_sockets_are_left_out_of_the_commands()
    {
        var item = Create(Vest) with { Sockets = [new(SocketColour.Abyss)] };
        Assert.DoesNotContain(ItemSend.Commands("Rarity: NORMAL\nPlate Vest", Vest, item, new ModCatalog("missing"), []), c => c.StartsWith("/sockets"));
    }
}

public class CompatibilityTests
{
    [Theory]
    [InlineData("1.0.0+b2737133477b23f27a98b27196189bcad5881bc6", "additional_strength", "implemented")]
    [InlineData("unknown", "additional_strength", "unknown")]
    [InlineData("1.0.0+b2737133477b23f27a98b27196189bcad5881bc6", "local_no_attribute_requirements", "partial")]
    [InlineData("1.0.0+b2737133477b23f27a98b27196189bcad5881bc6", "unverified_fixture_effect", "unknown")]
    public void Passive_effect_status_is_versioned_and_does_not_filter_the_node(string version, string stat, string expected)
    {
        string folder = Directory.CreateTempSubdirectory("evrybuild-compatibility-").FullName;
        try
        {
            Directory.CreateDirectory(Path.Combine(folder, "tables"));
            File.WriteAllText(Path.Combine(folder, "tables/Stats.json"), JsonSerializer.Serialize(new[] { new { Id = stat } }));
            File.WriteAllText(Path.Combine(folder, "tables/PassiveSkills.json"), JsonSerializer.Serialize(new[] { new {
                PassiveSkillGraphId = 11, Id = "Fixture", Name = "Fixture", Stats = new[] { 0 }, Stat1Value = 10,
                SkillPointsGranted = 0, AscendancyKey = (int?)null, Characters = Array.Empty<int>(), IsExpansion = false,
                IsMultipleChoice = false, MasteryGroup = (int?)null } }));
            var build = PathOfBuilding.Parse("<PathOfBuilding><Build className=\"Witch\" level=\"20\"/></PathOfBuilding>");
            var progress = new PathOfBuildingCharacters.Progress(CharacterClass.Witch, 20, 123, [11], [], 0, []);
            var result = Compatibility.Check(build, progress, new PathOfBuildingItems.Result([], [], []), new ItemCatalog(folder), folder, version);
            var finding = Assert.Single(result.Findings);
            Assert.Equal(expected, finding.Status);
            Assert.Equal("kept", finding.Action);
            Assert.Equal(new ushort[] { 11 }, progress.Passives);
        }
        finally { Directory.Delete(folder, true); }
    }
}
