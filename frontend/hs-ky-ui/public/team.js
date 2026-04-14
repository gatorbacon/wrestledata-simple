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
  if (formatter) return formatter(value);
  return typeof value === "number" ? Number(value).toFixed(1) : String(value);
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
    
    console.log(`[HS Team] Loading team "${teamSlug}" for ${gender} ${season}...`);
    
    // Load team profile JSON (contains all required data)
    const teamProfileUrl = `/data/teams/${gender}/${season}/${teamSlug}.json`;
    const teamProfileData = await fetchJSON(teamProfileUrl);
    console.log(`[HS Team] Team profile loaded`);
    
    const teamName = teamProfileData.team_name || teamProfileData.name;
    
    // Check if team profile has new minimal structure (schema_version 2.0+ with starters/remaining)
    if (teamProfileData.starters && teamProfileData.remaining !== undefined) {
      // New structure: Extract starters and remaining from team profile
      console.log(`[HS Team] Using new minimal team profile structure`);
      
      const starterProfiles = [];
      const startersByWeight = {};
      
      // Build starter profiles from minimal data
      for (const [weightStr, starterData] of Object.entries(teamProfileData.starters)) {
        if (starterData) {
          const weight = Number(weightStr);
          startersByWeight[weight] = starterData.wrestler_id;
          
          // Convert minimal starter data to profile-like object for compatibility
          starterProfiles.push({
            weight,
            profile: {
              wrestler_id: starterData.wrestler_id,
              name: starterData.name,
              weight_class: starterData.weight,
              current_rank: starterData.current_rank,
              // Add precomputed records for calculateTopRecord compatibility
              match_list: [], // Empty - records are precomputed
              record: {
                overall: `${starterData.wins || 0}-${starterData.losses || 0}`,
              },
              // Add top10/top33 records as metadata
              _top10_record: starterData.top10_record,
              _top33_record: starterData.top33_record,
              // Add precomputed top25_wins and bonus_rate
              _top25_wins: starterData.top25_wins,
              metrics: {
                bonus_rate: starterData.bonus_rate,
              },
              // Add grade for display
              grade: starterData.grade,
              // Add embedded xTP data for renderStartersTable
              _xtp_data: {
                xTP: starterData.xtp,
                xTP_P: starterData.xtp_p,
                xTP_A: starterData.xtp_a,
                xTP_B: starterData.xtp_b,
                xTP_simple: starterData.xtp_simple,  // Simplified rank-based scoring
                rank: starterData.current_rank,
              },
            }
          });
        }
      }
      
      // Build remaining roster from minimal data
      const remainingProfiles = teamProfileData.remaining.map(rosterData => ({
        weight: rosterData.weight,
        profile: {
          wrestler_id: rosterData.wrestler_id,
          name: rosterData.name,
          weight_class: rosterData.weight,
          grade: rosterData.grade,  // Add grade for display
          record: {
            overall: `${rosterData.wins}-${rosterData.losses}`,
          },
          metrics: {
            bonus_rate: rosterData.bonus_rate,
          },
          // Add precomputed top25_wins for countTop25Wins compatibility
          _top25_wins: rosterData.top25_wins,
          match_list: [], // Empty - top25_wins is precomputed
        }
      }));
      
      // Load xTP data if not embedded
      let xtpData = teamProfileData.xtp_summary || null;
      let xtpRank = null;
      let fullXtpData = null; // Cache full xTP data for rank computation
      
      if (!xtpData) {
        try {
          const xtpUrl = `/data/xtp/${gender}/${season}/xtp_teams_${season}.json`;
          fullXtpData = await fetchJSON(xtpUrl);
          // Find this team's data
          const teamsArray = Array.isArray(fullXtpData) ? fullXtpData : fullXtpData.teams || [];
          xtpData = teamsArray.find(t => normalizeTeamName(t.team) === normalizeTeamName(teamName)) || null;
          
          // Compute rank from the full xTP data we just loaded
          if (fullXtpData && xtpData) {
            xtpRank = computeTeamRankFromData(teamName, teamsArray);
          }
        } catch (err) {
          console.warn(`[HS Team] Could not load xTP data:`, err);
        }
      } else {
        // If xTP data is embedded, we still need to load full data for rank computation
        try {
          const xtpUrl = `/data/xtp/${gender}/${season}/xtp_teams_${season}.json`;
          fullXtpData = await fetchJSON(xtpUrl);
          const teamsArray = Array.isArray(fullXtpData) ? fullXtpData : fullXtpData.teams || [];
          xtpRank = computeTeamRankFromData(teamName, teamsArray);
        } catch (err) {
          console.warn(`[HS Team] Could not load xTP data for rank computation:`, err);
        }
      }
      
      // Load team metrics if not embedded
      let teamMetrics = teamProfileData.team_metrics || null;
      if (!teamMetrics) {
        try {
          const metricsUrl = `/data/team_metrics/${gender}/${season}/team_metrics.json`;
          const metricsData = await fetchJSON(metricsUrl);
          const teamsArray = metricsData.teams || [];
          teamMetrics = teamsArray.find(t => 
            normalizeTeamName(t.team_name || t.team) === normalizeTeamName(teamName)
          ) || null;
        } catch (err) {
          console.warn(`[HS Team] Could not load team metrics:`, err);
        }
      }
      
      // Create synthetic team profile object for renderTeamPage
      const teamProfile = {
        team_name: teamName,
        name: teamName,
        conference: teamProfileData.location?.region ? `Region ${teamProfileData.location.region}` : 'Kentucky High School',
        division: gender === 'boys' ? 'KY HS Boys' : 'KY HS Girls',
        roster: {
          starters: startersByWeight
        }
      };
      
      // Wrap teamMetrics in expected format for renderTeamProfileMetrics
      // It expects metrics.metrics structure, but we have flat team_metrics
      let wrappedMetrics = null;
      if (teamMetrics) {
        // If teamMetrics already has the expected structure, use it
        if (teamMetrics.metrics) {
          wrappedMetrics = teamMetrics;
        } else {
          // Wrap flat structure
          // Extract wins/losses from overall object (set by build_team_profiles.py)
          const overallWins = teamMetrics.overall?.wins;
          const overallLosses = teamMetrics.overall?.losses;
          
          wrappedMetrics = {
            metrics: teamMetrics,
            counts: {
              wins_included: overallWins !== null && overallWins !== undefined ? overallWins : 0,
              losses_included: overallLosses !== null && overallLosses !== undefined ? overallLosses : 0,
              win_pct: (overallWins !== null && overallWins !== undefined && overallLosses !== null && overallLosses !== undefined && (overallWins + overallLosses) > 0)
                ? overallWins / (overallWins + overallLosses)
                : null
            }
          };
        }
      }
      
      // Render the page with loaded data (pass rank to avoid re-fetching)
      await renderTeamPage(teamProfile, wrappedMetrics, starterProfiles, remainingProfiles, xtpData, xtpRank);
    } else {
      // Old structure: Fallback to old loading logic (for backward compatibility)
      console.log(`[HS Team] Using legacy team profile structure, falling back to old loading`);
      throw new Error("Legacy team profile structure not supported. Please regenerate team profiles.");
    }
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
  return `${wins}–${losses}`;
}

function calculateTopRecord(starters, maxRank) {
  // Check if using precomputed records from team profile
  if (maxRank === 10 && starters.length > 0 && starters[0].profile._top10_record) {
    // Use precomputed top10 records
    let wins = 0;
    let losses = 0;
    starters.forEach(({ profile }) => {
      if (profile._top10_record) {
        wins += profile._top10_record.wins || 0;
        losses += profile._top10_record.losses || 0;
      }
    });
    return { wins, losses };
  } else if (maxRank === 33 && starters.length > 0 && starters[0].profile._top33_record) {
    // Use precomputed top33 records
    let wins = 0;
    let losses = 0;
    starters.forEach(({ profile }) => {
      if (profile._top33_record) {
        wins += profile._top33_record.wins || 0;
        losses += profile._top33_record.losses || 0;
      }
    });
    return { wins, losses };
  }
  
  // Fallback: Calculate from match_list (legacy behavior)
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
  
  if (total === 0) return "0–0";
  return `${wins}–${losses}`;
}

function computeTeamRankFromData(teamName, teamsData) {
  // Sort teams: xTP_simple desc (primary), then xTP desc, team name asc (same as leaderboard)
  const sorted = [...teamsData].sort((a, b) => {
    // Primary sort: xTP_simple (simplified rank-based scoring)
    const aSimple = a.team_xTP_simple || 0;
    const bSimple = b.team_xTP_simple || 0;
    if (bSimple !== aSimple) return bSimple - aSimple;
    // Fallback: xTP (detailed model)
    if (b.team_xTP !== a.team_xTP) return b.team_xTP - a.team_xTP;
    return a.team.localeCompare(b.team);
  });
  
  // Find team's rank (normalize team names for comparison)
  const normalizedTeamName = normalizeTeamName(teamName);
  const rank = sorted.findIndex(t => normalizeTeamName(t.team) === normalizedTeamName) + 1;
  return rank > 0 ? rank : null;
}

async function computeTeamRank(teamName, season, cachedData = null) {
  // If cached data is provided, use it instead of fetching
  if (cachedData) {
    const teamsData = Array.isArray(cachedData) ? cachedData : (cachedData.teams || []);
    return computeTeamRankFromData(teamName, teamsData);
  }
  
  // Otherwise, fetch the data (fallback for backward compatibility)
  try {
    const gender = getGenderFromURL();
    const url = buildXTPURL(gender, season);
    const data = await fetchJSON(url);
    
    // Handle both array and object with 'teams' property
    const teamsData = Array.isArray(data) ? data : (data.teams || []);
    return computeTeamRankFromData(teamName, teamsData);
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
async function renderTopSummaryRow(metrics, starters, xtpData, teamName, xtpRank = null) {
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
  
  // LEFT COLUMN: xTP Headline (Projected State Tournament Points)
  const leftCol = document.createElement("div");
  leftCol.className = "xtp-headline-summary";
  
  if (xtpData) {
    await renderXTPHeadline(xtpData, teamName, xtpRank);
    const xtpSection = document.getElementById("xtp-headline-section");
    if (xtpSection) {
      // Clone the xTP content
      const xtpClone = xtpSection.cloneNode(true);
      xtpClone.style.display = "block";
      leftCol.appendChild(xtpClone);
    }
  } else {
    const noXTP = document.createElement("div");
    noXTP.textContent = "xTP data not available";
    noXTP.style.cssText = "color: var(--muted); padding: 2em; text-align: center;";
    leftCol.appendChild(noXTP);
  }
  
  // RIGHT COLUMN: Team Profile Stats (Team Overview) - in a box matching xTP styling
  const rightCol = document.createElement("div");
  rightCol.className = "team-profile-summary";
  rightCol.style.cssText = "background: var(--bg-card); border: 1px solid var(--border-light); padding: var(--pad-lg);";
  
  const rightHeader = document.createElement("h3");
  rightHeader.className = "metrics-section-title";
  rightHeader.textContent = "Team Overview";
  rightCol.appendChild(rightHeader);
  
  const rightGrid = document.createElement("div");
  rightGrid.className = "metrics-grid metrics-grid--two-columns";
  rightGrid.style.cssText = "display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 24px; margin-bottom: 0;";
  
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
  
  rightGrid.appendChild(col1);
  rightGrid.appendChild(col2);
  rightCol.appendChild(rightGrid);
  
  // Append in swapped order: xTP left, Team Overview right
  topSummaryContainer.appendChild(leftCol);
  topSummaryContainer.appendChild(rightCol);
}

async function renderTeamPage(team, metrics, starters, remaining, xtpData, xtpRank = null) {
  const isHS = isHSSite();
  
  // Header
  const teamName = team.team_name || team.name;
  const gender = getGenderFromURL();
  document.getElementById("team-name").textContent = teamName;
  const _teamSeason = getSeasonFromURL();
  const _teamGenderLabel = gender === "girls" ? "Kentucky Girls High School" : "Kentucky High School";
  document.title = `${teamName} Wrestling ${_teamSeason} | ${_teamGenderLabel} | KentuckyMat`;
  sendPageView();
  setMetaDescription(`${teamName} ${_teamSeason} Kentucky high school wrestling. Full roster, rankings, match results, and team stats on KentuckyMat.`);
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
    await renderTopSummaryRow(metrics, starters, xtpData, teamName, xtpRank);
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
    const tmSection = document.getElementById("team-profile-metrics-section");
    if (tmSection) tmSection.style.display = "block";
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

async function renderXTPHeadline(xtpData, teamName, xtpRank = null) {
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
      disclaimerEl.textContent = "Projected points are based on statewide rank.";
      const labelEl = document.querySelector(".xtp-headline-label");
      if (labelEl) {
        labelEl.parentNode.insertBefore(disclaimerEl, labelEl.nextSibling);
      }
    }
  } else {
    // Remove disclaimer for NCAA
    const disclaimerEl = document.getElementById("xtp-disclaimer");
    if (disclaimerEl) {
      disclaimerEl.remove();
    }
  }
  
  // Large xTP value - use xTP_simple as primary, fall back to xTP
  const primaryScore = xtpData.team_xTP_simple !== null && xtpData.team_xTP_simple !== undefined 
    ? xtpData.team_xTP_simple 
    : xtpData.team_xTP;
  const total = safe(primaryScore, v => v.toFixed(1));
  const sign = primaryScore >= 0 ? "+" : "";
  document.getElementById("xtp-total").textContent = `${sign}${total}`;
  
  // Rank badge (use provided rank or compute from leaderboard)
  const rankBadgeContainer = document.getElementById("xtp-rank-badge");
  rankBadgeContainer.innerHTML = "";
  if (xtpRank !== null) {
    // Use provided rank (already computed)
    rankBadgeContainer.appendChild(createMVRankBadge(xtpRank));
  } else {
    // Fallback: compute rank (shouldn't happen in normal flow)
    const season = resolveSeason();
    const rank = await computeTeamRank(teamName, season);
    if (rank) {
      rankBadgeContainer.appendChild(createMVRankBadge(rank));
    }
  }
  
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
    // Check if using precomputed value from team profile
    if (profile._top25_wins !== undefined && profile._top25_wins !== null) {
      return profile._top25_wins;
    }
    
    // Fallback: Calculate from match_list (legacy behavior)
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

  // Calculate max xTP_simple for bar scaling (from this team's starters)
  let maxXTP = 0;
  starters.forEach(({ weight }) => {
    const weightStr = String(weight);
    const weightData = xtpData?.weights?.[weightStr];
    // Use xTP_simple as primary, fall back to xTP
    const score = weightData?.xTP_simple !== null && weightData?.xTP_simple !== undefined 
      ? weightData.xTP_simple 
      : weightData?.xTP;
    if (score !== null && score !== undefined && score > maxXTP) {
      maxXTP = score;
    }
  });

  starters.forEach(({ weight, profile }) => {
    const weightStr = String(weight);
    // Use embedded xTP data from profile if available (new structure), otherwise fall back to xtpData
    const weightData = profile._xtp_data || xtpData?.weights?.[weightStr];
    const row = document.createElement("tr");
    row.className = "xtp-expanded-row";

    // Weight
    const weightTd = document.createElement("td");
    weightTd.textContent = weight;
    row.appendChild(weightTd);

    // Grade
    const gradeTd = document.createElement("td");
    const grade = profile?.grade;
    if (grade !== null && grade !== undefined) {
      gradeTd.textContent = grade;
    } else {
      gradeTd.textContent = "—";
    }
    row.appendChild(gradeTd);

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

    // xTP_simple (primary) - simplified rank-based scoring with bar (show "0" if no qualifier)
    const xtpTd = document.createElement("td");
    xtpTd.className = "num metric-primary expanded-xtp-cell";
    xtpTd.style.cssText = "padding: 6px 12px;";

    // Use xTP_simple as primary, fall back to xTP
    const weightScore = weightData?.xTP_simple !== null && weightData?.xTP_simple !== undefined 
      ? weightData.xTP_simple 
      : weightData?.xTP;

    if (weightScore !== null && weightScore !== undefined && weightScore > 0) {
      // Scale bars relative to max xTP_simple in THIS team's starters
      xtpTd.appendChild(createMetricBar(weightScore, maxXTP || 100.0));
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

    // Record: Format as "W–L"
    const record = parseRecord(profile);
    const recordTd = document.createElement("td");
    recordTd.className = "text-center";
    recordTd.textContent = `${record.wins}–${record.losses}`;
    row.appendChild(recordTd);

    // Top 25 Wins
    const top25Td = document.createElement("td");
    top25Td.className = "num text-center";
    const top25Wins = countTop25Wins(profile);
    top25Td.textContent = top25Wins > 0 ? String(top25Wins) : "—";
    row.appendChild(top25Td);

    // Bonus Rate: Display as percentage (e.g., 75.0%)
    const bonusTd = document.createElement("td");
    bonusTd.className = "num text-center";
    const bonusRate = profile?.metrics?.bonus_rate;
    if (bonusRate !== null && bonusRate !== undefined) {
      bonusTd.textContent = percent(bonusRate);
    } else {
      bonusTd.textContent = "—";
    }
    row.appendChild(bonusTd);

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
    cell.colSpan = 6;
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
    // Check if using precomputed value from team profile
    if (profile._top25_wins !== undefined && profile._top25_wins !== null) {
      return profile._top25_wins;
    }
    
    // Fallback: Calculate from match_list (legacy behavior)
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

    // Grade
    const gradeTd = document.createElement("td");
    const grade = profile?.grade;
    if (grade !== null && grade !== undefined) {
      gradeTd.textContent = grade;
    } else {
      gradeTd.textContent = "—";
    }
    tr.appendChild(gradeTd);

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