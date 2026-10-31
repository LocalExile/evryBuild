using System.Text.Json;
using GameServer.Core.Protocol.Instance;

public sealed class ModTextTests : IDisposable
{
    readonly string folder = Directory.CreateTempSubdirectory("evrybuild-mod-text-").FullName;
    readonly ModCatalog mods;
    static readonly ItemCatalog.BaseType Armour = new(0, "Metadata/Items/Vest", "Plate Vest", 1, 2, 3, 0, ["Base", "Mods", "Armour"], 0);
    static readonly ItemCatalog.BaseType Ring = new(1, "Metadata/Items/Ring", "Iron Ring", 2, 1, 1, 0, ["Base", "Mods"], 0);
    static readonly Item Rare = ItemCatalog.Create(Armour) with { Rarity = ItemRarity.Rare };

    static readonly (string Id, bool Local)[] Stats =
    [
        ("local_armour", true), ("armour", false), ("local_es", true), ("leech", false), ("recovery", false), ("life", false),
    ];

    public ModTextTests()
    {
        Directory.CreateDirectory(Path.Combine(folder, "tables"));
        File.WriteAllText(Path.Combine(folder, "tables/Stats.json"), JsonSerializer.Serialize(Stats.Select(s => new { s.Id, IsLocal = s.Local })));
        object Row(int row, string id, int generation, int domain, params (int Stat, int Min, int Max)[] stats)
        {
            var values = new Dictionary<string, object?>
            {
                ["Id"] = id, ["HASH16"] = 100 + row, ["Name"] = id, ["Domain"] = domain, ["GenerationType"] = generation, ["Level"] = 1,
                ["Families"] = Array.Empty<int>(), ["SpawnWeight_TagsKeys"] = Array.Empty<int>(), ["SpawnWeight_Values"] = Array.Empty<int>(),
                ["GenerationWeight_TagsKeys"] = Array.Empty<int>(), ["GenerationWeight_Values"] = Array.Empty<int>(), ["IsEssenceOnlyModifier"] = false,
            };
            for (int i = 0; i < stats.Length; i++)
            {
                values[$"StatsKey{i + 1}"] = stats[i].Stat;
                values[$"Stat{i + 1}Min"] = stats[i].Min;
                values[$"Stat{i + 1}Max"] = stats[i].Max;
            }
            values[$"StatsKey{stats.Length + 1}"] = null;
            return values;
        }
        File.WriteAllText(Path.Combine(folder, "tables/Mods.json"), JsonSerializer.Serialize(new[]
        {
            Row(0, "GlobalArmour", 3, 1, (1, 350, 400)),
            Row(1, "LocalArmour", 1, 1, (0, 100, 200)),
            Row(2, "LocalHybrid", 1, 1, (0, 300, 375), (2, 60, 70)),
            Row(3, "Leech", 1, 1, (3, 20, 40)),
            Row(4, "SlowRecovery", 1, 1, (4, -20, -10)),
            Row(5, "UniqueLife", 3, 1, (5, 40, 50)),
            Row(6, "PrefixLife", 1, 1, (5, 40, 50)),
            Row(7, "CrossLife", 1, 1, (5, 1, 1)),
        }));
        mods = new ModCatalog(folder);
    }

    public void Dispose() => Directory.Delete(folder, true);

    static readonly ModText Text = new(new Dictionary<string, string[]>
    {
        ["GlobalArmour"] = ["+(350-400) to Armour"],
        ["LocalArmour"] = ["+(100-200) to Armour"],
        ["LocalHybrid"] = ["+(300-375) to Armour", "+(60-70) to maximum Energy Shield"],
        ["Leech"] = ["(0.2-0.4)% of Damage Leeched as Life"],
        ["SlowRecovery"] = ["(10-20)% reduced Recovery"],
        ["UniqueLife"] = ["+(40-50) to Life"],
        ["PrefixLife"] = ["+(40-50) to Life"],
        ["CrossLife"] = ["Grants Level 1 Ward"],
    });

    IReadOnlyList<ModText.Found> Resolve(ItemCatalog.BaseType type, Item item, params string[] lines) =>
        Text.Resolve([.. lines.Select(l => new ModText.Line(ModSection.Explicit, l))], type, item, mods);

    string Id(ModText.Found found) => mods.ByHash(found.Mod.Hash)!.Id;

    [Fact]
    public void Two_lines_become_one_hybrid_modifier_with_a_value_per_stat()
    {
        var found = Assert.Single(Resolve(Armour, Rare, "+320 to Armour", "+65 to maximum Energy Shield"));
        Assert.Equal("LocalHybrid", Id(found));
        Assert.Equal([320, 65], found.Mod.Values);
        Assert.Equal([0, 1], found.Lines);
    }

    [Fact]
    public void A_catalysed_value_stays_on_the_local_modifier_instead_of_an_in_range_global_one()
    {
        var found = Assert.Single(Resolve(Armour, Rare, "+397 to Armour"));
        Assert.True(mods.ByHash(found.Mod.Hash)!.Stats.All(s => s.Local), Id(found));
        Assert.True(found.OutsideRoll);
        Assert.Equal([397], found.Mod.Values);
    }

    [Fact]
    public void Armour_on_a_ring_is_the_global_stat()
    {
        var ring = ItemCatalog.Create(Ring) with { Rarity = ItemRarity.Unique };
        Assert.Equal("GlobalArmour", Id(Assert.Single(Resolve(Ring, ring, "+380 to Armour"))));
    }

    [Fact]
    public void A_number_shown_in_other_units_is_converted_to_the_stats_range()
    {
        Assert.Equal([30], Assert.Single(Resolve(Ring, Rare, "0.3% of Damage Leeched as Life")).Mod.Values);
    }

    [Fact]
    public void Reduced_text_is_a_negative_stat()
    {
        Assert.Equal([-15], Assert.Single(Resolve(Ring, Rare, "15% reduced Recovery")).Mod.Values);
    }

    [Fact]
    public void A_rare_line_prefers_a_prefix_over_a_unique_modifier_with_the_same_text()
    {
        Assert.Equal("PrefixLife", Id(Assert.Single(Resolve(Ring, Rare, "+45 to Life"))));
    }

    [Fact]
    public void Capitals_do_not_matter()
    {
        Assert.Single(Resolve(Ring, Rare, "15% REDUCED recovery"));
    }

    [Fact]
    public void Each_line_is_used_once_and_unknown_wording_is_left_out()
    {
        var found = Resolve(Ring, Rare, "+45 to Life", "Something new");
        Assert.Equal([0], Assert.Single(found).Lines);
    }

    [Fact]
    public void A_modifier_missing_from_this_client_is_not_used()
    {
        var text = new ModText(new Dictionary<string, string[]> { ["NotInMods"] = ["+(1-2) to Life"] });
        Assert.Empty(text.Resolve([new(ModSection.Explicit, "+1 to Life")], Ring, Rare, mods));
    }

    [Fact]
    public void The_bundled_index_loads_with_hybrids_intact()
    {
        var text = ModText.Embedded;
        Assert.Equal("# to armour", ModText.Wording("+(5-9) to Armour"));
        Assert.Equal(ModText.Wording("+397 to Armour"), ModText.Wording("+(5-9) to Armour"));
        Assert.NotNull(text);
    }
}
