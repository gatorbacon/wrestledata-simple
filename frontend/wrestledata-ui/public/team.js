// ========================================
// Team profile page: the team directory profile (distinct from Team race,
// which is the xTP leaderboard/comparison page). Header carries identity
// (left) and the team's projected points (right, no "xTP" label anywhere
// on this page); then Starting Roster, one merged Scoring per 7 Minutes
// card, then Remaining Roster. No placement/advancement/bonus split here.
// Same data sources throughout, no new fetches beyond team_metrics' now
// slightly richer counts (top10_wins/top10_losses added alongside the
// existing win/loss aggregates -- see build_team_metrics.py).
// ========================================

const SEASON = "2026";
const WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285];

function safe(v, fn) {
  if (v === null || v === undefined || v === "") return "—";
  return fn ? fn(v) : v;
}

function percent(v) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return (v * 100).toFixed(1) + "%";
}

function fmtDecimal(v, decimals = 1) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return Number(v).toFixed(decimals);
}

// Always show the sign, for point-differential-style stats ("+1.4"/"-0.6").
function fmtSigned(v, decimals = 1) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  const n = Number(v);
  return (n >= 0 ? "+" : "") + n.toFixed(decimals);
}

// DPG: no sign, same format as the rankings page ("5.8" not "+5.8").
function fmtDpg(v) {
  if (v === null || v === undefined || isNaN(v)) return null;
  return v.toFixed(1);
}

function rankInParens(value, rank, formatter) {
  const valStr = formatter ? formatter(value) : safe(value);
  if (valStr === "—") return "—";
  return rank !== null && rank !== undefined ? `${valStr} (#${rank})` : valStr;
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}`);
  return res.json();
}

function teamNameToProcessedDataFilename(teamName) {
  return teamName.replace(/\s+/g, "_");
}

const GRADE_ABBREV = [
  [/redshirt.*fr|r-?fr/i, "RS Fr."],
  [/redshirt.*so|r-?so/i, "RS So."],
  [/redshirt.*jr|r-?jr/i, "RS Jr."],
  [/redshirt.*sr|r-?sr/i, "RS Sr."],
  [/fresh|^fr\.?$/i, "Fr."],
  [/soph|^so\.?$/i, "So."],
  [/junior|^jr\.?$/i, "Jr."],
  [/senior|^sr\.?$/i, "Sr."],
  [/graduate/i, "Gr."],
];
function abbrevGrade(grade) {
  if (!grade) return "";
  for (const [re, short] of GRADE_ABBREV) {
    if (re.test(grade)) return short;
  }
  return grade;
}

// Sitewide rank-badge convention (same as Rankings/Team race/Hodge): top 3
// get a medal, everything else is a neutral "standard" pill, no rank is UNR.
function createRankBadge(rank) {
  if (rank === null || rank === undefined || rank === "") {
    return createUnrankedBadge();
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
function createUnrankedBadge() {
  const badge = document.createElement("span");
  badge.className = "rank-badge unr-badge";
  badge.textContent = "UNR";
  return badge;
}

function seedRisk(aaProb) {
  if (aaProb === null || aaProb === undefined) return null;
  if (aaProb >= 0.85) return { label: "Lock", cls: "tp2-risk-lock" };
  if (aaProb >= 0.4) return { label: "Coin flip", cls: "tp2-risk-flip" };
  return { label: "Bubble", cls: "tp2-risk-bubble" };
}

// Photo + rank pill + name (+ class year) cell, same crop convention as the
// rest of the site's headshot rows, just smaller (32-40px here vs 64px
// elsewhere). Photo is omitted entirely (no crest/placeholder fallback)
// when missing. Rank pill sits between the photo and the name -- no
// separate Rank column, and never folded into the name text itself.
function renderWrestlerCell(profile, rank) {
  const wrap = document.createElement("div");
  wrap.className = "tp2-wrestler-cell";

  if (profile?.photo_url) {
    const img = document.createElement("img");
    img.className = "tp2-headshot";
    img.src = profile.photo_url;
    img.alt = "";
    img.loading = "lazy";
    img.onerror = () => { img.remove(); };
    wrap.appendChild(img);
  }

  wrap.appendChild(createRankBadge(rank));

  const textWrap = document.createElement("div");
  if (profile?.wrestler_id) {
    const a = document.createElement("a");
    a.href = `/wrestler.html?id=${profile.wrestler_id}`;
    a.textContent = profile.name || "Unknown";
    textWrap.appendChild(a);
  } else {
    textWrap.appendChild(document.createTextNode(safe(profile?.name)));
  }
  const grade = abbrevGrade(profile?.grade);
  if (grade) {
    const sub = document.createElement("div");
    sub.className = "tp2-name-sub";
    sub.textContent = grade;
    textWrap.appendChild(sub);
  }
  wrap.appendChild(textWrap);
  return wrap;
}

// Season record: the wrestler's own current-season W-L, already computed
// on their profile (record.overall) -- never derived/invented here.
function seasonRecord(profile) {
  return profile?.record?.overall || "—";
}

// Shared row builder for Starting Roster and Remaining Roster: weight,
// wrestler cell (photo + rank pill + name), season record, DPG, then
// (Starting Roster only) bold points + seed-risk chip.
function buildRosterRow(weight, profile, wd, { withPoints }) {
  const tr = document.createElement("tr");

  const weightTd = document.createElement("td");
  weightTd.textContent = weight;
  tr.appendChild(weightTd);

  // Empty slot: weight + dashes across every other column, no fake data.
  if (!profile) {
    const colCount = withPoints ? 5 : 3;
    for (let i = 0; i < colCount; i++) {
      const dashTd = document.createElement("td");
      dashTd.className = "tp2-empty-slot";
      dashTd.textContent = "—";
      tr.appendChild(dashTd);
    }
    return tr;
  }

  const rank = wd?.rank ?? profile?.current_rank;

  const nameTd = document.createElement("td");
  nameTd.className = "name-cell";
  nameTd.appendChild(renderWrestlerCell(profile, rank));
  tr.appendChild(nameTd);

  const recordTd = document.createElement("td");
  recordTd.textContent = seasonRecord(profile);
  tr.appendChild(recordTd);

  const dpgTd = document.createElement("td");
  dpgTd.className = "num";
  const dpgVal = fmtDpg(profile?.metrics?.mat_value?.mv_avg);
  dpgTd.textContent = dpgVal !== null ? dpgVal : "—";
  tr.appendChild(dpgTd);

  if (withPoints) {
    const pointsTd = document.createElement("td");
    pointsTd.className = "num tp2-proj-cell";
    pointsTd.textContent = wd && wd.xTP !== null && wd.xTP !== undefined ? fmtDecimal(wd.xTP) : "—";
    tr.appendChild(pointsTd);

    const riskTd = document.createElement("td");
    const risk = wd ? seedRisk(wd.aa_prob) : null;
    if (risk) {
      const chip = document.createElement("span");
      chip.className = `tp2-risk-chip ${risk.cls}`;
      chip.textContent = risk.label;
      riskTd.appendChild(chip);
    } else {
      riskTd.textContent = "—";
    }
    tr.appendChild(riskTd);
  }

  return tr;
}

// ===============================
// Fetch + orchestration
// ===============================

async function loadTeam(teamId) {
  try {
    const team = await fetchJSON(`/data/teams/${teamId}.json`);
    const teamName = team.team_name || team.name;

    const metricsFile = await fetchJSON(`/data/team_metrics/${SEASON}/team_metrics.json`);
    const metrics = metricsFile.teams.find(t => t.team_id === teamId);

    const xtpFile = await fetchJSON(`/data/xtp/${SEASON}/xtp_teams_${SEASON}.json`).catch(() => null);
    const xtpTeams = xtpFile ? (Array.isArray(xtpFile) ? xtpFile : (xtpFile.teams || [])) : [];
    const xtpData = xtpTeams.find(t => t.team === teamName) || null;

    let allWrestlerIds = new Set();
    try {
      const processed = await fetchJSON(`/data/processed_data/ncaa_men/${SEASON}/${teamNameToProcessedDataFilename(teamName)}.json`);
      (processed.roster || []).forEach(w => { if (w.season_wrestler_id) allWrestlerIds.add(w.season_wrestler_id); });
    } catch (err) { /* remaining roster just won't have entries */ }

    const starters = team.roster.starters || {};
    const starterIds = new Set(Object.values(starters).filter(Boolean));
    const remainingIds = [...allWrestlerIds].filter(id => !starterIds.has(id));

    const [starterProfiles, remainingProfiles] = await Promise.all([
      Promise.all(WEIGHTS.map(async weight => {
        const id = starters[String(weight)];
        if (!id) return { weight, profile: null };
        try { return { weight, profile: await fetchJSON(`/data/wrestlers/${SEASON}/by_id/${id}.json`) }; }
        catch { return { weight, profile: null }; }
      })),
      Promise.all(remainingIds.map(async id => {
        try {
          const profile = await fetchJSON(`/data/wrestlers/${SEASON}/by_id/${id}.json`);
          return { weight: profile.weight_class ? Number(profile.weight_class) : null, profile };
        } catch { return null; }
      })).then(list => list.filter(Boolean)),
    ]);

    renderTeamPage({ team, teamName, metrics, xtpData, xtpTeams, starterProfiles, remainingProfiles });
  } catch (err) {
    console.error(err);
    document.getElementById("team-name").textContent = "Team Not Found";
    document.getElementById("team-subline").textContent = err.message;
  }
}

// A team's Team race rank comes from this same xTP dataset (this page keeps
// the existing xTP source rather than pivoting to the Monte Carlo team_odds
// feed that now powers the Team race page itself). Shown exactly once, as
// the header's "Team race #N" link -- no second copy of the rank pill.
function computeTeamRank(teamName, xtpTeams) {
  if (!xtpTeams || xtpTeams.length === 0) return null;
  const sorted = [...xtpTeams].sort((a, b) => {
    if (b.team_xTP !== a.team_xTP) return b.team_xTP - a.team_xTP;
    if (b.team_xTP_P !== a.team_xTP_P) return b.team_xTP_P - a.team_xTP_P;
    return a.team.localeCompare(b.team);
  });
  const idx = sorted.findIndex(t => t.team === teamName);
  return idx >= 0 ? idx + 1 : null;
}

function renderTeamPage({ team, teamName, metrics, xtpData, xtpTeams, starterProfiles, remainingProfiles }) {
  const rank = computeTeamRank(teamName, xtpTeams);
  renderHeader(team, rank, xtpData);
  renderStartingRoster(starterProfiles, xtpData);
  renderScoreCard(metrics);
  renderFinishCard(metrics);
  renderRemainingRoster(remainingProfiles);
}

// ===============================
// Header: identity (left) + projected team points (right)
// ===============================

function renderHeader(team, rank, xtpData) {
  const teamName = team.team_name || team.name;
  document.getElementById("team-name").textContent = teamName;

  const logo = document.getElementById("team-logo");
  const slug = team.team_id;
  logo.src = `/assets/team_logos/${slug}.svg`;
  logo.alt = `${teamName} logo`;
  logo.hidden = false;
  logo.onerror = () => {
    if (!logo.dataset.fb) { logo.dataset.fb = "1"; logo.src = `/assets/team_logos/${slug}.png`; }
    else { logo.hidden = true; }
  };

  // "Conference · D1" -- omit a clause entirely rather than invent a
  // placeholder when conference is genuinely null for a team.
  const sublineEl = document.getElementById("team-subline");
  const parts = [team.conference, team.division].filter(Boolean);
  sublineEl.textContent = parts.join(" · ");

  // Team race rank -- links to the Team race leaderboard. No invented
  // dual-record line: team_metrics' win/loss counts are an all-bouts
  // aggregate across the roster, not a season dual record, so it can't be
  // labeled correctly and is omitted per the same "don't invent it" rule.
  const raceLineEl = document.getElementById("team-race-line");
  raceLineEl.innerHTML = "";
  if (rank) {
    raceLineEl.appendChild(document.createTextNode("Team race "));
    const pill = document.createElement("a");
    pill.className = "rank-badge standard tp2-teamrace-pill";
    pill.href = "/leaderboards/xtp/teams.html";
    pill.textContent = `#${rank}`;
    raceLineEl.appendChild(pill);
  }

  // Projected team points -- no "xTP" label anywhere on this page.
  const valueEl = document.getElementById("hero-value");
  const onelinerEl = document.getElementById("hero-oneliner");

  if (!xtpData) {
    valueEl.textContent = "—";
    onelinerEl.textContent = "";
    return;
  }
  valueEl.textContent = fmtDecimal(xtpData.team_xTP, 1);

  // Projected AAs/champions: expected value (sum of real per-wrestler
  // probabilities: aa_prob / champ_prob), not a hard threshold count. Hide
  // a clause if it rounds to zero rather than printing "0 projected
  // champions". No team-level title-% field exists in this xTP source, so
  // that clause is omitted entirely rather than invented.
  const weights = Object.values(xtpData.weights || {});
  const projectedAAs = Math.round(weights.reduce((s, w) => s + (w.aa_prob || 0), 0));
  const projectedChamps = Math.round(weights.reduce((s, w) => s + (w.champ_prob || 0), 0));
  const clauses = [];
  if (projectedAAs > 0) clauses.push(`${projectedAAs} projected AA${projectedAAs === 1 ? "" : "s"}`);
  if (projectedChamps > 0) clauses.push(`${projectedChamps} projected champion${projectedChamps === 1 ? "" : "s"}`);
  onelinerEl.textContent = clauses.join(" · ");
}

// ===============================
// Starting Roster
// ===============================

function renderStartingRoster(starters, xtpData) {
  const tbody = document.querySelector("#starting-roster-table tbody");
  tbody.innerHTML = "";
  starters.forEach(({ weight, profile }) => {
    const wd = xtpData?.weights?.[String(weight)];
    tbody.appendChild(buildRosterRow(weight, profile, wd, { withPoints: true }));
  });
}

// ===============================
// Scoring per 7 Minutes / How they finish -- side-by-side cards
// ===============================

function renderScoreCard(metrics) {
  const card = document.getElementById("score-card");
  const m = metrics.metrics || {};
  const counts = metrics.counts || {};

  const hasTop10Record = counts.top10_wins !== null && counts.top10_wins !== undefined &&
    counts.top10_losses !== null && counts.top10_losses !== undefined;
  const top10Record = hasTop10Record ? `${counts.top10_wins}–${counts.top10_losses}` : "—";

  card.innerHTML = `
    <div class="tp2-subhead">Scoring per 7 Minutes</div>
    <div class="tp2-big-stat">
      <span class="tp2-big-stat-value">${fmtSigned(m.avg_pd7?.value)}</span>
      <span class="tp2-big-stat-label">point differential</span>
    </div>
    <div class="tp2-two-bar" id="score-two-bar"></div>
    <div class="tp2-stat-row"><span>Top-10 record</span><span>${top10Record}</span></div>
  `;

  const pf = m.avg_pf7?.value || 0, pa = m.avg_pa7?.value || 0;
  const maxPfPa = Math.max(pf, pa, 1);
  document.getElementById("score-two-bar").innerHTML = `
    <div class="tp2-two-bar-row"><span class="tp2-two-bar-label">Scored</span><span class="tp2-two-bar-track"><span class="tp2-two-bar-fill tp2-two-bar-fill--scored" style="width:${(pf / maxPfPa * 100).toFixed(1)}%"></span></span><span class="tp2-two-bar-value">${fmtDecimal(pf)}</span></div>
    <div class="tp2-two-bar-row"><span class="tp2-two-bar-label">Allowed</span><span class="tp2-two-bar-track"><span class="tp2-two-bar-fill tp2-two-bar-fill--allowed" style="width:${(pa / maxPfPa * 100).toFixed(1)}%"></span></span><span class="tp2-two-bar-value">${fmtDecimal(pa)}</span></div>
  `;
}

function renderFinishCard(metrics) {
  const card = document.getElementById("finish-card");
  const m = metrics.metrics || {};
  const am = metrics.advanced_metrics || {};

  card.innerHTML = `
    <div class="tp2-subhead">How they finish</div>
    <div class="tp2-stat-row"><span>Bonus</span><span>${rankInParens(m.bonus_rate?.value, m.bonus_rate?.rank, percent)}</span></div>
    <div class="tp2-stat-row"><span>TF</span><span>${rankInParens(m.tech_rate?.value, m.tech_rate?.rank, percent)}</span></div>
    <div class="tp2-stat-row"><span>Pin</span><span>${rankInParens(m.pin_rate?.value, m.pin_rate?.rank, percent)}</span></div>
    <div class="section-divider" style="margin:12px 0"></div>
  `;

  const skillWrap = document.createElement("div");
  if (am.si_plus?.value != null) skillWrap.appendChild(createSkillRow("SI+", "Scoring", am.si_plus.value));
  if (am.df_plus?.value != null) skillWrap.appendChild(createSkillRow("DF+", "Defense", am.df_plus.value));
  if (am.apr_plus?.value != null) skillWrap.appendChild(createSkillRow("APR+", "Pin Rate", am.apr_plus.value));
  card.appendChild(skillWrap);
}

function createSkillRow(label, fullName, value) {
  const row = document.createElement("div");
  row.className = "tp2-skill-row-dense";
  const labelEl = document.createElement("div");
  labelEl.className = "tp2-skill-row-label";
  labelEl.innerHTML = `${label} <span class="tp2-skill-fullname">${fullName}</span>`;
  row.appendChild(labelEl);

  const barWrapper = document.createElement("div");
  barWrapper.className = "skill-bar-wrapper";
  barWrapper.appendChild(Object.assign(document.createElement("div"), { className: "skill-baseline" }));
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

// ===============================
// Remaining Roster: everyone not in the Starting Roster, one flat sorted
// list, same row format (minus points/seed-risk, which backups don't have).
// ===============================

function renderRemainingRoster(remaining) {
  // Ranked first (rank ascending), unranked after; ties broken by higher
  // DPG first.
  const sorted = [...remaining].sort((a, b) => {
    const rankA = a.profile?.current_rank;
    const rankB = b.profile?.current_rank;
    const hasA = rankA !== null && rankA !== undefined;
    const hasB = rankB !== null && rankB !== undefined;
    if (hasA && hasB && rankA !== rankB) return rankA - rankB;
    if (hasA !== hasB) return hasA ? -1 : 1;
    const mvA = a.profile?.metrics?.mat_value?.mv_avg ?? -Infinity;
    const mvB = b.profile?.metrics?.mat_value?.mv_avg ?? -Infinity;
    return mvB - mvA;
  });

  const body = document.getElementById("roster-body");
  body.innerHTML = "";
  sorted.forEach(({ weight, profile }) => {
    body.appendChild(buildRosterRow(weight || "—", profile, null, { withPoints: false }));
  });
}
