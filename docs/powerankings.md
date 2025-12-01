Wrestler Power Ranking System (Specification)

Purpose

Create a tunable numerical power-ranking score for each wrestler to break ties or near-ties in your ranking matrix. This score supplements—not replaces—your primary ranking logic. It helps differentiate between closely matched wrestlers by rewarding:
	•	Wins over higher-ranked opponents
	•	Competitive losses to higher-ranked opponents
	•	Bonus-point wins (MD/TF/pin)
	•	Consistency against similarly ranked opponents
	•	Avoiding bad losses

The system is fully parameterized so you can adjust weight values as needed.

⸻

Core Concept

Each wrestler receives a Power Score computed from:

Power Score = Quality Wins + Competitive Losses + Bonus Score + Consistency − Bad Loss Penalty

You can adjust the weight of each component through modifiers.

⸻

Input Requirements

For each match:
	•	Opponent rank (integer)
	•	Wrestler rank (integer)
	•	Match result (W/L)
	•	Win type (DEC/MD/TF/FALL)
	•	Score margin (if DEC)
	•	Optional: home/away/neutral (ignored for now)

⸻

Tunable Modifiers

These are the variables you can tweak based on how strong you want each effect:

# Weight modifiers you can tune
MOD_QUALITY_WIN: 1.0
MOD_QUALITY_LOSS: 0.6
MOD_BONUS: 0.4
MOD_PIN: 0.8
MOD_BAD_LOSS: 1.2
MOD_CONSISTENCY: 0.25

You can change these anytime.

⸻

Component Details

1. Quality Wins (Reward beating good opponents)

Formula:

Quality Win = MOD_QUALITY_WIN × (Max(0, OppRank − WrestRank) + 1)

Notes:
	•	Beating someone close to your ranking gives high points.
	•	Beating a much lower opponent gives little or no credit.

Examples:
	•	#5 beats #7 → (7−5)+1 = 3 points
	•	#5 beats #25 → (25−5)+1 = 21 → capped or weighted down? (Tunable)

Optional Cap: You can cap at +10 if you don’t want big spreads.

⸻

2. Competitive Losses (Reward close losses to high opponents)

Formula:

Competitive Loss = MOD_QUALITY_LOSS × Max(0, WrestRank − OppRank)

Rules:
	•	Only applied if the loss is not by pin or blowout.
	•	Close decision (≤3 points) gets full credit.
	•	Loss by >7 points → credit = 0.

Examples:
	•	#8 loses 4–3 to #2 → (8−2)=6 → weighted
	•	#8 loses 12–2 to #2 → 0

⸻

3. Bonus Score (Reward MD, TF, FALL)

Suggested:
	•	MD: +1 × MOD_BONUS
	•	TF: +2 × MOD_BONUS
	•	PIN: +1 × MOD_PIN (because falls matter more)

You can tune these as needed.

⸻

4. Consistency Score

Penalize struggling with lower-ranked opponents even in wins.

Formula:

Consistency = MOD_CONSISTENCY × (OppRank − WrestRank)

Applied if:
	•	Wrestler wins by ≤2 points
	•	Opponent is ≥10 ranks lower

Example:
	•	#4 wins 4–3 over #22 → (22−4)=18 × 0.25

Keeps guys from coasting.

⸻

5. Bad Loss Penalty

Penalize losing to much lower-ranked opponents.

Formula:

Bad Loss = MOD_BAD_LOSS × (OppRank − WrestRank)

Trigger:
	•	Opponent ranked ≥10 spots lower

Example:
	•	#3 loses to #18 → (18−3)=15 × 1.2

This hits hard, as it should.

⸻

Final Output

For each wrestler:

Power Score = sum( all components for all matches )

Sort highest → lowest to break ties or generate a list of overall strength.

⸻

Implementation Notes
	•	You should store modifiers at the top of your script so you can tweak easily.
	•	Components add up naturally; no need for normalization unless scores get too large.
	•	You can optionally build a per-match breakdown table for debugging.

⸻

Example (Simple)

Wrestler #5:
	•	Beat #7 by MD → Quality Win=3, MD bonus
	•	Beat #25 by DEC 4–3 → Quality Win=0 (low value), Consistency hit
	•	Lost 3–2 to #3 → Competitive Loss

When tallied, this clearly separates him from:
	•	A #5 wrestler who beat #25 by 12–1 TF and never faced #3.

⸻

Summary

This framework is:
	•	Clear
	•	Tunable
	•	Rankings-aware
	•	Bonus-aware
	•	Loss-context-aware

It’s exactly the kind of tool that will stabilize close calls in your matrix.