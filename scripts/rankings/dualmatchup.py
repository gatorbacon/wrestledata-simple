#!/usr/bin/env python3
"""
Interactive dual-meet predictor.

Workflow:
  - Run:  python scripts/rankings/dualmatchup.py  (or via .venv)
  - Script will:
      * Ask for Team #1 name fragment (e.g. "Iowa"), list matches, let you choose.
      * Ask for Team #2 the same way.
      * For NCAA weights 125..285, find each team's highest-ranked wrestler
        in that weight class from rankings_{weight}.json.
      * For each weight, predict a winner based on rank (lower rank wins;
        ranked beats unranked; if both unranked, call it "Even").
      * Look up head-to-head and common-opponent edges from
        relationships_{weight}.json and add short notes.
      * Write an HTML file summarizing the predicted dual.

This is intentionally a simple predictor; you can refine the scoring logic later.
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from load_data import load_team_data


RANKINGS_DIR = Path("mt/rankings_data")

# Standard NCAA weights for D1 duals
WEIGHTS = ["125", "133", "141", "149", "157", "165", "174", "184", "197", "285"]


def search_teams(teams: List[Dict], query: str) -> List[str]:
    """Return sorted list of team_name values containing the query."""
    query_lower = query.lower()
    names = set()
    for team in teams:
        name = team.get("team_name", "Unknown")
        if query_lower in name.lower():
            names.add(name)
    return sorted(names)


def prompt_for_team(teams: List[Dict], label: str) -> str:
    """Interactively prompt for a team by name fragment and return the full name."""
    while True:
        fragment = input(f"Enter name fragment for {label} (e.g. 'Iowa'): ").strip()
        if not fragment:
            print("  Please enter at least one character.\n")
            continue

        matches = search_teams(teams, fragment)
        if not matches:
            print("  No teams found containing that fragment. Try again.\n")
            continue

        print(f"Found {len(matches)} team(s):")
        for idx, name in enumerate(matches, start=1):
            print(f"  {idx:2d}) {name}")

        while True:
            sel = input(
                f"Select {label} by number (1-{len(matches)}), "
                f"or blank to search again: "
            ).strip()
            if not sel:
                print("  Search cancelled, try another fragment.\n")
                break
            try:
                num = int(sel)
                if 1 <= num <= len(matches):
                    chosen = matches[num - 1]
                    print(f"  Selected {label}: {chosen}\n")
                    return chosen
            except ValueError:
                pass
            print("  Invalid selection; please enter a valid number.")


def load_rankings_for_weight(
    season: int, weight: str
) -> List[Dict]:
    """Load rankings_{weight}.json; return list of entries (may be empty)."""
    path = RANKINGS_DIR / str(season) / f"rankings_{weight}.json"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("rankings", [])


def best_wrestler_for_team_at_weight(
    rankings: List[Dict], team_name: str
) -> Optional[Dict]:
    """
    Given rankings for a weight, return the entry with the best (lowest) rank
    for the specified team_name, or None if the team has no ranked wrestler
    at this weight.
    """
    best: Optional[Dict] = None
    best_rank = 10**9
    for e in rankings:
        if e.get("team") != team_name:
            continue
        r = e.get("rank")
        if r is None:
            continue
        try:
            rank_int = int(r)
        except (TypeError, ValueError):
            continue
        if rank_int < best_rank:
            best_rank = rank_int
            best = e
    return best


def load_relationships_for_weight(
    season: int, weight: str
) -> Optional[Dict]:
    """Load relationships_{weight}.json, or None if missing."""
    path = RANKINGS_DIR / str(season) / f"relationships_{weight}.json"
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def head_to_head_summary(
    rel_data: Dict, wid1: str, wid2: str
) -> Tuple[Optional[str], str]:
    """
    Return (winner_wid_or_None, summary_text) for direct head-to-head results
    between wid1 and wid2 using direct_relationships in rel_data.
    """
    pair_key = "_".join(sorted([wid1, wid2]))
    drels = rel_data.get("direct_relationships", {})
    rel = drels.get(pair_key)
    if not rel:
        return None, ""

    w1 = rel["wrestler1_id"]
    w2 = rel["wrestler2_id"]
    wins1 = rel.get("direct_wins_1", 0)
    wins2 = rel.get("direct_wins_2", 0)

    # Map counts to wid1/wid2 perspective
    if wid1 == w1:
        wid1_wins, wid2_wins = wins1, wins2
    else:
        wid1_wins, wid2_wins = wins2, wins1

    if wid1_wins == 0 and wid2_wins == 0:
        return None, ""

    if wid1_wins > wid2_wins:
        winner = wid1
    elif wid2_wins > wid1_wins:
        winner = wid2
    else:
        winner = None

    summary = f"H2H: {wid1_wins}-{wid2_wins}"
    return winner, summary


def common_opp_summary(
    rel_data: Dict, wid1: str, wid2: str
) -> Tuple[Optional[str], str]:
    """
    Return (winner_wid_or_None, summary_text) for common-opponent advantage
    between wid1 and wid2 using common_opponent_relationships.
    """
    pair_key = "_".join(sorted([wid1, wid2]))
    cores = rel_data.get("common_opponent_relationships", {})
    rel = cores.get(pair_key)
    if not rel:
        return None, ""

    w1 = rel["wrestler1_id"]
    w2 = rel["wrestler2_id"]
    wins1 = rel.get("common_opp_wins_1", 0)
    wins2 = rel.get("common_opp_wins_2", 0)

    # Map counts to wid1/wid2 perspective
    if wid1 == w1:
        wid1_wins, wid2_wins = wins1, wins2
    else:
        wid1_wins, wid2_wins = wins2, wins1

    if wid1_wins == 0 and wid2_wins == 0:
        return None, ""

    if wid1_wins > wid2_wins:
        winner = wid1
    elif wid2_wins > wid1_wins:
        winner = wid2
    else:
        winner = None

    summary = f"CO: {wid1_wins}-{wid2_wins}"
    return winner, summary


def predict_dual_for_weight(
    season: int,
    weight: str,
    team1: str,
    team2: str,
) -> Dict:
    """
    Compute prediction + notes for a single weight.
    Returns a dict with keys:
      weight, w1, w2, w1_rank, w2_rank, winner ("team1"/"team2"/"even"/"none"),
      h2h_note, co_note
    """
    rankings = load_rankings_for_weight(season, weight)
    w1 = best_wrestler_for_team_at_weight(rankings, team1)
    w2 = best_wrestler_for_team_at_weight(rankings, team2)

    if not w1 and not w2:
        return {
            "weight": weight,
            "w1": None,
            "w2": None,
            "w1_rank": None,
            "w2_rank": None,
            "winner": "none",
            "h2h_note": "",
            "co_note": "",
        }

    def rank_val(entry: Optional[Dict]) -> int:
        if not entry:
            return 10**9
        r = entry.get("rank")
        try:
            return int(r)
        except (TypeError, ValueError):
            return 10**8

    r1 = rank_val(w1)
    r2 = rank_val(w2)

    if r1 < r2:
        winner = "team1"
    elif r2 < r1:
        winner = "team2"
    else:
        winner = "even"

    h2h_note = ""
    co_note = ""
    rel_data = load_relationships_for_weight(season, weight)
    if rel_data and w1 and w2:
        wid1 = w1["wrestler_id"]
        wid2 = w2["wrestler_id"]
        h2h_winner, h2h = head_to_head_summary(rel_data, wid1, wid2)
        co_winner, co = common_opp_summary(rel_data, wid1, wid2)

        if h2h:
            # Attach which side has the edge, if any
            if h2h_winner == wid1:
                h2h_note = f"H2H edge: {w1['name']} ({h2h})"
            elif h2h_winner == wid2:
                h2h_note = f"H2H edge: {w2['name']} ({h2h})"
            else:
                h2h_note = f"H2H tied: {h2h}"

        if co:
            if co_winner == wid1:
                co_note = f"CO edge: {w1['name']} ({co})"
            elif co_winner == wid2:
                co_note = f"CO edge: {w2['name']} ({co})"
            else:
                co_note = f"CO even: {co}"

    return {
        "weight": weight,
        "w1": w1,
        "w2": w2,
        "w1_rank": None if r1 >= 10**8 else r1,
        "w2_rank": None if r2 >= 10**8 else r2,
        "winner": winner,
        "h2h_note": h2h_note,
        "co_note": co_note,
    }


def generate_dual_html(
    season: int,
    team1: str,
    team2: str,
    rows: List[Dict],
    output_path: Path,
) -> None:
    """Write an HTML table summarizing the dual prediction."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def esc(s: str) -> str:
        return html.escape(s, quote=True)

    title = f"{team1} vs {team2} — {season} Dual Prediction"

    html_parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        f"<meta charset='utf-8'>",
        f"<title>{esc(title)}</title>",
        "<style>",
        "body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }",
        "h1 { margin-top: 0; }",
        "table { border-collapse: collapse; width: 100%; background-color: #fff; font-size: 13px; }",
        "th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; }",
        "th { background-color: #f0f0f0; }",
        "tbody tr:nth-child(even) { background-color: #fafafa; }",
        ".center { text-align: center; }",
        ".winner { font-weight: bold; color: #006400; }",
        ".unranked { color: #777; }",
        ".notes { font-size: 12px; color: #555; }",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>{esc(team1)} vs {esc(team2)} — {season}</h1>",
        "<table>",
        "<thead>",
        "<tr>",
        "<th>Wt</th>",
        f"<th>{esc(team1)} Wrestler</th>",
        "<th>Rank</th>",
        f"<th>{esc(team2)} Wrestler</th>",
        "<th>Rank</th>",
        "<th class='center'>Predicted Winner</th>",
        "<th>Notes</th>",
        "</tr>",
        "</thead>",
        "<tbody>",
    ]

    for row in rows:
        wt = row["weight"]
        w1 = row["w1"]
        w2 = row["w2"]
        w1_rank = row["w1_rank"]
        w2_rank = row["w2_rank"]
        winner = row["winner"]
        h2h_note = row["h2h_note"]
        co_note = row["co_note"]

        if w1:
            w1_name = f"{w1['name']} ({w1['team']})"
        else:
            w1_name = "-"
        if w2:
            w2_name = f"{w2['name']} ({w2['team']})"
        else:
            w2_name = "-"

        w1_rank_str = str(w1_rank) if w1_rank is not None else "<span class='unranked'>UNR</span>"
        w2_rank_str = str(w2_rank) if w2_rank is not None else "<span class='unranked'>UNR</span>"

        # Winner display
        if winner == "team1" and w1:
            winner_text = esc(w1["name"])
        elif winner == "team2" and w2:
            winner_text = esc(w2["name"])
        elif winner == "even":
            winner_text = "Even"
        else:
            winner_text = "-"

        notes_parts = []
        if h2h_note:
            notes_parts.append(esc(h2h_note))
        if co_note:
            notes_parts.append(esc(co_note))
        notes_html = "<br>".join(notes_parts)

        html_parts.extend(
            [
                "<tr>",
                f"<td class='center'>{esc(wt)}</td>",
                f"<td>{esc(w1_name)}</td>",
                f"<td class='center'>{w1_rank_str}</td>",
                f"<td>{esc(w2_name)}</td>",
                f"<td class='center'>{w2_rank_str}</td>",
                f"<td class='center winner'>{winner_text}</td>",
                f"<td class='notes'>{notes_html}</td>",
                "</tr>",
            ]
        )

    html_parts.extend(
        [
            "</tbody>",
            "</table>",
            "</body>",
            "</html>",
        ]
    )

    with output_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))

    print(f"\nDual prediction written to {output_path}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactive dual-meet predictor using rankings and relationships."
    )
    parser.add_argument(
        "-season",
        type=int,
        default=2026,
        help="Season year (default: 2026).",
    )
    parser.add_argument(
        "-output",
        default=None,
        help=(
            "Output HTML path. Defaults to "
            "mt/graphics/{season}/dual_{team1}_vs_{team2}.html "
            "(with team names slugified)."
        ),
    )

    args = parser.parse_args()
    season = args.season

    teams = load_team_data(season)
    print(f"Loaded {len(teams)} teams for season {season}.\n")

    team1 = prompt_for_team(teams, "Team #1")
    team2 = prompt_for_team(teams, "Team #2")

    print(f"Predicting dual: {team1} vs {team2} (season {season})\n")

    rows: List[Dict] = []
    for wt in WEIGHTS:
        rows.append(predict_dual_for_weight(season, wt, team1, team2))

    if args.output:
        out_path = Path(args.output)
    else:
        def slug(s: str) -> str:
            return (
                "".join(c.lower() if c.isalnum() else "_" for c in s)
                .strip("_")
                .replace("__", "_")
            )

        out_dir = Path("mt/graphics") / str(season)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"dual_{slug(team1)}_vs_{slug(team2)}.html"

    generate_dual_html(season, team1, team2, rows, out_path)


if __name__ == "__main__":
    main()



