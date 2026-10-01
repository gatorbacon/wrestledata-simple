# Validation: PDF parser vs. your independent 2013, 2014 and 2016 files

"Yours" = your match files. "Sheet" = what the parser read from the wrestlingstats PDF.

| | 2013 | 2014 | 2016 |
|---|---|---|---|
| Bouts (yours / sheet) | 640 / 640 | 640 / 638 | 640 / 640 |
| Same bout, same winner | 638 | 638 | 640 |
| Same round (of matched) | 638 / 638 | 638 / 638 | 640 / 640 |
| Same result type* | 634 | 635 | 637 |
| Sheet printed no result | 4 | 3 | 3 |
| Score / fall time differs | 5 | 5 | 16 |
| Seeds disagreeing | 0 | 0 | 0 |

*Decision, major, tech fall, SV and TB all count as a decision (the sheet does not label MD/TF).

Every disagreement was checked against the PDF text. **In each one the parser recorded exactly what the sheet prints**:
it is the sheet and your data that disagree, not a parsing error.

## 2013
- 184 R16/QF: sheet has Josh Ihnen beating Max Thomusseit 3-1, then Ed Ruth beating Ihnen 11-1 in the QF.
  Yours has Thomusseit winning and meeting Ruth. (2 bouts)
- 285 C_R4 Delaney over Hanke: yours Fall 4:22, sheet Fall 4:12.
- Scores: 133 C_R1 DiCamillo-Spjut (yours 6-1 / sheet 4-1), 157 R32 Fleming-Churchard (16-0 / 15-0),
  165 R16 Dake-LeBlanc (10-0 / 11-0), 197 R16 Meeks-Hein (4-3 / 5-3).

## 2014
- 165 R32: the sheet puts a Bye opposite Joseph Booth but still prints "Booth 10-2"; your file has
  Booth over Jacob Kemerer 10-2 and Kemerer's consolation loss. The parser now flags this pattern
  (it found the same thing in two other years).
- Scores: 125 SF Delgado-Peters (9-6 / 6-4), 141 QF Carter-Durso (4-3 / 5-3), 149 C_R2 English-Barber
  (3-1 / 4-3), 184 R32 Thomusseit-Morrison (5-4 / 7-5), 285 R32 Smith-Fager (6-2 / 5-2).

## 2016
- 16 score/time differences, all confirmed as printed on the sheet (see compare_2016.md), e.g.
  125 7th Millhof-Schram (yours 1-0 / sheet 7-1, the summary page also says 7-1),
  197 QF Cox-Harner (6-0 / 8-0), 285 QF Snyder-Dhesi (16-5 / 18-5).

## Names
40-55 wrestlers per year are spelled differently (Nicholas/Nick, Stephen Dutton III/Steve Dutton,
Undrakhbayar/Ugi Khishignyam, Ream/Rearn). They were matched by surname + first name/initial; the
full lists are at the end of each compare_YYYY.md.

## Conclusion
Structure (who wrestled whom, in which round, who advanced where, placements, seeds) matched 100% of
the bouts both sources contain, except the 3 bouts where the sheet itself is different. Score-level
disagreement is 1-2.5% of bouts and comes from the source PDFs, which are hand-compiled.
