"""
NCAA 33-man bracket schema.

Defines the static wiring structure for championship and consolation brackets.
No probabilities, scoring, or simulation logic here.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class Slot:
    """Represents a single bracket slot/match."""
    id: str
    bracket: str  # "champ" or "consol"
    round: str  # e.g. "R32", "QF", "SF", "F", "PIG"
    inputs: list[str]  # exactly 2 symbolic inputs
    winner_to: Optional[str] = None
    loser_to: Optional[str] = None


def build_championship_bracket() -> Dict[str, Slot]:
    """Build championship bracket slots."""
    slots = {}
    
    # PIGTAIL
    slots["C_PIG_0"] = Slot(
        id="C_PIG_0",
        bracket="champ",
        round="PIG",
        inputs=["SEED_32", "SEED_33"],
        winner_to="C_R32_0",
        loser_to="CONS_PIG_0"
    )
    
    # ROUND OF 32
    r32_seed_pairs = [
        (1, "PIG_WINNER"),   # C_R32_0
        (16, 17),            # C_R32_1
        (9, 24),             # C_R32_2
        (8, 25),             # C_R32_3
        (5, 28),             # C_R32_4
        (12, 21),            # C_R32_5
        (13, 20),            # C_R32_6
        (4, 29),             # C_R32_7
        (3, 30),             # C_R32_8 (SPECIAL)
        (14, 19),            # C_R32_9
        (11, 22),            # C_R32_10
        (6, 27),             # C_R32_11
        (7, 26),             # C_R32_12
        (10, 23),            # C_R32_13
        (15, 18),            # C_R32_14
        (2, 31),             # C_R32_15
    ]
    
    for i, pair in enumerate(r32_seed_pairs):
        slot_id = f"C_R32_{i}"
        if i == 0:
            # Special case: uses PIG_WINNER
            inputs = [f"SEED_{pair[0]}", pair[1]]
        else:
            inputs = [f"SEED_{pair[0]}", f"SEED_{pair[1]}"]
        
        # Winners go to R16
        winner_to = f"C_R16_{i // 2}"
        
        # Losers: C_R32_8 goes to CONS_PIG_0, others to CONS_R1
        if i == 8:
            loser_to = "CONS_PIG_0"
        else:
            # Map to CONS_R1 slot
            # CONS_R1_0 gets losers from C_R32_0, C_R32_1
            # CONS_R1_1 gets losers from C_R32_2, C_R32_3
            # etc.
            cons_r1_slot = i // 2
            if i < 8:
                loser_to = f"CONS_R1_{cons_r1_slot}"
            else:
                # For slots 9-15, map to CONS_R1_4-7
                # CONS_R1_4 gets PIG winner and C_R32_9 loser
                # CONS_R1_5 gets C_R32_10, C_R32_11
                # CONS_R1_6 gets C_R32_12, C_R32_13
                # CONS_R1_7 gets C_R32_14, C_R32_15
                if i == 9:
                    loser_to = "CONS_R1_4"
                elif i in [10, 11]:
                    loser_to = "CONS_R1_5"
                elif i in [12, 13]:
                    loser_to = "CONS_R1_6"
                else:  # i in [14, 15]
                    loser_to = "CONS_R1_7"
        
        slots[slot_id] = Slot(
            id=slot_id,
            bracket="champ",
            round="R32",
            inputs=inputs,
            winner_to=winner_to,
            loser_to=loser_to
        )
    
    # ROUND OF 16
    for i in range(8):
        slot_id = f"C_R16_{i}"
        inputs = [
            f"C_R32_{i * 2}_WINNER",
            f"C_R32_{i * 2 + 1}_WINNER"
        ]
        winner_to = f"C_QF_{i // 2}"
        loser_to = f"CONS_R2_{7 - i}"  # Reversed mapping
        
        slots[slot_id] = Slot(
            id=slot_id,
            bracket="champ",
            round="R16",
            inputs=inputs,
            winner_to=winner_to,
            loser_to=loser_to
        )
    
    # QUARTERFINALS
    for i in range(4):
        slot_id = f"C_QF_{i}"
        inputs = [
            f"C_R16_{i * 2}_WINNER",
            f"C_R16_{i * 2 + 1}_WINNER"
        ]
        winner_to = f"C_SF_{i // 2}"
        # Losers go to CONS_R4 (blood round) with crossover
        # CONS_R4_0 vs loser(C_QF_1)
        # CONS_R4_1 vs loser(C_QF_0)
        # CONS_R4_2 vs loser(C_QF_3)
        # CONS_R4_3 vs loser(C_QF_2)
        crossover_map = {0: 1, 1: 0, 2: 3, 3: 2}
        loser_to = f"CONS_R4_{crossover_map[i]}"
        
        slots[slot_id] = Slot(
            id=slot_id,
            bracket="champ",
            round="QF",
            inputs=inputs,
            winner_to=winner_to,
            loser_to=loser_to
        )
    
    # SEMIFINALS
    for i in range(2):
        slot_id = f"C_SF_{i}"
        inputs = [
            f"C_QF_{i * 2}_WINNER",
            f"C_QF_{i * 2 + 1}_WINNER"
        ]
        winner_to = "C_F_0"  # Both winners go to final
        loser_to = f"CONS_SF_{1 - i}"  # Crossover: SF_0 loser goes to CONS_SF_1, etc.
        
        slots[slot_id] = Slot(
            id=slot_id,
            bracket="champ",
            round="SF",
            inputs=inputs,
            winner_to=winner_to,
            loser_to=loser_to
        )
    
    # FINAL
    slots["C_F_0"] = Slot(
        id="C_F_0",
        bracket="champ",
        round="F",
        inputs=["C_SF_0_WINNER", "C_SF_1_WINNER"],
        winner_to="PLACE_1",
        loser_to="PLACE_2"
    )
    
    return slots


def build_consolation_bracket() -> Dict[str, Slot]:
    """Build consolation bracket slots."""
    slots = {}
    
    # CONSOLATION PIGTAIL
    slots["CONS_PIG_0"] = Slot(
        id="CONS_PIG_0",
        bracket="consol",
        round="PIG",
        inputs=["C_PIG_0_LOSER", "C_R32_8_LOSER"],
        winner_to="CONS_R1_4",
        loser_to=None  # Eliminated
    )
    
    # CONS_R1 (8 matches)
    cons_r1_inputs = [
        ["C_R32_0_LOSER", "C_R32_1_LOSER"],   # CONS_R1_0
        ["C_R32_2_LOSER", "C_R32_3_LOSER"],   # CONS_R1_1
        ["C_R32_4_LOSER", "C_R32_5_LOSER"],   # CONS_R1_2
        ["C_R32_6_LOSER", "C_R32_7_LOSER"],   # CONS_R1_3
        ["CONS_PIG_0_WINNER", "C_R32_9_LOSER"], # CONS_R1_4
        ["C_R32_10_LOSER", "C_R32_11_LOSER"], # CONS_R1_5
        ["C_R32_12_LOSER", "C_R32_13_LOSER"], # CONS_R1_6
        ["C_R32_14_LOSER", "C_R32_15_LOSER"], # CONS_R1_7
    ]
    
    for i, inputs in enumerate(cons_r1_inputs):
        slot_id = f"CONS_R1_{i}"
        slots[slot_id] = Slot(
            id=slot_id,
            bracket="consol",
            round="R1",
            inputs=inputs,
            winner_to=f"CONS_R2_{i}",  # CONS_R1_i winner goes to CONS_R2_i
            loser_to=None  # Eliminated
        )
    
    # CONS_R2 (8 matches)
    # winner(CONS_R1_i) vs loser(C_R16_(7 - i))
    for i in range(8):
        slot_id = f"CONS_R2_{i}"
        inputs = [
            f"CONS_R1_{i}_WINNER",
            f"C_R16_{7 - i}_LOSER"
        ]
        slots[slot_id] = Slot(
            id=slot_id,
            bracket="consol",
            round="R2",
            inputs=inputs,
            winner_to=f"CONS_R3_{i // 2}",
            loser_to=None  # Eliminated
        )
    
    # CONS_R3 (4 matches)
    # CONS_R2 winners: 0v1, 2v3, 4v5, 6v7
    for i in range(4):
        slot_id = f"CONS_R3_{i}"
        inputs = [
            f"CONS_R2_{i * 2}_WINNER",
            f"CONS_R2_{i * 2 + 1}_WINNER"
        ]
        slots[slot_id] = Slot(
            id=slot_id,
            bracket="consol",
            round="R3",
            inputs=inputs,
            winner_to=f"CONS_R4_{i}",
            loser_to=None  # Eliminated
        )
    
    # CONS_R4 (Blood Round - 4 matches)
    # CONS_R3_0 vs loser(C_QF_1)
    # CONS_R3_1 vs loser(C_QF_0)
    # CONS_R3_2 vs loser(C_QF_3)
    # CONS_R3_3 vs loser(C_QF_2)
    crossover_map = {0: 1, 1: 0, 2: 3, 3: 2}
    for i in range(4):
        slot_id = f"CONS_R4_{i}"
        qf_slot = crossover_map[i]
        inputs = [
            f"CONS_R3_{i}_WINNER",
            f"C_QF_{qf_slot}_LOSER"
        ]
        slots[slot_id] = Slot(
            id=slot_id,
            bracket="consol",
            round="R4",
            inputs=inputs,
            winner_to=f"CONS_QF_{i // 2}",
            loser_to=None  # Eliminated
        )
    
    # CONS_QF (2 matches)
    # CONS_R4_0 vs CONS_R4_1
    # CONS_R4_2 vs CONS_R4_3
    for i in range(2):
        slot_id = f"CONS_QF_{i}"
        inputs = [
            f"CONS_R4_{i * 2}_WINNER",
            f"CONS_R4_{i * 2 + 1}_WINNER"
        ]
        slots[slot_id] = Slot(
            id=slot_id,
            bracket="consol",
            round="QF",
            inputs=inputs,
            winner_to=f"CONS_SF_{i}",
            loser_to="CONS_7TH"  # Both CONS_QF losers go to 7th place match
        )
    
    # CONS_SF (2 matches)
    # CONS_QF_0 winner vs C_SF_1 loser
    # CONS_QF_1 winner vs C_SF_0 loser
    for i in range(2):
        slot_id = f"CONS_SF_{i}"
        inputs = [
            f"CONS_QF_{i}_WINNER",
            f"C_SF_{1 - i}_LOSER"  # Crossover
        ]
        slots[slot_id] = Slot(
            id=slot_id,
            bracket="consol",
            round="SF",
            inputs=inputs,
            winner_to="CONS_3RD",
            loser_to="CONS_5TH"
        )
    
    # PLACEMENT MATCHES
    # 3rd place: winners of CONS_SF_0 vs CONS_SF_1
    slots["CONS_3RD"] = Slot(
        id="CONS_3RD",
        bracket="consol",
        round="PLACE",
        inputs=["CONS_SF_0_WINNER", "CONS_SF_1_WINNER"],
        winner_to="PLACE_3",
        loser_to="PLACE_4"
    )
    
    # 5th place: losers of CONS_SF_0 vs CONS_SF_1
    slots["CONS_5TH"] = Slot(
        id="CONS_5TH",
        bracket="consol",
        round="PLACE",
        inputs=["CONS_SF_0_LOSER", "CONS_SF_1_LOSER"],
        winner_to="PLACE_5",
        loser_to="PLACE_6"
    )
    
    # 7th place: losers of CONS_QF_0 vs CONS_QF_1
    slots["CONS_7TH"] = Slot(
        id="CONS_7TH",
        bracket="consol",
        round="PLACE",
        inputs=["CONS_QF_0_LOSER", "CONS_QF_1_LOSER"],
        winner_to="PLACE_7",
        loser_to="PLACE_8"
    )
    
    # PLACE terminals (1st-8th)
    for i in range(1, 9):
        place_id = f"PLACE_{i}"
        # These are terminal nodes - no outputs
        slots[place_id] = Slot(
            id=place_id,
            bracket="champ" if i <= 2 else "consol",
            round="PLACE",
            inputs=[],  # Will be populated by references
            winner_to=None,
            loser_to=None
        )
    
    return slots


def get_all_slots() -> Dict[str, Slot]:
    """Get all bracket slots."""
    slots = {}
    slots.update(build_championship_bracket())
    slots.update(build_consolation_bracket())
    return slots


# Export ALL_SLOTS
ALL_SLOTS = get_all_slots()

