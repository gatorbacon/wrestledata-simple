// compare_core.js — pure (DOM-free) head-to-head + common-opponent logic.
//
// Input: two enriched career objects (data/careers/{gender}/career_XXXXXX.json, built by
// scripts/rankings/build_career_profiles.py). Works in the browser (window.CompareCore) and in Node (module.exports).
//
// Opponent identity (see CLAUDE.md "Compare page"):
//   1. opponent_career_id when present  -> key "c:<career_id>"
//   2. else normalized "name|team"      -> key "n:<name>|<team>"; if that same name|team resolves to a career_id
//      anywhere in either wrestler's matches, the career key wins (covers unlinked rows for a linked opponent)
//   3. skip opponent_name "Unknown" (many opponents collapse onto one id) and forfeits / injury defaults
(function (root) {
  'use strict';

  function norm(s) {
    return (s || '').toString().trim().toLowerCase().replace(/\s+/g, ' ');
  }

  // Mirrors isForfeitMatch() in app.js, plus MFF (medical forfeit).
  function isForfeit(m) {
    const result = (m.result || '').toUpperCase();
    const method = (m.method || '').toUpperCase();
    const summary = (m.summary || '').toUpperCase();
    if (result.startsWith('FOR')) return true;
    if (method.startsWith('FOR') || method === 'FF' || method === 'MFF') return true;
    if (summary.includes('OVER UNKNOWN')) return true;
    return false;
  }

  function isInjury(m) {
    const method = (m.method || '').toUpperCase();
    return method === 'INJ' || method === 'NC';
  }

  function nameTeamKey(m) {
    const name = norm(m.opponent_name);
    if (!name || name === 'unknown') return null;
    return 'n:' + name + '|' + norm(m.opponent_team);
  }

  // Flatten a career's seasons[].matches[] into normalized, de-duplicated match rows.
  // `nameTeamToCareer` (optional) maps "n:name|team" -> "c:career_id" to resolve unlinked rows.
  function normalizeMatches(career, nameTeamToCareer) {
    const out = [];
    const seen = new Set();
    (career.seasons || []).forEach(function (s) {
      (s.matches || []).forEach(function (m) {
        if (isForfeit(m)) return;
        const ntKey = nameTeamKey(m);
        let oppKey = null;
        if (m.opponent_career_id) oppKey = 'c:' + m.opponent_career_id;
        else if (ntKey) oppKey = (nameTeamToCareer && nameTeamToCareer.get(ntKey)) || ntKey;
        const row = {
          season: m.season != null ? m.season : s.season,
          date: m.date || '',
          event: m.event || '',
          weight: m.weight_class != null ? String(m.weight_class) : '',
          result: (m.result || '').toUpperCase() === 'W' ? 'W' : 'L',
          method: m.method || '',
          score: m.score || '',
          duration: m.duration || '',
          oppKey: oppKey,
          oppName: m.opponent_name || '',
          oppTeam: m.opponent_team || '',
          oppCareerId: m.opponent_career_id || null,
          oppId: m.opponent_id != null ? String(m.opponent_id) : '',
          injury: isInjury(m)
        };
        const dk = [row.date, row.oppKey || row.oppId, row.result, row.score, row.method, row.event].join('|');
        if (seen.has(dk)) return;
        seen.add(dk);
        out.push(row);
      });
    });
    return out;
  }

  // "n:name|team" -> "c:career" for every unlinked-name that is linked somewhere (only if unambiguous).
  function buildNameTeamMap(careers) {
    const map = new Map();
    const ambiguous = new Set();
    careers.forEach(function (career) {
      (career.seasons || []).forEach(function (s) {
        (s.matches || []).forEach(function (m) {
          if (!m.opponent_career_id) return;
          const k = nameTeamKey(m);
          if (!k) return;
          const c = 'c:' + m.opponent_career_id;
          if (map.has(k) && map.get(k) !== c) ambiguous.add(k);
          else map.set(k, c);
        });
      });
    });
    ambiguous.forEach(function (k) { map.delete(k); });
    return map;
  }

  function wrestlerIds(career) {
    const ids = new Set();
    (career.seasons || []).forEach(function (s) { if (s.wrestler_id) ids.add(String(s.wrestler_id)); });
    return ids;
  }

  function seasonsOf() {
    const set = new Set();
    for (let i = 0; i < arguments.length; i++) {
      (arguments[i].seasons || []).forEach(function (s) { set.add(Number(s.season)); });
    }
    return Array.from(set).sort(function (a, b) { return b - a; });
  }

  function byDateDesc(a, b) {
    return a.date < b.date ? 1 : a.date > b.date ? -1 : 0;
  }

  function inSeason(rows, season) {
    if (season == null || season === '' || season === 'all') return rows;
    return rows.filter(function (r) { return String(r.season) === String(season); });
  }

  function prep(careerA, careerB, opts) {
    const map = buildNameTeamMap([careerA, careerB]);
    const season = opts && opts.season;
    return {
      a: inSeason(normalizeMatches(careerA, map), season),
      b: inSeason(normalizeMatches(careerB, map), season),
      idsA: wrestlerIds(careerA),
      idsB: wrestlerIds(careerB)
    };
  }

  function isVs(row, career, ids) {
    return row.oppCareerId === career.career_id || (row.oppId && ids.has(row.oppId));
  }

  // Head-to-head from A's perspective. Union of A's matches vs B and B's matches vs A (flipped), de-duplicated.
  function computeHeadToHead(careerA, careerB, opts) {
    const p = prep(careerA, careerB, opts);
    const rows = [];
    const seen = new Set();
    function add(r) {
      const k = [r.date, r.result, r.score, r.method].join('|');
      if (seen.has(k)) return;
      seen.add(k);
      rows.push(r);
    }
    p.a.filter(function (r) { return isVs(r, careerB, p.idsB); }).forEach(function (r) {
      add({ season: r.season, date: r.date, event: r.event, weight: r.weight, result: r.result,
            method: r.method, score: r.score, duration: r.duration });
    });
    p.b.filter(function (r) { return isVs(r, careerA, p.idsA); }).forEach(function (r) {
      add({ season: r.season, date: r.date, event: r.event, weight: r.weight,
            result: r.result === 'W' ? 'L' : 'W', method: r.method, score: r.score, duration: r.duration });
    });
    rows.sort(byDateDesc);
    return {
      aWins: rows.filter(function (r) { return r.result === 'W'; }).length,
      bWins: rows.filter(function (r) { return r.result === 'L'; }).length,
      matches: rows
    };
  }

  function groupByOpp(rows, excludeKeys) {
    const map = new Map();
    rows.forEach(function (r) {
      if (!r.oppKey || r.injury || excludeKeys.has(r.oppKey)) return;
      if (!map.has(r.oppKey)) map.set(r.oppKey, []);
      map.get(r.oppKey).push(r);
    });
    return map;
  }

  function outcome(matches) {
    const w = matches.filter(function (m) { return m.result === 'W'; }).length;
    if (w === matches.length) return 'W';
    if (w === 0) return 'L';
    return 'S'; // split
  }

  function record(matchLists) {
    let w = 0, l = 0, pins = 0;
    matchLists.forEach(function (list) {
      list.forEach(function (m) {
        if (m.result === 'W') { w++; if ((m.method || '').toUpperCase() === 'FALL') pins++; } else l++;
      });
    });
    return { wins: w, losses: l, pins: pins };
  }

  // Common opponents: opponents both wrestlers have faced (any season, any weight).
  function computeCommonOpponents(careerA, careerB, opts) {
    const p = prep(careerA, careerB, opts);
    const exclude = new Set(['c:' + careerA.career_id, 'c:' + careerB.career_id]);
    // Drop rows against the other wrestler by season wrestler_id too (unlinked H2H rows).
    const notPair = function (r) { return !(r.oppId && (p.idsA.has(r.oppId) || p.idsB.has(r.oppId))); };
    const mapA = groupByOpp(p.a.filter(notPair), exclude);
    const mapB = groupByOpp(p.b.filter(notPair), exclude);

    const rows = [];
    mapA.forEach(function (aMatches, key) {
      if (!mapB.has(key)) return;
      const bMatches = mapB.get(key);
      const all = aMatches.concat(bMatches).sort(byDateDesc);
      const latest = all[0];
      rows.push({
        key: key,
        linked: key.charAt(0) === 'c',
        careerId: key.charAt(0) === 'c' ? key.slice(2) : null,
        name: latest.oppName,
        team: latest.oppTeam,
        lastDate: latest.date,
        aMatches: aMatches.slice().sort(byDateDesc),
        bMatches: bMatches.slice().sort(byDateDesc),
        aOutcome: outcome(aMatches),
        bOutcome: outcome(bMatches)
      });
    });
    rows.sort(function (x, y) { return x.lastDate < y.lastDate ? 1 : x.lastDate > y.lastDate ? -1 : 0; });

    const summary = { count: rows.length, aOnly: 0, bOnly: 0, bothWon: 0, bothLost: 0, mixed: 0 };
    rows.forEach(function (r) {
      if (r.aOutcome === 'S' || r.bOutcome === 'S') summary.mixed++;
      else if (r.aOutcome === 'W' && r.bOutcome === 'W') summary.bothWon++;
      else if (r.aOutcome === 'L' && r.bOutcome === 'L') summary.bothLost++;
      else if (r.aOutcome === 'W') summary.aOnly++;
      else summary.bOnly++;
    });
    summary.aRecord = record(rows.map(function (r) { return r.aMatches; }));
    summary.bRecord = record(rows.map(function (r) { return r.bMatches; }));
    return { rows: rows, summary: summary };
  }

  const api = {
    normalizeMatches: normalizeMatches,
    computeHeadToHead: computeHeadToHead,
    computeCommonOpponents: computeCommonOpponents,
    seasonsOf: seasonsOf
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.CompareCore = api;
})(typeof window !== 'undefined' ? window : globalThis);
