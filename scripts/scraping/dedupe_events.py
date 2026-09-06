#!/usr/bin/env python3
"""
First-pass event deduplication across all scraped official schedules.

Two separate matching problems, per the design discussion this session:
  1. DUALS -- pairwise. Once each side's "opponent" string resolves to a
     canonical team slug, a real dual should appear in BOTH teams' own
     schedules (one says "home vs X", the other says "away at Y"). Match
     key: (date, frozenset({team_a, team_b})). When both sides agree, merge
     into one record and fill gaps from whichever side has richer data
     (TV info, final score, etc).
  2. TOURNAMENTS -- N-way. Many teams' schedules independently reference
     the same named event. Match key: (normalized event name, date). Group
     every team that mentions a matching name+date into one record with a
     list of participants.

Team-name resolution is intentionally conservative: only resolves a raw
scraped string to a slug when it's unambiguous (exact/substring match
against the current D1 team list, or a short explicit alias list for real
variants already seen in scraped data -- "NC State University" -> nc_state,
"UT Chattanooga" -> chattanooga, "LIU"/"Long Island" -> liu, etc). A string
that doesn't resolve is treated as a tournament/other-event name, not a
dual opponent -- this is deliberately simple for a first pass; genuinely
ambiguous abbreviations (the "OSU" problem) aren't handled yet and would
need the location + reciprocal-schedule disambiguation discussed earlier.

Usage:
  .venv/bin/python scripts/scraping/dedupe_events.py
"""
import glob
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from batch_scrape_schedules import build_team_map  # noqa: E402 -- single source of truth for slug<->name

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEDULES_DIR = PROJECT_ROOT / "mt" / "data" / "official_schedules"

# Real variant spellings already observed in scraped data that a plain
# normalize() won't bridge on its own -- extend this as new cases surface
# (the "match first, fix as it comes" approach agreed on this session).
# NOTE: these are text-variant aliases only (different ways of *writing* a
# team's name). They are NOT for slug-scheme differences -- those come from
# build_team_map() below, the same slug source batch_scrape_schedules.py
# uses to name each team's own schedule folder (mt/data/official_schedules/
# {slug}/), so a team's schedule-folder slug and its resolved-opponent slug
# are guaranteed to be the same string. Previously this file derived its own
# slugs via slugify(name) independently of that folder-naming scheme, which
# silently broke dual-confirmation and display names for any team whose
# folder slug isn't just slugify(name) -- e.g. South Dakota State's folder
# is "sd_state", not "south_dakota_state"; Northern Colorado's is
# "n_colorado". A dual would never show as "confirmed both sides" for such
# a team, because the two code paths were computing two different slugs for
# the same school.
EXTRA_ALIASES = {
    "long island": "liu",
    "virginia military institute": "vmi",
    "ut chattanooga": "chattanooga",
    "university of buffalo": "buffalo",
    "university of pennsylvania": "penn",
}


def normalize(s):
    s = s.lower()
    s = re.sub(r"^university of\s+", "", s)
    s = re.sub(r"\b(university|college)\b", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return s


def build_team_index():
    """Returns {normalized_name: slug} for every current D1 team, plus the
    extra alias entries. Slugs come from build_team_map() (the scraper's
    own folder-naming scheme), not a fresh slugify(name)."""
    team_map = build_team_map()
    index = {}
    for slug, (name, _url) in team_map.items():
        index[normalize(name)] = slug
    for alias, target_slug in EXTRA_ALIASES.items():
        index[alias] = target_slug
    return index


def build_slug_to_norm():
    """Returns {slug: canonical_normalized_name}, one entry per real team
    (unlike build_team_index(), no aliases -- used for the "is this
    single-sided dual actually a mention of a tournament hosted by the
    'opponent' school" prefix check below, where we need each team's own
    canonical name, longest-match-wins)."""
    return {slug: normalize(name) for slug, (name, _url) in build_team_map().items()}


def build_slug_to_display():
    """Returns {slug: display_name} for readable output -- the team list's
    own name string, not a normalized/slugified version of it."""
    return {slug: name for slug, (name, _url) in build_team_map().items()}


TOURNAMENT_KEYWORDS = re.compile(
    r"\b(open|invite|invitational|classic|tournament|duals?|championships?|"
    r"round\s*robin|scrimmage|wrestle.?offs?|showcase|salute|scuffle|"
    r"nationals?|dual\s*meet|session|day\s*[ivx0-9]+)\b",
    re.IGNORECASE,
)

# A school's own intra-squad exhibition (no real opponent, not a real
# tournament) -- these still get parsed as an "event" off the schedule page
# but should never be treated as a tournament to merge across schools, since
# they're inherently single-team. Kept (tagged "scrimmage") rather than
# dropped, per the user's call, but excluded from the tournament bucket.
SCRIMMAGE_KEYWORDS = re.compile(
    r"\b(wrestle.?offs?|scrimmage|showcase)\b",
    re.IGNORECASE,
)


def resolve_team(raw_name, team_index):
    """Returns a team slug if raw_name unambiguously matches exactly one
    known team, else None (treated as a tournament/other-event name).

    Checks for a tournament-naming keyword FIRST and refuses to resolve at
    all if one is present -- confirmed necessary: a school's own team name
    is often a substring of a tournament hosted there or named after it
    ("Clarion Open" contains "Clarion", "Mercyhurst Invite" contains
    "Mercyhurst", "Navy Classic" contains "Navy"), and without this guard
    those all silently became fake DUALS against that team instead of the
    tournament mentions they actually are."""
    if not raw_name:
        return None
    if TOURNAMENT_KEYWORDS.search(raw_name):
        return None
    norm = normalize(raw_name)
    if norm in team_index:
        return team_index[norm]
    # substring match, but only accept if exactly one team matches --
    # ambiguous or zero matches both fall through to "not a team"
    matches = {slug for known, slug in team_index.items() if known and (known in norm or norm in known)}
    if len(matches) == 1:
        return matches.pop()
    return None


TOURNAMENT_STOPWORDS = re.compile(r"\b(day|session)\s*[ivx0-9]+\b", re.IGNORECASE)


def normalize_tournament_name(name):
    n = name.lower()
    n = TOURNAMENT_STOPWORDS.sub("", n)
    n = re.sub(r"\(.*?\)", "", n)  # strip "(Day 1)" style parentheticals
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    # A leading season year is the same real-world event with or without it
    # ("2026 Clarion Open" vs "Clarion Open", "2026 National Duals" vs
    # "National Duals Invitational") -- without stripping it these silently
    # failed to merge even though every other school's mention of the same
    # tournament, same date, did merge.
    n = re.sub(r"^(19|20)\d{2}\s+", "", n)
    # Drop a few generic words/phrases that vary school-to-school for the
    # same event. "national" and "division i/1" specifically exist because
    # the NCAA national tournament itself was splitting into up to 3
    # canonical entries per season -- "NCAA National Championships" vs
    # "NCAA Division I Wrestling Championships" vs plain "NCAA Championship"
    # are all the same event, worded differently by different schools' sites.
    for phrase in ("division i", "division 1", "national", "wrestling", "collegiate",
                   "invitational", "invite", "championships", "championship", "tournament"):
        n = re.sub(rf"\b{re.escape(phrase)}\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


def load_all_events():
    events = []
    for f in sorted(glob.glob(str(SCHEDULES_DIR / "*" / "2026-27.json"))):
        team_slug = Path(f).parent.name
        d = json.loads(Path(f).read_text())
        for e in d["events"]:
            events.append({**e, "_team": team_slug})
    return events


def dedupe(events, team_index):
    duals = defaultdict(list)       # (date, frozenset({a,b})) -> [event, event, ...]
    tournaments = defaultdict(list)  # (norm_name, date) -> [event, ...]
    scrimmages = defaultdict(list)   # (norm_name, date) -> [event, ...] -- intra-squad, never merged across teams
    unresolved_singles = []

    for e in events:
        if not e.get("date"):
            continue
        who = e.get("opponent") or e.get("event_name") or ""
        opp_slug = resolve_team(who, team_index)
        if opp_slug and opp_slug != e["_team"]:
            key = (e["date"], frozenset({e["_team"], opp_slug}))
            duals[key].append(e)
        elif SCRIMMAGE_KEYWORDS.search(who):
            norm = normalize_tournament_name(who) or who.lower()
            scrimmages[(norm, e["date"])].append(e)
        else:
            norm = normalize_tournament_name(who)
            if norm:
                tournaments[(norm, e["date"])].append(e)
            else:
                unresolved_singles.append(e)

    return duals, tournaments, scrimmages, unresolved_singles


def merge_similar_tournaments(tournaments):
    """Second pass: merges same-date tournament entries that are really the
    same real event under different school-specific wording -- "Cornell Big
    Red Invitational" vs "Big Red Invitational", "PRTC Keystone Classic" vs
    "Keystone Classic", "Cliff Keen Invitational" vs "Cliff Keen Las Vegas
    Invitational" vs "Cliff Keen Las Vegas Collegiate Invitational". These
    weren't already unified by the exact (norm_name, date) key because one
    school's own site adds a host prefix, a city name, or an extra word the
    others don't use.

    Merge rule: same date, and one entry's word-set is a full subset of the
    other's. The subset side must still have >= 2 meaningful words left --
    a single leftover word (e.g. a mention that normalizes down to just
    "Duals") is too generic to safely merge on its own; this is the same
    ambiguous-matching concern raised earlier for team abbreviations (don't
    silently fold something together on a thin, coincidental text match).
    Confirmed against real data: this exact rule merges all 3 of the cases
    above correctly, while leaving unrelated same-date events (which share
    no such subset relationship) untouched.
    """
    by_date = defaultdict(list)
    for norm_name, date in tournaments.keys():
        by_date[date].append(norm_name)

    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for date, names in by_date.items():
        word_sets = {n: set(n.split()) for n in set(names)}
        names_list = list(word_sets.keys())
        for i, a in enumerate(names_list):
            for b in names_list[i + 1:]:
                wa, wb = word_sets[a], word_sets[b]
                if min(len(wa), len(wb)) < 2:
                    continue
                if wa <= wb or wb <= wa:
                    union((a, date), (b, date))

    groups = defaultdict(list)
    for key in tournaments.keys():
        groups[find(key)].append(key)

    merged = {}
    for keys in groups.values():
        if len(keys) == 1:
            merged[keys[0]] = tournaments[keys[0]]
            continue
        combined = []
        for k in keys:
            combined.extend(tournaments[k])
        canonical_key = max(keys, key=lambda k: len(tournaments[k]))
        merged[canonical_key] = combined

    return merged


def reconcile_ambiguous_duals(duals, tournaments, slug_to_norm):
    """Catches the "Edinboro says it's playing Michigan State University,
    but Bucknell/Michigan both say they're at the Michigan State Open, same
    date" case: a raw opponent string that's just a plain school name is
    actually that school's own tournament, not a real dual against them.

    Only reconciles a dual that's single-sided (nobody's schedule confirms
    it as a real two-team meet) AND whose "opponent" school's own name is
    an unambiguous prefix of a real tournament's normalized name on that
    same date. "Unambiguous" here specifically means: no OTHER real team's
    (longer) name is also a valid prefix of that same tournament name --
    this is exactly the guard the ambiguous-abbreviation concern from this
    session's design discussion calls for (e.g. never let "Iowa" quietly
    absorb an "Iowa State Open" mention just because "Iowa" is a text
    prefix of "Iowa State" -- "Iowa State" is the longer, more specific
    match, so "Iowa" is correctly left alone as still-ambiguous instead of
    silently merged).
    """
    by_len = sorted(slug_to_norm.items(), key=lambda kv: -len(kv[1]))
    reconciled = []

    for key in list(duals.keys()):
        date, pair = key
        members = duals[key]
        teams_involved = {m["_team"] for m in members}
        if len(teams_involved) != 1:
            continue  # confirmed both-sides dual -- a real match, leave it
        reporting_team = next(iter(teams_involved))
        other = next(t for t in pair if t != reporting_team)
        other_norm = slug_to_norm.get(other)
        if not other_norm:
            continue

        for (norm_name, t_date), t_members in tournaments.items():
            if t_date != date:
                continue
            if not (norm_name == other_norm or norm_name.startswith(other_norm + " ")):
                continue
            # Ambiguity guard: does any OTHER, longer team name also match
            # as a prefix of this same tournament name? If so, "other" is
            # not a safe host match -- skip, leave the dual flagged as-is.
            longer_match_exists = any(
                slug != other and len(norm) > len(other_norm)
                and (norm_name == norm or norm_name.startswith(norm + " "))
                for slug, norm in by_len
            )
            if longer_match_exists:
                continue
            t_members.append({**members[0], "_team": reporting_team})
            reconciled.append((key, (norm_name, t_date), reporting_team))
            del duals[key]
            break

    return reconciled


def _pick_display_name(members):
    names = {m.get("opponent") or m.get("event_name") for m in members}
    # Prefer a name that actually reads as a tournament (has one of the
    # TOURNAMENT_KEYWORDS) over the longest string -- a reconciled entry
    # can include a raw opponent string that's just a plain school name
    # ("Michigan State University"), which is longer than the real
    # tournament name ("Michigan State Open") but is the wrong display.
    keyworded = {n for n in names if n and TOURNAMENT_KEYWORDS.search(n)}
    return max(keyworded or names, key=len)


def _strip_day_label(name):
    """Removes a "(Day 1)" / "- Day II" / "- Session VI" style suffix from
    a display name. Used only for the shared cross-date canonical name of a
    multi-day tournament series -- the record's own `date` field is what
    actually tells you which day it is, so baking one arbitrary day/session
    label from whichever date happened to produce the longest raw string
    into the name shared by every OTHER date in the series would be wrong
    (e.g. every day of the NCAA Championships showing "(Day 2)")."""
    n = TOURNAMENT_STOPWORDS.sub("", name)
    n = re.sub(r"\(\s*\)", "", n)       # empty parens left behind
    n = re.sub(r"\s*-\s*$", "", n)      # dangling trailing " - "
    return re.sub(r"\s{2,}", " ", n).strip()


FRONTEND_DUALS_PATH = (
    PROJECT_ROOT / "frontend" / "wrestledata-ui" / "public" / "data" / "schedule" / "duals_2026-27.json"
)


def frontend_slug(name):
    """Same algorithm as teamNameToSlug() in frontend/wrestledata-ui/public/
    app.js and homepage.js -- deliberately NOT the same slug as this file's
    own build_team_index()/build_slug_to_display(), which come from the
    schedule scraper's own folder-naming convention (batch_scrape_schedules.
    build_team_map(), e.g. "army", "sd_state", "n_colorado"). The frontend's
    team pages use a different, fuller slug for the same schools (e.g.
    "army_west_point.json", "south_dakota_state.json", "northern_colorado.
    json" under data/teams/) -- exporting scrape-slugs here would silently
    produce dead team.html links for every team whose two slug schemes
    diverge."""
    if not name:
        return ""
    s = name.lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^\w_]", "", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_")


def export_duals_for_ticker(dual_records, slug_to_display, out_path):
    """Writes the upcoming-duals ticker feed consumed by the MatSavant
    homepage ticker -- date-sorted, only today-or-later, frontend-facing
    team slugs (see frontend_slug() above), no scores (schedule data only,
    per the user's "for now just upcoming with no scores" scope)."""
    import datetime

    today = datetime.date.today().isoformat()
    out = []
    for r in sorted(dual_records, key=lambda r: r["date"]):
        if r["date"] < today:
            continue
        a, b = r["team_pair"]
        name_a, name_b = slug_to_display.get(a, a), slug_to_display.get(b, b)
        out.append({
            "date": r["date"],
            "team_a": {"slug": frontend_slug(name_a), "name": name_a},
            "team_b": {"slug": frontend_slug(name_b), "name": name_b},
            "confirmed": r["confirmed_both_sides"],
        })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    return len(out)


def main():
    team_index = build_team_index()
    events = load_all_events()
    print(f"Raw events loaded: {len(events)}")

    duals, tournaments, scrimmages, unresolved = dedupe(events, team_index)

    tournaments = merge_similar_tournaments(tournaments)

    slug_to_norm = build_slug_to_norm()
    reconciled = reconcile_ambiguous_duals(duals, tournaments, slug_to_norm)
    if reconciled:
        print(f"Reconciled {len(reconciled)} single-sided dual(s) into existing tournaments:")
        for (date, pair), (norm_name, t_date), team in reconciled:
            print(f"  {date}: {team}'s reported dual -> folded into tournament matching '{norm_name}'")

    dual_records = []
    for (date, team_pair), members in duals.items():
        teams_involved = sorted({m["_team"] for m in members})
        dual_records.append({
            "date": date,
            "type": "dual",
            "teams": teams_involved,
            "team_pair": sorted(team_pair),
            "confirmed_both_sides": len(teams_involved) == 2,
            "locations": sorted({m.get("location") for m in members if m.get("location")}),
        })

    # One canonical display name per norm_name, shared across every date it
    # appears on -- a multi-day tournament (Big Ten Championships, NCAAs)
    # gets worded slightly differently depending on whichever school's raw
    # text happens to be the longest on any given day (e.g. day 1-3 might
    # only have schools saying "NCAA Division I Wrestling Championships",
    # while the lone team still alive on the final day says "NCAA Division
    # I Championships - Session VI"). Since normalize_tournament_name()
    # already reduces all of those to the same norm_name regardless of
    # date, pick the name from the union of every date's raw mentions
    # instead of only that one day's, so the whole series reads as one
    # event with one name.
    members_by_norm_name = defaultdict(list)
    for (norm_name, date), members in tournaments.items():
        members_by_norm_name[norm_name].extend(members)
    canonical_names = {
        norm_name: _strip_day_label(_pick_display_name(members))
        for norm_name, members in members_by_norm_name.items()
    }

    tourney_records = []
    for (norm_name, date), members in tournaments.items():
        teams_involved = sorted({m["_team"] for m in members})
        tourney_records.append({
            "date": date,
            "type": "tournament",
            "name": canonical_names[norm_name],
            "teams": teams_involved,
            "num_mentions": len(members),
        })

    scrimmage_records = []
    for (norm_name, date), members in scrimmages.items():
        teams_involved = sorted({m["_team"] for m in members})
        scrimmage_records.append({
            "date": date,
            "type": "scrimmage",
            "name": _pick_display_name(members),
            "teams": teams_involved,
            "num_mentions": len(members),
        })

    all_records = sorted(dual_records + tourney_records + scrimmage_records, key=lambda r: r["date"])

    n_confirmed_duals = sum(1 for r in dual_records if r["confirmed_both_sides"])
    n_single_side_duals = len(dual_records) - n_confirmed_duals
    print(f"Duals: {len(dual_records)} canonical ({n_confirmed_duals} confirmed both sides, "
          f"{n_single_side_duals} single-sided so far)")
    print(f"Tournaments: {len(tourney_records)} canonical (from {sum(r['num_mentions'] for r in tourney_records)} raw mentions)")
    print(f"Scrimmages: {len(scrimmage_records)} (intra-squad, not merged across teams)")
    print(f"Unresolved singles (no date match / neither team nor tournament pattern): {len(unresolved)}")
    print(f"Total canonical events: {len(all_records)}  (from {len(events)} raw)")

    display = build_slug_to_display()
    n_exported = export_duals_for_ticker(dual_records, display, FRONTEND_DUALS_PATH)
    print(f"Wrote {n_exported} upcoming duals to {FRONTEND_DUALS_PATH.relative_to(PROJECT_ROOT)}")

    if "--list" in sys.argv:
        print()
        for i, r in enumerate(all_records, 1):
            if r["type"] == "dual":
                a, b = r["team_pair"]
                a, b = display.get(a, a), display.get(b, b)
                tag = "confirmed" if r["confirmed_both_sides"] else "single-sided"
                print(f"{i:>3}. {r['date']}  DUAL          {a} vs {b}  ({tag})")
            else:
                label = "TOURNAMENT" if r["type"] == "tournament" else "SCRIMMAGE "
                team_names = ", ".join(display.get(t, t) for t in r["teams"])
                print(f"{i:>3}. {r['date']}  {label}    {r['name']}  [{len(r['teams'])} team(s): {team_names}]")

    return all_records


if __name__ == "__main__":
    main()
