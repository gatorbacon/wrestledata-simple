#!/usr/bin/env python3
"""
di_optimizer.py

Analyze exported SI+/DF+/PE+/APD+/DI+ data for top-100 wrestlers per weight
and search for DI+ weights that best align with your existing rankings.

Usage:
    .venv/bin/python scripts/analysis/di_optimizer.py \
        -input mt/metrics_export/season_2026/metrics_top100.json \
        -include-apd \
        -maxrank 100

What it does:

1. Loads a JSON file created by normalized_scoring.py that looks like:
   {
     "season": 2026,
     "weights": {
       "125": [
         {
           "rank": 1,
           "wrestler_id": "...",
           "name": "...",
           "team": "...",
           "SI+": 131.2,
           "DF+": 118.4,
           "PE+": 104.1,
           "APD+": 112.9,      # optional
           "DI+": 123.4,
           "APS7": 14.21,
           "APG7": 7.88,
           "APR": -0.022,
           "APD7": 6.33,
           "sum_weight_APS7": 3.41,
           "sum_weight_APG7": 2.92,
           "matches": 7
         },
         ...
       ],
       "133": [ ... ],
       ...
     }
   }

2. Flattens the data but evaluates rank alignment **within each weight class**
   (because "rank" is defined per weight).

3. Performs a grid search over weights for DI+:
   DI_pred = w_SI * SI+ + w_DF * DF+ + w_PE * PE+ (+ w_APD * APD+ if used)

   - Step size default: 0.05
   - Sum of weights constrained to 1.0 (within small tolerance).
   - Top-50 ranks are given extra importance via a rank-weight multiplier.

4. Objective:
   Minimize total weighted |predicted_rank - true_rank| across all
   wrestlers in all weights.
   - Top-50: multiplied by rank_importance_top (default 2.0)
   - 51–maxrank: multiplied by rank_importance_rest (default 1.0)

5. Prints:
   - Best weight combos and their total error
   - Per-weight summary statistics
   - Example top-10 lists for a sample weight (to eyeball the fit)
"""

import argparse
import json
import math
from collections import defaultdict
from typing import Dict, List, Tuple, Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize DI+ weights against existing rankings.")
    parser.add_argument(
        "-input", "--input",
        required=True,
        help="Path to metrics_topN.json produced by normalized_scoring.py"
    )
    parser.add_argument(
        "-maxrank", "--max-rank",
        type=int,
        default=100,
        help="Maximum ranking position to include per weight class (default: 100)"
    )
    parser.add_argument(
        "-step", "--grid-step",
        type=float,
        default=0.05,
        help="Grid search step size for weights (default: 0.05)"
    )
    parser.add_argument(
        "-include-apd",
        action="store_true",
        help="Include APD+ as a fourth feature if present in JSON"
    )
    parser.add_argument(
        "-topk", "--top-k",
        type=int,
        default=10,
        help="How many best weight sets to print (default: 10)"
    )
    parser.add_argument(
        "--rank-importance-top",
        type=float,
        default=2.0,
        help="Multiplier for |rank error| when true rank <= 50 (default: 2.0)"
    )
    parser.add_argument(
        "--rank-importance-rest",
        type=float,
        default=1.0,
        help="Multiplier for |rank error| when true rank > 50 (default: 1.0)"
    )
    parser.add_argument(
        "--example-weight",
        default="285",
        help="Weight class to show example top-10 comparison (default: '285')"
    )
    return parser.parse_args()


def load_metrics(path: str, max_rank: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Load the metrics JSON and return a dict:
        weight -> list of wrestler dicts (filtered to rank <= max_rank)
    """
    with open(path, "r") as f:
        data = json.load(f)

    if "weights" not in data:
        raise ValueError("JSON missing 'weights' key; check input format.")

    by_weight: Dict[str, List[Dict[str, Any]]] = {}
    for weight, wrestlers in data["weights"].items():
        filtered = [w for w in wrestlers if int(w.get("rank", 9999)) <= max_rank]
        # Sort by true rank just to be safe
        filtered.sort(key=lambda x: int(x["rank"]))
        by_weight[str(weight)] = filtered

    return by_weight


def check_features(by_weight: Dict[str, List[Dict[str, Any]]], include_apd: bool) -> bool:
    """
    Check if APD+ is present when requested. Returns True if APD+ can be used.
    """
    has_apd = False
    for wrestlers in by_weight.values():
        for w in wrestlers:
            if "APD+" in w:
                has_apd = True
                break
        if has_apd:
            break

    if include_apd and not has_apd:
        print("[WARN] --include-apd was set but 'APD+' not found in data. Falling back to 3-feature mode.")
        return False

    return include_apd and has_apd


def evaluate_weights(
    by_weight: Dict[str, List[Dict[str, Any]]],
    w_si: float,
    w_df: float,
    w_pe: float,
    w_apd: float,
    use_apd: bool,
    rank_importance_top: float,
    rank_importance_rest: float
) -> Tuple[float, Dict[str, float]]:
    """
    Given a set of weights, compute:

    - total_error: sum over all weights and wrestlers of
        rank_weight * |predicted_rank - true_rank|

    - per_weight_error: same but keyed by weight string

    We compute predicted ranks *within each weight class*.
    """
    total_error = 0.0
    per_weight_error: Dict[str, float] = {}

    for weight, wrestlers in by_weight.items():
        # Build list with predicted DI scores
        scored = []
        for w in wrestlers:
            si = w.get("SI+")
            df = w.get("DF+")
            pe = w.get("PE+")
            apd = w.get("APD+") if use_apd else None

            # Require these features to be present
            if si is None or df is None or pe is None:
                continue
            if use_apd and apd is None:
                continue

            if use_apd:
                di_pred = w_si * si + w_df * df + w_pe * pe + w_apd * apd
            else:
                di_pred = w_si * si + w_df * df + w_pe * pe

            scored.append((w, di_pred))

        # If not enough wrestlers, skip weight
        if len(scored) < 5:
            continue

        # Sort by predicted DI descending (higher DI = better rank)
        scored.sort(key=lambda tup: tup[1], reverse=True)

        # Map wrestler id -> predicted rank
        pred_ranks: Dict[str, int] = {}
        for idx, (w, _) in enumerate(scored, start=1):
            wid = str(w.get("wrestler_id", f"{weight}_{w.get('name')}"))
            pred_ranks[wid] = idx

        # Accumulate error
        weight_err = 0.0
        for w, _score in scored:
            true_rank = int(w["rank"])
            wid = str(w.get("wrestler_id", f"{weight}_{w.get('name')}"))
            pred_rank = pred_ranks[wid]

            rank_diff = abs(pred_rank - true_rank)

            if true_rank <= 50:
                mult = rank_importance_top
            else:
                mult = rank_importance_rest

            weight_err += mult * rank_diff

        total_error += weight_err
        per_weight_error[weight] = weight_err

    return total_error, per_weight_error


def grid_search(
    by_weight: Dict[str, List[Dict[str, Any]]],
    step: float,
    use_apd: bool,
    rank_importance_top: float,
    rank_importance_rest: float,
    top_k: int
) -> List[Dict[str, Any]]:
    """
    Grid search over weight combinations.

    If use_apd:
        w_si, w_df, w_pe in [0, 1] with step; w_apd = 1 - sum(others)
    Else:
        w_si, w_df in [0, 1] with step; w_pe = 1 - (w_si + w_df)

    Returns a list of the top_k best combos sorted by total_error ascending.
    """
    best_results: List[Dict[str, Any]] = []

    n_steps = int(round(1.0 / step)) + 1
    tol = 1e-6

    if use_apd:
        print(f"[INFO] Grid search with SI+/DF+/PE+/APD+ (step={step})")
        for i in range(n_steps):
            w_si = i * step
            for j in range(n_steps):
                w_df = j * step
                for k in range(n_steps):
                    w_pe = k * step
                    s = w_si + w_df + w_pe
                    if s > 1.0 + tol:
                        continue
                    w_apd = 1.0 - s
                    if w_apd < -tol or w_apd > 1.0 + tol:
                        continue
                    if w_apd < 0:
                        w_apd = 0.0  # numerical noise clamp

                    total_err, per_weight_err = evaluate_weights(
                        by_weight,
                        w_si,
                        w_df,
                        w_pe,
                        w_apd,
                        use_apd=True,
                        rank_importance_top=rank_importance_top,
                        rank_importance_rest=rank_importance_rest,
                    )
                    best_results.append({
                        "w_SI": w_si,
                        "w_DF": w_df,
                        "w_PE": w_pe,
                        "w_APD": w_apd,
                        "total_error": total_err,
                        "per_weight_error": per_weight_err,
                    })
    else:
        print(f"[INFO] Grid search with SI+/DF+/PE+ (step={step})")
        for i in range(n_steps):
            w_si = i * step
            for j in range(n_steps):
                w_df = j * step
                s = w_si + w_df
                if s > 1.0 + tol:
                    continue
                w_pe = 1.0 - s
                if w_pe < -tol or w_pe > 1.0 + tol:
                    continue
                if w_pe < 0:
                    w_pe = 0.0  # clamp

                total_err, per_weight_err = evaluate_weights(
                    by_weight,
                    w_si,
                    w_df,
                    w_pe,
                    w_apd=0.0,
                    use_apd=False,
                    rank_importance_top=rank_importance_top,
                    rank_importance_rest=rank_importance_rest,
                )
                best_results.append({
                    "w_SI": w_si,
                    "w_DF": w_df,
                    "w_PE": w_pe,
                    "w_APD": 0.0,
                    "total_error": total_err,
                    "per_weight_error": per_weight_err,
                })

    # Sort by total_error ascending
    best_results.sort(key=lambda r: r["total_error"])
    return best_results[:top_k]


def show_example_weight(
    by_weight: Dict[str, List[Dict[str, Any]]],
    weights: Dict[str, float],
    example_weight: str
) -> None:
    """
    For a given weight class, print:
      - top 10 by true rank
      - top 10 by predicted DI using the given weights
    so you can eyeball how well they line up.
    """
    example_weight = str(example_weight)
    wrestlers = by_weight.get(example_weight)
    if not wrestlers:
        print(f"[WARN] No data for example weight {example_weight}")
        return

    print("\n=== Example weight class:", example_weight, "===\n")

    # True top 10 by existing rank
    print("Top 10 by TRUE rank:")
    for w in sorted(wrestlers, key=lambda x: int(x["rank"]))[:10]:
        print(f"  #{int(w['rank']):2d}  {w.get('name','?'):25s}  "
              f"SI+={w.get('SI+',0):6.1f}  DF+={w.get('DF+',0):6.1f}  "
              f"PE+={w.get('PE+',0):6.1f}  APD+={w.get('APD+',0):6.1f}")

    print("\nTop 10 by PREDICTED DI with optimized weights:")
    scored = []
    for w in wrestlers:
        si = w.get("SI+")
        df = w.get("DF+")
        pe = w.get("PE+")
        apd = w.get("APD+")
        if si is None or df is None or pe is None:
            continue

        if apd is None:
            di_pred = (
                weights["w_SI"] * si +
                weights["w_DF"] * df +
                weights["w_PE"] * pe
            )
        else:
            di_pred = (
                weights["w_SI"] * si +
                weights["w_DF"] * df +
                weights["w_PE"] * pe +
                weights["w_APD"] * apd
            )
        scored.append((w, di_pred))

    scored.sort(key=lambda tup: tup[1], reverse=True)

    for idx, (w, di_pred) in enumerate(scored[:10], start=1):
        print(f"  DI_rank {idx:2d}  TRUE #{int(w['rank']):2d}  "
              f"{w.get('name','?'):25s}  DI_pred={di_pred:7.2f}")


def main() -> None:
    args = parse_args()

    print(f"[INFO] Loading metrics from: {args.input}")
    by_weight = load_metrics(args.input, max_rank=args.max_rank)
    print(f"[INFO] Loaded {len(by_weight)} weight classes.")
    total_wrestlers = sum(len(lst) for lst in by_weight.values())
    print(f"[INFO] Total wrestlers (rank <= {args.max_rank}): {total_wrestlers}")

    use_apd = check_features(by_weight, include_apd=args.include_apd)

    best = grid_search(
        by_weight=by_weight,
        step=args.grid_step,
        use_apd=use_apd,
        rank_importance_top=args.rank_importance_top,
        rank_importance_rest=args.rank_importance_rest,
        top_k=args.top_k,
    )

    print("\n=== Best weight combinations (lowest total rank error) ===")
    for idx, res in enumerate(best, start=1):
        w_si = res["w_SI"]
        w_df = res["w_DF"]
        w_pe = res["w_PE"]
        w_apd = res["w_APD"]
        total_err = res["total_error"]
        print(f"{idx:2d}) total_error={total_err:10.1f}  "
              f"w_SI={w_si:4.2f}, w_DF={w_df:4.2f}, w_PE={w_pe:4.2f}, w_APD={w_apd:4.2f}")

    if best:
        best_weights = {
            "w_SI": best[0]["w_SI"],
            "w_DF": best[0]["w_DF"],
            "w_PE": best[0]["w_PE"],
            "w_APD": best[0]["w_APD"],
        }

        print("\n=== Recommended DI+ weights based on this run ===")
        print(f"  w_SI  = {best_weights['w_SI']:.3f}")
        print(f"  w_DF  = {best_weights['w_DF']:.3f}")
        print(f"  w_PE  = {best_weights['w_PE']:.3f}")
        if use_apd:
            print(f"  w_APD = {best_weights['w_APD']:.3f}")
        else:
            print("  w_APD = 0.000  (APD+ not used or not present)")

        # Show example for a given weight
        show_example_weight(by_weight, best_weights, args.example_weight)


if __name__ == "__main__":
    main()