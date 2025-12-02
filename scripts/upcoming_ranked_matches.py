import base64
import csv
import io
import json
import webbrowser
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEAMS_FILE = PROJECT_ROOT / "data" / "team_lists" / "2026" / "ncaa_d1_teams.json"
RANKINGS_DIR = PROJECT_ROOT / "mt" / "rankings_data" / "2026"
SCHEDULE_FILE = PROJECT_ROOT / "mt" / "rankings_data" / "2026" / "dual_schedule.json"
REPORT_HTML_STARTERS = PROJECT_ROOT / "mt" / "graphics" / "upcoming_ranked_report_starters.html"
REPORT_HTML_ALL = PROJECT_ROOT / "mt" / "graphics" / "upcoming_ranked_report_all.html"


@dataclass
class Team:
    name: str
    state: str
    abbreviation: str


@dataclass
class Dual:
    date: date
    date_code: str  # original MMDDYY string like "113025"
    team1: str
    team2: str


@dataclass
class RankedWrestler:
    weight_class: int
    rank: int  # rank used in report (starter-only or original)
    name: str
    team: str
    wrestler_id: str


def load_teams() -> List[Team]:
    with TEAMS_FILE.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    teams: List[Team] = []
    for t in raw:
        teams.append(
            Team(
                name=t["name"],
                state=t.get("state", ""),
                abbreviation=t.get("abbreviation", ""),
            )
        )
    return teams


def search_teams(teams: List[Team], query: str) -> List[Team]:
    q = query.lower()
    results = []
    for t in teams:
        haystack = f"{t.name} {t.abbreviation} {t.state}".lower()
        if q in haystack:
            results.append(t)
    return results


def prompt_for_team(teams: List[Team], label: str) -> Team:
    while True:
        query = input(f"Enter search string for {label} (e.g. 'virginia'): ").strip()
        if not query:
            print("Please enter a non-empty search string.")
            continue
        matches = search_teams(teams, query)
        if not matches:
            print("No teams found. Try a different search.")
            continue

        print(f"\nMatches for '{query}':")
        for idx, t in enumerate(matches, start=1):
            extra = f" ({t.abbreviation}, {t.state})" if t.abbreviation or t.state else ""
            print(f"  {idx}. {t.name}{extra}")

        choice_str = input(
            f"Choose {label} by number (1-{len(matches)}), or press Enter to search again: "
        ).strip()
        if not choice_str:
            continue
        try:
            choice = int(choice_str)
        except ValueError:
            print("Invalid choice. Please enter a number.")
            continue
        if 1 <= choice <= len(matches):
            return matches[choice - 1]
        print("Choice out of range. Try again.")


def normalize_team_key(name: str) -> str:
    """
    Normalize a team name for matching: lowercase, alphanumeric plus spaces,
    collapse multiple spaces.
    """
    s = name.lower()
    cleaned_chars = []
    for ch in s:
        if ch.isalnum() or ch.isspace():
            cleaned_chars.append(ch)
    cleaned = "".join(cleaned_chars)
    return " ".join(cleaned.split())


def clean_csv_team_name(label: str) -> str:
    """
    From CSV entries like '#6 Iowa State', strip the ranking and '#',
    leaving just the team name, e.g. 'Iowa State'.
    """
    s = label.strip()
    if not s:
        return s
    if s.startswith("#"):
        s = s[1:].strip()
        parts = s.split(maxsplit=1)
        if parts and parts[0].lstrip("0123456789") == "" and len(parts) > 1:
            # First token is all digits (rank); drop it.
            s = parts[1].strip()
    return s


def parse_flexible_date(item: dict) -> Optional[Tuple[date, str]]:
    """
    Try to parse a date from an imported dual item.

    Supported inputs:
    - date_code: MMDDYY (preferred, uses parse_mmddyy)
    - date: ISO 'YYYY-MM-DD'
    - date: 'MM/DD/YYYY' or 'M/D/YY' (slashes or dashes allowed)

    Returns (date_obj, date_code_str) or None if parsing fails.
    """
    # Prefer explicit date_code if present
    code_val = item.get("date_code")
    if isinstance(code_val, str) and code_val.strip():
        code = code_val.strip()
        try:
            d = parse_mmddyy(code)
            return d, code
        except Exception:
            pass

    raw_date = item.get("date")
    if raw_date is None:
        return None
    s = str(raw_date).strip()
    if not s:
        return None

    # Treat bare 6-digit strings as MMDDYY (common in imported data).
    if len(s) == 6 and s.isdigit():
        try:
            d = parse_mmddyy(s)
            return d, s
        except Exception:
            # fall through to other parsing strategies
            pass

    # Try ISO format first
    try:
        d = date.fromisoformat(s)
    except Exception:
        # Fallback: MM/DD/YYYY or similar, allowing '-' instead of '/'
        try:
            parts = s.replace("-", "/").split("/")
            if len(parts) != 3:
                return None
            month = int(parts[0])
            day = int(parts[1])
            year = int(parts[2])
            if year < 100:
                year += 2000
            d = date(year, month, day)
        except Exception:
            return None

    code = f"{d.month:02}{d.day:02}{d.year % 100:02}"
    return d, code


def resolve_team_name(
    raw_name: str,
    teams: List[Team],
    alias_cache: Dict[str, Optional[str]],
) -> Optional[str]:
    """
    Map an imported team string to a canonical D1 team name, interactively if needed.

    - Uses a cache so repeated names don't prompt multiple times.
    - Attempts exact normalized match first.
    - Then offers suggestions based on simple substring search.
    - User can search manually or mark a name as non-D1 (ignored).
    """
    key = normalize_team_key(raw_name)
    if not key:
        return None

    if key in alias_cache:
        return alias_cache[key]

    # Exact normalized match on known team names
    for t in teams:
        if normalize_team_key(t.name) == key:
            alias_cache[key] = t.name
            return t.name

    # Build candidate suggestions using simple substring searches
    candidates: List[Team] = []
    seen: Dict[str, bool] = {}

    queries = [raw_name]
    parts = raw_name.split()
    if parts:
        queries.append(parts[0])

    for q in queries:
        q = q.strip()
        if not q:
            continue
        for t in search_teams(teams, q):
            if t.name not in seen:
                candidates.append(t)
                seen[t.name] = True

    while True:
        print(f"\nUnrecognized team name from import: '{raw_name}'")
        if candidates:
            print("Possible matches:")
            for idx, t in enumerate(candidates, start=1):
                extra = f" ({t.abbreviation}, {t.state})" if t.abbreviation or t.state else ""
                print(f"  {idx}. {t.name}{extra}")
        else:
            print("No obvious matches found among D1 teams.")

        print("Options:")
        if candidates:
            print("  [number] - choose a matching team from the list above")
        print("  s - search D1 teams manually")
        print("  i - treat as non-D1 and ignore all duals with this team")

        choice = input("Enter choice (or press Enter to search manually): ").strip().lower()

        if choice == "i":
            alias_cache[key] = None
            return None

        if choice in ("", "s"):
            # Manual search flow using the existing prompt
            t = prompt_for_team(teams, f"match for '{raw_name}'")
            alias_cache[key] = t.name
            return t.name

        try:
            idx = int(choice)
        except ValueError:
            print("Invalid choice. Try again.")
            continue

        if 1 <= idx <= len(candidates):
            t = candidates[idx - 1]
            alias_cache[key] = t.name
            return t.name

        print("Choice out of range. Try again.")


def parse_mmddyy(code: str) -> date:
    """
    Parse MMDDYY into a date, assuming 2000-based year.
    Example: '113025' -> 2025-11-30.
    """
    if len(code) != 6 or not code.isdigit():
        raise ValueError("Date must be 6 digits in MMDDYY format.")
    month = int(code[0:2])
    day = int(code[2:4])
    year_suffix = int(code[4:6])
    year = 2000 + year_suffix
    return date(year, month, day)


def parse_mmdd_current_season(s: str, today: Optional[date] = None) -> Tuple[date, str]:
    """
    Parse a date like '11/30' or '1/2' and infer the year based on the
    current date, assuming a winter season that can span two calendar years.

    Heuristic:
      - If today is in the back half of the year (Jul–Dec) and the month is
        in the front half (Jan–Jun), treat the date as next year.
      - If today is in the front half (Jan–Jun) and the month is in the
        back half (Jul–Dec), treat the date as previous year.
      - Otherwise, use today's year.
    """
    if today is None:
        today = date.today()

    parts = s.strip().split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid MM/DD date: {s}")
    month = int(parts[0])
    day = int(parts[1])

    year = today.year
    if today.month >= 7 and month < 7:
        year = today.year + 1
    elif today.month < 7 and month > 6:
        year = today.year - 1

    d = date(year, month, day)
    code = f"{month:02}{day:02}{year % 100:02}"
    return d, code


def format_iso(d: date) -> str:
    return d.isoformat()


def load_schedule() -> List[Dual]:
    if not SCHEDULE_FILE.exists():
        return []
    with SCHEDULE_FILE.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    duals: List[Dual] = []
    for item in raw:
        try:
            d = date.fromisoformat(item["date"])
        except Exception:
            # Fallback to parse from date_code if available
            if "date_code" in item:
                d = parse_mmddyy(item["date_code"])
            else:
                continue
        duals.append(
            Dual(
                date=d,
                date_code=item.get("date_code", ""),
                team1=item["team1"],
                team2=item["team2"],
            )
        )
    return duals


def save_schedule(duals: List[Dual]) -> None:
    SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
    serializable = []
    for d in duals:
        serializable.append(
            {
                "date": format_iso(d.date),
                "date_code": d.date_code,
                "team1": d.team1,
                "team2": d.team2,
            }
        )
    with SCHEDULE_FILE.open("w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2)


def interactive_add_duals() -> None:
    print("\n=== Add Upcoming Duals ===\n")
    teams = load_teams()
    duals = load_schedule()

    while True:
        team1 = prompt_for_team(teams, "team 1")
        team2 = prompt_for_team(teams, "team 2")

        while True:
            date_code = input(
                "Enter dual date in MMDDYY format (e.g. 113025 for Nov 30, 2025): "
            ).strip()
            try:
                d = parse_mmddyy(date_code)
                break
            except Exception as e:
                print(f"Invalid date: {e}")

        print(
            f"\nAdding dual: {team1.name} vs {team2.name} on {d.strftime('%Y-%m-%d')} (code {date_code})"
        )
        confirm = input("Confirm? [Y/n]: ").strip().lower()
        if confirm in ("", "y", "yes"):
            duals.append(Dual(date=d, date_code=date_code, team1=team1.name, team2=team2.name))
            save_schedule(duals)
            print("Dual saved.\n")
        else:
            print("Dual discarded.\n")

        again = input("Add another dual? [Y/n]: ").strip().lower()
        if again not in ("", "y", "yes"):
            break


def import_duals_from_json() -> None:
    """
    Import duals from a JSON file, resolving team names against the D1 list.

    Expected JSON formats:
    - A list of duals: [{...}, {...}, ...]
    - Or an object with a 'duals' key: {"duals": [{...}, ...]}

    Each dual object should have:
      - team1: string
      - team2: string
      - date or date_code:
          * date_code: MMDDYY (e.g. 113025)
          * OR date: 'YYYY-MM-DD' or 'MM/DD/YYYY' (slashes or dashes)
    """
    print("\n=== Import Duals from JSON ===\n")
    path_str = input(
        "Enter path to JSON file (absolute or relative to project root): "
    ).strip()
    if not path_str:
        print("No path provided, aborting import.")
        return

    path = Path(path_str)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if not path.exists():
        print(f"File not found: {path}")
        return

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Failed to read JSON: {e}")
        return

    if isinstance(data, dict) and "duals" in data:
        items = data["duals"]
    elif isinstance(data, list):
        items = data
    else:
        print("JSON must be a list of duals or an object with a 'duals' array.")
        return

    teams = load_teams()
    alias_cache: Dict[str, Optional[str]] = {}
    existing_duals = load_schedule()

    def make_key(d: date, team1: str, team2: str) -> Tuple[date, str, str]:
        a, b = sorted([team1, team2])
        return d, a, b

    existing_keys = {make_key(d.date, d.team1, d.team2) for d in existing_duals}

    imported_count = 0
    skipped_missing_team = 0
    skipped_invalid_date = 0
    skipped_duplicates = 0

    for item in items:
        if not isinstance(item, dict):
            continue

        parsed = parse_flexible_date(item)
        if parsed is None:
            skipped_invalid_date += 1
            continue
        d, date_code = parsed

        raw_team1 = str(item.get("team1", "")).strip()
        raw_team2 = str(item.get("team2", "")).strip()
        if not raw_team1 or not raw_team2:
            skipped_missing_team += 1
            continue

        team1 = resolve_team_name(raw_team1, teams, alias_cache)
        team2 = resolve_team_name(raw_team2, teams, alias_cache)
        if not team1 or not team2:
            skipped_missing_team += 1
            continue

        key = make_key(d, team1, team2)
        if key in existing_keys:
            skipped_duplicates += 1
            continue

        existing_duals.append(Dual(date=d, date_code=date_code, team1=team1, team2=team2))
        existing_keys.add(key)
        imported_count += 1

    if imported_count:
        save_schedule(existing_duals)

    print(
        f"\nImport complete. Added {imported_count} dual(s). "
        f"Skipped {skipped_duplicates} duplicate(s), "
        f"{skipped_missing_team} with missing/non-D1 team(s), "
        f"{skipped_invalid_date} with invalid date."
    )


def import_duals_from_csv() -> None:
    """
    Import duals from a CSV file with columns like:

      Date,School,Opponent,...

    Example rows:
      11/30,#6 Iowa State,#2 Iowa,

    Behavior:
      - Date is parsed as MM/DD, year inferred for the current season.
      - Leading rank markers like '#6 ' are stripped from team names.
      - Team names are then resolved against the D1 list (same as JSON import).
    """
    print("\n=== Import Duals from CSV ===\n")
    path_str = input(
        "Enter path to CSV file (absolute or relative to project root): "
    ).strip()
    if not path_str:
        print("No path provided, aborting CSV import.")
        return

    path = Path(path_str)
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if not path.exists():
        print(f"File not found: {path}")
        return

    try:
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)
    except Exception as e:
        print(f"Failed to read CSV: {e}")
        return

    if not rows:
        print("CSV file is empty.")
        return

    header = rows[0]
    # Expect at least Date, School, Opponent
    if len(header) < 3:
        print("CSV must have at least three columns: Date, School, Opponent")
        return

    teams = load_teams()
    alias_cache: Dict[str, Optional[str]] = {}
    existing_duals = load_schedule()

    def make_key(d: date, team1: str, team2: str) -> Tuple[date, str, str]:
        a, b = sorted([team1, team2])
        return d, a, b

    existing_keys = {make_key(d.date, d.team1, d.team2) for d in existing_duals}

    imported_count = 0
    skipped_missing_team = 0
    skipped_invalid_date = 0
    skipped_duplicates = 0

    for row in rows[1:]:
        if len(row) < 3:
            continue

        raw_date = row[0].strip()
        raw_team1 = row[1].strip()
        raw_team2 = row[2].strip()

        if not raw_date:
            skipped_invalid_date += 1
            continue

        try:
            d, date_code = parse_mmdd_current_season(raw_date)
        except Exception:
            skipped_invalid_date += 1
            continue

        if not raw_team1 or not raw_team2:
            skipped_missing_team += 1
            continue

        cleaned_team1 = clean_csv_team_name(raw_team1)
        cleaned_team2 = clean_csv_team_name(raw_team2)

        team1 = resolve_team_name(cleaned_team1, teams, alias_cache)
        team2 = resolve_team_name(cleaned_team2, teams, alias_cache)
        if not team1 or not team2:
            skipped_missing_team += 1
            continue

        key = make_key(d, team1, team2)
        if key in existing_keys:
            skipped_duplicates += 1
            continue

        existing_duals.append(Dual(date=d, date_code=date_code, team1=team1, team2=team2))
        existing_keys.add(key)
        imported_count += 1

    if imported_count:
        save_schedule(existing_duals)

    print(
        f"\nCSV import complete. Added {imported_count} dual(s). "
        f"Skipped {skipped_duplicates} duplicate(s), "
        f"{skipped_missing_team} with missing/non-D1 team(s), "
        f"{skipped_invalid_date} with invalid date."
    )


def load_rankings_starters(
    max_rank: int,
) -> Dict[int, Dict[str, List[RankedWrestler]]]:
    """
    Load all rankings_*.json files and return starter-only rankings:

    {weight_class: {team_name: [RankedWrestler, ...]}}

    Logic:
    - Keep only entries where is_starter is true.
    - Sort starters by their original rank.
    - Re-number ranks consecutively among starters (1, 2, 3, ...).
    - Apply the max_rank cutoff to the new starter-only rank.
    """
    result: Dict[int, Dict[str, List[RankedWrestler]]] = {}

    if not RANKINGS_DIR.exists():
        print(f"Rankings directory not found: {RANKINGS_DIR}")
        return result

    for path in sorted(RANKINGS_DIR.glob("rankings_*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        try:
            weight_class = int(data["weight_class"])
            rankings = data["rankings"]
        except Exception:
            continue

        by_team = result.setdefault(weight_class, {})
        # Filter to starters only, then re-number by original rank.
        starters = []
        for r in rankings:
            if not r.get("is_starter", False):
                continue
            try:
                orig_rank = int(r["rank"])
            except Exception:
                continue
            starters.append((orig_rank, r))

        # Sort by original rank and assign new starter-only rank.
        starters.sort(key=lambda x: x[0])
        for new_rank, (_, r) in enumerate(starters, start=1):
            if new_rank > max_rank:
                break
            team_name = r["team"]
            wrestler = RankedWrestler(
                weight_class=weight_class,
                rank=new_rank,
                name=r["name"],
                team=team_name,
                wrestler_id=str(r.get("wrestler_id", "")),
            )
            by_team.setdefault(team_name, []).append(wrestler)

    return result


def load_rankings_all(
    max_rank: int,
) -> Dict[int, Dict[str, List[RankedWrestler]]]:
    """
    Load all rankings_*.json files and return rankings including all wrestlers.

    {weight_class: {team_name: [RankedWrestler, ...]}}

    Logic:
    - Do not filter on is_starter.
    - Use the original rank values from the JSON.
    - Apply the max_rank cutoff directly to the original rank.
    """
    result: Dict[int, Dict[str, List[RankedWrestler]]] = {}

    if not RANKINGS_DIR.exists():
        print(f"Rankings directory not found: {RANKINGS_DIR}")
        return result

    for path in sorted(RANKINGS_DIR.glob("rankings_*.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        try:
            weight_class = int(data["weight_class"])
            rankings = data["rankings"]
        except Exception:
            continue

        by_team = result.setdefault(weight_class, {})
        for r in rankings:
            try:
                rank = int(r["rank"])
            except Exception:
                continue
            if rank > max_rank:
                continue

            team_name = r["team"]
            wrestler = RankedWrestler(
                weight_class=weight_class,
                rank=rank,
                name=r["name"],
                team=team_name,
                wrestler_id=str(r.get("wrestler_id", "")),
            )
            by_team.setdefault(team_name, []).append(wrestler)

    return result


def build_weekly_histogram_data(
    matchups: List[Tuple[Dual, RankedWrestler, RankedWrestler]]
) -> Tuple[List[date], List[int], List[str]]:
    """
    Aggregate matchup counts by calendar week (Mon-Sun).

    Returns:
      week_starts: list of Monday dates
      counts:      list of counts per week
      labels:      list of 'MM/DD-<newline>MM/DD' strings for axis labels
    """
    if not matchups:
        return [], [], []

    buckets: Dict[date, int] = {}
    for dual, _, _ in matchups:
        d = dual.date
        week_start = d - timedelta(days=d.weekday())  # Monday
        buckets[week_start] = buckets.get(week_start, 0) + 1

    week_starts = sorted(buckets.keys())
    counts = [buckets[w] for w in week_starts]
    labels = []
    for w in week_starts:
        week_end = w + timedelta(days=6)
        label = f"{w.month:02}/{w.day:02}-\n{week_end.month:02}/{week_end.day:02}"
        labels.append(label)

    return week_starts, counts, labels


def generate_html_report(
    output_path: Path,
    today: date,
    end_date: date,
    max_rank: int,
    label: str,
    upcoming_lines: List[str],
    all_matchups: List[Tuple[Dual, RankedWrestler, RankedWrestler]],
) -> None:
    """
    Generate an HTML report with:
      - Weekly histogram over the full season (based on current ranks)
      - Text list of upcoming matchups in the requested window
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Try to build the histogram image using matplotlib, but fall back gracefully.
    img_data_uri = None
    week_starts, counts, labels = build_weekly_histogram_data(all_matchups)

    if week_starts:
        try:
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(10, 3))
            x = list(range(len(week_starts)))
            ax.bar(x, counts, color="orange", edgecolor="black")
            ax.set_xticks(x)
            ax.set_xticklabels(labels, fontsize=8)
            ax.set_ylabel("# of Matches")
            ax.set_title("Ranked Matchups per Week")
            ax.grid(axis="y", linestyle="--", alpha=0.4)
            fig.tight_layout()

            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=150)
            plt.close(fig)
            buf.seek(0)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            img_data_uri = f"data:image/png;base64,{b64}"
        except Exception:
            img_data_uri = None

    html_lines: List[str] = []
    html_lines.append("<!DOCTYPE html>")
    html_lines.append("<html lang='en'>")
    html_lines.append("<head>")
    html_lines.append("<meta charset='utf-8' />")
    html_lines.append("<title>Upcoming Ranked Matchups</title>")
    html_lines.append(
        "<style>"
        "body { font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif; padding: 16px; }"
        "h1, h2 { margin: 0.5em 0; }"
        ".summary { margin-bottom: 1em; }"
        ".histogram { margin: 1em 0 2em; }"
        "pre { background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; }"
        "</style>"
    )
    html_lines.append("</head>")
    html_lines.append("<body>")

    html_lines.append("<h1>Upcoming Ranked Matchups</h1>")
    html_lines.append(
        f"<div class='summary'>Window: {today.isoformat()} to {end_date.isoformat()} "
        f"({label}, top {max_rank})</div>"
    )

    if img_data_uri:
        html_lines.append("<div class='histogram'>")
        html_lines.append(
            f"<img src='{img_data_uri}' alt='Season histogram' style='max-width: 100%; height: auto;' />"
        )
        html_lines.append("</div>")
    else:
        html_lines.append(
            "<p><em>Histogram could not be generated (matplotlib not available or failed).</em></p>"
        )

    html_lines.append("<h2>Upcoming Matchups</h2>")
    if upcoming_lines:
        html_lines.append("<pre>")
        for line in upcoming_lines:
            html_lines.append(line)
        html_lines.append("</pre>")
    else:
        html_lines.append("<p>No upcoming matchups in the requested window.</p>")

    html_lines.append("</body></html>")

    output_path.write_text("\n".join(html_lines), encoding="utf-8")


def find_ranked_matchups_for_dual(
    dual: Dual,
    rankings_by_weight_team: Dict[int, Dict[str, List[RankedWrestler]]],
    weight_filter: Optional[int] = None,
) -> List[Tuple[Dual, RankedWrestler, RankedWrestler]]:
    matchups: List[Tuple[Dual, RankedWrestler, RankedWrestler]] = []

    for weight_class, by_team in rankings_by_weight_team.items():
        if weight_filter is not None and weight_class != weight_filter:
            continue
        team1_wrestlers = by_team.get(dual.team1, [])
        team2_wrestlers = by_team.get(dual.team2, [])
        if not team1_wrestlers or not team2_wrestlers:
            continue

        # For now, produce all combinations of ranked wrestlers between the two teams
        for w1 in team1_wrestlers:
            for w2 in team2_wrestlers:
                matchups.append((dual, w1, w2))

    return matchups


def list_upcoming_ranked_matchups(days_ahead: Optional[int] = None) -> None:
    if days_ahead is None:
        days_str = input("How many days ahead? [7]: ").strip()
        if days_str:
            try:
                days_ahead = int(days_str)
            except ValueError:
                print("Invalid number, defaulting to 7 days.")
                days_ahead = 7
        else:
            days_ahead = 7

    today = date.today()
    end_date = today + timedelta(days=days_ahead)

    rank_cutoff_str = input("Show matchups up to what rank? [33]: ").strip()
    if rank_cutoff_str:
        try:
            max_rank = int(rank_cutoff_str)
        except ValueError:
            print("Invalid rank cutoff, defaulting to 33.")
            max_rank = 33
    else:
        max_rank = 33

    # Optional weight-class filter
    weight_filter: Optional[int] = None
    wc_str = input(
        "Filter by weight class (e.g. 125), or press Enter for all weights: "
    ).strip()
    if wc_str:
        try:
            weight_filter = int(wc_str)
        except ValueError:
            print("Invalid weight; showing all weights.\n")
            weight_filter = None

    duals = load_schedule()
    if not duals:
        print("No duals scheduled yet. Use the 'add duals' option first.")
        return

    # Helper to build and sort matchups for a given rankings map.
    def build_matchups(
        rankings_by_weight_team: Dict[int, Dict[str, List[RankedWrestler]]]
    ) -> Tuple[
        List[Tuple[Dual, RankedWrestler, RankedWrestler]],
        List[Tuple[Dual, RankedWrestler, RankedWrestler]],
    ]:
        window_matchups: List[Tuple[Dual, RankedWrestler, RankedWrestler]] = []
        season_matchups: List[Tuple[Dual, RankedWrestler, RankedWrestler]] = []

        for dual in duals:
            m = find_ranked_matchups_for_dual(
                dual, rankings_by_weight_team, weight_filter=weight_filter
            )
            season_matchups.extend(m)
            if today <= dual.date <= end_date:
                window_matchups.extend(m)

        # Sort window matchups by average rank (best first), then date, then weight.
        def sort_key(item: Tuple[Dual, RankedWrestler, RankedWrestler]):
            dual, w1, w2 = item
            avg_rank = (w1.rank + w2.rank) / 2.0
            return (avg_rank, dual.date, w1.weight_class)

        window_matchups.sort(key=sort_key)
        return window_matchups, season_matchups

    # --- Starters-only report (console + HTML) ---
    print(
        f"\n=== Upcoming Ranked Matchups (starters only, top {max_rank}) "
        f"from {today.isoformat()} to {end_date.isoformat()} ===\n"
    )

    starter_rankings = load_rankings_starters(max_rank=max_rank)
    if not starter_rankings:
        print("No rankings data loaded for starters-only view. Check rankings JSON files.")
        return

    starter_window, starter_season = build_matchups(starter_rankings)
    if not starter_window:
        print("No potential ranked matchups in the selected window (starters only).")
    else:
        starter_lines: List[str] = []
        starter_simple_lines: List[str] = []
        for dual, w1, w2 in starter_window:
            detailed = (
                f"{dual.date.strftime('%m/%d')} - "
                f"{w1.weight_class:>3} lbs: "
                f"#{w1.rank} {w1.name} ({w1.team}) vs "
                f"#{w2.rank} {w2.name} ({w2.team})"
            )
            simple = (
                f"#{w1.rank} {w1.name} ({w1.team}) vs "
                f"#{w2.rank} {w2.name} ({w2.team})"
            )
            print(detailed)
            starter_lines.append(detailed)
            starter_simple_lines.append(simple)

        print()

        # Re-print the same matchups in a simplified inline format (no date/weight).
        print("Simplified matchup list:\n")
        for line in starter_simple_lines:
            print(line)
        print()

        generate_html_report(
            output_path=REPORT_HTML_STARTERS,
            today=today,
            end_date=end_date,
            max_rank=max_rank,
            label="starters only",
            upcoming_lines=starter_lines,
            all_matchups=starter_season,
        )
        print(f"Starters-only HTML report written to: {REPORT_HTML_STARTERS}")
        try:
            webbrowser.open(REPORT_HTML_STARTERS.as_uri())
        except Exception:
            pass

    # --- All-wrestlers report (HTML only) ---
    all_rankings = load_rankings_all(max_rank=max_rank)
    if not all_rankings:
        print("No rankings data loaded for all-wrestlers view. Check rankings JSON files.")
        return

    all_window, all_season = build_matchups(all_rankings)
    all_lines: List[str] = []
    for dual, w1, w2 in all_window:
        line = (
            f"{dual.date.strftime('%m/%d')} - "
            f"{w1.weight_class:>3} lbs: "
            f"#{w1.rank} {w1.name} ({w1.team}) vs "
            f"#{w2.rank} {w2.name} ({w2.team})"
        )
        all_lines.append(line)

    generate_html_report(
        output_path=REPORT_HTML_ALL,
        today=today,
        end_date=end_date,
        max_rank=max_rank,
        label="all wrestlers",
        upcoming_lines=all_lines,
        all_matchups=all_season,
    )
    print(f"All-wrestlers HTML report written to: {REPORT_HTML_ALL}")


def main() -> None:
    print("WrestleData Upcoming Duals & Ranked Matchups\n")
    print("Choose an option:")
    print("  1. Add upcoming duals")
    print("  2. List upcoming ranked matchups")
    print("  3. Import duals from JSON")
    print("  4. Import duals from CSV")
    print("  0. Exit")

    choice = input("Enter choice: ").strip()
    if choice == "1":
        interactive_add_duals()
    elif choice == "2":
        list_upcoming_ranked_matchups()
    elif choice == "3":
        import_duals_from_json()
    elif choice == "4":
        import_duals_from_csv()
    else:
        print("Exiting.")


if __name__ == "__main__":
    main()


