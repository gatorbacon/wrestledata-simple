# Season record differences: today's site vs the canonical bout list

## boys

| season | wrestlers | canon bouts | ACC differs | LIST differs | ACC≠LIST | all agree | ACC replicated | ACC not |
|---|---|---|---|---|---|---|---|---|
| 2013 | 1831 | 25922 | 1538 | 382 | 1543 | 270 | 1831 | 0 |
| 2014 | 1764 | 24564 | 1523 | 413 | 1527 | 220 | 1764 | 0 |
| 2015 | 1809 | 28690 | 855 | 471 | 922 | 812 | 1809 | 0 |
| 2016 | 1764 | 25646 | 799 | 371 | 844 | 876 | 1764 | 0 |
| 2017 | 1720 | 25206 | 837 | 345 | 867 | 797 | 1720 | 0 |
| 2018 | 1726 | 25158 | 771 | 393 | 811 | 832 | 1726 | 0 |
| 2019 | 1898 | 25898 | 852 | 456 | 905 | 916 | 1898 | 0 |
| 2020 | 2025 | 27814 | 898 | 459 | 942 | 995 | 2025 | 0 |
| 2021 | 1467 | 15629 | 454 | 290 | 543 | 881 | 1467 | 0 |
| 2022 | 2243 | 26145 | 859 | 407 | 950 | 1226 | 2243 | 0 |
| 2023 | 2789 | 37008 | 1034 | 449 | 1160 | 1556 | 2789 | 0 |
| 2024 | 2792 | 34198 | 898 | 495 | 1023 | 1721 | 2792 | 0 |
| 2025 | 3035 | 37486 | 927 | 1351 | 1665 | 1304 | 3035 | 0 |
| 2026 | 2883 | 35966 | 749 | 442 | 953 | 1874 | 2883 | 0 |

## girls

| season | wrestlers | canon bouts | ACC differs | LIST differs | ACC≠LIST | all agree | ACC replicated | ACC not |
|---|---|---|---|---|---|---|---|---|
| 2024 | 466 | 4430 | 183 | 140 | 215 | 234 | 466 | 0 |
| 2025 | 664 | 7898 | 259 | 156 | 304 | 340 | 664 | 0 |
| 2026 | 851 | 10058 | 353 | 223 | 427 | 400 | 851 | 0 |

## Why ACC (header record) differs from canonical — net wins / losses that ACC has extra (+) or is missing (−)

| cause | bouts | wins | losses |
|---|---|---|---|
| bout only listed in the opponent's file (missing from this wrestler's) | 28119 | -12867 | -15252 |
| duplicate row(s) of the same bout counted more than once | 8505 | +4737 | +3768 |
| in canonical, not counted by accomplishments (name/team mismatch) | 7663 | -4162 | -3501 |
| winner differs (override / rows disagree) | 296 | +18 | -18 |
| rematch (distinct round labels) | 95 | -44 | -51 |
| override: result/winner | 1 | +0 | +1 |
| override: removed | 1 | +1 | +0 |

Reconciliation (wrestlers with an accomplishments entry): canonical 371205-284840 + causes (-12317/-15053) = 358888-269787; accomplishments file total = 358888-269787. All-wrestler canonical total = 371205-284840.

## Why LIST (Season Stats / match list) differs from canonical

| cause | bouts |
|---|---|
| LIST lacks the 2nd+ bout vs the same opponent on the same day | 6853 |
| LIST merges same-day bouts vs unknown/out-of-state opponents (e.g. two forfeits) into one | 3430 |
| LIST lacks a bout that is in raw data but NOT in the rankings_data weight_class files (dropped by load_data) | 1820 |
| LIST has an entry canonical lacks (other) | 302 |
| LIST has the opposite outcome for this bout (winner differs) | 178 |
| LIST lacks medical forfeits (MFF) | 115 |
| LIST lacks a bout canonical has (other) | 104 |
| LIST lists the same bout twice | 40 |

## Builder stats (all seasons)

| stat | count |
|---|---|
| rows | 669213 |
| canonical bouts | 417716 |
| excluded rows: BYE | 29102 |
| result-conflict clusters (before merging one-sided versions) | 7062 |
| unlabeled rows folded into a labeled bout | 3930 |
| same-day rematch groups (distinct round labels) | 3420 |
| excluded rows: NORESULT | 3282 |
| bouts where the two wrestlers' files record different results (counted once) | 3011 |
| different round labels folded into one bout (rematch not clear) | 1710 |
| bouts whose rows disagree on the winner | 230 |
| rows where the owner's name matches neither side | 193 |
| excluded rows: ERROR | 77 |
| bouts changed by match_overrides | 3 |
| bouts removed by match_overrides | 1 |

## Rematch evidence (all seasons): STRONG = both wrestlers' files list both bouts, or the results differ with real times; WEAK = only one side lists each / 0:00 placeholders (these are the judgment calls): {'STRONG': 3395, 'WEAK': 25}

## Round-label pairs behind 'same-day rematch' bouts (top 25)

| labels | groups |
|---|---|
| - | 797 |
| 3rd place match | quarterfinals | 517 |
| 5th place match | quarterfinals | 227 |
| champ. round 1 | cons. semis | 158 |
| - | quarterfinals | 92 |
| champ. round 1 | cons. round 1 | 77 |
| - | champ. round 1 | 67 |
| round 1 | round 2 | 50 |
| - | semifinals | 48 |
| - | cons. round 2 | 47 |
| champ. round 2 | quarterfinals | 45 |
| - | cons. round 1 | 37 |
| champ. round 2 | cons. semis | 37 |
| 5th place match | champ. round 1 | 35 |
| - | round 2 | 34 |
| - | cons. round 3 | 33 |
| - | round 1 | 33 |
| - | cons. semis | 31 |
| champ. round 1 | 31 |
| - | round 3 | 31 |
| semifinals | 29 |
| 3rd place match | champ. round 1 | 28 |
| champ. round 1 | quarterfinals | 26 |
| - | 1st place match | 25 |
| 1st place match | 25 |

## Samples of unexplained LIST differences

- ('boys', 2013, '1216552009', 'Tristan Lindsey', (None, '2012-12-29', 'L'), 'list-only', '', 0)
- ('boys', 2013, '1220967009', 'Tyler Sutton', (None, '2013-01-19', 'W'), 'list-only', '', 0)
- ('boys', 2013, '1236120009', 'Alex Wright', ('1400702009', '2012-12-01', 'L'), 'Fall 1:32', 'Rumble on the Hilltop. Harrison Co. High School', 2)
- ('boys', 2013, '1236119009', 'Jeffrey Whalen', ('1435725009', '2013-01-05', 'W'), 'Fall 4:00', 'Tates Creek Invitational', 2)
- ('boys', 2013, '1236113009', 'Jorge Mendes', ('1312647009', '2012-12-01', 'W'), 'Fall 1:36', 'Rumble on the Hilltop', 2)
- ('boys', 2013, '1236378009', 'Ean Daly', (None, '2013-01-19', 'L'), 'list-only', '', 0)
- ('boys', 2013, '1236385009', 'Josh Robbins', (None, '2013-02-16', 'L'), 'list-only', '', 0)
- ('boys', 2013, '1240025009', 'Manny Mora', ('1449590009', '2013-01-05', 'L'), 'Fall 3:57', 'Tates Creek Invitational', 2)
- ('boys', 2013, '1240900009', 'Jonathan Rogers', (None, '2012-12-15', 'W'), 'list-only', '', 0)
- ('boys', 2013, '1240899009', 'Megail Perkins', (None, '2012-12-15', 'W'), 'list-only', '', 0)
- ('boys', 2013, '1240908009', 'Kyle Staley', (None, '2012-12-15', 'W'), 'list-only', '', 0)
- ('boys', 2013, '1240902009', 'Jeff Saunders', (None, '2013-02-09', 'L'), 'list-only', '', 0)