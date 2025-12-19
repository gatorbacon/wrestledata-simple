"""
Deterministic bracket engine with probability mass propagation.

Propagates winners and losers through the bracket graph.
Supports probability mass tracking for bracket analysis.
"""

from typing import Dict, List, Optional
from xtp.engine.bracket_schema import Slot, get_all_slots
from xtp.engine.probability import compute_match_probabilities, compute_deterministic_match
from xtp.engine.scoring import advancement_points_for_slot, placement_points, expected_bonus_for_slot


class BracketEngine:
    """
    Deterministic bracket execution engine.
    
    Moves wrestler_ids through slots based on bracket wiring.
    """
    
    def __init__(
        self,
        slots: Dict[str, Slot],
        seeds: Dict[int, str],
        enable_probability: bool = True,
        rank_by_id: Optional[Dict[str, int]] = None,
        mv_by_id: Optional[Dict[str, float]] = None,
        bonus_ev_by_id: Optional[Dict[str, float]] = None
    ):
        """
        Initialize engine.
        
        Args:
            slots: All bracket slots (from bracket_schema.ALL_SLOTS)
            seeds: Mapping from seed number (1-33) to wrestler_id
            enable_probability: If True, track probability mass propagation
            rank_by_id: Optional dict mapping wrestler_id to rank (for Phase 4B)
            mv_by_id: Optional dict mapping wrestler_id to MV (for Phase 4B)
            bonus_ev_by_id: Optional dict mapping wrestler_id to shrunk bonus EV (for Phase 4B)
        """
        self.slots = slots
        self.seeds = seeds
        self.enable_probability = enable_probability
        
        # Phase 4B: Rank, MV, and bonus data
        self.rank_by_id = rank_by_id or {}
        self.mv_by_id = mv_by_id or {}
        self.bonus_ev_by_id = bonus_ev_by_id or {}
        
        # Track results for each slot
        # Format: {slot_id: {"winner": wrestler_id, "loser": wrestler_id}}
        self.slot_results: Dict[str, Dict[str, Optional[str]]] = {}
        
        # Track final placements (1-8)
        self.placements: Dict[int, str] = {}
        
        # Track which slots have been resolved
        self.resolved_slots: set = set()
        
        # Slot-centric probability model
        # Each slot has two incoming distributions (A_dist and B_dist)
        # Format: {slot_id: {"A": {wrestler_id: prob}, "B": {wrestler_id: prob}}}
        self.slot_input_dists: Dict[str, Dict[str, Dict[str, float]]] = {}
        
        # Slot-level probability distributions (outputs)
        # Format: {slot_id: {"winner": {wrestler_id: prob}, "loser": {wrestler_id: prob}}}
        self.slot_prob_results: Dict[str, Dict[str, Dict[str, float]]] = {}
        
        # Track which slots were resolved deterministically (via set_winner)
        self.deterministic_slots: set = set()
        
        # Initialize slot input distributions for seeds
        if self.enable_probability:
            # Initialize all slots with empty distributions
            for slot_id in self.slots:
                self.slot_input_dists[slot_id] = {"A": {}, "B": {}}
            
            # Initialize seeds as delta distributions
            for seed_num, wrestler_id in self.seeds.items():
                seed_ref = f"SEED_{seed_num}"
                # Find slots that use this seed as input
                for slot_id, slot in self.slots.items():
                    for i, input_ref in enumerate(slot.inputs):
                        if input_ref == seed_ref:
                            dist_key = "A" if i == 0 else "B"
                            self.slot_input_dists[slot_id][dist_key][wrestler_id] = 1.0
        
        # Expected points tracking
        # Format: {wrestler_id: expected_points}
        self.expected_adv_points: Dict[str, float] = {}
        self.expected_place_points: Dict[str, float] = {}
        self.expected_bonus_points: Dict[str, float] = {}
        
        # Track if expected points have been computed
        self._points_computed = False
    
    def _resolve_symbolic_reference(self, ref: str) -> Optional[str]:
        """
        Resolve a symbolic reference to a concrete wrestler_id.
        
        Examples:
            "SEED_1" -> seeds[1]
            "C_R32_0_WINNER" -> slot_results["C_R32_0"]["winner"]
            "C_R32_0_LOSER" -> slot_results["C_R32_0"]["loser"]
            "PIG_WINNER" -> slot_results["C_PIG_0"]["winner"]
        """
        # Handle SEED references
        if ref.startswith("SEED_"):
            seed_num = int(ref.split("_")[1])
            return self.seeds.get(seed_num)
        
        # Handle PIG_WINNER
        if ref == "PIG_WINNER":
            if "C_PIG_0" in self.slot_results:
                return self.slot_results["C_PIG_0"].get("winner")
            return None
        
        # Handle WINNER/LOSER references
        if "_WINNER" in ref or "_LOSER" in ref:
            base_slot_id = ref.rsplit("_", 1)[0]  # Remove _WINNER or _LOSER
            result_type = "winner" if "_WINNER" in ref else "loser"
            
            if base_slot_id in self.slot_results:
                return self.slot_results[base_slot_id].get(result_type)
            return None
        
        # Unknown reference type
        return None
    
    def get_slot_inputs(self, slot_id: str) -> List[Optional[str]]:
        """
        Get the two wrestler_ids currently feeding this slot.
        
        Returns:
            List of two wrestler_ids (or None if not resolved yet)
        """
        if slot_id not in self.slots:
            raise ValueError(f"Slot {slot_id} does not exist")
        
        slot = self.slots[slot_id]
        inputs = []
        
        for input_ref in slot.inputs:
            wrestler_id = self._resolve_symbolic_reference(input_ref)
            inputs.append(wrestler_id)
        
        return inputs
    
    def _propagate_result(self, slot_id: str, result_type: str, wrestler_id: str):
        """
        Propagate a result to downstream slots.
        
        Args:
            slot_id: Source slot
            result_type: "winner" or "loser"
            wrestler_id: Wrestler ID to propagate
        """
        slot = self.slots[slot_id]
        target_slot_id = slot.winner_to if result_type == "winner" else slot.loser_to
        
        if target_slot_id is None:
            return
        
        # Check if target is a PLACE_X terminal slot
        if target_slot_id.startswith("PLACE_"):
            try:
                place_num = int(target_slot_id.split("_")[1])
                self.placements[place_num] = wrestler_id
            except (ValueError, IndexError):
                pass
            return
        
        # For placement matches (CONS_3RD, CONS_5TH, CONS_7TH), set placements when they resolve
        # This is handled in set_winner when those slots are resolved
        # The propagation here is implicit - downstream slots will see the result via get_slot_inputs
    
    def _propagate_probability_mass_to_downstream(
        self,
        slot_id: str,
        winner_dist: Dict[str, float],
        loser_dist: Dict[str, float]
    ):
        """
        Propagate probability distributions to downstream slots.
        
        ADD distributions to downstream slot inputs (never subtract).
        
        Args:
            slot_id: Source slot
            winner_dist: Probability distribution for winners
            loser_dist: Probability distribution for losers
        """
        if not self.enable_probability:
            return
        
        slot = self.slots[slot_id]
        
        # Propagate winner distribution to winner_to slot
        if slot.winner_to:
            if slot.winner_to.startswith("PLACE_"):
                # Terminal placement - handled in compute_expected_points
                pass
            else:
                # Find which input of the downstream slot this feeds
                if slot.winner_to in self.slots:
                    downstream_slot = self.slots[slot.winner_to]
                    # Determine which input (A or B) this winner feeds
                    # This depends on the bracket wiring
                    self._add_dist_to_slot_input(slot.winner_to, winner_dist, slot_id, "winner")
        
        # Propagate loser distribution to loser_to slot
        if slot.loser_to:
            if slot.loser_to.startswith("PLACE_"):
                # Terminal placement - handled in compute_expected_points
                pass
            else:
                # Find which input of the downstream slot this feeds
                if slot.loser_to in self.slots:
                    self._add_dist_to_slot_input(slot.loser_to, loser_dist, slot_id, "loser")
    
    def _add_dist_to_slot_input(
        self,
        target_slot_id: str,
        dist: Dict[str, float],
        source_slot_id: str,
        source_type: str
    ):
        """
        Add a probability distribution to a slot's input (A or B).
        
        Determines which input (A or B) the source feeds based on bracket wiring.
        
        Args:
            target_slot_id: Target slot to add distribution to
            dist: Distribution to add (wrestler_id -> probability)
            source_slot_id: Source slot ID
            source_type: "winner" or "loser"
        """
        if target_slot_id not in self.slots:
            return
        
        target_slot = self.slots[target_slot_id]
        
        # Determine which input (A or B) this source feeds
        # Check if target slot's inputs reference the source
        input_index = None
        for i, input_ref in enumerate(target_slot.inputs):
            # Check if this input references the source slot
            if f"{source_slot_id}_WINNER" == input_ref and source_type == "winner":
                input_index = i
                break
            elif f"{source_slot_id}_LOSER" == input_ref and source_type == "loser":
                input_index = i
                break
            # Also check for PIG_WINNER special case
            if source_slot_id == "C_PIG_0" and input_ref == "PIG_WINNER" and source_type == "winner":
                input_index = i
                break
        
        if input_index is None:
            # Try to infer from bracket structure
            # For now, default to A if index 0, B if index 1
            # This is a fallback - ideally all references should be explicit
            pass
        
        # Add distribution to the appropriate input
        dist_key = "A" if input_index == 0 else "B"
        
        # ADD to existing distribution (never subtract)
        for wrestler_id, prob in dist.items():
            if prob > 0.0:
                self.slot_input_dists[target_slot_id][dist_key][wrestler_id] = \
                    self.slot_input_dists[target_slot_id][dist_key].get(wrestler_id, 0.0) + prob
    
    def _resolve_slot_probabilities(self, slot_id: str, is_deterministic: bool = False):
        """
        Resolve probability distributions for a slot using slot-centric model.
        
        Computes cross-product of A_dist and B_dist to get winner_dist and loser_dist.
        
        Args:
            slot_id: Slot to resolve
            is_deterministic: If True, use deterministic override (100% to winner)
        """
        if not self.enable_probability:
            return
        
        slot = self.slots[slot_id]
        A_dist = self.slot_input_dists[slot_id]["A"]
        B_dist = self.slot_input_dists[slot_id]["B"]
        
        # Skip if either distribution is empty
        if not A_dist or not B_dist:
            return
        
        if is_deterministic and slot_id in self.slot_results:
            # Deterministic override: winner gets 100% of combined mass
            winner_id = self.slot_results[slot_id]["winner"]
            loser_id = self.slot_results[slot_id]["loser"]
            
            # Total mass from both distributions
            total_mass = sum(A_dist.values()) + sum(B_dist.values())
            
            winner_dist = {winner_id: total_mass}
            loser_dist = {loser_id: 0.0}
        else:
            # Probabilistic resolution: cross-product computation
            winner_dist: Dict[str, float] = {}
            loser_dist: Dict[str, float] = {}
            
            # Cross-product: for each a in A_dist, for each b in B_dist
            for wrestler_a, prob_a in A_dist.items():
                for wrestler_b, prob_b in B_dist.items():
                    Ppair = prob_a * prob_b
                    
                    if Ppair == 0.0:
                        continue
                    
                    # Get win probability
                    rank_a = self.rank_by_id.get(wrestler_a)
                    rank_b = self.rank_by_id.get(wrestler_b)
                    mv_a = self.mv_by_id.get(wrestler_a, 0.0)
                    mv_b = self.mv_by_id.get(wrestler_b, 0.0)
                    
                    from xtp.engine.probability import compute_win_probability
                    p_a_wins = compute_win_probability(rank_a, rank_b, mv_a, mv_b)
                    p_b_wins = 1.0 - p_a_wins
                    
                    # Add to winner distribution
                    winner_dist[wrestler_a] = winner_dist.get(wrestler_a, 0.0) + Ppair * p_a_wins
                    winner_dist[wrestler_b] = winner_dist.get(wrestler_b, 0.0) + Ppair * p_b_wins
                    
                    # Add to loser distribution
                    loser_dist[wrestler_a] = loser_dist.get(wrestler_a, 0.0) + Ppair * p_b_wins
                    loser_dist[wrestler_b] = loser_dist.get(wrestler_b, 0.0) + Ppair * p_a_wins
        
        # Store slot probability results
        self.slot_prob_results[slot_id] = {
            "winner": winner_dist,
            "loser": loser_dist
        }
        
        # Propagate to downstream slots by ADDING distributions
        self._propagate_probability_mass_to_downstream(slot_id, winner_dist, loser_dist)
    
    def set_winner(self, slot_id: str, winner_id: str):
        """
        Set the winner for a slot and propagate results.
        
        Args:
            slot_id: Slot to resolve
            winner_id: Wrestler ID of the winner
        
        Raises:
            ValueError: If slot doesn't exist, winner not in inputs, or slot already resolved
        """
        if slot_id not in self.slots:
            raise ValueError(f"Slot {slot_id} does not exist")
        
        if slot_id in self.resolved_slots:
            raise ValueError(f"Slot {slot_id} has already been resolved")
        
        # Get current inputs
        inputs = self.get_slot_inputs(slot_id)
        
        # Verify winner is one of the inputs
        if winner_id not in inputs:
            raise ValueError(
                f"Winner {winner_id} not in inputs for {slot_id}. "
                f"Inputs: {inputs}"
            )
        
        # Verify both inputs are resolved
        if None in inputs:
            unresolved = [ref for ref, wid in zip(self.slots[slot_id].inputs, inputs) if wid is None]
            raise ValueError(
                f"Cannot resolve {slot_id}: inputs not ready. "
                f"Unresolved: {unresolved}"
            )
        
        # Infer loser
        loser_id = inputs[1] if inputs[0] == winner_id else inputs[0]
        
        # Store result
        self.slot_results[slot_id] = {
            "winner": winner_id,
            "loser": loser_id
        }
        self.resolved_slots.add(slot_id)
        self.deterministic_slots.add(slot_id)  # Mark as deterministic override
        
        # Handle probability mass for deterministic override
        if self.enable_probability:
            self._resolve_slot_probabilities(slot_id, is_deterministic=True)
        
        # Handle placement matches directly
        if slot_id == "CONS_3RD":
            self.placements[3] = winner_id
            self.placements[4] = loser_id
        elif slot_id == "CONS_5TH":
            self.placements[5] = winner_id
            self.placements[6] = loser_id
        elif slot_id == "CONS_7TH":
            self.placements[7] = winner_id
            self.placements[8] = loser_id
        elif slot_id == "C_F_0":
            self.placements[1] = winner_id
            self.placements[2] = loser_id
        
        # Propagate to downstream slots
        slot = self.slots[slot_id]
        if slot.winner_to:
            self._propagate_result(slot_id, "winner", winner_id)
        if slot.loser_to:
            self._propagate_result(slot_id, "loser", loser_id)
        
        # After propagation, check if downstream slots can now resolve probabilistically
        if self.enable_probability:
            self._check_and_resolve_downstream_probabilities(slot_id)
    
    def _get_slot_dependencies(self, slot_id: str) -> List[str]:
        """
        Get all slots that must be resolved before this slot can be resolved.
        
        Returns:
            List of slot IDs that are dependencies
        """
        dependencies = []
        slot = self.slots[slot_id]
        
        for input_ref in slot.inputs:
            # Handle SEED references (no dependency)
            if input_ref.startswith("SEED_"):
                continue
            
            # Handle PIG_WINNER
            if input_ref == "PIG_WINNER":
                dependencies.append("C_PIG_0")
                continue
            
            # Handle WINNER/LOSER references
            if "_WINNER" in input_ref or "_LOSER" in input_ref:
                base_slot_id = input_ref.rsplit("_", 1)[0]
                if base_slot_id in self.slots:
                    dependencies.append(base_slot_id)
        
        return dependencies
    
    def _topological_sort_overrides(self, overrides: Dict[str, str]) -> List[tuple]:
        """
        Sort overrides by bracket dependency order.
        
        Returns:
            List of (slot_id, winner_id) tuples in dependency order
        """
        # Build dependency graph
        remaining = set(overrides.keys())
        result = []
        
        while remaining:
            # Find slots with no unresolved dependencies
            ready = []
            for slot_id in remaining:
                deps = self._get_slot_dependencies(slot_id)
                # Filter to only dependencies that are in overrides
                unresolved_deps = [d for d in deps if d in remaining]
                if not unresolved_deps:
                    ready.append(slot_id)
            
            if not ready:
                # Circular dependency or missing dependency
                raise ValueError(
                    f"Cannot resolve dependencies for overrides. "
                    f"Remaining: {remaining}"
                )
            
            # Add ready slots to result
            for slot_id in ready:
                result.append((slot_id, overrides[slot_id]))
                remaining.remove(slot_id)
        
        return result
    
    def resolve_all_overrides(self, overrides: Dict[str, str]):
        """
        Apply all overrides in dependency order.
        
        Args:
            overrides: Dict mapping slot_id -> winner_id
        
        Raises:
            ValueError: If dependencies cannot be resolved
        """
        sorted_overrides = self._topological_sort_overrides(overrides)
        
        for slot_id, winner_id in sorted_overrides:
            self.set_winner(slot_id, winner_id)
    
    def get_placements(self) -> Dict[int, str]:
        """
        Get final placements (1-8).
        
        Returns:
            Dict mapping placement (1-8) to wrestler_id
        """
        return self.placements.copy()
    
    def get_prob_mass(self) -> Dict[str, float]:
        """
        Get current probability mass per wrestler.
        
        Returns:
            Dict mapping wrestler_id to probability mass
        """
        if not self.enable_probability:
            return {}
        return self.prob_mass.copy()
    
    def get_slot_probabilities(self, slot_id: str) -> Dict:
        """
        Get probability distributions for a slot.
        
        Returns:
            Dict with "winner" and "loser" keys, each mapping to
            {wrestler_id: probability}
        """
        if not self.enable_probability:
            return {"winner": {}, "loser": {}}
        
        if slot_id not in self.slot_prob_results:
            return {"winner": {}, "loser": {}}
        
        return self.slot_prob_results[slot_id].copy()
    
    def compute_expected_points(self):
        """
        Compute expected advancement, placement, and bonus points for all wrestlers.
        
        Iterates through all resolved slots and computes:
        - Expected advancement points from slot wins
        - Expected placement points from final placements
        - Expected bonus points (0.0 in Phase 4A)
        """
        # Reset expected points
        all_wrestlers = set(self.seeds.values())
        self.expected_adv_points = {w: 0.0 for w in all_wrestlers}
        self.expected_place_points = {w: 0.0 for w in all_wrestlers}
        self.expected_bonus_points = {w: 0.0 for w in all_wrestlers}
        
        if not self.enable_probability:
            self._points_computed = True
            return
        
        # Compute advancement points from resolved slots
        for slot_id in self.resolved_slots:
            slot = self.slots[slot_id]
            
            # Skip placement matches (they don't give advancement points)
            if slot.round == "PLACE" and slot.id.startswith(("CONS_3RD", "CONS_5TH", "CONS_7TH")):
                continue
            
            # Advancement points for winning this slot
            adv_points = advancement_points_for_slot(slot)
            
            if adv_points == 0.0:
                continue
            
            # Get probability of winning this slot
            is_deterministic = slot_id in self.deterministic_slots
            
            if is_deterministic and slot_id in self.slot_results:
                # Deterministic: winner has probability 1.0
                winner_id = self.slot_results[slot_id].get("winner")
                if winner_id:
                    self.expected_adv_points[winner_id] = \
                        self.expected_adv_points.get(winner_id, 0.0) + (1.0 * adv_points)
            elif slot_id in self.slot_prob_results:
                # Probabilistic: use probability distribution
                winner_dist = self.slot_prob_results[slot_id].get("winner", {})
                
                # Normalize probabilities (they should sum to the total mass that entered this slot)
                total_prob = sum(winner_dist.values())
                
                if total_prob > 0.0:
                    # Normalize to get actual probabilities
                    for wrestler_id, mass in winner_dist.items():
                        if mass > 0.0:
                            prob = mass / total_prob
                            self.expected_adv_points[wrestler_id] = \
                                self.expected_adv_points.get(wrestler_id, 0.0) + (prob * adv_points)
            
            # Compute bonus points (Phase 4B: real model)
            # In slot-centric model, we need to look at the input distributions to find all possible matchups
            if slot_id in self.slot_prob_results and slot_id in self.slot_input_dists:
                A_dist = self.slot_input_dists[slot_id]["A"]
                B_dist = self.slot_input_dists[slot_id]["B"]
                winner_dist = self.slot_prob_results[slot_id].get("winner", {})
                loser_dist = self.slot_prob_results[slot_id].get("loser", {})
                total_prob = sum(winner_dist.values())
                
                if total_prob > 0.0:
                    # For each potential winner, compute expected bonus across all possible opponents
                    for wrestler_id, winner_mass in winner_dist.items():
                        if winner_mass <= 0.0:
                            continue
                        
                        # Probability of winning this slot
                        p_win_slot = winner_mass / total_prob
                        
                        # Get wrestler's bonus EV
                        bonus_ev = self.bonus_ev_by_id.get(wrestler_id, 0.0)
                        
                        if bonus_ev <= 0.0:
                            continue
                        
                        # Find all possible opponents and compute weighted average bonus
                        # Opponents come from the input distributions
                        total_bonus = 0.0
                        total_opponent_prob = 0.0
                        
                        # Check all possible opponents in A_dist and B_dist
                        all_opponents = set()
                        if wrestler_id in A_dist:
                            all_opponents.update(B_dist.keys())
                        if wrestler_id in B_dist:
                            all_opponents.update(A_dist.keys())
                        
                        # Remove self
                        all_opponents.discard(wrestler_id)
                        
                        # For each possible opponent, compute weighted bonus
                        for opponent_id in all_opponents:
                            # Get probability of this matchup occurring
                            prob_a = A_dist.get(wrestler_id, 0.0) if wrestler_id in A_dist else 0.0
                            prob_b = B_dist.get(opponent_id, 0.0) if opponent_id in B_dist else 0.0
                            
                            if prob_a > 0.0 and prob_b > 0.0:
                                matchup_prob = prob_a * prob_b
                            else:
                                prob_a = A_dist.get(opponent_id, 0.0) if opponent_id in A_dist else 0.0
                                prob_b = B_dist.get(wrestler_id, 0.0) if wrestler_id in B_dist else 0.0
                                matchup_prob = prob_a * prob_b
                            
                            if matchup_prob <= 0.0:
                                continue
                            
                            # Get opponent rank for multiplier
                            opponent_rank = self.rank_by_id.get(opponent_id)
                            
                            # Compute probability of winning this specific matchup
                            rank_a = self.rank_by_id.get(wrestler_id)
                            rank_b = self.rank_by_id.get(opponent_id)
                            mv_a = self.mv_by_id.get(wrestler_id, 0.0)
                            mv_b = self.mv_by_id.get(opponent_id, 0.0)
                            
                            from xtp.engine.probability import compute_win_probability
                            p_win_matchup = compute_win_probability(rank_a, rank_b, mv_a, mv_b)
                            
                            # Compute expected bonus for this matchup
                            # Expected bonus = P(win matchup) * bonus_ev * opponent_multiplier
                            expected_bonus = expected_bonus_for_slot(
                                slot,
                                wrestler_id,
                                opponent_id,
                                p_win_matchup,
                                bonus_ev,
                                opponent_rank
                            )
                            
                            # Weight by probability of this matchup occurring
                            # The expected bonus is already weighted by p_win_matchup inside expected_bonus_for_slot
                            # So we just need to weight by matchup probability
                            total_bonus += matchup_prob * expected_bonus
                            total_opponent_prob += matchup_prob
                        
                        # Add total bonus (already weighted by matchup probabilities)
                        # This is the expected bonus for winning this slot, summed across all possible opponents
                        if total_bonus > 0.0:
                            self.expected_bonus_points[wrestler_id] = \
                                self.expected_bonus_points.get(wrestler_id, 0.0) + total_bonus
        
        # Compute placement points from final placements
        # For deterministic placements, probability is 1.0 for the placed wrestler
        # For probabilistic placements, use probability distributions
        
        # Check placement matches (CONS_3RD, CONS_5TH, CONS_7TH) and final (C_F_0)
        placement_slots = {
            "C_F_0": [(1, "winner"), (2, "loser")],
            "CONS_3RD": [(3, "winner"), (4, "loser")],
            "CONS_5TH": [(5, "winner"), (6, "loser")],
            "CONS_7TH": [(7, "winner"), (8, "loser")]
        }
        
        for slot_id, placements_info in placement_slots.items():
            if slot_id not in self.resolved_slots:
                continue
            
            slot = self.slots[slot_id]
            is_deterministic = slot_id in self.deterministic_slots
            
            for place, result_type in placements_info:
                place_pts = placement_points(place)
                
                if is_deterministic and slot_id in self.slot_results:
                    # Deterministic: wrestler has probability 1.0
                    wrestler_id = self.slot_results[slot_id].get(result_type)
                    if wrestler_id:
                        self.expected_place_points[wrestler_id] = \
                            self.expected_place_points.get(wrestler_id, 0.0) + (1.0 * place_pts)
                elif slot_id in self.slot_prob_results:
                    # Probabilistic: use probability distribution
                    dist = self.slot_prob_results[slot_id].get(result_type, {})
                    total_prob = sum(dist.values())
                    
                    if total_prob > 0.0:
                        # Normalize to get actual probabilities
                        for wrestler_id, mass in dist.items():
                            if mass > 0.0:
                                prob = mass / total_prob
                                self.expected_place_points[wrestler_id] = \
                                    self.expected_place_points.get(wrestler_id, 0.0) + (prob * place_pts)
        
        self._points_computed = True
    
    def get_xtp(self) -> Dict[str, float]:
        """
        Get xTP (expected Tournament Points) for all wrestlers.
        
        xTP = xTP_A + xTP_P + xTP_B
        
        Returns:
            Dict mapping wrestler_id to xTP
        """
        # Compute points if not already computed
        if not self._points_computed:
            self.compute_expected_points()
        
        # Combine all expected points
        xtp = {}
        all_wrestlers = set(self.seeds.values())
        
        for wrestler_id in all_wrestlers:
            adv = self.expected_adv_points.get(wrestler_id, 0.0)
            place = self.expected_place_points.get(wrestler_id, 0.0)
            bonus = self.expected_bonus_points.get(wrestler_id, 0.0)
            xtp[wrestler_id] = adv + place + bonus
        
        return xtp
    
    def get_placement_probabilities(self) -> Dict[str, Dict[str, float]]:
        """
        Extract placement probabilities (AA, Champion, Finalist) from terminal placement slots.
        
        Uses probability mass already computed in slot_prob_results for placement matches.
        This is a pure aggregation step - no new probabilities are computed.
        
        Returns:
            Dict mapping wrestler_id to {
                "aa_probability": float,        # Top 8 (placements 1-8)
                "champion_probability": float,   # Placement 1
                "finalist_probability": float    # Placements 1-2
            }
        """
        if not self.enable_probability:
            return {}
        
        # Mapping of placement slots to their placement numbers
        # Format: {slot_id: [(placement_num, result_type), ...]}
        placement_slots = {
            "C_F_0": [(1, "winner"), (2, "loser")],
            "CONS_3RD": [(3, "winner"), (4, "loser")],
            "CONS_5TH": [(5, "winner"), (6, "loser")],
            "CONS_7TH": [(7, "winner"), (8, "loser")]
        }
        
        # Initialize probability dictionaries for all wrestlers
        all_wrestlers = set(self.seeds.values())
        placement_probs = {wrestler_id: {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0, 7: 0.0, 8: 0.0}
                           for wrestler_id in all_wrestlers}
        
        # Extract probability mass from each placement slot
        for slot_id, placements_info in placement_slots.items():
            if slot_id not in self.resolved_slots:
                continue
            
            slot = self.slots[slot_id]
            is_deterministic = slot_id in self.deterministic_slots
            
            for place, result_type in placements_info:
                if is_deterministic and slot_id in self.slot_results:
                    # Deterministic: wrestler has probability 1.0
                    wrestler_id = self.slot_results[slot_id].get(result_type)
                    if wrestler_id and wrestler_id in all_wrestlers:
                        placement_probs[wrestler_id][place] = 1.0
                elif slot_id in self.slot_prob_results:
                    # Probabilistic: use probability distribution
                    dist = self.slot_prob_results[slot_id].get(result_type, {})
                    total_mass = sum(dist.values())
                    
                    if total_mass > 0.0:
                        # Normalize to get actual probabilities
                        for wrestler_id, mass in dist.items():
                            if wrestler_id in all_wrestlers and mass > 0.0:
                                prob = mass / total_mass
                                placement_probs[wrestler_id][place] = prob
        
        # Aggregate into AA, Champion, and Finalist probabilities
        result = {}
        for wrestler_id in all_wrestlers:
            probs = placement_probs[wrestler_id]
            
            # Champion probability = placement 1
            champ_prob = probs[1]
            
            # Finalist probability = placements 1 + 2
            final_prob = probs[1] + probs[2]
            
            # All-American probability = placements 1-8
            aa_prob = sum(probs[i] for i in range(1, 9))
            
            result[wrestler_id] = {
                "aa_probability": aa_prob,
                "champion_probability": champ_prob,
                "finalist_probability": final_prob
            }
        
        # Validation checks
        total_champ_prob = sum(r["champion_probability"] for r in result.values())
        total_aa_prob = sum(r["aa_probability"] for r in result.values())
        
        # Champion probabilities should sum to ~1.0 (one champion)
        if abs(total_champ_prob - 1.0) > 0.01:
            raise ValueError(
                f"Champion probability mass conservation violated: "
                f"sum={total_champ_prob:.6f}, expected ~1.0"
            )
        
        # AA probabilities should sum to ~8.0 (8 All-Americans)
        if abs(total_aa_prob - 8.0) > 0.1:
            raise ValueError(
                f"All-American probability mass conservation violated: "
                f"sum={total_aa_prob:.6f}, expected ~8.0"
            )
        
        # Validate ordering: champ_prob <= finalist_prob <= aa_prob
        for wrestler_id, probs in result.items():
            champ = probs["champion_probability"]
            final = probs["finalist_probability"]
            aa = probs["aa_probability"]
            
            if champ > final + 1e-6:
                raise ValueError(
                    f"Invalid probability ordering for {wrestler_id}: "
                    f"champ_prob ({champ:.6f}) > finalist_prob ({final:.6f})"
                )
            if final > aa + 1e-6:
                raise ValueError(
                    f"Invalid probability ordering for {wrestler_id}: "
                    f"finalist_prob ({final:.6f}) > aa_prob ({aa:.6f})"
                )
        
        return result
    
    def get_xtp_components(self) -> Dict[str, Dict[str, float]]:
        """
        Get xTP components separately for all wrestlers.
        
        Returns:
            Dict mapping wrestler_id to {
                "xTP_A": float,
                "xTP_P": float,
                "xTP_B": float,
                "xTP": float,
                "aa_probability": float,
                "champion_probability": float,
                "finalist_probability": float
            }
        """
        # Compute points if not already computed
        if not self._points_computed:
            self.compute_expected_points()
        
        # Get placement probabilities
        placement_probs = self.get_placement_probabilities()
        
        components = {}
        all_wrestlers = set(self.seeds.values())
        
        for wrestler_id in all_wrestlers:
            xTP_A = self.expected_adv_points.get(wrestler_id, 0.0)
            xTP_P = self.expected_place_points.get(wrestler_id, 0.0)
            xTP_B = self.expected_bonus_points.get(wrestler_id, 0.0)
            xTP = xTP_A + xTP_P + xTP_B
            
            # Get placement probabilities (default to 0.0 if not found)
            probs = placement_probs.get(wrestler_id, {
                "aa_probability": 0.0,
                "champion_probability": 0.0,
                "finalist_probability": 0.0
            })
            
            components[wrestler_id] = {
                "xTP_A": xTP_A,
                "xTP_P": xTP_P,
                "xTP_B": xTP_B,
                "xTP": xTP,
                "aa_probability": probs["aa_probability"],
                "champion_probability": probs["champion_probability"],
                "finalist_probability": probs["finalist_probability"]
            }
        
        return components
    
    def _check_and_resolve_downstream_probabilities(self, resolved_slot_id: str):
        """
        Check if any downstream slots can now resolve probabilistically.
        
        Args:
            resolved_slot_id: Slot that was just resolved
        """
        if not self.enable_probability:
            return
        
        slot = self.slots[resolved_slot_id]
        
        # Check winner_to slot
        if slot.winner_to and not slot.winner_to.startswith("PLACE_"):
            if slot.winner_to in self.slots:
                downstream_slot_id = slot.winner_to
                A_dist = self.slot_input_dists[downstream_slot_id]["A"]
                B_dist = self.slot_input_dists[downstream_slot_id]["B"]
                
                # Check if both inputs are ready
                if A_dist and B_dist:
                    if downstream_slot_id not in self.resolved_slots:
                        if downstream_slot_id not in self.deterministic_slots:
                            try:
                                self._resolve_slot_probabilities(downstream_slot_id, is_deterministic=False)
                                if downstream_slot_id in self.slot_prob_results:
                                    self.resolved_slots.add(downstream_slot_id)
                                    # Recursively check downstream
                                    self._check_and_resolve_downstream_probabilities(downstream_slot_id)
                            except Exception:
                                pass
        
        # Check loser_to slot
        if slot.loser_to and not slot.loser_to.startswith("PLACE_"):
            if slot.loser_to in self.slots:
                downstream_slot_id = slot.loser_to
                A_dist = self.slot_input_dists[downstream_slot_id]["A"]
                B_dist = self.slot_input_dists[downstream_slot_id]["B"]
                
                # Check if both inputs are ready
                if A_dist and B_dist:
                    if downstream_slot_id not in self.resolved_slots:
                        if downstream_slot_id not in self.deterministic_slots:
                            try:
                                self._resolve_slot_probabilities(downstream_slot_id, is_deterministic=False)
                                if downstream_slot_id in self.slot_prob_results:
                                    self.resolved_slots.add(downstream_slot_id)
                                    # Recursively check downstream
                                    self._check_and_resolve_downstream_probabilities(downstream_slot_id)
                            except Exception:
                                pass
    
    def resolve_all_probabilistically(self, max_iterations: int = 100, epsilon: float = 1e-9):
        """
        Resolve all slots probabilistically until convergence.
        
        Iterates until no slot probability distributions change beyond epsilon,
        or max_iterations is reached.
        
        Args:
            max_iterations: Maximum number of iterations (safety guard)
            epsilon: Convergence threshold for probability changes
        
        Raises:
            RuntimeError: If resolution doesn't converge within max_iterations
        """
        if not self.enable_probability:
            return
        
        iteration = 0
        last_resolved_count = 0
        
        while iteration < max_iterations:
            iteration += 1
            slots_resolved_this_iteration = 0
            
            # Try to resolve each unresolved slot
            for slot_id, slot in self.slots.items():
                # Skip if already resolved
                if slot_id in self.resolved_slots:
                    continue
                if slot_id in self.slot_prob_results:
                    # Already has probability results, mark as resolved
                    self.resolved_slots.add(slot_id)
                    continue
                
                # Skip if deterministically resolved
                if slot_id in self.deterministic_slots:
                    self.resolved_slots.add(slot_id)
                    continue
                
                # Check if both input distributions are non-empty
                A_dist = self.slot_input_dists[slot_id]["A"]
                B_dist = self.slot_input_dists[slot_id]["B"]
                
                if not A_dist or not B_dist:
                    continue
                
                # Both inputs have distributions - try to resolve
                try:
                    # Get snapshot before resolution to check for changes
                    before_winner = self.slot_prob_results.get(slot_id, {}).get("winner", {})
                    before_loser = self.slot_prob_results.get(slot_id, {}).get("loser", {})
                    
                    # Resolve the slot
                    self._resolve_slot_probabilities(slot_id, is_deterministic=False)
                    
                    # Check if resolution succeeded
                    if slot_id in self.slot_prob_results:
                        after_winner = self.slot_prob_results[slot_id].get("winner", {})
                        after_loser = self.slot_prob_results[slot_id].get("loser", {})
                        
                        # Check if distributions changed
                        if self._distributions_changed(before_winner, after_winner, epsilon) or \
                           self._distributions_changed(before_loser, after_loser, epsilon):
                            changed = True
                        
                        # Mark as resolved
                        self.resolved_slots.add(slot_id)
                        slots_resolved_this_iteration += 1
                        
                        # Propagate to downstream slots
                        self._check_and_resolve_downstream_probabilities(slot_id)
                except Exception as e:
                    # Slot might not be ready yet, continue
                    continue
            
            # Check convergence: if no changes and no new slots resolved, we're done
            if not changed and slots_resolved_this_iteration == 0:
                # Check if there are any unresolved slots that could be resolved
                can_resolve_more = False
                for slot_id in self.slots:
                    if slot_id in self.resolved_slots:
                        continue
                    if slot_id in self.deterministic_slots:
                        continue
                    
                    A_dist = self.slot_input_dists[slot_id]["A"]
                    B_dist = self.slot_input_dists[slot_id]["B"]
                    
                    if A_dist and B_dist:
                        can_resolve_more = True
                        break
                
                if not can_resolve_more:
                    # No more slots can be resolved
                    break
            
            last_resolved_count = len(self.resolved_slots)
        
        # Mark all slots with probability results as resolved
        for slot_id in self.slot_prob_results:
            self.resolved_slots.add(slot_id)
        
        # Filter out PLACE_* terminals (they're not actual slots, just references)
        actual_unresolved = [
            s for s in self.slots 
            if s not in self.resolved_slots and not s.startswith("PLACE_")
        ]
        
        if iteration >= max_iterations and actual_unresolved:
            # Debug output
            debug_info = []
            for slot_id in actual_unresolved[:20]:  # Limit to first 20
                A_dist = self.slot_input_dists.get(slot_id, {}).get("A", {})
                B_dist = self.slot_input_dists.get(slot_id, {}).get("B", {})
                slot = self.slots[slot_id]
                debug_info.append(
                    f"  {slot_id}: A_empty={not A_dist}, B_empty={not B_dist}, "
                    f"inputs={slot.inputs}"
                )
            
            raise RuntimeError(
                f"Bracket resolution did not converge after {max_iterations} iterations. "
                f"{len(actual_unresolved)} slots unresolved:\n" + "\n".join(debug_info)
            )
    
    def _distributions_changed(
        self,
        before: Dict[str, float],
        after: Dict[str, float],
        epsilon: float
    ) -> bool:
        """
        Check if two probability distributions differ beyond epsilon.
        
        Args:
            before: Distribution before
            after: Distribution after
            epsilon: Threshold for change
        
        Returns:
            True if distributions changed significantly
        """
        # If before is empty, any after is a change
        if not before:
            return bool(after)
        
        # Check if any wrestler's probability changed
        all_wrestlers = set(before.keys()) | set(after.keys())
        
        for wrestler_id in all_wrestlers:
            prob_before = before.get(wrestler_id, 0.0)
            prob_after = after.get(wrestler_id, 0.0)
            
            if abs(prob_after - prob_before) > epsilon:
                return True
        
        return False
    
    def _try_resolve_slot_probabilities(self, slot_id: str):
        """
        Try to resolve a slot probabilistically if both inputs are ready.
        
        Only resolves if the slot hasn't been and won't be resolved deterministically.
        
        Args:
            slot_id: Slot to check
        """
        if not self.enable_probability:
            return
        
        # Skip if already resolved deterministically
        if slot_id in self.deterministic_slots:
            return
        
        # Skip if already resolved probabilistically
        if slot_id in self.slot_prob_results:
            return
        
        # Skip if slot is already in resolved_slots (means it was resolved deterministically)
        if slot_id in self.resolved_slots:
            return
        
        inputs = self.get_slot_inputs(slot_id)
        
        # Check if both inputs are ready
        if None in inputs or len(inputs) != 2:
            return
        
        # Both inputs ready - but don't auto-resolve probabilistically
        # Only resolve if explicitly requested (for now, we'll let deterministic resolution handle it)
        # This prevents premature probabilistic resolution that removes mass
        pass

