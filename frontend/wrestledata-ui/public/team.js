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
      // Handle both array and object with 'teams' property
      const teamsArray = Array.isArray(xtpFile) ? xtpFile : (xtpFile.teams || []);
      xtpData = teamsArray.find(t => t.team === teamName);
    } catch (err) {
      console.warn(`Could not load xTP data:`, err);
      // Continue without xTP data
    }

    await renderTeamPage(teamProfile, teamMetrics, starterProfiles, remainingProfiles, xtpData);
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

function calculateTopRecord(starters, maxRank) {
  let wins = 0;
  let losses = 0;
  
  starters.forEach(({ profile }) => {
    if (!profile || !profile.match_list) return;
    
    profile.match_list.forEach(match => {
      const opponentRank = match.opponent_rank;
      if (opponentRank === null || opponentRank === undefined || opponentRank > maxRank) {
        return;
      }
      
      const result = match.result || "";
      if (result === "W") {
        wins++;
      } else if (result === "L") {
        losses++;
      }
    });
  });
  
  return { wins, losses };
}

function formatTopRecord(record) {
  const { wins, losses } = record;
  const total = wins + losses;
  
  if (total === 0) {
    return "0–0 (—)";
  }
  
  const winPct = ((wins / total) * 100).toFixed(1);
  return `${wins}–${losses} (${winPct}%)`;
}

async function computeTeamRank(teamName, season) {
  try {
    const url = `/xtp/${season}/xtp_teams_${season}.json`;
    const data = await fetchJSON(url);
    
    // Handle both array and object with 'teams' property
    const teamsData = Array.isArray(data) ? data : (data.teams || []);
    
    // Sort teams: xTP desc, xTP_P desc, team name asc (same as leaderboard)
    const sorted = [...teamsData].sort((a, b) => {
      if (b.team_xTP !== a.team_xTP) return b.team_xTP - a.team_xTP;
      if (b.team_xTP_P !== a.team_xTP_P) return b.team_xTP_P - a.team_xTP_P;
      return a.team.localeCompare(b.team);
    });
    
    // Find team's rank
    const rank = sorted.findIndex(t => t.team === teamName) + 1;
    return rank > 0 ? rank : null;
  } catch (e) {
    console.warn("Could not compute team rank:", e);
    return null;
  }
}

function createMVRankBadge(rank) {
  if (rank === null || rank === undefined || rank === "") {
    return document.createTextNode("");
  }
  
  const badge = document.createElement("span");
  badge.className = "rank-badge";
  
  // Medal badge styling: #1 gold, #2 silver, #3-5 bronze, others neutral
  if (rank === 1) {
    badge.classList.add("medal-gold");
  } else if (rank === 2) {
    badge.classList.add("medal-silver");
  } else if (rank >= 3 && rank <= 5) {
    badge.classList.add("medal-bronze");
  } else {
    badge.classList.add("standard");
  }
  
  badge.textContent = `#${rank}`;
  return badge;
}

async function renderTeamPage(team, metrics, starters, remaining, xtpData) {
  // Header
  const teamName = team.team_name || team.name;
  document.getElementById("team-name").textContent = teamName;
  document.getElementById("team-meta").textContent =
    `${team.conference} · ${team.division}`;

  // xTP Headline (Primary Metric) - show only if data exists
  if (xtpData) {
    await renderXTPHeadline(xtpData, teamName);
    document.getElementById("starting-roster-section").style.display = "block";
  } else {
    document.getElementById("xtp-headline-section").style.display = "none";
    document.getElementById("starting-roster-section").style.display = "none";
  }

  // Team Profile Metrics (Supporting)
  const m = metrics.metrics;
  document.getElementById("tm-pf7").textContent = formatWithRank(m.avg_pf7?.value, m.avg_pf7?.rank, formatDecimal);
  document.getElementById("tm-pa7").textContent = formatWithRank(m.avg_pa7?.value, m.avg_pa7?.rank, formatDecimal);
  document.getElementById("tm-pd7").textContent = formatWithRank(m.avg_pd7?.value, m.avg_pd7?.rank, formatDecimal);
  document.getElementById("tm-bonus").textContent = formatWithRank(m.bonus_rate?.value, m.bonus_rate?.rank, percent);
  document.getElementById("tm-pin").textContent = formatWithRank(m.pin_rate?.value, m.pin_rate?.rank, percent);
  document.getElementById("tm-tech").textContent = formatWithRank(m.tech_rate?.value, m.tech_rate?.rank, percent);
  
  // Top-10 and Top-33 Records: Calculate from starter profiles
  const top10Record = calculateTopRecord(starters, 10);
  const top33Record = calculateTopRecord(starters, 33);
  document.getElementById("tm-top10-record").textContent = formatTopRecord(top10Record);
  document.getElementById("tm-top33-record").textContent = formatTopRecord(top33Record);
  
  // W/L Record
  const counts = metrics.counts || {};
  document.getElementById("tm-wl-record").textContent = formatWLRecord(
    counts.wins_included,
    counts.losses_included,
    counts.win_pct
  );

  // Advanced Metrics (Supporting)
  const am = metrics.advanced_metrics;
  document.getElementById("tm-si-plus").textContent = formatWithRank(am.si_plus?.value, am.si_plus?.rank);
  document.getElementById("tm-df-plus").textContent = formatWithRank(am.df_plus?.value, am.df_plus?.rank);
  document.getElementById("tm-apr-plus").textContent = formatWithRank(am.apr_plus?.value, am.apr_plus?.rank);

  renderStartersTable(starters, xtpData);
  renderRemainingRosterTable(remaining);
}

async function renderXTPHeadline(xtpData, teamName) {
  const section = document.getElementById("xtp-headline-section");
  section.style.display = "block";
  
  // Large xTP value
  const total = safe(xtpData.team_xTP, v => v.toFixed(1));
  const sign = xtpData.team_xTP >= 0 ? "+" : "";
  document.getElementById("xtp-total").textContent = `${sign}${total}`;
  
  // Rank badge (computed from leaderboard)
  const season = resolveSeason();
  const rank = await computeTeamRank(teamName, season);
  const rankBadgeContainer = document.getElementById("xtp-rank-badge");
  rankBadgeContainer.innerHTML = "";
  if (rank) {
    rankBadgeContainer.appendChild(createMVRankBadge(rank));
  }
  
  // Breakdown text
  document.getElementById("xtp-p").textContent = safe(xtpData.team_xTP_P, v => v.toFixed(1));
  document.getElementById("xtp-a").textContent = safe(xtpData.team_xTP_A, v => v.toFixed(1));
  document.getElementById("xtp-b").textContent = safe(xtpData.team_xTP_B, v => v.toFixed(1));
}

function resolveSeason() {
  return "2026"; // Or make dynamic later
}

function createMVRankBadge(rank) {
  if (rank === null || rank === undefined || rank === "") {
    return document.createTextNode("—");
  }
  
  const badge = document.createElement("span");
  badge.className = "rank-badge";
  
  // Medal badge styling: #1 gold, #2 silver, #3-5 bronze, others neutral
  if (rank === 1) {
    badge.classList.add("medal-gold");
  } else if (rank === 2) {
    badge.classList.add("medal-silver");
  } else if (rank >= 3 && rank <= 5) {
    badge.classList.add("medal-bronze");
  } else {
    badge.classList.add("standard");
  }
  
  badge.textContent = `#${rank}`;
  return badge;
}

function renderStartersTable(starters, xtpData) {
  const tbody = document.querySelector("#starting-roster-table tbody");
  tbody.innerHTML = "";

  starters.sort((a, b) => a.weight - b.weight);

  // Calculate max xTP for bar scaling (from this team's starters)
  let maxXTP = 0;
  starters.forEach(({ weight }) => {
    const weightStr = String(weight);
    const weightData = xtpData?.weights?.[weightStr];
    if (weightData && weightData.xTP !== null && weightData.xTP !== undefined) {
      if (weightData.xTP > maxXTP) maxXTP = weightData.xTP;
    }
  });

  starters.forEach(({ weight, profile }) => {
    const weightStr = String(weight);
    const weightData = xtpData?.weights?.[weightStr];
    const row = document.createElement("tr");
    row.className = "xtp-expanded-row";

    // Weight
    const weightTd = document.createElement("td");
    weightTd.textContent = weight;
    row.appendChild(weightTd);

    // Wrestler name (clickable) - always show if profile exists
    const wrestlerTd = document.createElement("td");
    if (profile && profile.wrestler_id) {
      const wrestlerLink = document.createElement("a");
      wrestlerLink.href = `/wrestler.html?id=${profile.wrestler_id}`;
      wrestlerLink.textContent = profile.name || "Unknown";
      wrestlerTd.appendChild(wrestlerLink);
    } else {
      wrestlerTd.textContent = "—";
    }
    row.appendChild(wrestlerTd);

    // Rank - medal badge (use weightData rank if available, otherwise profile rank)
    const rankTd = document.createElement("td");
    const rank = weightData?.rank ?? profile?.current_rank;
    if (rank !== null && rank !== undefined) {
      rankTd.appendChild(createMVRankBadge(rank));
    } else {
      rankTd.textContent = "—";
    }
    row.appendChild(rankTd);

    // MV - numeric value only (no bar, typographic thresholds) - always show if available
    const mvTd = document.createElement("td");
    mvTd.className = "num mv-value-cell";
    
    if (profile?.metrics?.mat_value?.mv_avg !== null && profile?.metrics?.mat_value?.mv_avg !== undefined) {
      const mv = profile.metrics.mat_value.mv_avg;
      const mvSpan = document.createElement("span");
      mvSpan.className = "mv-numeric";
      
      // Apply typographic thresholds
      if (mv >= 4.5) {
        mvSpan.classList.add("mv-high");
      } else if (mv >= 3.0) {
        mvSpan.classList.add("mv-mid");
      } else if (mv >= 0) {
        mvSpan.classList.add("mv-low");
      } else {
        // MV < 0: muted red, normal weight, slightly reduced opacity
        mvSpan.classList.add("mv-negative");
      }
      
      // Format with leading + for positive values
      const sign = mv >= 0 ? "+" : "";
      mvSpan.textContent = `${sign}${mv.toFixed(1)}`;
      
      // Add tooltip using tooltip system
      const tooltipText = `Mat Value: ${sign}${mv.toFixed(1)}. Per-match value above opponent expectation at ${weight} lbs.`;
      addTooltip(mvSpan, tooltipText);
      
      mvTd.appendChild(mvSpan);
    } else {
      mvTd.textContent = "—";
    }
    row.appendChild(mvTd);

    // xTP (total) - primary metric with bar (show "0" if no qualifier)
    const xtpTd = document.createElement("td");
    xtpTd.className = "num metric-primary expanded-xtp-cell";

    if (weightData && weightData.xTP !== null && weightData.xTP !== undefined && weightData.xTP > 0) {
      // Scale bars relative to max xTP in THIS team's starters
      xtpTd.appendChild(createMetricBar(weightData.xTP, maxXTP || 100.0));
    } else {
      // No qualifier - show "0"
      xtpTd.textContent = "0";
    }
    row.appendChild(xtpTd);

    // xTP_P - subcomponent (show "-" if no qualifier)
    const xtpPTd = document.createElement("td");
    xtpPTd.className = "num metric-sub expanded-component-col xtp-sub";
    if (weightData && weightData.xTP_P !== null && weightData.xTP_P !== undefined) {
      xtpPTd.textContent = weightData.xTP_P.toFixed(1);
    } else {
      xtpPTd.textContent = "—";
    }
    row.appendChild(xtpPTd);

    // xTP_A - subcomponent (show "-" if no qualifier)
    const xtpATd = document.createElement("td");
    xtpATd.className = "num metric-sub expanded-component-col xtp-sub";
    if (weightData && weightData.xTP_A !== null && weightData.xTP_A !== undefined) {
      xtpATd.textContent = weightData.xTP_A.toFixed(1);
    } else {
      xtpATd.textContent = "—";
    }
    row.appendChild(xtpATd);

    // xTP_B - subcomponent (show "-" if no qualifier)
    const xtpBTd = document.createElement("td");
    xtpBTd.className = "num metric-sub expanded-component-col xtp-sub";
    if (weightData && weightData.xTP_B !== null && weightData.xTP_B !== undefined) {
      xtpBTd.textContent = weightData.xTP_B.toFixed(1);
    } else {
      xtpBTd.textContent = "—";
    }
    row.appendChild(xtpBTd);

    tbody.appendChild(row);
  });
}

function renderRemainingRosterTable(remaining) {
  const tbody = document.querySelector("#remaining-roster-table tbody");
  tbody.innerHTML = "";

  // Sort: Weight asc, Bonus Rate desc, Wins desc
  remaining.sort((a, b) => {
    const weightA = a.weight || 999;
    const weightB = b.weight || 999;
    if (weightA !== weightB) return weightA - weightB;
    
    // Secondary: Bonus Rate desc
    const bonusA = a.profile.metrics?.bonus_rate ?? 0;
    const bonusB = b.profile.metrics?.bonus_rate ?? 0;
    if (bonusB !== bonusA) return bonusB - bonusA;
    
    // Tertiary: Wins desc (parse from record.overall)
    const parseWins = (profile) => {
      const overall = profile?.record?.overall;
      if (overall && typeof overall === "string") {
        const parts = overall.split("-");
        if (parts.length === 2) {
          return parseInt(parts[0], 10) || 0;
        }
      }
      return 0;
    };
    const winsA = parseWins(a.profile);
    const winsB = parseWins(b.profile);
    return winsB - winsA;
  });

  remaining.forEach(({ weight, profile }) => {
    const tr = document.createElement("tr");

    // Weight
    const weightTd = document.createElement("td");
    weightTd.textContent = weight || "—";
    tr.appendChild(weightTd);

    // Wrestler name (linked)
    const nameTd = document.createElement("td");
    if (profile && profile.wrestler_id) {
      const a = document.createElement("a");
      a.href = `/wrestler.html?id=${profile.wrestler_id}`;
      a.textContent = profile.name || "Unknown";
      nameTd.appendChild(a);
    } else {
      nameTd.textContent = "—";
    }
    tr.appendChild(nameTd);

    // Record: Format as "W–L" (no percentage)
    // Parse from record.overall string (format: "W-L") or calculate from match_list
    const recordTd = document.createElement("td");
    let wins = 0;
    let losses = 0;
    
    const overallRecord = profile?.record?.overall;
    if (overallRecord && typeof overallRecord === "string") {
      // Parse "W-L" format
      const parts = overallRecord.split("-");
      if (parts.length === 2) {
        wins = parseInt(parts[0], 10) || 0;
        losses = parseInt(parts[1], 10) || 0;
      }
    } else {
      // Fallback: count from match_list
      const matchList = profile?.match_list;
      if (matchList && Array.isArray(matchList)) {
        matchList.forEach(match => {
          const result = match.result || "";
          const isWin = result.includes("WIN") || result.includes("W");
          if (isWin) wins++;
          else if (result && !result.includes("MFF")) losses++;
        });
      }
    }
    
    recordTd.textContent = `${wins}–${losses}`;
    tr.appendChild(recordTd);
    
    // MV - numeric value only (no bar, typographic thresholds) - identical to Starting Roster
    const mvTd = document.createElement("td");
    mvTd.className = "num mv-value-cell";
    
    if (profile?.metrics?.mat_value?.mv_avg !== null && profile?.metrics?.mat_value?.mv_avg !== undefined) {
      const mv = profile.metrics.mat_value.mv_avg;
      const mvSpan = document.createElement("span");
      mvSpan.className = "mv-numeric";
      
      // Apply typographic thresholds
      if (mv >= 4.5) {
        mvSpan.classList.add("mv-high");
      } else if (mv >= 3.0) {
        mvSpan.classList.add("mv-mid");
      } else if (mv >= 0) {
        mvSpan.classList.add("mv-low");
      } else {
        // MV < 0: muted red, normal weight, slightly reduced opacity
        mvSpan.classList.add("mv-negative");
      }
      
      // Format with leading + for positive values
      const sign = mv >= 0 ? "+" : "";
      mvSpan.textContent = `${sign}${mv.toFixed(1)}`;
      
      // Add tooltip using tooltip system
      const tooltipText = `Mat Value: ${sign}${mv.toFixed(1)}. Per-match value above opponent expectation at ${weight} lbs.`;
      addTooltip(mvSpan, tooltipText);
      
      mvTd.appendChild(mvSpan);
    } else {
      mvTd.textContent = "—";
    }
    tr.appendChild(mvTd);
    
    // Bonus Rate: Display as percentage (e.g., 75.0%)
    const bonusTd = document.createElement("td");
    const bonusRate = profile?.metrics?.bonus_rate;
    if (bonusRate !== null && bonusRate !== undefined) {
      bonusTd.textContent = percent(bonusRate);
    } else {
      bonusTd.textContent = "0.0%";
    }
    tr.appendChild(bonusTd);

    // Matches Wrestled: Count from match_list if available
    const matchesTd = document.createElement("td");
    matchesTd.className = "num";
    const matchList = profile?.match_list;
    if (matchList && Array.isArray(matchList)) {
      matchesTd.textContent = matchList.length.toString();
    } else {
      // Fallback: calculate from wins + losses
      const totalMatches = wins + losses;
      matchesTd.textContent = totalMatches > 0 ? totalMatches.toString() : "0";
    }
    tr.appendChild(matchesTd);

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

// renderXTPSection removed - replaced by renderXTPHeadline

// Init
document.addEventListener("DOMContentLoaded", () => {
  const teamId = getQueryParam("team");
  if (!teamId) {
    document.getElementById("team-name").textContent = "No team selected";
    return;
  }
  loadTeam(teamId);
});