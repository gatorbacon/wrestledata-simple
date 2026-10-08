#!/usr/bin/env python3
"""
Builds MatSavant's name-based wrestler URLs (/wrestler/levi-haines) -- Step 1 of
docs/matsavant_seo_plan.md.

Source of truth: data/url_slugs/ncaa_men.json (committed). APPEND-ONLY: once a
wrestler has a slug it never changes and is never reused, because Google and
shared links point at it. Each run only adds slugs for new wrestlers and turns
retired slugs into aliases (redirects).

Who gets a slug ("entity"):
  - every NCAA career (data/careers/ncaa_men/career_*.json)        key "c:<n>"
  - every season profile that belongs to no career (24 on
    2026-10-07)                                                    key "w:<id>"
  Only profiles tracked in git count (tracked = deployed), same rule as
  scripts/reports/build_career_seasons.py, so we never link to a missing page.

Slug rules (TJ, 2026-10-07):
  - lowercase name, accents stripped, apostrophes (incl. ` and ?) and periods dropped, anything
    else non-alphanumeric -> "-"
  - name shared with another wrestler -> add the school of the wrestler's
    first season (tyler-johnson-wisconsin); still taken -> -2, -3. A wrestler
    who already has the bare name keeps it; only newcomers get a suffix.
    (On the first build every shared name got the school suffix.)
  - name changes later: slug stays.
  - career merged away (career file gone): its slug becomes an alias of the
    career that now holds its seasons.
  - unlinked season later linked into a career: a career with no slug yet
    takes that season's slug; otherwise the season's slug becomes an alias.

Published under frontend/wrestledata-ui/public/seo/ -- NOT under /data/, so the
edge function's own lookups don't count against the per-IP rate limit on
/data/* (plan Step 5). This script owns seo/wrestlers/ and seo/by_id/ entirely.
  seo/wrestlers/<slug>.json
      {"slug", "name", "latest_season", "latest_id", "seasons": {"2026": id},
       "team", "team_slug", "weight", "rank", "career_record", "season_record"}
      or for an alias {"slug", "alias_of"}
      Everything the edge function needs for title/description in one fetch.
  seo/by_id/<wrestler_id mod 97>.json
      {wrestler_id: [slug, season, is_latest (1/0)]} -- for redirecting old
      wrestler.html?id= links (97 shards of ~400 ids instead of one 1.5 MB file).
      Shard = Number(id) % 97 (ids are < 2^53, exact in JS). Not the last digits:
      TrackWrestling ids end in fixed suffixes like ...132 / ...009.
  seo/teams.json
      {team_id: {"name", "season"}} for every team page that has data: a
      data/teams/<id>.json whose id matches a team in the latest
      data/team_metrics/<season>/team_metrics.json (ignoring punctuation, as
      team.js does). Anything else at /team/<x> gets a real 404.
  And adds "url_slug" to every wrestler profile and "opponent_url_slug" to
  each match_list row that has a known opponent, so pages build clean links
  without a lookup. build_wrestler_profiles.py rewrites profiles without these
  fields, so this script must run after it (pipeline step "Build URL Slugs").

Run (after profiles + career linking):
    .venv/bin/python scripts/seo/build_url_slugs.py [--dry-run]
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAREERS_DIR = ROOT / "data/careers/ncaa_men"
PROFILES_DIR = ROOT / "frontend/wrestledata-ui/public/data/wrestlers"
STATE_PATH = ROOT / "data/url_slugs/ncaa_men.json"
PUBLIC_DIR = ROOT / "frontend/wrestledata-ui/public/seo"
TEAMS_DIR = ROOT / "frontend/wrestledata-ui/public/data/teams"
TEAM_METRICS_DIR = ROOT / "frontend/wrestledata-ui/public/data/team_metrics"
DATA_DIR = ROOT / "frontend/wrestledata-ui/public/data"
SEARCH_INDEX = ROOT / "frontend/wrestledata-ui/public/search_index.js"

# Data files that pages build wrestler links from (relative to DATA_DIR). Every
# object in them with a "wrestler_id" gets "url_path" right after it.
# Not included on purpose: reports/ (15k files, 107 MB, two minor report pages;
# their old ?id= links 301) and the large per-match Mat Value files.
DATA_PATCH_GLOBS = [
    "p4p/*.json",                          # rankings P4P tab, wrestlers directory
    "public_rankings/*/*.json",            # rankings page
    "rankings/*/*.json",                   # homepage, DPG leaderboard
    "leaderboards/*.json",                 # leaderboards, homepage
    "awards/*/*/*.json",                   # Hodge, Freshman of the Year
    "xtp/*/xtp_weight_*.json",             # AA odds
    "mat_value/*/mat_value_[0-9]*.json",   # DPG leaderboard, homepage
]


# Programs whose team_slug changed over the years: older seasons' profiles still carry
# the old one. Used for the school suffix so it names the program as it is today.
# The website's copy (team page redirects) is TEAM_SLUG_ALIASES in
# frontend/wrestledata-ui/public/seo_text.js -- keep the two in step.
# (Gone / non-D1 programs -- old_dominion, eastern_michigan, boston_u, grand_canyon,
# millersville, allstar_* ... -- keep their own slug.)
TEAM_SLUG_RENAMES = {
    "army": "army_west_point",
    "binghamton_university": "binghamton",
    "franklin__marshall": "franklin_marshall",
    "north_carolina_state": "nc_state",
    "north_dakota_state_university": "north_dakota_state",
    "southern_illinois_edwardsville": "siu_edwardsville",
    "utah_valley_university": "utah_valley",
}


def slugify(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    # Apostrophe stand-ins seen in the data: ' ’ ` and ? (lost encoding, "D?Ambrosio").
    text = re.sub(r"['’`?.]", "", text)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def tracked_profiles():
    """{wrestler_id: (season, path)} for every profile tracked in git."""
    out = subprocess.run(["git", "ls-files", str(PROFILES_DIR.relative_to(ROOT))],
                         capture_output=True, text=True, check=True, cwd=ROOT).stdout
    found = {}
    for line in out.splitlines():
        p = Path(line)
        if p.suffix != ".json" or p.parent.name != "by_id":
            continue
        season = p.parent.parent.name
        wid = p.stem
        # Skips stray copies like "10430251132 (1).json" (4,535 stale 2020 copies were
        # committed 2026-09-10 in 8ee6c9a209; see docs/TODO.md).
        if not season.isdigit() or not wid.isdigit():
            continue
        # A wrestler_id is season-specific; if one ever appears twice, keep the newest season.
        if wid not in found or int(season) > int(found[wid][0]):
            found[wid] = (season, ROOT / p)
    return found


def load_careers(profiles):
    """{"c:<n>": {season: id}} for careers, keeping only seasons with a tracked profile."""
    careers = {}
    for f in sorted(CAREERS_DIR.glob("career_*.json")):
        d = json.loads(f.read_text())
        n = str(int(d["career_id"].split("_")[1]))
        seasons = {s: str(i) for s, i in (d.get("seasons") or {}).items() if str(i) in profiles}
        if seasons:
            careers[f"c:{n}"] = seasons
    return careers


def json_style(raw):
    """The json.dumps settings that reproduce this file byte for byte, or None."""
    d = json.loads(raw)
    for indent in (2, 1, 4, None):
        for ensure_ascii in (False, True):
            for seps in (((", ", ": "), (",", ":")) if indent is None else ((",", ": "),)):
                s = dict(indent=indent, ensure_ascii=ensure_ascii, separators=seps)
                dumped = json.dumps(d, **s)
                if dumped == raw or dumped + "\n" == raw:
                    return s
    return None


def add_url_paths(node, id_path):
    """Adds "url_path" after every "wrestler_id" we know (replacing an old one)."""
    if isinstance(node, list):
        return [add_url_paths(x, id_path) for x in node]
    if not isinstance(node, dict):
        return node
    path = id_path.get(str(node.get("wrestler_id"))) if "wrestler_id" in node else None
    out = {}
    for k, v in node.items():
        if k == "url_path":
            continue
        out[k] = add_url_paths(v, id_path)
        if k == "wrestler_id" and path:
            out["url_path"] = path
    return out


SEARCH_RE = re.compile(r"\A(?P<head>.*?=\s*)(?P<body>\[.*\])(?P<tail>\s*;?\s*)\Z", re.S)


def rewrite_search_index(raw, id_path):
    """search_index.js (window.SEARCH_INDEX = [...]): wrestler url -> name address
    with "wrestler_id" kept as its own field; team url -> /team/<id-with-hyphens>
    with "team_id" kept (tools/compare.js and schedule.js read those). Re-runs
    rebuild the url from the kept id. None if the file doesn't look as expected."""
    m = SEARCH_RE.match(raw)
    if not m:
        return None
    items = json.loads(m.group("body"))
    style = json_style(m.group("body"))
    if style is None:
        return None
    out = []
    for it in items:
        it = dict(it)
        url = it.get("url") or ""
        if it.get("type") == "wrestler":
            wid = str(it.get("wrestler_id") or "")
            if not wid:
                q = re.search(r"[?&]id=(\d+)", url)
                wid = q.group(1) if q else ""
            if wid in id_path:
                new = {}
                for k, v in it.items():
                    if k in ("wrestler_id", "url"):
                        continue
                    new[k] = v
                    if k == "type":
                        new["wrestler_id"] = wid
                        new["url"] = id_path[wid]
                it = new
        elif it.get("type") == "team":
            tid = it.get("team_id")
            if not tid:
                q = re.search(r"[?&]team=([^&]+)", url)
                tid = q.group(1) if q else None
            if tid:
                tid = TEAM_SLUG_RENAMES.get(tid, tid)
                new = {}
                for k, v in it.items():
                    if k in ("team_id", "url"):
                        continue
                    new[k] = v
                    if k == "type":
                        new["team_id"] = tid
                        new["url"] = "/team/" + tid.replace("_", "-")
                it = new
        out.append(it)
    return m.group("head") + json.dumps(out, **style) + m.group("tail")


def parse_record(rec):
    """'12-3' -> (12, 3). Anything else -> None."""
    m = re.fullmatch(r"\s*(\d+)-(\d+)(?:-\d+)?\s*", rec or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    args = ap.parse_args()

    profiles = tracked_profiles()
    careers = load_careers(profiles)
    in_career = {i for seasons in careers.values() for i in seasons.values()}
    entities = dict(careers)
    for wid, (season, _) in profiles.items():
        if wid not in in_career:
            entities[f"w:{wid}"] = {season: wid}

    cache = {}

    def profile(wid):
        if wid not in cache:
            cache[wid] = json.loads(profiles[wid][1].read_text())
        return cache[wid]

    def latest(seasons):
        s = max(seasons, key=int)
        return s, seasons[s]

    def first_school(seasons):
        p = profile(seasons[min(seasons, key=int)])
        team = p.get("team_slug") or ""
        return slugify(TEAM_SLUG_RENAMES.get(team, team) or p.get("team") or "")

    # ---- state ----
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    known = state.get("wrestlers", {})   # key -> {"slug", "base", "ids"}
    aliases = state.get("aliases", {})   # old slug -> slug it redirects to
    taken = {v["slug"] for v in known.values()} | set(aliases)
    id_owner_now = {i: k for k, seasons in entities.items() for i in seasons.values()}

    report = Counter()

    # 1. Entities that disappeared (career merged away, unlinked season now in a career).
    for key in [k for k in known if k not in entities]:
        old = known.pop(key)
        successors = {id_owner_now[i] for i in old.get("ids", []) if i in id_owner_now}
        succ = min(successors) if successors else None
        if succ and succ not in known:
            # The successor has no slug yet: hand this one over (keeps the URL).
            known[succ] = {"slug": old["slug"], "base": old["base"], "ids": []}
            report["slug handed to successor"] += 1
        elif succ:
            aliases[old["slug"]] = known[succ]["slug"]
            report["slug -> alias"] += 1
        else:
            # Nothing holds its seasons any more; keep the slug reserved, no redirect target.
            aliases[old["slug"]] = None
            report["slug orphaned (reserved)"] += 1
            print(f"WARNING: {key} ({old['slug']}) is gone and nothing holds its seasons", file=sys.stderr)

    # 2. New entities get slugs.
    new_keys = sorted((k for k in entities if k not in known),
                      key=lambda k: (k[0], int(k[2:])))  # careers (c) first, then by number / id
    names = {k: profile(latest(entities[k])[1]).get("name") or "" for k in entities}
    base_count = Counter(v["base"] for v in known.values())
    base_count.update(slugify(names[k]) for k in new_keys)
    for key in new_keys:
        base = slugify(names[key]) or "wrestler"
        slug = base
        if base_count[base] > 1 or slug in taken:
            school = first_school(entities[key])
            slug = f"{base}-{school}" if school else base
            n = 2
            while slug in taken:
                slug = f"{base}-{school}-{n}" if school else f"{base}-{n}"
                n += 1
        known[key] = {"slug": slug, "base": base, "ids": []}
        taken.add(slug)
        report["new slugs"] += 1
    # A slug can't be both live and an alias (e.g. handed back to a successor).
    for k in [a for a in aliases if a in {v["slug"] for v in known.values()}]:
        del aliases[k]
    # Resolve alias chains (a -> b -> c becomes a -> c).
    live = {v["slug"] for v in known.values()}
    for a in list(aliases):
        seen, t = set(), aliases[a]
        while t is not None and t not in live and t in aliases and t not in seen:
            seen.add(t)
            t = aliases[t]
        aliases[a] = t

    for key, seasons in entities.items():
        known[key]["ids"] = sorted(seasons.values())

    # ---- published files ----
    slug_files = {}
    by_id = {}
    for key, seasons in entities.items():
        slug = known[key]["slug"]
        ls, lid = latest(seasons)
        p = profile(lid)
        recs = [parse_record((profile(i).get("record") or {}).get("overall")) for i in seasons.values()]
        recs_ok = [r for r in recs if r]
        slug_files[slug] = {
            "slug": slug,
            "name": p.get("name"),
            "latest_season": int(ls),
            "latest_id": lid,
            "seasons": {s: seasons[s] for s in sorted(seasons, key=int, reverse=True)},
            "team": p.get("team"),
            "team_slug": p.get("team_slug"),
            "weight": p.get("weight_class"),
            "rank": p.get("current_rank"),
            "career_record": f"{sum(r[0] for r in recs_ok)}-{sum(r[1] for r in recs_ok)}" if recs_ok else None,
            "season_record": (p.get("record") or {}).get("overall"),
        }
        for s, i in seasons.items():
            by_id[i] = [slug, int(s), 1 if i == lid else 0]
    for a, target in aliases.items():
        if target:
            slug_files[a] = {"slug": a, "alias_of": target}

    shards = {}
    for i, v in by_id.items():
        shards.setdefault(str(int(i) % 97), {})[i] = v

    # ---- team pages with data ----
    bare = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())
    metric_seasons = sorted((d.name for d in TEAM_METRICS_DIR.iterdir()
                             if d.name.isdigit() and (d / "team_metrics.json").exists()), key=int)
    teams_json = {}
    if metric_seasons:
        tm_season = metric_seasons[-1]
        tm = json.loads((TEAM_METRICS_DIR / tm_season / "team_metrics.json").read_text())
        with_metrics = {bare(x["team_id"]) for x in tm.get("teams", [])}
        for f in sorted(TEAMS_DIR.glob("*.json")):
            if bare(f.stem) in with_metrics:
                td = json.loads(f.read_text())
                teams_json[f.stem] = {"name": td.get("team_name") or td.get("name"), "season": int(tm_season)}

    # ---- profile fields ----
    # url_path = the ready-made link: /wrestler/<slug>, plus ?season=YYYY when
    # that season id isn't the wrestler's latest (so a link from a 2024 match
    # history opens 2024). Pages pass it to wrestlerHref() in header.js.
    id_slug = {i: v[0] for i, v in by_id.items()}
    id_path = {i: f"/wrestler/{v[0]}" + ("" if v[2] else f"?season={v[1]}") for i, v in by_id.items()}
    changed_files = []
    for wid, (season, path) in profiles.items():
        raw = path.read_text()
        d = json.loads(raw)
        out = {}
        for k, v in d.items():
            if k in ("url_slug", "url_path"):
                continue
            out[k] = v
            if k == "wrestler_id":
                out["url_slug"] = id_slug.get(wid)
                out["url_path"] = id_path.get(wid)
        for m in out.get("match_list") or []:
            opp = m.get("opponent_id")
            opp_path = id_path.get(str(opp)) if opp else None
            items = [(k, v) for k, v in m.items() if k not in ("opponent_url_slug", "opponent_url_path")]
            m.clear()
            for k, v in items:
                m[k] = v
                if k == "opponent_id" and opp_path:
                    m["opponent_url_path"] = opp_path
        new_raw = json.dumps(out, indent=2, ensure_ascii=False) + ("\n" if raw.endswith("\n") else "")
        if new_raw != raw:
            changed_files.append((path, new_raw))
    n_profiles = len(changed_files)

    # ---- other data files the site builds wrestler links from ----
    n_data, skipped = 0, []
    for g in DATA_PATCH_GLOBS:
        for f in sorted(DATA_DIR.glob(g)):
            raw = f.read_text()
            style = json_style(raw)
            if style is None:
                skipped.append(str(f.relative_to(DATA_DIR)))
                continue
            d = add_url_paths(json.loads(raw), id_path)
            new_raw = json.dumps(d, **style) + ("\n" if raw.endswith("\n") else "")
            if new_raw != raw:
                changed_files.append((f, new_raw))
                n_data += 1

    # ---- search index: name addresses, ids kept as fields ----
    search_raw = SEARCH_INDEX.read_text() if SEARCH_INDEX.exists() else None
    new_search = rewrite_search_index(search_raw, id_path) if search_raw else None
    if new_search is not None and new_search != search_raw:
        changed_files.append((SEARCH_INDEX, new_search))

    print(f"Entities: {len(entities)} ({len(careers)} careers, {len(entities) - len(careers)} unlinked season profiles)")
    for k, v in sorted(report.items()):
        print(f"  {k}: {v}")
    suffixed = sum(1 for v in known.values() if v["slug"] != v["base"])
    print(f"  slugs with a school/number suffix: {suffixed}")
    print(f"  aliases: {sum(1 for t in aliases.values() if t)} (+{sum(1 for t in aliases.values() if not t)} reserved)")
    print(f"Published: {len(slug_files)} slug files, {len(shards)} id shards, {len(teams_json)} team pages")
    print(f"To update: {n_profiles} profiles, {n_data} other data files"
          f"{', search_index.js' if new_search is not None and new_search != search_raw else ''}")
    if skipped:
        print(f"WARNING: left alone (can't rewrite without reformatting): {skipped}", file=sys.stderr)
    if args.dry_run:
        print("(dry run: nothing written)")
        return

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({
        "_about": "MatSavant wrestler URL slugs. Append-only source of truth -- see scripts/seo/build_url_slugs.py.",
        "wrestlers": dict(sorted(known.items(), key=lambda kv: (kv[0][0], int(kv[0][2:])))),
        "aliases": dict(sorted(aliases.items())),
    }, indent=1, ensure_ascii=False) + "\n")

    (PUBLIC_DIR / "teams.json").parent.mkdir(parents=True, exist_ok=True)
    (PUBLIC_DIR / "teams.json").write_text(json.dumps(teams_json, indent=1, ensure_ascii=False) + "\n")

    for sub, files in (("wrestlers", slug_files), ("by_id", shards)):
        d = PUBLIC_DIR / sub
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        for name, obj in files.items():
            (d / f"{name}.json").write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))

    for path, new_raw in changed_files:
        path.write_text(new_raw)
    print("Written.")


if __name__ == "__main__":
    main()
