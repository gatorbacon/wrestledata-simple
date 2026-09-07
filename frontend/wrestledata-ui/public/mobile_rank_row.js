// ========================================
// Shared mobile "rank row" component (<768px) -- used by the homepage P4P
// table (p4p_rankings.js) and the Full Rankings page (rankings.js) so both
// render the identical compact row instead of the desktop <table>. Desktop
// (>=768px) is untouched; these rows just stay display:none there.
// ========================================

// Falls back to the team's own official abbreviation (data/teams/{slug}.json
// -- baked into p4p/2027.json at build time as team_abbr) when available;
// this map only covers the page that doesn't have that field yet
// (rankings.js's public_rankings dataset).
const MOBILE_TEAM_ABBR = {
  "penn state": "PSU",
  "oklahoma state": "OKST",
  "minnesota": "MINN",
  "iowa": "IOWA",
  "iowa state": "ISU",
  "nebraska": "NEB",
  "virginia tech": "VT",
  "ohio state": "OHST",
  "missouri": "MIZZ",
  "stanford": "STAN",
};

function mobileTeamAbbr(teamName, providedAbbr) {
  if (providedAbbr) return providedAbbr;
  if (!teamName) return "";
  const known = MOBILE_TEAM_ABBR[teamName.trim().toLowerCase()];
  if (known) return known;
  const words = teamName.trim().split(/\s+/).filter(Boolean);
  if (words.length <= 1) return (words[0] || "").slice(0, 4).toUpperCase();
  return words.map(w => w[0]).join("").toUpperCase().slice(0, 5);
}

function mobileInitials(name) {
  if (!name) return "";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const MOBILE_GRADE_ABBREV = [
  [/redshirt.*fr|r-?fr/i, "R-FR"],
  [/redshirt.*so|r-?so/i, "R-SO"],
  [/redshirt.*jr|r-?jr/i, "R-JR"],
  [/redshirt.*sr|r-?sr/i, "R-SR"],
  [/fresh|^fr\.?$/i, "FR"],
  [/soph|^so\.?$/i, "SO"],
  [/junior|^jr\.?$/i, "JR"],
  [/senior|^sr\.?$/i, "SR"],
];
function mobileAbbrevGrade(grade) {
  if (!grade) return "";
  for (const [re, short] of MOBILE_GRADE_ABBREV) {
    if (re.test(grade)) return short;
  }
  return grade;
}

// Same 4 bands/thresholds as the desktop P4P table (tpar2-band-* colors are
// generic, shared classes already defined in styles.css).
const MOBILE_TPAR_BANDS = [
  { min: 5.5, cls: "tpar2-band-elite", elite: true },
  { min: 4.5, cls: "tpar2-band-dominant" },
  { min: 3.5, cls: "tpar2-band-solid" },
  { min: -Infinity, cls: "tpar2-band-developing" },
];
function mobileTparBand(tpar) {
  if (tpar === null || tpar === undefined) return null;
  const rounded = Math.round(tpar * 10) / 10;
  return MOBILE_TPAR_BANDS.find(b => rounded >= b.min);
}

function mobileRankChipClass(rank) {
  if (rank === 1) return "medal-gold";
  if (rank === 2) return "medal-silver";
  if (rank === 3) return "medal-bronze";
  return "standard";
}

// row: { rank, wrestlerId, name, team, teamSlug, teamAbbr, weightClass,
//        grade, photoUrl, tpar, gapCls }
// gapCls (optional): "tpar2-row-gap-above" / "tpar2-row-gap-below", same
// TPAR-vs-editorial-rank disagreement accent already used on desktop rows.
function renderMobileRankRow(row) {
  const band = mobileTparBand(row.tpar);
  const rankCls = mobileRankChipClass(row.rank);

  const metaParts = [];
  const gradeAbbr = mobileAbbrevGrade(row.grade);
  if (gradeAbbr) metaParts.push(gradeAbbr);
  if (row.weightClass) metaParts.push(row.weightClass);
  const abbr = mobileTeamAbbr(row.team, row.teamAbbr);
  if (abbr) metaParts.push(abbr);
  const metaText = metaParts.join(" · ");

  const teamCrest = row.teamSlug
    ? `<img class="tpar2-mobile-team-mark" src="/assets/team_logos/${row.teamSlug}.svg" alt="" onerror="this.remove()">`
    : "";

  const initials = mobileInitials(row.name);
  const avatarImg = row.photoUrl
    ? `<img class="tpar2-mobile-avatar" src="${row.photoUrl}" alt="" loading="lazy" onerror="this.style.display='none'">`
    : "";

  const tparHtml = (row.tpar === null || row.tpar === undefined)
    ? `<span class="tpar2-mobile-tpar tpar2-band-nodata">—</span>`
    : `<span class="tpar2-mobile-tpar ${band.cls}">${row.tpar.toFixed(1)}</span>` +
      (band.elite ? `<span class="tpar2-mobile-elite-pill">ELITE</span>` : "");

  const href = row.wrestlerId ? `/wrestler.html?id=${row.wrestlerId}` : "#";
  const gapCls = row.gapCls || "";

  return (
    `<a class="tpar2-mobile-row ${gapCls}" href="${href}">` +
    `<span class="tpar2-mobile-rank ${rankCls}">${row.rank || "—"}</span>` +
    `<span class="tpar2-mobile-avatar-wrap"><span class="tpar2-mobile-avatar-initials">${initials}</span>${avatarImg}</span>` +
    `<span class="tpar2-mobile-identity">` +
    `<span class="tpar2-mobile-name">${row.name || ""}</span>` +
    `<span class="tpar2-mobile-meta">${metaText}${teamCrest}</span>` +
    `</span>` +
    `<span class="tpar2-mobile-tpar-wrap">${tparHtml}</span>` +
    `</a>`
  );
}
