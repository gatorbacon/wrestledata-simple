#!/bin/sh
# Rebuild everything from the PDFs in pdf/ ("NCAA 1928.pdf" ...).
mkdir -p raw json out
for f in pdf/NCAA*.pdf; do y=$(echo "$f" | grep -o '[0-9]\{4\}'); python3 extract.py "$f" > raw/NCAA$y.txt; done
for f in raw/NCAA[0-9][0-9][0-9][0-9].txt; do y=$(echo "$f" | grep -o '[0-9]\{4\}')
  [ "$y" -gt 2016 ] && continue   # 2017+ are scans or NCAA-format PDFs, not handled here
  case $y in 2015) awk '/^#P2$/{exit} {print}' $f > raw/NCAA2015_summary.txt; python3 parse_badpoints.py raw/NCAA2015_summary.txt meta/_base.json > out/NCAA$y.json ;;
    1934|1936|1938|1948) python3 parse_badpoints.py $f meta/_base.json > out/NCAA$y.json ;;
    *) python3 parse_ws.py $f meta/_base.json > json/NCAA$y.json && python3 to_house_format.py json/NCAA$y.json > out/NCAA$y.json ;; esac
  python3 replay_house.py out/NCAA$y.json > out/replay_$y.txt || echo "$y: replay errors"
done
python3 check_sheets.py        # consolation-sheet structure
python3 make_team_scores.py    # team_scores/
python3 make_audit.py          # AUDIT.md
python3 build_v2.py            # v2/ = the published data files
