// ========================================
// Freshman of the Year Watch
// ========================================
// Data: data/awards/freshman/{season}/freshman_{season}.json, built by
// scripts/rankings/freshman_of_year.py (ranked freshmen, stats from each
// wrestler's profile, DPG = season mat_value.mv_avg, rows ordered by DPG;
// ncaa = NCAA finish, null for everyone until the NCAAs are done -- then the
// NCAAs column is hidden). Styled like the
// Rankings page: same dpg-* table classes, DPG bands and mobile rows
// (mobile_rank_row.js helpers).

const FRESHMAN_SEASON = "2026";

const FR_DPG_BANDS = [
  { min: 5.5, label: "Elite", cls: "dpg-band-elite" },
  { min: 4.5, label: "Dominant", cls: "dpg-band-dominant" },
  { min: 3.5, label: "Solid", cls: "dpg-band-solid" },
  { min: -Infinity, label: "Developing", cls: "dpg-band-developing" },
];
const FR_DPG_METER_MAX = 6.5;

function frSafe(v, fmt) {
  if (v === null || v === undefined || v === "") return "—";
  return fmt ? fmt(v) : v;
}

function frPct(v) {
  return frSafe(v, n => `${Math.round(n * 100)}%`);
}

function frEsc(s) {
  return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function frDpgBand(dpg) {
  if (dpg === null || dpg === undefined) return null;
  const rounded = Math.round(dpg * 10) / 10;
  return FR_DPG_BANDS.find(b => rounded >= b.min);
}

function frProfileHref(row) {
  return `/wrestler.html?id=${encodeURIComponent(row.wrestler_id)}&view=season`;
}

function frRankBadge(rank) {
  const cls = rank <= 3 ? `medal-${["gold", "silver", "bronze"][rank - 1]}` : "standard";
  return `<span class="rank-badge ${cls}">#${rank}</span>`;
}

// "RS Fr." (grade-override spelling) isn't in the shared abbreviation list.
function frGrade(grade) {
  return /^rs\.?\s*fr/i.test(grade || "") ? "R-FR" : mobileAbbrevGrade(grade);
}

function frSubLine(row) {
  const parts = [];
  const grade = frGrade(row.grade);
  if (grade) parts.push(grade);
  if (row.weight) parts.push(row.weight_rank ? `#${row.weight_rank} at ${row.weight}` : row.weight);
  return parts.join(" · ");
}

function frWrestlerCell(row) {
  const crest = row.team_slug ? `/assets/team_logos/${row.team_slug}.svg` : null;
  const img = row.photo_url
    ? `<img class="dpg-headshot" src="${frEsc(row.photo_url)}" alt="" loading="lazy" ` +
      `onerror="if(!this.dataset.fb&&'${crest || ""}'){this.dataset.fb=1;this.classList.add('dpg-headshot--crest');this.src='${crest || ""}';}else{this.style.visibility='hidden';}">`
    : crest
      ? `<img class="dpg-headshot dpg-headshot--crest" src="${crest}" alt="" onerror="this.style.visibility='hidden'">`
      : `<span class="dpg-headshot dpg-headshot--blank"></span>`;
  return (
    `<div class="dpg-wrestler-cell">${img}` +
    `<div class="dpg-wrestler-text">` +
    `<div class="dpg-wrestler-name"><a href="${frProfileHref(row)}">${frEsc(row.name)}</a></div>` +
    `<div class="dpg-wrestler-sub">${frEsc(frSubLine(row))}</div>` +
    `</div></div>`
  );
}

function frTeamCell(row) {
  if (!row.team_slug) return frEsc(row.team);
  return (
    `<a class="dpg-team-cell" href="/team.html?team=${row.team_slug}">` +
    `<span class="dpg-team-icon-slot"><img class="dpg-team-crest" src="/assets/team_logos/${row.team_slug}.svg" alt="" ` +
    `onerror="if(!this.dataset.fb){this.dataset.fb=1;this.src='/assets/team_logos/${row.team_slug}.png';}else{this.remove();}"></span>` +
    `<span class="dpg-team-name">${frEsc(row.team)}</span></a>`
  );
}

function frOrdinal(n) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

function frNcaaSub(n) {
  const parts = [];
  if (n.seed) parts.push(`#${n.seed} seed`);
  parts.push(`${n.wins}-${n.losses}`);
  return parts.join(" · ");
}

function frNcaaCell(n) {
  if (!n) return "—";
  if (n.dnq) return `<span class="fr-place-dnp">Did not qualify</span>`;
  const main = n.place
    ? `<div class="fr-place">${frOrdinal(n.place)}</div>`
    : `<div class="fr-place fr-place-dnp">Did not place</div>`;
  return main + `<div class="fr-place-sub">${frNcaaSub(n)}</div>`;
}

function frNcaaShort(n) {
  if (!n) return "";
  if (n.dnq) return "NCAA: DNQ";
  return n.place ? `NCAA <strong>${frOrdinal(n.place)}</strong>` : "NCAA: DNP";
}

function frDpgCell(dpg) {
  const band = frDpgBand(dpg);
  if (!band) {
    return `<div class="dpg-dpg-row"><span class="dpg-dpg-value dpg-band-nodata">—</span></div>`;
  }
  const pct = Math.min(Math.max(dpg / FR_DPG_METER_MAX, 0), 1) * 100;
  const elite = band.label === "Elite" ? `<span class="dpg-elite-badge">Elite</span>` : "";
  return (
    `<div class="dpg-dpg-row"><span class="dpg-dpg-value ${band.cls}">${dpg.toFixed(1)}</span>${elite}</div>` +
    `<div class="dpg-meter-track"><div class="dpg-meter-fill ${band.cls}" style="width:${pct.toFixed(0)}%"></div></div>`
  );
}

function renderFreshmanTable(rows) {
  const tbody = document.querySelector("#freshman-table tbody");
  tbody.innerHTML = rows.map(row => {
    const m = row.metrics || {};
    return (
      `<tr>` +
      `<td class="rank-cell">${frRankBadge(row.rank)}</td>` +
      `<td class="name">${frWrestlerCell(row)}</td>` +
      `<td>${frTeamCell(row)}</td>` +
      `<td>${frDpgCell(m.dpg)}</td>` +
      `<td class="fr-ncaa-col">${frNcaaCell(row.ncaa)}</td>` +
      `<td class="num fr-group fr-strong">${frEsc(frSafe(row.record))}</td>` +
      `<td class="num">${frPct(m.bonus_pct)}</td>` +
      `<td class="num">${frPct(m.fall_pct)}</td>` +
      `<td class="num fr-group">${frSafe(m.ranked_wins)}</td>` +
      `<td class="num">${frSafe(m.top10_wins)}</td>` +
      `<td class="num">${m.ranked_wins ? frPct(m.ranked_bonus_pct) : "—"}</td>` +
      `</tr>`
    );
  }).join("");
}

// Phone rows: same shell as the Rankings page's mobile rows (dpg-mobile-*),
// with DPG as the big number and the NCAA finish under it.
function renderFreshmanMobile(rows) {
  const list = document.getElementById("freshman-mobile-list");
  list.innerHTML = rows.map(row => {
    const m = row.metrics || {};
    const band = frDpgBand(m.dpg);
    const rankCls = mobileRankChipClass(row.rank);
    const meta = [frGrade(row.grade), row.weight, mobileTeamAbbr(row.team), row.record]
      .filter(Boolean).join(" · ");
    const crest = row.team_slug
      ? `<img class="dpg-mobile-team-mark" src="/assets/team_logos/${row.team_slug}.svg" alt="" onerror="this.remove()">`
      : "";
    const avatar = row.photo_url
      ? `<img class="dpg-mobile-avatar" src="${frEsc(row.photo_url)}" alt="" loading="lazy" onerror="this.style.display='none'">`
      : "";
    const dpg = band
      ? `<span class="dpg-mobile-dpg ${band.cls}">${m.dpg.toFixed(1)}</span>`
      : `<span class="dpg-mobile-dpg dpg-band-nodata">—</span>`;
    const place = row.ncaa ? `<span class="fr-mobile-place">${frNcaaShort(row.ncaa)}</span>` : "";
    return (
      `<a class="dpg-mobile-row" href="${frProfileHref(row)}">` +
      `<span class="dpg-mobile-rank ${rankCls}">${row.rank}</span>` +
      `<span class="dpg-mobile-avatar-wrap"><span class="dpg-mobile-avatar-initials">${frEsc(mobileInitials(row.name))}</span>${avatar}</span>` +
      `<span class="dpg-mobile-identity">` +
      `<span class="dpg-mobile-name">${frEsc(row.name)}</span>` +
      `<span class="dpg-mobile-meta">${frEsc(meta)}${crest}</span>` +
      `</span>` +
      `<span class="fr-mobile-right">${dpg}${place}</span>` +
      `</a>`
    );
  }).join("");
}

function renderMessage(text) {
  document.querySelector("#freshman-table tbody").innerHTML =
    `<tr><td colspan="11" style="text-align:center;padding:2em;color:var(--muted);">${frEsc(text)}</td></tr>`;
  document.getElementById("freshman-mobile-list").innerHTML = `<div class="dpg-mobile-empty">${frEsc(text)}</div>`;
}

async function init() {
  const season = FRESHMAN_SEASON;
  document.getElementById("season-info").textContent = `${Number(season) - 1}–${season.slice(2)} season`;
  try {
    const res = await fetch(`/data/awards/freshman/${season}/freshman_${season}.json`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!data || !Array.isArray(data.rows)) throw new Error("missing rows");
    if (data.description) document.getElementById("description").textContent = data.description;
    if (!data.rows.length) {
      renderMessage("No data available");
      return;
    }
    document.body.classList.toggle("fr-no-ncaa", !data.rows.some(r => r.ncaa));
    renderFreshmanTable(data.rows);
    renderFreshmanMobile(data.rows);
  } catch (error) {
    console.error("Error loading Freshman of the Year data:", error);
    renderMessage(`Error loading data: ${error.message}`);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
