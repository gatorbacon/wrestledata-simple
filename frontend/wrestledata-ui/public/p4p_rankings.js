// ========================================
// Homepage P4P (pound-for-pound) + per-weight rankings table
// ========================================
// Rank order comes straight from FloWrestling's own rankings pages; record
// is "0-0" for everyone since the season hasn't started (falls back to
// last season's real record for context) -- bonus rate, pin rate, and
// DPG are each wrestler's real numbers from the most recently completed
// season (see scripts/rankings/build_p4p_rankings.py for why). DPG is the
// signature stat here: bigger, color-banded, with a mini meter bar. Tabs
// (P4P / 125 / 133 / ... / 285) swap which already-loaded list renders --
// one fetch on page load, same convention as the other weight-tabbed
// panels on this page (e.g. DPG Leaders).

const P4P_SEASON = "2027";
let p4pData = null;
let currentWeight = "p4p";
let currentSort = "rank";

// Gap (in ranks) before a DPG-vs-editorial-rank disagreement gets called
// out visually.
const DPG_RANK_GAP_THRESHOLD = 5;

// DPG band thresholds, checked high to low.
const DPG_BANDS = [
  { min: 5.5, label: "Elite", cls: "dpg-band-elite" },
  { min: 4.5, label: "Dominant", cls: "dpg-band-dominant" },
  { min: 3.5, label: "Solid", cls: "dpg-band-solid" },
  { min: -Infinity, label: "Developing", cls: "dpg-band-developing" },
];

// DPG scaled against this as "full bar" -- 5.8 (highest seen) reads as
// nearly full, not maxed.
const DPG_METER_MAX = 6.5;

const GRADE_ABBREV = [
  [/redshirt.*fr|r-?fr/i, "R-FR"],
  [/redshirt.*so|r-?so/i, "R-SO"],
  [/redshirt.*jr|r-?jr/i, "R-JR"],
  [/redshirt.*sr|r-?sr/i, "R-SR"],
  [/fresh|^fr\.?$/i, "FR"],
  [/soph|^so\.?$/i, "SO"],
  [/junior|^jr\.?$/i, "JR"],
  [/senior|^sr\.?$/i, "SR"],
];

function p4pSafe(v, fmt) {
  if (v === null || v === undefined || v === "") return "—";
  return fmt ? fmt(v) : v;
}

function p4pPct(v) {
  return p4pSafe(v, n => `${(n * 100).toFixed(1)}%`);
}

function abbrevGrade(grade) {
  if (!grade) return "";
  for (const [re, short] of GRADE_ABBREV) {
    if (re.test(grade)) return short;
  }
  return grade;
}

function dpgBand(dpg) {
  if (dpg === null || dpg === undefined) return null;
  // Band against the ROUNDED value (same rounding as what's displayed), so
  // a value like 4.498 -- shown as "4.5" -- doesn't visually land in a
  // different band than its own printed number implies.
  const rounded = Math.round(dpg * 10) / 10;
  return DPG_BANDS.find(b => rounded >= b.min);
}

async function loadP4PRankings() {
  try {
    const res = await fetch(`/data/p4p/${P4P_SEASON}.json`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function p4pListFor(weight) {
  if (!p4pData) return [];
  if (weight === "p4p") return p4pData.p4p || [];
  return (p4pData.weights || {})[weight] || [];
}

// Rank-by-DPG within the current list (nulls sort last), used to detect
// when a wrestler's real performance disagrees with their editorial rank.
function withDpgRank(list) {
  const sorted = [...list].sort((a, b) => {
    if (a.dpg === null && b.dpg === null) return 0;
    if (a.dpg === null) return 1;
    if (b.dpg === null) return -1;
    return b.dpg - a.dpg;
  });
  const dpgRankById = new Map();
  sorted.forEach((w, i) => dpgRankById.set(w.wrestler_id || w.name, i + 1));
  return list.map(w => ({ ...w, dpg_rank: dpgRankById.get(w.wrestler_id || w.name) }));
}

function sortedList(weight, sort) {
  const list = withDpgRank(p4pListFor(weight));
  if (sort === "dpg") {
    return [...list].sort((a, b) => {
      if (a.dpg === null && b.dpg === null) return 0;
      if (a.dpg === null) return 1;
      if (b.dpg === null) return -1;
      return b.dpg - a.dpg;
    });
  }
  return [...list].sort((a, b) => a.rank - b.rank);
}

function renderWrestlerCell(w) {
  const photoSrc = w.photo_url;
  const crestFallback = w.team_slug ? `/assets/team_logos/${w.team_slug}.svg` : null;
  const imgTag = photoSrc
    ? `<img class="dpg-headshot" src="${photoSrc}" alt="" ` +
      `onerror="if(!this.dataset.fb1){this.dataset.fb1=1;this.src='${crestFallback || ""}';}` +
      `else if(!this.dataset.fb2){this.dataset.fb2=1;this.src='${crestFallback ? crestFallback.replace('.svg', '.png') : ""}';}` +
      `else{this.style.visibility='hidden';}">`
    : crestFallback
      ? `<img class="dpg-headshot dpg-headshot--crest" src="${crestFallback}" alt="" ` +
        `onerror="if(!this.dataset.fb){this.dataset.fb=1;this.src='${crestFallback.replace('.svg', '.png')}';}else{this.style.visibility='hidden';}">`
      : `<span class="dpg-headshot dpg-headshot--blank"></span>`;

  const nameCell = w.wrestler_id
    ? `<a href="/wrestler.html?id=${w.wrestler_id}">${w.name}</a>`
    : w.name;

  const subParts = [];
  const gradeAbbrev = abbrevGrade(w.grade);
  if (gradeAbbrev) subParts.push(gradeAbbrev);
  if (w.weight_class) subParts.push(w.weight_class);
  const subLine = subParts.length ? `<div class="dpg-wrestler-sub">${subParts.join(" · ")}</div>` : "";

  return (
    `<div class="dpg-wrestler-cell">` +
    imgTag +
    `<div class="dpg-wrestler-text"><div class="dpg-wrestler-name">${nameCell}</div>${subLine}</div>` +
    `</div>`
  );
}

function renderTeamCell(w) {
  if (!w.team_slug) return w.team;
  return (
    `<a class="dpg-team-cell" href="/team.html?team=${w.team_slug}">` +
    `<span class="dpg-team-icon-slot">` +
    `<img class="dpg-team-crest" src="/assets/team_logos/${w.team_slug}.svg" alt="" ` +
    `onerror="if(!this.dataset.fb){this.dataset.fb=1;this.src='/assets/team_logos/${w.team_slug}.png';}else{this.remove();}">` +
    `</span>` +
    `<span class="dpg-team-name">${w.team}</span></a>`
  );
}

function renderMeter(w, band) {
  if (w.dpg === null || w.dpg === undefined) {
    return `<div class="dpg-meter-track dpg-meter-track--empty"></div>`;
  }
  const pct = Math.min(Math.max(w.dpg / DPG_METER_MAX, 0), 1) * 100;
  return (
    `<div class="dpg-meter-track">` +
    `<div class="dpg-meter-fill ${band.cls}" style="width:${pct.toFixed(0)}%"></div>` +
    `</div>`
  );
}

function renderDpgCell(w, band) {
  if (w.dpg === null || w.dpg === undefined) {
    return (
      `<div class="dpg-dpg-row"><span class="dpg-dpg-value dpg-band-nodata">—</span></div>` +
      `<div class="dpg-nodata-label">Insufficient data</div>` +
      renderMeter(w, null)
    );
  }
  const eliteBadge = band.label === "Elite" ? `<span class="dpg-elite-badge">Elite</span>` : "";
  return (
    `<div class="dpg-dpg-row">` +
    `<span class="dpg-dpg-value ${band.cls}">${w.dpg.toFixed(1)}</span>` +
    eliteBadge +
    `</div>` +
    renderMeter(w, band)
  );
}

function renderBonusCell(w, band) {
  const cls = band ? band.cls : "";
  return `<span class="dpg-bonus-value ${cls}">${p4pPct(w.bonus_rate)}</span>`;
}

function renderRecordCell(w) {
  if (w.record && w.record !== "0-0") {
    return w.record;
  }
  if (w.prior_record) {
    return `<span class="dpg-prior-record">${w.prior_record}</span>`;
  }
  return p4pSafe(w.record);
}

function rankGapInfo(w) {
  if (!w.dpg_rank || w.dpg === null) return null;
  const gap = w.rank - w.dpg_rank; // positive = DPG thinks they should rank higher (better) than editorial rank
  if (gap >= DPG_RANK_GAP_THRESHOLD) return "above"; // DPG > rank (undervalued by editorial rank)
  if (-gap >= DPG_RANK_GAP_THRESHOLD) return "below"; // DPG < rank (overvalued by editorial rank)
  return null;
}

function renderP4PTable(weight, sort) {
  const tbody = document.querySelector("#p4p-table tbody");
  if (!tbody) return;

  const list = sortedList(weight, sort);
  tbody.innerHTML = list.map(w => {
    const gap = rankGapInfo(w);
    const rowCls = gap === "above" ? "dpg-row-gap-above" : gap === "below" ? "dpg-row-gap-below" : "";
    const band = dpgBand(w.dpg);

    return (
      `<tr class="${rowCls}">` +
      `<td class="rank-cell"><span class="rank-badge ${w.rank <= 3 ? `medal-${["gold", "silver", "bronze"][w.rank - 1]}` : "standard"}">#${w.rank}</span></td>` +
      `<td class="name">${renderWrestlerCell(w)}</td>` +
      `<td>${renderTeamCell(w)}</td>` +
      `<td class="num">${renderDpgCell(w, band)}</td>` +
      `<td class="num">${renderBonusCell(w, band)}</td>` +
      `<td class="num dpg-pin-value">${p4pPct(w.pin_rate)}</td>` +
      `<td class="dpg-record-value">${renderRecordCell(w)}</td>` +
      `</tr>`
    );
  }).join("");
}

// Mobile (<768px) row list -- same data/sort/filter state as the desktop
// table, rendered as compact link-rows via the shared mobile_rank_row.js
// component instead of a <table>. Desktop just keeps this hidden via CSS.
function renderP4PMobileList(weight, sort) {
  const list = document.getElementById("p4p-mobile-list");
  if (!list || typeof renderMobileRankRow !== "function") return;

  const rows = sortedList(weight, sort);
  list.innerHTML = rows.map(w => {
    const gap = rankGapInfo(w);
    const gapCls = gap === "above" ? "dpg-row-gap-above" : gap === "below" ? "dpg-row-gap-below" : "";
    return renderMobileRankRow({
      rank: w.rank,
      wrestlerId: w.wrestler_id,
      name: w.name,
      team: w.team,
      teamSlug: w.team_slug,
      teamAbbr: w.team_abbr,
      weightClass: w.weight_class,
      grade: w.grade,
      photoUrl: w.photo_url,
      dpg: w.dpg,
      gapCls,
    });
  }).join("");
}

function renderP4P(weight, sort) {
  renderP4PTable(weight, sort);
  renderP4PMobileList(weight, sort);
}

function setupP4PTabs() {
  document.querySelectorAll("#p4p-weight-tabs .hp-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("#p4p-weight-tabs .hp-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentWeight = tab.dataset.weight;
      renderP4P(currentWeight, currentSort);
    });
  });
}

function setupSortControl() {
  const select = document.getElementById("p4p-sort-select");
  if (!select) return;
  select.addEventListener("change", () => {
    currentSort = select.value;
    renderP4P(currentWeight, currentSort);
  });
}

// Deep-link support: a page linking in with ?weight=133 (e.g. the
// homepage's other "DPG Leaders" panel, whose "See all" link points here)
// should land on that weight's tab already selected, not always P4P.
function initialWeightFromURL(data) {
  const w = new URLSearchParams(window.location.search).get("weight");
  if (w && data.weights && data.weights[w]) return w;
  return "p4p";
}

function renderP4PRankings(data) {
  const section = document.getElementById("p4p-section");
  if (!data || !data.p4p || !data.p4p.length) {
    if (section) section.hidden = true;
    return;
  }

  p4pData = data;
  currentWeight = initialWeightFromURL(data);
  document.querySelectorAll("#p4p-weight-tabs .hp-tab").forEach(t => {
    t.classList.toggle("active", t.dataset.weight === currentWeight);
  });
  setupP4PTabs();
  setupSortControl();
  renderP4P(currentWeight, currentSort);
}

document.addEventListener("DOMContentLoaded", async () => {
  const data = await loadP4PRankings();
  renderP4PRankings(data);
});
