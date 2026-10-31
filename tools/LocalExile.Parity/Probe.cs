using System.Text.Json;
using GameServer.Core.World;

namespace LocalExile.Parity;

/// <summary>
/// Prints what a LocalExile checkout computes for a saved character, through the path a real login takes
/// (PrepareCharacterForArea, then PoolsFor). No client or network is involved. Run it from the checkout's root:
/// the Gateway's game data paths are relative to it. "init" creates an empty database with the Gateway's own schema.
/// </summary>
static class Probe
{
    static int Main(string[] args)
    {
        try
        {
            if (args is ["init", var database]) { Saves.Open(database); return 0; }
            if (args is not ["stats", var saves, var character, var classId])
                throw new ArgumentException("Usage: init <database> | stats <database> <character> <class id>");
            Saves.Open(saves);
            Console.WriteLine(JsonSerializer.Serialize(Read(character, int.Parse(classId))));
            return 0;
        }
        catch (Exception e)
        {
            Console.Error.WriteLine(e);
            return 1;
        }
    }

    static object Read(string character, int classId)
    {
        var state = new ClientState(new(AreaLayouts.LioneyesWatch, "ParityTown", 128, 128, 32, 32, null, []), 0, 1)
            { Character = character, Account = character, League = "Standard", ClassRow = ClassRow(classId) };
        int level = Program.PrepareCharacterForArea("parity", state, 1);
        var p = Program.PoolsFor(state, level);
        var items = PlayerInventories.For(character, Program.Items);
        var inactive = Program.InactiveItems.GetValueOrDefault(character) ?? [];
        var equipped = Enumerable.Range(1, 15).Select(row => (byte)row).Where(row => row != PlayerInventories.Cursor)
            .SelectMany(row => items.Items(row).Select(i =>
            {
                var type = Program.Items.ByHash(i.Item.TypeHash);
                var defences = type is not null && Program.Items.Defences(type) is { } values
                    ? ItemDefences.Calculate(i.Item, values, Program.Items.Mods) : default;
                return new { Row = (int)row, type?.Name, Inactive = inactive.Contains(i.Id), defences.Armour, defences.Evasion, defences.EnergyShield };
            }));
        return new
        {
            Equipment = equipped.ToList(),
            p.Level, Life = (long)p.Life, Mana = (long)p.Mana, EnergyShield = (long)p.EnergyShield, Ward = (long)p.Ward,
            p.Strength, p.Dexterity, p.Intelligence, p.Armour, p.ArmourPct, p.Evasion, p.EvasionPct, p.EnergyShieldPct, p.Accuracy,
            p.FireResistance, p.ColdResistance, p.LightningResistance, p.ChaosResistance,
            p.FireMaxResistance, p.ColdMaxResistance, p.LightningMaxResistance, p.ChaosMaxResistance,
            p.BlockChance, p.SpellBlockChance, p.SpellSuppressionChance, p.MovementVelocityPct,
            Passives = state.Passives.Count, Masteries = state.MasteryEffects.Count,
        };
    }

    // Saves use the class's IntegerId; a connection uses its Characters.dat row.
    static int ClassRow(int classId)
    {
        using var rows = JsonDocument.Parse(File.ReadAllBytes(Path.Combine("data", "tables", "Characters.json")));
        int row = 0;
        foreach (var character in rows.RootElement.EnumerateArray())
        {
            if (character.GetProperty("IntegerId").GetInt32() == classId) return row;
            row++;
        }
        throw new ArgumentException($"data/tables/Characters.json has no class {classId}.");
    }
}
