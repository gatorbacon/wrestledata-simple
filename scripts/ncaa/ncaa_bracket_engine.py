#!/usr/bin/env python3
"""
NCAA Tournament bracket engine adapter.

Wraps BracketEngine (one per weight class) with seed-based win probability
and bonus EV from seed_model.json, instead of rank+MatValue.

Wrestler IDs throughout = seed number as string: "1", "2", ..., "33".
"""

import copy
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from xtp.engine.bracket_schema import ALL_SLOTS, get_all_slots, Slot
from xtp.engine.engine import BracketEngine
from xtp.engine.scoring import advancement_points_for_slot, placement_points

WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285]


# ---------------------------------------------------------------------------
# Seed-aware BracketEngine subclass
# ---------------------------------------------------------------------------

class NCAASeedBracketEngine(BracketEngine):
    """
    BracketEngine subclass that uses seed-pair win probabilities from seed_model.json
    instead of rank+MV-based model.

    All wrestler IDs are seed strings: "1", "2", ..., "33".
    """

    def __init__(
        self,
        slots: dict,
        seeds: Dict[int, str],
        win_prob_table: Dict[str, Dict[str, float]],
        bonus_ev_table: Dict[str, Dict[str, float]],
    ):
        """
        Args:
            slots: Bracket slot dict (from bracket_schema.get_all_slots())
            seeds: {seed_int: wrestler_id_str}  e.g. {1: "1", ..., 33: "33"}
            win_prob_table: {str(lo_seed): {str(hi_seed): p_lo_wins}}
            bonus_ev_table: {str(winner_seed): {str(loser_seed): ev}}
        """
        # Initialize with empty rank/mv/bonus so parent bonus calc = 0
        super().__init__(slots, seeds, enable_probability=True)
        self.win_prob_table = win_prob_table
        self.bonus_ev_table = bonus_ev_table
        # Actual bonus earned per slot (locked in when result is applied)
        self.actual_bonus_by_slot: Dict[str, float] = {}

    # ------------------------------------------------------------------
    # Override win probability lookup
    # ------------------------------------------------------------------

    def _get_win_prob(self, id_a: str, id_b: str) -> float:
        """P(id_a wins) using seed-based table. id_a and id_b are seed strings."""
        try:
            sa, sb = int(id_a), int(id_b)
        except (ValueError, TypeError):
            return 0.5
        lo, hi = min(sa, sb), max(sa, sb)
        p_lo_wins = self.win_prob_table.get(str(lo), {}).get(str(hi), 0.5)
        return p_lo_wins if sa == lo else (1.0 - p_lo_wins)

    def _resolve_slot_probabilities(self, slot_id: str, is_deterministic: bool = False):
        """Override: use seed-based win probability in cross-product."""
        if not self.enable_probability:
            return

        A_dist = self.slot_input_dists[slot_id]["A"]
        B_dist = self.slot_input_dists[slot_id]["B"]

        if not A_dist or not B_dist:
            return

        if is_deterministic and slot_id in self.slot_results:
            winner_id = self.slot_results[slot_id]["winner"]
            loser_id = self.slot_results[slot_id]["loser"]
            # Both winner and loser have probability 1.0 in their respective paths
            winner_dist = {winner_id: 1.0}
            loser_dist = {loser_id: 1.0}
        else:
            winner_dist: Dict[str, float] = {}
            loser_dist: Dict[str, float] = {}

            # Normalize Ppairs so they sum to 1.0 regardless of mass inflation
            total_mass = sum(pa * pb for pa in A_dist.values() for pb in B_dist.values())
            if total_mass <= 0.0:
                return

            for wrestler_a, prob_a in A_dist.items():
                for wrestler_b, prob_b in B_dist.items():
                    Ppair = (prob_a * prob_b) / total_mass  # normalized
                    if Ppair == 0.0:
                        continue
                    p_a_wins = self._get_win_prob(wrestler_a, wrestler_b)
                    p_b_wins = 1.0 - p_a_wins
                    winner_dist[wrestler_a] = winner_dist.get(wrestler_a, 0.0) + Ppair * p_a_wins
                    winner_dist[wrestler_b] = winner_dist.get(wrestler_b, 0.0) + Ppair * p_b_wins
                    loser_dist[wrestler_a] = loser_dist.get(wrestler_a, 0.0) + Ppair * p_b_wins
                    loser_dist[wrestler_b] = loser_dist.get(wrestler_b, 0.0) + Ppair * p_a_wins

        self.slot_prob_results[slot_id] = {"winner": winner_dist, "loser": loser_dist}
        self._propagate_probability_mass_to_downstream(slot_id, winner_dist, loser_dist)

    def compute_expected_points(self):
        """Override: use parent's advancement+placement logic, then add seed-based bonus."""
        # Call parent with empty bonus_ev_by_id (already empty from __init__)
        super().compute_expected_points()

        # Now add seed-based bonus on top
        if not self.enable_probability:
            return

        all_wrestlers = set(self.seeds.values())

        for slot_id in self.resolved_slots:
            slot = self.slots[slot_id]

            # Count bonus for all slots that have known results, including
            # placement matches (3rd/5th/7th give bonus but no advancement)
            # and the championship final (gives bonus but no advancement).
            # Only skip true terminal PLACE_ slots and unscored rounds.
            adv = advancement_points_for_slot(slot)

            if slot_id not in self.slot_prob_results:
                continue
            if slot_id not in self.slot_input_dists:
                continue

            A_dist = self.slot_input_dists[slot_id]["A"]
            B_dist = self.slot_input_dists[slot_id]["B"]

            is_det = slot_id in self.deterministic_slots

            if is_det and slot_id in self.slot_results:
                # Deterministic: use actual bonus earned, not model EV
                winner_id = self.slot_results[slot_id]["winner"]
                actual_bonus = self.actual_bonus_by_slot.get(slot_id, 0.0)
                self.expected_bonus_points[winner_id] = (
                    self.expected_bonus_points.get(winner_id, 0.0) + actual_bonus
                )
            else:
                # Probabilistic: iterate over normalized A×B matchup pairs
                pair_total = sum(pa * pb for pa in A_dist.values() for pb in B_dist.values())
                if pair_total <= 0.0:
                    continue

                for id_a, prob_a in A_dist.items():
                    for id_b, prob_b in B_dist.items():
                        Ppair = (prob_a * prob_b) / pair_total  # normalized
                        if Ppair == 0.0:
                            continue
                        p_a_wins = self._get_win_prob(id_a, id_b)
                        p_b_wins = 1.0 - p_a_wins

                        ev_a = self.bonus_ev_table.get(id_a, {}).get(id_b, 0.0)
                        self.expected_bonus_points[id_a] = (
                            self.expected_bonus_points.get(id_a, 0.0)
                            + Ppair * p_a_wins * ev_a
                        )

                        ev_b = self.bonus_ev_table.get(id_b, {}).get(id_a, 0.0)
                        self.expected_bonus_points[id_b] = (
                            self.expected_bonus_points.get(id_b, 0.0)
                            + Ppair * p_b_wins * ev_b
                        )

    def _check_and_resolve_downstream_probabilities(self, resolved_slot_id: str):
        """Suppress eager cascade during set_winner — run() handles full resolution."""
        pass  # intentionally no-op; avoids pre-empting later deterministic overrides

    def resolve_all_probabilistically(self, max_iterations: int = 100, epsilon: float = 1e-9):
        """Override to fix uninitialized 'changed' variable in parent."""
        if not self.enable_probability:
            return

        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            changed = False  # ← parent is missing this initialization
            slots_resolved_this_iteration = 0

            for slot_id, slot in self.slots.items():
                if slot_id in self.resolved_slots:
                    continue
                if slot_id in self.slot_prob_results:
                    self.resolved_slots.add(slot_id)
                    continue
                if slot_id in self.deterministic_slots:
                    self.resolved_slots.add(slot_id)
                    continue

                A_dist = self.slot_input_dists[slot_id]["A"]
                B_dist = self.slot_input_dists[slot_id]["B"]
                if not A_dist or not B_dist:
                    continue

                try:
                    before_winner = self.slot_prob_results.get(slot_id, {}).get("winner", {})
                    before_loser = self.slot_prob_results.get(slot_id, {}).get("loser", {})
                    self._resolve_slot_probabilities(slot_id, is_deterministic=False)
                    if slot_id in self.slot_prob_results:
                        after_winner = self.slot_prob_results[slot_id].get("winner", {})
                        after_loser = self.slot_prob_results[slot_id].get("loser", {})
                        if self._distributions_changed(before_winner, after_winner, epsilon) or \
                           self._distributions_changed(before_loser, after_loser, epsilon):
                            changed = True
                        self.resolved_slots.add(slot_id)
                        slots_resolved_this_iteration += 1
                        self._check_and_resolve_downstream_probabilities(slot_id)
                except Exception:
                    continue

            if not changed and slots_resolved_this_iteration == 0:
                can_resolve_more = False
                for slot_id in self.slots:
                    if slot_id in self.resolved_slots or slot_id in self.deterministic_slots:
                        continue
                    A_dist = self.slot_input_dists[slot_id]["A"]
                    B_dist = self.slot_input_dists[slot_id]["B"]
                    if A_dist and B_dist:
                        can_resolve_more = True
                        break
                if not can_resolve_more:
                    break

        for slot_id in self.slot_prob_results:
            self.resolved_slots.add(slot_id)

    def find_slot_for_match(self, winner_id: str, loser_id: str) -> Optional[str]:
        """Find the slot that currently has winner_id and loser_id as inputs.

        Skips slots already resolved deterministically. Probabilistically-resolved
        slots are still candidates (they'll be overridden).
        Returns slot_id or None.
        """
        for slot_id, slot in self.slots.items():
            if slot_id in self.deterministic_slots:  # already has a known result
                continue
            if slot_id.startswith("PLACE_"):
                continue
            inputs = self.get_slot_inputs(slot_id)
            if set(inputs) == {winner_id, loser_id}:
                return slot_id
        return None


# ---------------------------------------------------------------------------
# Multi-weight NCAA Tournament Engine
# ---------------------------------------------------------------------------

class NCAATournamentEngine:
    """
    Manages 10 weight-class bracket engines for a full NCAA tournament.

    Usage:
        engine = NCAATournamentEngine(seed_model, seeds_by_weight)
        engine.run()  # probabilistic projection
        engine.set_result(125, "R32", "1")  # apply live result
        snap = engine.get_snapshot()
    """

    def __init__(
        self,
        seed_model: dict,
        seeds_by_weight: Dict[int, Dict[int, dict]],
    ):
        """
        Args:
            seed_model: Loaded seed_model.json dict
            seeds_by_weight: {weight: {seed_int: {"name": str, "team": str}}}
        """
        self.seed_model = seed_model
        self.seeds_by_weight = seeds_by_weight

        win_prob = seed_model["win_prob"]
        bonus_ev = seed_model["bonus_ev_for_winner"]

        # One engine per weight class
        # Wrestler IDs = str(seed) for each weight (separate namespaces)
        self.engines: Dict[int, NCAASeedBracketEngine] = {}
        for weight in WEIGHTS:
            if weight not in seeds_by_weight:
                continue
            seeds_dict = {s: str(s) for s in range(1, 34)}  # seed_int → "seed_str"
            engine = NCAASeedBracketEngine(
                slots=get_all_slots(),
                seeds=seeds_dict,
                win_prob_table=win_prob,
                bonus_ev_table=bonus_ev,
            )
            self.engines[weight] = engine

        # Track actual points earned so far (locked in for eliminated wrestlers)
        # {weight: {seed_str: actual_pts_so_far}}
        self.actual_points: Dict[int, Dict[str, float]] = {w: {} for w in WEIGHTS}

        # Pre-tournament projections (set after first run())
        self.pre_tourney_projections: Dict[int, Dict[str, float]] = {}

    def run(self) -> None:
        """Run full probabilistic projection for all weight classes."""
        for weight, engine in self.engines.items():
            engine.resolve_all_probabilistically()
            engine.compute_expected_points()

    def _find_slot(self, engine: NCAASeedBracketEngine, winner_seed: str, loser_seed: str) -> Optional[str]:
        """Find slot for this winner/loser pair in the engine."""
        return engine.find_slot_for_match(winner_seed, loser_seed)

    def set_result(
        self,
        weight: int,
        winner_seed: int,
        loser_seed: int,
        result_type: str = "Dec",
        actual_bonus: float = 0.0,
    ) -> bool:
        """
        Apply a live match result.

        Args:
            weight: Weight class (125, 133, ...)
            winner_seed: Seed of winner
            loser_seed: Seed of loser
            result_type: "Dec", "MD", "TF", "Fall", etc.
            actual_bonus: Bonus points earned (0.0, 1.0, 1.5, 2.0)

        Returns:
            True if successfully applied
        """
        engine = self.engines.get(weight)
        if not engine:
            return False

        w_id = str(winner_seed)
        l_id = str(loser_seed)

        slot_id = self._find_slot(engine, w_id, l_id)
        if not slot_id:
            return False

        try:
            engine.set_winner(slot_id, w_id)
        except ValueError as e:
            print(f"  WARNING: {weight}lb {winner_seed} vs {loser_seed}: {e}", file=sys.stderr)
            return False

        # Track actual bonus earned for this slot (used instead of model EV for completed matches)
        engine.actual_bonus_by_slot[slot_id] = actual_bonus

        # Track actual advancement points earned
        slot = engine.slots[slot_id]
        adv = advancement_points_for_slot(slot)
        prev = self.actual_points[weight].get(w_id, 0.0)
        self.actual_points[weight][w_id] = prev + adv + actual_bonus

        return True

    def get_projections(self) -> Dict[int, Dict[str, float]]:
        """
        Get projected total points per wrestler per weight.

        For eliminated wrestlers: locked-in actual points.
        For surviving wrestlers: actual so far + engine's remaining xTP.

        Returns:
            {weight: {seed_str: projected_total}}
        """
        projections = {}
        for weight, engine in self.engines.items():
            engine.compute_expected_points()
            xtp = engine.get_xtp()

            weight_proj = {}
            for seed_str, xtp_val in xtp.items():
                actual = self.actual_points[weight].get(seed_str, 0.0)
                # xTP already accounts for actual-locked slots; just use it directly
                weight_proj[seed_str] = round(xtp_val, 4)
            projections[weight] = weight_proj
        return projections

    def get_team_totals(self, projections: Optional[dict] = None) -> Dict[str, float]:
        """Sum projected points by team across all weights."""
        if projections is None:
            projections = self.get_projections()

        team_totals: Dict[str, float] = {}
        for weight, weight_proj in projections.items():
            weight_info = self.seeds_by_weight.get(weight, {})
            for seed_str, pts in weight_proj.items():
                try:
                    seed_int = int(seed_str)
                except ValueError:
                    continue
                wrestler_info = weight_info.get(seed_int, {})
                team = wrestler_info.get("team", "Unknown")
                team_totals[team] = team_totals.get(team, 0.0) + pts

        return team_totals

    def get_aa_probabilities(self) -> Dict[int, Dict[str, float]]:
        """P(All-American) per wrestler per weight."""
        aa = {}
        for weight, engine in self.engines.items():
            try:
                probs = engine.get_placement_probabilities()
                aa[weight] = {wid: p["aa_probability"] for wid, p in probs.items()}
            except Exception:
                aa[weight] = {}
        return aa

    def _infer_missing_pig_matches(self, matches: list) -> list:
        """
        For weights missing a PIG match (pigtail), infer it from the R32 data.
        C_R32_0 = seed 1 vs PIG_WINNER. If there's an R32 match with seed 1,
        the other wrestler is PIG_WINNER; the other of {32,33} is PIG_LOSER.
        Returns matches with any inferred PIG matches prepended.
        """
        # Group by weight: which weights have PIG matches?
        by_weight = {}
        for m in matches:
            wt = m.get("weight")
            rnd = m.get("round")
            if wt not in by_weight:
                by_weight[wt] = {"PIG": [], "R32": []}
            if rnd == "PIG":
                by_weight[wt]["PIG"].append(m)
            elif rnd == "R32":
                by_weight[wt]["R32"].append(m)

        synthetic = []
        for wt, data in by_weight.items():
            if data["PIG"]:
                continue  # already have pigtail match
            # Look for seed 1 in R32 for this weight
            seed1_match = next(
                (m for m in data["R32"] if m.get("winner_seed") == 1 or m.get("loser_seed") == 1),
                None
            )
            if not seed1_match:
                continue
            # PIG_WINNER is whoever faced seed 1 in R32
            ws1 = seed1_match.get("winner_seed")
            ls1 = seed1_match.get("loser_seed")
            pig_winner = ls1 if ws1 == 1 else ws1
            pig_loser = 33 if pig_winner == 32 else 32
            synthetic.append({
                "weight": wt,
                "round": "PIG",
                "bracket": "champ",
                "winner_seed": pig_winner,
                "loser_seed": pig_loser,
                "result_type": "Forfeit",  # assume forfeit
            })

        return synthetic + matches if synthetic else matches

    def _infer_missing_cons_pig_matches(self, matches: list) -> list:
        """
        For weights missing a C_PIG match (consolation pigtail), infer from C_R1 data.
        The winner of C_PIG feeds into CONS_R1_4 alongside C_R32_9_LOSER.
        If a C_R1 match has a wrestler who would have been CONS_PIG_0_WINNER,
        we can infer the C_PIG result by checking who appears in the C_R1 data.
        """
        by_weight: dict = {}
        for m in matches:
            wt = m.get("weight")
            rnd = m.get("round")
            if wt not in by_weight:
                by_weight[wt] = {"C_PIG": [], "PIG": [], "R32": [], "C_R1": []}
            rnd_key = rnd if rnd in by_weight[wt] else None
            if rnd_key:
                by_weight[wt][rnd_key].append(m)

        synthetic = []
        for wt, data in by_weight.items():
            if data["C_PIG"]:
                continue  # already have consolation pigtail

            # CONS_PIG_0 inputs: [C_PIG_0_LOSER, C_R32_8_LOSER]
            # C_PIG_0_LOSER = pigtail loser (whichever of 32/33 lost the champ pigtail)
            # C_R32_8_LOSER = loser of seed 3 vs seed 30 R32 match

            # Find C_PIG_0 loser from PIG matches (or from synthesized PIGs we just made)
            all_pigs = data["PIG"] + [m for m in matches if m.get("weight") == wt and m.get("round") == "PIG"]
            pig_loser = None
            for pm in all_pigs:
                pig_loser = pm.get("loser_seed")
                break

            # Find C_R32_8 loser from R32 data (seed 3 vs seed 30 match)
            r32_8_loser = None
            for m in data["R32"]:
                ws, ls = m.get("winner_seed"), m.get("loser_seed")
                if {ws, ls} == {3, 30}:
                    r32_8_loser = ls
                    break

            if pig_loser is None or r32_8_loser is None:
                continue

            # Check if there's a C_R1 match that features a wrestler who should be
            # CONS_PIG_0_WINNER (either pig_loser or r32_8_loser won the consol pigtail)
            # CONS_R1_4 has CONS_PIG_0_WINNER vs C_R32_9_LOSER
            # C_R32_9_LOSER = loser of seed 14 vs seed 19 R32 match
            r32_9_loser = None
            for m in data["R32"]:
                ws, ls = m.get("winner_seed"), m.get("loser_seed")
                if {ws, ls} == {14, 19}:
                    r32_9_loser = ls
                    break

            if r32_9_loser is None:
                continue

            # Look for C_R1 match that has r32_9_loser as one participant
            # (since CONS_R1_4 = CONS_PIG_0_WINNER vs r32_9_loser)
            cons_pig_winner = None
            for m in data["C_R1"]:
                ws, ls = m.get("winner_seed"), m.get("loser_seed")
                if ls == r32_9_loser or ws == r32_9_loser:
                    # The other wrestler is CONS_PIG_0_WINNER
                    cons_pig_winner = ws if ls == r32_9_loser else ls
                    break

            if cons_pig_winner is None:
                # Fallback: assume r32_8_loser won the consol pigtail
                cons_pig_winner = r32_8_loser

            cons_pig_loser = pig_loser if cons_pig_winner == r32_8_loser else r32_8_loser
            synthetic.append({
                "weight": wt,
                "round": "C_PIG",
                "bracket": "consol",
                "winner_seed": cons_pig_winner,
                "loser_seed": cons_pig_loser,
                "result_type": "Forfeit",
            })

        return synthetic + matches if synthetic else matches

    def replay_matches(self, matches: list) -> int:
        """
        Apply a list of match dicts in round order. Returns count applied.
        Matches must have: weight, winner_seed, loser_seed, result_type.
        """
        ROUND_ORDER = [
            "PIG",
            "R32", "C_PIG",  # C_PIG needs C_R32_8_LOSER → must come after R32
            "C_R1",
            "R16", "C_R2",
            "QF", "C_R3", "C_R4",
            "SF", "C_QF",
            "C_SF", "Final", "3rd", "5th", "7th",
        ]
        round_rank = {r: i for i, r in enumerate(ROUND_ORDER)}
        matches = self._infer_missing_pig_matches(matches)
        matches = self._infer_missing_cons_pig_matches(matches)
        sorted_m = sorted(
            matches,
            key=lambda m: (round_rank.get(m.get("round", ""), 99), m.get("weight", 0)),
        )
        applied = 0
        for m in sorted_m:
            ws = m.get("winner_seed")
            ls = m.get("loser_seed")
            wt = m.get("weight")
            result_type = m.get("result_type", "Dec")
            bonus_map = {
                "Dec": 0.0, "SV-1": 0.0, "SV-2": 0.0, "SV-3": 0.0,
                "TB-1": 0.0, "TB-2": 0.0, "TB-3": 0.0, "UTB": 0.0,
                "MD": 1.0, "TF": 1.5,
                "Fall": 2.0, "Forfeit": 2.0, "DQ": 2.0, "Inj.": 2.0,
            }
            bonus = bonus_map.get(result_type, 0.0)
            if ws and ls and wt:
                ok = self.set_result(wt, ws, ls, result_type=result_type, actual_bonus=bonus)
                if ok:
                    applied += 1
        return applied

    @classmethod
    def from_matches(
        cls,
        seed_model: dict,
        seeds_by_weight: dict,
        matches: list,
    ) -> "NCAATournamentEngine":
        """Create a fresh engine, apply matches, run projection. Returns ready engine."""
        eng = cls(seed_model, seeds_by_weight)
        eng.replay_matches(matches)
        eng.run()
        return eng

    def get_snapshot(self) -> dict:
        """Return a serializable snapshot for live_data.json."""
        projections = self.get_projections()
        team_totals = self.get_team_totals(projections)
        aa_probs = self.get_aa_probabilities()

        wrestlers_out = {}
        for weight in WEIGHTS:
            engine = self.engines.get(weight)
            if not engine:
                continue
            weight_info = self.seeds_by_weight.get(weight, {})
            try:
                xtp_components = engine.get_xtp_components() if engine._points_computed else {}
            except (ValueError, Exception):
                xtp_components = {}  # partial data — skip xtp_components for this weight

            wrestlers_out[str(weight)] = {}
            for seed_int in range(1, 34):
                seed_str = str(seed_int)
                info = weight_info.get(seed_int, {})
                comp = xtp_components.get(seed_str, {})
                actual = self.actual_points[weight].get(seed_str, 0.0)
                projected = projections.get(weight, {}).get(seed_str, 0.0)
                aa_prob = aa_probs.get(weight, {}).get(seed_str, 0.0)
                alive = seed_str not in _get_eliminated(engine)

                wrestlers_out[str(weight)][seed_str] = {
                    "name": info.get("name", f"Seed {seed_int}"),
                    "team": info.get("team", "Unknown"),
                    "actual": round(actual, 2),
                    "projected_remaining": round(projected - actual, 2),
                    "projected_total": round(projected, 2),
                    "aa_prob": round(aa_prob, 4),
                    "alive": alive,
                }

        # Count completed matches
        matches_completed = sum(
            len(e.deterministic_slots)
            for e in self.engines.values()
        )

        return {
            "year": 2026,
            "last_updated": datetime.now().isoformat(timespec="seconds"),
            "matches_completed": matches_completed,
            "matches_total": 640,
            "current_projection": {t: round(v, 2) for t, v in team_totals.items()},
            "wrestlers": wrestlers_out,
        }


def _get_eliminated(engine: NCAASeedBracketEngine) -> set:
    """Return set of wrestler IDs that have been eliminated (lost and have no further path)."""
    eliminated = set()
    for slot_id, result in engine.slot_results.items():
        loser = result.get("loser")
        if not loser:
            continue
        slot = engine.slots[slot_id]
        if slot.loser_to is None:
            eliminated.add(loser)
    return eliminated


# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------

def load_seed_model(path: Optional[Path] = None) -> dict:
    """Load seed_model.json."""
    if path is None:
        path = PROJECT_ROOT / "data" / "ncaa-tourney-parsed" / "seed_model.json"
    if not path.exists():
        print(f"ERROR: seed_model.json not found at {path}", file=sys.stderr)
        print("Run: python scripts/ncaa/build_ncaa_seed_model.py", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text())


def load_seeds_by_weight(year: int) -> Dict[int, Dict[int, dict]]:
    """
    Load wrestler seeds for a given year from seed files.

    Looks for: data/{year}/ncaa-tourney/seeds/{weight}.txt
    Format (one per line): "1. Name, School"

    Returns:
        {weight: {seed_int: {"name": str, "team": str}}}
    """
    seeds_dir = PROJECT_ROOT / "data" / str(year) / "ncaa-tourney" / "seeds"
    import re
    result = {}
    for weight in WEIGHTS:
        seed_file = seeds_dir / f"{weight}.txt"
        if not seed_file.exists():
            continue
        weight_seeds = {}
        for line in seed_file.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            # Skip header row
            if line.startswith("Seed") or line.lower().startswith("seed\t"):
                continue
            # Format: "3.\tAyala, Drake\tIowa\t\t23-4\tYes"  (tab-separated)
            parts = re.split(r'\t', line)
            if len(parts) < 2:
                continue
            seed_part = parts[0].strip().rstrip('.')
            try:
                seed_num = int(seed_part)
            except ValueError:
                continue
            name_raw = parts[1].strip() if len(parts) > 1 else ""
            team_raw = parts[2].strip() if len(parts) > 2 else "Unknown"
            # Name may be "Last, First" — normalize to "First Last"
            if "," in name_raw:
                name_parts = name_raw.split(",", 1)
                name = name_parts[1].strip() + " " + name_parts[0].strip()
            else:
                name = name_raw
            weight_seeds[seed_num] = {"name": name, "team": team_raw}
        result[weight] = weight_seeds
    return result


if __name__ == "__main__":
    # Quick sanity test with mock data
    model = load_seed_model()
    seeds_by_weight = {
        125: {i: {"name": f"Wrestler {i}", "team": f"Team {i % 10}"} for i in range(1, 34)}
    }
    eng = NCAATournamentEngine(model, seeds_by_weight)
    eng.run()
    totals = eng.get_team_totals()
    print("Mock test - top teams:")
    for team, pts in sorted(totals.items(), key=lambda x: -x[1])[:5]:
        print(f"  {team}: {pts:.2f}")
