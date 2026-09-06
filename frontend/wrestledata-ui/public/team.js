// ========================================
// Team profile page: reframed around 3 jobs in order -- projection (team
// points vs. the field), lineup (who starts, what each weight is worth),
// how they wrestle (the box-score stats). TPAR stays but is demoted to a
// column -- the hero is team points, not TPAR.
// ========================================

const SEASON = "2026";

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

// TPAR: no sign, same format as the rankings page ("5.8" not "+5.8").
function fmtTpar(v) {
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

// Unified rank-tier system for this page: #1 gold, #2-4 navy, #5-12 slate,
// #13+ gray.
function rankTierClass(rank) {
  if (rank === null || rank === undefined) return "tp2-rank--unranked";
  if (rank === 1) return "tp2-rank--gold";
  if (rank <= 4) return "tp2-rank--navy";
  if (rank <= 12) return "tp2-rank--slate";
  return "tp2-rank--gray";
}
function rankChip(rank) {
  const span = document.createElement("span");
  span.className = `tp2-rank-chip ${rankTierClass(rank)}`;
  span.textContent = rank ? `#${rank}` : "—";
  return span;
}

function seedRisk(aaProb) {
  if (aaProb === null || aaProb === undefined) return null;
  if (aaProb >= 0.85) return { label: "Lock", cls: "tp2-risk-lock" };
  if (aaProb >= 0.4) return { label: "Coin flip", cls: "tp2-risk-flip" };
  return { label: "Bubble", cls: "tp2-risk-bubble" };
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

    const starterIds = new Set(Object.values(team.roster.starters).filter(Boolean));
    const remainingIds = [...allWrestlerIds].filter(id => !starterIds.has(id));

    const starterEntries = Object.entries(team.roster.starters).filter(([, id]) => id);
    const [starterProfiles, remainingProfiles] = await Promise.all([
      Promise.all(starterEntries.map(async ([weight, id]) => {
        try { return { weight: Number(weight), profile: await fetchJSON(`/data/wrestlers/${SEASON}/by_id/${id}.json`) }; }
        catch { return { weight: Number(weight), profile: null }; }
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
    document.getElementById("team-resume").textContent = err.message;
  }
}

function renderTeamPage({ team, teamName, metrics, xtpData, xtpTeams, starterProfiles, remainingProfiles }) {
  renderHeader(team, metrics);
  renderHero(teamName, xtpData, xtpTeams);
  renderStartingRoster(starterProfiles, xtpData);
  renderScoreCard(metrics);
  renderFinishCard(metrics);
  renderRemainingRoster(remainingProfiles);
}

// ===============================
// Header
// ===============================

function renderHeader(team, metrics) {
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

  // Chips: never render a chip for missing data (conference is genuinely
  // null for some teams, so the chip is simply omitted, not filled with a
  // placeholder).
  const chipsEl = document.getElementById("team-chips");
  chipsEl.innerHTML = "";
  if (team.conference) {
    const c = document.createElement("span");
    c.className = "tp2-chip";
    c.textContent = team.conference;
    chipsEl.appendChild(c);
  }
  if (team.division) {
    const d = document.createElement("span");
    d.className = "tp2-chip";
    d.textContent = team.division;
    chipsEl.appendChild(d);
  }
  // No coach field exists in the data -- omitted entirely, same principle.

  const resumeEl = document.getElementById("team-resume");
  const counts = (metrics && metrics.counts) || {};
  const parts = [`${SEASON - 1}-${String(SEASON).slice(2)}`];
  if (counts.wins_included !== undefined && counts.losses_included !== undefined) {
    parts.push(`Overall Record ${counts.wins_included}-${counts.losses_included}`);
  }
  resumeEl.textContent = parts.join(" · ");
}

// ===============================
// Hero: projected NCAA team points
// ===============================

function renderHero(teamName, xtpData, xtpTeams) {
  const valueEl = document.getElementById("hero-value");
  const rankEl = document.getElementById("hero-rank");
  const barEl = document.getElementById("hero-segmented-bar");
  const legendEl = document.getElementById("hero-segmented-legend");
  const onelinerEl = document.getElementById("hero-oneliner");
  const top5El = document.getElementById("hero-top5-rows");

  if (!xtpData) {
    valueEl.textContent = "—";
    document.getElementById("hero-section").querySelector(".tp2-hero-label").textContent = "Projected NCAA team points not available";
    return;
  }

  valueEl.textContent = fmtDecimal(xtpData.team_xTP, 1);

  const sorted = [...xtpTeams].sort((a, b) => {
    if (b.team_xTP !== a.team_xTP) return b.team_xTP - a.team_xTP;
    if (b.team_xTP_P !== a.team_xTP_P) return b.team_xTP_P - a.team_xTP_P;
    return a.team.localeCompare(b.team);
  });
  const rank = sorted.findIndex(t => t.team === teamName) + 1;
  rankEl.innerHTML = "";
  if (rank > 0) rankEl.appendChild(rankChip(rank));

  // Segmented 100% bar: this team's own placement/advancement/bonus split.
  const p = xtpData.team_xTP_P || 0, a = xtpData.team_xTP_A || 0, b = xtpData.team_xTP_B || 0;
  const total = p + a + b || 1;
  barEl.innerHTML = `
    <span class="tp2-segment tp2-segment--placement" style="width:${(p / total * 100).toFixed(1)}%"></span>
    <span class="tp2-segment tp2-segment--advancement" style="width:${(a / total * 100).toFixed(1)}%"></span>
    <span class="tp2-segment tp2-segment--bonus" style="width:${(b / total * 100).toFixed(1)}%"></span>
  `;
  legendEl.innerHTML = `
    <span class="tp2-legend-item"><span class="tp2-legend-swatch tp2-segment--placement"></span>Placement ${fmtDecimal(p)}</span>
    <span class="tp2-legend-item"><span class="tp2-legend-swatch tp2-segment--advancement"></span>Advancement ${fmtDecimal(a)}</span>
    <span class="tp2-legend-item"><span class="tp2-legend-swatch tp2-segment--bonus"></span>Bonus ${fmtDecimal(b)}</span>
  `;

  // Projected finalists/champions: expected value (sum of real per-wrestler
  // probabilities), not a hard threshold count.
  const weights = Object.values(xtpData.weights || {});
  const finalists = Math.round(weights.reduce((s, w) => s + (w.final_prob || 0), 0));
  const champions = Math.round(weights.reduce((s, w) => s + (w.champ_prob || 0), 0));
  onelinerEl.textContent = `${finalists} projected finalists · ${champions} projected champions`;

  // Top 5 team comparison -- shows the gap vs the field directly.
  const top5 = sorted.slice(0, 5);
  const maxVal = top5[0].team_xTP;
  top5El.innerHTML = top5.map(t => {
    const isSelf = t.team === teamName;
    const pct = Math.max((t.team_xTP / maxVal) * 100, 2);
    return `<div class="tp2-top5-row ${isSelf ? "tp2-top5-row--self" : ""}">` +
      `<span class="tp2-top5-name">${t.team}</span>` +
      `<span class="tp2-top5-bar-track"><span class="tp2-top5-bar-fill" style="width:${pct}%"></span></span>` +
      `<span class="tp2-top5-value">${fmtDecimal(t.team_xTP)}</span>` +
      `</div>`;
  }).join("");
}

// ===============================
// Starting roster
// ===============================

function renderStartingRoster(starters, xtpData) {
  const tbody = document.querySelector("#starting-roster-table tbody");
  tbody.innerHTML = "";
  starters.sort((a, b) => a.weight - b.weight);

  const maxXTP = Math.max(...starters.map(({ weight }) => (xtpData?.weights?.[String(weight)]?.xTP) || 0), 1);

  starters.forEach(({ weight, profile }) => {
    const wd = xtpData?.weights?.[String(weight)];
    const tr = document.createElement("tr");

    const weightTd = document.createElement("td");
    weightTd.textContent = weight;
    tr.appendChild(weightTd);

    const nameTd = document.createElement("td");
    nameTd.className = "name-cell";
    if (profile?.wrestler_id) {
      const a = document.createElement("a");
      a.href = `/wrestler.html?id=${profile.wrestler_id}`;
      a.textContent = profile.name || "Unknown";
      nameTd.appendChild(a);
      const grade = abbrevGrade(profile.grade);
      if (grade) {
        const sub = document.createElement("div");
        sub.className = "tp2-name-sub";
        sub.textContent = grade;
        nameTd.appendChild(sub);
      }
    } else {
      nameTd.textContent = "—";
    }
    tr.appendChild(nameTd);

    const rankTd = document.createElement("td");
    const rank = wd?.rank ?? profile?.current_rank;
    rankTd.appendChild(rankChip(rank));
    tr.appendChild(rankTd);

    const tparTd = document.createElement("td");
    tparTd.className = "num";
    const tparVal = fmtTpar(profile?.metrics?.mat_value?.mv_avg);
    tparTd.textContent = tparVal !== null ? tparVal : "—";
    tr.appendChild(tparTd);

    const projTd = document.createElement("td");
    projTd.className = "num tp2-proj-cell";
    if (wd && wd.xTP !== null && wd.xTP !== undefined) {
      const pct = Math.max((wd.xTP / maxXTP) * 100, 2);
      const p = wd.xTP_P || 0, a = wd.xTP_A || 0, b = wd.xTP_B || 0;
      const rowTotal = (p + a + b) || 1;
      projTd.innerHTML =
        `<span class="tp2-proj-value">${fmtDecimal(wd.xTP)}</span>` +
        `<span class="tp2-proj-bar-track" style="width:${pct}%">` +
        `<span class="tp2-segment tp2-segment--placement" style="width:${(p / rowTotal * 100).toFixed(1)}%"></span>` +
        `<span class="tp2-segment tp2-segment--advancement" style="width:${(a / rowTotal * 100).toFixed(1)}%"></span>` +
        `<span class="tp2-segment tp2-segment--bonus" style="width:${(b / rowTotal * 100).toFixed(1)}%"></span>` +
        `</span>`;
    } else {
      projTd.textContent = "0";
    }
    tr.appendChild(projTd);

    const breakdownTd = document.createElement("td");
    breakdownTd.className = "tp2-breakdown-cell";
    if (wd) {
      breakdownTd.textContent = `${fmtDecimal(wd.xTP_P)} pl · ${fmtDecimal(wd.xTP_A)} adv · ${fmtDecimal(wd.xTP_B)} bonus`;
    } else {
      breakdownTd.textContent = "—";
    }
    tr.appendChild(breakdownTd);

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

    tbody.appendChild(tr);
  });
}

// ===============================
// How they score / How they finish
// ===============================

function renderScoreCard(metrics) {
  const card = document.getElementById("score-card");
  const m = metrics.metrics || {};
  const counts = metrics.counts || {};

  card.innerHTML = `
    <div class="tp2-subhead">How they score</div>
    <div class="tp2-big-stat">
      <span class="tp2-big-stat-value">${rankInParens(m.avg_pd7?.value, m.avg_pd7?.rank, v => fmtDecimal(v))}</span>
      <span class="tp2-big-stat-label">Point differential / 7 min</span>
    </div>
    <div class="tp2-two-bar" id="score-two-bar"></div>
    <div class="tp2-stat-row"><span>Overall Record</span><span>${counts.wins_included ?? "—"}–${counts.losses_included ?? "—"} (${percent(counts.win_pct)})</span></div>
    <div class="tp2-stat-row"><span>Top-10 record</span><span>${rankInParens(m.top10_win_pct?.value, m.top10_win_pct?.rank, percent)}</span></div>
  `;

  const pf = m.avg_pf7?.value || 0, pa = m.avg_pa7?.value || 0;
  const maxPfPa = Math.max(pf, pa, 1);
  document.getElementById("score-two-bar").innerHTML = `
    <div class="tp2-two-bar-row"><span class="tp2-two-bar-label">Scored</span><span class="tp2-two-bar-track"><span class="tp2-two-bar-fill tp2-two-bar-fill--scored" style="width:${(pf / maxPfPa * 100).toFixed(1)}%"></span></span><span class="tp2-two-bar-value">${fmtDecimal(pf)}</span></div>
    <div class="tp2-two-bar-row"><span class="tp2-two-bar-label">Allowed</span><span class="tp2-two-bar-track"><span class="tp2-two-bar-fill tp2-two-bar-fill--allowed" style="width:${(pa / maxPfPa * 100).toFixed(1)}%"></span></span><span class="tp2-two-bar-value">${fmtDecimal(pa)}</span></div>
  `;
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

// ===============================
// Remaining roster: next up vs. the rest
// ===============================

const NEXT_UP_RANK_CUTOFF = 40;
const NEXT_UP_TPAR_CUTOFF = 0;

function renderTparCell(profile) {
  const mv = profile?.metrics?.mat_value?.mv_avg;
  if (mv === null || mv === undefined) {
    return `<span class="tp2-tpar-nodata">— <span class="tp2-nodata-label">Insufficient data</span></span>`;
  }
  const cls = mv < 0 ? "tp2-tpar-negative" : mv >= 3.0 ? "tp2-tpar-positive" : "";
  return `<span class="${cls}">${fmtTpar(mv)}</span>`;
}

function renderRemainingRoster(remaining) {
  remaining.sort((a, b) => {
    const w = (a.weight || 999) - (b.weight || 999);
    if (w !== 0) return w;
    const mvA = a.profile?.metrics?.mat_value?.mv_avg ?? -999;
    const mvB = b.profile?.metrics?.mat_value?.mv_avg ?? -999;
    return mvB - mvA;
  });

  const nextUp = [];
  const rest = [];
  remaining.forEach(entry => {
    const rank = entry.profile?.current_rank;
    const mv = entry.profile?.metrics?.mat_value?.mv_avg;
    const isNextUp = (rank !== null && rank !== undefined && rank <= NEXT_UP_RANK_CUTOFF) ||
      (mv !== null && mv !== undefined && mv > NEXT_UP_TPAR_CUTOFF);
    (isNextUp ? nextUp : rest).push(entry);
  });

  const buildRows = (list) => list.map(({ weight, profile }) => {
    const nameCell = profile?.wrestler_id
      ? `<a href="/wrestler.html?id=${profile.wrestler_id}">${profile.name || "Unknown"}</a>`
      : "—";
    const rank = profile?.current_rank;
    return `<tr>` +
      `<td>${weight || "—"}</td>` +
      `<td>${nameCell}</td>` +
      `<td>${rank ? `<span class="tp2-rank-chip ${rankTierClass(rank)}">#${rank}</span>` : "—"}</td>` +
      `<td class="num">${renderTparCell(profile)}</td>` +
      `</tr>`;
  }).join("");

  document.getElementById("next-up-body").innerHTML = buildRows(nextUp);
  document.getElementById("rest-body").innerHTML = buildRows(rest);
  document.getElementById("rest-count").textContent = rest.length;

  const toggleBtn = document.getElementById("toggle-rest-btn");
  const restWrapper = document.getElementById("rest-wrapper");
  if (rest.length === 0) {
    toggleBtn.hidden = true;
  } else {
    toggleBtn.addEventListener("click", () => {
      restWrapper.hidden = !restWrapper.hidden;
      toggleBtn.textContent = restWrapper.hidden ? `Show the rest (${rest.length})` : "Hide";
    });
  }
}
