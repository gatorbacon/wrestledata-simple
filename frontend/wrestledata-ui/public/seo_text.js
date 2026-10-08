// Page titles, descriptions and addresses for wrestler and team pages
// (docs/matsavant_seo_plan.md). ONE copy, used by the browser (wrestler.html,
// team.html load it) and by the edge functions (netlify/edge-functions/*.ts
// import it), so the title Google reads in the raw HTML and the one the page
// sets after loading are always the same.
// Plain script (no import/export) so it works both as a <script> tag and as an
// ES-module side-effect import; it only defines globalThis.MatSavantSEO.
(function (root) {
  "use strict";

  const SITE = "https://www.matsavant.com";

  // Old team ids that still turn up in links (older seasons' profiles carry
  // them, and Google remembers them: Search Console soft 404s, 2026-10-07) ->
  // today's team id. scripts/seo/build_url_slugs.py has the same renames in
  // TEAM_SLUG_RENAMES (it can't read this file); keep the two in step.
  const TEAM_SLUG_ALIASES = {
    army: "army_west_point",
    binghamton_university: "binghamton",
    franklin__marshall: "franklin_marshall",
    north_carolina_state: "nc_state",
    north_dakota_state_university: "north_dakota_state",
    ok_state: "oklahoma_state",
    southern_illinois_edwardsville: "siu_edwardsville",
    utah_valley_university: "utah_valley",
  };

  // 2026 -> "2025-26"
  function seasonLabel(season) {
    const y = Number(season);
    return y ? `${y - 1}-${String(y).slice(-2)}` : "";
  }

  // The scraped data sometimes types an apostrophe as a backtick ("Grant O`Dell").
  function cleanName(name) {
    return String(name || "").replace(/`/g, "'");
  }

  // w = a /seo/wrestlers/<slug>.json record (or the same fields).
  // Approved by TJ 2026-10-07: "Levi Haines Wrestling Record & Stats | Penn State 174 | MatSavant"
  function wrestlerTitle(w) {
    const where = [w.team, w.weight].filter(Boolean).join(" ");
    return `${cleanName(w.name)} Wrestling Record & Stats${where ? ` | ${where}` : ""} | MatSavant`;
  }

  // "Levi Haines college wrestling record and stats: 99-4 career, 26-0 in
  //  2025-26 at 174 for Penn State. Every match, ranking and head-to-head on MatSavant."
  function wrestlerDescription(w) {
    const parts = [];
    if (w.career_record && Object.keys(w.seasons || {}).length > 1) parts.push(`${w.career_record} career`);
    if (w.season_record) {
      let s = `${w.season_record} in ${seasonLabel(w.latest_season)}`;
      if (w.weight) s += ` at ${w.weight}`;
      if (w.team) s += ` for ${w.team}`;
      parts.push(s);
    }
    return `${cleanName(w.name)} college wrestling record and stats${parts.length ? `: ${parts.join(", ")}` : ""}. ` +
      `Every match, ranking and head-to-head on MatSavant.`;
  }

  function wrestlerPath(slug) {
    return `/wrestler/${slug}`;
  }

  // team id (penn_state, or an old alias) -> address (/team/penn-state)
  function teamPath(teamId) {
    const id = TEAM_SLUG_ALIASES[teamId] || teamId;
    return `/team/${String(id).replace(/_/g, "-")}`;
  }

  // "/team/penn-state" segment -> team id "penn_state" (no team id has a hyphen)
  function teamIdFromPath(segment) {
    return String(segment).toLowerCase().replace(/-/g, "_");
  }

  function teamTitle(teamName, season) {
    return `${teamName} Wrestling ${seasonLabel(season)}: Roster, Lineup, Results & Rankings | MatSavant`;
  }

  function teamDescription(teamName, season) {
    return `${teamName} wrestling ${seasonLabel(season)}: roster, starting lineup, results, ` +
      `rankings and projected NCAA team points on MatSavant.`;
  }

  // Browser only: set <title>, meta description, canonical (and noindex for
  // not-found pages). Updates tags the edge function already wrote instead of
  // adding second copies.
  function applyHead({ title, description, canonical, noindex } = {}) {
    const doc = root.document;
    if (!doc) return;
    const tag = (selector, make) => doc.head.querySelector(selector) || doc.head.appendChild(make());
    if (title) doc.title = title;
    if (description) {
      tag('meta[name="description"]', () => Object.assign(doc.createElement("meta"), { name: "description" }))
        .setAttribute("content", description);
    }
    if (canonical) {
      tag('link[rel="canonical"]', () => Object.assign(doc.createElement("link"), { rel: "canonical" }))
        .setAttribute("href", canonical);
    }
    if (noindex) {
      tag('meta[name="robots"]', () => Object.assign(doc.createElement("meta"), { name: "robots" }))
        .setAttribute("content", "noindex");
    }
  }

  root.MatSavantSEO = {
    SITE, TEAM_SLUG_ALIASES, seasonLabel,
    wrestlerTitle, wrestlerDescription, wrestlerPath,
    teamPath, teamIdFromPath, teamTitle, teamDescription,
    applyHead,
  };
})(typeof window !== "undefined" ? window : globalThis);
