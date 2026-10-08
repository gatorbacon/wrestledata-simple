// tools/compare.js — MatSavant "Compare Wrestlers": two pickers, then head-to-head + common opponents.
// Port of KentuckyMat's compare.js. The comparison logic is the shared /compare_core.js (CompareCore);
// this file is UI, URL state and data loading.
//
// NCAA has no frontend career files, so a career is assembled here from the per-season profiles
// (/data/wrestlers/{season}/by_id/{id}.json), using /data/careers/career_seasons.json (built by
// scripts/reports/build_career_seasons.py) to find every season of a wrestler and to give each
// opponent a cross-season career id (NCAA profiles ship opponent_career_id = null).
//
// URL: /tools/compare.html?a={wrestler_id}&b={wrestler_id}[&season=2026]   (any season's id works)
(function () {
  'use strict';

  const MIN_CHARS = 2;
  const MAX_RESULTS = 8;
  const ID_RE = /^\d+$/;
  const CORE = window.CompareCore;

  // ---------- helpers ----------
  function $(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function careerKey(num) { return 'career_' + String(num).padStart(6, '0'); }

  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function fmtDate(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
    return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}` : (iso || '');
  }

  const METHOD_LABELS = {
    'FALL': 'Fall', 'DEC': 'Dec', 'MD': 'Maj Dec', 'TF': 'Tech Fall',
    'SV-1': 'SV-1', 'SV-2': 'SV-2', 'SV-3': 'SV-3', 'TB-1': 'TB-1', 'TB-2': 'TB-2', 'TB-3': 'TB-3',
    'DFLT': 'Default', 'DQ': 'DQ', 'INJ': 'Inj Def'
  };
  const RESULT_LABELS = Object.assign({}, METHOD_LABELS, { 'MD': 'Major' });

  function methodText(m) {
    const key = (m.method || '').toUpperCase();
    let text = METHOD_LABELS[key] || m.method || '';
    if (key === 'FALL') { if (m.duration && m.duration !== '0:00') text += ' ' + m.duration; }
    else if (m.score) text += ' ' + m.score;
    return text.trim();
  }

  // ---------- career lookup ----------
  // ID_INFO: wrestler_id -> {num, season}; CAREER_SEASONS: num -> {season: wrestler_id}
  let lookupPromise = null;
  let ID_INFO = new Map();
  let CAREER_SEASONS = {};
  function loadLookup() {
    if (!lookupPromise) {
      lookupPromise = fetch('/data/careers/career_seasons.json')
        .then(function (r) { if (!r.ok) throw new Error('career lookup ' + r.status); return r.json(); })
        .then(function (d) {
          CAREER_SEASONS = d.careers || {};
          Object.keys(CAREER_SEASONS).forEach(function (num) {
            const seasons = CAREER_SEASONS[num];
            Object.keys(seasons).forEach(function (s) { ID_INFO.set(seasons[s], { num: num, season: s }); });
          });
        })
        .catch(function (err) { console.warn('Compare: career lookup unavailable', err); });
    }
    return lookupPromise;
  }

  function latestIdForCareer(careerId) {
    const num = String(Number(String(careerId).replace('career_', '')));
    const seasons = CAREER_SEASONS[num];
    if (!seasons) return null;
    const years = Object.keys(seasons).sort();
    return seasons[years[years.length - 1]];
  }

  // ---------- profiles ----------
  const profileCache = new Map();
  function fetchProfile(season, id) {
    const key = season + '/' + id;
    if (!profileCache.has(key)) {
      profileCache.set(key, fetch(`/data/wrestlers/${season}/by_id/${id}.json`)
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; }));
    }
    return profileCache.get(key);
  }

  let seasonsListPromise = null;
  function knownSeasons() {
    if (!seasonsListPromise) {
      seasonsListPromise = fetch('/data/wrestlers/available_seasons.json')
        .then(function (r) { return r.ok ? r.json() : [2026]; })
        .then(function (list) { return list.map(String); })
        .catch(function () { return ['2026']; });
    }
    return seasonsListPromise;
  }

  // {season: wrestler_id} for the wrestler behind `id` (any season's id).
  async function seasonsForId(id) {
    await loadLookup();
    const info = ID_INFO.get(id);
    if (info) return { num: info.num, seasons: CAREER_SEASONS[info.num] };
    // Not career-linked: find its season by probing, then trust its own season_summary.
    for (const season of await knownSeasons()) {
      const p = await fetchProfile(season, id);
      if (!p) continue;
      const seasons = {};
      (p.season_summary || []).forEach(function (s) { if (s.wrestler_id) seasons[String(s.season)] = String(s.wrestler_id); });
      if (!Object.keys(seasons).length) seasons[season] = id;
      return { num: null, seasons: seasons };
    }
    throw new Error('No profile found for wrestler ' + id);
  }

  function parseRecord(rec) {
    const m = /^(\d+)-(\d+)/.exec((rec && rec.overall) || '');
    return m ? [Number(m[1]), Number(m[2])] : [0, 0];
  }

  // Build a CompareCore career object: {career_id, canonical_name, career_record, seasons:[{season, matches, ...}]}.
  const careerCache = new Map();
  function loadCareer(id) {
    if (!careerCache.has(id)) {
      careerCache.set(id, (async function () {
        const found = await seasonsForId(id);
        const years = Object.keys(found.seasons).sort(function (a, b) { return b - a; });
        const profiles = await Promise.all(years.map(function (y) { return fetchProfile(y, found.seasons[y]); }));
        const seasons = [];
        let wins = 0, losses = 0;
        profiles.forEach(function (p, i) {
          if (!p) return;
          const season = Number(years[i]);
          const wl = parseRecord(p.record);
          wins += wl[0]; losses += wl[1];
          seasons.push({
            season: season,
            wrestler_id: String(p.wrestler_id),
            team: p.team,
            weight_class: p.weight_class,
            current_rank: p.current_rank,
            matches: (p.match_list || []).map(function (m) {
              const opp = m.opponent_id != null ? ID_INFO.get(String(m.opponent_id)) : null;
              return Object.assign({}, m, {
                season: season,
                opponent_career_id: m.opponent_career_id || (opp ? careerKey(opp.num) : null)
              });
            })
          });
        });
        if (!seasons.length) throw new Error('No profile found for wrestler ' + id);
        const latest = profiles.find(Boolean);
        const total = wins + losses;
        return {
          career_id: found.num ? careerKey(found.num) : 'wid_' + id,
          canonical_name: latest.name,
          latest_id: String(latest.wrestler_id),
          career_record: { wins: wins, losses: losses, win_pct: total ? wins / total : null },
          seasons: seasons
        };
      })().catch(function (err) { careerCache.delete(id); throw err; }));
    }
    return careerCache.get(id);
  }

  // ---------- search (shared ranking from header.js: window.MatSavantSearch) ----------
  let FUSE = null;
  function getFuse() {
    if (!FUSE) {
      FUSE = new Fuse((window.SEARCH_INDEX || []).filter(function (i) { return i.type === 'wrestler'; }),
        window.MatSavantSearch.fuseOptions);
    }
    return FUSE;
  }

  function idFromItem(item) {
    // wrestler_id since 2026-10-07 (urls became /wrestler/<name>); older index: parse ?id=
    if (item.wrestler_id) return String(item.wrestler_id);
    try { return new URL(item.url, location.origin).searchParams.get('id'); } catch (e) { return null; }
  }

  function searchWrestlers(query, excludeId) {
    return window.MatSavantSearch.rankResults(query, getFuse().search(query))
      .map(function (r) { return Object.assign(r, { id: idFromItem(r.item) }); })
      .filter(function (r) { return r.id && r.id !== excludeId; })
      .slice(0, MAX_RESULTS);
  }

  // ---------- state ----------
  const state = { a: null, b: null, season: 'all', careers: null }; // pick = {id, name, sub, fromIndex}
  const slots = {};

  function pickFromItem(item, id) {
    return { id: id, name: item.name, sub: item.secondary || '', fromIndex: true };
  }

  function createSlot(root, which, label) {
    root.textContent = '';
    root.appendChild(el('div', 'cmp-slot-label', label));

    const wrap = el('div', 'search-container');
    const input = el('input', 'search-input');
    input.type = 'text';
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.placeholder = window.matchMedia('(max-width: 680px)').matches ? 'Search name…' : 'Search wrestler name…';
    input.setAttribute('aria-label', label + ' name');
    const dropdown = el('div', 'search-dropdown');
    dropdown.style.display = 'none';
    wrap.appendChild(input);
    wrap.appendChild(dropdown);
    root.appendChild(wrap);

    const chip = el('div', 'cmp-chip');
    chip.style.display = 'none';
    const chipText = el('div', 'cmp-chip-text');
    const chipName = el('div', 'cmp-chip-name');
    const chipSub = el('div', 'cmp-chip-sub');
    const chipDetail = el('div', 'cmp-chip-detail');
    chipText.appendChild(chipName);
    chipText.appendChild(chipSub);
    chipText.appendChild(chipDetail);
    const clearBtn = el('button', 'cmp-btn cmp-clear', '×');
    clearBtn.type = 'button';
    clearBtn.title = 'Clear';
    clearBtn.setAttribute('aria-label', 'Clear ' + label);
    chip.appendChild(chipText);
    chip.appendChild(clearBtn);
    root.appendChild(chip);

    let current = [];
    let activeIndex = -1;

    function hide() { dropdown.style.display = 'none'; activeIndex = -1; }

    function setActive(i) {
      activeIndex = i;
      Array.prototype.forEach.call(dropdown.querySelectorAll('.search-result'), function (n, idx) {
        n.classList.toggle('is-active', idx === i);
        if (idx === i) n.scrollIntoView({ block: 'nearest' });
      });
    }

    function choose(r) {
      input.value = '';
      hide();
      onPick(which, pickFromItem(r.item, r.id));
    }

    function render() {
      const q = input.value.trim();
      if (q.length < MIN_CHARS) { hide(); return; }
      dropdown.textContent = '';
      if (typeof Fuse === 'undefined' || !window.SEARCH_INDEX || !window.MatSavantSearch) {
        dropdown.appendChild(el('div', 'search-result-item search-result-empty', 'Search is unavailable right now.'));
        dropdown.style.display = 'block';
        return;
      }
      const other = which === 'a' ? state.b : state.a;
      current = searchWrestlers(q, other && other.id);
      activeIndex = -1;
      if (!current.length) {
        dropdown.appendChild(el('div', 'search-result-item search-result-empty', 'No matching wrestlers'));
      } else {
        const list = el('div', 'search-results');
        current.forEach(function (r, idx) {
          const row = el('div', 'search-result');
          row.appendChild(el('div', 'search-name', r.item.name));
          row.appendChild(el('div', 'search-secondary', r.item.secondary || ''));
          // mousedown (not click) so the choice lands before the input blurs
          row.addEventListener('mousedown', function (e) { e.preventDefault(); choose(r); });
          row.addEventListener('mouseenter', function () { setActive(idx); });
          list.appendChild(row);
        });
        dropdown.appendChild(list);
      }
      dropdown.style.display = 'block';
    }

    input.addEventListener('input', render);
    input.addEventListener('focus', render);
    input.addEventListener('keydown', function (e) {
      if (dropdown.style.display === 'none') return;
      if (e.key === 'ArrowDown') { e.preventDefault(); if (current.length) setActive((activeIndex + 1) % current.length); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); if (current.length) setActive((activeIndex - 1 + current.length) % current.length); }
      else if (e.key === 'Enter') { e.preventDefault(); const r = current[activeIndex >= 0 ? activeIndex : 0]; if (r) choose(r); }
      else if (e.key === 'Escape') { hide(); input.blur(); }
    });
    document.addEventListener('click', function (e) { if (!wrap.contains(e.target)) hide(); });
    clearBtn.addEventListener('click', function () { onPick(which, null); input.focus(); });

    return {
      focus: function () { input.focus(); },
      show: function (pick) {
        chip.classList.remove('has-detail');
        chipDetail.textContent = '';
        if (!pick) {
          chip.style.display = 'none';
          wrap.style.display = '';
          return;
        }
        chipName.textContent = pick.name;
        chipSub.textContent = pick.sub || '';
        chip.style.display = 'flex';
        wrap.style.display = 'none';
        hide();
      },
      setDetail: function (career) {
        chipDetail.textContent = '';
        const info = careerInfo(career);
        if (info.sub) chipDetail.appendChild(el('div', 'cmp-chip-sub', info.sub));
        if (info.rec) {
          const rec = el('div', 'cmp-chip-rec');
          rec.appendChild(info.rec);
          const link = el('a', 'cmp-chip-link', 'Profile ›');
          link.href = profileHref(career.latest_id);
          rec.appendChild(link);
          chipDetail.appendChild(rec);
        }
        chip.classList.toggle('has-detail', !!(info.sub || info.rec));
      }
    };
  }

  function onPick(which, pick) {
    state[which] = pick;
    slots[which].show(pick);
    state.careers = null;
    syncURL();
    update();
  }

  // ---------- URL ----------
  function syncURL() {
    const p = new URLSearchParams();
    if (state.a) p.set('a', state.a.id);
    if (state.b) p.set('b', state.b.id);
    if (state.season !== 'all' && state.a && state.b) p.set('season', state.season);
    const qs = p.toString();
    try { history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '')); } catch (e) { /* ignore */ }
  }

  // ---------- load + render ----------
  let renderToken = 0;
  function showMessage(node) {
    const r = $('cmp-results');
    r.textContent = '';
    r.appendChild(node);
  }

  async function update() {
    const token = ++renderToken;
    const toolbar = $('cmp-toolbar');
    if (!state.a || !state.b) {
      toolbar.style.display = 'none';
      showMessage(el('div', 'cmp-empty-state', state.a || state.b
        ? 'Now pick a second wrestler.'
        : 'Pick two wrestlers to see their head-to-head matches and the opponents they have in common.'));
      updateMeta(null, null);
      return;
    }
    showMessage(el('div', 'cmp-empty-state', 'Loading…'));
    try {
      const both = await Promise.all([loadCareer(state.a.id), loadCareer(state.b.id)]);
      if (token !== renderToken) return;
      if (both[0].career_id === both[1].career_id) throw new Error('Those are two seasons of the same wrestler.');
      state.careers = { A: both[0], B: both[1] };
      // Chips restored from a bare URL id have no display info yet — fill from the career.
      [['a', both[0]], ['b', both[1]]].forEach(function (pair) {
        const pick = state[pair[0]];
        if (pick && !pick.fromIndex) {
          const latest = pair[1].seasons[0] || {};
          pick.name = pair[1].canonical_name || pick.name;
          pick.sub = [latest.team, latest.weight_class].filter(Boolean).join(' · ');
          pick.fromIndex = true;
          slots[pair[0]].show(pick);
        }
      });
      populateSeasons();
      renderResults();
    } catch (err) {
      if (token !== renderToken) return;
      toolbar.style.display = 'none';
      showMessage(el('div', 'cmp-empty-state', 'Could not load these wrestlers: ' + (err.message || 'unknown error')));
    }
  }

  function populateSeasons() {
    const sel = $('cmp-season');
    const seasons = CORE.seasonsOf(state.careers.A, state.careers.B);
    sel.textContent = '';
    const all = el('option', null, 'All seasons');
    all.value = 'all';
    sel.appendChild(all);
    seasons.forEach(function (s) {
      const o = el('option', null, String(s));
      o.value = String(s);
      sel.appendChild(o);
    });
    if (state.season !== 'all' && seasons.indexOf(Number(state.season)) === -1) state.season = 'all';
    sel.value = state.season;
    $('cmp-toolbar').style.display = 'flex';
  }

  function setMetaDescription(text) {
    let tag = document.querySelector('meta[name="description"]');
    if (!tag) { tag = document.createElement('meta'); tag.name = 'description'; document.head.appendChild(tag); }
    tag.content = text;
  }

  function updateMeta(A, B) {
    if (!A || !B) {
      document.title = 'Compare Wrestlers: Head-to-Head & Common Opponents | MatSavant';
      setMetaDescription('Compare any two NCAA Division I wrestlers: every head-to-head match and common-opponent result between them.');
      return;
    }
    document.title = `${A.canonical_name} vs ${B.canonical_name} | Head-to-Head & Common Opponents | MatSavant`;
    setMetaDescription(`${A.canonical_name} vs ${B.canonical_name}: NCAA wrestling head-to-head matches and common-opponent results on MatSavant.`);
  }

  // The search index knows each wrestler's name address (latest-season id); any
  // other id gets the old ?id= form, which the edge function 301s.
  function profileHref(wrestlerId) {
    const hit = (window.SEARCH_INDEX || []).find(r => r.type === 'wrestler' && String(r.wrestler_id) === String(wrestlerId));
    return wrestlerHref(hit && hit.url, wrestlerId);
  }

  // "Team · 165 · #1 · 2026" and "93–1 (.989) career" — shared by the desktop cards and the mobile chips.
  function careerInfo(career) {
    const out = { sub: '', rec: null };
    const latest = career.seasons[0];
    if (latest) {
      const bits = [];
      if (latest.team) bits.push(latest.team);
      if (latest.weight_class) bits.push(latest.weight_class);
      if (latest.current_rank != null) bits.push('#' + latest.current_rank);
      bits.push(latest.season);
      out.sub = bits.join(' · ');
    }
    const cr = career.career_record;
    if (cr && (cr.wins || cr.losses)) {
      const rec = document.createDocumentFragment();
      rec.appendChild(el('strong', null, `${cr.wins}–${cr.losses}`));
      if (cr.win_pct != null) rec.appendChild(el('span', null, ` (${cr.win_pct.toFixed(3).replace(/^0\./, '.')}) career`));
      out.rec = rec;
    }
    return out;
  }

  function wrestlerCard(career) {
    const card = el('div', 'cmp-card');
    const nm = el('div', 'cmp-card-name');
    const a = el('a', null, career.canonical_name || '—');
    a.href = profileHref(career.latest_id);
    nm.appendChild(a);
    card.appendChild(nm);
    const info = careerInfo(career);
    if (info.sub) card.appendChild(el('div', 'cmp-card-sub', info.sub));
    if (info.rec) {
      const rec = el('div', 'cmp-card-rec');
      rec.appendChild(info.rec);
      card.appendChild(rec);
    }
    return card;
  }

  function matchLine(m) {
    const line = el('div', 'cmp-mline');
    line.appendChild(el('span', 'cmp-res cmp-res--' + (m.result === 'W' ? 'w' : 'l'), m.result));
    line.appendChild(document.createTextNode(' ' + methodText(m) + ' '));
    line.appendChild(el('small', null, fmtDate(m.date)));
    return line;
  }

  // Centre of a head-to-head row: method label over the score or fall time.
  function resultBadge(m) {
    const key = (m.method || '').toUpperCase();
    const box = el('div', 'cmp-res-badge' + (key === 'FALL' || key === 'TF' ? ' cmp-res-badge--bonus' : ''));
    box.appendChild(el('span', 'cmp-res-type', RESULT_LABELS[key] || m.method || 'Result'));
    let detail = '';
    if (key === 'FALL') detail = (m.duration && m.duration !== '0:00') ? m.duration : '';
    else if (m.score) {
      detail = m.score;
      // Scores are stored winner-first; flip when the right-hand wrestler won so each number sits by its scorer.
      const pts = /^(\d+)-(\d+)$/.exec(detail);
      if (pts && m.result === 'L') detail = pts[2] + '-' + pts[1];
    }
    if (detail) box.appendChild(el('span', 'cmp-res-detail', detail));
    return box;
  }

  function h2hSection(A, B, h2h) {
    const sec = el('div');
    sec.appendChild(el('h2', 'cmp-h2', 'Head-to-Head'));
    if (!h2h.matches.length) {
      sec.appendChild(el('div', 'cmp-note', 'These wrestlers have no recorded matches against each other' +
        (state.season !== 'all' ? ' in ' + state.season : '') + '.'));
      return sec;
    }
    const series = el('div', 'cmp-series');
    const nA = A.canonical_name, nB = B.canonical_name;
    if (h2h.aWins === h2h.bWins) series.appendChild(document.createTextNode('Series tied '));
    else series.appendChild(document.createTextNode((h2h.aWins > h2h.bWins ? nA : nB) + ' leads '));
    series.appendChild(el('span', 'cmp-score', Math.max(h2h.aWins, h2h.bWins) + '–' + Math.min(h2h.aWins, h2h.bWins)));
    sec.appendChild(series);

    h2h.matches.forEach(function (m) {
      const row = el('div', 'cmp-h2h-row');
      const main = el('div', 'cmp-h2h-main');
      main.appendChild(el('div', 'cmp-pill' + (m.result === 'W' ? ' cmp-pill--win' : ''), nA));
      main.appendChild(resultBadge(m));
      main.appendChild(el('div', 'cmp-pill' + (m.result === 'W' ? '' : ' cmp-pill--win'), nB));
      row.appendChild(main);
      const bits = [fmtDate(m.date)];
      if (m.event) bits.push(m.event);
      if (m.weight) bits.push(m.weight);
      row.appendChild(el('div', 'cmp-h2h-meta', bits.join(' · ')));
      sec.appendChild(row);
    });
    return sec;
  }

  function commonSection(A, B, co) {
    const sec = el('div');
    sec.appendChild(el('h2', 'cmp-h2', 'Common Opponents'));
    const s = co.summary;
    if (!s.count) {
      sec.appendChild(el('div', 'cmp-note', 'No common opponents found' +
        (state.season !== 'all' ? ' in ' + state.season : '') + '.'));
      return sec;
    }
    const nA = A.canonical_name, nB = B.canonical_name;
    const rec = function (r) { return `${r.wins}–${r.losses}` + (r.pins ? ` (${r.pins} pin${r.pins === 1 ? '' : 's'})` : ''); };

    const recLine = el('div', 'cmp-tally');
    [[nA, s.aRecord], [nB, s.bRecord]].forEach(function (pair) {
      const span = el('span');
      span.appendChild(el('strong', null, pair[0]));
      span.appendChild(document.createTextNode(' vs common opponents: '));
      span.appendChild(el('b', null, rec(pair[1])));
      recLine.appendChild(span);
    });
    sec.appendChild(recLine);

    const tally = el('div', 'cmp-tally');
    [
      [s.bothWon, 'both beat'],
      [s.aOnly, 'only ' + nA + ' beat'],
      [s.bOnly, 'only ' + nB + ' beat'],
      [s.mixed, 'split results'],
      [s.bothLost, 'neither beat']
    ].forEach(function (t) {
      if (!t[0]) return;
      const span = el('span');
      span.appendChild(el('b', null, String(t[0])));
      span.appendChild(document.createTextNode(' ' + t[1]));
      tally.appendChild(span);
    });
    sec.appendChild(tally);

    const head = el('div', 'cmp-opp-head');
    head.appendChild(el('div', null, `Opponent (${s.count})`));
    head.appendChild(el('div', null, nA));
    head.appendChild(el('div', null, nB));
    sec.appendChild(head);

    co.rows.forEach(function (r) {
      const row = el('div', 'cmp-opp-row');
      const opp = el('div');
      const nm = el('div', 'cmp-opp-name');
      const oppId = r.careerId ? latestIdForCareer(r.careerId) : null;
      if (oppId) {
        const a = el('a', null, r.name);
        a.href = profileHref(oppId);
        nm.appendChild(a);
      } else {
        nm.textContent = r.name;
      }
      opp.appendChild(nm);
      opp.appendChild(el('div', 'cmp-opp-team', r.team));
      row.appendChild(opp);
      [[nA, r.aMatches], [nB, r.bMatches]].forEach(function (pair) {
        const cell = el('div');
        cell.appendChild(el('div', 'cmp-cell-label', pair[0]));
        pair[1].forEach(function (m) { cell.appendChild(matchLine(m)); });
        row.appendChild(cell);
      });
      sec.appendChild(row);
    });
    return sec;
  }

  function renderResults() {
    const A = state.careers.A, B = state.careers.B;
    const opts = { season: state.season };
    const h2h = CORE.computeHeadToHead(A, B, opts);
    const co = CORE.computeCommonOpponents(A, B, opts);

    const root = $('cmp-results');
    root.textContent = '';
    const cards = el('div', 'cmp-cards');
    cards.appendChild(wrestlerCard(A));
    cards.appendChild(wrestlerCard(B));
    root.appendChild(cards);
    slots.a.setDetail(A);
    slots.b.setDetail(B);
    root.appendChild(h2hSection(A, B, h2h));
    root.appendChild(commonSection(A, B, co));
    root.appendChild(el('div', 'cmp-note',
      'Opponents are matched by career link across seasons; opponents without one are matched by name and team. ' +
      'Forfeits, medical forfeits, injury defaults and unknown opponents are excluded.'));
    updateMeta(A, B);
  }

  // ---------- init ----------
  function init() {
    slots.a = createSlot($('slot-a'), 'a', 'Wrestler A');
    slots.b = createSlot($('slot-b'), 'b', 'Wrestler B');
    loadLookup(); // warm it while the user types

    $('cmp-season').addEventListener('change', function (e) {
      state.season = e.target.value;
      syncURL();
      if (state.careers) renderResults();
    });

    $('cmp-swap').addEventListener('click', function () {
      const t = state.a; state.a = state.b; state.b = t;
      slots.a.show(state.a);
      slots.b.show(state.b);
      syncURL();
      update();
    });

    const params = new URLSearchParams(location.search);
    const season = params.get('season');
    if (season && /^\d{4}$/.test(season)) state.season = season;
    ['a', 'b'].forEach(function (which) {
      const id = params.get(which);
      if (!id || !ID_RE.test(id)) return;
      const item = (window.SEARCH_INDEX || []).find(function (i) { return i.type === 'wrestler' && idFromItem(i) === id; });
      state[which] = item ? pickFromItem(item, id) : { id: id, name: 'Loading…', sub: '', fromIndex: false };
      slots[which].show(state[which]);
    });
    if (state.a && state.b && state.a.id === state.b.id) { state.b = null; slots.b.show(null); }
    update();
    // Arrived with one wrestler filled in (the profile's Compare pill): put the cursor in the other box.
    if (state.a && !state.b) slots.b.focus();
    else if (state.b && !state.a) slots.a.focus();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
