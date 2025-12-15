function getQueryParam(key) {
  return new URLSearchParams(window.location.search).get(key);
}

function safe(v, fn) {
  if (v === null || v === undefined || v === "") return "—";
  return fn ? fn(v) : v;
}

function percent(v) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return (v * 100).toFixed(1) + "%";
}

function formatDecimal(v, decimals = 2) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  return Number(v).toFixed(decimals);
}

function formatWithRank(value, rank, formatter = null) {
  if (value === null || value === undefined || isNaN(value)) return "—";
  let valStr;
  if (formatter) {
    valStr = formatter(value);
  } else {
    valStr = typeof value === "number" ? Number(value).toFixed(1) : String(value);
  }
  if (rank === null || rank === undefined) return valStr;
  return `${valStr} (#${rank})`;
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}`);
  return res.json();
}

function teamNameToProcessedDataFilename(teamName) {
  // Convert team name to processed_data filename format
  // e.g., "Penn State" -> "Penn_State"
  return teamName.replace(/\s+/g, "_");
}

async function loadTeam(teamId) {
  try {
    // 1) Load team profile (identity + starters)
    const teamProfile = await fetchJSON(`/teams/${teamId}.json`);

    // 2) Load team metrics (analytics)
    const metricsData = await fetchJSON(`/team_metrics/2026/team_metrics.json`);
    const teamMetrics = metricsData.teams.find(t => t.team_id === teamId);

    if (!teamMetrics) {
      throw new Error(`No metrics found for team ${teamId}`);
    }

    // 3) Load processed_data to get all wrestler IDs
    const teamName = teamProfile.team_name || teamProfile.name;
    const processedDataFilename = teamNameToProcessedDataFilename(teamName);
    let allWrestlerIds = new Set();
    
    try {
      const processedData = await fetchJSON(`/processed_data/2026/${processedDataFilename}.json`);
      if (processedData.roster && Array.isArray(processedData.roster)) {
        processedData.roster.forEach(wrestler => {
          if (wrestler.season_wrestler_id) {
            allWrestlerIds.add(wrestler.season_wrestler_id);
          }
        });
      }
    } catch (err) {
      console.warn(`Could not load processed_data for ${teamName}:`, err);
      // Continue with just starters if processed_data is unavailable
    }

    // 4) Extract starter IDs
    const starters = teamProfile.roster.starters;
    const starterIds = new Set();
    Object.values(starters).forEach(id => {
      if (id) starterIds.add(id);
    });

    // 5) Compute remaining roster IDs
    const remainingIds = new Set();
    allWrestlerIds.forEach(id => {
      if (!starterIds.has(id)) {
        remainingIds.add(id);
      }
    });

    // 6) Load starter wrestler profiles
    const starterProfiles = [];
    for (const [weight, wrestlerId] of Object.entries(starters)) {
      if (!wrestlerId) continue;
      try {
      const w = await fetchJSON(`/wrestlers/2026/by_id/${wrestlerId}.json`);
      starterProfiles.push({ weight: Number(weight), profile: w });
      } catch (err) {
        console.warn(`Could not load wrestler profile ${wrestlerId}:`, err);
      }
    }

    // 7) Load remaining roster wrestler profiles
    const remainingProfiles = [];
    for (const wrestlerId of remainingIds) {
      try {
        const w = await fetchJSON(`/wrestlers/2026/by_id/${wrestlerId}.json`);
        const weight = w.weight_class ? Number(w.weight_class) : null;
        remainingProfiles.push({ weight, profile: w });
      } catch (err) {
        console.warn(`Could not load wrestler profile ${wrestlerId}:`, err);
      }
    }

    // 8) Load xTP data (optional, fail silently if missing)
    let xtpData = null;
    try {
      const xtpFile = await fetchJSON(`/xtp/2026/xtp_teams_2026.json`);
      const teamName = teamProfile.team_name || teamProfile.name;
      xtpData = xtpFile.teams.find(t => t.team === teamName);
    } catch (err) {
      console.warn(`Could not load xTP data:`, err);
      // Continue without xTP data
    }

    renderTeamPage(teamProfile, teamMetrics, starterProfiles, remainingProfiles, xtpData);
  } catch (err) {
    document.getElementById("team-name").textContent = "Team Not Found";
    document.getElementById("team-meta").textContent = err.message;
    console.error(err);
  }
}

function formatWLRecord(wins, losses, winPct) {
  if (wins === null || wins === undefined || losses === null || losses === undefined) {
    return "—";
  }
  const pct = winPct !== null && winPct !== undefined ? (winPct * 100).toFixed(1) : "0.0";
  return `${wins}–${losses} (${pct}%)`;
}

function renderTeamPage(team, metrics, starters, remaining, xtpData) {
  // Header
  const teamName = team.team_name || team.name;
  document.getElementById("team-name").textContent = teamName;
  document.getElementById("team-meta").textContent =
    `${team.conference} · ${team.division}`;

  // xTP section (show only if data exists)
  if (xtpData) {
    renderXTPSection(xtpData, starters);
  } else {
    document.getElementById("xtp-section").style.display = "none";
  }

  // Team metrics
  const m = metrics.metrics;
  document.getElementById("tm-pf7").textContent = formatWithRank(m.avg_pf7?.value, m.avg_pf7?.rank, formatDecimal);
  document.getElementById("tm-pa7").textContent = formatWithRank(m.avg_pa7?.value, m.avg_pa7?.rank, formatDecimal);
  document.getElementById("tm-pd7").textContent = formatWithRank(m.avg_pd7?.value, m.avg_pd7?.rank, formatDecimal);
  document.getElementById("tm-bonus").textContent = formatWithRank(m.bonus_rate?.value, m.bonus_rate?.rank, percent);
  document.getElementById("tm-pin").textContent = formatWithRank(m.pin_rate?.value, m.pin_rate?.rank, percent);
  document.getElementById("tm-tech").textContent = formatWithRank(m.tech_rate?.value, m.tech_rate?.rank, percent);
  document.getElementById("tm-top10-pct").textContent = formatWithRank(m.top10_win_pct?.value, m.top10_win_pct?.rank, percent);
  document.getElementById("tm-top33-pct").textContent = formatWithRank(m.top33_win_pct?.value, m.top33_win_pct?.rank, percent);
  
  // W/L Record
  const counts = metrics.counts || {};
  document.getElementById("tm-wl-record").textContent = formatWLRecord(
    counts.wins_included,
    counts.losses_included,
    counts.win_pct
  );

  // Advanced metrics
  const am = metrics.advanced_metrics;
  document.getElementById("tm-si-plus").textContent = formatWithRank(am.si_plus?.value, am.si_plus?.rank);
  document.getElementById("tm-df-plus").textContent = formatWithRank(am.df_plus?.value, am.df_plus?.rank);
  document.getElementById("tm-apr-plus").textContent = formatWithRank(am.apr_plus?.value, am.apr_plus?.rank);

  renderStartersTable(starters);
  renderRemainingRosterTable(remaining);
}

function renderStartersTable(starters) {
  const tbody = document.querySelector("#starting-roster-table tbody");
  tbody.innerHTML = "";

  starters.sort((a, b) => a.weight - b.weight);

  starters.forEach(({ weight, profile }) => {
    const tr = document.createElement("tr");

    const td = (v) => {
      const c = document.createElement("td");
      c.textContent = safe(v);
      tr.appendChild(c);
    };

    td(weight);

    const nameTd = document.createElement("td");
    const a = document.createElement("a");
    a.href = `/wrestler.html?id=${profile.wrestler_id}`;
    a.textContent = profile.name;
    nameTd.appendChild(a);
    tr.appendChild(nameTd);

    // Rank with badge
    const rankTd = document.createElement("td");
    rankTd.appendChild(createRankBadge(profile.current_rank));
    tr.appendChild(rankTd);
    
    // Record: use overall from record object
    const record = profile.record?.overall || "—";
    td(record);
    
    // Bonus Rate: read from profile.metrics.bonus_rate (already computed)
    const bonusRate = profile.metrics?.bonus_rate;
    td(bonusRate !== null && bonusRate !== undefined ? percent(bonusRate) : "—");
    
    // Advanced metrics (weight ranks not currently available in profiles)
    const siPlus = profile.metrics?.si_plus;
    td(siPlus !== null && siPlus !== undefined ? formatDecimal(siPlus, 1) : "—");
    
    const dfPlus = profile.metrics?.df_plus;
    td(dfPlus !== null && dfPlus !== undefined ? formatDecimal(dfPlus, 1) : "—");
    
    const aprPlus = profile.metrics?.apr_plus;
    td(aprPlus !== null && aprPlus !== undefined ? formatDecimal(aprPlus, 1) : "—");

    tbody.appendChild(tr);
  });
}

function renderRemainingRosterTable(remaining) {
  const tbody = document.querySelector("#remaining-roster-table tbody");
  tbody.innerHTML = "";

  // Sort by weight, then by name
  remaining.sort((a, b) => {
    const weightA = a.weight || 999;
    const weightB = b.weight || 999;
    if (weightA !== weightB) return weightA - weightB;
    return (a.profile.name || "").localeCompare(b.profile.name || "");
  });

  remaining.forEach(({ weight, profile }) => {
    const tr = document.createElement("tr");

    const td = (v) => {
      const c = document.createElement("td");
      c.textContent = safe(v);
      tr.appendChild(c);
    };

    td(weight || "—");

    const nameTd = document.createElement("td");
    const a = document.createElement("a");
    a.href = `/wrestler.html?id=${profile.wrestler_id}`;
    a.textContent = profile.name;
    nameTd.appendChild(a);
    tr.appendChild(nameTd);
    
    // Record: use overall from record object
    const record = profile.record?.overall || "—";
    td(record);
    
    // Bonus Rate: read from profile.metrics.bonus_rate (already computed)
    const bonusRate = profile.metrics?.bonus_rate;
    td(bonusRate !== null && bonusRate !== undefined ? percent(bonusRate) : "—");

    tbody.appendChild(tr);
  });
}

function createRankBadge(rank) {
  if (rank === null || rank === undefined || rank === "") {
    return document.createTextNode("—");
  }
  
  const badge = document.createElement("span");
  badge.className = "rank-badge";
  
  // Top 5 get accent color, others get muted
  if (rank <= 5) {
    badge.classList.add("top");
  } else {
    badge.classList.add("standard");
  }
  
  badge.textContent = `#${rank}`;
  return badge;
}

function createMetricBar(value, maxValue) {
  if (value === null || value === undefined || maxValue === 0) {
    return document.createTextNode("—");
  }
  
  // Cap width at 96%
  const width = Math.min((value / maxValue) * 100, 96);
  
  const bar = document.createElement("div");
  bar.className = "metric-bar";
  
  const fill = document.createElement("div");
  fill.className = "metric-bar-fill";
  fill.style.width = `${width}%`;
  
  const valueSpan = document.createElement("span");
  valueSpan.className = "metric-bar-value";
  valueSpan.textContent = value.toFixed(1);
  
  bar.appendChild(fill);
  bar.appendChild(valueSpan);
  return bar;
}

function renderXTPSection(xtpData, starters) {
  // Show section
  document.getElementById("xtp-section").style.display = "block";

  // Summary block
  document.getElementById("xtp-total").textContent = safe(xtpData.team_xTP, v => v.toFixed(1));
  document.getElementById("xtp-p").textContent = safe(xtpData.team_xTP_P, v => v.toFixed(1));
  document.getElementById("xtp-a").textContent = safe(xtpData.team_xTP_A, v => v.toFixed(1));
  document.getElementById("xtp-b").textContent = safe(xtpData.team_xTP_B, v => v.toFixed(1));

  // Per-weight breakdown table
  const tbody = document.querySelector("#xtp-breakdown-table tbody");
  tbody.innerHTML = "";

  // Sort weights ascending
  const weights = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285];
  
  // Calculate max values for bars
  let maxXTP = 0;
  let maxXTP_P = 0;
  let maxXTP_A = 0;
  let maxXTP_B = 0;
  let maxMV = 0;
  
  weights.forEach(weight => {
    const weightStr = String(weight);
    const weightData = xtpData.weights?.[weightStr];
    if (weightData) {
      if (weightData.xTP > maxXTP) maxXTP = weightData.xTP;
      if (weightData.xTP_P > maxXTP_P) maxXTP_P = weightData.xTP_P;
      if (weightData.xTP_A > maxXTP_A) maxXTP_A = weightData.xTP_A;
      if (weightData.xTP_B > maxXTP_B) maxXTP_B = weightData.xTP_B;
      
      const starterProfile = starters.find(s => s.weight === weight);
      if (starterProfile && starterProfile.profile.metrics?.mat_value?.mv_avg !== undefined) {
        const mv = starterProfile.profile.metrics.mat_value.mv_avg;
        if (mv > maxMV) maxMV = mv;
      }
    }
  });
  
  weights.forEach(weight => {
    const weightStr = String(weight);
    const weightData = xtpData.weights?.[weightStr];
    const tr = document.createElement("tr");

    // Weight
    const weightTd = document.createElement("td");
    weightTd.textContent = weight;
    tr.appendChild(weightTd);

    if (weightData && weightData.wrestler_id) {
      // Wrestler name (link)
      const wrestlerTd = document.createElement("td");
      wrestlerTd.className = "name";
      const wrestlerLink = document.createElement("a");
      wrestlerLink.href = `/wrestler.html?id=${weightData.wrestler_id}`;
      wrestlerLink.textContent = weightData.name || "Unknown";
      wrestlerTd.appendChild(wrestlerLink);
      tr.appendChild(wrestlerTd);

      // Rank with badge
      const rankTd = document.createElement("td");
      rankTd.appendChild(createRankBadge(weightData.rank));
      tr.appendChild(rankTd);

      // MV (from wrestler profile if available)
      const mvTd = document.createElement("td");
      mvTd.className = "num metric-primary";
      const starterProfile = starters.find(s => s.weight === weight);
      if (starterProfile && starterProfile.profile.metrics?.mat_value?.mv_avg !== undefined) {
        const mv = starterProfile.profile.metrics.mat_value.mv_avg;
        mvTd.appendChild(createMetricBar(mv, maxMV));
      } else {
        mvTd.textContent = "—";
      }
      tr.appendChild(mvTd);

      // xTP (total) - primary metric
      const xtpTd = document.createElement("td");
      xtpTd.className = "num metric-primary";
      xtpTd.appendChild(createMetricBar(weightData.xTP, maxXTP));
      tr.appendChild(xtpTd);

      // xTP_P - subcomponent
      const xtpPTd = document.createElement("td");
      xtpPTd.className = "num metric-sub";
      xtpPTd.appendChild(createMetricBar(weightData.xTP_P, maxXTP_P));
      tr.appendChild(xtpPTd);

      // xTP_A - subcomponent
      const xtpATd = document.createElement("td");
      xtpATd.className = "num metric-sub";
      xtpATd.appendChild(createMetricBar(weightData.xTP_A, maxXTP_A));
      tr.appendChild(xtpATd);

      // xTP_B - subcomponent
      const xtpBTd = document.createElement("td");
      xtpBTd.className = "num metric-sub";
      xtpBTd.appendChild(createMetricBar(weightData.xTP_B, maxXTP_B));
      tr.appendChild(xtpBTd);
    } else {
      // No qualifier
      const noQualTd = document.createElement("td");
      noQualTd.colSpan = 7;
      noQualTd.className = "no-qualifier";
      noQualTd.textContent = "No qualifier";
      tr.appendChild(noQualTd);
    }

    tbody.appendChild(tr);
  });
}

// Init
document.addEventListener("DOMContentLoaded", () => {
  const teamId = getQueryParam("team");
  if (!teamId) {
    document.getElementById("team-name").textContent = "No team selected";
    return;
  }
  loadTeam(teamId);
});