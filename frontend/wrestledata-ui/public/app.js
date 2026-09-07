// ========================================
// Wrestler profile page: TPAR hero card, TPAR trajectory chart, combined
// season box-score + skill profile card, season selector, match history.
// ========================================

let _knownSeasonsCache = null;
async function getKnownSeasons() {
  if (_knownSeasonsCache) return _knownSeasonsCache;
  try {
    const res = await fetch('/data/wrestlers/available_seasons.json');
    if (res.ok) {
      _knownSeasonsCache = (await res.json()).map(String);
      return _knownSeasonsCache;
    }
  } catch (err) { /* fall through */ }
  _knownSeasonsCache = ["2026"];
  return _knownSeasonsCache;
}

function getMinMatchThreshold() {
  const now = new Date();
  const month = now.getMonth() + 1;
  const day = now.getDate();
  if (month < 12) return 3;
  if (month === 12 && day < 15) return 4;
  return 5;
}

// Cached by promise so the desktop TPAR card and the mobile TPAR strip --
// both computing this for the same season in the same tick -- share one
// fetch instead of two.
const _matValueListCache = {};
function fetchMatValueList(season) {
  if (!_matValueListCache[season]) {
    _matValueListCache[season] = fetch(`/data/mat_value/${season}/mat_value_${season}.json`)
      .then(res => (res.ok ? res.json() : null))
      .catch(() => null);
  }
  return _matValueListCache[season];
}

async function computeFilteredMVRankAndPercentile(wrestlerId, weight, season) {
  try {
    const allData = await fetchMatValueList(season);
    if (!allData) return null;
    const minMatches = getMinMatchThreshold();
    const filtered = allData.filter(e => e.weight === weight && e.matches >= minMatches);
    filtered.sort((a, b) => {
      if (b.mv_avg !== a.mv_avg) return b.mv_avg - a.mv_avg;
      if (b.matches !== a.matches) return b.matches - a.matches;
      return (a.current_rank || 9999) - (b.current_rank || 9999);
    });
    const idx = filtered.findIndex(e => String(e.wrestler_id) === String(wrestlerId));
    if (idx === -1) return null;
    const rank = idx + 1;
    const total = filtered.length;
    const percentile = Math.max(1, Math.round(100 - ((rank - 1) / total * 100)));
    return { rank, percentile, total };
  } catch (err) {
    console.error("Error computing MV percentile:", err);
    return null;
  }
}

const _rollingMbtCache = {};
async function fetchRollingMbt(season) {
  if (_rollingMbtCache[season]) return _rollingMbtCache[season];
  const res = await fetch(`/data/mat_value/${season}/rolling_mbt_${season}.json`);
  if (!res.ok) throw new Error(`Could not load rolling MBT data for ${season}`);
  const data = await res.json();
  _rollingMbtCache[season] = data;
  return data;
}

// Cached (by promise, not just resolved value) so concurrent callers in the
// same tick -- the desktop season table's enrichment pass and the mobile
// career-line aggregation both want every season's full profile on initial
// load -- coalesce into one real fetch per season instead of two.
const _seasonProfileCache = {};
function fetchSeasonProfile(season, wrestlerId) {
  const key = String(wrestlerId);
  if (!_seasonProfileCache[key]) {
    _seasonProfileCache[key] = fetch(`/data/wrestlers/${season}/by_id/${wrestlerId}.json`)
      .then(res => (res.ok ? res.json() : null))
      .catch(() => null);
  }
  return _seasonProfileCache[key];
}

// "26-0" -> {wins:26, losses:0}. Career totals are summed from each
// season's own record.overall string rather than a separate stat.
function parseRecord(str) {
  if (!str) return null;
  const m = /^(\d+)\s*-\s*(\d+)/.exec(str);
  if (!m) return null;
  return { wins: parseInt(m[1], 10), losses: parseInt(m[2], 10) };
}

function safe(value, formatter) {
  if (value === null || value === undefined || value === "") return "—";
  return formatter ? formatter(value) : value;
}

function percentFormatter(v) {
  return (v * 100).toFixed(1) + "%";
}

function fmtTpar(v) {
  if (v === null || v === undefined) return "—";
  return v.toFixed(2); // no +/- sign -- TPAR is a rating, not a delta
}

function fmtImpact(v) {
  if (v === null || v === undefined) return "—";
  return (v >= 0 ? "+" : "") + v.toFixed(1);
}

// percentile: 1 (worst) - 100 (best), i.e. "beats this % of the field."
// Above the 50th percentile that reads naturally as "Top X%" (X = how far
// from the best). Below it, "Top 98%" is technically correct but reads as
// impressive when it's actually saying he's near the bottom -- "Bottom X%"
// (X = the percentile itself, since beating only e.g. 3% of the field IS
// being in the bottom 3%) is the honest framing there.
function formatPercentileLabel(percentile) {
  if (percentile >= 50) return `Top ${100 - percentile + 1}%`;
  return `Bottom ${percentile}%`;
}

function teamNameToSlug(teamName) {
  if (!teamName) return "";
  return teamName.toLowerCase().replace(/\s+/g, "_").replace(/[^\w_]/g, "").replace(/_+/g, "_").replace(/^_+|_+$/g, "");
}

// Grade strings appear both abbreviated ("R-Sr.") and spelled out ("Junior")
// depending on which part of the pipeline wrote them -- normalize both to
// the same short form for consistent chips/table cells.
const GRADE_ABBREV = [
  [/redshirt.*fr|r-?fr/i, "RS Fr."],
  [/redshirt.*so|r-?so/i, "RS So."],
  [/redshirt.*jr|r-?jr/i, "RS Jr."],
  [/redshirt.*sr|r-?sr/i, "RS Sr."],
  [/fresh|^fr\.?$/i, "Fr."],
  [/soph|^so\.?$/i, "So."],
  [/junior|^jr\.?$/i, "Jr."],
  [/senior|^sr\.?$/i, "Sr."],
];
function abbrevGrade(grade) {
  if (!grade) return "";
  for (const [re, short] of GRADE_ABBREV) {
    if (re.test(grade)) return short;
  }
  return grade;
}

// Unified rank-tier system for the wrestler's OWN rank (header chip, TPAR
// card, season table).
function rankTierClass(rank) {
  if (rank === null || rank === undefined) return "wp2-rank--unranked";
  if (rank <= 4) return "wp2-rank--gold";
  if (rank <= 12) return "wp2-rank--navy";
  return "wp2-rank--gray";
}
function rankChip(rank, extraText) {
  const span = document.createElement("span");
  span.className = `wp2-rank-chip ${rankTierClass(rank)}`;
  span.textContent = rank ? `#${rank}${extraText ? " " + extraText : ""}` : "Unranked";
  return span;
}

// Hometown + high_school sometimes duplicate the same city name in an
// awkward join (e.g. "Brunswick, Ohio" + "Brunswick HS / Cleveland State")
// -- drop the high school clause when it's just re-stating the city.
function formatLocation(hometown, highSchool) {
  if (!hometown && !highSchool) return null;
  if (!highSchool) return hometown;
  if (!hometown) return highSchool;
  const city = hometown.split(",")[0].trim().toLowerCase();
  const hsBare = highSchool.replace(/\bHS\b\.?/i, "").replace(/\bHigh School\b/i, "").trim().toLowerCase();
  if (city && hsBare === city) return hometown;
  return `${hometown} · ${highSchool}`;
}

// Normalizes the raw result/method strings (which vary a lot in the
// scraped data -- "M. For.", "SV-1", "TB-2", etc.) into one of a small set
// of short codes. Shared by the desktop result badge and the mobile match
// row's result pill so both stay in sync.
function matchMethodCode(result, method) {
  const resultStr = (result || "").toUpperCase();
  const methodStr = (method || "").toUpperCase();
  const combined = `${resultStr} ${methodStr}`;
  let code;
  if (combined.includes("M. FOR.") || combined.includes("MFF") || (combined.includes("MEDICAL") && combined.includes("FORFEIT"))) code = "MFF";
  else if (combined.includes("DQ") || combined.includes("DISQUAL")) code = "DQ";
  else if (combined.includes("INJ") || combined.includes("INJURY")) code = "INJ";
  else if (combined.includes("FORFEIT") || (combined.includes(" FF") && !combined.includes("MFF"))) code = "FF";
  else if (combined.includes("TF") || combined.includes("TECH")) code = "TF";
  else if ((combined.includes("FALL") || combined.includes(" PIN")) && !combined.includes("TF") && !combined.includes("TECH")) code = "FALL";
  else if (combined.includes("MD") || combined.includes("MAJOR")) code = "MD";
  else if (combined.includes("DEC") || combined.includes("SV-") || combined.includes("TB-")) code = "DEC";
  else if (methodStr && methodStr !== "—" && methodStr !== "DEF.") code = methodStr;
  else code = "O";

  const methodName = code === "DEC" ? "Decision" :
                    code === "MD" ? "Major Decision" :
                    code === "TF" ? "Technical Fall" :
                    code === "FALL" || code === "PIN" ? "Fall" :
                    code === "INJ" ? "Injury Default" :
                    code === "DQ" ? "Disqualification" :
                    code === "MFF" ? "Medical Forfeit" :
                    code === "FF" ? "Forfeit" :
                    code === "O" ? "Other" :
                    code;
  return { code, methodName };
}

function createResultBadge(result, method) {
  const badge = document.createElement("span");
  badge.className = "result-badge";
  const isWin = result === "W";
  badge.classList.add(isWin ? "result-win" : "result-loss");

  const { code, methodName } = matchMethodCode(result, method);
  badge.textContent = code;
  badge.setAttribute("title", `${isWin ? "Win" : "Loss"} by ${methodName}`);
  return badge;
}

// ===============================
// Fetch + top-level orchestration
// ===============================

async function loadWrestlerProfile(id) {
  const seasons = await getKnownSeasons();
  for (const season of seasons) {
    try {
      const res = await fetch(`/data/wrestlers/${season}/by_id/${id}.json`);
      if (!res.ok) continue;
      const data = await res.json();
      renderProfile(data);
      return;
    } catch (err) { /* try next season */ }
  }
  console.error("Wrestler not found in any known season", id);
  document.getElementById("wrestler-name").textContent = "Not Found";
  document.getElementById("wrestler-resume").textContent = "Could not load wrestler JSON";
}

// Tracks whichever season is currently on screen (desktop tpar-card,
// mobile strip/chip-subtitle, trajectory, matches) -- the mobile "Season
// stats" sheet reads from this so it always reflects the season actually
// showing, not just the season the page loaded with.
let _currentSeasonProfile = null;

function renderProfile(data) {
  renderHeader(data);
  renderMobileIdentity(data);
  renderMobileSeasonChips(data);
  _currentSeasonProfile = data;
  renderSeasonSelector(data);
  renderSeasonBody(data);
}

// ===============================
// Header: chips + one résumé line, renders once (never on season click)
// ===============================

function renderHeader(data) {
  document.getElementById("wrestler-name").textContent = safe(data.name);

  const chipsEl = document.getElementById("wrestler-chips");
  chipsEl.innerHTML = "";
  chipsEl.appendChild(rankChip(data.current_rank, data.weight_class ? `· ${data.weight_class} lbs` : ""));
  if (data.team) {
    const teamChip = document.createElement("a");
    teamChip.className = "wp2-chip wp2-chip--team";
    teamChip.href = `/team.html?team=${data.team_slug || teamNameToSlug(data.team)}`;
    const slug = data.team_slug || teamNameToSlug(data.team);
    teamChip.innerHTML =
      `<img class="wp2-chip-crest" src="/assets/team_logos/${slug}.svg" alt="" ` +
      `onerror="if(!this.dataset.fb){this.dataset.fb=1;this.src='/assets/team_logos/${slug}.png';}else{this.remove();}">` +
      `<span>${data.team}</span>`;
    chipsEl.appendChild(teamChip);
  }
  const gradeAbbrev = abbrevGrade(data.grade);
  if (gradeAbbrev) {
    const gradeChip = document.createElement("span");
    gradeChip.className = "wp2-chip";
    gradeChip.textContent = gradeAbbrev;
    chipsEl.appendChild(gradeChip);
  }
  const location = formatLocation(data.hometown, data.high_school);
  if (location) {
    const locChip = document.createElement("span");
    locChip.className = "wp2-chip wp2-chip--location";
    locChip.textContent = location;
    chipsEl.appendChild(locChip);
  }

  const photoEl = document.getElementById("wrestler-photo");
  if (data.photo_url) {
    photoEl.src = data.photo_url;
    photoEl.alt = `${safe(data.name)} headshot`;
    photoEl.hidden = false;
    photoEl.onerror = () => { photoEl.hidden = true; };
  } else {
    photoEl.hidden = true;
  }

  const resumeEl = document.getElementById("wrestler-resume");
  const parts = [];
  if (data.year) parts.push(`${data.year}:`);
  if (data.record && data.record.overall) parts.push(data.record.overall + (data.record.overall.includes(",") ? "" : ","));
  if (data.current_rank && data.weight_class) parts.push(`#${data.current_rank} at ${data.weight_class}`);
  resumeEl.textContent = parts.join(" ");
  resumeEl.hidden = parts.length === 0;
}

// ===============================
// Mobile (<768px) identity block: photo, name, one meta line (rank is
// stated here ONLY -- never repeated in the season chip subtitle), career
// totals line. Renders once, like the desktop header -- never on season
// switch (career totals span every season, not just the selected one).
// ===============================

function renderMobileIdentity(data) {
  const photoEl = document.getElementById("wp2m-photo");
  if (photoEl) {
    if (data.photo_url) {
      photoEl.src = data.photo_url;
      photoEl.alt = `${safe(data.name)} headshot`;
      photoEl.hidden = false;
      photoEl.onerror = () => { photoEl.hidden = true; };
    } else {
      photoEl.hidden = true;
    }
  }

  const nameEl = document.getElementById("wp2m-name");
  if (nameEl) nameEl.textContent = safe(data.name);

  const metaEl = document.getElementById("wp2m-meta");
  if (metaEl) {
    const metaParts = [];
    if (data.current_rank) metaParts.push(`#${data.current_rank}`);
    if (data.weight_class) metaParts.push(String(data.weight_class));
    const gradeAbbrev = typeof mobileAbbrevGrade === "function" ? mobileAbbrevGrade(data.grade) : "";
    if (gradeAbbrev) metaParts.push(gradeAbbrev);
    metaEl.innerHTML = "";
    const textSpan = document.createElement("span");
    textSpan.textContent = metaParts.join(" · ");
    metaEl.appendChild(textSpan);

    if (data.team) {
      const slug = data.team_slug || teamNameToSlug(data.team);
      const abbr = typeof mobileTeamAbbr === "function" ? mobileTeamAbbr(data.team) : data.team;
      const teamLink = document.createElement("a");
      teamLink.className = "wp2m-meta-team";
      teamLink.href = `/team.html?team=${slug}`;
      teamLink.innerHTML =
        ` · ${abbr} ` +
        `<img class="wp2m-meta-crest" src="/assets/team_logos/${slug}.svg" alt="" ` +
        `onerror="if(!this.dataset.fb){this.dataset.fb=1;this.src='/assets/team_logos/${slug}.png';}else{this.remove();}">`;
      metaEl.appendChild(teamLink);
    }
  }

  renderMobileCareerLine(data);
}

async function renderMobileCareerLine(data) {
  const el = document.getElementById("wp2m-career-line");
  if (!el) return;

  const summary = (data.season_summary && data.season_summary.length)
    ? data.season_summary
    : [{ season: data.year, wrestler_id: data.wrestler_id }];

  const profiles = await Promise.all(summary.map(s => fetchSeasonProfile(s.season, s.wrestler_id)));

  let wins = 0, losses = 0, bonusWins = 0, pins = 0;
  profiles.forEach(p => {
    if (!p) return;
    const rec = parseRecord((p.record || {}).overall);
    if (rec) { wins += rec.wins; losses += rec.losses; }
    const m = p.metrics || {};
    pins += m.pins || 0;
    bonusWins += (m.pins || 0) + (m.techs || 0) + (m.majors || 0);
  });

  if (wins === 0 && losses === 0) { el.textContent = ""; return; }

  const parts = [`${wins}–${losses} career`];
  if (wins > 0) {
    parts.push(`${Math.round((pins / wins) * 100)}% pin`);
    parts.push(`${Math.round((bonusWins / wins) * 100)}% bonus`);
  }
  el.textContent = parts.join(" · ");
}

// ===============================
// Mobile season chips: replaces the desktop season <table> with a single
// scrollable chip row + a one-line subtitle (record first, since rank
// already lives in the identity meta line above -- see anti-duplication
// note in the spec). Built directly from season_summary (no fetch needed
// for the chips/subtitle themselves); each click lazily loads that
// season's full profile via the shared cache.
// ===============================

function renderMobileSeasonChips(data) {
  const row = document.getElementById("wp2m-chip-row");
  if (!row) return;

  const summary = (data.season_summary && data.season_summary.length)
    ? data.season_summary
    : [{ season: data.year, wrestler_id: data.wrestler_id, team: data.team, grade: data.grade, record: (data.record || {}).overall }];

  row.innerHTML = "";
  summary.forEach(s => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "wp2m-chip";
    chip.dataset.wrestlerId = String(s.wrestler_id);
    chip.textContent = safe(s.season);
    if (String(s.wrestler_id) === String(data.wrestler_id)) chip.classList.add("active");
    chip.addEventListener("click", () => {
      if (chip.classList.contains("active")) return;
      fetchSeasonProfile(s.season, s.wrestler_id).then(seasonData => {
        if (!seasonData) return;
        _currentSeasonProfile = seasonData;
        renderSeasonBody(seasonData);
        renderMobileChipSubtitle(seasonData);
        selectMobileSeasonChip(String(s.wrestler_id));
        selectDesktopSeasonRow(String(s.wrestler_id));
      });
    });
    row.appendChild(chip);
  });

  renderMobileChipSubtitle(data);
}

function selectMobileSeasonChip(wrestlerId) {
  document.querySelectorAll("#wp2m-chip-row .wp2m-chip").forEach(c => {
    c.classList.toggle("active", c.dataset.wrestlerId === wrestlerId);
  });
}

function selectDesktopSeasonRow(wrestlerId) {
  document.querySelectorAll("#season-selector-body .season-row").forEach(r => {
    r.classList.toggle("season-row--active", r.dataset.wrestlerId === wrestlerId);
  });
}

// Record first (and visually darker) so it reads as "this is the season
// W-L," not a repeat of the rank already stated in the identity meta line.
function renderMobileChipSubtitle(profile) {
  const el = document.getElementById("wp2m-chip-subtitle");
  if (!el) return;
  const record = safe((profile.record || {}).overall);
  const team = safe(profile.team);
  const grade = abbrevGrade(profile.grade) || "";
  el.innerHTML = `<span class="wp2m-chip-record">${record}</span> · ${team}${grade ? " · " + grade : ""}`;

  if (_sheetOpen) renderMobileSeasonSheet(profile);
}

// ===============================
// Mobile "Season stats" bottom sheet -- the desktop box score, presented as
// a sheet instead of an inline card. Bound to whichever season is
// currently selected; reopens/refreshes live if the chip changes while open.
// ===============================

let _sheetOpen = false;

function renderMobileSeasonSheet(profile) {
  const title = document.getElementById("wp2m-sheet-title");
  const body = document.getElementById("wp2m-sheet-body");
  if (!title || !body) return;

  title.textContent = `${safe(profile.year)} season`;

  const record = profile.record || {};
  const m = profile.metrics || {};
  const mv = m.mat_value || {};
  const location = formatLocation(profile.hometown, profile.high_school);

  const rows = [
    ["Record", safe(record.overall)],
    ["Rank / weight", profile.current_rank && profile.weight_class ? `#${profile.current_rank} at ${profile.weight_class}` : safe(profile.current_rank)],
    ["Team", safe(profile.team)],
    ["Class", abbrevGrade(profile.grade) || "—"],
    ["TPAR", fmtTpar(mv.mv_avg)],
    ["Bonus %", m.bonus_rate !== null && m.bonus_rate !== undefined ? percentFormatter(m.bonus_rate) : "—"],
    ["Pin %", m.pin_rate !== null && m.pin_rate !== undefined ? percentFormatter(m.pin_rate) : "—"],
    ["Pins", safe(m.pins)],
    ["Tech falls", safe(m.techs)],
    ["Majors", safe(m.majors)],
    ["vs Top 10", safe(record.vs_top10)],
    ["Hometown / HS", location || "—"],
  ];

  body.innerHTML = rows.map(([label, value]) =>
    `<div class="wp2m-sheet-row"><span class="wp2m-sheet-label">${label}</span><span class="wp2m-sheet-value">${value}</span></div>`
  ).join("");
}

function openMobileSeasonSheet() {
  const overlay = document.getElementById("wp2m-sheet-overlay");
  const sheet = document.getElementById("wp2m-sheet");
  if (!overlay || !sheet || !_currentSeasonProfile) return;
  renderMobileSeasonSheet(_currentSeasonProfile);
  overlay.hidden = false;
  sheet.hidden = false;
  sheet.setAttribute("aria-hidden", "false");
  _sheetOpen = true;
}

function closeMobileSeasonSheet() {
  const overlay = document.getElementById("wp2m-sheet-overlay");
  const sheet = document.getElementById("wp2m-sheet");
  if (!overlay || !sheet) return;
  overlay.hidden = true;
  sheet.hidden = true;
  sheet.setAttribute("aria-hidden", "true");
  _sheetOpen = false;
}

function initMobileSeasonSheetControls() {
  const openBtn = document.getElementById("wp2m-season-stats-btn");
  const closeBtn = document.getElementById("wp2m-sheet-close");
  const overlay = document.getElementById("wp2m-sheet-overlay");
  if (openBtn) openBtn.addEventListener("click", openMobileSeasonSheet);
  if (closeBtn) closeBtn.addEventListener("click", closeMobileSeasonSheet);
  if (overlay) overlay.addEventListener("click", closeMobileSeasonSheet);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && _sheetOpen) closeMobileSeasonSheet();
  });
}
document.addEventListener("DOMContentLoaded", initMobileSeasonSheetControls);

// ===============================
// Season selector: Season / Team / Class / Rank / Record / TPAR / Bonus %
// ===============================

async function renderSeasonSelector(data) {
  const section = document.getElementById("season-selector-section");
  const tbody = document.getElementById("season-selector-body");
  const summary = data.season_summary || [];
  if (summary.length === 0) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  tbody.innerHTML = "";

  // TPAR/Bonus% aren't in season_summary -- pull them from each season's own
  // already-published profile via the shared fetchSeasonProfile cache (the
  // mobile career-line aggregation wants the same per-season profiles, so
  // whichever of the two runs first fetches for both).
  const enriched = await Promise.all(summary.map(async s => {
    const seasonData = await fetchSeasonProfile(s.season, s.wrestler_id);
    if (!seasonData) return { ...s, tpar: null, bonus_rate: null };
    const mv = (seasonData.metrics || {}).mat_value || {};
    return { ...s, tpar: mv.mv_avg, bonus_rate: (seasonData.metrics || {}).bonus_rate };
  }));

  enriched.forEach(s => {
    const tr = document.createElement("tr");
    tr.className = "season-row";
    tr.dataset.wrestlerId = String(s.wrestler_id);
    if (String(s.wrestler_id) === String(data.wrestler_id)) tr.classList.add("season-row--active");

    const cells = [
      safe(s.season),
      null, // team, built below
      abbrevGrade(s.grade) || "—",
      null, // rank chip, built below
      safe(s.record),
      fmtTpar(s.tpar),
      s.bonus_rate !== null && s.bonus_rate !== undefined ? percentFormatter(s.bonus_rate) : "—",
    ];

    const seasonTd = document.createElement("td");
    seasonTd.textContent = cells[0];
    tr.appendChild(seasonTd);

    const teamTd = document.createElement("td");
    if (s.team) {
      const teamLink = document.createElement("a");
      teamLink.href = `/team.html?team=${s.team_slug || teamNameToSlug(s.team)}`;
      teamLink.textContent = s.team;
      teamLink.addEventListener("click", ev => ev.stopPropagation());
      teamTd.appendChild(teamLink);
    } else {
      teamTd.textContent = "—";
    }
    tr.appendChild(teamTd);

    const gradeTd = document.createElement("td");
    gradeTd.textContent = cells[2];
    tr.appendChild(gradeTd);

    const rankTd = document.createElement("td");
    rankTd.className = "num";
    rankTd.appendChild(rankChip(s.current_rank));
    tr.appendChild(rankTd);

    const recordTd = document.createElement("td");
    recordTd.className = "num";
    recordTd.textContent = cells[4];
    tr.appendChild(recordTd);

    const tparTd = document.createElement("td");
    tparTd.className = "num";
    tparTd.textContent = cells[5];
    tr.appendChild(tparTd);

    const bonusTd = document.createElement("td");
    bonusTd.className = "num";
    bonusTd.textContent = cells[6];
    tr.appendChild(bonusTd);

    tr.addEventListener("click", () => {
      if (tr.classList.contains("season-row--active")) return;
      fetchSeasonProfile(s.season, s.wrestler_id).then(seasonData => {
        if (!seasonData) { console.error("Could not load season data"); return; }
        _currentSeasonProfile = seasonData;
        renderSeasonBody(seasonData);
        renderMobileChipSubtitle(seasonData);
        selectMobileSeasonChip(String(s.wrestler_id));
        tbody.querySelectorAll(".season-row--active").forEach(row => row.classList.remove("season-row--active"));
        tr.classList.add("season-row--active");
      });
    });

    tbody.appendChild(tr);
  });
}

// ===============================
// Season body: TPAR card, box score, skill, trajectory, match history
// ===============================

function renderSeasonBody(data) {
  const season = safe(data.year);
  const mv = (data.metrics || {}).mat_value || {};
  renderTparCard(data, mv, season);
  renderMobileTparStrip(data, mv, season);
  renderBoxScoreCard(data);
  renderSkillCard(data);
  renderRollingMbtTimeline(data, mv.mv_avg);
  renderMatchHistory(data.match_list || []);
  renderMobileMatchList(data.match_list || [], season);
}

// ===============================
// Mobile TPAR strip: one row (number + ELITE pill + compressed percentile
// bar), season-scoped -- follows whichever chip is selected. Same ELITE
// threshold (>=5.5) and percentile source as the desktop card and the
// homepage rankings row.
// ===============================

function renderMobileTparStrip(data, mv, season) {
  const strip = document.getElementById("wp2m-tpar-strip");
  if (!strip) return;

  if (mv.mv_avg === null || mv.mv_avg === undefined) {
    strip.innerHTML = `<p class="section-empty-state">TPAR not available for this season.</p>`;
    return;
  }

  const weightClass = data.weight_class;
  const isElite = mv.mv_avg >= 5.5;
  const leaderboardUrl = weightClass ? `/leaderboards/tpar.html?weight=${weightClass}` : "/leaderboards/tpar.html";

  strip.innerHTML =
    `<div class="wp2m-tpar-row">` +
    `<span class="wp2m-tpar-label">TPAR<span class="tooltip-icon" data-tooltip="mv">ⓘ</span></span>` +
    `<span class="wp2m-tpar-percentile-label" id="wp2m-tpar-percentile-label"></span>` +
    `</div>` +
    `<div class="wp2m-tpar-row wp2m-tpar-row--main">` +
    `<span class="wp2m-tpar-number-group">` +
    `<span class="wp2m-tpar-number">${fmtTpar(mv.mv_avg)}</span>` +
    (isElite ? `<span class="tpar2-elite-badge">Elite</span>` : "") +
    `</span>` +
    `<a class="wp2m-tpar-scale-link" href="${leaderboardUrl}">` +
    `<span class="wp2m-tpar-scale" id="wp2m-tpar-scale"><span class="wp2m-tpar-marker" id="wp2m-tpar-marker"></span></span>` +
    `</a>` +
    `</div>`;

  const setPercentile = (percentile) => {
    const label = document.getElementById("wp2m-tpar-percentile-label");
    const marker = document.getElementById("wp2m-tpar-marker");
    if (label) label.textContent = formatPercentileLabel(percentile);
    if (marker) marker.style.left = `${percentile}%`;
  };

  if (weightClass && data.wrestler_id) {
    computeFilteredMVRankAndPercentile(data.wrestler_id, weightClass, season).then(result => {
      if (result) {
        setPercentile(result.percentile);
      } else if (mv.rank_weight !== null && mv.rank_weight !== undefined) {
        let est = 50;
        if (mv.rank_weight <= 3) est = 95;
        else if (mv.rank_weight <= 10) est = 85;
        else if (mv.rank_weight <= 20) est = 70;
        else if (mv.rank_weight <= 33) est = 50;
        else est = 30;
        setPercentile(est);
      }
    }).catch(() => {});
  } else if (mv.rank_weight !== null && mv.rank_weight !== undefined) {
    setPercentile(50);
  }
}

function renderTparCard(data, mv, season) {
  const card = document.getElementById("tpar-card");
  card.innerHTML = "";
  const weightClass = data.weight_class;

  const headerRow = document.createElement("div");
  headerRow.className = "section-header";
  const title = document.createElement("h2");
  title.textContent = "TPAR";
  const tooltipIcon = document.createElement("span");
  tooltipIcon.className = "tooltip-icon";
  tooltipIcon.setAttribute("data-tooltip", "mv");
  tooltipIcon.textContent = "ⓘ";
  title.appendChild(tooltipIcon);
  headerRow.appendChild(title);
  card.appendChild(headerRow);
  card.appendChild(Object.assign(document.createElement("div"), { className: "section-divider" }));

  if (mv.mv_avg === null || mv.mv_avg === undefined) {
    const empty = document.createElement("p");
    empty.className = "section-empty-state";
    empty.textContent = "TPAR not available for this season.";
    card.appendChild(empty);
    return;
  }

  const heroNumber = document.createElement("div");
  heroNumber.className = "wp2-tpar-hero";
  heroNumber.textContent = fmtTpar(mv.mv_avg);
  card.appendChild(heroNumber);

  const rankLabel = document.createElement("div");
  rankLabel.className = "wp2-tpar-rank-label";
  rankLabel.textContent = "Loading rank…";
  card.appendChild(rankLabel);

  // Fully custom block (not the shared, flex-row .mv-percentile-bar-
  // container) so the percentile text can sit as its own centered line
  // above a bar that spans the full card width.
  const percentileBarContainer = document.createElement("div");
  percentileBarContainer.className = "wp2-percentile-block";
  card.appendChild(percentileBarContainer);

  const leaderboardUrl = weightClass ? `/leaderboards/tpar.html?weight=${weightClass}` : "/leaderboards/tpar.html";

  const renderRankAndPercentile = (rank, percentile) => {
    rankLabel.innerHTML = "";
    const link = document.createElement("a");
    link.href = leaderboardUrl;
    link.className = "wp2-tpar-rank-link";
    link.textContent = weightClass ? `#${rank} at ${weightClass}` : `#${rank}`;
    rankLabel.appendChild(link);

    percentileBarContainer.innerHTML = "";

    const percentileText = document.createElement("div");
    percentileText.className = "mv-percentile-text wp2-percentile-text-centered";
    percentileText.textContent = `${formatPercentileLabel(percentile)} nationally`;
    percentileBarContainer.appendChild(percentileText);

    // Fixed 0-100 gradient scale (not a "fill width" bar) with a marker
    // pinned at the wrestler's own percentile -- reads as "where does he
    // sit on the whole scale" rather than a partially-filled progress bar.
    const scale = document.createElement("div");
    scale.className = "wp2-percentile-scale";
    const marker = document.createElement("div");
    marker.className = "wp2-percentile-marker";
    marker.style.left = `${percentile}%`;
    scale.appendChild(marker);
    percentileBarContainer.appendChild(scale);

    const ticks = document.createElement("div");
    ticks.className = "wp2-percentile-ticks";
    ticks.innerHTML = `<span>0th</span><span>50th</span><span>100th</span>`;
    percentileBarContainer.appendChild(ticks);
  };

  if (weightClass && data.wrestler_id) {
    computeFilteredMVRankAndPercentile(data.wrestler_id, weightClass, season).then(result => {
      if (result) {
        renderRankAndPercentile(result.rank, result.percentile);
      } else if (mv.rank_weight !== null && mv.rank_weight !== undefined) {
        let est = 50;
        if (mv.rank_weight <= 3) est = 95;
        else if (mv.rank_weight <= 10) est = 85;
        else if (mv.rank_weight <= 20) est = 70;
        else if (mv.rank_weight <= 33) est = 50;
        else est = 30;
        renderRankAndPercentile(mv.rank_weight, est);
      } else {
        rankLabel.textContent = "";
      }
    }).catch(() => { rankLabel.textContent = ""; });
  } else if (mv.rank_weight !== null && mv.rank_weight !== undefined) {
    renderRankAndPercentile(mv.rank_weight, 50);
  } else {
    rankLabel.textContent = "";
  }

  const definition = document.createElement("p");
  definition.className = "wp2-tpar-definition";
  definition.textContent = "How completely he wins, not just whether he wins.";
  card.appendChild(definition);
}

function renderBoxScoreCard(data) {
  const card = document.getElementById("boxscore-card");
  card.innerHTML = "";
  const headerRow = document.createElement("div");
  headerRow.className = "wp2-subhead";
  headerRow.textContent = "Season box score";
  card.appendChild(headerRow);

  const record = data.record || {};
  const m = data.metrics || {};
  const grid = document.createElement("div");
  grid.className = "wp2-boxscore-grid";

  const addStat = (label, value) => {
    const cell = document.createElement("div");
    cell.className = "wp2-boxscore-cell";
    cell.innerHTML = `<span class="wp2-boxscore-label">${label}</span><span class="wp2-boxscore-value">${value}</span>`;
    grid.appendChild(cell);
  };

  addStat("Record", safe(record.overall));
  addStat("Bonus %", m.bonus_rate !== null && m.bonus_rate !== undefined ? percentFormatter(m.bonus_rate) : "—");
  addStat("TF", safe(m.techs));
  addStat("MD", safe(m.majors));
  addStat("Pins", safe(m.pins));
  addStat("vs Top 10", safe(record.vs_top10));

  card.appendChild(grid);
}

function createSkillRow(label, tooltipKey, fullName, value, weightClass) {
  // Single dense row: label+fullname, bar, value all inline.
  const row = document.createElement("div");
  row.className = "wp2-skill-row-dense";

  const labelEl = document.createElement("div");
  labelEl.className = "wp2-skill-row-label";
  labelEl.innerHTML = `${label} <span class="wp2-skill-fullname">${fullName}</span>`;
  row.appendChild(labelEl);

  const barWrapper = document.createElement("div");
  barWrapper.className = "skill-bar-wrapper";
  const baseline = document.createElement("div");
  baseline.className = "skill-baseline";
  barWrapper.appendChild(baseline);

  const SKILL_MAX = 160;
  const barPct = Math.min((value / SKILL_MAX) * 100, 100);
  const bar = document.createElement("div");
  bar.className = "skill-bar";
  bar.style.width = `${barPct}%`;
  bar.classList.add(value < 95 ? "low" : value <= 105 ? "neutral" : "high");
  barWrapper.appendChild(bar);
  row.appendChild(barWrapper);

  const valueEl = document.createElement("div");
  valueEl.className = "skill-value";
  valueEl.classList.add(value < 95 ? "skill-value-low" : value > 105 ? "skill-value-high" : "skill-value-neutral");
  valueEl.textContent = Math.round(value);
  row.appendChild(valueEl);

  return row;
}

function renderSkillCard(data) {
  const card = document.getElementById("skill-card");
  card.innerHTML = "";
  const headerRow = document.createElement("div");
  headerRow.className = "wp2-subhead";
  headerRow.textContent = "Skill Profile";
  card.appendChild(headerRow);

  const m = data.metrics || {};
  const rowsContainer = document.createElement("div");
  rowsContainer.className = "skill-rows-container";
  let hasAny = false;

  if (m.si_plus != null) { rowsContainer.appendChild(createSkillRow("SI+", "si", "Scoring", m.si_plus)); hasAny = true; }
  if (m.df_plus != null) { rowsContainer.appendChild(createSkillRow("DF+", "df", "Defense", m.df_plus)); hasAny = true; }
  if (m.apr_plus != null) { rowsContainer.appendChild(createSkillRow("APR+", "apr", "Pin Rate", m.apr_plus)); hasAny = true; }

  if (!hasAny) {
    const empty = document.createElement("p");
    empty.className = "section-empty-state";
    empty.textContent = "Skill profile not available for this season.";
    card.appendChild(empty);
    return;
  }
  card.appendChild(rowsContainer);

  const caption = document.createElement("p");
  caption.className = "wp2-skill-caption";
  caption.textContent = `100 = D1 ${safe(data.weight_class)}-lb average`;
  card.appendChild(caption);
}

// ===============================
// Trajectory chart: bars colored by win/loss x impact-sign agreement
// ===============================

function barColorClass(result, impact) {
  const isWin = result === "W";
  const isPositive = impact >= 0;
  if (isWin && isPositive) return "wp2-bar-green";
  if (!isWin && !isPositive) return "wp2-bar-red";
  return "wp2-bar-grey"; // disagreement: ugly win, or hard-fought loss
}

function renderRollingMbtTimeline(data, seasonMV) {
  const container = document.getElementById("match-impact-chart-container");
  container.innerHTML = '<span style="opacity:0.4;font-size:0.85em;padding:8px;display:block">Loading…</span>';

  const avgLabel = document.getElementById("match-impact-avg-label");
  const avgSuffix = seasonMV !== null && seasonMV !== undefined ? ` (${fmtTpar(seasonMV)})` : "";
  avgLabel.innerHTML =
    `<span class="wp2m-label-full">Season avg${avgSuffix}</span>` +
    `<span class="wp2m-label-short">Avg${avgSuffix}</span>`;

  const season = String(data.year || "2026");
  const wrestlerId = String(data.wrestler_id);

  const matches = (data.match_list || [])
    .map(m => {
      const impact = m.mv_impact_v1 !== undefined ? m.mv_impact_v1 : m.mv_impact;
      return { date: m.date || "", mvImpact: impact, opponent: m.opponent_name, opponentRank: m.opponent_rank, result: m.result, method: m.method };
    })
    .filter(m => m.mvImpact !== null && m.mvImpact !== undefined)
    .sort((a, b) => (a.date || "").localeCompare(b.date || ""));

  if (matches.length === 0) {
    container.innerHTML = "";
    const empty = document.createElement("p");
    empty.className = "section-empty-state";
    empty.textContent = "TPAR trajectory not available for this season.";
    container.appendChild(empty);
    return;
  }

  fetchRollingMbt(season).then(allTimelines => {
    container.innerHTML = "";
    const toISO = s => { if (!s) return s; if (s.includes('-')) return s; const [m, d, y] = s.split('/'); return `${y}-${m.padStart(2,'0')}-${d.padStart(2,'0')}`; };
    const mbtByDate = {};
    (allTimelines[wrestlerId] || []).forEach(pt => { mbtByDate[toISO(pt.date)] = pt.tpar; });

    let lastMbt = null;
    const matchMbt = matches.map(m => {
      const key = toISO(m.date);
      if (mbtByDate[key] !== undefined) lastMbt = mbtByDate[key];
      return lastMbt;
    });

    // Mobile gets its own real chart height/padding here (not a CSS-forced
    // height on a 250-tall SVG) -- forcing the CSS height while the JS
    // still computed a 250-tall coordinate system clipped negative bars,
    // since zeroY sat near the bottom of the shrunk viewport with no room
    // left below it for downward (loss) bars to render into.
    const isMobileChart = window.matchMedia("(max-width: 767px)").matches;
    const chartHeight = isMobileChart ? 130 : 250;
    const containerWidth = container.clientWidth || 600;
    const padding = isMobileChart
      ? { top: 14, right: 12, bottom: 14, left: 12 }
      : { top: 30, right: 20, bottom: 30, left: 20 };
    const plotWidth = containerWidth - padding.left - padding.right;
    const plotHeight = chartHeight - padding.top - padding.bottom;

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", containerWidth);
    svg.setAttribute("height", chartHeight);
    svg.setAttribute("class", "match-impact-chart");
    svg.style.display = "block";

    const maxAbsImpact = Math.max(...matches.map(m => Math.abs(m.mvImpact || 0)), 1);
    const chartMaxValue = Math.max(6, maxAbsImpact);
    const zeroY = padding.top + plotHeight / 2;
    const yOf = v => zeroY - (Math.max(-chartMaxValue, Math.min(chartMaxValue, v)) / chartMaxValue) * (plotHeight / 2);
    const xOf = i => matches.length === 1 ? padding.left + plotWidth / 2 : padding.left + (i / (matches.length - 1)) * plotWidth;

    [6, 4, 2, 0, -2, -4, -6].forEach(gv => {
      const gy = yOf(gv);
      if (gy < padding.top - 1 || gy > padding.top + plotHeight + 1) return;
      const gl = document.createElementNS("http://www.w3.org/2000/svg", "line");
      gl.setAttribute("x1", padding.left); gl.setAttribute("x2", padding.left + plotWidth);
      gl.setAttribute("y1", gy); gl.setAttribute("y2", gy);
      gl.setAttribute("stroke", gv === 0 ? "rgba(33,28,22,0.15)" : "rgba(33,28,22,0.08)");
      gl.setAttribute("stroke-width", "1");
      svg.appendChild(gl);
    });

    if (seasonMV !== null && seasonMV !== undefined) {
      const flatY = yOf(seasonMV);
      const flat = document.createElementNS("http://www.w3.org/2000/svg", "line");
      flat.setAttribute("x1", padding.left); flat.setAttribute("x2", padding.left + plotWidth);
      flat.setAttribute("y1", flatY); flat.setAttribute("y2", flatY);
      flat.setAttribute("stroke", "rgba(200,150,40,0.85)");
      flat.setAttribute("stroke-width", "1.5");
      flat.setAttribute("stroke-dasharray", "5 4");
      svg.appendChild(flat);
    }

    const barWidth = Math.max(3, plotWidth / matches.length - 2);
    const bars = matches.map((m, idx) => {
      const impact = m.mvImpact;
      const x = xOf(idx);
      const barHeight = Math.abs(impact) / chartMaxValue * (plotHeight / 2);
      const isPositive = impact >= 0;
      const colorCls = barColorClass(m.result, impact);

      const bar = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      bar.setAttribute("x", x - barWidth / 2);
      bar.setAttribute("y", isPositive ? zeroY - barHeight : zeroY);
      bar.setAttribute("width", barWidth);
      bar.setAttribute("height", barHeight);
      bar.setAttribute("class", `match-impact-bar ${colorCls}`);
      bar.setAttribute("opacity", "0.85");
      svg.appendChild(bar);
      return { element: bar, x, barHeight, isPositive, match: m, mbt: matchMbt[idx] };
    });

    const rollingMbt = matches.map((_, i) => {
      const window = matches.slice(Math.max(0, i - 4), i + 1);
      return window.reduce((s, m) => s + (m.mvImpact || 0), 0) / window.length;
    });

    if (rollingMbt.length > 1) {
      let pathData = "";
      rollingMbt.forEach((v, i) => {
        const x = xOf(i);
        const y = yOf(v);
        pathData += pathData === "" ? `M ${x} ${y}` : ` L ${x} ${y}`;
      });
      const trajPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
      trajPath.setAttribute("d", pathData);
      trajPath.setAttribute("stroke", "rgba(43,108,176,0.85)");
      trajPath.setAttribute("stroke-width", "2");
      trajPath.setAttribute("fill", "none");
      svg.appendChild(trajPath);
    }

    const lineDot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    lineDot.setAttribute("r", "3");
    lineDot.setAttribute("fill", "rgba(43,108,176,1)");
    lineDot.setAttribute("opacity", "0");
    svg.appendChild(lineDot);
    container.appendChild(svg);

    let activeIndex = -1;
    svg.addEventListener("mousemove", (e) => {
      const svgRect = svg.getBoundingClientRect();
      const relX = (e.clientX - svgRect.left) - padding.left;
      const normX = Math.max(0, Math.min(1, relX / plotWidth));
      let index = Math.round(normX * (matches.length - 1));
      index = Math.max(0, Math.min(matches.length - 1, index));
      if (index !== activeIndex) {
        activeIndex = index;
        bars.forEach((b, i) => b.element.setAttribute("opacity", i === activeIndex ? "1.0" : "0.85"));
      }
      const b = bars[activeIndex];
      const m = b.match;
      const rollingVal = rollingMbt[activeIndex];
      const tooltipLines = [
        m.date, m.opponent || "",
        `TPAR Impact: ${fmtImpact(m.mvImpact)}`,
        `5-match avg TPAR: ${rollingVal !== null ? fmtImpact(rollingVal) : "—"}`,
        `Season TPAR: ${seasonMV !== null && seasonMV !== undefined ? fmtTpar(seasonMV) : "—"}`,
      ];
      const tooltipY = b.isPositive ? zeroY - b.barHeight - 12 : zeroY + b.barHeight + 12;
      showChartTooltip(e, tooltipLines.join('\n'), svg, b.x, tooltipY, m.mvImpact);
      lineDot.setAttribute("cx", b.x);
      lineDot.setAttribute("cy", yOf(rollingMbt[activeIndex]));
      lineDot.setAttribute("opacity", "1");
    });
    svg.addEventListener("mouseleave", () => {
      bars.forEach(b => b.element.setAttribute("opacity", "0.85"));
      lineDot.setAttribute("opacity", "0");
      activeIndex = -1;
      hideChartTooltip();
    });
  }).catch(() => {
    container.innerHTML = "";
    const empty = document.createElement("p");
    empty.className = "section-empty-state";
    empty.textContent = "TPAR trajectory not available for this season.";
    container.appendChild(empty);
  });
}

// The `.chart-tooltip` CSS class carries no position rule of its own -- it
// MUST be set to fixed here (plus a transform for above/below-bar centering
// and an edge-of-viewport nudge), or the tooltip renders in normal document
// flow wherever it was appended.
function showChartTooltip(event, text, svgElement, svgX, svgY, mvImpact) {
  hideChartTooltip();
  const svgRect = svgElement.getBoundingClientRect();
  const pageX = svgRect.left + svgX;
  const pageY = svgRect.top + svgY;

  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip";
  text.split("\n").forEach(line => {
    const lineEl = document.createElement("div");
    lineEl.textContent = line;
    tooltip.appendChild(lineEl);
  });

  tooltip.style.position = "fixed";
  tooltip.style.left = `${pageX}px`;
  tooltip.style.top = `${pageY}px`;
  tooltip.style.transform = mvImpact >= 0 ? "translate(-50%, -100%)" : "translate(-50%, 0)";

  document.body.appendChild(tooltip);

  const rect = tooltip.getBoundingClientRect();
  if (rect.left < 10) {
    tooltip.style.left = "10px";
    tooltip.style.transform = tooltip.style.transform.replace("translate(-50%", "translate(0");
  } else if (rect.right > window.innerWidth - 10) {
    tooltip.style.left = `${window.innerWidth - 10}px`;
    tooltip.style.transform = tooltip.style.transform.replace("translate(-50%", "translate(-100%");
  }
  if (rect.top < 10) {
    tooltip.style.top = `${pageY + 20}px`;
    tooltip.style.transform = tooltip.style.transform.replace("-100%", "0");
  } else if (rect.bottom > window.innerHeight - 10) {
    tooltip.style.top = `${pageY - 20}px`;
    tooltip.style.transform = tooltip.style.transform.replace("0", "-100%");
  }
}
function hideChartTooltip() {
  const existing = document.querySelector(".chart-tooltip");
  if (existing) existing.remove();
}

// ===============================
// Match history
// ===============================

function createOpponentRankBadge(rank) {
  if (rank === null || rank === undefined || rank === "") {
    const badge = document.createElement("span");
    badge.className = "rank-badge unr-badge";
    badge.textContent = "UNR";
    return badge;
  }
  const badge = document.createElement("span");
  badge.className = "rank-badge";
  if (rank === 1) badge.classList.add("medal-gold");
  else if (rank === 2) badge.classList.add("medal-silver");
  else if (rank >= 3 && rank <= 5) badge.classList.add("medal-bronze");
  else if (rank >= 6 && rank <= 10) badge.classList.add("top");
  else badge.classList.add("standard");
  badge.textContent = `#${rank}`;
  return badge;
}

function formatDateMMDDYY(dateStr) {
  if (!dateStr) return "—";
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return dateStr;
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const year = String(date.getFullYear()).slice(-2);
  return `${month}-${day}-${year}`;
}

function renderMatchHistory(matches) {
  const tbody = document.querySelector("#match-table tbody");
  tbody.innerHTML = "";

  const sortedMatches = [...matches].sort((a, b) => (a.date || "").localeCompare(b.date || ""));

  sortedMatches.forEach((match) => {
    const tr = document.createElement("tr");

    const dateTd = document.createElement("td");
    dateTd.textContent = formatDateMMDDYY(match.date);
    tr.appendChild(dateTd);

    const oppTd = document.createElement("td");
    oppTd.className = "name-cell";
    if (match.opponent_id) {
      const a = document.createElement("a");
      a.href = `/wrestler.html?id=${match.opponent_id}`;
      a.textContent = safe(match.opponent_name);
      oppTd.appendChild(a);
    } else {
      oppTd.textContent = safe(match.opponent_name);
    }
    tr.appendChild(oppTd);

    const oppTeamTd = document.createElement("td");
    oppTeamTd.className = "metric-secondary";
    const oppTeamName = safe(match.opponent_team);
    if (oppTeamName && oppTeamName !== "—") {
      const teamLink = document.createElement("a");
      teamLink.href = `/team.html?team=${teamNameToSlug(oppTeamName)}`;
      teamLink.textContent = oppTeamName;
      oppTeamTd.appendChild(teamLink);
    } else {
      oppTeamTd.textContent = oppTeamName;
    }
    tr.appendChild(oppTeamTd);

    const oppRankTd = document.createElement("td");
    oppRankTd.appendChild(createOpponentRankBadge(match.opponent_rank));
    tr.appendChild(oppRankTd);

    const resultTd = document.createElement("td");
    resultTd.appendChild(createResultBadge(match.result, match.method));
    tr.appendChild(resultTd);

    const impactTd = document.createElement("td");
    impactTd.className = "num";
    const mvImpact = match.mv_impact_v1 !== undefined ? match.mv_impact_v1 : match.mv_impact;
    if (mvImpact !== null && mvImpact !== undefined) {
      impactTd.textContent = mvImpact > 0 ? `+${mvImpact.toFixed(1)}` : mvImpact.toFixed(1);
      impactTd.classList.add(mvImpact > 0 ? "impact-positive" : "impact-negative");
    } else {
      impactTd.textContent = "—";
    }
    tr.appendChild(impactTd);

    const scoreTd = document.createElement("td");
    scoreTd.className = "metric-secondary num";
    scoreTd.textContent = safe(match.score);
    tr.appendChild(scoreTd);

    tbody.appendChild(tr);
  });
}

// ===============================
// Mobile match list: 4 columns (date | rank+name/team | result pill+score |
// impact), one row each, no stacked run-on line, no initials.
// ===============================

function formatDateShort(dateStr) {
  if (!dateStr) return "—";
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return dateStr;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function renderMobileMatchList(matches, season) {
  const list = document.getElementById("wp2m-match-list");
  const yearEl = document.getElementById("wp2m-matches-year");
  if (yearEl) yearEl.textContent = safe(season);
  if (!list) return;

  if (!matches.length) {
    list.innerHTML = `<p class="section-empty-state">No matches yet this season.</p>`;
    return;
  }

  const sortedMatches = [...matches].sort((a, b) => (a.date || "").localeCompare(b.date || ""));

  list.innerHTML = sortedMatches.map(match => {
    const isWin = match.result === "W";
    const { code } = matchMethodCode(match.result, match.method);
    const pillLabel = code === "FALL" ? "F" : code;

    // Decision/MD/TF/etc. show the stored score as-is (winner-loser, never
    // flipped for a loss); a fall has no score, only a clock time; anything
    // else with neither is a bare forfeit/no-score bout.
    const scoreOrTime = match.score ? safe(match.score) : (code === "FALL" ? safe(match.duration) : "—");

    const mvImpact = match.mv_impact_v1 !== undefined ? match.mv_impact_v1 : match.mv_impact;
    let impactText, impactCls;
    if (mvImpact === null || mvImpact === undefined) {
      impactText = "—"; impactCls = "wp2m-impact-nodata";
    } else if (mvImpact > 0) {
      impactText = `+${mvImpact.toFixed(1)}`; impactCls = "wp2m-impact-positive";
    } else if (mvImpact < 0) {
      impactText = mvImpact.toFixed(1); impactCls = "wp2m-impact-negative";
    } else {
      impactText = "0.0"; impactCls = "wp2m-impact-nodata";
    }

    // Full name only -- never an initial-dot abbreviation. opponent_name is
    // already stored as the full first+last name in the match payload. The
    // whole row is the link (when an id exists), so the name itself is
    // plain text here, not a nested anchor.
    const fullName = safe(match.opponent_name);
    const rankHtml = match.opponent_rank ? `<span class="wp2m-match-rank">#${match.opponent_rank}</span> ` : "";

    const href = match.opponent_id ? `/wrestler.html?id=${match.opponent_id}` : null;
    const tag = href ? "a" : "div";
    const hrefAttr = href ? ` href="${href}"` : "";

    return (
      `<${tag} class="wp2m-match-row"${hrefAttr}>` +
      `<div class="wp2m-match-date">${formatDateShort(match.date)}</div>` +
      `<div class="wp2m-match-opponent">` +
      `<div class="wp2m-match-opp-name">${rankHtml}${fullName}</div>` +
      `<div class="wp2m-match-opp-team">${safe(match.opponent_team)}</div>` +
      `</div>` +
      `<div class="wp2m-match-result">` +
      `<span class="wp2m-match-pill ${isWin ? "wp2m-match-pill--win" : "wp2m-match-pill--loss"}">${pillLabel}</span>` +
      `<span class="wp2m-match-score">${scoreOrTime}</span>` +
      `</div>` +
      `<div class="wp2m-match-impact ${impactCls}">${impactText}</div>` +
      `</${tag}>`
    );
  }).join("");
}
