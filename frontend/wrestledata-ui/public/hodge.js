// ========================================
// Hodge Trophy Watch Page
// ========================================
// Data source: /data/awards/hodge/{season}/hodge_{season}.json, built by
// scripts/rankings/hodge_candidates.py off elo_ratings.json's
// hybrid_rank_by_weight + each candidate's wrestler-profile match_list
// (see docs/matsavant.md's "Hodge Trophy Candidates" section).
// Visual language matches Team Race (leaderboards/xtp/teams.js): rank-badge
// medals, team crest + school-color bars, single-expand rows.

const HG_SEASON = "2026"; // 2027 data isn't available yet -- switch once it is
const HG_SCORE_MAX = 100; // hodge_score is already on a 0-100 scale
const HG_NAVY_FALLBACK = "#2c5c8f";

let hodgeRows = [];
let teamColors = {}; // slug -> { hex, stroke }
let expandedKey = null; // wrestler_id (or name fallback), or null

function safe(v, fn) {
  if (v === null || v === undefined || v === "") return "—";
  return fn ? fn(v) : v;
}

function teamNameToSlug(teamName) {
  if (!teamName) return "";
  let slug = teamName.toLowerCase();
  slug = slug.replace(/\s+/g, "_");
  slug = slug.replace(/[^\w_]/g, "");
  slug = slug.replace(/_+/g, "_");
  slug = slug.replace(/^_+|_+$/g, "");
  return slug;
}

function teamAbbr(teamName) {
  if (!teamName) return "";
  const words = teamName.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "";
  if (words.length === 1) return words[0].slice(0, 3).toUpperCase();
  return words.map(w => w[0]).join("").toUpperCase().slice(0, 3);
}

function teamBarColor(slug) {
  const entry = teamColors[slug];
  return entry && entry.hex ? entry.hex : HG_NAVY_FALLBACK;
}

async function loadTeamColors() {
  try {
    const res = await fetch("/data/team_colors.json");
    if (!res.ok) return {};
    const data = await res.json();
    return data.teams || {};
  } catch {
    return {};
  }
}

function createRankBadge(rank) {
  if (rank === null || rank === undefined || rank === "") {
    return document.createTextNode("—");
  }
  const badge = document.createElement("span");
  badge.className = "rank-badge";
  if (rank === 1) badge.classList.add("medal-gold");
  else if (rank === 2) badge.classList.add("medal-silver");
  else if (rank === 3) badge.classList.add("medal-bronze");
  else badge.classList.add("standard");
  badge.textContent = `#${rank}`;
  return badge;
}

// Team crest with a required fallback: svg -> png -> abbreviation circle.
function createTeamMark(teamName, slug) {
  const wrap = document.createElement("span");
  wrap.className = "hg-team-mark";
  const img = document.createElement("img");
  img.alt = "";
  img.loading = "lazy";
  img.src = `/assets/team_logos/${slug}.svg`;
  img.addEventListener("error", () => {
    if (!img.dataset.fb) {
      img.dataset.fb = "1";
      img.src = `/assets/team_logos/${slug}.png`;
    } else {
      wrap.innerHTML = "";
      wrap.classList.add("hg-team-mark--abbr");
      wrap.textContent = teamAbbr(teamName);
    }
  });
  wrap.appendChild(img);
  return wrap;
}

// Near-black -> muted green -> strong green, keyed off a 0-100 component
// score. Kept from the previous version of this page -- a useful secondary
// signal distinct from the team-color hero bar.
function getScoreColor(score) {
  const t = Math.max(0, Math.min(100, score)) / 100.0;
  if (t <= 0.5) {
    const r = Math.round(26 + (45 - 26) * (t * 2));
    const g = Math.round(26 + (90 - 26) * (t * 2));
    const b = Math.round(26 + (61 - 26) * (t * 2));
    return `rgb(${r}, ${g}, ${b})`;
  } else if (t <= 0.8) {
    const localT = (t - 0.5) / 0.3;
    const r = Math.round(45 + (26 - 45) * localT);
    const g = Math.round(90 + (110 - 90) * localT);
    const b = Math.round(61 + (34 - 61) * localT);
    return `rgb(${r}, ${g}, ${b})`;
  }
  return "rgb(26, 110, 34)";
}

async function fetchJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to fetch ${url}: ${response.statusText}`);
  return response.json();
}

function rowKey(row) {
  return row.wrestler_id || row.name;
}

// ========================================
// Render
// ========================================
function renderHodgeTable(data) {
  hodgeRows = (data && data.rows) || [];

  const eligibleTbody = document.getElementById("eligible-tbody");
  const ineligibleTbody = document.getElementById("ineligible-tbody");

  if (hodgeRows.length === 0) {
    eligibleTbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:2em;color:var(--muted);">No data available</td></tr>`;
    ineligibleTbody.innerHTML = "";
    return;
  }

  const eligibleRows = hodgeRows.filter(r => r.eligible).sort((a, b) => a.rank - b.rank);
  const ineligibleRows = hodgeRows.filter(r => !r.eligible).sort((a, b) => a.rank - b.rank);

  eligibleTbody.innerHTML = "";
  ineligibleTbody.innerHTML = "";

  eligibleRows.forEach(row => renderRowInto(eligibleTbody, row));
  ineligibleRows.forEach(row => renderRowInto(ineligibleTbody, row));
}

function renderRowInto(tbody, row) {
  const key = rowKey(row);
  const isExpanded = expandedKey === key;
  const slug = teamNameToSlug(row.team);
  const color = teamBarColor(slug);

  const tr = document.createElement("tr");
  tr.className = `hg-row expandable-row ${isExpanded ? "expanded" : "collapsed"}`;

  // 1. Expand chevron
  const chevronTd = document.createElement("td");
  chevronTd.className = "hg-chevron-cell";
  const expandIcon = document.createElement("span");
  expandIcon.className = "expand-icon";
  chevronTd.appendChild(expandIcon);
  tr.appendChild(chevronTd);

  // 2. Overall Hodge Watch rank (medal top 3)
  const rankTd = document.createElement("td");
  rankTd.className = "hg-rank-cell";
  rankTd.appendChild(createRankBadge(row.rank));
  tr.appendChild(rankTd);

  // 3. Wrestler + team crest + weight/weight-rank subline
  const wrestlerTd = document.createElement("td");
  wrestlerTd.className = "hg-wrestler-cell-td";
  const wrap = document.createElement("div");
  wrap.className = "hg-wrestler-cell";
  wrap.appendChild(createTeamMark(row.team, slug));

  const textWrap = document.createElement("div");
  const nameEl = row.wrestler_id
    ? Object.assign(document.createElement("a"), {
        className: "hg-wrestler-name",
        href: `/wrestler.html?id=${row.wrestler_id}`,
        textContent: row.name,
      })
    : Object.assign(document.createElement("span"), {
        className: "hg-wrestler-name",
        textContent: row.name,
      });
  textWrap.appendChild(nameEl);

  const sub = document.createElement("div");
  sub.className = "hg-wrestler-sub";
  const teamLink = document.createElement("a");
  teamLink.href = `/team.html?team=${slug}`;
  teamLink.textContent = row.team;
  sub.appendChild(teamLink);
  sub.appendChild(document.createTextNode(` · ${row.weight} lbs · Wt #${row.weight_rank}`));
  textWrap.appendChild(sub);

  wrap.appendChild(textWrap);
  wrestlerTd.appendChild(wrap);
  tr.appendChild(wrestlerTd);

  // 4. Hodge Score hero: bold number + team-color bar, record/reason underneath
  const heroTd = document.createElement("td");
  heroTd.className = "hg-hero-cell";

  const heroRow = document.createElement("div");
  heroRow.className = "hg-hero-row";

  const valueEl = document.createElement("span");
  valueEl.className = "hg-hero-value";
  valueEl.textContent = safe(row.hodge_score, v => v.toFixed(1));
  heroRow.appendChild(valueEl);

  const track = document.createElement("div");
  track.className = "hg-bar-track";
  const fill = document.createElement("div");
  fill.className = "hg-bar-fill";
  fill.style.width = `${Math.max(0, Math.min(100, (row.hodge_score / HG_SCORE_MAX) * 100))}%`;
  fill.style.background = color;
  track.appendChild(fill);
  heroRow.appendChild(track);
  heroTd.appendChild(heroRow);

  const heroSub = document.createElement("div");
  heroSub.className = "hg-hero-sub";
  const rec = row.components.record.raw;
  const recordChip = document.createElement("span");
  recordChip.className = "hg-hero-chip";
  recordChip.innerHTML = `Record <strong>${rec.wins}-${rec.losses}</strong>`;
  heroSub.appendChild(recordChip);

  const qual = row.components.quality.raw;
  const qualChip = document.createElement("span");
  qualChip.className = "hg-hero-chip";
  qualChip.innerHTML = `Ranked wins <strong>${qual.ranked_wins}</strong>`;
  heroSub.appendChild(qualChip);

  if (!row.eligible && row.eligibility_reason) {
    const reasonChip = document.createElement("span");
    reasonChip.className = "hg-hero-chip hg-ineligible-note";
    reasonChip.textContent = row.eligibility_reason;
    heroSub.appendChild(reasonChip);
  }
  heroTd.appendChild(heroSub);
  tr.appendChild(heroTd);

  const toggle = () => {
    expandedKey = expandedKey === key ? null : key;
    renderHodgeTable({ rows: hodgeRows });
  };
  tr.addEventListener("click", e => {
    if (e.target.tagName === "A") return;
    toggle();
  });
  expandIcon.addEventListener("click", e => {
    e.stopPropagation();
    toggle();
  });

  tbody.appendChild(tr);
  if (isExpanded) tbody.appendChild(renderExpandedRow(row, color));
}

const HG_COMPONENTS = [
  { key: "record", label: "Record", raw: c => `${c.raw.wins}-${c.raw.losses} (${(c.raw.win_pct * 100).toFixed(1)}%)` },
  { key: "quality", label: "Quality", raw: c => `${c.raw.ranked_wins} ranked wins (${c.raw.top10_wins} top-10)` },
  { key: "dominance", label: "Dominance", raw: c => `${c.raw.avg_team_points.toFixed(2)} avg team pts/match` },
  { key: "pins", label: "Pins", raw: c => `${(c.raw.pin_pct * 100).toFixed(1)}% pin rate` },
];

function renderExpandedRow(row, color) {
  const tr = document.createElement("tr");
  tr.className = "weight-breakdown expanded";

  const td = document.createElement("td");
  td.colSpan = 4;
  td.className = "hg-expanded-td";

  const grid = document.createElement("div");
  grid.className = "hg-component-grid";

  HG_COMPONENTS.forEach(({ key, label, raw }) => {
    const c = row.components[key];
    const card = document.createElement("div");
    card.className = "hg-component-card";

    const labelEl = document.createElement("div");
    labelEl.className = "hg-component-label";
    labelEl.textContent = label;
    card.appendChild(labelEl);

    const rawEl = document.createElement("div");
    rawEl.className = "hg-component-raw";
    rawEl.textContent = raw(c);
    card.appendChild(rawEl);

    const scoreRow = document.createElement("div");
    scoreRow.className = "hg-component-score-row";
    const scoreEl = document.createElement("span");
    scoreEl.className = "hg-component-score";
    scoreEl.textContent = c.score.toFixed(1);
    scoreRow.appendChild(scoreEl);
    const weightEl = document.createElement("span");
    weightEl.className = "hg-component-weight";
    weightEl.textContent = `× ${c.weight} weight`;
    scoreRow.appendChild(weightEl);
    card.appendChild(scoreRow);

    const barTrack = document.createElement("div");
    barTrack.className = "hg-component-bar-track";
    const barFill = document.createElement("div");
    barFill.className = "hg-component-bar-fill";
    barFill.style.width = `${Math.max(0, Math.min(100, c.score))}%`;
    barFill.style.background = getScoreColor(c.score);
    barTrack.appendChild(barFill);
    card.appendChild(barTrack);

    const contribEl = document.createElement("div");
    contribEl.className = "hg-component-contribution";
    contribEl.textContent = `Contributes ${c.contribution.toFixed(2)} pts to Hodge Score`;
    card.appendChild(contribEl);

    grid.appendChild(card);
  });

  td.appendChild(grid);
  tr.appendChild(td);
  return tr;
}

// ========================================
// Initialize
// ========================================
async function init() {
  try {
    document.getElementById("season-info").textContent = `Season ${HG_SEASON}`;

    const [data, colors] = await Promise.all([
      fetchJSON(`/data/awards/hodge/${HG_SEASON}/hodge_${HG_SEASON}.json`),
      loadTeamColors(),
    ]);
    teamColors = colors;

    renderHodgeTable(data);
  } catch (error) {
    console.error("Error loading Hodge Trophy data:", error);
    const eligibleTbody = document.getElementById("eligible-tbody");
    eligibleTbody.innerHTML = `<tr><td colspan="4" style="text-align:center;padding:2em;color:var(--muted);">Error loading data: ${error.message}</td></tr>`;
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
