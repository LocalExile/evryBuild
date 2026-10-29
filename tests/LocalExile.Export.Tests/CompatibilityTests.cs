using System.Text.Json;
using GameServer.Core.Accounts;
using GameServer.Core.Imports;

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
