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
    
    def __init__(self, slots: Dict[str, Slot], seeds: Dict[int, str], enable_probability: bool = True):
        """
        Initialize engine.
        
        Args:
            slots: All bracket slots (from bracket_schema.ALL_SLOTS)
            seeds: Mapping from seed number (1-33) to wrestler_id
            enable_probability: If True, track probability mass propagation
        """
        self.slots = slots
        self.seeds = seeds
        self.enable_probability = enable_probability
        
        # Track results for each slot
        # Format: {slot_id: {"winner": wrestler_id, "loser": wrestler_id}}
        self.slot_results: Dict[str, Dict[str, Optional[str]]] = {}
        
        # Track final placements (1-8)
        self.placements: Dict[int, str] = {}
        
        # Track which slots have been resolved
        self.resolved_slots: set = set()
        
        # Probability mass tracking
        # Format: {wrestler_id: probability_mass}
        self.prob_mass: Dict[str, float] = {}
        
        # Slot-level probability distributions
        # Format: {slot_id: {"winner": {wrestler_id: prob}, "loser": {wrestler_id: prob}}}
        self.slot_prob_results: Dict[str, Dict[str, Dict[str, float]]] = {}
        
        # Track which slots were resolved deterministically (via set_winner)
        self.deterministic_slots: set = set()
        
        # Initialize probability mass for all seeded wrestlers
        if self.enable_probability:
            for wrestler_id in self.seeds.values():
                self.prob_mass[wrestler_id] = 1.0
        
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
        Propagate probability mass to downstream slots.
        
        Mass flows to downstream slots based on distributions.
        For deterministic resolutions, only the actual winner/loser get mass.
        
        Args:
            slot_id: Source slot
            winner_dist: Probability distribution for winners
            loser_dist: Probability distribution for losers
        """
        if not self.enable_probability:
            return
        
        slot = self.slots[slot_id]
        is_deterministic = slot_id in self.deterministic_slots
        
        # Propagate winner mass to winner_to
        if slot.winner_to:
            if is_deterministic and slot_id in self.slot_results:
                # Deterministic: only the actual winner gets mass
                winner_id = self.slot_results[slot_id]["winner"]
                winner_mass = sum(winner_dist.values())
                # Create a distribution with only the winner
                deterministic_winner_dist = {winner_id: winner_mass}
                self._add_mass_to_slot(slot.winner_to, deterministic_winner_dist)
            else:
                # Probabilistic: distribute according to winner_dist
                self._add_mass_to_slot(slot.winner_to, winner_dist)
        
        # Propagate loser mass to loser_to
        if slot.loser_to:
            if is_deterministic and slot_id in self.slot_results:
                # Deterministic: loser gets 0 mass (already handled in compute_deterministic_match)
                # But we still need to propagate (with 0 mass)
                loser_id = self.slot_results[slot_id]["loser"]
                deterministic_loser_dist = {loser_id: 0.0}
                self._add_mass_to_slot(slot.loser_to, deterministic_loser_dist)
            else:
                # Probabilistic: distribute according to loser_dist
                self._add_mass_to_slot(slot.loser_to, loser_dist)
    
    def _add_mass_to_slot(self, target_slot_id: str, mass_dist: Dict[str, float]):
        """
        Add probability mass to a target slot.
        
        Distributes mass to wrestlers that can reach the target slot.
        Mass is added immediately to wrestlers in the target slot's inputs.
        
        Args:
            target_slot_id: Target slot to add mass to
            mass_dist: Distribution of mass to add (wrestler_id -> probability)
        """
        if target_slot_id.startswith("PLACE_"):
            # Terminal placement - mass is recorded but placements are deterministic
            # For placements, we track mass in slot_prob_results
            return
        
        # Get target slot inputs (may include None if not ready)
        target_inputs = self.get_slot_inputs(target_slot_id)
        
        total_mass = sum(mass_dist.values())
        
        if total_mass == 0.0:
            return
        
        # Distribute mass to wrestlers in the target slot's inputs
        # For deterministic resolution, only one wrestler in mass_dist has mass
        # For probabilistic, both wrestlers have mass
        
        for wrestler_id, prob in mass_dist.items():
            if prob > 0.0:
                # This wrestler has mass to distribute
                # Always add it to the wrestler - they'll use it when target slot resolves
                # Even if target slot inputs aren't ready yet, the wrestler needs the mass
                self.prob_mass[wrestler_id] = self.prob_mass.get(wrestler_id, 0.0) + prob
    
    def _resolve_slot_probabilities(self, slot_id: str, is_deterministic: bool = False):
        """
        Resolve probability distributions for a slot when both inputs are known.
        
        Args:
            slot_id: Slot to resolve
            is_deterministic: If True, use deterministic override (100% to winner)
        """
        if not self.enable_probability:
            return
        
        inputs = self.get_slot_inputs(slot_id)
        
        # Skip if inputs not ready
        if None in inputs or len(inputs) != 2:
            return
        
        wrestler_a, wrestler_b = inputs[0], inputs[1]
        
        # Get current probability mass
        prob_mass_a = self.prob_mass.get(wrestler_a, 0.0)
        prob_mass_b = self.prob_mass.get(wrestler_b, 0.0)
        
        if is_deterministic and slot_id in self.slot_results:
            # Deterministic override: winner gets 100% of combined mass
            winner_id = self.slot_results[slot_id]["winner"]
            loser_id = self.slot_results[slot_id]["loser"]
            
            winner_dist, loser_dist = compute_deterministic_match(
                winner_id, loser_id, prob_mass_a, prob_mass_b
            )
        else:
            # Probability-based resolution
            winner_dist, loser_dist = compute_match_probabilities(
                wrestler_a, wrestler_b, prob_mass_a, prob_mass_b
            )
        
        # Store slot probability results
        self.slot_prob_results[slot_id] = {
            "winner": winner_dist,
            "loser": loser_dist
        }
        
        # Remove mass from input wrestlers at this slot level
        # Mass moves forward, doesn't duplicate
        # But only remove mass that was actually used in this slot
        # If wrestlers have mass from other sources, keep that
        # For now, remove all mass from inputs (they've been "consumed" by this slot)
        # Mass will be added back when it flows to downstream slots
        if wrestler_a in self.prob_mass:
            # Only remove the mass that was used (prob_mass_a)
            # But since this is the slot where they meet, remove all their current mass
            self.prob_mass[wrestler_a] = 0.0
        if wrestler_b in self.prob_mass:
            self.prob_mass[wrestler_b] = 0.0
        
        # Distribute mass to downstream slots
        slot = self.slots[slot_id]
        
        # Winner mass goes to winner_to
        winner_total = sum(winner_dist.values())
        if slot.winner_to:
            if slot.winner_to.startswith("PLACE_"):
                # Terminal placement - track mass but placements are deterministic
                # Mass is already accounted for in slot_prob_results
                pass
            else:
                # Distribute mass to wrestlers that can reach winner_to
                # For now, we track in slot_prob_results
                # Actual mass distribution happens when downstream slots resolve
                pass
        
        # Loser mass goes to loser_to
        loser_total = sum(loser_dist.values())
        if slot.loser_to:
            if slot.loser_to.startswith("PLACE_"):
                # Terminal placement
                pass
            else:
                # Track in slot_prob_results
                pass
        
        # Propagate probability mass to downstream slots
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
            
            # Compute bonus points (0.0 in Phase 4A)
            if slot_id in self.slot_results:
                winner_id = self.slot_results[slot_id].get("winner")
                loser_id = self.slot_results[slot_id].get("loser")
                
                if winner_id and loser_id:
                    # Get probability of this outcome
                    if slot_id in self.slot_prob_results:
                        winner_dist = self.slot_prob_results[slot_id].get("winner", {})
                        prob_winner = winner_dist.get(winner_id, 0.0)
                        
                        # Bonus points (0.0 in Phase 4A)
                        bonus = expected_bonus_for_slot(slot, winner_id, loser_id)
                        self.expected_bonus_points[winner_id] = \
                            self.expected_bonus_points.get(winner_id, 0.0) + (prob_winner * bonus)
        
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
        
        xTP = expected_adv_points + expected_place_points + expected_bonus_points
        
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
            self._try_resolve_slot_probabilities(slot.winner_to)
        
        # Check loser_to slot
        if slot.loser_to and not slot.loser_to.startswith("PLACE_"):
            self._try_resolve_slot_probabilities(slot.loser_to)
    
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

