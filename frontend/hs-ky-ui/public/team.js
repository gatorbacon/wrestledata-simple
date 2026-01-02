function getQueryParam(key) {
  return new URLSearchParams(window.location.search).get(key);
}

// Helper function to check if we're on HS site
function isHSSite() {
  // Check if hs_config.js is loaded (HS site indicator)
  return typeof HS_CONFIG !== 'undefined';
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

// Note: hs_config.js must be loaded before this file

async function fetchJSON(url) {
  console.log(`[HS Team] Fetching: ${url}`);
  const res = await fetch(url);
  if (!res.ok) {
    const errorText = await res.text().catch(() => '');
    // Check if response is HTML (404 page)
    if (errorText.includes('<!doctype') || errorText.includes('<html')) {
      throw new Error(`Failed to load ${url}: Received HTML instead of JSON (likely 404)`);
    }
    throw new Error(`Failed to load ${url}: ${res.status} - ${res.statusText}`);
  }
  return res.json();
}

function normalizeTeamName(teamName) {
  // Normalize team name for comparison (case-insensitive, trim whitespace, normalize separators)
  if (!teamName) return '';
  return teamName.trim()
    .toLowerCase()
    .replace(/[^\w\s]/g, '') // Remove punctuation
    .replace(/\s+/g, '_'); // Convert spaces to underscores
}

async function loadTeam(teamSlug) {
  try {
    // Get gender from URL or default to boys
    const gender = getGenderFromURL();
    const season = getSeasonFromURL();
    const weights = getWeightsForGender(gender);
    
    console.log(`[HS Team] Loading team "${teamSlug}" for ${gender} ${season}...`);
    
    // 1) Load all weight files and aggregate wrestlers by team
    const allWrestlers = [];
    const wrestlersByWeight = {};
    
    for (const weight of weights) {
      try {
        const url = buildRankingsURL(gender, season, weight);
        const data = await fetchJSON(url);
        const wrestlers = data?.wrestlers || [];
        
        wrestlersByWeight[weight] = wrestlers;
        allWrestlers.push(...wrestlers.map(w => ({ ...w, weight })));
      } catch (err) {
        console.warn(`[HS Team] Could not load weight ${weight}:`, err);
        continue;
      }
    }
    
    if (allWrestlers.length === 0) {
      throw new Error(`No wrestlers found for ${gender} ${season}`);
    }
    
    // 2) Find team by matching slug (normalize team names)
    const normalizedSlug = normalizeTeamName(teamSlug);
    console.log(`[HS Team] Searching for team with normalized slug: "${normalizedSlug}"`);
    console.log(`[HS Team] Total wrestlers loaded: ${allWrestlers.length}`);
    
    // Get unique team names for debugging
    const uniqueTeams = [...new Set(allWrestlers.map(w => w.team))];
    console.log(`[HS Team] Found ${uniqueTeams.length} unique teams. Sample teams:`, uniqueTeams.slice(0, 10));
    
    const teamWrestlers = allWrestlers.filter(w => {
      const normalizedTeamName = normalizeTeamName(w.team);
      const matches = normalizedTeamName === normalizedSlug;
      
      if (matches) {
        console.log(`[HS Team] Match found: "${w.team}" (normalized: "${normalizedTeamName}") matches slug "${normalizedSlug}"`);
      }
      
      return matches;
    });
    
    if (teamWrestlers.length === 0) {
      // Try to find similar team names for better error message
      const similarTeams = uniqueTeams.filter(t => {
        const normalized = normalizeTeamName(t);
        return normalized.includes(normalizedSlug) || normalizedSlug.includes(normalized);
      });
      
      const errorMsg = similarTeams.length > 0
        ? `Team "${teamSlug}" not found. Did you mean: ${similarTeams.slice(0, 5).join(', ')}?`
        : `Team "${teamSlug}" not found in HS ${gender} rankings for season ${season}`;
      
      throw new Error(errorMsg);
    }
    
    // Get team name from first wrestler (most common name)
    const teamName = teamWrestlers[0].team;
    console.log(`[HS Team] Found ${teamWrestlers.length} ranked wrestlers for team "${teamName}"`);
    
    // 2.5) Load ALL wrestlers from index_teams.json (includes unranked wrestlers)
    let allWrestlerIds = new Set(teamWrestlers.map(w => String(w.wrestler_id)));
    let teamProfileData = null;
    
    try {
      // Load team profile for starters info
      const teamProfileUrl = `/data/teams/${gender}/${season}/${teamSlug}.json`;
      teamProfileData = await fetchJSON(teamProfileUrl);
      console.log(`[HS Team] Team profile loaded`);
    } catch (err) {
      console.warn(`[HS Team] Could not load team profile:`, err);
    }
    
    // Load full roster from index_teams.json
    try {
      const indexUrl = `/data/wrestlers/${gender}/${season}/index_teams.json`;
      const indexData = await fetchJSON(indexUrl);
      const teamEntry = indexData.find(t => normalizeTeamName(t.team_slug) === normalizedSlug);
      
      if (teamEntry && teamEntry.roster) {
        console.log(`[HS Team] Found roster in index: ${teamEntry.roster.length} wrestlers`);
        // Add all wrestler IDs from roster
        teamEntry.roster.forEach(id => {
          if (id && !id.startsWith('OUTSTATE_')) {
            allWrestlerIds.add(String(id));
          }
        });
      } else {
        console.warn(`[HS Team] Team not found in index_teams.json`);
      }
    } catch (err) {
      console.warn(`[HS Team] Could not load index_teams.json:`, err);
    }
    
    console.log(`[HS Team] Total unique wrestler IDs: ${allWrestlerIds.size}`);
    
    // Load all wrestler profiles
    const allTeamWrestlerProfiles = [];
    for (const wrestlerId of allWrestlerIds) {
      try {
        const profileUrl = `/data/wrestlers/${gender}/${season}/by_id/${wrestlerId}.json`;
        const profile = await fetchJSON(profileUrl);
        // Get weight from profile
        const weight = profile.weight_class;
        if (weight) {
          allTeamWrestlerProfiles.push({ weight, profile, wrestler_id: wrestlerId });
        }
      } catch (err) {
        // Skip if profile doesn't exist
        continue;
      }
    }
    
    console.log(`[HS Team] Total team wrestler profiles loaded: ${allTeamWrestlerProfiles.length}`);
    
    // 3) Build starting roster (best-ranked wrestler per weight)
    const startersByWeight = {};
    const starterProfiles = [];
    
    // Use team profile starters if available, otherwise use rankings
    if (teamProfileData?.roster?.starters) {
      // Use starters from team profile
      for (const [weightStr, wrestlerId] of Object.entries(teamProfileData.roster.starters)) {
        if (wrestlerId) {
          const weight = Number(weightStr);
          startersByWeight[weight] = String(wrestlerId);
          
          // Find profile
          const profileData = allTeamWrestlerProfiles.find(p => p.wrestler_id === String(wrestlerId));
          if (profileData) {
            starterProfiles.push({ weight, profile: profileData.profile });
          } else {
            // Try to load profile
            try {
              const profileUrl = `/data/wrestlers/${gender}/${season}/by_id/${wrestlerId}.json`;
              const profile = await fetchJSON(profileUrl);
              starterProfiles.push({ weight, profile });
            } catch (err) {
              console.warn(`[HS Team] Could not load starter profile for ${wrestlerId}`);
            }
          }
        }
      }
    } else {
      // Fallback: Group by weight and find best-ranked wrestler per weight
      const wrestlersByWeightGroup = {};
      teamWrestlers.forEach(w => {
        if (!wrestlersByWeightGroup[w.weight]) {
          wrestlersByWeightGroup[w.weight] = [];
        }
        wrestlersByWeightGroup[w.weight].push(w);
      });
      
      for (const [weightStr, weightWrestlers] of Object.entries(wrestlersByWeightGroup)) {
        const weight = Number(weightStr);
        // Sort by rank (lower is better)
        weightWrestlers.sort((a, b) => {
          const rankA = a.rank || 9999;
          const rankB = b.rank || 9999;
          return rankA - rankB;
        });
        
        const starter = weightWrestlers[0];
        startersByWeight[weight] = starter.wrestler_id;
        
        // Try to load full profile
        try {
          const profileUrl = `/data/wrestlers/${gender}/${season}/by_id/${starter.wrestler_id}.json`;
          const profile = await fetchJSON(profileUrl);
          starterProfiles.push({ weight, profile });
        } catch (err) {
          // Fallback: use ranking data as profile
          console.warn(`[HS Team] Could not load full profile for ${starter.wrestler_id}, using ranking data`);
          starterProfiles.push({ weight, profile: starter });
        }
      }
    }
    
    // 4) Build remaining roster (all other wrestlers)
    const starterIds = new Set(Object.values(startersByWeight).map(id => String(id)));
    
    // Debug logging
    console.log(`[HS Team] Total team wrestler profiles: ${allTeamWrestlerProfiles.length}`);
    console.log(`[HS Team] Starter IDs:`, Array.from(starterIds));
    console.log(`[HS Team] Starter IDs count: ${starterIds.size}`);
    
    const remainingProfiles = allTeamWrestlerProfiles.filter(({ wrestler_id }) => {
      const isStarter = starterIds.has(String(wrestler_id));
      if (!isStarter) {
        console.log(`[HS Team] Remaining wrestler: ${wrestler_id}`);
      }
      return !isStarter;
    });
    
    console.log(`[HS Team] Remaining profiles count: ${remainingProfiles.length}`);
    
    console.log(`[HS Team] Remaining profiles built: ${remainingProfiles.length}`);
    
    // 5) Load team metrics (HS path)
    let teamMetrics = null;
    try {
      const metricsUrl = `/data/team_metrics/${gender}/${season}/team_metrics.json`;
      const metricsData = await fetchJSON(metricsUrl);
      const teams = metricsData?.teams || [];
      
      // Match by team_id (slug format like "grant_county")
      teamMetrics = teams.find(t => {
        if (t.team_id) {
          const normalizedTeamId = normalizeTeamName(t.team_id);
          if (normalizedTeamId === normalizedSlug) {
            return true;
          }
        }
        // Fallback: match by team_name
        const normalizedTeamName = normalizeTeamName(t.team_name || t.team);
        return normalizedTeamName === normalizedSlug;
      });
      
      if (!teamMetrics) {
        console.warn(`[HS Team] No metrics found for team "${teamName}" (slug: "${normalizedSlug}")`);
        console.log(`[HS Team] Available team_ids (sample):`, teams.slice(0, 5).map(t => t.team_id));
      } else {
        console.log(`[HS Team] Found metrics for team "${teamMetrics.team_name || teamMetrics.team}"`);
      }
    } catch (err) {
      console.warn(`[HS Team] Could not load team metrics:`, err);
    }
    
    // 6) Load xTP data (HS path)
    let xtpData = null;
    try {
      const xtpUrl = buildXTPURL(gender, season);
      const xtpFile = await fetchJSON(xtpUrl);
      const teamsArray = Array.isArray(xtpFile) ? xtpFile : (xtpFile.teams || []);
      // Match by team name (xTP uses team name, not team_id)
      xtpData = teamsArray.find(t => normalizeTeamName(t.team) === normalizedSlug || normalizeTeamName(t.team) === normalizeTeamName(teamName));
      
      if (!xtpData) {
        console.warn(`[HS Team] No xTP data found for team "${teamName}" (slug: "${normalizedSlug}")`);
      } else {
        console.log(`[HS Team] Found xTP data for team "${xtpData.team}"`);
      }
    } catch (err) {
      console.warn(`[HS Team] Could not load xTP data:`, err);
    }
    
    // 7) Create synthetic team profile object
    const teamProfile = {
      team_name: teamName,
      name: teamName,
      conference: 'Kentucky High School',
      division: gender === 'boys' ? 'KY HS Boys' : 'KY HS Girls',
      roster: {
        starters: startersByWeight
      }
    };
    
    await renderTeamPage(teamProfile, teamMetrics, starterProfiles, remainingProfiles, xtpData);
  } catch (err) {
    console.error(`[HS Team] Error loading team:`, err);
    document.getElementById("team-name").textContent = "Team Not Found";
    document.getElementById("team-meta").textContent = err.message || "Team not found in HS rankings";
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
    const gender = getGenderFromURL();
    const url = buildXTPURL(gender, season);
    const data = await fetchJSON(url);
    
    // Handle both array and object with 'teams' property
    const teamsData = Array.isArray(data) ? data : (data.teams || []);
    
    // Sort teams: xTP desc, xTP_P desc, team name asc (same as leaderboard)
    const sorted = [...teamsData].sort((a, b) => {
      if (b.team_xTP !== a.team_xTP) return b.team_xTP - a.team_xTP;
      if (b.team_xTP_P !== a.team_xTP_P) return b.team_xTP_P - a.team_xTP_P;
      return a.team.localeCompare(b.team);
    });
    
    // Find team's rank (normalize team names for comparison)
    const normalizedTeamName = normalizeTeamName(teamName);
    const rank = sorted.findIndex(t => normalizeTeamName(t.team) === normalizedTeamName) + 1;
    return rank > 0 ? rank : null;
  } catch (e) {
    console.warn("[HS Team] Could not compute team rank:", e);
    return null;
  }
}

// Render Team Profile metrics (extracted for reuse)
function renderTeamProfileMetrics(metrics, starters, isHS) {
  if (metrics && metrics.metrics) {
    const m = metrics.metrics;
    
    // Hide Points Scored/Allowed/Differential column for HS
    const col1 = document.querySelector("#team-profile-metrics-section .metrics-column:first-child");
    if (col1) {
      col1.style.display = isHS ? "none" : "block";
    }
    
    // Update grid layout for HS (2 columns instead of 3)
    const metricsGrid = document.querySelector("#team-profile-metrics-section .metrics-grid");
    if (metricsGrid) {
      if (isHS) {
        metricsGrid.classList.remove("metrics-grid--three-columns");
        metricsGrid.classList.add("metrics-grid--two-columns");
      } else {
        metricsGrid.classList.remove("metrics-grid--two-columns");
        metricsGrid.classList.add("metrics-grid--three-columns");
      }
    }
    
    // Always set these (they'll be hidden via CSS for HS)
    document.getElementById("tm-pf7").textContent = formatWithRank(m.avg_pf7?.value, m.avg_pf7?.rank, formatDecimal);
    document.getElementById("tm-pa7").textContent = formatWithRank(m.avg_pa7?.value, m.avg_pa7?.rank, formatDecimal);
    document.getElementById("tm-pd7").textContent = formatWithRank(m.avg_pd7?.value, m.avg_pd7?.rank, formatDecimal);
    
    document.getElementById("tm-bonus").textContent = formatWithRank(m.bonus_rate?.value, m.bonus_rate?.rank, percent);
    document.getElementById("tm-pin").textContent = formatWithRank(m.pin_rate?.value, m.pin_rate?.rank, percent);
    document.getElementById("tm-tech").textContent = formatWithRank(m.tech_rate?.value, m.tech_rate?.rank, percent);
    
    // W/L Record
    const counts = metrics.counts || {};
    document.getElementById("tm-wl-record").textContent = formatWLRecord(
      counts.wins_included,
      counts.losses_included,
      counts.win_pct
    );

    // Advanced Metrics (Supporting) - only for NCAA
    if (!isHS) {
      const am = metrics.advanced_metrics || {};
      document.getElementById("tm-si-plus").textContent = formatWithRank(am.si_plus?.value, am.si_plus?.rank);
      document.getElementById("tm-df-plus").textContent = formatWithRank(am.df_plus?.value, am.df_plus?.rank);
      document.getElementById("tm-apr-plus").textContent = formatWithRank(am.apr_plus?.value, am.apr_plus?.rank);
    }
  } else {
    // Show "—" for all metrics if not available
    document.getElementById("tm-pf7").textContent = "—";
    document.getElementById("tm-pa7").textContent = "—";
    document.getElementById("tm-pd7").textContent = "—";
    document.getElementById("tm-bonus").textContent = "—";
    document.getElementById("tm-pin").textContent = "—";
    document.getElementById("tm-tech").textContent = "—";
    document.getElementById("tm-wl-record").textContent = "—";
    if (!isHS) {
      document.getElementById("tm-si-plus").textContent = "—";
      document.getElementById("tm-df-plus").textContent = "—";
      document.getElementById("tm-apr-plus").textContent = "—";
    }
  }
  
  // Top-10 and Top-33 Records: Calculate from starter profiles
  const top10Record = calculateTopRecord(starters, 10);
  const top33Record = calculateTopRecord(starters, 33);
  document.getElementById("tm-top10-record").textContent = formatTopRecord(top10Record);
  document.getElementById("tm-top33-record").textContent = formatTopRecord(top33Record);
}

// Render top summary row (Team Profile + xTP) for HS
async function renderTopSummaryRow(metrics, starters, xtpData, teamName) {
  // Create or get the top summary container
  let topSummaryContainer = document.getElementById("top-summary-row");
  if (!topSummaryContainer) {
    topSummaryContainer = document.createElement("div");
    topSummaryContainer.id = "top-summary-row";
    topSummaryContainer.className = "team-summary-row";
    topSummaryContainer.style.cssText = "display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 2em;";
    
    // Insert after header, before starting roster
    const header = document.querySelector("header");
    const startingRosterSection = document.getElementById("starting-roster-section");
    header.parentNode.insertBefore(topSummaryContainer, startingRosterSection);
  }
  
  topSummaryContainer.innerHTML = "";
  
  // Render metrics first to populate the values
  renderTeamProfileMetrics(metrics, starters, true);
  
  // LEFT COLUMN: Team Profile Stats
  const leftCol = document.createElement("div");
  leftCol.className = "team-profile-summary";
  
  const leftHeader = document.createElement("h3");
  leftHeader.className = "metrics-section-title";
  leftHeader.textContent = "Team Overview";
  leftCol.appendChild(leftHeader);
  
  const leftGrid = document.createElement("div");
  leftGrid.className = "metrics-grid metrics-grid--two-columns";
  leftGrid.style.cssText = "display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 24px; margin-bottom: 0;";
  
  // Create metric items dynamically
  const createMetricItem = (label, valueId, value) => {
    const item = document.createElement("div");
    item.className = "metric-item";
    const labelSpan = document.createElement("span");
    labelSpan.className = "metric-label";
    labelSpan.textContent = label;
    const valueSpan = document.createElement("span");
    valueSpan.className = "metric-value";
    valueSpan.id = valueId;
    valueSpan.textContent = value || "—";
    item.appendChild(labelSpan);
    item.appendChild(valueSpan);
    return item;
  };
  
  // Add metrics to grid
  const col1 = document.createElement("div");
  col1.className = "metrics-column";
  col1.appendChild(createMetricItem("W–L Record", "tm-wl-record-top", document.getElementById("tm-wl-record")?.textContent || "—"));
  col1.appendChild(createMetricItem("Top-33 Record", "tm-top33-record-top", document.getElementById("tm-top33-record")?.textContent || "—"));
  col1.appendChild(createMetricItem("Top-10 Record", "tm-top10-record-top", document.getElementById("tm-top10-record")?.textContent || "—"));
  
  const col2 = document.createElement("div");
  col2.className = "metrics-column";
  col2.appendChild(createMetricItem("Bonus Rate", "tm-bonus-top", document.getElementById("tm-bonus")?.textContent || "—"));
  col2.appendChild(createMetricItem("Pin Rate", "tm-pin-top", document.getElementById("tm-pin")?.textContent || "—"));
  col2.appendChild(createMetricItem("Tech Fall Rate", "tm-tech-top", document.getElementById("tm-tech")?.textContent || "—"));
  
  leftGrid.appendChild(col1);
  leftGrid.appendChild(col2);
  leftCol.appendChild(leftGrid);
  
  // RIGHT COLUMN: xTP Headline
  const rightCol = document.createElement("div");
  rightCol.className = "xtp-headline-summary";
  
  if (xtpData) {
    await renderXTPHeadline(xtpData, teamName);
    const xtpSection = document.getElementById("xtp-headline-section");
    if (xtpSection) {
      // Clone the xTP content
      const xtpClone = xtpSection.cloneNode(true);
      xtpClone.style.display = "block";
      rightCol.appendChild(xtpClone);
    }
  } else {
    const noXTP = document.createElement("div");
    noXTP.textContent = "xTP data not available";
    noXTP.style.cssText = "color: var(--muted); padding: 2em; text-align: center;";
    rightCol.appendChild(noXTP);
  }
  
  topSummaryContainer.appendChild(leftCol);
  topSummaryContainer.appendChild(rightCol);
}

async function renderTeamPage(team, metrics, starters, remaining, xtpData) {
  const isHS = isHSSite();
  
  // Header
  const teamName = team.team_name || team.name;
  const gender = getGenderFromURL();
  document.getElementById("team-name").textContent = teamName;
  document.getElementById("team-meta").textContent =
    `${team.conference} · ${team.division} · Season ${getSeasonFromURL()}`;

  // Update section header for HS
  const startingRosterHeader = document.querySelector("#starting-roster-section h2");
  if (startingRosterHeader) {
    if (isHS) {
      startingRosterHeader.textContent = "Projected State Tournament Lineup";
    } else {
      startingRosterHeader.textContent = "Starting Roster";
    }
  }

  // Create top summary row (Team Profile stats + xTP) for HS
  if (isHS) {
    await renderTopSummaryRow(metrics, starters, xtpData, teamName);
    // Hide old Team Profile section for HS (we moved it to top)
    const oldTeamProfileSection = document.getElementById("team-profile-metrics-section");
    if (oldTeamProfileSection) {
      oldTeamProfileSection.style.display = "none";
    }
    // Hide xTP headline section (we moved it to top summary)
    document.getElementById("xtp-headline-section").style.display = "none";
  } else {
    // NCAA: show xTP headline separately
    if (xtpData) {
      await renderXTPHeadline(xtpData, teamName);
      document.getElementById("xtp-headline-section").style.display = "block";
    } else {
      document.getElementById("xtp-headline-section").style.display = "none";
    }
    
    // Render Team Profile metrics in original location
    renderTeamProfileMetrics(metrics, starters, isHS);
  }
  
  // Always show starting roster section (even without xTP data)
  document.getElementById("starting-roster-section").style.display = "block";
  
  // Hide Advanced Metrics section for HS
  const advancedMetricsSection = document.getElementById("advanced-metrics-section");
  if (advancedMetricsSection) {
    advancedMetricsSection.style.display = isHS ? "none" : "block";
  }

  renderStartersTable(starters, xtpData);
  
  // Debug: Log remaining roster before rendering
  console.log(`[HS Team] About to render remaining roster. remaining parameter:`, remaining);
  console.log(`[HS Team] remaining type: ${typeof remaining}, isArray: ${Array.isArray(remaining)}`);
  if (remaining) {
    console.log(`[HS Team] remaining.length: ${remaining.length}`);
    if (remaining.length > 0) {
      console.log(`[HS Team] First remaining wrestler:`, remaining[0]);
    }
  }
  
  renderRemainingRosterTable(remaining);
}

async function renderXTPHeadline(xtpData, teamName) {
  const section = document.getElementById("xtp-headline-section");
  section.style.display = "block";
  
  const isHS = isHSSite();
  
  // Update label for HS
  const labelEl = document.querySelector(".xtp-headline-label");
  if (labelEl) {
    if (isHS) {
      labelEl.textContent = "Projected State Tournament Points";
    } else {
      labelEl.textContent = "Projected NCAA Team Points";
    }
  }
  
  // Add disclaimer for HS (if not already present)
  if (isHS) {
    let disclaimerEl = document.getElementById("xtp-disclaimer");
    if (!disclaimerEl) {
      disclaimerEl = document.createElement("div");
      disclaimerEl.id = "xtp-disclaimer";
      disclaimerEl.style.cssText = "font-size: 0.75rem; color: var(--muted); margin-top: 8px; font-style: italic;";
      disclaimerEl.textContent = "Projected points based on estimated state tournament advancement.";
      const breakdownEl = document.querySelector(".xtp-headline-breakdown");
      if (breakdownEl) {
        breakdownEl.parentNode.insertBefore(disclaimerEl, breakdownEl.nextSibling);
      }
    }
  } else {
    // Remove disclaimer for NCAA
    const disclaimerEl = document.getElementById("xtp-disclaimer");
    if (disclaimerEl) {
      disclaimerEl.remove();
    }
  }
  
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
  const isHS = isHSSite();
  const tbody = document.querySelector("#starting-roster-table tbody");
  tbody.innerHTML = "";

  // Hide TPAR column header for HS
  const table = document.getElementById("starting-roster-table");
  if (table) {
    const headerRow = table.querySelector("thead tr");
    if (headerRow) {
      const headers = headerRow.querySelectorAll("th");
      headers.forEach((th, index) => {
        if (th.textContent.trim() === "TPAR" || th.getAttribute("data-tooltip") === "mv") {
          th.style.display = isHS ? "none" : "";
        }
      });
    }
  }

  if (!starters || starters.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    // Adjust colspan based on HS (7 columns without TPAR) vs NCAA (8 columns with TPAR)
    cell.colSpan = isHS ? 7 : 8;
    cell.textContent = "No starters found";
    cell.style.textAlign = "center";
    cell.style.padding = "2em";
    cell.style.color = "var(--muted)";
    row.appendChild(cell);
    tbody.appendChild(row);
    console.warn("[HS Team] No starters to render");
    return;
  }

  console.log(`[HS Team] Rendering ${starters.length} starters`);
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
    const gender = getGenderFromURL();
    if (profile && profile.wrestler_id) {
      const wrestlerLink = document.createElement("a");
      wrestlerLink.href = buildPageURL('wrestler.html', gender, { id: profile.wrestler_id });
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

    // MV/TPAR - only show for NCAA, hide for HS
    if (!isHS) {
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
        const tooltipText = `TPAR: ${sign}${mv.toFixed(1)}. Team Points Above Replacement relative to a replacement-level Division I starter at ${weight} lbs.`;
        addTooltip(mvSpan, tooltipText);
        
        mvTd.appendChild(mvSpan);
      } else {
        mvTd.textContent = "—";
      }
      row.appendChild(mvTd);
    }

    // xTP (total) - primary metric with bar (show "0" if no qualifier)
    const xtpTd = document.createElement("td");
    xtpTd.className = "num metric-primary expanded-xtp-cell";
    xtpTd.style.cssText = "padding: 6px 12px;";

    if (weightData && weightData.xTP !== null && weightData.xTP !== undefined && weightData.xTP > 0) {
      // Scale bars relative to max xTP in THIS team's starters
      xtpTd.appendChild(createMetricBar(weightData.xTP, maxXTP || 100.0));
    } else {
      // No qualifier - show "0" with same layout
      const zeroWrapper = document.createElement("div");
      zeroWrapper.className = "xtp-bar-wrapper";
      zeroWrapper.style.cssText = "display: flex; align-items: center; gap: 8px; width: 100%;";
      const zeroValue = document.createElement("span");
      zeroValue.className = "xtp-value-text";
      zeroValue.style.cssText = "color: #111; font-weight: 600; min-width: 45px; text-align: right; font-variant-numeric: tabular-nums;";
      zeroValue.textContent = "0";
      zeroWrapper.appendChild(zeroValue);
      xtpTd.appendChild(zeroWrapper);
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

  // Debug logging
  console.log(`[HS Team] renderRemainingRosterTable called with:`, remaining);
  console.log(`[HS Team] remaining is array: ${Array.isArray(remaining)}`);
  console.log(`[HS Team] remaining length: ${remaining ? remaining.length : 'null/undefined'}`);

  if (!remaining || remaining.length === 0) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.textContent = "No remaining roster";
    cell.style.textAlign = "center";
    cell.style.padding = "2em";
    cell.style.color = "var(--muted)";
    row.appendChild(cell);
    tbody.appendChild(row);
    console.log("[HS Team] No remaining roster to render - array is empty or null");
    return;
  }

  console.log(`[HS Team] Rendering ${remaining.length} remaining roster members`);

  // Helper function to parse wins/losses from record
  const parseRecord = (profile) => {
    const overall = profile?.record?.overall;
    if (overall && typeof overall === "string") {
      const parts = overall.split("-");
      if (parts.length === 2) {
        return {
          wins: parseInt(parts[0], 10) || 0,
          losses: parseInt(parts[1], 10) || 0
        };
      }
    }
    // Fallback: count from match_list
    let wins = 0;
    let losses = 0;
    const matchList = profile?.match_list;
    if (matchList && Array.isArray(matchList)) {
      matchList.forEach(match => {
        const result = match.result || "";
        const isWin = result.includes("WIN") || result.includes("W");
        if (isWin) wins++;
        else if (result && !result.includes("MFF")) losses++;
      });
    }
    return { wins, losses };
  };

  // Helper function to count Top 25 wins
  const countTop25Wins = (profile) => {
    const matchList = profile?.match_list || [];
    let top25Wins = 0;
    matchList.forEach(match => {
      const opponentRank = match.opponent_rank;
      const result = match.result || "";
      const isWin = result.includes("WIN") || result.includes("W");
      if (isWin && opponentRank !== null && opponentRank !== undefined && opponentRank <= 25) {
        top25Wins++;
      }
    });
    return top25Wins;
  };

  // Sort: Non-zero records first (by weight), then 0-0 records (by weight)
  remaining.sort((a, b) => {
    const recordA = parseRecord(a.profile);
    const recordB = parseRecord(b.profile);
    const isZeroA = recordA.wins === 0 && recordA.losses === 0;
    const isZeroB = recordB.wins === 0 && recordB.losses === 0;
    
    // Separate 0-0 records from non-zero records
    if (isZeroA !== isZeroB) {
      return isZeroA ? 1 : -1; // Non-zero records first
    }
    
    // Within each group, sort by weight
    const weightA = a.weight || 999;
    const weightB = b.weight || 999;
    if (weightA !== weightB) return weightA - weightB;
    
    // Secondary: Bonus Rate desc
    const bonusA = a.profile.metrics?.bonus_rate ?? 0;
    const bonusB = b.profile.metrics?.bonus_rate ?? 0;
    if (bonusB !== bonusA) return bonusB - bonusA;
    
    // Tertiary: Wins desc
    return recordB.wins - recordA.wins;
  });

  // Separate 0-0 records from non-zero records for rendering
  const nonZeroRecords = [];
  const zeroRecords = [];
  
  remaining.forEach(item => {
    const record = parseRecord(item.profile);
    if (record.wins === 0 && record.losses === 0) {
      zeroRecords.push(item);
    } else {
      nonZeroRecords.push(item);
    }
  });
  
  // Render non-zero records first
  [...nonZeroRecords, ...zeroRecords].forEach(({ weight, profile }) => {
    const record = parseRecord(profile);
    const isZeroRecord = record.wins === 0 && record.losses === 0;
    
    const tr = document.createElement("tr");
    
    // Apply grey styling to 0-0 records
    if (isZeroRecord) {
      tr.classList.add("zero-record");
    }

    // Weight
    const weightTd = document.createElement("td");
    weightTd.textContent = weight || "—";
    tr.appendChild(weightTd);

    // Wrestler name (linked)
    const nameTd = document.createElement("td");
    const gender = getGenderFromURL();
    if (profile && profile.wrestler_id) {
      const a = document.createElement("a");
      a.href = buildPageURL('wrestler.html', gender, { id: profile.wrestler_id });
      a.textContent = profile.name || "Unknown";
      nameTd.appendChild(a);
    } else {
      nameTd.textContent = "—";
    }
    tr.appendChild(nameTd);

    // Record: Format as "W–L"
    const recordTd = document.createElement("td");
    recordTd.textContent = `${record.wins}–${record.losses}`;
    tr.appendChild(recordTd);
    
    // Top 25 Wins
    const top25Td = document.createElement("td");
    top25Td.className = "num";
    const top25Wins = countTop25Wins(profile);
    top25Td.textContent = top25Wins > 0 ? String(top25Wins) : "—";
    tr.appendChild(top25Td);
    
    // Bonus Rate: Display as percentage (e.g., 75.0%)
    const bonusTd = document.createElement("td");
    const bonusRate = profile?.metrics?.bonus_rate;
    if (bonusRate !== null && bonusRate !== undefined) {
      bonusTd.textContent = percent(bonusRate);
    } else {
      bonusTd.textContent = "0.0%";
    }
    tr.appendChild(bonusTd);

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
  
  // Create wrapper container with two parts: value + bar
  const wrapper = document.createElement("div");
  wrapper.className = "xtp-bar-wrapper";
  wrapper.style.cssText = "display: flex; align-items: center; gap: 8px; width: 100%;";
  
  // Numeric value (outside bar, left-aligned)
  const valueSpan = document.createElement("span");
  valueSpan.className = "xtp-value-text";
  valueSpan.style.cssText = "color: #111; font-weight: 600; min-width: 45px; text-align: right; font-variant-numeric: tabular-nums;";
  valueSpan.textContent = value.toFixed(1);
  wrapper.appendChild(valueSpan);
  
  // Bar container (visual only, no text)
  const bar = document.createElement("div");
  bar.className = "metric-bar";
  bar.style.cssText = "flex: 1; position: relative; height: 12px; background: #e9e9e9; border-radius: 0;";
  
  // Cap width at 96%
  const width = Math.min((value / maxValue) * 100, 96);
  
  const fill = document.createElement("div");
  fill.className = "metric-bar-fill";
  fill.style.cssText = `position: absolute; left: 0; top: 0; bottom: 0; width: ${width}%; background: var(--accent-primary); opacity: 0.75; border-radius: 0;`;
  
  bar.appendChild(fill);
  wrapper.appendChild(bar);
  
  return wrapper;
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