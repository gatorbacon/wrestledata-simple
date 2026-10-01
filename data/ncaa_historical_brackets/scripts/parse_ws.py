#!/usr/bin/env python3
"""Parse a wrestlingstats.com NCAA bracket-sheet text dump (x<TAB>y<TAB>text per
PDF text item, pages separated by '#P<n>') into a replayable bracket JSON.

Usage: python parse_ws.py raw/NCAA1928.txt meta/1928.json > json/NCAA1928.json
"""
import json, re, sys
from collections import defaultdict

RESULT_TYPES = [  # (regex on raw result, normalized code)
    (r'^TF\b', 'TF'), (r'^MT\b', 'TF'), (r'^Pin\b', 'FALL'), (r'^Fa[;:,.]', 'FALL'), (r'^Inj', 'DEF'), (r'^W \d', 'DEC'), (r'^\d+=\d+$', 'DEC'), (r'^Med FFT', 'MFF'), (r'^MFT', 'MFF'), (r'^Med Forfeit', 'MFF'), (r'^DSQ', 'DQ'), (r'^WDQ', 'DQ'), (r'^Med DFT', 'DEF'), (r'^WFT', 'FF'), (r'^RD\b', 'DEC'), (r'^DFT', 'DEF'), (r'^WDF', 'DEF'), (r'^WBF', 'FALL'), (r'^Fall', 'FALL'),
    (r'^TA', 'TA'), (r'^Dec', 'DEC'), (r'^Auto', 'AUTO'), (r'^FFT', 'FF'),
    (r'^Forfeit', 'FF'), (r'^Default', 'DEF'), (r'^DQ', 'DQ'),
]


def parse_result(raw):
    raw = (raw or '').strip()
    if not raw:
        return None
    code = next((c for rx, c in RESULT_TYPES if re.match(rx, raw, re.I)), None)
    pts = re.search(r'\b(\d+-\d+(?:, \d+-\d+)*)\b', raw)
    if code is None:
        if re.match(r'^\d+-\d+,\s*\d+:\d\d$', raw):
            code = 'TF'                                   # '19-4, 4:48' = tech fall (points, time)
        else:
            code = 'DEC' if re.match(r'^\d+-\d+', raw) else 'UNKNOWN'
    t = re.search(r'(\d+:\d\d)', raw)
    return {'raw': raw, 'type': code, 'time': t.group(1) if t else None,
            'points': pts.group(1) if pts else None,
            'ot': bool(re.search(r'\b(OT|TB|SV|Cr)\b|\b(sv|tb|SV|TB)-\d', raw))}   # overtime / tiebreaker / sudden victory / criteria


def load_pages(path):
    pages, cur = [], None
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line:
            continue
        if line.startswith('#P'):
            cur = []
            pages.append(cur)
            continue
        x, y, s = line.split('\t', 2)
        cur.append({'x': int(x), 'y': int(y), 's': s.strip()})
    return pages


def split_name_school(s):
    name, _, school = s.partition(', ')
    return name.strip(), school.strip()


def cluster_x(items, tol=8):
    cols = []
    for it in sorted(items, key=lambda i: i['x']):
        if cols and it['x'] - cols[-1][0]['x'] <= tol:
            cols[-1].append(it)
        else:
            cols.append([it])
    return [sorted(c, key=lambda i: -i['y']) for c in cols]


def round_names(n_lines):
    """16 -> ['R1','QF','SF','F'];  32 -> ['R1','R2','QF','SF','F']."""
    k = n_lines.bit_length() - 1
    tail = ['QF', 'SF', 'F'][-k:] if k <= 3 else ['QF', 'SF', 'F']
    head = [f'R{i+1}' for i in range(k - len(tail))]
    return head + tail


HEADER_RX = re.compile(r'^(Page \d+ of \d+|\d{4} NCAA .*Championship|\d+/\d+/\d{4} .*)$')


def split_pages(pages):
    """Return {weight: {'bracket': [items], 'cons': [items]}} regardless of layout
    (bracket + consolations on one page, or on separate pages)."""
    out = {}
    order = []
    for items in pages[1:]:
        items = [i for i in items if not HEADER_RX.match(i['s'])]
        ch = next((i for i in items if re.match(r'^\S+ Weight Class Consolation Bouts$', i['s'])), None)
        lab = next((i for i in items if re.match(r'^\S+ Weight Class$', i['s'])), None)
        cb = next((i for i in items if re.match(r'^(\S+ )?Consolation Bracket$', i['s'])), None)
        pg = [i for i in items if re.match(r'^(Championship|Consolation) Pigtail Bouts for \S+$', i['s'])]
        rest = items
        if pg:
            wt = pg[0]['s'].split()[-1]
            out.setdefault(wt, {'bracket': [], 'cons': []})
            out[wt].setdefault('pig', []).append(items)      # one list per page
            continue
        if any(re.match(r'^No Pigtails? Bouts', i['s']) for i in items):
            continue
        if cb:
            wt = cb['s'].split()[0] if cb['s'] != 'Consolation Bracket' else lab['s'].split()[0]
            out.setdefault(wt, {'bracket': [], 'cons': []})
            if wt not in order: order.append(wt)
            below = [i for i in items if i['y'] < cb['y'] + (0 if cb['s'] == 'Consolation Bracket' else 30)
                     and i is not cb]
            out[wt]['cons'] += [dict(i, ladder=True) for i in below]
            out[wt]['style'] = 'ladder'
            rest = [i for i in items if i['y'] > cb['y']] if cb['s'] == 'Consolation Bracket' else []
        elif ch:
            wt = ch['s'].split()[0]
            out.setdefault(wt, {'bracket': [], 'cons': []})
            out[wt]['cons'] += [i for i in items if i['y'] < ch['y']]
            if wt not in order: order.append(wt)
            rest = [i for i in items if i['y'] > ch['y']]
        if lab:
            wt = lab['s'].split()[0]
            out.setdefault(wt, {'bracket': [], 'cons': []})
            if wt not in order: order.append(wt)
            out[wt]['bracket'] += [i for i in rest if i is not lab and i['s'] != 'Consolation Bouts']
    return [(w, out[w]) for w in order]


def parse_weight_page(wt, bitems, citems, discrepancies, pitems=None):
    # ---------------- championship bracket ----------------
    cols = cluster_x(bitems)
    lines = cols[0]
    n = len(lines)
    if n & (n - 1):
        raise ValueError(f'{wt}: draw has {n} lines (not a power of 2)')
    rnames = round_names(n)
    entrants, line_to_id = [], {}
    k = 0
    for li, it in enumerate(lines, start=1):
        if it['s'] == 'Bye':
            line_to_id[li] = None
            continue
        k += 1
        name, school = split_name_school(it['s'])
        sm = re.search(r'\s*\[(\d+|US)\]$', school)
        seed = int(sm.group(1)) if sm and sm.group(1).isdigit() else None
        if sm:
            school = school[:sm.start()]
        wid = f'{wt}-{k:02d}'
        entrants.append({'id': wid, 'line': li, 'seed': seed, 'name': name, 'school': school})
        line_to_id[li] = wid
    by_name = {e['name']: e['id'] for e in entrants}

    # distribute result columns into rounds; overflow (final drawn beside SF) by y-middle
    result_cols = cols[1:]
    round_entries = []
    expected = [n >> (r + 1) for r in range(len(rnames))]
    for ci, col in enumerate(result_cols):
        need = expected[len(round_entries)]
        if len(col) == need:
            round_entries.append(col)
        elif len(col) == need + 1 and need == 2:  # SF column with final in middle
            ys = sorted(col, key=lambda i: -i['y'])
            round_entries.append([ys[0], ys[2]])
            round_entries.append([ys[1]])
        else:
            raise ValueError(f'{wt}: unexpected column size {len(col)} (need {need})')

    matches, prev_ids = [], [('line', li) for li in range(1, n + 1)]
    for r, (rname, col) in enumerate(zip(rnames, round_entries)):
        cur_ids = []
        for b, it in enumerate(col, start=1):
            mid = f'{wt}-{rname}' + ('' if rname == 'F' else f'-{b:02d}')
            srcs = prev_ids[2 * (b - 1): 2 * b]
            sides = []
            for kind, ref in srcs:
                if kind == 'line':
                    sides.append({'from': {'line': ref}, 'wrestler': line_to_id[ref]})
                else:
                    pm = next(m for m in matches if m['id'] == ref)
                    sides.append({'from': {'winner_of': ref}, 'wrestler': pm['winner']})
            s = it['s']
            winner, raw = None, ''
            if s != 'Bye':
                cands = [sd['wrestler'] for sd in sides if sd['wrestler']]
                for wid in sorted(cands, key=lambda w: -len(next(e['name'] for e in entrants if e['id'] == w))):
                    nm = next(e['name'] for e in entrants if e['id'] == wid)
                    if s == nm or s.startswith(nm + ' '):
                        winner, raw = wid, s[len(nm):].strip()
                        break
                if winner is None:
                    # source typo: pick the candidate who shows up in the consolation text, if exactly one does
                    ctext = ' '.join(i['s'] for i in citems)
                    names = {w: next(e['name'] for e in entrants if e['id'] == w) for w in cands}
                    seen = [w for w in cands if names[w] in ctext]
                    rm = re.search(r'\s((?:Fall|TA|Dec|RD|DFT|WDF|Med FFT|FFT|WBF)\b.*)$', s)
                    sur = [w for w in cands if s.split()[1:2] and names[w].split()[-1] == s.split()[1]]
                    if winner is None and len(sur) == 1:
                        winner = sur[0]
                        raw = rm.group(1) if rm else ''
                        discrepancies.append(f'{mid}: source prints winner "{s}"; bout is {" vs ".join(names.values())}; '
                                             f'taken as {names[winner]} (same surname)')
                    elif len(seen) == 1:
                        winner, raw = seen[0], rm.group(1) if rm else ''
                        discrepancies.append(f'{mid}: source prints winner "{s}", who is not in this bout; '
                                             f'inferred {names[winner]} (only one of the pair who appears in the consolations)')
                    else:
                        fw, fr = fuzzy_pick(s, cands, names)
                        if fw:
                            winner, raw = fw, fr
                            discrepancies.append(f'{mid}: source prints winner "{s}"; taken as {names[fw]} (spelling)')
                        else:
                            discrepancies.append(f'{mid}: could not match winner text "{s}" to {list(names.values())}')
            present = [sd['wrestler'] for sd in sides if sd['wrestler']]
            loser = next((w for w in present if w != winner), None) if len(present) == 2 else None
            if len(present) == 2:
                res = parse_result(raw) or {'raw': '', 'type': 'UNKNOWN', 'time': None, 'ot': False}
                status = 'contested'
            elif len(present) == 1:
                res, status = {'raw': '', 'type': 'BYE', 'time': None, 'ot': False}, 'bye'
                if raw and re.search(r'\d', raw):
                    discrepancies.append(f'{mid}: sheet prints a result ("{s}") but the opponent\'s line is a Bye - '
                                         f'a wrestler is probably missing from the draw; recorded as a bye')
                if winner != present[0]:
                    discrepancies.append(f'{mid}: bye winner mismatch')
            else:
                res, status = None, 'empty'
            matches.append({'id': mid, 'bracket': 'championship', 'round': rname,
                            'bout': None if rname == 'F' else b, 'status': status,
                            'top': sides[0], 'bottom': sides[1],
                            'winner': winner, 'loser': loser, 'result': res})
            cur_ids.append(('match', mid))
        prev_ids = cur_ids

    # ---------------- consolation / place bouts ----------------
    if citems and citems[0].get('ladder'):
        pre, precons = [], []
        if pitems:
            pig = parse_pigtails(wt, pitems, entrants, discrepancies)
            for kind, lst, out in (('champ', pig['champ'], pre), ('cons', pig['cons'], precons)):
                for b, (sides, w, raw) in enumerate(lst, start=1):
                    rnd = 'PIG' if kind == 'champ' else 'C_PIG'
                    l = sides[1] if w == sides[0] else sides[0]
                    out.append({'id': f'{wt}-{rnd}-{b:02d}', 'bracket': 'championship' if kind == 'champ' else 'consolation',
                                'round': rnd, 'bout': b, 'for_place': None, 'status': 'contested' if w else 'unknown_winner',
                                'top': {'from': 'entry', 'wrestler': sides[0]}, 'bottom': {'from': 'entry', 'wrestler': sides[1]},
                                'winner': w, 'loser': l if w else None, 'result': parse_result(raw) if raw else None,
                                '_pair': (w, l) if w else tuple(sides)})
            # championship pigtail winners enter the draw: point their first-round source at the pigtail
            for pm in pre:
                for m in matches:
                    for side in ('top', 'bottom'):
                        if m[side]['wrestler'] == pm['winner'] and 'line' in (m[side]['from'] or {}):
                            m[side]['from'] = {'line': m[side]['from']['line'], 'winner_of': pm['id']}
            for pm in pre:
                pm.pop('_pair')
        lost = {m['loser'] for m in pre + matches if m.get('loser')}
        cm, pl = (parse_ladder_cons(wt, citems, entrants, discrepancies) if LEGACY_LADDER
                  else parse_tree_cons(wt, citems, entrants, discrepancies, lost))
        return wt, entrants, pre + matches, precons + cm, pl
    citems = sorted(citems, key=lambda i: (-i['y'], i['x']))
    rows = defaultdict(list)
    for it in citems:
        rows[it['y']].append(it)
    section, placements_auto, cmatches = None, [], []
    counters = defaultdict(int)
    for y in sorted(rows, reverse=True):
        row = sorted(rows[y], key=lambda i: i['x'])
        if len(row) == 1:
            section = row[0]['s']  # e.g. 'Second Place', 'Third Place'
            continue
        label, text = row[0]['s'], ' '.join(r['s'] for r in row[1:])
        place = {'Second Place': 2, 'Third Place': 3, 'Fourth Place': 4,
                 'Fifth Place': 5, 'Sixth Place': 6}.get(section)
        m = re.match(r'^(.*?) defeated (.*?)(?: - (.*))?$', text)
        if not m:
            ma = re.match(r'^(.*?)( automatic)?$', text)
            nm, _ = split_name_school(ma.group(1))
            final_label = label in ('Second', 'Third', 'Fourth', 'Fifth', 'Sixth')
            if nm in by_name and (ma.group(2) or final_label):
                # 'automatic' = awarded with no bout; bare name = place listed, bout not recorded
                placements_auto.append({'place': place, 'wrestler': by_name[nm],
                                        'method': 'automatic' if ma.group(2) else 'bout_not_recorded'})
                continue
            discrepancies.append(f'{wt} consolation: unparsed "{text}"')
            continue
        wn, _ = split_name_school(m.group(1))
        ln, _ = split_name_school(m.group(2))
        w, l = by_name.get(wn), by_name.get(ln)
        if not w or not l:
            discrepancies.append(f'{wt} consolation: unknown wrestler in "{text}"')
        code = {'WRB Semi-Final': 'SF', 'WRB Quarter-Final': 'QF', 'WRB Eighth-Final': 'R16', 'WRB Final': 'WF',
                'Second': 'F', 'Third': 'F'}.get(label, re.sub(r'\W+', '', label).upper())
        base = f'{wt}-P{place}-{code}'
        counters[base] += 1
        cmatches.append({'id': base if code == 'F' else f'{base}-{counters[base]:02d}',
                         'bracket': 'consolation', 'round': f'P{place}-{code}',
                         'label': label, 'for_place': place, 'status': 'contested',
                         'winner': w, 'loser': l, 'result': parse_result(m.group(3) or '')})
    for cm in cmatches:
        cm.setdefault('_pair', (cm['winner'], cm['loser']))
    return wt, entrants, matches, cmatches, placements_auto


LEGACY_LADDER = False
RES_TAIL = re.compile(r'\s+((?:Fall|TF|MT|Pin|TA|Dec|RD|DFT|WDF|Med FFT|Med DFT|Med Forfeit|MFT|FFT|WFT|WBF|Default|Forfeit|DQ|DSQ|Inj|\d+-\d+)\b.*)$', re.I)


def parse_ladder_cons(wt, citems, entrants, discrepancies):
    """1941+ drawn consolation: per half, a stepladder of the finalist's victims
    (col A: two earliest losers; col B: + QF loser; col C: + SF loser; col D: half winner),
    then a box 'Third Place: <winner, school result>' / 'Fourth Place: <loser>'."""
    box = {}
    for lab in [i for i in citems if i['s'] in ('Third Place:', 'Fourth Place:')]:
        val = next((i for i in citems if i['y'] == lab['y'] and i['x'] > lab['x']), None)
        box[lab['s']] = val
    skip = {id(v) for v in box.values() if v} | {id(i) for i in citems if i['s'] in ('Third Place:', 'Fourth Place:')}
    items = [i for i in citems if id(i) not in skip]
    cols = cluster_x(items)
    if len(cols) != 4:
        discrepancies.append(f'{wt} consolation: expected 4 ladder columns, found {len(cols)}')
        return [], []
    A = cols[0]
    if len(A) != 4:
        discrepancies.append(f'{wt} consolation: expected 4 first-column lines, found {len(A)}')
        return [], []
    split_y = A[2]['y'] + 3
    is_entry = lambda i: i['s'] == 'Bye' or bool(re.match(r'^[^,\d]+, [^\d\s]', i['s']))   # 'Surname, School': no digits before the comma

    def find(sur_school):
        if sur_school == 'Bye':
            return None
        sur, _, school = sur_school.partition(', ')
        sm = re.search(r'\s*\[(\d+|US)\]$', school)
        if sm: school = school[:sm.start()]
        hits = [e['id'] for e in entrants if (e['name'] == sur or e['name'].endswith(' ' + sur)) and e['school'] == school]
        if len(hits) != 1:
            hits = [e['id'] for e in entrants if e['name'] == sur or e['name'].endswith(' ' + sur)]
        if len(hits) != 1:
            discrepancies.append(f'{wt} consolation: cannot identify "{sur_school}"')
            return None
        return hits[0]

    name = {e['id']: e['name'] for e in entrants}

    def winner_of(text, a, b):
        cands = [w for w in (a, b) if w]
        for w in sorted(cands, key=lambda w: -len(name[w])):
            for form in (name[w], name[w].split()[-1] if ' ' in name[w] else name[w]):
                if text == form or text.startswith(form + ' '):
                    return w, text[len(form):].strip()
        return None, text

    t3, t4 = box.get('Third Place:'), box.get('Fourth Place:')
    w3 = w4 = None
    raw3 = ''
    if t3:
        m3 = RES_TAIL.search(t3['s'])
        raw3 = m3.group(1) if m3 else ''
        who3 = t3['s'][:m3.start()] if m3 else t3['s']
        n3, _, s3 = who3.partition(', ')
        w3 = next((e['id'] for e in entrants if e['name'] == n3 and e['school'] == s3), None) or \
             next((e['id'] for e in entrants if e['name'] == n3), None) or find(f"{n3.split()[-1]}, {s3}")
    if t4:
        n4, _, s4 = t4['s'].partition(', ')
        w4 = next((e['id'] for e in entrants if e['name'] == n4 and e['school'] == s4), None) or \
             next((e['id'] for e in entrants if e['name'] == n4), None) or find(f"{n4.split()[-1]}, {s4}")
    cmatches, halves = [], []
    rounds = ['C_R1', 'C_QF', 'C_SF']
    for h, (hi, lo) in enumerate(((10**6, split_y), (split_y, -10**6)), start=1):
        part = [[i for i in c if lo < i['y'] < hi] for c in cols]
        a = sorted(part[0], key=lambda i: -i['y'])
        surv = find(a[0]['s'])
        entrants_in = [find(a[1]['s'])]
        for k in (1, 2):
            e = [i for i in part[k] if is_entry(i)]
            entrants_in.append(find(e[0]['s']) if e else None)
        for k in range(3):
            other = entrants_in[k]
            wtxt = [i for i in part[k + 1] if not is_entry(i)]
            if surv and other:
                inbox = [x for x in (surv, other) if x in (w3, w4)]
                if not wtxt and k == 2 and len(inbox) == 1:
                    w, raw = inbox[0], ''
                    discrepancies.append(f'{wt} consolation half {h} {rounds[k]}: winner not printed; '
                                         f'{name[w]} taken as winner because he wrestled for 3rd/4th')
                elif not wtxt:
                    discrepancies.append(f'{wt} consolation half {h} {rounds[k]}: no winner printed')
                    w, raw = None, ''
                else:
                    w, raw = winner_of(wtxt[0]['s'], surv, other)
                    if not w:
                        discrepancies.append(f'{wt} consolation half {h} {rounds[k]}: winner "{wtxt[0]["s"]}" not in bout')
                l = other if w == surv else surv
                cmatches.append({'id': f'{wt}-{rounds[k]}-{h:02d}', 'bracket': 'consolation', 'round': rounds[k],
                                 'label': rounds[k], 'for_place': None, 'status': 'contested',
                                 'winner': w, 'loser': l if w else None,
                                 'result': parse_result(raw) if raw else None, '_pair': (w, l)})
                surv = w
            else:
                surv = surv or other
        halves.append(surv)
    placements = []
    raw = raw3
    n3 = name.get(w3) or (t3 and t3['s']); n4 = name.get(w4) or (t4 and t4['s'])
    if t3:
        if set(halves) == {w3, w4} and w3 and w4:
            cmatches.append({'id': f'{wt}-3rd', 'bracket': 'consolation', 'round': '3rd', 'label': 'Third Place',
                             'for_place': 3, 'status': 'contested', 'winner': w3, 'loser': w4,
                             'result': parse_result(raw) if raw else None, '_pair': (w3, w4)})
        else:
            discrepancies.append(f'{wt}: 3rd/4th ({n3} / {n4}) are not the two consolation half winners '
                                 f'({[name.get(x) for x in halves]}); recorded as placements only')
            if w3: placements.append({'place': 3, 'wrestler': w3, 'method': 'listed'})
            if w4: placements.append({'place': 4, 'wrestler': w4, 'method': 'listed'})
    for cm in cmatches:
        if cm['winner'] is None:
            cm['status'] = 'unknown_winner'
    return cmatches, placements


def edit_distance(a, b):
    a, b = a.lower(), b.lower()
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def fuzzy_pick(text, cands, name):
    """text = 'Baima 6-4'; cands = wrestler ids; pick the one whose surname (or full name) is within 2 edits
    of the text's leading word(s). Returns (id, rest) or (None, text)."""
    m = RES_TAIL.search(' ' + text)
    who = (' ' + text)[:m.start()].strip() if m else text
    rest = m.group(1) if m else ''
    scored = []
    for w in cands:
        parts = name[w].split()
        forms = [name[w]] + [' '.join(parts[k:]) for k in range(1, len(parts))]
        scored.append((min(edit_distance(who, f) for f in forms), w))
    scored.sort()
    if scored and scored[0][0] <= 2 and (len(scored) == 1 or scored[1][0] > scored[0][0]):
        return scored[0][1], rest
    return None, text


PLACE_WORDS = {'Third': 3, 'Fourth': 4, 'Fifth': 5, 'Sixth': 6, 'Seventh': 7, 'Eighth': 8}
PLACE_LAB = re.compile(r'^(Third|Fourth|Fifth|Sixth|Seventh|Eighth) Place:$')


def parse_tree_cons(wt, citems, entrants, discrepancies, lost_in_champ=frozenset()):
    """1941+ drawn consolation bracket, read as a tree from its geometry.
    A text without a school is a bout result (winner [+score]) and its two feeders are
    the nearest items above/below it in the column to its left, within the band that
    belongs to it. Texts with a school (or 'Bye') are wrestlers entering the tree.
    Place bouts come from the box: 'Third Place: <winner, school score>' / 'Fourth Place:
    <loser>' (likewise 5th/6th, 7th/8th)."""
    box = {}
    labs = [i for i in citems if PLACE_LAB.match(i['s'])]
    used = set(id(l) for l in labs)
    for lab in labs:
        val = next((i for i in citems if i['y'] == lab['y'] and i['x'] > lab['x']), None)
        if val:
            box[PLACE_WORDS[PLACE_LAB.match(lab['s']).group(1)]] = val['s']
            used.add(id(val))
    items = [i for i in citems if id(i) not in used]
    cols = cluster_x(items, tol=20)      # consolation columns drift a few points; columns are >100pt apart
    is_entry = lambda i: i['s'] == 'Bye' or bool(re.match(r'^[^,\d]+, [^\d\s]', i['s']))   # 'Surname, School': no digits before the comma
    name = {e['id']: e['name'] for e in entrants}

    def find(txt):
        if txt == 'Bye':
            return None
        sur, _, school = txt.partition(', ')
        sm = re.search(r'\s*\[(\d+|US)\]$', school)
        if sm: school = school[:sm.start()]
        for pool in ([e for e in entrants if e['school'] == school],
                     [e for e in entrants if len(school) >= 8 and e['school'].startswith(school)],   # truncated school
                     entrants):
            hits = [e['id'] for e in pool if e['name'] == sur or e['name'].endswith(' ' + sur)]
            if len(hits) == 1:
                return hits[0]
        pool = [e for e in entrants if e['school'] == school or (len(school) >= 8 and e['school'].startswith(school))]
        close = [e['id'] for e in pool if edit_distance(e['name'].split()[-1], sur.split()[-1]) <= 2]
        if len(close) == 1:
            discrepancies.append(f'{wt} consolation: source prints "{txt}"; taken as {name[close[0]]} (spelling)')
            return close[0]
        # not in the championship draw at all, but named (full name + school) in the place box
        for v in box.values():
            m = RES_TAIL.search(v)
            who = v[:m.start()] if m else v
            n2, _, s2 = who.partition(', ')
            if n2.split() and n2.split()[-1] == sur and (s2 == school or s2.startswith(school)):
                nid = f'{wt}-X{len([e for e in entrants if e["id"].startswith(f"{wt}-X")]) + 1:02d}'
                entrants.append({'id': nid, 'line': None, 'seed': None, 'name': n2, 'school': s2,
                                 'consolation_only': True})
                name[nid] = n2
                discrepancies.append(f'{wt}: {n2} ({s2}) is missing from the championship draw on the sheet but '
                                     f'wrestles in the consolations and is in the place box; added as a consolation-only '
                                     f'wrestler (his championship-bracket bouts are not recorded)')
                return nid
        discrepancies.append(f'{wt} consolation: cannot identify "{txt}"')
        return None

    def full(txt):
        """'Tom Balent, Penn State 5-3' -> (id, result)"""
        m = RES_TAIL.search(txt)
        raw = m.group(1) if m else ''
        who = txt[:m.start()] if m else txt
        n, _, sc = who.partition(', ')
        wid = next((e['id'] for e in entrants if e['name'] == n and e['school'] == sc), None) or \
              next((e['id'] for e in entrants if e['name'] == n), None) or \
              (find(f"{n.split()[-1]}, {sc}") if n else None)
        return wid, raw

    def winner_in(text, cands, note=True):
        hits = []
        for w in sorted([c for c in cands if c], key=lambda w: -len(name[w])):
            parts = name[w].split()
            for k, form in enumerate([name[w]] + [' '.join(parts[j:]) for j in range(1, len(parts))]):
                if text == form or text.startswith(form + ' '):
                    hits.append((k == 0, len(form), w, text[len(form):].strip()))
                    break
        if not hits:
            return None, text
        hits.sort(key=lambda h: (not h[0], -h[1]))
        best = [h for h in hits if (h[0], h[1]) == (hits[0][0], hits[0][1])]
        if len(best) > 1 and not note:
            return None, text
        if len(best) > 1:
            # same printed surname for both wrestlers: the one who places later (place box) must have won
            placed = [h for h in best if h[2] in place_of]
            pick = placed[0] if len(placed) == 1 else best[0]
            discrepancies.append(f'{wt} consolation: "{text}" fits both {" and ".join(name[h[2]] for h in best)}; '
                                 f'taken as {name[pick[2]]}' + (' (he is in the place box)' if len(placed) == 1
                                                                 else ' (could not be resolved)'))
            return pick[2], pick[3]
        return hits[0][2], hits[0][3]

    # node table
    nodes = []
    for ci, col in enumerate(cols):
        for it in col:
            nodes.append({'it': it, 'col': ci, 'leaf': is_entry(it), 'kids': [], 'parent': None})
    bycol = defaultdict(list)
    for n in nodes:
        bycol[n['col']].append(n)
    for ci in bycol:
        bycol[ci].sort(key=lambda n: -n['it']['y'])
    for n in nodes:
        if n['leaf'] or n['col'] == 0:
            continue
        same = [m for m in bycol[n['col']] if not m['leaf']]   # only results bound a result's band
        k = same.index(n)
        hi = (same[k - 1]['it']['y'] + n['it']['y']) / 2 if k > 0 else 1e9
        lo = (same[k + 1]['it']['y'] + n['it']['y']) / 2 if k + 1 < len(same) else -1e9
        prev = [c for c in bycol[n['col'] - 1] if lo < c['it']['y'] < hi and c['parent'] is None]
        above = [c for c in prev if c['it']['y'] >= n['it']['y']]
        below = [c for c in prev if c['it']['y'] < n['it']['y']]
        top_kid = min(above, key=lambda c: c['it']['y']) if above else None
        bot_kid = max(below, key=lambda c: c['it']['y']) if below else None
        kids = [k for k in (top_kid, bot_kid) if k]
        for c in kids:
            c['parent'] = n
        n['kids'] = kids
        n['top_kid'], n['bot_kid'] = top_kid, bot_kid
    # resolve bottom-up by column
    places = {p: full(t) for p, t in box.items()}
    place_of = {wid: p for p, (wid, _) in places.items() if wid}
    ncols = len(cols)
    rnames = {}
    order = list(range(1, ncols))
    for j, ci in enumerate(reversed(order)):
        rnames[ci] = ['C_SF', 'C_QF'][j] if j < 2 else None
    k = 1
    for ci in order:
        if rnames[ci] is None:
            rnames[ci] = f'C_R{k}'; k += 1
    # positional bout numbers: slots per round column, bout # = which slot (top to bottom) the result sits in
    leaves = {ci: sum(1 for n in bycol[ci] if n['leaf']) for ci in range(ncols)}
    slots = {}
    for ci in range(1, ncols):
        slots[ci] = (leaves[0] // 2 if ci == 1 else leaves[ci - 1] if leaves[ci - 1] else max(1, slots[ci - 1] // 2)) or 1
    ys = [n['it']['y'] for n in nodes]
    ytop, ybot = max(ys) + 8, min(ys) - 8
    taken = defaultdict(set)

    def slot(n):
        col = [m for m in bycol.get(n['col'], []) if not m['leaf']]
        if n in col and len(col) == slots[n['col']]:
            k = col.index(n) + 1                       # full round: rank top to bottom
        else:
            f = (ytop - n['it']['y']) / (ytop - ybot)
            k = min(slots[n['col']] - 1, max(0, int(f * slots[n['col']]))) + 1
        while k in taken[n['col']]:
            k += 1
        taken[n['col']].add(k)
        return k

    cm, counters = [], defaultdict(int)
    for ci in range(ncols):
        for n in bycol[ci]:
            if n['leaf']:
                n['w'] = find(n['it']['s'])
                continue
            if ci == 0:
                discrepancies.append(f'{wt} consolation: result "{n["it"]["s"]}" in first column'); n['w'] = None
                continue
            ws = [c.get('w') for c in n['kids']]
            unk = [c for c in n['kids'] if c.get('unknown_id')]          # feeder bout whose winner is unknown
            real = [w for w in ws if w]
            w, raw = winner_in(n['it']['s'], real)
            if w is None and real:
                w, raw = fuzzy_pick(n['it']['s'], real, name)
                if w:
                    discrepancies.append(f'{wt} consolation: source prints "{n["it"]["s"]}"; taken as {name[w]} (spelling)')
            if w is None and real:
                # sheet put the wrong wrestler in an entry slot? the printed winner lost in the championship
                # bracket, is not anywhere else in the consolations, and one feeder is a plain entry slot
                x, xraw = winner_in(n['it']['s'], [e['id'] for e in entrants], note=False)
                leaf_kids = [c for c in n['kids'] if c['leaf'] and not c.get('w')] or \
                            [c for c in n['kids'] if c['leaf'] and c.get('w')]   # a 'Bye' in an entry slot first, else a wrong name
                elsewhere = {m.get('w') for m in nodes if m['leaf']}
                cons_only = {e['id'] for e in entrants if e.get('consolation_only')}
                if x and x not in real and x not in elsewhere and (x in lost_in_champ or x in cons_only) \
                        and len(leaf_kids) == 1:
                    old_w = leaf_kids[0].get('w')
                    discrepancies.append(f'{wt} consolation: sheet lists "{leaf_kids[0]["it"]["s"]}" in an entry slot but '
                                         f'prints "{n["it"]["s"]}" as that bout\'s winner; {name[x]} (eligible for the '
                                         f'consolations and appearing nowhere else on the sheet) taken as the entrant')
                    leaf_kids[0]['w'] = x
                    leaf_kids[0]['kind'] = 'entry'
                    real = [x if r == old_w else r for r in real] if old_w else real + [x]
                    w, raw = x, xraw
            if w is None and real:
                discrepancies.append(f'{wt} consolation: "{n["it"]["s"]}" is not one of {[name[x] for x in real]}')
            n['w'] = w
            n['kind'] = ('unidentified' if not w and n['it']['s'].strip() and len(real) < 2 and not unk
                         else 'advance' if len(real) == 1 and not unk else 'empty' if not real and not unk
                         else 'unrecorded' if len(real) == 2 and not w else 'bout')
            if len(real) == 2:
                bid = f'{wt}-{rnames[ci]}-{slot(n):02d}'
                n['bout_id'] = bid
                if not w:
                    n['unknown_id'] = bid
                    discrepancies.append(f'{wt} consolation {bid}: winner of {name[real[0]]} vs {name[real[1]]} unknown '
                                         f'(sheet prints "{n["it"]["s"]}")')
                cm.append({'id': bid, 'bracket': 'consolation',
                           'round': rnames[ci], 'label': rnames[ci], 'for_place': None,
                           'status': 'contested' if w else 'unknown_winner',
                           'winner': w, 'loser': (real[1] if w == real[0] else real[0]) if w else None,
                           'result': parse_result(raw) if raw else None, '_pair': tuple(real) if not w else (w, real[1] if w == real[0] else real[0])})
            elif len(real) == 1 and unk and w:
                # bout against the unknown winner of a feeder bout
                bid = f'{wt}-{rnames[ci]}-{slot(n):02d}'
                n['bout_id'] = bid
                cm.append({'id': bid, 'bracket': 'consolation', 'round': rnames[ci], 'label': rnames[ci],
                           'for_place': None, 'status': 'contested', 'winner': w, 'loser': None,
                           'result': parse_result(raw) if raw else None, '_pair': (w, None),
                           'unknown_side_from': {'winner_of': unk[0]['unknown_id']}})
    # orphans: entries/results never fed anywhere, i.e. a bout whose result is not printed
    roots = [n for n in nodes if n['parent'] is None and not n['leaf'] and n['col'] == ncols - 1]
    orphans = [n for n in nodes if n['parent'] is None and n.get('w') and n not in roots]
    by_c = defaultdict(list)
    for n in orphans:
        by_c[n['col']].append(n)
    for ci, grp in sorted(by_c.items()):
        grp.sort(key=lambda n: -n['it']['y'])
        while len(grp) >= 2:
            a, b = grp.pop(0), grp.pop(0)
            pa, pb = place_of.get(a['w'], 99), place_of.get(b['w'], 99)
            rn = rnames.get(ci + 1, 'C_SF')
            counters[rn] = slot({'it': {'y': (a['it']['y'] + b['it']['y']) / 2}, 'col': min(ci + 1, ncols - 1)})
            synth = {'it': {'y': (a['it']['y'] + b['it']['y']) / 2, 's': '(result not printed)'},
                     'col': min(ci + 1, ncols - 1) if ci + 1 < ncols else ci + 1, 'leaf': False,
                     'kids': [a, b], 'top_kid': a, 'bot_kid': b, 'parent': None, 'kind': 'bout', 'synthetic': True}
            a['parent'] = b['parent'] = synth
            nodes.append(synth)
            if pa != pb:
                w, l = (a['w'], b['w']) if pa < pb else (b['w'], a['w'])
                synth['w'] = w
                synth['bout_id'] = f'{wt}-{rn}-{counters[rn]:02d}'
                discrepancies.append(f'{wt} consolation {rn}: result not printed for {name[a["w"]]} vs {name[b["w"]]}; '
                                     f'{name[w]} taken as winner (he placed higher)')
                cm.append({'id': f'{wt}-{rn}-{counters[rn]:02d}', 'bracket': 'consolation', 'round': rn, 'label': rn,
                           'for_place': None, 'status': 'contested', 'winner': w, 'loser': l, 'result': None,
                           '_pair': (w, l)})
            else:
                synth['kind'] = 'unrecorded'
                discrepancies.append(f'{wt} consolation {rn}: result not printed for {name[a["w"]]} vs {name[b["w"]]}')
        for n in grp:
            if n['it']['s'] != 'Bye':
                discrepancies.append(f'{wt} consolation: "{n["it"]["s"]}" does not connect to any bout')
    # place bouts
    placements = []
    for p in (3, 5, 7):
        if p not in places:
            continue
        w, raw = places[p]
        l = places.get(p + 1, (None, ''))[0]
        if w and l:
            cm.append({'id': f'{wt}-{p}{"rd" if p == 3 else "th"}', 'bracket': 'consolation',
                       'round': f'{p}{"rd" if p == 3 else "th"}', 'label': f'{p} place', 'for_place': p,
                       'status': 'contested', 'winner': w, 'loser': l,
                       'result': parse_result(raw) if raw else None, '_pair': (w, l)})
        else:
            discrepancies.append(f'{wt}: place box {p}/{p+1} incomplete ({box.get(p)} / {box.get(p+1)})')
            if w: placements.append({'place': p, 'wrestler': w, 'method': 'listed'})
            if l: placements.append({'place': p + 1, 'wrestler': l, 'method': 'listed'})
    LAST_SHEET[wt] = export_sheet(nodes, cm)
    return cm, placements


LAST_SHEET = {}


def export_sheet(nodes, cm):
    """The consolation sheet as a tree: every drawn slot, with the two slots feeding each result.
    Blank lines on the sheet (no text, e.g. the 'winner' of Bye vs Bye) become explicit slots."""
    allnodes = list(nodes)
    maxcol = max((n['col'] for n in allnodes), default=0)
    wrestlerless = lambda n: n['leaf'] and not n.get('w') or n.get('kind') in ('empty', 'empty_result')
    # 1) two adjacent unconnected slots that carry no wrestler (Bye/Bye, blank/Bye) meet in a blank result;
    #    a result fed by a Bye while an unconnected blank result sits closer to it takes the blank result instead
    def swap_once():
        for n in allnodes:
            for side in ('top_kid', 'bot_kid'):
                k = n.get(side)
                if not k or not (k['leaf'] and not k.get('w')):
                    continue
                alt = [x for x in allnodes if x['col'] == k['col'] and x.get('parent') is None
                       and x.get('kind') == 'empty_result'
                       and abs(x['it']['y'] - n['it']['y']) < abs(k['it']['y'] - n['it']['y'])]
                if alt:
                    a = min(alt, key=lambda x: abs(x['it']['y'] - n['it']['y']))
                    k['parent'] = None; a['parent'] = n; n[side] = a
                    n['kids'] = [x for x in (n.get('top_kid'), n.get('bot_kid')) if x]
                    return True
        return False

    def pair_once():
        for c in range(0, maxcol):
            col = sorted([n for n in allnodes if n['col'] == c], key=lambda n: -n['it']['y'])
            for a, b in zip(col, col[1:]):
                if a.get('parent') is None and b.get('parent') is None and wrestlerless(a) and wrestlerless(b):
                    e = {'it': {'y': (a['it']['y'] + b['it']['y']) / 2, 's': ''}, 'col': c + 1, 'leaf': False,
                         'w': None, 'kind': 'empty_result', 'top_kid': a, 'bot_kid': b, 'parent': None,
                         'synthetic': True}
                    a['parent'] = b['parent'] = e
                    allnodes.append(e)
                    return True
        return False

    for _ in range(500):
        if not (swap_once() or pair_once()):
            break
    # 2) a result missing a feeder takes the nearest unconnected slot one column left, else a blank line
    for n in list(allnodes):
        if n['leaf'] or n.get('col', 0) == 0 or n.get('kind') is None:
            continue
        for side, off in (('top_kid', +6), ('bot_kid', -6)):
            if n.get(side) is not None:
                continue
            free = [x for x in allnodes if x['col'] == n['col'] - 1 and x.get('parent') is None]
            pref = [x for x in free if (x['it']['y'] >= n['it']['y']) == (side == 'top_kid')] or free
            if pref:
                e = min(pref, key=lambda x: abs(x['it']['y'] - n['it']['y']))
            else:
                e = {'it': {'y': n['it']['y'] + off, 's': ''}, 'col': n['col'] - 1, 'leaf': True, 'w': None,
                     'kind': 'empty', 'synthetic': True}
                allnodes.append(e)
            e['parent'] = n
            n[side] = e
    bycol = defaultdict(list)
    for n in allnodes:
        bycol[n['col']].append(n)
    ident = {}
    for c in sorted(bycol):
        for r, n in enumerate(sorted(bycol[c], key=lambda n: -n['it']['y']), start=1):
            ident[id(n)] = f'S{c + 1}.{r}'
    out = []
    for c in sorted(bycol):
        for n in sorted(bycol[c], key=lambda n: -n['it']['y']):
            if n['leaf']:
                kind = n.get('kind') or ('bye' if n['it']['s'] == 'Bye' else 'entry' if n.get('w') else 'unidentified')
                out.append({'slot': ident[id(n)], 'column': c + 1, 'kind': kind, 'wrestler': n.get('w'),
                            'printed': n['it']['s'] or None,
                            'feeds': ident.get(id(n['parent'])) if n.get('parent') else None})
            else:
                out.append({'slot': ident[id(n)], 'column': c + 1, 'kind': n.get('kind', 'bout'),
                            'wrestler': n.get('w'), 'bout': n.get('bout_id'), 'printed': n['it']['s'],
                            'top': ident.get(id(n.get('top_kid'))), 'bottom': ident.get(id(n.get('bot_kid'))),
                            'feeds': ident.get(id(n['parent'])) if n.get('parent') else None})
    return out


def parse_pigtails(wt, pitems, entrants, discrepancies):
    """'Championship Pigtail Bouts for 118' / 'Consolation Pigtail Bouts for 118' page:
    pairs of 'Name - School' lines with the winner's surname [+score] between them."""
    out = {'champ': [], 'cons': []}
    if pitems and isinstance(pitems[0], list):          # several pages: parse each on its own
        for page in pitems:
            sub = parse_pigtails(wt, page, entrants, discrepancies)
            out['champ'] += sub['champ']; out['cons'] += sub['cons']
        return out
    heads = sorted([i for i in pitems if re.match(r'^(Championship|Consolation) Pigtail Bouts', i['s'])],
                   key=lambda i: -i['y'])
    for hi, h in enumerate(heads):
        kind = 'champ' if h['s'].startswith('Championship') else 'cons'
        lo = heads[hi + 1]['y'] if hi + 1 < len(heads) else -1e9
        rows = sorted([i for i in pitems if lo < i['y'] < h['y'] and i['x'] == h['x']], key=lambda i: -i['y'])
        res = [i for i in pitems if lo < i['y'] < h['y'] and i['x'] > h['x'] + 50]
        for a, b in zip(rows[0::2], rows[1::2]):
            r = next((i for i in res if b['y'] < i['y'] < a['y']), None)
            sides = []
            for row in (a, b):
                if ' - ' in row['s']:
                    n, _, sc = row['s'].partition(' - ')
                else:                                          # 1983+ style 'Name, School'
                    n, _, sc = row['s'].partition(', ')
                if ', ' in n:                                  # 1980 style 'Last, First'
                    last, _, first = n.partition(', ')
                    n = f'{first} {last}'
                sm = re.search(r'\s*\[(\d+|US)\]$', sc)
                seed = int(sm.group(1)) if sm and sm.group(1).isdigit() else None
                if sm: sc = sc[:sm.start()]
                wid = next((e['id'] for e in entrants if e['name'] == n and e['school'] == sc), None) or \
                      next((e['id'] for e in entrants if e['name'] == n), None)
                if not wid:
                    wid = f'{wt}-P{len([e for e in entrants if e["line"] is None]) + 1:02d}'
                    entrants.append({'id': wid, 'line': None, 'seed': seed, 'name': n, 'school': sc})
                sides.append(wid)
            w, raw = None, ''
            if r:
                for wid in sides:
                    nm = next(e['name'] for e in entrants if e['id'] == wid)
                    parts = nm.split()
                    for form in [nm] + [' '.join(parts[k:]) for k in range(1, len(parts))]:
                        if r['s'] == form or r['s'].startswith(form + ' '):
                            w, raw = wid, r['s'][len(form):].strip()
                            break
                    if w: break
            if not w:
                discrepancies.append(f'{wt} {kind} pigtail: winner not identified ({a["s"]} vs {b["s"]}: {r and r["s"]})')
            out[kind].append((sides, w, raw))
    return out


def resolve_sources(matches):
    """For every consolation bout, record where each participant came from (the last
    bout they were in), and for every bout record where winner/loser went next."""
    order = [m['id'] for m in matches]
    for i, m in enumerate(matches):
        if m['bracket'] != 'consolation':
            continue
        sides = []
        for wid in m.pop('_pair'):
            src = None
            if wid is None:
                sides.append({'from': m.pop('unknown_side_from', None), 'wrestler': None})
                continue
            for pm in reversed(matches[:i]):
                if pm.get('winner') == wid:
                    src = {'winner_of': pm['id']}; break
                if pm.get('loser') == wid:
                    src = {'loser_of': pm['id']}; break
            sides.append({'from': src, 'wrestler': wid})
        # no drawn slots for place bouts: order sides by where they came from (earlier bout first)
        def src_idx(sd):
            ref = sd['from'] and (sd['from'].get('winner_of') or sd['from'].get('loser_of'))
            return order.index(ref) if ref in order else -1
        sides.sort(key=src_idx)
        m['top'], m['bottom'] = sides
        # key order tidy
        for k in ('winner', 'loser', 'result'):
            m[k] = m.pop(k)
    for i, m in enumerate(matches):
        m['winner_to'] = m['loser_to'] = None
        for side_key, wid in (('winner_to', m.get('winner')), ('loser_to', m.get('loser'))):
            if not wid:
                continue
            for nm in matches[i + 1:]:
                for slot in ('top', 'bottom'):
                    if nm[slot]['wrestler'] == wid:
                        m[side_key] = {'match': nm['id'], 'slot': slot}
                        break
                if m[side_key]:
                    break
    # a bout whose winner is unknown feeds the bout that names it as an unknown side
    byid = {m['id']: m for m in matches}
    for m in matches:
        for side in ('top', 'bottom'):
            sd = m.get(side) or {}
            if sd.get('wrestler') is None and (sd.get('from') or {}).get('winner_of') in byid:
                byid[sd['from']['winner_of']]['winner_to'] = {'match': m['id'], 'slot': side}


def parse_summary(items):
    """Page 1: placewinners with the result that clinched each place."""
    out = {}
    rows = defaultdict(list)
    for it in items:
        rows[it['y']].append(it)
    cur = None
    for y in sorted(rows, reverse=True):
        row = sorted(rows[y], key=lambda i: i['x'])
        for j, it in enumerate(row):
            if re.fullmatch(r'\d{3}|UNL|HWT|Hwt', it['s']) and it['x'] < 80:
                cur = it['s']; out[cur] = {}
            m = re.fullmatch(r'(\d)(st|nd|rd|th):', it['s'])
            if m and cur and j + 1 < len(row):
                t = re.match(r'^(.*?)(?: \[(\d+|US)\])? - (.*?)(?: \((.*)\))?$', row[j + 1]['s'])
                if t:
                    out[cur][int(m.group(1))] = {'name': t.group(1), 'school': t.group(3), 'result_raw': t.group(4),
                                                 'seed': t.group(2)}
    return out


def build_meta(items, base):
    """Header facts from the summary page; format/legend text comes from base (meta/_base.json)."""
    rows = defaultdict(list)
    for it in items:
        rows[it['y']].append(it)
    txt = [' '.join(i['s'] for i in sorted(rows[y], key=lambda i: i['x'])) for y in sorted(rows, reverse=True)]
    flat = '\n'.join(txt)
    meta = dict(base)
    yr = next(int(i['s']) for i in items if re.fullmatch(r'19\d\d|20\d\d', i['s']))
    ed = re.search(r'(\d+)(?:st|nd|rd|th) NCAA Wrestling Tournament', flat)
    dt = re.search(r'(\d+)/(\d+)/(\d{4}) (?:to|and) (\d+)/(\d+)/(\d{4}) at (.*)', flat)
    host = dt.group(7).strip() if dt else None
    if not dt:
        at = re.search(r'^At (.*)$', flat, re.M)
        host = at.group(1) if at else None
    meta.update({'year': yr, 'edition': int(ed.group(1)) if ed else None, 'host': host,
                 'dates': [f'{dt.group(3)}-{int(dt.group(1)):02d}-{int(dt.group(2)):02d}',
                           f'{dt.group(6)}-{int(dt.group(4)):02d}-{int(dt.group(5)):02d}'] if dt else None})
    # the 1928 summary has no dates on page 1; fall back to base
    lab = lambda rx: next((i for i in items if re.fullmatch(rx, i['s'])), None)
    def right_of(l):
        if not l: return None
        cand = sorted([i for i in items if abs(i['y'] - l['y']) <= 2 and i['x'] > l['x']], key=lambda c: c['x'])
        stop = next((k for k, c in enumerate(cand) if c['s'].endswith(':')), None)   # next label on the row
        cand = cand[:stop] if stop is not None else cand
        out = [c['s'] for c in sorted(cand, key=lambda c: c['x'])]
        # continuation lines directly under (e.g. two Outstanding Wrestlers)
        x0 = min((c['x'] for c in cand), default=None)
        nxt = [i['s'] for i in items if x0 is not None and i['x'] == x0 and 0 < l['y'] - i['y'] <= 16
               and not any(abs(j['y'] - i['y']) <= 2 and j['x'] < x0 for j in items)]
        return ' '.join(out + nxt) or None
    tc_lab = lab(r'.*Team Champions?')
    tc = right_of(tc_lab)
    meta['team_champion_label'] = tc_lab['s'] if tc_lab else None
    m = re.match(r'^(.*?) - (\d+(?:\.\d+)?) Points$', tc or '')
    meta['team_champion'] = m.group(1) if m else tc
    ow = right_of(lab(r'Outstanding Wrestlers?:?'))
    meta['outstanding_wrestler'] = None if (not ow or ow == 'None Selected') else ow
    ga = right_of(lab(r'Gorriaran Award:?'))
    if ga:
        meta['gorriaran_award'] = ga
    # team scores: rank / team / points / (champs) in two side-by-side columns
    ts = []
    hdr = lab(r'(Unofficial )?Top Ten Team Scores')
    meta['team_scores_official'] = bool(hdr) and not hdr['s'].startswith('Unofficial')
    cp = lab(r'Champions and Place Winners')
    if hdr and cp:
        body = [i for i in items if cp['y'] < i['y'] < hdr['y']]
        for y in sorted({i['y'] for i in body}, reverse=True):
            r = sorted([i for i in body if i['y'] == y], key=lambda i: i['x'])
            for half in (r[:], ):
                pass
            left = [i for i in r if i['x'] < 330]
            right = [i for i in r if i['x'] >= 330]
            for part in (left, right):
                vals = [i['s'] for i in part]
                if len(vals) >= 3 and vals[0].isdigit():
                    ch = next((v for v in vals[3:] if re.fullmatch(r'\(\d+\)', v)), None)
                    ts.append({'rank': int(vals[0]), 'team': vals[1], 'points': float(vals[2]) if '.' in vals[2] else int(vals[2]),
                               'champions': int(ch[1:-1]) if ch else 0})
    ts.sort(key=lambda t: (t['rank'], -t['points']))
    meta['team_scoring'] = bool(ts)
    meta['team_scores'] = ts
    return meta


def main(raw_path, meta_path):
    pages = load_pages(raw_path)
    base = json.load(open(meta_path))
    meta = build_meta(pages[0], base)
    if not meta.get('dates'):
        for pg in pages[1:]:
            for it in pg:
                dt = re.match(r'(\d+)/(\d+)/(\d{4}) (?:to|and) (\d+)/(\d+)/(\d{4})', it['s'])
                if dt:
                    meta['dates'] = [f'{dt.group(3)}-{int(dt.group(1)):02d}-{int(dt.group(2)):02d}',
                                     f'{dt.group(6)}-{int(dt.group(4)):02d}-{int(dt.group(5)):02d}']
                    break
            if meta.get('dates'):
                break
    yr = meta['year']
    src = dict(base['source'])
    src['url'] = src.pop('url_pattern').format(year=yr)
    src['incomplete_consolations'] = yr in src.pop('incomplete_consolation_years')
    meta['source'] = src
    summary = parse_summary(pages[0])
    weights = []
    ladder_audit = []
    for wt, parts in split_pages(pages):
        disc = []
        wt, entrants, champ, cons, autos = parse_weight_page(wt, parts['bracket'], parts['cons'], disc, parts.get('pig'))
        matches = champ + cons
        resolve_sources(matches)
        final = next(m for m in champ if m['round'] == 'F')
        places = {1: {'place': 1, 'wrestler': final['winner'], 'decided_by': final['id']}}
        ladder = parts.get('style') == 'ladder'
        if ladder:
            places[2] = {'place': 2, 'wrestler': final['loser'], 'decided_by': final['id']}
            for cm in cons:
                if cm['round'] in ('3rd', '5th', '7th'):
                    p = int(cm['round'][0])
                    places[p] = {'place': p, 'wrestler': cm['winner'], 'decided_by': cm['id']}
                    places[p + 1] = {'place': p + 1, 'wrestler': cm['loser'], 'decided_by': cm['id']}
        for cm in cons:
            if cm['for_place'] and cm['round'].endswith('-F'):
                places[cm['for_place']] = {'place': cm['for_place'], 'wrestler': cm['winner'], 'decided_by': cm['id']}
        for a in autos:
            places[a['place']] = {'place': a['place'], 'wrestler': a['wrestler'], 'decided_by': None,
                                  'method': a['method']}
        placements = [places[p] for p in sorted(places)]
        # cross-check against page-1 summary
        name_of = {e['id']: e['name'] for e in entrants}
        allm = {m['id']: m for m in matches}
        for p in placements:
            s = summary.get(wt, {}).get(p['place'])
            if not s:
                continue
            if s['name'] != name_of.get(p['wrestler']):
                disc.append(f'{wt} place {p["place"]}: summary says {s["name"]}, bracket says {name_of.get(p["wrestler"])}')
            p['summary_result_raw'] = s['result_raw']
            bm = allm.get(p['decided_by'])
            if not s['result_raw']:
                continue
            bres = (bm or {}).get('result') or {}
            fam = lambda t: 'FORFEIT' if t in ('MFF', 'FF', 'DEF') else t
            if bm and fam(parse_result(s['result_raw'])['type']) != fam(bres.get('type')):
                disc.append(f'{wt} place {p["place"]}: summary result "{s["result_raw"]}" vs bout {bm["id"]} "{bres.get("raw")}"')
            elif bm and fam(bres.get('type')) != 'FORFEIT' and parse_result(s['result_raw'])['time'] != bres.get('time'):
                disc.append(f'{wt} place {p["place"]}: summary time "{s["result_raw"]}" vs bout {bm["id"]} "{bres.get("raw")}"')
        # Bergman eligibility audit (informational): who lost to the 1st/2nd placer but never wrestled back
        notes = []
        cons_ids = {m['id'] for m in cons}
        in_cons = {sd['wrestler'] for m in cons for sd in (m['top'], m['bottom'])}
        if ladder:
            # who is eligible for consolations? find the tightest tier that covers this weight's consolation field
            tiers = {}
            r16 = 'R2' if any(m['round'] == 'R2' for m in champ) and len([m for m in champ if m['round'] == 'R2']) == 8 else 'R1'
            pig_only = {e['id'] for e in entrants if e.get('line') is None}
            in_cons = in_cons - pig_only
            for tier, rnds in (('finalists', ('F',)), ('semifinalists', ('SF',)), ('quarterfinalists', ('QF',)),
                               ('all', None)):
                bouts = [m for m in champ if m['round'] != 'PIG' and m['loser'] and m['id'] != final['id']]
                if rnds is None:
                    tiers[tier] = {m['loser'] for m in bouts}
                    continue
                players = {x for m in champ if m['round'] in rnds for x in (m['winner'], m['loser']) if x}
                tiers[tier] = {m['loser'] for m in bouts if m['winner'] in players}
            weight_tier = next((t for t, v in tiers.items() if not (in_cons - {None}) - v), 'unclear')
            ladder_audit.append((wt, weight_tier, tiers, in_cons, disc, notes, name_of, placements))
        for p in placements:
            if ladder or p['place'] not in (1, 2):
                continue
            beaten = [m['loser'] for m in champ if m['winner'] == p['wrestler'] and m['loser']]
            placed = {q['wrestler'] for q in placements if q['place'] <= p['place'] + 1}
            skipped = [b for b in beaten if b not in in_cons and b not in placed]
            if skipped:
                notes.append(f'lost to the {"champion" if p["place"]==1 else "2nd-place winner"} but no wrestle-back bout listed: '
                             + ', '.join(f'{name_of[b]} ({b})' for b in skipped))
        if wt in LAST_SHEET:
            parts['sheet'] = LAST_SHEET.pop(wt)
        weights.append({'consolation_sheet': parts.get('sheet'), 'notes': notes, 'weight': wt, 'draw_size': len([1 for m in champ if m['round'] == 'R1']) * 2,
                        'entrant_count': len(entrants), 'entrants': entrants,
                        'matches': matches, 'placements': placements, 'discrepancies': disc})
    out = dict(meta)
    if ladder_audit:
        from collections import Counter
        cnt = Counter(t for _, t, *_ in ladder_audit)
        order_t = ['finalists', 'semifinalists', 'quarterfinalists', 'all']
        # the year's rule = the tier most weights need (ties go to the looser tier); outliers get flagged
        year_tier = max((t for t in order_t if cnt[t]), key=lambda t: (cnt[t], order_t.index(t)), default='unclear')
        for wt, wtier, tiers, in_cons, disc, notes, name_of, placements in ladder_audit:
            if year_tier not in tiers:
                continue
            victims = tiers[year_tier]
            placed = {q['wrestler'] for q in placements}
            missing = victims - in_cons - placed
            extra = in_cons - victims - {None}
            if missing:
                notes.append(('lost in the championship bracket' if year_tier == 'all' else f'lost to one of the {year_tier}')
                             + ' but not in the consolation bracket: '
                             + ', '.join(f'{name_of[b]} ({b})' for b in sorted(missing)))
            if extra:
                disc.append('in the consolation bracket without ' + ('a championship loss' if year_tier == 'all' else f'having lost to one of the {year_tier}')
                            + ': '
                            + ', '.join(f'{name_of[b]} ({b})' for b in sorted(extra)))
        maxp = max(len(w['placements']) for w in weights)
        rules = {
            'finalists': 'Only wrestlers who lost to one of the two finalists wrestle back: one consolation tree per '
                         'half, fed in the order they lost (earliest first), ending with the finalist\'s semifinal victim.',
            'semifinalists': 'Wrestlers who lost to any of the four semifinalists wrestle back: one consolation tree '
                             'per quarter, the quarter winners meet in pairs, and the survivors meet the semifinal '
                             'losers.',
            'quarterfinalists': 'Wrestlers who lost to any of the eight quarterfinalists wrestle back.',
            'round_of_16': 'Wrestlers who lost to anyone who reached the round of 16 wrestle back.',
            'all': 'Full wrestle-back: every championship-bracket loser (except the finalist) enters the consolation '
                   'bracket, first-round losers first, then round-of-16, quarterfinal and semifinal losers feed in.'}
        out['format'] = {
            'consolation_system': f'wrestleback_to_{year_tier}',
            'consolation_rules': rules.get(year_tier, 'unclear') + ' The finals loser is 2nd with no further bout; '
                                 'the two consolation winners wrestle for 3rd/4th' +
                                 (', the losers of the last consolation round for 5th/6th' if maxp >= 6 else '') +
                                 (', and the losers of the round before for 7th/8th' if maxp >= 8 else '') + '.',
            'weights_by_tier': dict(cnt),
            'placements_awarded': maxp, 'bout_order_known': False}
    out['weights'] = weights
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == '__main__':
    main(*sys.argv[1:3])
