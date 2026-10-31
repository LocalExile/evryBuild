# Parity check

Compares what Path of Building and a LocalExile checkout calculate for one saved build. It is a developer tool for
finding stats the server gets wrong or does not implement, and it is not part of the portable application.

```powershell
.\scripts\build-exporter.ps1
python scripts/parity.py --localexile C:\LocalExile --build C:\Builds\Example.xml
```

It needs the .NET 10 SDK, Python 3.10+ and a LocalExile checkout with its game data extracted.
A run takes about 10 seconds, plus about 20 for the first build of the server probe. `--no-build` reuses the probe.
`--show-skipped` lists the modifier lines the exporter could not write, and `--json <file>` saves the result.

No client, Gateway or real save is involved, and it does not change your LocalExile checkout. It is safe while you play.
PoB runs headless through the bundled runtime. The build is exported to a temporary database, and
`tools/LocalExile.Parity` runs the checkout's own login path on it (`PrepareCharacterForArea`, then `PoolsFor`).
That project builds against your checkout under the assembly name the Gateway's `InternalsVisibleTo` already trusts,
so it can break when those internals change.

## Reading the report

Both sides must describe one character, so PoB is first reduced to what the server received:

| Left out of PoB | Why |
|---|---|
| Passive jewels, ascendancy, tattoos and cluster nodes | The exporter does not write them. PoB uses the saved passive list. |
| Skills and auras | A fresh server character has none active. |
| Active flasks, bandit and Pantheon | A fresh server character has none of them. |
| The Kitava resistance penalties | They need quest flags the character does not have. |
| Modifier lines the exporter could not write | The server never received them. Lines match by base item and wording. |
| Items the server made inactive | They are listed as one finding, so the table shows formulas only. |

Reading a line in the table:

- **Blank status:** both sides agree.
- **rounding:** they differ by 1.
- **mismatch:** a real difference. Check it before calling it a bug: PoB is the project's formula reference, not
  proof of the official game.
- **missing:** one side did not report this stat.

A low attribute can make the server switch off an item, usually through a socketed gem whose requirement is not met.
That happens more often here than in game, because the attributes from jewels and skipped modifiers are gone.

To find the cause of a mismatch, list PoB's sources for that stat with `modDB:Tabulate` and compare them with the
server's total. A missing percentage often points straight at one passive or mastery.

## Limits

The check covers the character sheet: attributes, life, mana, energy shield, ward, armour, evasion, accuracy,
resistances, block and spell suppression. Skill damage, speed and critical strikes are not compared yet.
Builds that rely on modifiers the exporter skips test less of the server, because those lines leave both sides.
