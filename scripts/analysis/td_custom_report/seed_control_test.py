#!/usr/bin/env python3
"""Test 1 of the causation-vs-skill question (2026-09-20): among pins in NCAA matches with a takedown edge,
how often was the pinner the wrestler BEHIND on takedowns -- overall, and once wrestler quality is roughly held
constant by comparing only wrestlers with close NCAA seeds.

Seeds come from data/{year}/ncaa-tourney/parsed/matches.json (winner_seed / loser_seed, None when unseeded).
Both wrestlers must be seeded. Output: data/analysis/seed_control_test.txt
"""
import math, sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(HERE.parent))
import td_differential_report as R


def wilson(w, n, z=1.96):
    if n == 0:
        return (0, 0)
    p = w / n; d = 1 + z * z / n; c = p + z * z / (2 * n); a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return 100 * (c - a) / d, 100 * (c + a) / d


def pct(w, n):
    return f"{100 * w / n:5.1f}%" if n else "   -  "


def main():
    bouts = []
    for a, z in [(2014, 2016), (2017, 2019), (2021, 2023), (2024, 2026)]:
        bs, _ = R.load(range(a, z + 1))
        bouts += bs
    out = []
    add = out.append
    edge = [b for b in bouts if b["td"]["winner"] != b["td"]["loser"] and b["cls"] != "forfeit"]
    seeded = [b for b in edge if b["wseed"] and b["lseed"]]
    add("SEED-CONTROL TEST: do pins go to the takedown leader because takedowns matter, or because the better wrestler")
    add("gets both? NCAA Championships 2015-2026 (no 2020), matches with a takedown differential of 1+.")
    add("")
    add(f"Matches with a takedown edge: {len(edge):,}.  Both wrestlers seeded: {len(seeded):,} ({100*len(seeded)/len(edge):.0f}%).")
    add("Unseeded or unmatched-to-results bouts are left out of the seed-controlled rows.")
    add("")

    def row(label, bs):
        pins = [b for b in bs if b["cls"] == "fall"]
        n = len(bs)
        lead = sum(1 for b in pins if b["td"]["winner"] > b["td"]["loser"])
        trail = len(pins) - lead
        lo, hi = wilson(trail, len(pins))
        # pin rate for each side, per match with an edge: leader pins / all edge matches ; trailer pins / all
        add(f"{label:<34} {n:5d} matches | pins {len(pins):4d} | pinner ahead {lead:4d} behind {trail:3d} | "
            f"behind = {pct(trail, len(pins))}  (95% CI {lo:4.1f}-{hi:4.1f}) | leader pins {pct(lead, n)}  trailer pins {pct(trail, n)} of matches")
    add("A. ALL matches with an edge (as in report 3c, forfeit-free), any seeding")
    row("All windows, any seeding", edge)
    add("")
    add("B. Both wrestlers seeded, by SEED GAP (|winner seed - loser seed|; 1 = adjacent seeds, nearly equal skill)")
    bins = [("gap 0-1 (near-equal)", 0, 1), ("gap 2-3", 2, 3), ("gap 4-7", 4, 7), ("gap 8-15", 8, 15), ("gap 16+", 16, 99)]
    for lab, lo, hi in bins:
        row(lab, [b for b in seeded if lo <= abs(b["wseed"] - b["lseed"]) <= hi])
    row("Both seeded, all gaps", seeded)
    add("")
    add("C. Near-equal skill, wider net: gap <= 3 (seeds within 3 places)")
    close = [b for b in seeded if abs(b["wseed"] - b["lseed"]) <= 3]
    row("gap <= 3", close)
    add("")
    add("D. Same rows, but who was the BETTER SEED, and did the better seed lead on takedowns?")
    add("   (skill-only would say the better seed leads AND pins; a takedown effect shows up when the")
    add("    WORSE seed leads on takedowns and still gets the pins)")
    for lab, bs in (("gap <= 3", close), ("both seeded, all", seeded)):
        pins = [b for b in bs if b["cls"] == "fall"]
        cnt = Counter()
        for b in pins:
            better_is_winner = b["wseed"] < b["lseed"]
            winner_leads = b["td"]["winner"] > b["td"]["loser"]
            cnt[(("better seed" if better_is_winner else "worse seed") + " pinned", "led TDs" if winner_leads else "behind on TDs")] += 1
        add(f"   {lab}: " + "; ".join(f"{k[0]}, {k[1]}: {v}" for k, v in sorted(cnt.items())))
    # worse seed leads on takedowns: how do those matches end?
    add("")
    add("E. Only matches where the WORSE seed led on takedowns (skill and takedowns point opposite ways)")
    for lab, bs in (("gap <= 3", close), ("gap 4+", [b for b in seeded if abs(b["wseed"] - b["lseed"]) >= 4]), ("all seeded", seeded)):
        sel = []
        for b in bs:
            lead_seed = b["wseed"] if b["td"]["winner"] > b["td"]["loser"] else b["lseed"]
            other_seed = b["lseed"] if b["td"]["winner"] > b["td"]["loser"] else b["wseed"]
            if lead_seed > other_seed:
                sel.append(b)
        lead_wins = sum(1 for b in sel if b["td"]["winner"] > b["td"]["loser"])
        pins = [b for b in sel if b["cls"] == "fall"]
        lead_pins = sum(1 for b in pins if b["td"]["winner"] > b["td"]["loser"])
        add(f"   {lab:<11} {len(sel):4d} matches | takedown leader (worse seed) won {lead_wins} ({pct(lead_wins, len(sel))}); "
            f"pins {len(pins)}: leader pinned {lead_pins}, better seed pinned from behind {len(pins) - lead_pins}")
    text = "\n".join(out)
    (ROOT / "data/analysis/seed_control_test.txt").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
