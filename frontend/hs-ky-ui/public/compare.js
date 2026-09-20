// compare.js — KentuckyMat "Compare Wrestlers" page: two autocomplete pickers, then head-to-head + common opponents.
// Logic lives in compare_core.js (CompareCore); this file is UI, URL state and data fetching.
// URL: compare.html?gender=boys&a=career_000279&b=career_000249[&season=2026]
(function () {
  'use strict';

  const MIN_CHARS = 2;
  const MAX_RESULTS = 10;
  const CAREER_ID_RE = /^career_\d+$/;
  const CORE = window.CompareCore;

  // ---------- helpers ----------
  function $(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function nameNode(name, gender) {
    const frag = document.createDocumentFragment();
    frag.appendChild(document.createTextNode(name));
    if (gender === 'girls') {
      const s = el('span', null, ' ♀');
      s.style.color = '#ff69b4';
      frag.appendChild(s);
    }
    return frag;
  }

  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function fmtDate(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
    return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}` : (iso || '');
  }

  const METHOD_LABELS = {
    'FALL': 'Fall', 'DEC': 'Dec', 'MD': 'Maj Dec', 'TF': 'Tech Fall', 'SV-1': 'SV-1', 'TB-1': 'TB-1',
    'DFLT': 'Default', 'DQ': 'DQ', 'INJ': 'Inj Def'
  };
  function methodText(m) {
    const key = (m.method || '').toUpperCase();
    let text = METHOD_LABELS[key] || m.method || '';
    // Some falls have no recorded time and come through as "0:00" — omit those
    if (key === 'FALL') { if (m.duration && m.duration !== '0:00') text += ' ' + m.duration; }
    else if (m.score) text += ' ' + m.score;
    return text.trim();
  }

  // ---------- search index / picker ----------
  let INDEX = null;
  let INDEX_BY_KEY = null;
  let FUSE = null;

  function getIndex() {
    if (INDEX) return INDEX;
    INDEX = [];
    INDEX_BY_KEY = new Map();
    (window.SEARCH_INDEX || []).forEach(function (item) {
      if (item.type !== 'wrestler') return;
      let careerId = null;
      try { careerId = new URL(item.url, location.origin).searchParams.get('career_id'); } catch (e) { /* ignore */ }
      if (!careerId) return;
      const entry = Object.assign({}, item, { careerId: careerId });
      INDEX.push(entry);
      INDEX_BY_KEY.set(item.gender + ':' + careerId, entry);
    });
    return INDEX;
  }

  function getFuse() {
    if (!FUSE) {
      // Same weights/threshold as the header search (header.js initSearch)
      FUSE = new Fuse(getIndex(), {
        keys: [{ name: 'name', weight: 0.4 }, { name: 'first_name', weight: 0.3 }, { name: 'last_name', weight: 0.3 }],
        threshold: 0.15,
        ignoreLocation: true,
        minMatchCharLength: 2,
        includeScore: true
      });
    }
    return FUSE;
  }

  function searchWrestlers(query, gender, exclude) {
    const q = query.toLowerCase().trim();
    const results = getFuse().search(q).filter(function (r) {
      const it = r.item;
      if (gender && it.gender !== gender) return false;
      if (exclude && it.careerId === exclude.careerId && it.gender === exclude.gender) return false;
      return true;
    });
    const isPrefix = function (it) {
      return (it.name || '').toLowerCase().startsWith(q) ||
        (it.first_name || '').toLowerCase().startsWith(q) ||
        (it.last_name || '').toLowerCase().startsWith(q);
    };
    results.sort(function (a, b) {
      const pa = isPrefix(a.item), pb = isPrefix(b.item);
      if (pa !== pb) return pa ? -1 : 1;
      const sa = a.score || 1, sb = b.score || 1;
      if (Math.abs(sa - sb) > 0.01) return sa - sb;
      const ra = a.item.rank != null ? a.item.rank : 9999;
      const rb = b.item.rank != null ? b.item.rank : 9999;
      return ra - rb;
    });
    return results.slice(0, MAX_RESULTS).map(function (r) { return r.item; });
  }

  // ---------- state ----------
  const state = {
    a: null,            // {careerId, gender, name, sub, fromIndex}
    b: null,
    seedGender: null,   // gender from URL when nothing is picked yet
    season: 'all',
    careers: null       // {A, B} once loaded
  };
  const slots = {};

  function activeGender() {
    return (state.a && state.a.gender) || (state.b && state.b.gender) || state.seedGender || null;
  }

  function pickFromItem(item) {
    return { careerId: item.careerId, gender: item.gender, name: item.name, sub: item.secondary || '', fromIndex: true };
  }

  // ---------- slot (label + search box + chip) ----------
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
    // Mobile-only extra lines (rank/season + career record + profile link) that replace the separate wrestler cards.
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

    const hint = el('div', 'cmp-slot-hint');
    root.appendChild(hint);

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

    function choose(item) {
      input.value = '';
      hide();
      onPick(which, pickFromItem(item));
    }

    function render() {
      const q = input.value.trim();
      if (q.length < MIN_CHARS) { hide(); return; }
      if (typeof Fuse === 'undefined' || !window.SEARCH_INDEX) {
        dropdown.textContent = '';
        dropdown.appendChild(el('div', 'search-result-item search-result-empty', 'Search is unavailable right now.'));
        dropdown.style.display = 'block';
        return;
      }
      const other = which === 'a' ? state.b : state.a;
      current = searchWrestlers(q, activeGender(), other);
      dropdown.textContent = '';
      activeIndex = -1;
      if (!current.length) {
        dropdown.appendChild(el('div', 'search-result-item search-result-empty', 'No matching wrestlers'));
      } else {
        const list = el('div', 'search-results');
        current.forEach(function (item, idx) {
          const row = el('div', 'search-result');
          const nm = el('div', 'search-name');
          nm.appendChild(nameNode(item.name, item.gender));
          row.appendChild(nm);
          row.appendChild(el('div', 'search-secondary', item.secondary || ''));
          // mousedown (not click) so the choice lands before the input blurs
          row.addEventListener('mousedown', function (e) { e.preventDefault(); choose(item); });
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
      else if (e.key === 'Enter') { e.preventDefault(); const it = current[activeIndex >= 0 ? activeIndex : 0]; if (it) choose(it); }
      else if (e.key === 'Escape') { hide(); input.blur(); }
    });
    document.addEventListener('click', function (e) { if (!wrap.contains(e.target)) hide(); });
    clearBtn.addEventListener('click', function () { onPick(which, null); input.focus(); });

    return {
      input: input,
      show: function (pick) {
        chip.classList.remove('has-detail');
        chipDetail.textContent = '';
        if (!pick) {
          chip.style.display = 'none';
          wrap.style.display = '';
          return;
        }
        chipName.textContent = '';
        chipName.appendChild(nameNode(pick.name, pick.gender));
        chipSub.textContent = pick.sub || '';
        chip.style.display = 'flex';
        wrap.style.display = 'none';
        hide();
      },
      setHint: function (text) { hint.textContent = text || ''; },
      setDetail: function (career, gender) {
        chipDetail.textContent = '';
        const info = careerInfo(career);
        if (info.sub) chipDetail.appendChild(el('div', 'cmp-chip-sub', info.sub));
        if (info.rec) {
          const rec = el('div', 'cmp-chip-rec');
          rec.appendChild(info.rec);
          const link = el('a', 'cmp-chip-link', 'Profile \u203A');
          link.href = profileHref(gender, career.career_id);
          rec.appendChild(link);
          chipDetail.appendChild(rec);
        }
        chip.classList.toggle('has-detail', !!(info.sub || info.rec));
      }
    };
  }

  function refreshHints() {
    const g = activeGender();
    ['a', 'b'].forEach(function (which) {
      if (state[which]) { slots[which].setHint(''); return; }
      slots[which].setHint(g ? `Searching ${g} wrestlers` : 'Search boys or girls wrestlers by name');
    });
  }

  function onPick(which, pick) {
    state[which] = pick;
    if (!pick && !state.a && !state.b) state.seedGender = null;
    slots[which].show(pick);
    state.careers = null;
    refreshHints();
    syncURL();
    update();
  }

  // ---------- URL ----------
  function syncURL() {
    const p = new URLSearchParams();
    const g = activeGender();
    if (g) p.set('gender', g);
    if (state.a) p.set('a', state.a.careerId);
    if (state.b) p.set('b', state.b.careerId);
    if (state.season !== 'all' && state.a && state.b) p.set('season', state.season);
    const qs = p.toString();
    try { history.replaceState(null, '', location.pathname + (qs ? '?' + qs : '')); } catch (e) { /* ignore */ }
  }

  // ---------- data ----------
  const careerCache = new Map();
  function loadCareer(gender, careerId) {
    const key = gender + ':' + careerId;
    if (!careerCache.has(key)) {
      careerCache.set(key, fetch('/data/careers/' + gender + '/' + careerId + '.json').then(function (r) {
        if (!r.ok) throw new Error(r.status === 404 ? 'No career profile found for ' + careerId : 'Failed to load ' + careerId + ' (' + r.status + ')');
        return r.json();
      }).catch(function (err) { careerCache.delete(key); throw err; }));
    }
    return careerCache.get(key);
  }

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
      const g = activeGender();
      const both = await Promise.all([loadCareer(g, state.a.careerId), loadCareer(g, state.b.careerId)]);
      if (token !== renderToken) return;
      state.careers = { A: both[0], B: both[1] };
      // Chips built from a bare URL id have no display info yet — fill from the career file.
      [['a', both[0]], ['b', both[1]]].forEach(function (pair) {
        const pick = state[pair[0]];
        if (pick && !pick.fromIndex) {
          const latest = (pair[1].seasons || [])[0] || {};
          pick.name = pair[1].canonical_name || pick.name;
          pick.sub = [latest.team, latest.weight_class ? latest.weight_class + ' lbs' : ''].filter(Boolean).join(' · ');
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

  function updateMeta(A, B) {
    if (!A || !B) {
      document.title = 'Compare Wrestlers: Head-to-Head & Common Opponents | KentuckyMat';
      setMetaDescription('Compare any two Kentucky high school wrestlers. See every head-to-head match and common-opponent result between them on KentuckyMat.');
      return;
    }
    document.title = `${A.canonical_name} vs ${B.canonical_name} | Wrestling Head-to-Head & Common Opponents | KentuckyMat`;
    setMetaDescription(`${A.canonical_name} vs ${B.canonical_name}: head-to-head matches and common-opponent results for Kentucky high school wrestling on KentuckyMat.`);
  }

  // ---------- rendering ----------
  function profileHref(gender, careerId) {
    return buildPageURL('wrestler.html', gender, { career_id: careerId });
  }

  // "Team · 114 lbs · #2 · 2026" and "81–16 (.835) career" for a career — shared by the desktop cards and the mobile chips.
  function careerInfo(career) {
    const out = { sub: '', rec: null };
    const latest = (career.seasons || [])[0];
    if (latest) {
      const bits = [];
      if (latest.team) bits.push(latest.team);
      if (latest.weight_class) bits.push(latest.weight_class + ' lbs');
      if (latest.current_rank != null) bits.push('#' + latest.current_rank);
      bits.push(latest.season);
      out.sub = bits.join(' · ');
    }
    const cr = career.career_record || {};
    if (cr.wins != null) {
      const rec = document.createDocumentFragment();
      rec.appendChild(el('strong', null, `${cr.wins}–${cr.losses ?? 0}`));
      if (cr.win_pct != null) rec.appendChild(el('span', null, ` (${cr.win_pct.toFixed(3).replace(/^0\./, '.')}) career`));
      out.rec = rec;
    }
    return out;
  }

  function wrestlerCard(career, gender) {
    const card = el('div', 'cmp-card');
    const nm = el('div', 'cmp-card-name');
    const a = el('a', null, career.canonical_name || '—');
    a.href = profileHref(gender, career.career_id);
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

  // Centre of a head-to-head row: bold method label (FALL / TECH FALL / MAJOR / DEC ...) over the score or fall time.
  const RESULT_LABELS = {
    'FALL': 'Fall', 'TF': 'Tech Fall', 'MD': 'Major', 'DEC': 'Dec', 'SV-1': 'SV-1', 'TB-1': 'TB-1',
    'DFLT': 'Default', 'DQ': 'DQ', 'INJ': 'Inj Def'
  };
  function resultBadge(m) {
    const key = (m.method || '').toUpperCase();
    const box = el('div', 'cmp-res-badge' + (key === 'FALL' || key === 'TF' ? ' cmp-res-badge--bonus' : ''));
    box.appendChild(el('span', 'cmp-res-type', RESULT_LABELS[key] || m.method || 'Result'));
    let detail = '';
    if (key === 'FALL') detail = (m.duration && m.duration !== '0:00') ? m.duration : '';
    else if (m.score) {
      detail = m.score;
      // Stored scores are winner-first ("10-7"). The score sits between the two pills, so when the RIGHT wrestler
      // won (m.result === 'L' from A's side) flip it so each number is next to the wrestler who scored it ("7-10").
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

    // One compact block per bout: [A pill]  [result]  [B pill], then a small date · event · weight line.
    // A is always on the left (same as the wrestler cards above); the winner's pill is highlighted green.
    h2h.matches.forEach(function (m) {
      const row = el('div', 'cmp-h2h-row');
      const main = el('div', 'cmp-h2h-main');
      main.appendChild(el('div', 'cmp-pill cmp-pill--a' + (m.result === 'W' ? ' cmp-pill--win' : ''), nA));
      main.appendChild(resultBadge(m));
      main.appendChild(el('div', 'cmp-pill cmp-pill--b' + (m.result === 'W' ? '' : ' cmp-pill--win'), nB));
      row.appendChild(main);
      const bits = [fmtDate(m.date)];
      if (m.event) bits.push(m.event);
      if (m.weight) bits.push(m.weight + ' lbs');
      row.appendChild(el('div', 'cmp-h2h-meta', bits.join(' · ')));
      sec.appendChild(row);
    });
    return sec;
  }

  function commonSection(A, B, gender, co) {
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
      if (r.careerId) {
        const a = el('a', null, r.name);
        a.href = profileHref(gender, r.careerId);
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
    const gender = activeGender();
    const opts = { season: state.season };
    const h2h = CORE.computeHeadToHead(A, B, opts);
    const co = CORE.computeCommonOpponents(A, B, opts);

    const root = $('cmp-results');
    root.textContent = '';
    const cards = el('div', 'cmp-cards');
    cards.appendChild(wrestlerCard(A, gender));
    cards.appendChild(wrestlerCard(B, gender));
    root.appendChild(cards);
    slots.a.setDetail(A, gender);
    slots.b.setDetail(B, gender);
    root.appendChild(h2hSection(A, B, h2h));
    root.appendChild(commonSection(A, B, gender, co));
    root.appendChild(el('div', 'cmp-note',
      'Opponents are matched by career link; opponents without one are matched by name and team. ' +
      'Forfeits, injury defaults and unknown opponents are excluded.'));
    updateMeta(A, B);
  }

  // ---------- init ----------
  function init() {
    slots.a = createSlot($('slot-a'), 'a', 'Wrestler A');
    slots.b = createSlot($('slot-b'), 'b', 'Wrestler B');

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
      if (state.careers) state.careers = { A: state.careers.B, B: state.careers.A };
      update();
    });

    // Restore from URL
    const params = new URLSearchParams(location.search);
    const gParam = params.get('gender');
    const urlGender = (gParam === 'boys' || gParam === 'girls') ? gParam : null;
    const season = params.get('season');
    if (season && /^\d{4}$/.test(season)) state.season = season;

    const seeds = { a: params.get('a'), b: params.get('b') };
    ['a', 'b'].forEach(function (which) {
      const id = seeds[which];
      if (!id || !CAREER_ID_RE.test(id)) return;
      const g = urlGender || 'boys';
      getIndex();
      const item = INDEX_BY_KEY && INDEX_BY_KEY.get(g + ':' + id);
      state[which] = item ? pickFromItem(item) : { careerId: id, gender: g, name: id, sub: '', fromIndex: false };
      slots[which].show(state[which]);
    });
    if (!state.a && !state.b) state.seedGender = urlGender;
    if (state.a && state.b && state.a.careerId === state.b.careerId) { state.b = null; slots.b.show(null); }

    refreshHints();
    update();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
