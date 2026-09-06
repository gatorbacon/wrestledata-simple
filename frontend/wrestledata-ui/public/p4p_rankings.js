// ========================================
// Homepage P4P (pound-for-pound) + per-weight rankings table
// ========================================
// Rank order comes straight from FloWrestling's own rankings pages; record
// is "0-0" for everyone since the season hasn't started (falls back to
// last season's real record for context) -- bonus rate, pin rate, and
// TPAR are each wrestler's real numbers from the most recently completed
// season (see scripts/rankings/build_p4p_rankings.py for why). TPAR is the
// signature stat here: bigger, color-banded, with a mini meter bar. Tabs
// (P4P / 125 / 133 / ... / 285) swap which already-loaded list renders --
// one fetch on page load, same convention as the other weight-tabbed
// panels on this page (e.g. TPAR Leaders).

const P4P_SEASON = "2027";
let p4pData = null;
let currentWeight = "p4p";
let currentSort = "rank";

// Gap (in ranks) before a TPAR-vs-editorial-rank disagreement gets called
// out visually.
const TPAR_RANK_GAP_THRESHOLD = 5;

// TPAR band thresholds, checked high to low.
const TPAR_BANDS = [
  { min: 5.5, label: "Elite", cls: "tpar2-band-elite" },
  { min: 4.5, label: "Dominant", cls: "tpar2-band-dominant" },
  { min: 3.5, label: "Solid", cls: "tpar2-band-solid" },
  { min: -Infinity, label: "Developing", cls: "tpar2-band-developing" },
];

// TPAR scaled against this as "full bar" -- 5.8 (highest seen) reads as
// nearly full, not maxed.
const TPAR_METER_MAX = 6.5;

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

function tparBand(tpar) {
  if (tpar === null || tpar === undefined) return null;
  // Band against the ROUNDED value (same rounding as what's displayed), so
  // a value like 4.498 -- shown as "4.5" -- doesn't visually land in a
  // different band than its own printed number implies.
  const rounded = Math.round(tpar * 10) / 10;
  return TPAR_BANDS.find(b => rounded >= b.min);
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

// Rank-by-TPAR within the current list (nulls sort last), used to detect
// when a wrestler's real performance disagrees with their editorial rank.
function withTparRank(list) {
  const sorted = [...list].sort((a, b) => {
    if (a.tpar === null && b.tpar === null) return 0;
    if (a.tpar === null) return 1;
    if (b.tpar === null) return -1;
    return b.tpar - a.tpar;
  });
  const tparRankById = new Map();
  sorted.forEach((w, i) => tparRankById.set(w.wrestler_id || w.name, i + 1));
  return list.map(w => ({ ...w, tpar_rank: tparRankById.get(w.wrestler_id || w.name) }));
}

function sortedList(weight, sort) {
  const list = withTparRank(p4pListFor(weight));
  if (sort === "tpar") {
    return [...list].sort((a, b) => {
      if (a.tpar === null && b.tpar === null) return 0;
      if (a.tpar === null) return 1;
      if (b.tpar === null) return -1;
      return b.tpar - a.tpar;
    });
  }
  return [...list].sort((a, b) => a.rank - b.rank);
}

function renderWrestlerCell(w) {
  const photoSrc = w.photo_url;
  const crestFallback = w.team_slug ? `/assets/team_logos/${w.team_slug}.svg` : null;
  const imgTag = photoSrc
    ? `<img class="tpar2-headshot" src="${photoSrc}" alt="" ` +
      `onerror="if(!this.dataset.fb1){this.dataset.fb1=1;this.src='${crestFallback || ""}';}` +
      `else if(!this.dataset.fb2){this.dataset.fb2=1;this.src='${crestFallback ? crestFallback.replace('.svg', '.png') : ""}';}` +
      `else{this.style.visibility='hidden';}">`
    : crestFallback
      ? `<img class="tpar2-headshot tpar2-headshot--crest" src="${crestFallback}" alt="" ` +
        `onerror="if(!this.dataset.fb){this.dataset.fb=1;this.src='${crestFallback.replace('.svg', '.png')}';}else{this.style.visibility='hidden';}">`
      : `<span class="tpar2-headshot tpar2-headshot--blank"></span>`;

  const nameCell = w.wrestler_id
    ? `<a href="/wrestler.html?id=${w.wrestler_id}">${w.name}</a>`
    : w.name;

  const subParts = [];
  const gradeAbbrev = abbrevGrade(w.grade);
  if (gradeAbbrev) subParts.push(gradeAbbrev);
  if (w.weight_class) subParts.push(w.weight_class);
  const subLine = subParts.length ? `<div class="tpar2-wrestler-sub">${subParts.join(" · ")}</div>` : "";

  return (
    `<div class="tpar2-wrestler-cell">` +
    imgTag +
    `<div class="tpar2-wrestler-text"><div class="tpar2-wrestler-name">${nameCell}</div>${subLine}</div>` +
    `</div>`
  );
}

function renderTeamCell(w) {
  if (!w.team_slug) return w.team;
  return (
    `<a class="tpar2-team-cell" href="/team.html?team=${w.team_slug}">` +
    `<span class="tpar2-team-icon-slot">` +
    `<img class="tpar2-team-crest" src="/assets/team_logos/${w.team_slug}.svg" alt="" ` +
    `onerror="if(!this.dataset.fb){this.dataset.fb=1;this.src='/assets/team_logos/${w.team_slug}.png';}else{this.remove();}">` +
    `</span>` +
    `<span class="tpar2-team-name">${w.team}</span></a>`
  );
}

function renderMeter(w, band) {
  if (w.tpar === null || w.tpar === undefined) {
    return `<div class="tpar2-meter-track tpar2-meter-track--empty"></div>`;
  }
  const pct = Math.min(Math.max(w.tpar / TPAR_METER_MAX, 0), 1) * 100;
  return (
    `<div class="tpar2-meter-track">` +
    `<div class="tpar2-meter-fill ${band.cls}" style="width:${pct.toFixed(0)}%"></div>` +
    `</div>`
  );
}

function renderTparCell(w, band) {
  if (w.tpar === null || w.tpar === undefined) {
    return (
      `<div class="tpar2-tpar-row"><span class="tpar2-tpar-value tpar2-band-nodata">—</span></div>` +
      `<div class="tpar2-nodata-label">Insufficient data</div>` +
      renderMeter(w, null)
    );
  }
  const eliteBadge = band.label === "Elite" ? `<span class="tpar2-elite-badge">Elite</span>` : "";
  return (
    `<div class="tpar2-tpar-row">` +
    `<span class="tpar2-tpar-value ${band.cls}">${w.tpar.toFixed(1)}</span>` +
    eliteBadge +
    `</div>` +
    renderMeter(w, band)
  );
}

function renderBonusCell(w, band) {
  const cls = band ? band.cls : "";
  return `<span class="tpar2-bonus-value ${cls}">${p4pPct(w.bonus_rate)}</span>`;
}

function renderRecordCell(w) {
  if (w.record && w.record !== "0-0") {
    return w.record;
  }
  if (w.prior_record) {
    return `<span class="tpar2-prior-record">${w.prior_record}</span>`;
  }
  return p4pSafe(w.record);
}

function rankGapInfo(w) {
  if (!w.tpar_rank || w.tpar === null) return null;
  const gap = w.rank - w.tpar_rank; // positive = TPAR thinks they should rank higher (better) than editorial rank
  if (gap >= TPAR_RANK_GAP_THRESHOLD) return "above"; // TPAR > rank (undervalued by editorial rank)
  if (-gap >= TPAR_RANK_GAP_THRESHOLD) return "below"; // TPAR < rank (overvalued by editorial rank)
  return null;
}

function renderP4PTable(weight, sort) {
  const tbody = document.querySelector("#p4p-table tbody");
  if (!tbody) return;

  const list = sortedList(weight, sort);
  tbody.innerHTML = list.map(w => {
    const gap = rankGapInfo(w);
    const rowCls = gap === "above" ? "tpar2-row-gap-above" : gap === "below" ? "tpar2-row-gap-below" : "";
    const band = tparBand(w.tpar);

    return (
      `<tr class="${rowCls}">` +
      `<td class="rank-cell"><span class="rank-badge ${w.rank <= 3 ? `medal-${["gold", "silver", "bronze"][w.rank - 1]}` : "standard"}">#${w.rank}</span></td>` +
      `<td class="name">${renderWrestlerCell(w)}</td>` +
      `<td>${renderTeamCell(w)}</td>` +
      `<td class="num">${renderTparCell(w, band)}</td>` +
      `<td class="num">${renderBonusCell(w, band)}</td>` +
      `<td class="num tpar2-pin-value">${p4pPct(w.pin_rate)}</td>` +
      `<td class="tpar2-record-value">${renderRecordCell(w)}</td>` +
      `</tr>`
    );
  }).join("");
}

function setupP4PTabs() {
  document.querySelectorAll("#p4p-weight-tabs .hp-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("#p4p-weight-tabs .hp-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      currentWeight = tab.dataset.weight;
      renderP4PTable(currentWeight, currentSort);
    });
  });
}

function setupSortControl() {
  const select = document.getElementById("p4p-sort-select");
  if (!select) return;
  select.addEventListener("change", () => {
    currentSort = select.value;
    renderP4PTable(currentWeight, currentSort);
  });
}

function renderP4PRankings(data) {
  const section = document.getElementById("p4p-section");
  if (!data || !data.p4p || !data.p4p.length) {
    if (section) section.hidden = true;
    return;
  }

  p4pData = data;
  setupP4PTabs();
  setupSortControl();
  renderP4PTable("p4p", "rank");
}

document.addEventListener("DOMContentLoaded", async () => {
  const data = await loadP4PRankings();
  renderP4PRankings(data);
});
