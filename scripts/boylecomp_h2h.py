#!/usr/bin/env python3
"""
Boyle County competition H2H and common-opponent report.

Parses data/boylecomp.txt:
  - Weight (e.g. 106)
  - Boyle County wrestler name
  - Pairs of opponent name / school (until blank line)
  - Special: "Bentley Wren 285" has weight+name on one line
  - "Unbeaten Participants" is header for 285 opponents

For each weight: lists Boyle wrestler, then opponents in three categories:
  1. Head-to-head wins (Boyle beat them)
  2. Common opponent wins (Boyle beat X, opponent lost to X)
  3. Neither H2H nor common opponent

Includes records for each wrestler. Wrestlers not in database trigger interactive
lookup; resolved mappings update boylecomp.txt for future runs.

Leverages region_h2h_and_common_opponents.py for H2H/CO logic.

Usage:
  python scripts/boylecomp_h2h.py --season 2026
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BOYLECOMP_PATH = PROJECT_ROOT / "data" / "boylecomp.txt"
BOYLECOMP_LOOKUP_PATH = PROJECT_ROOT / "data" / "boylecomp_wrestler_lookup.json"
BOYLE_TEAM = "Boyle County"


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _override_key(name: str, team: str) -> str:
    return f"{name}|{team}"


def load_boylecomp_lookup() -> Dict[str, Dict]:
    """Load wrestler lookup: { override_key: { wrestler_id, name, team } }."""
    if not BOYLECOMP_LOOKUP_PATH.exists():
        return {}
    try:
        with BOYLECOMP_LOOKUP_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_boylecomp_lookup(lookup: Dict[str, Dict]) -> None:
    BOYLECOMP_LOOKUP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with BOYLECOMP_LOOKUP_PATH.open("w", encoding="utf-8") as f:
        json.dump(lookup, f, indent=2)
    print(f"  Saved lookup to {BOYLECOMP_LOOKUP_PATH}")


def parse_boylecomp(path: Path) -> List[Tuple[str, str, List[Tuple[str, str]]]]:
    """
    Parse boylecomp.txt. Returns list of (weight, boyle_wrestler, [(opp_name, opp_school), ...]).
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    lines = [ln.rstrip() for ln in text.splitlines()]
    result: List[Tuple[str, str, List[Tuple[str, str]]]] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip():
            continue

        # Check for "Weight Wrestler" on same line (e.g. "Bentley Wren 285")
        m = re.match(r"^(.+?)\s+(\d{2,3})\s*$", line.strip())
        if m:
            boyle_name = m.group(1).strip()
            weight = m.group(2)
            opponents: List[Tuple[str, str]] = []
            # Skip blanks and "Unbeaten Participants", then read name/school pairs
            while i < len(lines):
                next_line = lines[i].strip()
                if not next_line:
                    i += 1
                    continue
                if next_line == "Unbeaten Participants":
                    i += 1
                    continue
                if next_line.isdigit():
                    break  # Next weight started
                # Expect name, then school on next line
                if i + 1 < len(lines):
                    school = lines[i + 1].strip()
                    if school and not school.isdigit() and "Participants" not in school:
                        opponents.append((next_line, school))
                        i += 2
                        continue
                i += 1
                break
            result.append((weight, boyle_name, opponents))
            continue

        # Standard: weight on its own line
        if line.strip().isdigit():
            weight = line.strip()
            if i >= len(lines):
                break
            boyle_name = lines[i].strip()
            i += 1
            # Skip blank line(s) between Boyle wrestler and opponent list
            while i < len(lines) and not lines[i].strip():
                i += 1
            opponents = []
            while i < len(lines):
                name_line = lines[i].strip()
                i += 1
                if not name_line:
                    break
                if name_line == "Unbeaten Participants":
                    continue
                if name_line.isdigit():
                    # Next weight started
                    i -= 1
                    break
                if i < len(lines):
                    school_line = lines[i].strip()
                    if school_line and not school_line.isdigit() and "Participants" not in school_line:
                        opponents.append((name_line, school_line))
                        i += 1
            result.append((weight, boyle_name, opponents))

    return result


def find_wrestler(
    all_wrestlers: Dict[str, Dict],
    name: str,
    team: str,
    lookup: Dict[str, Dict],
) -> Optional[Dict]:
    """Find wrestler by name+team. Check lookup first, then fuzzy match in all_wrestlers."""
    key = _override_key(name, team)
    if key in lookup:
        entry = lookup[key]
        wid = entry.get("wrestler_id", "")
        if wid and wid in all_wrestlers:
            w = all_wrestlers[wid]
            return {"id": wid, "name": w.get("name", ""), "team": w.get("team", ""), **w}
        if wid:
            return {**entry, "id": wid}

    norm_name = _normalize(name)
    norm_team = _normalize(team)
    for wid, w in all_wrestlers.items():
        wteam = _normalize(w.get("team", ""))
        if wteam != norm_team:
            continue
        wname = _normalize(w.get("name", ""))
        if wname == norm_name:
            return {"id": wid, "name": w.get("name", ""), "team": w.get("team", ""), **w}
        # Fuzzy: last name match
        n1 = norm_name.split()
        n2 = wname.split()
        if len(n1) >= 2 and len(n2) >= 2 and n1[-1] == n2[-1]:
            if n1[0] == n2[0] or n1[0].startswith(n2[0]) or n2[0].startswith(n1[0]):
                return {"id": wid, "name": w.get("name", ""), "team": w.get("team", ""), **w}
    return None


def search_wrestlers_by_string(all_wrestlers: Dict[str, Dict], test_str: str) -> List[Dict]:
    """Search by substring in name or team."""
    norm = _normalize(test_str)
    if not norm:
        return []
    out = []
    for wid, w in all_wrestlers.items():
        if norm in _normalize(w.get("name", "")) or norm in _normalize(w.get("team", "")):
            out.append({"id": wid, "name": w.get("name", ""), "team": w.get("team", ""), **w})
    return out


def interactive_resolve(
    name: str,
    team: str,
    all_wrestlers: Dict[str, Dict],
    lookup: Dict[str, Dict],
) -> Dict:
    """Halt, prompt for test string, search, save to lookup, update boylecomp.txt."""
    print()
    print("=" * 60)
    print("WRESTLER NOT FOUND IN DATABASE")
    print("=" * 60)
    print(f"  From boylecomp: {name} ({team})")
    print()
    print("Enter a test string to search (name or team substring):")
    print("  (or wrestler_id:XXXX to use specific ID)")
    print()

    while True:
        try:
            test_str = input("> ").strip()
        except EOFError:
            print("Aborted.")
            raise SystemExit(1)
        if not test_str:
            continue

        if test_str.lower().startswith("wrestler_id:"):
            wid = test_str[12:].strip()
            if wid and wid in all_wrestlers:
                w = all_wrestlers[wid]
                entry = {
                    "wrestler_id": wid,
                    "name": w.get("name", ""),
                    "team": w.get("team", ""),
                }
                lookup[_override_key(name, team)] = entry
                save_boylecomp_lookup(lookup)
                update_boylecomp_file(name, team, w.get("name", ""), w.get("team", ""))
                return {"id": wid, "name": w.get("name", ""), "team": w.get("team", ""), **w}
            print("  Wrestler ID not found in database.")
            continue

        matches = search_wrestlers_by_string(all_wrestlers, test_str)
        if not matches:
            print(f"  No matches for '{test_str}'.")
            continue

        while True:
            print(f"  Found {len(matches)} match(es):")
            for idx, m in enumerate(matches[:20], 1):
                rec = f"{m.get('wins', 0)}-{m.get('losses', 0)}" if "wins" in m else "?"
                print(f"    {idx}. {m.get('name', '')} ({m.get('team', '')}) [{rec}] id={m.get('id', '')}")
            if len(matches) > 20:
                print(f"    ... and {len(matches) - 20} more")
            print()
            print("Enter number to select, or another search string:")
            try:
                choice = input("> ").strip()
            except EOFError:
                raise SystemExit(1)
            if not choice:
                continue
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(matches):
                    m = matches[idx - 1]
                    entry = {
                        "wrestler_id": m.get("id", ""),
                        "name": m.get("name", ""),
                        "team": m.get("team", ""),
                    }
                    lookup[_override_key(name, team)] = entry
                    save_boylecomp_lookup(lookup)
                    update_boylecomp_file(name, team, m.get("name", ""), m.get("team", ""))
                    return m
            test_str = choice
            matches = search_wrestlers_by_string(all_wrestlers, test_str)
            if not matches:
                print(f"  No matches for '{test_str}'.")
                break


def update_boylecomp_file(old_name: str, old_team: str, new_name: str, new_team: str) -> None:
    """Update boylecomp.txt so future parses find the wrestler by corrected name/team."""
    if not BOYLECOMP_PATH.exists():
        return
    text = BOYLECOMP_PATH.read_text(encoding="utf-8")
    # Use actual newline from file (handles \n and \r\n)
    nl = "\r\n" if "\r\n" in text else "\n"
    old_pair = f"{old_name}{nl}{old_team}"
    new_pair = f"{new_name}{nl}{new_team}"
    if old_pair in text and old_pair != new_pair:
        text = text.replace(old_pair, new_pair, 1)
        BOYLECOMP_PATH.write_text(text, encoding="utf-8")
        print(f"  Updated boylecomp.txt: {old_name} ({old_team}) -> {new_name} ({new_team})")


def load_career_lookup(data_root: Path) -> Dict[str, str]:
    """season_wrestler_id -> career_id."""
    base = data_root / "data" / "careers"
    if not base.exists():
        return {}
    lookup: Dict[str, str] = {}
    for career_file in base.glob("career_*.json"):
        try:
            with career_file.open("r", encoding="utf-8") as f:
                career_data = json.load(f)
            career_id = career_data.get("career_id")
            seasons = career_data.get("seasons", {})
            if career_id and isinstance(seasons, dict):
                for sid in seasons.values():
                    if sid:
                        lookup[str(sid)] = career_id
        except Exception:
            continue
    return lookup


def load_career(career_id: str, data_root: Path) -> Optional[Dict]:
    """Load career JSON (seasons: { year -> season_wrestler_id })."""
    path = data_root / "data" / "careers" / f"{career_id}.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_last_year_accomplishments(season: int, gender: str, data_root: Path) -> Dict[str, Dict]:
    """season_wrestler_id -> { regional_place, state_place } for season-1."""
    path = data_root / "data" / "season_accomplishments" / gender / str(season - 1) / "season_accomplishments.json"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    by_id: Dict[str, Dict] = {}
    for w in data.get("wrestlers", []):
        wid = w.get("season_wrestler_id")
        rp = w.get("regional_place")
        sp = w.get("state_place")
        if rp is None and sp is None:
            continue
        if wid:
            by_id[wid] = {"regional_place": rp, "state_place": sp}
    return by_id


def get_last_year_acc(
    wrestler_id: str,
    last_year_by_id: Dict[str, Dict],
    career_lookup: Dict[str, str],
    data_root: Path,
    last_year: int,
) -> Dict:
    """Resolve last-year accomplishments via career linkage."""
    acc = last_year_by_id.get(wrestler_id)
    if acc is None and career_lookup:
        career_id = career_lookup.get(wrestler_id)
        if career_id:
            career = load_career(career_id, data_root)
            if career:
                last_year_id = career.get("seasons", {}).get(str(last_year))
                if last_year_id:
                    acc = last_year_by_id.get(last_year_id)
    return acc or {}


def format_accomplishments(acc: Dict) -> str:
    """Format as (Reg: 1, State: 3) or empty string if none."""
    rp = acc.get("regional_place")
    sp = acc.get("state_place")
    if rp is None and sp is None:
        return ""
    parts = []
    if rp is not None:
        parts.append(f"Reg: {rp}")
    if sp is not None:
        parts.append(f"State: {sp}")
    if not parts:
        return ""
    return f" ({', '.join(parts)})"


def load_weight_class_data(season: int, gender: str, data_root: Path) -> Dict[str, Dict]:
    """Load all weight_class_*.json. Returns weight_class -> { wrestlers, matches }."""
    path = data_root / "mt" / "rankings_data" / f"hs_ky_{gender}" / str(season)
    if not path.exists():
        return {}
    out = {}
    for wc_file in sorted(path.glob("weight_class_*.json")):
        wc = wc_file.stem.replace("weight_class_", "")
        with wc_file.open("r", encoding="utf-8") as f:
            out[wc] = json.load(f)
    return out


def build_all_wrestlers_with_records(weight_data: Dict[str, Dict]) -> Dict[str, Dict]:
    """Build id -> { name, team, wins, losses, ... } from weight class data."""
    lookup = {}
    for data in weight_data.values():
        for wid, w in data.get("wrestlers", {}).items():
            if wid not in lookup:
                lookup[wid] = {
                    "id": wid,
                    "name": (w.get("name") or "").strip(),
                    "team": (w.get("team") or "").strip(),
                    "wins": w.get("wins", 0),
                    "losses": w.get("losses", 0),
                }
    return lookup


def _skip_match(match: Dict) -> bool:
    r = str(match.get("result", "") or "").lower()
    if "nc" in r or "no contest" in r or "mff" in r or "medical forfeit" in r or "inj" in r:
        return True
    return False


def build_pair_wins_and_opponents(weight_data: Dict[str, Dict]) -> Tuple[Dict, Dict]:
    """
    pair_wins[(id1,id2)] = (wins_by_first, wins_by_second)
    opponents[id] = set of opponent ids
    """
    opponents = defaultdict(set)
    pair_wins = defaultdict(lambda: (0, 0))

    for data in weight_data.values():
        for match in data.get("matches", []):
            if _skip_match(match):
                continue
            w1 = str(match.get("wrestler1_id") or "")
            w2 = str(match.get("wrestler2_id") or "")
            winner = str(match.get("winner_id") or "")
            if not w1 or not w2 or not winner or w1 == "-1" or w2 == "-1" or "OUTSTATE" in w1 or "OUTSTATE" in w2:
                continue
            opponents[w1].add(w2)
            opponents[w2].add(w1)
            pair = tuple(sorted([w1, w2]))
            a, b = pair[0], pair[1]
            wa, wb = pair_wins[pair]
            if winner == a:
                pair_wins[pair] = (wa + 1, wb)
            else:
                pair_wins[pair] = (wa, wb + 1)

    return dict(pair_wins), dict(opponents)


def _wins(pair_wins: Dict, wid: str, opp_id: str) -> int:
    p = tuple(sorted([wid, opp_id]))
    a, b = pair_wins.get(p, (0, 0))
    return a if wid == p[0] else b


def _losses(pair_wins: Dict, wid: str, opp_id: str) -> int:
    p = tuple(sorted([wid, opp_id]))
    a, b = pair_wins.get(p, (0, 0))
    return b if wid == p[0] else a


def run() -> None:
    parser = argparse.ArgumentParser(description="Boyle comp H2H and common-opponent report")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    data_root = args.data_dir

    weight_data = load_weight_class_data(args.season, "boys", data_root)
    if not weight_data:
        print(f"No weight class data for season {args.season} (boys).")
        return

    all_wrestlers = build_all_wrestlers_with_records(weight_data)
    pair_wins, opponents = build_pair_wins_and_opponents(weight_data)
    lookup = load_boylecomp_lookup()

    last_year = args.season - 1
    last_year_by_id = load_last_year_accomplishments(args.season, "boys", data_root)
    career_lookup = load_career_lookup(data_root)

    def acc_str(wid: str) -> str:
        acc = get_last_year_acc(wid, last_year_by_id, career_lookup, data_root, last_year)
        return format_accomplishments(acc)

    sections = parse_boylecomp(BOYLECOMP_PATH)
    if not sections:
        print(f"Could not parse {BOYLECOMP_PATH}")
        return

    for weight, boyle_name, opponent_list in sections:
        # Resolve Boyle wrestler
        boyle_w = find_wrestler(all_wrestlers, boyle_name, BOYLE_TEAM, lookup)
        if not boyle_w:
            boyle_w = interactive_resolve(boyle_name, BOYLE_TEAM, all_wrestlers, lookup)
        boyle_id = boyle_w.get("id", "")
        boyle_rec = f"{boyle_w.get('wins', 0)}-{boyle_w.get('losses', 0)}"
        boyle_acc = acc_str(boyle_id)
        boyle_display = f"{boyle_rec}{boyle_acc}"

        print(f"\n{weight}")
        print(f"{boyle_w.get('name', boyle_name)} {boyle_display}")
        print()

        h2h_wins: List[Tuple[str, str, str, str]] = []  # (name, team, record+acc, result)
        co_wins: List[Tuple[str, str, str, str, str]] = []  # (name, team, record+acc, co_name, co_team)
        neither: List[Tuple[str, str, str]] = []  # (name, team, record+acc)

        for opp_name, opp_school in opponent_list:
            opp_w = find_wrestler(all_wrestlers, opp_name, opp_school, lookup)
            if not opp_w:
                opp_w = interactive_resolve(opp_name, opp_school, all_wrestlers, lookup)
            opp_id = opp_w.get("id", "")
            opp_rec = f"{opp_w.get('wins', 0)}-{opp_w.get('losses', 0)}"
            opp_acc = acc_str(opp_id)
            opp_display = f"{opp_rec}{opp_acc}"
            entry = (opp_w.get("name", opp_name), opp_w.get("team", opp_school), opp_display)

            # H2H: Boyle beat opponent
            pw = pair_wins.get(tuple(sorted([boyle_id, opp_id])), (0, 0))
            boyle_wins_opp = _wins(pair_wins, boyle_id, opp_id)
            opp_wins_boyle = _losses(pair_wins, boyle_id, opp_id)

            if boyle_wins_opp > 0:
                # Get a sample result from matches
                result_str = ""
                for data in weight_data.values():
                    for m in data.get("matches", []):
                        w1 = str(m.get("wrestler1_id", ""))
                        w2 = str(m.get("wrestler2_id", ""))
                        winner = str(m.get("winner_id", ""))
                        if {w1, w2} == {boyle_id, opp_id} and winner == boyle_id:
                            result_str = (m.get("result") or "").strip()
                            break
                    if result_str:
                        break
                h2h_wins.append((*entry, result_str or "W"))
            else:
                # Common opponent: Boyle beat X, opponent lost to X
                common = opponents.get(boyle_id, set()) & opponents.get(opp_id, set())
                co_info = None
                for co_id in common:
                    if _wins(pair_wins, boyle_id, co_id) > 0 and _losses(pair_wins, opp_id, co_id) > 0:
                        co_w = all_wrestlers.get(co_id, {})
                        co_info = (co_w.get("name", "?"), co_w.get("team", "?"))
                        break
                if co_info:
                    co_wins.append((*entry, co_info[0], co_info[1]))
                else:
                    neither.append(entry)

        print("Head to Head")
        for name, team, rec, res in h2h_wins:
            print(f"  {name} ({team}) {rec}  {res}")
        if not h2h_wins:
            print("  (none)")

        print()
        print("Common Opponents")
        for name, team, rec, co_name, co_team in co_wins:
            print(f"  {name} ({team}) {rec} <--- via {co_name} ({co_team})")
        if not co_wins:
            print("  (none)")

        print()
        print("No H2H or Common Opponent:")
        for name, team, rec in neither:
            print(f"  {name} ({team}) {rec}")
        if not neither:
            print("  (none)")

    print()


if __name__ == "__main__":
    run()
