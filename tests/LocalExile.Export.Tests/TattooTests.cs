using System.Text.Json;
using GameServer.Core.Imports;

/// <summary>PoB passive-tree overrides (tattoos) against a small 3.29-shaped data folder.</summary>
public sealed class TattooTests : IDisposable
{
    readonly string folder = Directory.CreateTempSubdirectory("evrybuild-tattoos-").FullName;
    readonly IReadOnlyDictionary<uint, uint[]> graph;

    // A chain from the Witch start; Island is in the tree but connected to nothing.
    const ushort Start = 1, Int1 = 10, Int2 = 11, Dex1 = 12, Notable1 = 20, Notable2 = 21, Acrobatics = 30, PhaseAcrobatics = 31, Island = 50;
    const ushort FirstExtra = 100;
    const int ExtraCount = 60;
    const string HinekoraWarrior = "Tattoo of the Hinekora Warrior", RamakoArcher = "Tattoo of the Ramako Archer",
        JourneySoul = "Journey Tattoo of the Soul", Makanui = "Journey Tattoo of Makanui";

    public TattooTests()
    {
        Directory.CreateDirectory(Path.Combine(folder, "tables"));
        Write("Characters", new[] { new { IntegerId = 3 } });
        Write("ExperienceLevels", new[] { new { Level = 20, Experience = 1000 }, new { Level = 60, Experience = 5000 } });
        Write("Stats", new[] { new { Id = "base_strength" }, new { Id = "base_dexterity" }, new { Id = "base_intelligence" } });
        var passives = new List<Dictionary<string, object?>>
        {
            Node(Start, "Witch", characters: [0]),
            Node(Int1, "Intelligence", stat: 2, value: 10), Node(Int2, "Intelligence", stat: 2, value: 10),
            Node(Dex1, "Dexterity", stat: 1, value: 10),
            Node(Notable1, "Deep Thoughts", stat: 2, value: 30, notable: true), Node(Notable2, "Deep Wisdom", stat: 2, value: 30, notable: true),
            Node(Acrobatics, "Acrobatics", keystone: true), Node(PhaseAcrobatics, "Phase Acrobatics", keystone: true),
            Node(Island, "Intelligence", stat: 2, value: 10),
        };
        for (int i = 0; i < ExtraCount; i++) passives.Add(Node((ushort)(FirstExtra + i), "Intelligence", stat: 2, value: 10));
        Write("PassiveSkills", passives);
        int Row(ushort id) => passives.FindIndex(p => (int)p["PassiveSkillGraphId"]! == id);

        Write("PassiveSkillTattooTargetSets", new[] { ("Small Strength", ""), ("Small Dexterity", ""), ("Small Intelligence", ""), ("Small Attribute", ""),
                ("Notable", "+30 to Strength"), ("Notable", "+30 to Dexterity"), ("Notable", "+30 to Intelligence"), ("Keystone", ""), ("Mastery", ""), ("Ascendancy Notable", "") }
            .Select(set => new { Name = set.Item1, Qualifier = set.Item2 }));
        // BaseItemTypes row = PassiveSkillTattoos.Tattoo; the same index is the item's PassiveSkillOverrides row.
        (string Name, int Set, int? Limit)[] items = [(HinekoraWarrior, 2, null), (RamakoArcher, 1, null), (JourneySoul, 6, null), (Makanui, 7, 6),
            ("Tattoo of the Arohongui Shaman", 2, null), ("Honoured Tattoo of the Wise", 6, 4), ("Loyalty Tattoo of Kaom", 0, 0),
            ("Forbidden Tattoo of the Witch", 9, 40), ("Orb of Alchemy", -1, null)];
        Write("BaseItemTypes", items.Select(item => new { Id = "Metadata/Items/Currency/" + item.Name.Replace(" ", ""), item.Name }));
        Write("PassiveSkillTattoos", items.Select((item, index) => new { Tattoo = index, item.Set, Tribe = 0, Override = index }).Where(row => row.Set >= 0));
        var overrides = items.Select((item, index) => OverrideRow(2, item.Limit, 1000 + index)).ToList();
        overrides.Add(OverrideRow(15, 6, 2000, Row(Acrobatics)));
        overrides.Add(OverrideRow(15, 6, 2001, Row(PhaseAcrobatics)));
        Write("PassiveSkillOverrides", overrides);

        var chain = new List<uint> { Start, Int1, Int2, Dex1, Notable1, Notable2, Acrobatics, PhaseAcrobatics };
        for (int i = 0; i < ExtraCount; i++) chain.Add((uint)(FirstExtra + i));
        var edges = chain.ToDictionary(id => id, _ => new List<uint>());
        for (int i = 1; i < chain.Count; i++) { edges[chain[i - 1]].Add(chain[i]); edges[chain[i]].Add(chain[i - 1]); }
        edges[Island] = [];
        graph = edges.ToDictionary(e => e.Key, e => e.Value.ToArray());
    }

    public void Dispose() => Directory.Delete(folder, true);

    [Fact]
    public void Writes_a_supported_tattoo_on_an_eligible_retained_passive()
    {
        var progress = Prepare(Tattooed(Int1, HinekoraWarrior, "3% increased maximum Energy Shield"), 20, Int1, Int2);
        var tattoo = Assert.Single(progress.Tattoos!);
        Assert.Equal((Int1, HinekoraWarrior), (tattoo.Key, tattoo.Value));
        Assert.Empty(progress.TattooKeystones!);
        Assert.Equal(new ushort[] { Int1, Int2 }, progress.Passives);
        Assert.DoesNotContain(progress.Warnings, w => w.Contains("tattoo", StringComparison.OrdinalIgnoreCase) || w.Contains("override", StringComparison.OrdinalIgnoreCase));
        string save = Save(progress);
        Assert.Contains("\"Tattoos\":{\"10\":\"Tattoo of the Hinekora Warrior\"}", save);
        Assert.DoesNotContain("TattooKeystones", save);
    }

    [Fact]
    public void Journey_tattoos_repeat_without_a_group_limit()
    {
        var progress = Prepare(Tattooed(Notable1, JourneySoul) + Tattooed(Notable2, JourneySoul), 20, Int1, Int2, Dex1, Notable1, Notable2);
        Assert.Equal([Notable1, Notable2], progress.Tattoos!.Keys.Order());
        Assert.All(progress.Tattoos.Values, name => Assert.Equal(JourneySoul, name));
        Assert.DoesNotContain(progress.Warnings, w => w.StartsWith("Skipped tattoo", StringComparison.Ordinal));
    }

    [Theory]
    [InlineData(RamakoArcher, Int1, "replaces Small Dexterity passives")]
    [InlineData(JourneySoul, Int1, "replaces Notable (+30 to Intelligence) passives")]
    [InlineData(HinekoraWarrior, Notable1, "replaces Small Intelligence passives")]
    public void Skips_a_tattoo_whose_target_set_does_not_match(string name, int node, string reason)
    {
        var progress = Prepare(Tattooed((ushort)node, name), 20, Int1, Int2, Dex1, Notable1);
        Assert.Empty(progress.Tattoos!);
        Assert.Contains((ushort)node, progress.Passives);
        Assert.Contains(progress.Warnings, w => w.StartsWith($"Skipped tattoo '{name}' on passive {node}", StringComparison.Ordinal)
            && w.Contains(reason, StringComparison.Ordinal));
    }

    [Theory]
    [InlineData("Runegraft of Treachery", Int1, "Skipped Runegraft 'Runegraft of Treachery' on passive 10: Runegrafts have no native mapping")]
    [InlineData("Tattoo of the Arohongui Shaman", Int1, "the server has no effect for it yet; the passive keeps its ordinary effect")]
    [InlineData("Mystery Ink", Int1, "Skipped unknown passive-tree override 'Mystery Ink' on passive 10 (Intelligence): not a 3.29 tattoo")]
    [InlineData("", Int1, "Skipped an unnamed passive-tree override on passive 10 (Intelligence): not a 3.29 tattoo")]
    [InlineData("Loyalty Tattoo of Kaom", Int1, "Loyalty tattoos are not supported by the server yet")]
    [InlineData("Honoured Tattoo of the Wise", Notable1, "Honoured attribute notables are not supported by the server yet")]
    [InlineData("Forbidden Tattoo of the Witch", Int1, "event-only Forbidden tattoos are not supported by the server")]
    public void Skips_unsupported_overrides_with_an_explicit_warning(string name, int node, string warning)
    {
        var progress = Prepare(Tattooed((ushort)node, name, "Some effect text that must never become stats"), 20, Int1, Int2, Dex1, Notable1);
        Assert.Empty(progress.Tattoos!);
        Assert.Contains((ushort)node, progress.Passives);
        Assert.Contains(progress.Warnings, w => w.Contains(warning, StringComparison.Ordinal));
        Assert.DoesNotContain("Tattoo", Save(progress));
    }

    [Fact]
    public void Maps_Journey_Tattoo_of_Makanui_to_the_chosen_keystone()
    {
        var progress = Prepare(Tattooed(Acrobatics, "Phase Acrobatics"), 20, Int1, Int2, Dex1, Notable1, Notable2, Acrobatics);
        Assert.Equal(Makanui, Assert.Single(progress.Tattoos!).Value);
        var keystone = Assert.Single(progress.TattooKeystones!);
        Assert.Equal((Acrobatics, PhaseAcrobatics), (keystone.Key, keystone.Value));
        string save = Save(progress);
        Assert.Contains("\"Tattoos\":{\"30\":\"Journey Tattoo of Makanui\"}", save);
        Assert.Contains("\"TattooKeystones\":{\"30\":31}", save);
    }

    [Fact]
    public void Limits_keystone_tattoos_to_one_and_rejects_the_node_s_own_keystone()
    {
        ushort[] all = [Int1, Int2, Dex1, Notable1, Notable2, Acrobatics, PhaseAcrobatics];
        var progress = Prepare(Tattooed(Acrobatics, "Phase Acrobatics") + Tattooed(PhaseAcrobatics, "Acrobatics"), 20, all);
        Assert.Equal([Acrobatics], progress.Tattoos!.Keys);
        Assert.Contains(progress.Warnings, w => w.StartsWith($"Skipped tattoo '{Makanui}' (Acrobatics) on passive {PhaseAcrobatics}", StringComparison.Ordinal)
            && w.Contains("only one Keystone Tattoo can be applied", StringComparison.Ordinal));
        progress = Prepare(Tattooed(Acrobatics, "Acrobatics"), 20, all);
        Assert.Empty(progress.Tattoos!);
        Assert.Contains(progress.Warnings, w => w.Contains("the chosen keystone is the tattooed keystone itself", StringComparison.Ordinal));
    }

    [Fact]
    public void Skips_overrides_on_passives_that_were_not_retained()
    {
        var progress = Prepare(Tattooed(Island, HinekoraWarrior) + Tattooed(999, HinekoraWarrior) + Tattooed(Int1, HinekoraWarrior), 20, Int1, Island);
        Assert.Equal([Int1], progress.Tattoos!.Keys);
        Assert.Contains($"Skipped tattoo '{HinekoraWarrior}' on passive {Island}: the passive was not retained.", progress.Warnings);
        Assert.Contains($"Skipped tattoo '{HinekoraWarrior}' on passive 999: the passive was not retained.", progress.Warnings);
    }

    [Fact]
    public void Caps_tattoos_at_the_server_s_fifty()
    {
        var nodes = new List<ushort> { Int1, Int2, Dex1, Notable1, Notable2, Acrobatics, PhaseAcrobatics };
        string overrides = Tattooed(Int1, HinekoraWarrior) + Tattooed(Int2, HinekoraWarrior);
        for (int i = 0; i < ExtraCount; i++)
        {
            nodes.Add((ushort)(FirstExtra + i));
            overrides += Tattooed((ushort)(FirstExtra + i), HinekoraWarrior);
        }
        var progress = Prepare(overrides, 60, [.. nodes]);
        Assert.Equal(PathOfBuildingTattoos.TotalLimit, progress.Tattoos!.Count);
        Assert.Equal(12, progress.Warnings.Count(w => w.Contains("a character can have at most 50 tattoos", StringComparison.Ordinal)));
        Assert.Contains(Int1, progress.Tattoos.Keys);
        Assert.DoesNotContain((ushort)(FirstExtra + ExtraCount - 1), progress.Tattoos.Keys);
    }

    [Fact]
    public void Omits_the_tattoo_fields_when_there_are_none()
    {
        var progress = Prepare("", 20, Int1);
        Assert.Empty(progress.Tattoos!);
        Assert.DoesNotContain("Tattoo", Save(progress));
    }

    [Fact]
    public void Warns_once_when_the_tattoo_tables_are_missing()
    {
        File.Delete(Path.Combine(folder, "tables", "PassiveSkillTattoos.json"));
        var progress = Prepare(Tattooed(Int1, HinekoraWarrior) + Tattooed(Int2, HinekoraWarrior), 20, Int1, Int2);
        Assert.Empty(progress.Tattoos!);
        Assert.Equal(1, progress.Warnings.Count(w => w.StartsWith("Skipped 2 passive-tree override(s): the data folder has no tattoo tables", StringComparison.Ordinal)));
    }

    PathOfBuildingCharacters.Progress Prepare(string overrides, int level, params ushort[] nodes) =>
        PathOfBuildingCharacters.Prepare(PathOfBuilding.Parse($"""
            <PathOfBuilding><Build className="Witch" level="{level}" />
              <Spec classId="3" ascendClassId="0" treeVersion="3_29" nodes="{string.Join(',', nodes)}">
                <Overrides>{overrides}</Overrides>
              </Spec>
            </PathOfBuilding>
            """), folder, () => graph);

    static string Tattooed(ushort node, string name, string text = "") =>
        $"""<Override nodeId="{node}" dn="{name}" icon="Art/icon.png" activeEffectImage="Art/bg.png">{text}</Override>""";

    static string Save(PathOfBuildingCharacters.Progress progress) =>
        JsonSerializer.Serialize(progress.ToSave(new PathOfBuildingItems.Result([], [], [])));

    static Dictionary<string, object?> Node(ushort id, string name, int? stat = null, int value = 0, bool notable = false,
        bool keystone = false, int[]? characters = null) => new()
    {
        ["PassiveSkillGraphId"] = (int)id, ["Id"] = $"{name.Replace(' ', '_').ToLowerInvariant()}{id}", ["Name"] = name,
        ["Stats"] = stat is int index ? new[] { index } : Array.Empty<int>(), ["Stat1Value"] = value,
        ["SkillPointsGranted"] = 0, ["AscendancyKey"] = null, ["Characters"] = characters ?? Array.Empty<int>(),
        ["IsExpansion"] = false, ["IsMultipleChoice"] = false, ["MasteryGroup"] = null,
        ["IsNotable"] = notable, ["IsKeystone"] = keystone,
    };

    static Dictionary<string, object?> OverrideRow(int type, int? limit, int hash, int? allocated = null) => new()
    {
        ["Type"] = type, ["Limit"] = limit, ["HASH16"] = hash, ["AllocatedPassiveSkill"] = allocated,
        ["RequiresAdjacent"] = 0, ["MaxAdjacent"] = 0,
    };

    void Write<T>(string table, IEnumerable<T> rows) =>
        File.WriteAllText(Path.Combine(folder, "tables", table + ".json"), JsonSerializer.Serialize(rows));
}
