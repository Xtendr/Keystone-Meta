#!/usr/bin/env python3
"""
update_keystone_meta.py

Fetch ranked Mythic+ runs from the published Raider.IO API and write an
aggregated, privacy-safe snapshot to KeystoneMetaData.lua.

Credentials are read from RAIDER_IO_API_KEY when present and sent as
Authorization. The published static-data and ranked-runs endpoints also
work without a key. The key is never printed.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VERSION = "0.1.0"
USER_AGENT = f"KeystoneMeta-WoW-Addon/{VERSION}"
API_BASE = "https://raider.io/api/v1"
STATIC_DATA_PATH = "/mythic-plus/static-data"
RUNS_PATH = "/mythic-plus/runs"
AFFIXES_PATH = "/mythic-plus/affixes"

EXPANSION_PROBE_ORDER = (11, 12, 10)
PAGE_SIZE = 20
DEFAULT_TARGET_RUNS = 500
DEFAULT_REQUEST_BUDGET = 250
DEFAULT_SAFETY_RESERVE = 10
DEFAULT_MIN_VALID_RUNS = 20
MAX_RETRIES = 5
RETRY_STATUSES = {429, 500, 502, 503, 504}
HARD_FAIL_STATUSES = {401, 403, 404}
COVERAGE_DROP_LIMIT = 0.10
ROLE_SHARE_TOLERANCE = 0.51
SEASON_OVERRIDE_ENV = "KEYSTONE_META_SEASON"

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "KeystoneMetaData.lua")

FORBIDDEN_LUA_KEYS = (
    "keystone_run_id",
    "keystone_team_id",
    "keystone_platoon_id",
    "logged_run_id",
    "persona_id",
    "recruitmentProfiles",
    "oldCharacter",
    "loadout",
    "videos",
    "stream",
    "access_key",
)

ROLE_ORDER = ("tank", "healer", "dps")

CLASS_NAMES = {
    "warrior": "Warrior",
    "paladin": "Paladin",
    "hunter": "Hunter",
    "rogue": "Rogue",
    "priest": "Priest",
    "death-knight": "Death Knight",
    "shaman": "Shaman",
    "mage": "Mage",
    "warlock": "Warlock",
    "monk": "Monk",
    "druid": "Druid",
    "demon-hunter": "Demon Hunter",
    "evoker": "Evoker",
}

# (class.slug, spec.slug) -> Blizzard specialization ID
SPEC_MAP: dict[tuple[str, str], int] = {
    ("warrior", "arms"): 71,
    ("warrior", "fury"): 72,
    ("warrior", "protection"): 73,
    ("paladin", "holy"): 65,
    ("paladin", "protection"): 66,
    ("paladin", "retribution"): 70,
    ("hunter", "beast-mastery"): 253,
    ("hunter", "beastmastery"): 253,
    ("hunter", "marksmanship"): 254,
    ("hunter", "survival"): 255,
    ("rogue", "assassination"): 259,
    ("rogue", "outlaw"): 260,
    ("rogue", "subtlety"): 261,
    ("priest", "discipline"): 256,
    ("priest", "holy"): 257,
    ("priest", "shadow"): 258,
    ("death-knight", "blood"): 250,
    ("death-knight", "frost"): 251,
    ("death-knight", "unholy"): 252,
    ("shaman", "elemental"): 262,
    ("shaman", "enhancement"): 263,
    ("shaman", "restoration"): 264,
    ("mage", "arcane"): 62,
    ("mage", "fire"): 63,
    ("mage", "frost"): 64,
    ("warlock", "affliction"): 265,
    ("warlock", "demonology"): 266,
    ("warlock", "destruction"): 267,
    ("monk", "brewmaster"): 268,
    ("monk", "windwalker"): 269,
    ("monk", "mistweaver"): 270,
    ("druid", "balance"): 102,
    ("druid", "feral"): 103,
    ("druid", "guardian"): 104,
    ("druid", "restoration"): 105,
    ("demon-hunter", "havoc"): 577,
    ("demon-hunter", "vengeance"): 581,
    ("demon-hunter", "devourer"): 1480,
    ("evoker", "devastation"): 1467,
    ("evoker", "preservation"): 1468,
    ("evoker", "augmentation"): 1473,
}

SPEC_NAMES = {
    62: "Arcane",
    63: "Fire",
    64: "Frost",
    65: "Holy",
    66: "Protection",
    70: "Retribution",
    71: "Arms",
    72: "Fury",
    73: "Protection",
    102: "Balance",
    103: "Feral",
    104: "Guardian",
    105: "Restoration",
    250: "Blood",
    251: "Frost",
    252: "Unholy",
    253: "Beast Mastery",
    254: "Marksmanship",
    255: "Survival",
    256: "Discipline",
    257: "Holy",
    258: "Shadow",
    259: "Assassination",
    260: "Outlaw",
    261: "Subtlety",
    262: "Elemental",
    263: "Enhancement",
    264: "Restoration",
    265: "Affliction",
    266: "Demonology",
    267: "Destruction",
    268: "Brewmaster",
    269: "Windwalker",
    270: "Mistweaver",
    577: "Havoc",
    581: "Vengeance",
    1467: "Devastation",
    1468: "Preservation",
    1473: "Augmentation",
    1480: "Devourer",
}

SPEC_DEFAULT_ROLE = {
    65: "healer",
    66: "tank",
    73: "tank",
    104: "tank",
    105: "healer",
    250: "tank",
    256: "healer",
    257: "healer",
    264: "healer",
    268: "tank",
    270: "healer",
    581: "tank",
    1468: "healer",
}


class GeneratorError(Exception):
    """Fail-closed generation error. The known-good file must stay untouched."""


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

def has_api_key() -> bool:
    return bool(os.environ.get("RAIDER_IO_API_KEY", "").strip())


def api_key_status() -> str:
    return "present" if has_api_key() else "absent"


def log_credential_status(stream=None) -> None:
    stream = stream or sys.stdout
    print(f"RAIDER_IO_API_KEY {api_key_status()}", file=stream)


def build_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    api_key = os.environ.get("RAIDER_IO_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Token {api_key}"
    return headers


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class HttpClient:
    def __init__(
        self,
        budget: int = DEFAULT_REQUEST_BUDGET,
        reserve: int = DEFAULT_SAFETY_RESERVE,
        delay: float | None = None,
        sleep_fn: Callable[[float], None] | None = None,
        urlopen_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.budget = int(budget)
        self.reserve = int(reserve)
        self.used = 0
        self.delay = DEFAULT_REQUEST_DELAY if delay is None else float(delay)
        self.sleep_fn = sleep_fn or time.sleep
        self.urlopen_fn = urlopen_fn or urllib.request.urlopen

    def remaining(self) -> int:
        return self.budget - self.used

    def _reserve_request(self) -> None:
        if self.remaining() <= self.reserve:
            raise GeneratorError(
                f"rate-limit safety reserve would be exceeded "
                f"(used={self.used}, budget={self.budget}, reserve={self.reserve})"
            )
        self.used += 1

    def get_json(self, url: str) -> Any:
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            self._reserve_request()
            req = urllib.request.Request(url, headers=build_headers())
            try:
                with self.urlopen_fn(req, timeout=60) as response:
                    raw = response.read().decode("utf-8")
                    payload = json.loads(raw)
                if self.delay > 0:
                    self.sleep_fn(self.delay)
                return payload
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code in HARD_FAIL_STATUSES:
                    raise GeneratorError(classify_http_error(exc.code, exc.reason, url)) from exc
                if exc.code in RETRY_STATUSES and attempt < MAX_RETRIES:
                    retry_after = _retry_after_seconds(exc)
                    self.sleep_fn(retry_after if retry_after is not None else 2 ** attempt)
                    continue
                raise GeneratorError(classify_http_error(exc.code, exc.reason, url)) from exc
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    self.sleep_fn(2 ** attempt)
                    continue
                raise GeneratorError(f"network-failure: {exc.reason} for {redact_url(url)}") from exc
            except TimeoutError as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    self.sleep_fn(2 ** attempt)
                    continue
                raise GeneratorError(f"network-failure: request timed out for {redact_url(url)}") from exc
            except (ValueError, UnicodeDecodeError) as exc:
                raise GeneratorError(f"Incompatible API response from {redact_url(url)}") from exc
        raise GeneratorError(f"Request failed for {redact_url(url)}: {last_error}")


def _retry_after_seconds(exc: urllib.error.HTTPError) -> float | None:
    raw = exc.headers.get("Retry-After") if exc.headers else None
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def classify_http_error(code: int, reason: str, url: str) -> str:
    redacted = redact_url(url)
    label = (reason or "").strip() or "error"
    if code in (401, 403):
        return f"rejected-credential: HTTP {code} {label} for {redacted}"
    if code == 404:
        return f"unknown-or-unavailable-resource: HTTP 404 {label} for {redacted}"
    if code == 429:
        return f"rate-limited: HTTP 429 {label} for {redacted}"
    if code >= 500:
        return f"network-or-server-failure: HTTP {code} {label} for {redacted}"
    return f"HTTP {code} {label} for {redacted}"


def redact_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    redacted = [
        (key, "***") if key.lower() in {"access_key", "api_key", "key", "token"} else (key, value)
        for key, value in query
    ]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(redacted), parsed.fragment)
    )


def default_request_delay() -> float:
    raw = os.environ.get("KEYSTONE_META_REQUEST_DELAY", "").strip()
    if raw:
        try:
            return max(0.0, float(raw))
        except ValueError:
            pass
    return 0.15


DEFAULT_REQUEST_DELAY = 0.15


# ---------------------------------------------------------------------------
# Time / season helpers
# ---------------------------------------------------------------------------

def parse_api_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_generated_at(now: datetime | None = None) -> str:
    now = (now or utc_now()).astimezone(timezone.utc)
    return now.strftime("%Y-%m-%d %H:%M UTC")


def parse_generated_at(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def discover_static_data(client: HttpClient) -> tuple[dict, int]:
    last_error: Exception | None = None
    for expansion_id in EXPANSION_PROBE_ORDER:
        url = f"{API_BASE}{STATIC_DATA_PATH}?expansion_id={expansion_id}"
        try:
            payload = client.get_json(url)
        except GeneratorError as exc:
            last_error = exc
            continue
        if not isinstance(payload, dict):
            last_error = GeneratorError("static-data response is not an object")
            continue
        seasons = payload.get("seasons")
        if isinstance(seasons, list) and any(s.get("is_main_season") for s in seasons if isinstance(s, dict)):
            return payload, expansion_id
    if last_error:
        raise GeneratorError(f"Could not discover season metadata: {last_error}")
    raise GeneratorError("No main Mythic+ season discovered from static-data")


def select_release_season(static_data: dict, now: datetime | None = None) -> dict:
    now = (now or utc_now()).astimezone(timezone.utc)
    seasons = [s for s in static_data.get("seasons", []) if isinstance(s, dict) and s.get("is_main_season")]
    if not seasons:
        raise GeneratorError("season is missing or unexpected")

    override = os.environ.get(SEASON_OVERRIDE_ENV, "").strip()
    if override:
        for season in seasons:
            if season.get("slug") == override:
                return season
        raise GeneratorError(f"Unknown season override: {override}")

    eligible: list[tuple[datetime, dict]] = []
    for season in seasons:
        starts = season.get("starts") or {}
        earliest: datetime | None = None
        if isinstance(starts, dict):
            for value in starts.values():
                if not value:
                    continue
                try:
                    stamp = parse_api_datetime(str(value))
                except (TypeError, ValueError):
                    continue
                if earliest is None or stamp < earliest:
                    earliest = stamp
        if earliest is not None and earliest <= now:
            eligible.append((earliest, season))

    if not eligible:
        raise GeneratorError("No main Mythic+ season has started")
    return max(eligible, key=lambda item: item[0])[1]


def season_dungeons(season_info: dict) -> list[dict]:
    dungeons = []
    seen_ids: set[int] = set()
    seen_slugs: set[str] = set()
    for dungeon in season_info.get("dungeons") or []:
        if not isinstance(dungeon, dict):
            continue
        challenge_mode_id = dungeon.get("challenge_mode_id")
        slug = dungeon.get("slug")
        name = dungeon.get("name")
        if challenge_mode_id is None or not slug or not name:
            continue
        try:
            challenge_mode_id = int(challenge_mode_id)
        except (TypeError, ValueError) as exc:
            raise GeneratorError(f"malformed dungeon identity: {dungeon!r}") from exc
        if challenge_mode_id in seen_ids or slug in seen_slugs:
            raise GeneratorError(f"duplicated dungeon identity: {slug} / {challenge_mode_id}")
        seen_ids.add(challenge_mode_id)
        seen_slugs.add(str(slug))
        dungeons.append({
            "slug": str(slug),
            "name": str(name),
            "shortName": str(dungeon.get("short_name") or slug),
            "challengeModeID": challenge_mode_id,
            "rioId": dungeon.get("id"),
        })
    if not dungeons:
        raise GeneratorError("No dungeons are discovered")
    dungeons.sort(key=lambda item: item["challengeModeID"])
    return dungeons


# ---------------------------------------------------------------------------
# Spec mapping and roster
# ---------------------------------------------------------------------------

def map_spec(class_slug: str, spec_slug: str, rio_spec_id: Any = None) -> int:
    key = (str(class_slug).strip().lower(), str(spec_slug).strip().lower())
    if key not in SPEC_MAP:
        raise GeneratorError(f"unknown specialization cannot be mapped safely: {key[0]}/{key[1]}")
    blizzard_id = SPEC_MAP[key]
    if rio_spec_id is not None:
        try:
            rio_id = int(rio_spec_id)
        except (TypeError, ValueError) as exc:
            raise GeneratorError(f"malformed Raider.IO spec id {rio_spec_id!r}") from exc
        if rio_id != blizzard_id:
            raise GeneratorError(
                f"Raider.IO spec id {rio_id} disagrees with mapped Blizzard id "
                f"{blizzard_id} for {key[0]}/{key[1]}"
            )
    return blizzard_id


def spec_display_name(spec_id: int, fallback: str | None = None) -> str:
    return SPEC_NAMES.get(spec_id) or fallback or f"Spec {spec_id}"


def class_display_name(class_slug: str, fallback: str | None = None) -> str:
    return CLASS_NAMES.get(class_slug) or fallback or class_slug.replace("-", " ").title()


def normalize_role(role: Any) -> str | None:
    if not isinstance(role, str):
        return None
    value = role.strip().lower()
    if value in ROLE_ORDER:
        return value
    return None


def resolve_seat(member: Any) -> tuple[str, int, str, str] | None:
    """Return (role, spec_id, spec_name, class_name) or None if unresolved.

    Unknown mapped specs raise GeneratorError. Incomplete seats return None.
    """
    if not isinstance(member, dict):
        return None
    if member.get("isBanned"):
        return None
    role = normalize_role(member.get("role"))
    character = member.get("character")
    if not isinstance(character, dict):
        return None
    class_info = character.get("class") or {}
    spec_info = character.get("spec") or {}
    if not isinstance(class_info, dict) or not isinstance(spec_info, dict):
        return None
    class_slug = class_info.get("slug")
    spec_slug = spec_info.get("slug")
    if not class_slug or not spec_slug:
        return None
    if role is None:
        return None
    spec_id = map_spec(str(class_slug), str(spec_slug), spec_info.get("id"))
    return (
        role,
        spec_id,
        spec_display_name(spec_id, spec_info.get("name")),
        class_display_name(str(class_slug), class_info.get("name")),
    )


# ---------------------------------------------------------------------------
# Run validation
# ---------------------------------------------------------------------------

def current_affix_ids(payload: dict) -> set[int]:
    details = payload.get("affix_details") or []
    ids: set[int] = set()
    for item in details:
        if isinstance(item, dict) and item.get("id") is not None:
            try:
                ids.add(int(item["id"]))
            except (TypeError, ValueError):
                continue
    return ids


def run_affix_ids(run: dict) -> set[int]:
    ids: set[int] = set()
    for item in run.get("weekly_modifiers") or []:
        if isinstance(item, dict) and item.get("id") is not None:
            try:
                ids.add(int(item["id"]))
            except (TypeError, ValueError):
                continue
    return ids


def is_finite_number(value: Any) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(number)


def is_valid_run(
    ranking: Any,
    *,
    season_slug: str,
    dungeon_slug: str,
    challenge_mode_id: int,
    affix_mode: str,
    current_ids: set[int] | None,
) -> dict | None:
    if not isinstance(ranking, dict):
        return None
    run = ranking.get("run")
    if not isinstance(run, dict):
        return None
    if run.get("season") != season_slug:
        return None
    dungeon = run.get("dungeon") or {}
    if not isinstance(dungeon, dict):
        return None
    if dungeon.get("slug") not in {dungeon_slug, None} and dungeon.get("slug") != dungeon_slug:
        return None
    if dungeon.get("slug") and dungeon.get("slug") != dungeon_slug:
        return None
    cmid = dungeon.get("map_challenge_mode_id") or dungeon.get("challenge_mode_id")
    if cmid is not None:
        try:
            if int(cmid) != int(challenge_mode_id):
                return None
        except (TypeError, ValueError):
            return None
    if run.get("status") != "finished":
        return None
    if not is_finite_number(run.get("mythic_level")):
        return None
    level = float(run.get("mythic_level"))
    if level < 2 or level != int(level):
        return None
    if not is_finite_number(run.get("num_chests")) or float(run.get("num_chests")) < 1:
        return None
    run_id = run.get("keystone_run_id")
    if run_id is None:
        return None
    if affix_mode == "current":
        if not current_ids:
            return None
        if run_affix_ids(run) != current_ids:
            return None
    roster = run.get("roster")
    if not isinstance(roster, list) or not roster:
        return None
    return run


def dedupe_runs(runs: list[dict]) -> list[dict]:
    seen: set[Any] = set()
    unique: list[dict] = []
    for run in runs:
        run_id = run.get("keystone_run_id")
        if run_id in seen:
            continue
        seen.add(run_id)
        unique.append(run)
    return unique


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def empty_role_bucket() -> dict[str, Any]:
    return {
        "appearances": {},
        "presence_runs": {},
        "highest": {},
        "meta": {},
    }


def aggregate_dungeon(
    runs: list[dict],
    *,
    requested_runs: int,
    min_valid_runs: int,
) -> dict[str, Any]:
    roles = {role: empty_role_bucket() for role in ROLE_ORDER}
    resolved = {role: 0 for role in ROLE_ORDER}
    unresolved = 0

    for run in runs:
        level = int(run["mythic_level"])
        present_specs: set[int] = set()
        for member in run.get("roster") or []:
            resolved_seat = resolve_seat(member)
            if resolved_seat is None:
                unresolved += 1
                continue
            role, spec_id, spec_name, class_name = resolved_seat
            bucket = roles[role]
            bucket["appearances"][spec_id] = bucket["appearances"].get(spec_id, 0) + 1
            bucket["meta"][spec_id] = {"name": spec_name, "className": class_name}
            current_high = bucket["highest"].get(spec_id, 0)
            if level > current_high:
                bucket["highest"][spec_id] = level
            present_specs.add(spec_id)
            resolved[role] += 1
        for spec_id in present_specs:
            for role in ROLE_ORDER:
                if spec_id in roles[role]["appearances"]:
                    roles[role]["presence_runs"][spec_id] = roles[role]["presence_runs"].get(spec_id, 0) + 1

    valid_runs = len(runs)
    status = "ok" if valid_runs >= min_valid_runs else "insufficient_data"
    role_tables = {}
    for role in ROLE_ORDER:
        role_tables[role] = build_role_table(
            roles[role],
            resolved_seats=resolved[role],
            valid_runs=valid_runs,
        )

    return {
        "sample": {
            "requestedRuns": int(requested_runs),
            "validRuns": valid_runs,
            "resolvedTankSeats": resolved["tank"],
            "resolvedHealerSeats": resolved["healer"],
            "resolvedDpsSeats": resolved["dps"],
            "unresolvedSeats": unresolved,
            "status": status,
        },
        "roles": role_tables,
    }


def build_role_table(bucket: dict, *, resolved_seats: int, valid_runs: int) -> dict[str, Any]:
    specs: dict[int, dict[str, Any]] = {}
    for spec_id, appearances in bucket["appearances"].items():
        share = (appearances / resolved_seats * 100.0) if resolved_seats else 0.0
        presence = (bucket["presence_runs"].get(spec_id, 0) / valid_runs * 100.0) if valid_runs else 0.0
        meta = bucket["meta"].get(spec_id, {})
        specs[spec_id] = {
            "name": meta.get("name") or spec_display_name(spec_id),
            "className": meta.get("className") or "Unknown",
            "appearanceCount": int(appearances),
            "roleSharePct": round(share, 2),
            "runPresencePct": round(presence, 2),
            "representationRank": 0,
            "highestKey": int(bucket["highest"].get(spec_id, 0)),
            "previousRoleSharePct": None,
            "deltaPercentagePoints": None,
        }
    ranked = sorted(
        specs.items(),
        key=lambda item: (-item[1]["roleSharePct"], item[0]),
    )
    for index, (spec_id, _) in enumerate(ranked, start=1):
        specs[spec_id]["representationRank"] = index
    return {"specs": specs}


def apply_deltas(snapshot: dict, previous: dict | None) -> None:
    if not previous:
        snapshot["previousValidGeneratedAt"] = None
        return
    snapshot["previousValidGeneratedAt"] = previous.get("generatedAt")
    prev_dungeons = previous.get("dungeons") or {}
    for dungeon_id, dungeon in snapshot.get("dungeons", {}).items():
        prev_dungeon = prev_dungeons.get(dungeon_id)
        if not prev_dungeon:
            continue
        for role in ROLE_ORDER:
            prev_specs = ((prev_dungeon.get("roles") or {}).get(role) or {}).get("specs") or {}
            specs = ((dungeon.get("roles") or {}).get(role) or {}).get("specs") or {}
            for spec_id, spec in specs.items():
                prev_spec = prev_specs.get(spec_id)
                if not prev_spec or prev_spec.get("roleSharePct") is None:
                    continue
                previous_share = float(prev_spec["roleSharePct"])
                spec["previousRoleSharePct"] = previous_share
                spec["deltaPercentagePoints"] = round(float(spec["roleSharePct"]) - previous_share, 2)


# ---------------------------------------------------------------------------
# Snapshot assembly and validation
# ---------------------------------------------------------------------------

def new_snapshot(
    *,
    season: dict,
    affix_mode: str,
    target_runs: int,
    generated_at: str,
) -> dict:
    return {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "source": {
            "name": "Raider.IO",
            "url": "https://raider.io",
            "endpoint": "published Mythic+ runs API",
        },
        "season": {
            "slug": season.get("slug"),
            "name": season.get("name") or season.get("slug"),
        },
        "scope": {
            "region": "world",
            "affixMode": affix_mode,
            "targetRunsPerDungeon": int(target_runs),
        },
        "previousValidGeneratedAt": None,
        "dungeons": {},
    }


def total_valid_runs(snapshot: dict) -> int:
    return sum(int((d.get("sample") or {}).get("validRuns") or 0) for d in (snapshot.get("dungeons") or {}).values())


def previous_is_useful(previous: dict | None) -> bool:
    if not previous:
        return False
    return total_valid_runs(previous) > 0


def coverage_ratio(sample: dict) -> float:
    resolved = (
        int(sample.get("resolvedTankSeats") or 0)
        + int(sample.get("resolvedHealerSeats") or 0)
        + int(sample.get("resolvedDpsSeats") or 0)
    )
    unresolved = int(sample.get("unresolvedSeats") or 0)
    total = resolved + unresolved
    if total <= 0:
        return 1.0
    return resolved / total


def overall_coverage(snapshot: dict) -> float:
    samples = [d.get("sample") or {} for d in (snapshot.get("dungeons") or {}).values()]
    resolved = sum(
        int(s.get("resolvedTankSeats") or 0)
        + int(s.get("resolvedHealerSeats") or 0)
        + int(s.get("resolvedDpsSeats") or 0)
        for s in samples
    )
    unresolved = sum(int(s.get("unresolvedSeats") or 0) for s in samples)
    total = resolved + unresolved
    if total <= 0:
        return 1.0
    return resolved / total


def validate_snapshot(snapshot: dict, previous: dict | None = None) -> None:
    if not isinstance(snapshot, dict):
        raise GeneratorError("candidate snapshot is not an object")
    if snapshot.get("schemaVersion") != 1:
        raise GeneratorError("missing or unexpected schemaVersion")
    season = snapshot.get("season") or {}
    if not season.get("slug"):
        raise GeneratorError("season is missing or unexpected")
    dungeons = snapshot.get("dungeons")
    if not isinstance(dungeons, dict) or not dungeons:
        raise GeneratorError("No dungeons are discovered")
    seen_ids: set[int] = set()
    for dungeon_id, dungeon in dungeons.items():
        try:
            numeric_id = int(dungeon_id)
        except (TypeError, ValueError) as exc:
            raise GeneratorError(f"malformed dungeon identity: {dungeon_id!r}") from exc
        if numeric_id in seen_ids:
            raise GeneratorError(f"duplicated dungeon identity: {numeric_id}")
        seen_ids.add(numeric_id)
        if not isinstance(dungeon, dict) or not dungeon.get("name"):
            raise GeneratorError(f"malformed dungeon {numeric_id}")
        sample = dungeon.get("sample") or {}
        for key in (
            "requestedRuns",
            "validRuns",
            "resolvedTankSeats",
            "resolvedHealerSeats",
            "resolvedDpsSeats",
            "unresolvedSeats",
        ):
            value = sample.get(key)
            if not is_finite_number(value) or float(value) < 0:
                raise GeneratorError(f"{dungeon.get('name')}: invalid {key}")
        valid_runs = int(sample.get("validRuns") or 0)
        if int(sample.get("resolvedTankSeats") or 0) > valid_runs * 2:
            raise GeneratorError(f"{dungeon.get('name')}: impossible tank seat count")
        if int(sample.get("resolvedHealerSeats") or 0) > valid_runs * 2:
            raise GeneratorError(f"{dungeon.get('name')}: impossible healer seat count")
        if int(sample.get("resolvedDpsSeats") or 0) > valid_runs * 4:
            raise GeneratorError(f"{dungeon.get('name')}: impossible DPS seat count")
        roles = dungeon.get("roles") or {}
        for role in ROLE_ORDER:
            specs = ((roles.get(role) or {}).get("specs") or {})
            shares = []
            for spec_id, spec in specs.items():
                for field in ("appearanceCount", "roleSharePct", "runPresencePct", "representationRank", "highestKey"):
                    value = spec.get(field)
                    if value is None or not is_finite_number(value) or float(value) < 0:
                        raise GeneratorError(f"{dungeon.get('name')} {role} {spec_id}: invalid {field}")
                shares.append(float(spec["roleSharePct"]))
            resolved_key = {
                "tank": "resolvedTankSeats",
                "healer": "resolvedHealerSeats",
                "dps": "resolvedDpsSeats",
            }[role]
            if int(sample.get(resolved_key) or 0) > 0 and shares:
                total_share = sum(shares)
                if abs(total_share - 100.0) > ROLE_SHARE_TOLERANCE:
                    raise GeneratorError(
                        f"{dungeon.get('name')} {role}: role shares total {total_share:.2f}"
                    )
    if total_valid_runs(snapshot) <= 0:
        if snapshot.get("status") != "pending_season_data":
            raise GeneratorError("The sample contains zero useful runs")
        return
    if previous and previous.get("season", {}).get("slug") == snapshot.get("season", {}).get("slug"):
        prev_cov = overall_coverage(previous)
        curr_cov = overall_coverage(snapshot)
        if prev_cov - curr_cov > COVERAGE_DROP_LIMIT:
            raise GeneratorError(
                f"Coverage dropped suspiciously ({prev_cov:.3f} -> {curr_cov:.3f})"
            )


def season_slug(snapshot: dict | None) -> str | None:
    if not snapshot:
        return None
    return (snapshot.get("season") or {}).get("slug")


def should_preserve_known_good(snapshot: dict, previous: dict | None) -> bool:
    if not previous_is_useful(previous):
        return False
    if season_slug(previous) != season_slug(snapshot):
        return False
    return total_valid_runs(snapshot) <= 0


def mark_pending_season_data(snapshot: dict) -> dict:
    snapshot["status"] = "pending_season_data"
    for dungeon in (snapshot.get("dungeons") or {}).values():
        sample = dungeon.get("sample")
        if isinstance(sample, dict):
            sample["status"] = "insufficient_data"
    return snapshot


def strip_generated_at(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: strip_generated_at(item) for key, item in value.items() if key != "generatedAt"}
    if isinstance(value, list):
        return [strip_generated_at(item) for item in value]
    return value


def semantically_equal(left: dict, right: dict) -> bool:
    return strip_generated_at(left) == strip_generated_at(right)


# ---------------------------------------------------------------------------
# Lua serialize / parse
# ---------------------------------------------------------------------------

def lua_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def lua_number(value: Any) -> str:
    if value is None:
        return "nil"
    number = float(value)
    if not math.isfinite(number):
        raise GeneratorError("numeric values are non-finite")
    if number == int(number) and abs(number) < 1e15:
        return str(int(number))
    return f"{number:.2f}"


def lua_value(value: Any, indent: str) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return lua_string(value)
    if isinstance(value, (int, float)):
        return lua_number(value)
    if isinstance(value, dict):
        return lua_table(value, indent)
    raise GeneratorError(f"unsupported Lua value {type(value)!r}")


def lua_key(key: Any) -> str:
    if isinstance(key, int) or (isinstance(key, str) and key.isdigit()):
        return f"[{int(key)}]"
    if isinstance(key, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        return key
    return f"[{lua_string(str(key))}]"


def lua_table(value: dict, indent: str) -> str:
    if not value:
        return "{}"
    inner = indent + "    "
    lines = ["{"]
    items: list[tuple[Any, Any]]
    if all(_is_int_key(key) for key in value):
        items = sorted(value.items(), key=lambda item: int(item[0]))
    else:
        items = list(value.items())
    for key, item in items:
        lines.append(f"{inner}{lua_key(key)} = {lua_value(item, inner)},")
    lines.append(f"{indent}}}")
    return "\n".join(lines)


def _is_int_key(key: Any) -> bool:
    if isinstance(key, int):
        return True
    return isinstance(key, str) and key.isdigit()


def ordered_dungeon_block(dungeon: dict) -> dict:
    roles = {}
    for role in ROLE_ORDER:
        role_block = (dungeon.get("roles") or {}).get(role) or {"specs": {}}
        specs = role_block.get("specs") or {}
        ordered_specs = dict(
            sorted(
                specs.items(),
                key=lambda item: (int(item[1].get("representationRank") or 0), int(item[0])),
            )
        )
        roles[role] = {"specs": ordered_specs}
    return {
        "name": dungeon.get("name"),
        "shortName": dungeon.get("shortName"),
        "sample": dungeon.get("sample"),
        "roles": roles,
    }


def build_lua(snapshot: dict) -> str:
    generated_at = snapshot.get("generatedAt") or format_generated_at()
    season = snapshot.get("season") or {}
    lines = [
        "-- KeystoneMetaData.lua",
        "-- Auto-generated by update_keystone_meta.py – do not edit manually.",
        f"-- Last updated : {generated_at}",
        f"-- Season       : {season.get('slug', 'unknown')}",
        "-- Synthetic fixture numbers must never be presented as live Raider.IO data.",
        "",
        "KeystoneMetaData = {",
        f"    schemaVersion = {lua_number(snapshot.get('schemaVersion', 1))},",
        f"    generatedAt = {lua_string(generated_at)},",
        f"    source = {lua_value(snapshot.get('source') or {}, '    ')},",
        f"    season = {lua_value(snapshot.get('season') or {}, '    ')},",
        f"    scope = {lua_value(snapshot.get('scope') or {}, '    ')},",
        f"    previousValidGeneratedAt = {lua_value(snapshot.get('previousValidGeneratedAt'), '    ')},",
    ]
    if snapshot.get("status"):
        lines.append(f"    status = {lua_string(str(snapshot['status']))},")
    lines.append("    dungeons = {")
    dungeons = snapshot.get("dungeons") or {}
    for dungeon_id in sorted(dungeons, key=lambda key: int(key)):
        block = ordered_dungeon_block(dungeons[dungeon_id])
        rendered = lua_value(block, "        ")
        lines.append(f"        [{int(dungeon_id)}] = {rendered},")
    lines.extend([
        "    },",
        "}",
        "",
    ])
    text = "\n".join(lines)
    assert_no_pii(text)
    return text


def assert_no_pii(text: str, extra_names: list[str] | None = None) -> None:
    lowered = text.lower()
    for key in FORBIDDEN_LUA_KEYS:
        if key.lower() in lowered:
            raise GeneratorError(f"generated Lua contains forbidden field {key}")
    for name in extra_names or []:
        if name and name in text:
            raise GeneratorError("generated Lua contains character-level identities")


class _LuaParser:
    def __init__(self, text: str) -> None:
        self.text = _strip_lua_comments(text)
        self.pos = 0

    def parse_assignment(self) -> dict:
        self._skip()
        self._expect_ident("KeystoneMetaData")
        self._skip()
        self._eat("=")
        value = self._parse_value()
        self._skip()
        if not isinstance(value, dict):
            raise GeneratorError("candidate Lua cannot be validated")
        return value

    def _parse_value(self) -> Any:
        self._skip()
        if self._peek() == "{":
            return self._parse_table()
        if self._peek() == '"':
            return self._parse_string()
        if self.text.startswith("nil", self.pos) and self._is_boundary(self.pos + 3):
            self.pos += 3
            return None
        if self.text.startswith("true", self.pos) and self._is_boundary(self.pos + 4):
            self.pos += 4
            return True
        if self.text.startswith("false", self.pos) and self._is_boundary(self.pos + 5):
            self.pos += 5
            return False
        return self._parse_number()

    def _parse_table(self) -> dict:
        self._eat("{")
        table: dict[Any, Any] = {}
        while True:
            self._skip()
            if self._peek() == "}":
                self.pos += 1
                return table
            key = self._parse_key()
            self._skip()
            self._eat("=")
            table[key] = self._parse_value()
            self._skip()
            if self._peek() == ",":
                self.pos += 1
                continue
            if self._peek() == "}":
                self.pos += 1
                return table
            raise GeneratorError("candidate Lua cannot be validated")

    def _parse_key(self) -> Any:
        self._skip()
        if self._peek() == "[":
            self.pos += 1
            self._skip()
            if self._peek() == '"':
                key = self._parse_string()
            else:
                key = self._parse_number()
                if isinstance(key, float) and key == int(key):
                    key = int(key)
            self._skip()
            self._eat("]")
            return key
        return self._parse_ident()

    def _parse_ident(self) -> str:
        match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", self.text[self.pos:])
        if not match:
            raise GeneratorError("candidate Lua cannot be validated")
        self.pos += match.end()
        return match.group(0)

    def _expect_ident(self, expected: str) -> None:
        ident = self._parse_ident()
        if ident != expected:
            raise GeneratorError("candidate Lua cannot be validated")

    def _parse_string(self) -> str:
        self._eat('"')
        chars: list[str] = []
        while self.pos < len(self.text):
            char = self.text[self.pos]
            self.pos += 1
            if char == '"':
                return "".join(chars)
            if char == "\\":
                if self.pos >= len(self.text):
                    raise GeneratorError("candidate Lua cannot be validated")
                escaped = self.text[self.pos]
                self.pos += 1
                chars.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(escaped, escaped))
                continue
            chars.append(char)
        raise GeneratorError("candidate Lua cannot be validated")

    def _parse_number(self) -> int | float:
        match = re.match(r"-?\d+(?:\.\d+)?", self.text[self.pos:])
        if not match:
            raise GeneratorError("candidate Lua cannot be validated")
        self.pos += match.end()
        raw = match.group(0)
        if "." in raw:
            return float(raw)
        return int(raw)

    def _eat(self, token: str) -> None:
        self._skip()
        if not self.text.startswith(token, self.pos):
            raise GeneratorError("candidate Lua cannot be validated")
        self.pos += len(token)

    def _peek(self) -> str:
        self._skip()
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def _skip(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def _is_boundary(self, index: int) -> bool:
        return index >= len(self.text) or not (self.text[index].isalnum() or self.text[index] == "_")


def _strip_lua_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        in_string = False
        escaped = False
        cut = len(line)
        for index, char in enumerate(line):
            if escaped:
                escaped = False
                continue
            if char == "\\" and in_string:
                escaped = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string and line.startswith("--", index):
                cut = index
                break
        lines.append(line[:cut])
    return "\n".join(lines)


def parse_generated_lua(text: str) -> dict:
    try:
        snapshot = _LuaParser(text).parse_assignment()
    except GeneratorError:
        raise
    except Exception as exc:
        raise GeneratorError("candidate Lua cannot be validated") from exc
    snapshot["dungeons"] = {
        int(key): _normalize_dungeon(value)
        for key, value in (snapshot.get("dungeons") or {}).items()
    }
    return snapshot


def _normalize_dungeon(dungeon: dict) -> dict:
    roles = {}
    for role in ROLE_ORDER:
        specs_in = (((dungeon.get("roles") or {}).get(role) or {}).get("specs") or {})
        specs = {}
        for spec_id, spec in specs_in.items():
            specs[int(spec_id)] = spec
        roles[role] = {"specs": specs}
    dungeon = dict(dungeon)
    dungeon["roles"] = roles
    return dungeon


def load_previous_lua(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    text = _read_text(path)
    if not text.strip():
        return None
    try:
        return parse_generated_lua(text)
    except GeneratorError:
        if "KeystoneMetaData" not in text:
            return None
        raise


# ---------------------------------------------------------------------------
# Fetch orchestration
# ---------------------------------------------------------------------------

def runs_url(season: str, region: str, dungeon: str, affixes: str, page: int) -> str:
    query = urllib.parse.urlencode({
        "season": season,
        "region": region,
        "dungeon": dungeon,
        "affixes": affixes,
        "page": page,
    })
    return f"{API_BASE}{RUNS_PATH}?{query}"


def affixes_url(region: str = "us") -> str:
    query = urllib.parse.urlencode({"region": region, "locale": "en"})
    return f"{API_BASE}{AFFIXES_PATH}?{query}"


def api_affix_param(affix_mode: str) -> str:
    if affix_mode == "current":
        return "current"
    if affix_mode == "season":
        return "all"
    raise GeneratorError(f"unsupported affix mode: {affix_mode}")


def fetch_current_affixes(client: HttpClient, region: str = "us") -> set[int]:
    payload = client.get_json(affixes_url(region))
    if not isinstance(payload, dict):
        raise GeneratorError("affix response shape is incompatible")
    ids = current_affix_ids(payload)
    if not ids:
        raise GeneratorError("current weekly affixes could not be identified")
    return ids


def fetch_runs_for_dungeon(
    client: HttpClient,
    *,
    season: str,
    region: str,
    dungeon_slug: str,
    affix_mode: str,
    target: int,
) -> list[dict]:
    affixes = api_affix_param(affix_mode)
    pages_needed = max(1, math.ceil(target / PAGE_SIZE))
    rankings: list[dict] = []
    for page in range(pages_needed):
        payload = client.get_json(runs_url(season, region, dungeon_slug, affixes, page))
        if not isinstance(payload, dict) or "rankings" not in payload:
            raise GeneratorError("The API response shape is incompatible")
        params = payload.get("params") or {}
        if isinstance(params, dict):
            if params.get("region") and params.get("region") != region:
                raise GeneratorError("The wrong region or affix mode is returned")
            if params.get("affixes") and params.get("affixes") != affixes:
                raise GeneratorError("The wrong region or affix mode is returned")
            if params.get("season") and params.get("season") != season:
                raise GeneratorError("season is missing or unexpected")
        page_rows = payload.get("rankings") or []
        if not isinstance(page_rows, list):
            raise GeneratorError("The API response shape is incompatible")
        if not page_rows:
            break
        rankings.extend(page_rows)
        if len(rankings) >= target:
            return rankings[:target]
    return rankings


def collect_valid_runs(
    rankings: list[dict],
    *,
    season_slug: str,
    dungeon_slug: str,
    challenge_mode_id: int,
    affix_mode: str,
    current_ids: set[int] | None,
) -> list[dict]:
    valid: list[dict] = []
    for ranking in rankings:
        run = is_valid_run(
            ranking,
            season_slug=season_slug,
            dungeon_slug=dungeon_slug,
            challenge_mode_id=challenge_mode_id,
            affix_mode=affix_mode,
            current_ids=current_ids,
        )
        if run is not None:
            valid.append(run)
    return dedupe_runs(valid)


def probe_affix_mode(
    client: HttpClient,
    *,
    season: str,
    dungeon_slug: str,
    requested: str,
) -> str:
    if requested != "auto":
        return requested
    payload = client.get_json(runs_url(season, "world", dungeon_slug, "current", 0))
    rankings = payload.get("rankings") if isinstance(payload, dict) else None
    if isinstance(rankings, list) and rankings:
        return "current"
    return "season"


def build_snapshot_from_fetches(
    client: HttpClient,
    *,
    season_info: dict,
    dungeons: list[dict],
    affix_mode: str,
    target_runs: int,
    min_valid_runs: int,
    previous: dict | None,
    generated_at: str | None = None,
) -> dict:
    current_ids = fetch_current_affixes(client) if affix_mode == "current" else None
    snapshot = new_snapshot(
        season=season_info,
        affix_mode=affix_mode,
        target_runs=target_runs,
        generated_at=generated_at or format_generated_at(),
    )
    for dungeon in dungeons:
        rankings = fetch_runs_for_dungeon(
            client,
            season=season_info["slug"],
            region="world",
            dungeon_slug=dungeon["slug"],
            affix_mode=affix_mode,
            target=target_runs,
        )
        valid_runs = collect_valid_runs(
            rankings,
            season_slug=season_info["slug"],
            dungeon_slug=dungeon["slug"],
            challenge_mode_id=dungeon["challengeModeID"],
            affix_mode=affix_mode,
            current_ids=current_ids,
        )
        aggregated = aggregate_dungeon(
            valid_runs,
            requested_runs=target_runs,
            min_valid_runs=min_valid_runs,
        )
        snapshot["dungeons"][dungeon["challengeModeID"]] = {
            "name": dungeon["name"],
            "shortName": dungeon["shortName"],
            **aggregated,
        }
    apply_deltas(snapshot, previous)
    return snapshot


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def _read_text(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def atomic_replace(path: str, text: str) -> None:
    parse_generated_lua(text)
    assert_no_pii(text)
    temp_path = path + ".tmp"
    _write_text(temp_path, text)
    try:
        parse_generated_lua(_read_text(temp_path))
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def write_if_material(path: str, snapshot: dict, previous: dict | None, dry_run: bool = False) -> bool:
    text = build_lua(snapshot)
    parse_generated_lua(text)
    validate_snapshot(snapshot, previous)
    material = previous is None or not semantically_equal(snapshot, previous)
    if dry_run:
        print(f"DRY_RUN material_change={str(material).lower()}")
        return material
    if not material:
        print("MATERIAL_CHANGE=false")
        return False
    atomic_replace(path, text)
    print("MATERIAL_CHANGE=true")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate KeystoneMetaData.lua from Raider.IO")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--affix-mode", choices=("season", "current", "auto"), default="season")
    parser.add_argument("--target-runs", type=int, default=DEFAULT_TARGET_RUNS)
    parser.add_argument("--output", default=OUTPUT_FILE)
    parser.add_argument("--budget", type=int, default=DEFAULT_REQUEST_BUDGET)
    parser.add_argument("--min-valid-runs", type=int, default=DEFAULT_MIN_VALID_RUNS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log_credential_status()
    if not has_api_key():
        print(
            "[WARN] RAIDER_IO_API_KEY is absent; using the public Raider.IO API without Authorization.",
            file=sys.stderr,
        )
    if args.target_runs <= 0:
        print("[ERROR] --target-runs must be positive", file=sys.stderr)
        return 1

    client = HttpClient(
        budget=args.budget,
        reserve=DEFAULT_SAFETY_RESERVE,
        delay=default_request_delay(),
    )
    output = args.output
    previous = load_previous_lua(output)

    try:
        static_data, expansion_id = discover_static_data(client)
        season_info = select_release_season(static_data)
        dungeons = season_dungeons(season_info)
        print(f"Discovered expansion {expansion_id} season {season_info.get('slug')} with {len(dungeons)} dungeons.")
        affix_mode = probe_affix_mode(
            client,
            season=season_info["slug"],
            dungeon_slug=dungeons[0]["slug"],
            requested=args.affix_mode,
        )
        print(f"Using affix mode {affix_mode}; target {args.target_runs} runs / dungeon.")
        snapshot = build_snapshot_from_fetches(
            client,
            season_info=season_info,
            dungeons=dungeons,
            affix_mode=affix_mode,
            target_runs=args.target_runs,
            min_valid_runs=args.min_valid_runs,
            previous=previous,
        )
        if should_preserve_known_good(snapshot, previous):
            print(
                "[ERROR] valid-season-no-useful-runs: candidate had no useful coverage; "
                "preserving the existing known-good file.",
                file=sys.stderr,
            )
            return 1
        if total_valid_runs(snapshot) <= 0:
            mark_pending_season_data(snapshot)
            print(
                "[WARN] new-season-no-useful-runs: writing pending_season_data "
                "instead of keeping the previous season on screen.",
                file=sys.stderr,
            )
        validate_snapshot(snapshot, previous)
        write_if_material(output, snapshot, previous, dry_run=args.dry_run)
        print(f"Requests used: {client.used}/{client.budget}")
        return 0
    except GeneratorError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
