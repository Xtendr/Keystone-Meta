# Keystone Meta data methodology

Keystone Meta reports **observed representation** in a defined sample of completed ranked Mythic+ runs. It does not measure success rate, simulate power, or claim that one specialization is objectively stronger than another.

> Keystone Meta shows specialization representation among sampled top-ranked completed Mythic+ runs. Representation does not measure success rate or prove specialization strength.

## Source

Only Raider.IO’s published Developer API is used.

- Documentation: https://raider.io/api
- Static data: `GET https://raider.io/api/v1/mythic-plus/static-data?expansion_id={id}`
- Ranked runs: `GET https://raider.io/api/v1/mythic-plus/runs?season={slug}&region=world&dungeon={slug}&affixes={all|current}&page={n}`
- Current affixes: `GET https://raider.io/api/v1/mythic-plus/affixes?region=us&locale=en`

The addon never performs HTTP. Website scraping, undocumented endpoints, and third-party meta sites are out of scope.

## What “top-ranked completed runs” means

The generator reads Raider.IO’s ranked-runs leaderboard for one season, one dungeon, world scope, and one affix mode. Pages are 0-indexed and contain 20 runs each. The first N pages are taken until the configured target is reached or a page is empty.

A run is valid when all of the following are true:

- It belongs to the expected season and dungeon.
- `status` is `finished`.
- `mythic_level` is a finite number ≥ 2.
- `num_chests` ≥ 1 (timed).
- Roster data can resolve at least one seat.
- For `current` mode, `weekly_modifiers` IDs match the published current affix set.
- It is not a duplicate `keystone_run_id` inside the fetched sample.

Deduplication key: `keystone_run_id`. That identifier is used only during generation and is never written into packaged Lua.

## Sample size

The configured target starts at **500 runs per dungeon**. The generator does not silently reduce that target. If the daily request budget cannot safely fetch 500, the chosen target is recorded in `scope.targetRunsPerDungeon` and in each dungeon’s `sample.requestedRuns`. Actual accepted runs are stored in `sample.validRuns`.

v1 ships the **world** dataset. Regional datasets are optional later and are never merged into world numbers.

## Affix modes

- `season` queries `affixes=all` (ranked runs across the active season).
- `current` queries `affixes=current` (the active weekly combination) only when the API returns that set clearly.

These modes are never merged. As of 2026-08-15, `current` returned empty leaderboards, so v1 packages `season` and hides the unused selector.

## Metrics

For each dungeon and role:

- **Appearance count** = resolved roster seats occupied by that specialization.
- **Role share** = specialization appearances in that role ÷ all resolved sampled seats for that role × 100.
- **Run presence** = valid sampled runs containing at least one player of that specialization ÷ valid sampled runs × 100. A run is counted once even if two players use the same spec.
- **Highest key** = highest Mythic level among valid sampled runs containing that specialization. Label: “Highest key observed in this sample.”
- **Representation rank** = order by role share inside the role, ties broken by Blizzard specialization ID ascending.
- **Daily movement** = current role share − previous valid role share, in **percentage points**. If the previous snapshot is older than 36 hours, the UI says “Change since last valid update.”

Unknown or incomplete roster seats are not assigned to a specialization. Their count is stored as `unresolvedSeats`.

## Specialization identity

Raider.IO class/spec slugs are mapped to Blizzard specialization IDs. An unknown pair fails the snapshot. If a Raider.IO spec id disagrees with the mapped Blizzard id, generation fails. Generated data never stores character names, realms, guilds, profile URLs, run IDs, or raw rosters.

## Sparse and opening-week data

Dungeon statuses:

- `ok` — enough valid runs to display representation.
- `insufficient_data` — fewer than the minimum useful sample (starting threshold: 20 valid runs).
- `stale_retained` — reserved for same-season retained rows.
- `pending_season_data` — the season is known but ranked runs are not available yet.

Missing data is never shown as 0% representation. The UI says “Not enough ranked runs yet.” A completely empty fetch for the **same** season does not overwrite a useful known-good file. An empty fetch for a **newly selected** season writes `pending_season_data` with the new dungeon identities instead of keeping the previous season on screen. Previous-season numbers are never presented as the new season.

## Season discovery

The generator probes static-data expansion IDs `11`, then `12`, then `10`, and selects the newest main season whose earliest regional start is in the past. The world dataset does not wait for every region. `KEYSTONE_META_SEASON` may pin a discovered slug.

Midnight Season 2 dungeon identities are taken from Raider.IO static data when that season is selected. They are not invented in the addon.

## Fail-closed generation

A candidate is rejected when the season is missing, dungeons are missing or malformed, the response shape is wrong, the region or affix mode does not match, role counts are impossible, numbers are non-finite or negative, role shares are invalid, generated Lua contains identifying fields, coverage collapses versus the previous same-season snapshot, validation fails, or the rate-limit reserve would be exceeded. A same-season candidate with zero useful runs preserves the previous known-good file. A newly selected season with zero useful runs writes `pending_season_data` instead of showing last season as current.

Failed generation leaves the previous known-good `KeystoneMetaData.lua` untouched. Timestamp-only changes do not replace the file and do not create a release.

## Attribution

Data source: [Raider.IO](https://raider.io). Required community use of the published API, with name-and-link attribution. Keystone Meta is not an official Raider.IO ranking.
