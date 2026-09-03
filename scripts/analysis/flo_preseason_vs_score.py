#!/usr/bin/env python3
"""
Compares FloWrestling preseason (early-season) rankings to actual NCAA D1
Championships scoring, and benchmarks that against the same comparison using
the official tournament seed (the existing seed-vs-score ground truth).

Answers: "how many points did the #N preseason-ranked wrestler score at
NCAAs, on average, vs. how many points did the #N seed score?"

Inputs:
  data/2026/flo-preseason-rankings/2025-09-29.json   (scraped from FloWrestling)
  data/ncaa-tourney-parsed/all_wrestlers.json         (built by parse_ncaa_results.py)

Usage:
  python scripts/analysis/flo_preseason_vs_score.py
  python scripts/analysis/flo_preseason_vs_score.py --year 2026 --top 20
"""

import argparse
import json
import statistics
import unicodedata
import re
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
COMBINED_DIR = DATA_DIR / "ncaa-tourney-parsed"


def normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    # Canonicalize apostrophe-like characters -- FloWrestling and the tournament
    # results source use different ones inconsistently (e.g. "D'Emilio" (U+0027)
    # vs "D`Emilio" (U+0060) both appear for the same real person), and a raw
    # string comparison treats them as different names, silently losing matches
    # for every O'-/D'-prefixed name (O'Connor, O'Toole, O'Malley, O'Reilly, ...).
    name = re.sub(r"[`´'‘’]", "'", name)
    return re.sub(r"\s+", " ", name.strip().lower())


def load_preseason_rankings(path: Path) -> dict:
    data = json.loads(path.read_text())
    return data["weights"]


def load_tourney_results(year: int) -> dict:
    """Return {(weight, normalized_name): wrestler_record} for one year, plus a
    fallback (weight, last_name, first_initial) index for nickname mismatches
    (e.g. Flo's 'Michael Caliendo' vs. the tournament roster's 'Mikey Caliendo')."""
    all_wrestlers = json.loads((COMBINED_DIR / "all_wrestlers.json").read_text())
    by_weight_name = {}
    by_weight_lastname = defaultdict(list)
    for w in all_wrestlers:
        if w["year"] != year:
            continue
        key = (w["weight"], normalize_name(w["name"]))
        by_weight_name[key] = w
        parts = normalize_name(w["name"]).split()
        if len(parts) >= 2:
            by_weight_lastname[(w["weight"], parts[-1], parts[0][0])].append(w)
    return by_weight_name, by_weight_lastname


def lookup_result(weight, name, by_weight_name, by_weight_lastname):
    key = (weight, normalize_name(name))
    rec = by_weight_name.get(key)
    if rec:
        return rec
    parts = normalize_name(name).split()
    if len(parts) >= 2:
        candidates = by_weight_lastname.get((weight, parts[-1], parts[0][0]))
        if candidates and len(candidates) == 1:
            return candidates[0]
    return None


def match_preseason_to_results(preseason: dict, by_weight_name, by_weight_lastname, top_n: int):
    """Yield (rank, weight, preseason_name, result_record_or_None)."""
    rows = []
    for weight_str, entries in preseason.items():
        weight = int(weight_str)
        for e in entries:
            if e["rank"] > top_n:
                continue
            rec = lookup_result(weight, e["name"], by_weight_name, by_weight_lastname)
            rows.append((e["rank"], weight, e["name"], rec))
    return rows


def summarize_by_rank(rows, top_n: int):
    """DNQs (no tournament record found) score 0 points -- a preseason rank
    that never makes NCAAs (injury, transfer, failure to qualify) is exactly
    the kind of outcome this analysis is meant to capture: it IS the risk
    baked into an early-season ranking, not missing data to discard."""
    by_rank = defaultdict(list)
    for rank, weight, name, rec in rows:
        by_rank[rank].append((weight, name, rec))

    out = []
    for rank in range(1, top_n + 1):
        entries = by_rank.get(rank, [])
        dnq = [(w, n) for (w, n, r) in entries if r is None]
        points = [(r["total_points"] if r is not None else 0.0) for (_, _, r) in entries]
        placements = [r["placement"] for (_, _, r) in entries if r is not None and r["placement"] > 0]
        out.append({
            "rank": rank,
            "n": len(entries),
            "n_dnq": len(dnq),
            "avg_points": round(statistics.mean(points), 2) if points else None,
            "std_points": round(statistics.stdev(points), 2) if len(points) > 1 else 0.0,
            "avg_placement_if_qualified": round(statistics.mean(placements), 2) if placements else None,
            "dnq": [f"{n} ({w}lb)" for w, n in dnq],
        })
    return out


def summarize_by_seed(results: dict, top_n: int):
    by_seed = defaultdict(list)
    for rec in results.values():
        if 1 <= rec["seed"] <= top_n:
            by_seed[rec["seed"]].append(rec)

    out = []
    for seed in range(1, top_n + 1):
        recs = by_seed.get(seed, [])
        points = [r["total_points"] for r in recs]
        placements = [r["placement"] for r in recs if r["placement"] > 0]
        out.append({
            "seed": seed,
            "n": len(recs),
            "avg_points": round(statistics.mean(points), 2) if points else None,
            "std_points": round(statistics.stdev(points), 2) if len(points) > 1 else 0.0,
            "avg_placement": round(statistics.mean(placements), 2) if placements else None,
        })
    return out


def main():
    parser = argparse.ArgumentParser(description="Preseason rank vs. seed vs. NCAA score")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument(
        "--preseason-file",
        default=str(DATA_DIR / "2026" / "flo-preseason-rankings" / "2025-09-29.json"),
    )
    args = parser.parse_args()

    preseason = load_preseason_rankings(Path(args.preseason_file))
    by_weight_name, by_weight_lastname = load_tourney_results(args.year)

    rows = match_preseason_to_results(preseason, by_weight_name, by_weight_lastname, args.top)
    preseason_summary = summarize_by_rank(rows, args.top)
    seed_summary = summarize_by_seed(by_weight_name, args.top)

    print("=" * 110)
    print(f"{args.year} NCAA D1 Championships: Preseason Rank vs. Seed as Predictors of Score (DNQ = 0 pts)")
    print(f"Preseason source: {args.preseason_file}")
    print("=" * 110)
    print(f"{'Rank/Seed':>9}  {'Preseason n':>11}  {'DNQ':>4}  {'Preseason Avg Pts':>18}  {'Preseason Std':>13}  {'Seed Avg Pts':>13}  {'Diff (Preseason-Seed)':>22}")
    print("-" * 110)

    combined = []
    for p, s in zip(preseason_summary, seed_summary):
        assert p["rank"] == s["seed"]
        diff = None
        if p["avg_points"] is not None and s["avg_points"] is not None:
            diff = round(p["avg_points"] - s["avg_points"], 2)
        print(f"{p['rank']:>9}  {p['n']:>11}  {p['n_dnq']:>4}  {str(p['avg_points']):>18}  {str(p['std_points']):>13}  {str(s['avg_points']):>13}  {str(diff):>22}")
        combined.append({"rank": p["rank"], "preseason": p, "seed": s, "diff_avg_points": diff})

    all_dnq = [u for p in preseason_summary for u in p["dnq"]]
    if all_dnq:
        print(f"\n{len(all_dnq)} preseason-ranked wrestlers scored as 0 pts (never appeared in {args.year} tournament results):")
        for u in all_dnq:
            print(f"  - {u}")

    out_path = COMBINED_DIR / f"flo_preseason_vs_score_{args.year}.json"
    out_path.write_text(json.dumps({
        "year": args.year,
        "top_n": args.top,
        "preseason_source": args.preseason_file,
        "by_rank": combined,
    }, indent=2))
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
