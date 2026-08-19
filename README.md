# Keystone Meta

See what the highest-ranked Mythic+ groups are actually playing today.

Keystone Meta is a standalone World of Warcraft addon that ships a pre-generated, daily-updated snapshot of specialization representation in ranked Mythic+ runs. The addon never calls the internet from inside the game.

**Keystone Meta shows specialization representation among sampled top-ranked completed Mythic+ runs. Representation does not measure success rate or prove specialization strength.**

Popularity is not the same as power or success rate. This is not a tier list, a win-rate tracker, or an official Raider.IO product.

## What it answers

- Which tank, healer, and DPS specializations appear most often in the sampled top-ranked runs?
- How does representation differ between dungeons?
- How did a specialization’s role share change since the previous valid daily update?
- What is the highest timed key in the sample containing that specialization?
- In which dungeons is your current specialization most or least represented?
- How many completed runs and role seats support the displayed value?

## Usage

- `/kmeta` or `/keystonemeta` toggles the compact companion panel.
- Left-click the minimap button to toggle the same panel.
- The panel attaches to the right of Blizzard’s Mythic+ Challenges frame when that frame is open, and can be dragged as a standalone window when it is not.
- The default view follows your current specialization unless you override it by clicking the specialization name.
- Click a populated dungeon row to open a Dungeon Detail popout for that dungeon.

## Data

A Python generator queries Raider.IO’s published Developer API and writes `KeystoneMetaData.lua`.

- Dataset: world / global
- Default window: full season (`affixes=all`)
- Target: 500 completed ranked runs per dungeon, or the largest consistent target that fits the daily budget
- Actual sample sizes are stored and shown per dungeon

See [docs/DATA-METHODOLOGY.md](docs/DATA-METHODOLOGY.md) for exact formulas, limitations, and season-rollover rules.

## Attribution

Ranked-run data comes from [Raider.IO](https://raider.io). Keystone Meta is a community addon and is not affiliated with or endorsed by Raider.IO.

## Requirements

- World of Warcraft Retail 12.1 (`Interface: 120100`)
- No dependency on Keystone Cutoffs or any other addon

## Installation

Install via [CurseForge](https://www.curseforge.com/wow/addons/keystonemeta) or your addon manager after the project is approved.

## Local generation

```text
python -m unittest discover -s tests -v
python update_keystone_meta.py --affix-mode season --target-runs 500
```

`RAIDER_IO_API_KEY` is optional. The public Raider.IO API works without it. If you set a GitHub secret, it must be a Raider.IO API key, not the API base URL. Do not paste keys into chat, commits, or fixtures.
