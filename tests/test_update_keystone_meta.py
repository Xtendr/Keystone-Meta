import importlib.util
import io
import json
import os
import tempfile
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "synthetic"
SPEC = importlib.util.spec_from_file_location("update_keystone_meta", ROOT / "update_keystone_meta.py")
UPDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(UPDATE)


def load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def iso(day: int, hour: int = 0) -> str:
    return f"2026-08-{day:02d}T{hour:02d}:00:00Z"


def member(role: str, class_slug: str, spec_slug: str, spec_id: int, name: str = "SyntheticPlayer") -> dict:
    return {
        "role": role,
        "isBanned": False,
        "character": {
            "name": name,
            "realm": "SyntheticRealm",
            "class": {"id": 1, "name": class_slug, "slug": class_slug},
            "spec": {"id": spec_id, "name": spec_slug, "slug": spec_slug},
        },
    }


def ranking(
    run_id: int,
    *,
    season: str = "season-mn-1",
    dungeon_slug: str = "maisara-caverns",
    challenge_mode_id: int = 560,
    level: int = 16,
    chests: int = 1,
    status: str = "finished",
    roster: list | None = None,
    modifiers: list | None = None,
) -> dict:
    return {
        "rank": 1,
        "score": 12.0,
        "run": {
            "keystone_run_id": run_id,
            "keystone_team_id": run_id + 1000,
            "logged_run_id": run_id + 2000,
            "season": season,
            "status": status,
            "mythic_level": level,
            "num_chests": chests,
            "completed_at": "2026-08-01T12:00:00.000Z",
            "weekly_modifiers": modifiers or [
                {"id": 9, "name": "Tyrannical"},
                {"id": 10, "name": "Fortified"},
            ],
            "dungeon": {
                "id": 2001,
                "slug": dungeon_slug,
                "name": "Maisara Caverns",
                "short_name": "MC",
                "map_challenge_mode_id": challenge_mode_id,
            },
            "roster": roster or [
                member("tank", "druid", "guardian", 104),
                member("healer", "priest", "discipline", 256),
                member("dps", "mage", "frost", 64),
                member("dps", "warlock", "destruction", 267),
                member("dps", "evoker", "augmentation", 1473),
            ],
        },
    }


def page_payload(rows: list, *, page: int = 0, affixes: str = "all") -> dict:
    return {
        "rankings": rows,
        "params": {
            "affixes": affixes,
            "dungeon": "maisara-caverns",
            "page": page,
            "region": "world",
            "season": "season-mn-1",
            "access_key": "",
        },
    }


def standard_roster(dps_spec: tuple[str, str, int] = ("mage", "frost", 64)) -> list:
    class_slug, spec_slug, spec_id = dps_spec
    return [
        member("tank", "druid", "guardian", 104),
        member("healer", "priest", "discipline", 256),
        member("dps", class_slug, spec_slug, spec_id),
        member("dps", "warlock", "destruction", 267),
        member("dps", "evoker", "augmentation", 1473),
    ]


class CredentialTests(TestCase):
    def test_absent_key_is_logged_without_secret_output(self):
        stream = io.StringIO()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RAIDER_IO_API_KEY", None)
            UPDATE.log_credential_status(stream)
        text = stream.getvalue()
        self.assertIn("absent", text)
        self.assertNotIn("Token", text)

    def test_present_key_is_never_written_to_logs_or_headers_dump(self):
        secret = "super-secret-test-key-not-for-fixtures"
        stream = io.StringIO()
        with patch.dict(os.environ, {"RAIDER_IO_API_KEY": secret}):
            UPDATE.log_credential_status(stream)
            headers = UPDATE.build_headers()
        text = stream.getvalue()
        self.assertIn("present", text)
        self.assertNotIn(secret, text)
        self.assertEqual(headers["Authorization"], f"Token {secret}")

    def test_generator_does_not_read_dotenv_files(self):
        text = Path(__file__).resolve().parents[1].joinpath("update_keystone_meta.py").read_text(encoding="utf-8")
        self.assertNotIn("load_local_env", text)
        self.assertNotIn('".env"', text)
        self.assertNotIn("dotenv", text.lower())


class HttpClientTests(TestCase):
    def test_401_hard_fails_without_retry(self):
        calls = {"n": 0}

        def fake_urlopen(_req, timeout=60):
            calls["n"] += 1
            raise urllib.error.HTTPError("https://raider.io/api", 401, "Unauthorized", hdrs=None, fp=None)

        client = UPDATE.HttpClient(budget=20, reserve=2, delay=0, sleep_fn=lambda _s: None, urlopen_fn=fake_urlopen)
        with self.assertRaises(UPDATE.GeneratorError) as ctx:
            client.get_json("https://raider.io/api/v1/mythic-plus/runs")
        self.assertEqual(calls["n"], 1)
        self.assertIn("rejected-credential", str(ctx.exception))
        self.assertIn("HTTP 401", str(ctx.exception))

    def test_429_retries_with_backoff_then_succeeds(self):
        sleeps: list[float] = []
        calls = {"n": 0}

        class FakeResp:
            def read(self):
                return b'{"ok": true}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(_req, timeout=60):
            calls["n"] += 1
            if calls["n"] < 3:
                raise urllib.error.HTTPError("https://raider.io/api", 429, "Too Many", hdrs=None, fp=None)
            return FakeResp()

        client = UPDATE.HttpClient(budget=20, reserve=2, delay=0, sleep_fn=sleeps.append, urlopen_fn=fake_urlopen)
        payload = client.get_json("https://raider.io/api/v1/mythic-plus/runs")
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(calls["n"], 3)
        self.assertEqual(sleeps, [1, 2])

    def test_budget_reserve_stops_before_write(self):
        client = UPDATE.HttpClient(budget=5, reserve=2, delay=0, sleep_fn=lambda _s: None)
        client.used = 3
        with self.assertRaises(UPDATE.GeneratorError) as ctx:
            client._reserve_request()
        self.assertIn("safety reserve", str(ctx.exception))


class SeasonDiscoveryTests(TestCase):
    def setUp(self):
        self.static = load_json("static_data.json")

    def test_keeps_season_one_before_season_two_starts(self):
        now = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
        selected = UPDATE.select_release_season(self.static, now)
        self.assertEqual("season-mn-1", selected["slug"])

    def test_rolls_to_season_two_after_first_region_starts(self):
        now = datetime(2026, 8, 18, 16, tzinfo=timezone.utc)
        selected = UPDATE.select_release_season(self.static, now)
        self.assertEqual("season-mn-2", selected["slug"])

    def test_override_is_validated(self):
        with patch.dict(os.environ, {UPDATE.SEASON_OVERRIDE_ENV: "season-mn-2"}):
            selected = UPDATE.select_release_season(
                self.static, datetime(2026, 8, 15, tzinfo=timezone.utc)
            )
        self.assertEqual("season-mn-2", selected["slug"])

    def test_unknown_override_fails(self):
        with patch.dict(os.environ, {UPDATE.SEASON_OVERRIDE_ENV: "season-nope"}):
            with self.assertRaises(UPDATE.GeneratorError):
                UPDATE.select_release_season(self.static)

    def test_dungeon_discovery_and_duplicate_rejection(self):
        season = UPDATE.select_release_season(
            self.static, datetime(2026, 8, 15, tzinfo=timezone.utc)
        )
        dungeons = UPDATE.season_dungeons(season)
        self.assertEqual([560, 585], [d["challengeModeID"] for d in dungeons])
        broken = {
            "dungeons": [
                {"challenge_mode_id": 560, "slug": "a", "name": "A"},
                {"challenge_mode_id": 560, "slug": "b", "name": "B"},
            ]
        }
        with self.assertRaises(UPDATE.GeneratorError):
            UPDATE.season_dungeons(broken)


class MappingAndRosterTests(TestCase):
    def test_maps_devourer_and_frost_by_slug(self):
        self.assertEqual(64, UPDATE.map_spec("mage", "frost", 64))
        self.assertEqual(1480, UPDATE.map_spec("demon-hunter", "devourer", 1480))

    def test_unknown_spec_fails_closed(self):
        with self.assertRaises(UPDATE.GeneratorError):
            UPDATE.map_spec("mage", "timewalker", 999)

    def test_spec_id_mismatch_fails_closed(self):
        with self.assertRaises(UPDATE.GeneratorError):
            UPDATE.map_spec("mage", "frost", 12)

    def test_incomplete_or_banned_seats_are_unresolved(self):
        self.assertIsNone(UPDATE.resolve_seat({"role": "dps"}))
        banned = member("dps", "mage", "frost", 64)
        banned["isBanned"] = True
        self.assertIsNone(UPDATE.resolve_seat(banned))
        missing_spec = member("dps", "mage", "frost", 64)
        missing_spec["character"]["spec"] = {}
        self.assertIsNone(UPDATE.resolve_seat(missing_spec))


class RunFilterTests(TestCase):
    def test_rejects_malformed_and_untimed_runs(self):
        kwargs = dict(
            season_slug="season-mn-1",
            dungeon_slug="maisara-caverns",
            challenge_mode_id=560,
            affix_mode="season",
            current_ids=None,
        )
        self.assertIsNone(UPDATE.is_valid_run({}, **kwargs))
        self.assertIsNone(UPDATE.is_valid_run(ranking(1, status="in_progress"), **kwargs))
        self.assertIsNone(UPDATE.is_valid_run(ranking(1, chests=0), **kwargs))
        self.assertIsNone(UPDATE.is_valid_run(ranking(1, level=1), **kwargs))
        self.assertIsNone(UPDATE.is_valid_run(ranking(1, season="season-mn-2"), **kwargs))
        self.assertIsNotNone(UPDATE.is_valid_run(ranking(1), **kwargs))

    def test_current_affix_mode_requires_matching_modifiers(self):
        kwargs = dict(
            season_slug="season-mn-1",
            dungeon_slug="maisara-caverns",
            challenge_mode_id=560,
            affix_mode="current",
            current_ids={9, 10},
        )
        self.assertIsNotNone(UPDATE.is_valid_run(ranking(1), **kwargs))
        self.assertIsNone(UPDATE.is_valid_run(ranking(2, modifiers=[{"id": 9}]), **kwargs))

    def test_deduplicates_by_keystone_run_id(self):
        runs = [ranking(10)["run"], ranking(10)["run"], ranking(11)["run"]]
        unique = UPDATE.dedupe_runs(runs)
        self.assertEqual([10, 11], [run["keystone_run_id"] for run in unique])


class MetricTests(TestCase):
    def test_appearance_role_share_presence_and_highest_key(self):
        runs = [
            ranking(1, level=17, roster=standard_roster(("mage", "frost", 64)))["run"],
            ranking(2, level=16, roster=standard_roster(("mage", "frost", 64)))["run"],
            ranking(3, level=15, roster=standard_roster(("mage", "fire", 63)))["run"],
        ]
        # Two frost + one fire in the first DPS seat; destruction and augmentation always present.
        result = UPDATE.aggregate_dungeon(runs, requested_runs=20, min_valid_runs=2)
        dps = result["roles"]["dps"]["specs"]
        self.assertEqual(2, dps[64]["appearanceCount"])
        self.assertEqual(round(2 / 9 * 100, 2), dps[64]["roleSharePct"])
        self.assertEqual(round(2 / 3 * 100, 2), dps[64]["runPresencePct"])
        self.assertEqual(17, dps[64]["highestKey"])
        self.assertEqual(1, dps[267]["representationRank"])
        self.assertEqual(result["sample"]["status"], "ok")
        self.assertEqual(result["sample"]["validRuns"], 3)

    def test_duplicate_spec_in_one_run_counts_two_appearances_and_one_presence(self):
        roster = [
            member("tank", "druid", "guardian", 104),
            member("healer", "priest", "discipline", 256),
            member("dps", "mage", "frost", 64, name="One"),
            member("dps", "mage", "frost", 64, name="Two"),
            member("dps", "warlock", "destruction", 267),
        ]
        result = UPDATE.aggregate_dungeon(
            [ranking(1, roster=roster)["run"]],
            requested_runs=20,
            min_valid_runs=1,
        )
        frost = result["roles"]["dps"]["specs"][64]
        self.assertEqual(2, frost["appearanceCount"])
        self.assertEqual(100.0, frost["runPresencePct"])
        self.assertEqual(round(2 / 3 * 100, 2), frost["roleSharePct"])

    def test_rank_ties_are_deterministic_by_spec_id(self):
        roster_a = standard_roster(("mage", "frost", 64))
        roster_b = standard_roster(("mage", "fire", 63))
        runs = [
            ranking(1, roster=roster_a)["run"],
            ranking(2, roster=roster_b)["run"],
        ]
        result = UPDATE.aggregate_dungeon(runs, requested_runs=20, min_valid_runs=1)
        dps = result["roles"]["dps"]["specs"]
        # destruction and augmentation appear in both runs, so they lead.
        # frost and fire each appear once: same share, fire (63) ranks before frost (64).
        self.assertEqual(dps[63]["roleSharePct"], dps[64]["roleSharePct"])
        self.assertLess(dps[63]["representationRank"], dps[64]["representationRank"])

    def test_insufficient_data_is_not_converted_to_zero_meta(self):
        result = UPDATE.aggregate_dungeon(
            [ranking(1)["run"]],
            requested_runs=20,
            min_valid_runs=20,
        )
        self.assertEqual("insufficient_data", result["sample"]["status"])
        self.assertEqual(1, result["sample"]["validRuns"])
        self.assertGreater(result["roles"]["dps"]["specs"][64]["roleSharePct"], 0)

    def test_daily_deltas_use_percentage_points(self):
        current = {
            "generatedAt": "2026-08-16 12:00 UTC",
            "dungeons": {
                560: {
                    "roles": {
                        "dps": {
                            "specs": {
                                64: {"roleSharePct": 12.7},
                            }
                        }
                    }
                }
            },
        }
        previous = {
            "generatedAt": "2026-08-15 12:00 UTC",
            "dungeons": {
                560: {
                    "roles": {
                        "dps": {
                            "specs": {
                                64: {"roleSharePct": 10.6},
                            }
                        }
                    }
                }
            },
        }
        UPDATE.apply_deltas(current, previous)
        spec = current["dungeons"][560]["roles"]["dps"]["specs"][64]
        self.assertEqual(10.6, spec["previousRoleSharePct"])
        self.assertEqual(2.1, spec["deltaPercentagePoints"])
        self.assertEqual("2026-08-15 12:00 UTC", current["previousValidGeneratedAt"])

    def test_missing_previous_snapshot_leaves_delta_nil(self):
        current = {
            "generatedAt": "2026-08-16 12:00 UTC",
            "dungeons": {560: {"roles": {"dps": {"specs": {64: {"roleSharePct": 12.7}}}}}},
        }
        UPDATE.apply_deltas(current, None)
        spec = current["dungeons"][560]["roles"]["dps"]["specs"][64]
        self.assertIsNone(spec.get("previousRoleSharePct"))
        self.assertIsNone(current["previousValidGeneratedAt"])


class SnapshotSafetyTests(TestCase):
    def _ok_snapshot(self, season="season-mn-1", share=50.0, valid=20, unresolved=0):
        other = round(100.0 - share, 2)
        return {
            "schemaVersion": 1,
            "generatedAt": "2026-08-16 12:00 UTC",
            "source": {"name": "Raider.IO", "url": "https://raider.io", "endpoint": "published Mythic+ runs API"},
            "season": {"slug": season, "name": "Synthetic Season 1"},
            "scope": {"region": "world", "affixMode": "season", "targetRunsPerDungeon": 20},
            "previousValidGeneratedAt": None,
            "dungeons": {
                560: {
                    "name": "Maisara Caverns",
                    "shortName": "MC",
                    "sample": {
                        "requestedRuns": 20,
                        "validRuns": valid,
                        "resolvedTankSeats": valid,
                        "resolvedHealerSeats": valid,
                        "resolvedDpsSeats": valid * 3,
                        "unresolvedSeats": unresolved,
                        "status": "ok",
                    },
                    "roles": {
                        "tank": {"specs": {104: self._spec("Guardian", "Druid", valid, 100, 100, 1, 16)}},
                        "healer": {"specs": {256: self._spec("Discipline", "Priest", valid, 100, 100, 1, 16)}},
                        "dps": {"specs": {
                            64: self._spec("Frost", "Mage", valid, share, 40, 1, 16),
                            267: self._spec("Destruction", "Warlock", valid * 2, other, 80, 2, 16),
                        }},
                    },
                }
            },
        }

    def _spec(self, name, class_name, appearances, share, presence, rank, key):
        return {
            "name": name,
            "className": class_name,
            "appearanceCount": appearances,
            "roleSharePct": share,
            "runPresencePct": presence,
            "representationRank": rank,
            "highestKey": key,
            "previousRoleSharePct": None,
            "deltaPercentagePoints": None,
        }

    def test_rejects_zero_useful_runs(self):
        snapshot = self._ok_snapshot(valid=0)
        snapshot["dungeons"][560]["sample"]["resolvedTankSeats"] = 0
        snapshot["dungeons"][560]["sample"]["resolvedHealerSeats"] = 0
        snapshot["dungeons"][560]["sample"]["resolvedDpsSeats"] = 0
        snapshot["dungeons"][560]["roles"] = {"tank": {"specs": {}}, "healer": {"specs": {}}, "dps": {"specs": {}}}
        with self.assertRaises(UPDATE.GeneratorError):
            UPDATE.validate_snapshot(snapshot)

    def test_rejects_impossible_role_counts_and_invalid_shares(self):
        snapshot = self._ok_snapshot()
        snapshot["dungeons"][560]["sample"]["resolvedTankSeats"] = 999
        with self.assertRaises(UPDATE.GeneratorError):
            UPDATE.validate_snapshot(snapshot)
        snapshot = self._ok_snapshot()
        snapshot["dungeons"][560]["roles"]["dps"]["specs"][64]["roleSharePct"] = 10.0
        with self.assertRaises(UPDATE.GeneratorError):
            UPDATE.validate_snapshot(snapshot)

    def test_coverage_regression_rejects_same_season_collapse(self):
        previous = self._ok_snapshot(unresolved=0)
        current = self._ok_snapshot(unresolved=80)
        with self.assertRaises(UPDATE.GeneratorError):
            UPDATE.validate_snapshot(current, previous)

    def _empty_snapshot(self, season):
        empty = self._ok_snapshot(season, valid=0)
        empty["dungeons"][560]["sample"]["resolvedTankSeats"] = 0
        empty["dungeons"][560]["sample"]["resolvedHealerSeats"] = 0
        empty["dungeons"][560]["sample"]["resolvedDpsSeats"] = 0
        empty["dungeons"][560]["roles"] = {
            "tank": {"specs": {}},
            "healer": {"specs": {}},
            "dps": {"specs": {}},
        }
        return empty

    def test_empty_new_season_does_not_preserve_previous_season(self):
        previous = self._ok_snapshot("season-mn-1")
        empty = self._empty_snapshot("season-mn-2")
        self.assertFalse(UPDATE.should_preserve_known_good(empty, previous))

    def test_same_season_empty_preserves_known_good(self):
        previous = self._ok_snapshot("season-mn-1")
        empty = self._empty_snapshot("season-mn-1")
        self.assertTrue(UPDATE.should_preserve_known_good(empty, previous))

    def test_pending_new_season_snapshot_validates(self):
        snapshot = self._empty_snapshot("season-mn-2")
        UPDATE.mark_pending_season_data(snapshot)
        UPDATE.validate_snapshot(snapshot)
        self.assertEqual("pending_season_data", snapshot["status"])
        self.assertEqual("insufficient_data", snapshot["dungeons"][560]["sample"]["status"])
        text = UPDATE.build_lua(snapshot)
        self.assertIn('status = "pending_season_data"', text)
        parsed = UPDATE.parse_generated_lua(text)
        self.assertEqual("pending_season_data", parsed.get("status"))

    def test_semantic_compare_ignores_only_generated_at(self):
        left = self._ok_snapshot()
        right = self._ok_snapshot()
        right["generatedAt"] = "2026-08-17 12:00 UTC"
        self.assertTrue(UPDATE.semantically_equal(left, right))
        right["dungeons"][560]["roles"]["dps"]["specs"][64]["roleSharePct"] = 49.0
        right["dungeons"][560]["roles"]["dps"]["specs"][267]["roleSharePct"] = 51.0
        self.assertFalse(UPDATE.semantically_equal(left, right))


class LuaRoundTripTests(TestCase):
    def test_deterministic_lua_round_trip_and_privacy_scan(self):
        snapshot = SnapshotSafetyTests()._ok_snapshot()
        text = UPDATE.build_lua(snapshot)
        parsed = UPDATE.parse_generated_lua(text)
        self.assertEqual(snapshot["season"]["slug"], parsed["season"]["slug"])
        self.assertIn(560, parsed["dungeons"])
        self.assertEqual("Frost", parsed["dungeons"][560]["roles"]["dps"]["specs"][64]["name"])
        again = UPDATE.build_lua(parsed)
        self.assertEqual(text, again)
        self.assertNotIn("SyntheticPlayer", text)
        self.assertNotIn("keystone_run_id", text)
        self.assertNotIn("SyntheticRealm", text)

    def test_pii_scan_rejects_identifying_fields(self):
        with self.assertRaises(UPDATE.GeneratorError):
            UPDATE.assert_no_pii('KeystoneMetaData = { keystone_run_id = 1 }')
        with self.assertRaises(UPDATE.GeneratorError):
            UPDATE.assert_no_pii('KeystoneMetaData = { name = "Titiquemonk" }', extra_names=["Titiquemonk"])


class AtomicReplacementTests(TestCase):
    def test_failed_generation_preserves_known_good(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "KeystoneMetaData.lua"
            output.write_text("known-good", encoding="utf-8")
            with (
                patch.object(UPDATE, "OUTPUT_FILE", str(output)),
                patch.object(UPDATE, "discover_static_data", side_effect=UPDATE.GeneratorError("boom")),
                patch.object(UPDATE, "log_credential_status"),
            ):
                code = UPDATE.main(["--output", str(output), "--target-runs", "20"])
            self.assertEqual(1, code)
            self.assertEqual("known-good", output.read_text(encoding="utf-8"))

    def test_timestamp_only_change_does_not_replace_file(self):
        snapshot = SnapshotSafetyTests()._ok_snapshot()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "KeystoneMetaData.lua"
            UPDATE.atomic_replace(str(output), UPDATE.build_lua(snapshot))
            original = output.read_text(encoding="utf-8")
            newer = dict(snapshot)
            newer["generatedAt"] = "2026-08-17 08:00 UTC"
            changed = UPDATE.write_if_material(str(output), newer, snapshot, dry_run=False)
            self.assertFalse(changed)
            self.assertEqual(original, output.read_text(encoding="utf-8"))

    def test_material_change_replaces_atomically(self):
        snapshot = SnapshotSafetyTests()._ok_snapshot()
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "KeystoneMetaData.lua"
            UPDATE.atomic_replace(str(output), UPDATE.build_lua(snapshot))
            updated = SnapshotSafetyTests()._ok_snapshot(share=40.0)
            changed = UPDATE.write_if_material(str(output), updated, snapshot, dry_run=False)
            self.assertTrue(changed)
            parsed = UPDATE.parse_generated_lua(output.read_text(encoding="utf-8"))
            self.assertEqual(40.0, parsed["dungeons"][560]["roles"]["dps"]["specs"][64]["roleSharePct"])


class PaginationTests(TestCase):
    def test_fetches_pages_until_target_and_stops_on_empty(self):
        pages = {
            0: page_payload([ranking(i) for i in range(1, 21)], page=0),
            1: page_payload([ranking(i) for i in range(21, 31)], page=1),
            2: page_payload([], page=2),
        }

        class FakeClient:
            def __init__(self):
                self.urls = []

            def get_json(self, url):
                self.urls.append(url)
                if "page=0" in url:
                    return pages[0]
                if "page=1" in url:
                    return pages[1]
                return pages[2]

        client = FakeClient()
        rows = UPDATE.fetch_runs_for_dungeon(
            client,
            season="season-mn-1",
            region="world",
            dungeon_slug="maisara-caverns",
            affix_mode="season",
            target=25,
        )
        self.assertEqual(25, len(rows))
        self.assertEqual(2, len(client.urls))

    def test_wrong_region_or_affix_mode_fails(self):
        class FakeClient:
            def get_json(self, url):
                payload = page_payload([ranking(1)])
                payload["params"]["region"] = "eu"
                return payload

        with self.assertRaises(UPDATE.GeneratorError):
            UPDATE.fetch_runs_for_dungeon(
                FakeClient(),
                season="season-mn-1",
                region="world",
                dungeon_slug="maisara-caverns",
                affix_mode="season",
                target=20,
            )


class ProbeAndCollectTests(TestCase):
    def test_auto_mode_falls_back_to_season_when_current_is_empty(self):
        class FakeClient:
            def get_json(self, url):
                return {"rankings": []}

        mode = UPDATE.probe_affix_mode(
            FakeClient(),
            season="season-mn-1",
            dungeon_slug="maisara-caverns",
            requested="auto",
        )
        self.assertEqual("season", mode)

    def test_collect_valid_runs_applies_filter_and_dedup(self):
        rankings = [ranking(1), ranking(1), ranking(2, chests=0), ranking(3)]
        valid = UPDATE.collect_valid_runs(
            rankings,
            season_slug="season-mn-1",
            dungeon_slug="maisara-caverns",
            challenge_mode_id=560,
            affix_mode="season",
            current_ids=None,
        )
        self.assertEqual([1, 3], [run["keystone_run_id"] for run in valid])


if __name__ == "__main__":
    main()
