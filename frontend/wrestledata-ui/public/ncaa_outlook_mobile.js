// ========================================
// Mobile (<768px) "NCAA team outlook" card -- one card, 3 tabs (Title /
// Trophy / Points), replacing the desktop championship crosstab + trophy
// widget on small screens. Reuses the exact same /data/team_odds/{season}/
// feed those already fetch; no new model run, no new fields. >=768px keeps
// #title-contenders-section / #trophy-chances-section /
// #team-odds-preview-section exactly as they are (this card is CSS-hidden
// there).
// ========================================

const OUTLOOK_SEASON = "2027";
const OUTLOOK_ROW_CAP = 6;
const OUTLOOK_TAB_STORAGE_KEY = "outlookTab";

const OUTLOOK_SLUG_ALIASES = {
  "ok state": "oklahoma_state",
  "nd state": "north_dakota_state",
  "sd state": "south_dakota_state",
  "app state": "appalachian_state",
  "uni": "northern_iowa",
  "army": "army_west_point",
  "siue": "siu_edwardsville",
  "n. colorado": "northern_colorado",
};

function outlookSlug(name) {
  if (!name) return "";
  const alias = OUTLOOK_SLUG_ALIASES[name.trim().toLowerCase()];
  if (alias) return alias;
  return name.toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^\w_]/g, "")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

// One decimal; <0.05% reads as "<0.1%" rather than a misleading "0.0%" for
// the many teams whose title/trophy odds round to zero.
function outlookFormatPct(v) {
  if (v === null || v === undefined) return "—";
  if (v < 0.05) return "<0.1%";
  return `${v.toFixed(1)}%`;
}

function outlookFormatXTP(v) {
  if (v === null || v === undefined) return "—";
  return v.toFixed(1);
}

function outlookFormatRange(low, high) {
  if (low === null || low === undefined || high === null || high === undefined) return null;
  return `${Math.round(low)}–${Math.round(high)}`;
}

const OUTLOOK_HELPER_TEXT = {
  title: "Chance to win the NCAA team title",
  trophy: "Chance to finish top 4",
  points: "Expected NCAA team points (xTP)",
};

let outlookRows = [];
let outlookCurrentTab = "title";

async function loadOutlookTeams() {
  try {
    const idxRes = await fetch(`/data/team_odds/${OUTLOOK_SEASON}/index.json`);
    if (!idxRes.ok) return [];
    const idx = await idxRes.json();
    const newestDate = (idx.dates || [])[0];
    if (!newestDate) return [];
    const res = await fetch(`/data/team_odds/${OUTLOOK_SEASON}/${newestDate}.json`);
    if (!res.ok) return [];
    const data = await res.json();
    return (data.teams || []).map(t => {
      const p = t.p_place || {};
      const trophyPct = (p["1"] || 0) + (p["2"] || 0) + (p["3"] || 0) + (p["4"] || 0);
      return {
        team: t.team,
        slug: outlookSlug(t.team),
        xTP: t.expected ?? null,
        low: t.p5 ?? null,
        high: t.p95 ?? null,
        titlePct: t.p_1st ?? null,
        trophyPct,
      };
    });
  } catch {
    return [];
  }
}

function outlookSortedTop(tab) {
  const withMetric = outlookRows.map(r => ({
    ...r,
    _metric: tab === "title" ? r.titlePct : tab === "trophy" ? r.trophyPct : r.xTP,
  }));
  withMetric.sort((a, b) => (b._metric ?? -Infinity) - (a._metric ?? -Infinity));
  return withMetric.slice(0, OUTLOOK_ROW_CAP);
}

function outlookRowHTML(row, tab, maxXTP) {
  const range = outlookFormatRange(row.low, row.high);

  let heroText, subtitleText, barPct;
  if (tab === "title") {
    heroText = outlookFormatPct(row.titlePct);
    subtitleText = range ? `${outlookFormatXTP(row.xTP)} xTP · ${range}` : `${outlookFormatXTP(row.xTP)} xTP`;
    barPct = row.titlePct === null || row.titlePct === undefined ? 0 : Math.max(0, Math.min(100, row.titlePct));
  } else if (tab === "trophy") {
    heroText = outlookFormatPct(row.trophyPct);
    subtitleText = range ? `${outlookFormatXTP(row.xTP)} xTP · ${range}` : `${outlookFormatXTP(row.xTP)} xTP`;
    barPct = row.trophyPct === null || row.trophyPct === undefined ? 0 : Math.max(0, Math.min(100, row.trophyPct));
  } else {
    heroText = outlookFormatXTP(row.xTP);
    const titleStr = row.titlePct === null || row.titlePct === undefined ? "—" : outlookFormatPct(row.titlePct);
    subtitleText = range ? `${titleStr} title · ${range}` : `${titleStr} title`;
    barPct = (row.xTP === null || row.xTP === undefined || !maxXTP) ? 0 : Math.max(0, Math.min(100, (row.xTP / maxXTP) * 100));
  }

  const crest =
    `<img class="outlook-logo" src="/assets/team_logos/${row.slug}.svg" alt="" ` +
    `onerror="if(!this.dataset.fb){this.dataset.fb=1;this.src='/assets/team_logos/${row.slug}.png';}else{this.style.visibility='hidden';}">`;

  return (
    `<a class="outlook-row" href="/team.html?team=${row.slug}">` +
    crest +
    `<span class="outlook-main">` +
    `<span class="outlook-name-hero">` +
    `<span class="outlook-name">${row.team}</span>` +
    `<span class="outlook-hero">${heroText}</span>` +
    `</span>` +
    `<span class="outlook-subtitle">${subtitleText}</span>` +
    `<span class="outlook-bar-track"><span class="outlook-bar-fill" style="width:${barPct.toFixed(1)}%"></span></span>` +
    `</span>` +
    `</a>`
  );
}

function renderOutlookList() {
  const list = document.getElementById("outlook-list");
  if (!list) return;

  const top = outlookSortedTop(outlookCurrentTab);
  const maxXTP = outlookCurrentTab === "points"
    ? Math.max(...top.map(r => r.xTP || 0), 1)
    : null;

  list.innerHTML = top.map(row => outlookRowHTML(row, outlookCurrentTab, maxXTP)).join("");

  const helper = document.getElementById("outlook-helper");
  if (helper) helper.textContent = OUTLOOK_HELPER_TEXT[outlookCurrentTab];
}

function setOutlookTab(tab) {
  outlookCurrentTab = tab;
  try { sessionStorage.setItem(OUTLOOK_TAB_STORAGE_KEY, tab); } catch { /* ignore */ }

  document.querySelectorAll("#outlook-tabs .outlook-tab").forEach(btn => {
    const isActive = btn.dataset.tab === tab;
    btn.classList.toggle("active", isActive);
    btn.setAttribute("aria-selected", String(isActive));
  });

  renderOutlookList();
}

function initOutlookTabs() {
  document.querySelectorAll("#outlook-tabs .outlook-tab").forEach(btn => {
    btn.addEventListener("click", () => setOutlookTab(btn.dataset.tab));
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  const section = document.getElementById("ncaa-outlook-section");
  if (!section) return;

  initOutlookTabs();

  let storedTab = "title";
  try {
    const stored = sessionStorage.getItem(OUTLOOK_TAB_STORAGE_KEY);
    if (stored === "title" || stored === "trophy" || stored === "points") storedTab = stored;
  } catch { /* ignore */ }

  outlookRows = await loadOutlookTeams();
  if (!outlookRows.length) {
    section.hidden = true;
    return;
  }

  setOutlookTab(storedTab);
});
