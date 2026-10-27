# evryBuild - POB for LocalExile

The [evryBuild project](https://github.com/evrydayjunglist/evryBuild) is a fork of the
[Path of Building Community Fork](https://github.com/PathOfBuildingCommunity/PathOfBuilding),
based on its **master** release **2.67.2**.
It keeps PoB's build planner and adds **Forge Character** in **Import/Export Build** to preview or create a character
on a configurable LocalExile server.

The source checkout and runnable application are separate folders.
The portable application has its own settings and builds, so your normal PoB installation can stay dedicated to live PoE 1.
LocalExile's receiver is a separate server component; its current import compatibility determines which builds can be forged.
See [LocalExile setup and compatibility](docs/LocalExile.md) before importing a build.

<p float="middle">
  <img alt="Tree tab" src="https://github.com/user-attachments/assets/0826b7ab-84ba-440f-be52-2f216f13e75c" width="48%" />
  <img alt="Items tab" src="https://github.com/user-attachments/assets/e5af1326-7e22-43d8-ab12-aa5500da611a" width="48%" />
</p>

### Features
* Comprehensive offence + defence calculations:
  * Calculate your skill DPS, damage over time, life/mana/ES totals and much more!
  * Can factor in auras, buffs, charges, curses, monster resistances and more, to estimate your effective DPS
  * Also calculates life/mana reservations
  * Shows a summary of character stats in the side bar, as well as a detailed calculations breakdown tab which can show you how the stats were derived
  * Supports all skills and support gems, and most passives and item modifiers
    * Throughout the program, supported modifiers will show in blue and unsupported ones in red
  * Full support for minions
  * Support for party play and support builds
* Passive skill tree planner:
  * Support for jewels including most radius/conversion and timeless jewels
  * Features alternate path tracing (mouse over a sequence of nodes while holding shift, then click to allocate them all)
  * Fully integrated with the offence/defence calculations; see exactly how each node will affect your character!
  * Can import PathOfExile.com and PoEPlanner.com passive tree links; links shortened with PoEURL.com also work
* Skill planner:
  * Add any number of main or supporting skills to your build
  * Supporting skills (auras, curses, buffs) can be toggled on and off
  * Automatically applies Socketed Gem modifiers from the item a skill is socketed into
  * Automatically applies support gems granted by items
* Item planner:
  * Add items from in game by copying and pasting them straight into the program!
  * Automatically adds quality to non-corrupted items
  * Search the trade site for the most impactful items
  * Fully integrated with the offence/defence calculations; see exactly how much of an upgrade a given item is!
  * Contains a searchable database of all uniques that are currently in game (and some that aren't yet!)
    * You can choose the modifier rolls when you add a unique to your build
    * Includes all league-specific items and legacy variants
  * Features an item crafting system:
    * You can select from any of the game's base item types
    * You can select prefix/suffix modifiers from lists
    * Custom modifiers can be added, with Master and Essence modifiers available
  * Also contains a database of rare item templates:
    * Allows you to create rare items for your build to approximate the gear you will be using
    * Choose which modifiers appear on each item, and the rolls for each modifier, to suit your needs
    * Has templates that should cover the majority of builds
* Other features:
  * You can import passive tree, items, and skills from existing characters
  * Share builds with other users by generating a share code
  * evryBuild keeps upstream automatic updates disabled so they cannot overwrite this fork's integration

## Run evryBuild

On Windows, use Python 3.10 or newer and run this from the source checkout's root:

```powershell
python scripts/package-evrybuild.py --destination '..\evryBuild-app'
```

Choose a destination folder that does not already exist.
The command packages this fork's Lua, assets and existing compiled runtime into a separate application containing
**evryBuild.exe**.
It does not require an installed PoB copy or copy personal settings and builds.
Open the output folder in File Explorer and double-click **evryBuild.exe**.

For the LocalExile button, server connection, account token and packaging options, follow
[the evryBuild guide](docs/LocalExile.md).
The unmodified upstream application's downloads remain available from
[Path of Building Community releases](https://github.com/PathOfBuildingCommunity/PathOfBuilding/releases).

## Changelog
You can find the full version history [here](CHANGELOG.md).

## Contribute
Keep evryBuild changes focused on this fork's branding, packaging and LocalExile connection.
The [LocalExile guide](docs/LocalExile.md#development-checks) lists its focused checks.
The existing [contribution guide](CONTRIBUTING.md) describes upstream PoB development and contribution procedures.

## Licence
[MIT](https://opensource.org/licenses/MIT)

For 3rd-party licences, see [LICENSE](LICENSE.md).
The licencing information is considered to be part of the documentation.
