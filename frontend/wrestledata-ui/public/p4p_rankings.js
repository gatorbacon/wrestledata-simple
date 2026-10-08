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
  if (sort === "intermat") {
    return [...list].sort((a, b) => {
      if (a.intermat_rank === null && b.intermat_rank === null) return 0;
      if (a.intermat_rank === null || a.intermat_rank === undefined) return 1;
      if (b.intermat_rank === null || b.intermat_rank === undefined) return -1;
      return a.intermat_rank - b.intermat_rank;
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
    ? `<a href="${wrestlerHref(w.url_path, w.wrestler_id)}">${w.name}</a>`
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
    `<a class="dpg-team-cell" href="${teamHref(w.team_slug)}">` +
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

// Which rank number a row displays/badges depends on the active sort: Flo's
// own rank under "rank"/"dpg" (DPG sort re-orders rows but still shows the
// editorial rank, same as before -- that's what makes the DPG-vs-rank gap
// highlighting below meaningful), InterMat's own rank when sorted by it, so
// the badge always matches the number the list is actually ordered by.
function displayRankFor(w, sort) {
  return sort === "intermat" ? w.intermat_rank : w.rank;
}

function renderRankBadge(rank) {
  if (rank === null || rank === undefined) {
    return `<span class="rank-badge standard">—</span>`;
  }
  const medal = rank <= 3 ? `medal-${["gold", "silver", "bronze"][rank - 1]}` : "standard";
  return `<span class="rank-badge ${medal}">#${rank}</span>`;
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
      `<td class="rank-cell">${renderRankBadge(displayRankFor(w, sort))}</td>` +
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
      rank: displayRankFor(w, sort),
      wrestlerId: w.wrestler_id,
      urlPath: w.url_path,
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

// InterMat doesn't publish a pound-for-pound (cross-weight) list -- only
// per-weight rankings, confirmed when the scraper was built (no P4P tab on
// their page at all). So intermat_rank on the P4P tab is really just each
// wrestler's own single-weight rank, not a true cross-weight order -- e.g.
// every weight's #1 would show as "#1" here, which reads as broken, not
// informative.
//
// Rather than grey out the InterMat sort option whenever P4P happens to be
// selected (P4P is the default landing view, so that greyed it out far too
// often for a wrestler who just wants to see InterMat's numbers) -- picking
// "InterMat Rank" while on the P4P tab jumps the weight tab to 125 instead,
// so it's always one click away. The P4P tab itself is what gets disabled,
// but only while InterMat sort is actually active, since that's the one
// combination with no real data behind it.
const INTERMAT_DEFAULT_WEIGHT = "125";

function updateP4PTabAvailability() {
  const disabled = currentSort === "intermat";
  const p4pTab = document.querySelector('#p4p-weight-tabs .hp-tab[data-weight="p4p"]');
  if (!p4pTab) return;
  p4pTab.disabled = disabled;
  p4pTab.classList.toggle("hp-tab-disabled", disabled);
  p4pTab.title = disabled ? "InterMat doesn't publish a pound-for-pound list -- pick a weight class" : "";
}

function setActiveWeightTab(weight) {
  document.querySelectorAll("#p4p-weight-tabs .hp-tab").forEach(t => {
    t.classList.toggle("active", t.dataset.weight === weight);
  });
}

function setupP4PTabs() {
  document.querySelectorAll("#p4p-weight-tabs .hp-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      currentWeight = tab.dataset.weight;
      setActiveWeightTab(currentWeight);
      renderP4P(currentWeight, currentSort);
    });
  });
}

const SORT_SUBTEXT = {
  rank: "Rankings provided by FloWrestling",
  intermat: "Rankings provided by InterMat — a second editorial source, tracked in parallel for comparison. FloWrestling's rank stays the site's official rank everywhere else.",
  dpg: "Dual Points Gained - Measures how many extra dual points a wrestler adds or subtracts each time they wrestle, compared with what a typical wrestler gets against that same opponent.",
};

function updateSortSubtext(sort) {
  const el = document.getElementById("sort-subtext");
  if (!el) return;
  el.textContent = SORT_SUBTEXT[sort] || "";
}

function applySortChange(sort) {
  currentSort = sort;
  if (currentSort === "intermat" && currentWeight === "p4p") {
    currentWeight = INTERMAT_DEFAULT_WEIGHT;
    setActiveWeightTab(currentWeight);
  }

  document.querySelectorAll(".sort-pill[data-sort]").forEach(p => p.classList.toggle("active", p.dataset.sort === currentSort));
  const select = document.getElementById("p4p-sort-select");
  if (select) select.value = currentSort;

  updateSortSubtext(currentSort);
  updateP4PTabAvailability();
  renderP4P(currentWeight, currentSort);
}

function setupSortControl() {
  // Homepage widget: dropdown.
  const select = document.getElementById("p4p-sort-select");
  if (select) {
    select.addEventListener("change", () => applySortChange(select.value));
  }

  // Rankings page: "Sort by" pills.
  document.querySelectorAll(".sort-pill[data-sort]").forEach(pill => {
    pill.addEventListener("click", () => applySortChange(pill.dataset.sort));
  });

  updateSortSubtext(currentSort);
}

// Deep-link support: a page linking in with ?weight=133 (e.g. the
// homepage's other "DPG Leaders" panel, whose "See all" link points here)
// should land on that weight's tab already selected, not always P4P.
function initialWeightFromURL(data) {
  const w = new URLSearchParams(window.location.search).get("weight");
  if (w && data.weights && data.weights[w]) return w;
  return "p4p";
}

function updateSeasonInfoDate(data) {
  const el = document.getElementById("season-info");
  if (!el || !data || !data.ranking_date) return;
  const d = new Date(data.ranking_date + "T00:00:00");
  el.textContent = isNaN(d)
    ? data.ranking_date
    : d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
}

function renderP4PRankings(data) {
  const section = document.getElementById("p4p-section");
  if (!data || !data.p4p || !data.p4p.length) {
    if (section) section.hidden = true;
    return;
  }

  updateSeasonInfoDate(data);
  p4pData = data;
  currentWeight = initialWeightFromURL(data);
  document.querySelectorAll("#p4p-weight-tabs .hp-tab").forEach(t => {
    t.classList.toggle("active", t.dataset.weight === currentWeight);
  });
  setupP4PTabs();
  setupSortControl();
  updateP4PTabAvailability();
  renderP4P(currentWeight, currentSort);
}

document.addEventListener("DOMContentLoaded", async () => {
  const data = await loadP4PRankings();
  renderP4PRankings(data);
});
