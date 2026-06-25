"""
Dual-axis chart: TPAR differential bucket vs prediction accuracy (line)
and match volume (bars), for 2026 NCAA tournament.
"""

import json
import glob
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

DATA_DIR = "frontend/wrestledata-ui/public/data"
SEASON = 2026
NCAA_EVENT = "2026 NCAA Division I Championships"
NCAA_DATE_IMPACT = "03/21/2026"
BUCKET_ORDER = ["< 0.5", "0.5–1.0", "1.0–2.0", "2.0–3.0", "3.0+"]


def load_pretourney_tpar():
    impact_path = f"{DATA_DIR}/mat_value/{SEASON}/match_mv_impact_{SEASON}.json"
    with open(impact_path) as f:
        impact_data = json.load(f)
    pretourney = {}
    for wrestler_id, matches in impact_data.items():
        regular = [m["mv_impact"] for m in matches if m["date"] != NCAA_DATE_IMPACT]
        if regular:
            pretourney[wrestler_id] = sum(regular) / len(regular)
    return pretourney


def load_tournament_matches():
    by_id_dir = f"{DATA_DIR}/wrestlers/{SEASON}/by_id/*.json"
    seen = set()
    matchups = []
    for fpath in glob.glob(by_id_dir):
        with open(fpath) as f:
            d = json.load(f)
        wrestler_id = d["wrestler_id"]
        weight_class = d["weight_class"]
        for m in d.get("match_list", []):
            if m.get("event") != NCAA_EVENT:
                continue
            if m.get("method") == "MFF":
                continue
            opp_id = m.get("opponent_id")
            result = m.get("result")
            if not opp_id or not result:
                continue
            pair = (min(wrestler_id, opp_id), max(wrestler_id, opp_id))
            if pair in seen:
                continue
            seen.add(pair)
            winner_id = wrestler_id if result == "W" else opp_id
            loser_id = opp_id if result == "W" else wrestler_id
            matchups.append({"winner_id": winner_id, "loser_id": loser_id, "weight_class": weight_class})
    return matchups


def differential_bucket(diff):
    if diff < 0.5:
        return "< 0.5"
    elif diff < 1.0:
        return "0.5–1.0"
    elif diff < 2.0:
        return "1.0–2.0"
    elif diff < 3.0:
        return "2.0–3.0"
    else:
        return "3.0+"


def main():
    pretourney = load_pretourney_tpar()
    matchups = load_tournament_matches()

    bucket_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    for m in matchups:
        w_tpar = pretourney.get(m["winner_id"])
        l_tpar = pretourney.get(m["loser_id"])
        if w_tpar is None or l_tpar is None:
            continue
        diff = abs(w_tpar - l_tpar)
        b = differential_bucket(diff)
        bucket_stats[b]["total"] += 1
        if w_tpar >= l_tpar:
            bucket_stats[b]["correct"] += 1

    counts = [bucket_stats[b]["total"] for b in BUCKET_ORDER]
    accuracies = [
        100 * bucket_stats[b]["correct"] / bucket_stats[b]["total"]
        if bucket_stats[b]["total"] > 0 else 0
        for b in BUCKET_ORDER
    ]

    x = np.arange(len(BUCKET_ORDER))
    bar_width = 0.55

    fig, ax1 = plt.subplots(figsize=(9, 5.5))

    # Bars — match volume
    bars = ax1.bar(x, counts, width=bar_width, color="#4a90d9", alpha=0.55, label="Matches")
    ax1.set_ylabel("Number of Matches", fontsize=11, color="#4a90d9")
    ax1.tick_params(axis="y", labelcolor="#4a90d9")
    ax1.set_ylim(0, max(counts) * 1.45)

    # Count labels on bars
    for bar, count in zip(bars, counts):
        ax1.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 2,
            str(count),
            ha="center", va="bottom", fontsize=10, color="#2a6099"
        )

    # Line — accuracy
    ax2 = ax1.twinx()
    ax2.plot(x, accuracies, color="#e05c2a", marker="o", linewidth=2.5,
             markersize=8, label="Accuracy %", zorder=5)
    ax2.set_ylabel("Prediction Accuracy (%)", fontsize=11, color="#e05c2a")
    ax2.tick_params(axis="y", labelcolor="#e05c2a")
    ax2.set_ylim(0, 115)
    ax2.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))

    # Accuracy labels on line points
    for xi, acc in zip(x, accuracies):
        ax2.text(xi, acc + 4, f"{acc:.1f}%", ha="center", va="bottom",
                 fontsize=10, color="#e05c2a", fontweight="bold")

    # 50% reference line
    ax2.axhline(50, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)
    ax2.text(len(BUCKET_ORDER) - 0.5, 51.5, "50%", fontsize=8, color="gray", alpha=0.7)

    ax1.set_xticks(x)
    ax1.set_xticklabels(BUCKET_ORDER, fontsize=11)
    ax1.set_xlabel("Pre-Tournament TPAR Differential", fontsize=11)

    plt.title(
        "2026 NCAA Tournament — TPAR Prediction Accuracy by Differential\n"
        "(pre-tournament TPAR only, MFF excluded)",
        fontsize=12, pad=12
    )

    # Combined legend
    lines = [
        plt.Rectangle((0, 0), 1, 1, fc="#4a90d9", alpha=0.55),
        plt.Line2D([0], [0], color="#e05c2a", marker="o", linewidth=2.5, markersize=8),
    ]
    ax1.legend(lines, ["Matches in bucket", "Prediction accuracy"],
               loc="upper left", fontsize=10)

    plt.tight_layout()
    out_path = "scripts/analysis/tpar_accuracy_chart.png"
    plt.savefig(out_path, dpi=150)
    print(f"Saved: {out_path}")
    plt.show()


if __name__ == "__main__":
    main()
