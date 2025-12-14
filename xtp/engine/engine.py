"""
Deterministic bracket engine.

Propagates winners and losers through the bracket graph.
No probabilities, scoring, or simulation - pure logical execution.
"""

from typing import Dict, List, Optional
from xtp.engine.bracket_schema import Slot, get_all_slots


class BracketEngine:
    """
    Deterministic bracket execution engine.
    
    Moves wrestler_ids through slots based on bracket wiring.
    """
    
    def __init__(self, slots: Dict[str, Slot], seeds: Dict[int, str]):
        """
        Initialize engine.
        
        Args:
            slots: All bracket slots (from bracket_schema.ALL_SLOTS)
            seeds: Mapping from seed number (1-33) to wrestler_id
        """
        self.slots = slots
        self.seeds = seeds
        
        # Track results for each slot
        # Format: {slot_id: {"winner": wrestler_id, "loser": wrestler_id}}
        self.slot_results: Dict[str, Dict[str, Optional[str]]] = {}
        
        # Track final placements (1-8)
        self.placements: Dict[int, str] = {}
        
        # Track which slots have been resolved
        self.resolved_slots: set = set()
    
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

