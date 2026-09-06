// ===============================
// Helpers
// ===============================

// Seasons to try when loading a wrestler by id, newest first. A wrestler_id
// is only ever valid within the one season it was scraped under (a graduated
// senior's id doesn't exist under the current season at all), and no
// existing link site-wide passes season alongside id -- so on a miss we fall
// back through every season that actually has published data, rather than
// assuming every id is current or hardcoding a list that would need a manual
// edit each time a season is backfilled. Written by build_wrestler_profiles.py.
let _knownSeasonsCache = null;
async function getKnownSeasons() {
  if (_knownSeasonsCache) return _knownSeasonsCache;
  try {
    const res = await fetch('/data/wrestlers/available_seasons.json');
    if (res.ok) {
      _knownSeasonsCache = (await res.json()).map(String);
      return _knownSeasonsCache;
    }
  } catch (err) {
    // fall through to default below
  }
  _knownSeasonsCache = ["2026"];
  return _knownSeasonsCache;
}

// Date-aware minimum match threshold (same logic as leaderboard)
function getMinMatchThreshold() {
  const now = new Date();
  const month = now.getMonth() + 1; // 1-12
  const day = now.getDate();
  
  // Before Dec 1
  if (month < 12) {
    return 3;
  }
  
  // Dec 1 through Dec 14
  if (month === 12 && day < 15) {
    return 4;
  }
  
  // Dec 15 or later
  return 5;
}

// Compute filtered MV rank and percentile using same logic as leaderboard
async function computeFilteredMVRankAndPercentile(wrestlerId, weight, season) {
  try {
    // Load the full MV dataset
    const url = `/data/mat_value/${season}/mat_value_${season}.json`;
    const res = await fetch(url);
    if (!res.ok) return null;
    
    const allData = await res.json();
    const minMatches = getMinMatchThreshold();
    
    // Filter by weight and minimum matches (same logic as leaderboard)
    const filtered = allData.filter(entry => {
      return entry.weight === weight && entry.matches >= minMatches;
    });
    
    // Sort by MV (descending), then matches (descending), then current_rank (ascending)
    filtered.sort((a, b) => {
      if (b.mv_avg !== a.mv_avg) return b.mv_avg - a.mv_avg;
      if (b.matches !== a.matches) return b.matches - a.matches;
      const rankA = a.current_rank || 9999;
      const rankB = b.current_rank || 9999;
      return rankA - rankB;
    });
    
    // Find the wrestler's position in the filtered list
    const wrestlerIdStr = String(wrestlerId);
    const index = filtered.findIndex(entry => String(entry.wrestler_id) === wrestlerIdStr);
    
    if (index === -1) return null; // Wrestler not in filtered list
    
    const rank = index + 1; // Rank is 1-based
    const total = filtered.length;
    // Compute percentile: 100 - ((rank - 1) / total * 100)
    // Top rank (1) = 100th percentile, last rank = 1st percentile
    const percentile = Math.round(100 - ((rank - 1) / total * 100));
    // Ensure percentile is at least 1
    const finalPercentile = Math.max(1, percentile);
    
    return { rank, percentile: finalPercentile, total };
  } catch (err) {
    console.error("Error computing filtered MV rank and percentile:", err);
    return null;
  }
}

// Legacy function for backward compatibility
async function computeFilteredMVRank(wrestlerId, weight, season) {
  const result = await computeFilteredMVRankAndPercentile(wrestlerId, weight, season);
  return result ? result.rank : null;
}

// Rolling MBT trajectory cache (keyed by season string)
const _rollingMbtCache = {};

async function fetchRollingMbt(season) {
  if (_rollingMbtCache[season]) return _rollingMbtCache[season];
  const res = await fetch(`/data/mat_value/${season}/rolling_mbt_${season}.json`);
  if (!res.ok) throw new Error(`Could not load rolling MBT data for ${season}`);
  const data = await res.json();
  _rollingMbtCache[season] = data;
  return data;
}

// Define MV tier based on percentile
function getMVTier(percentile) {
  if (percentile >= 90) {
    return { tier: "elite", label: "Elite", colorClass: "mv-tier-elite" };
  } else if (percentile >= 70) {
    return { tier: "strong", label: "Strong", colorClass: "mv-tier-strong" };
  } else if (percentile >= 40) {
    return { tier: "average", label: "Average", colorClass: "mv-tier-average" };
  } else if (percentile >= 20) {
    return { tier: "below", label: "Below Avg", colorClass: "mv-tier-below" };
  } else {
    return { tier: "weak", label: "Weak", colorClass: "mv-tier-weak" };
  }
}

function safe(value, formatter) {
    if (value === null || value === undefined || value === "") return "—";
    return formatter ? formatter(value) : value;
  }
  
  function percentFormatter(v) {
    return (v * 100).toFixed(1) + "%";
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
  
  function resolveSeason() {
    return "2026"; // Or make dynamic later
  }
  
  function teamNameToSlug(teamName) {
    if (!teamName) return "";
    let slug = teamName.toLowerCase();
    slug = slug.replace(/\s+/g, "_");
    // Remove punctuation (keep only word characters and underscores)
    slug = slug.replace(/[^\w_]/g, "");
    // Collapse multiple underscores
    slug = slug.replace(/_+/g, "_");
    // Strip leading/trailing underscores
    slug = slug.replace(/^_+|_+$/g, "");
    return slug;
  }
  
  // ===============================
  // Fetch Wrestler JSON
  // ===============================
  
  async function loadWrestlerProfile(id) {
    // Try each known season (newest first) until one actually has this id --
    // see getKnownSeasons for why this can't just assume the current season.
    const seasons = await getKnownSeasons();
    for (const season of seasons) {
      try {
        const res = await fetch(`/data/wrestlers/${season}/by_id/${id}.json`);
        if (!res.ok) continue;
        const data = await res.json();
        renderWrestlerProfile(data);
        return;
      } catch (err) {
        // network error on this season -- try the next one
      }
    }
    console.error("Error loading: wrestler not found in any known season", id);
    document.getElementById("wrestler-name").textContent = "Not Found";
    document.getElementById("wrestler-tagline").textContent = "Could not load wrestler JSON";
  }

  // ===============================
  // Rendering
  // ===============================

  // Header renders once, from whichever season the page was loaded with
  // (always the most recent one a link points to) -- it never re-runs when
  // a different season row is picked below, per the "rank/weight stay at
  // current status" design. Team and grade live only in the season
  // selector table since they change year to year; hometown/high school
  // stay here since those don't.
  function renderHeader(data) {
    document.getElementById("wrestler-name").textContent = safe(data.name);

    // Wrestler tagline with rank badge
    const taglineEl = document.getElementById("wrestler-tagline");
    taglineEl.innerHTML = "";
    if (data.current_rank) {
      taglineEl.appendChild(createRankBadge(data.current_rank));
      taglineEl.appendChild(document.createTextNode(` at ${safe(data.weight_class)} lbs`));
    } else {
      taglineEl.textContent = `${safe(data.weight_class)} lbs`;
    }

    // Photo
    const photoEl = document.getElementById("wrestler-photo");
    if (data.photo_url) {
      photoEl.src = data.photo_url;
      photoEl.alt = `${safe(data.name)} headshot`;
      photoEl.hidden = false;
      photoEl.onerror = () => { photoEl.hidden = true; };
    } else {
      photoEl.hidden = true;
    }

    // Bio line: hometown · high school -- only the parts we have
    const bioEl = document.getElementById("wrestler-bio");
    const bioParts = [data.hometown, data.high_school].filter(Boolean);
    bioEl.textContent = bioParts.join(" · ");
    bioEl.hidden = bioParts.length === 0;
  }

  // Season selector: one row per season_summary entry, defaulting to
  // whichever wrestler_id the page loaded with as "active". Clicking a
  // different row re-renders everything renderSeasonBody covers, without
  // touching the header.
  function renderSeasonSelector(data) {
    const section = document.getElementById("season-selector-section");
    const tbody = document.getElementById("season-selector-body");
    const summary = data.season_summary || [];
    if (summary.length === 0) {
      section.hidden = true;
      return;
    }
    section.hidden = false;
    tbody.innerHTML = "";

    summary.forEach(s => {
      const tr = document.createElement("tr");
      tr.className = "season-row";
      if (String(s.wrestler_id) === String(data.wrestler_id)) {
        tr.classList.add("season-row--active");
      }

      const seasonCell = document.createElement("td");
      seasonCell.textContent = safe(s.season);
      tr.appendChild(seasonCell);

      const teamCell = document.createElement("td");
      if (s.team) {
        const teamLink = document.createElement("a");
        teamLink.href = `/team.html?team=${s.team_slug || teamNameToSlug(s.team)}`;
        teamLink.textContent = s.team;
        teamLink.addEventListener("click", ev => ev.stopPropagation());
        teamCell.appendChild(teamLink);
      } else {
        teamCell.textContent = "—";
      }
      tr.appendChild(teamCell);

      const gradeCell = document.createElement("td");
      gradeCell.textContent = safe(s.grade);
      tr.appendChild(gradeCell);

      const rankCell = document.createElement("td");
      rankCell.className = "num";
      rankCell.textContent = s.current_rank ? `#${s.current_rank}` : "—";
      tr.appendChild(rankCell);

      const recordCell = document.createElement("td");
      recordCell.className = "num";
      recordCell.textContent = safe(s.record);
      tr.appendChild(recordCell);

      tr.addEventListener("click", () => {
        if (tr.classList.contains("season-row--active")) return;
        fetch(`/data/wrestlers/${s.season}/by_id/${s.wrestler_id}.json`)
          .then(res => {
            if (!res.ok) throw new Error("Could not load season data");
            return res.json();
          })
          .then(seasonData => {
            renderSeasonBody(seasonData);
            tbody.querySelectorAll(".season-row--active").forEach(row => row.classList.remove("season-row--active"));
            tr.classList.add("season-row--active");
          })
          .catch(err => console.error("Error switching season:", err));
      });

      tbody.appendChild(tr);
    });
  }

  function renderWrestlerProfile(data) {
    renderHeader(data);
    renderSeasonSelector(data);
    renderSeasonBody(data);
  }

  // Everything below the season selector: re-invokable per season, since a
  // season-row click re-renders this without touching the header.
  function renderSeasonBody(data) {
    const season = safe(data.year);

    // ========================================
    // MV SECTION (DataGolf-style, no card)
    // ========================================
    const mv = (data.metrics || {}).mat_value || {};
    const weightClass = data.weight_class;
    const mvSection = document.getElementById("mv-section");
    mvSection.innerHTML = "";
  
    // Section header
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
    
    // MV leaderboard URL (used by rank badge link only)
    let leaderboardUrl = "/leaderboards/tpar.html";
    if (weightClass) {
      leaderboardUrl += `?weight=${weightClass}`;
    }
    mvSection.appendChild(headerRow);
    
    // Divider
    const divider = document.createElement("div");
    divider.className = "section-divider";
    mvSection.appendChild(divider);
    
    // B) Primary metric row -- if this season has no TPAR data at all
    // (e.g. 2025, which predates the mat_value pipeline), show one muted
    // line instead of an empty rank badge + "—" number.
    if (mv.mv_avg === null || mv.mv_avg === undefined) {
      const empty = document.createElement("p");
      empty.className = "section-empty-state";
      empty.textContent = "TPAR not available for this season.";
      mvSection.appendChild(empty);
    } else {
      const primaryRow = document.createElement("div");
      primaryRow.className = "mv-primary-row";

      // RANK BADGE (primary visual) - wraps badge in link to MV leaderboard
      const rankBadgeLink = document.createElement("a");
      rankBadgeLink.href = leaderboardUrl;
      rankBadgeLink.className = "mv-rank-badge-link";
      if (mv.rank_weight !== null && mv.rank_weight !== undefined) {
        rankBadgeLink.appendChild(createMVRankBadge(mv.rank_weight));
      }
      // Add tooltip to rank badge
      addTooltip(rankBadgeLink, "Per-match value above opponent expectation.");
      primaryRow.appendChild(rankBadgeLink);

      // MV Number with explicit sign (smaller font, same row as badge)
      const mvValue = document.createElement("div");
      mvValue.className = "mv-number mv-number-inline";
      const sign = mv.mv_avg >= 0 ? "+" : "";
      mvValue.textContent = `${sign}${mv.mv_avg.toFixed(3)}`;
      primaryRow.appendChild(mvValue);

      // Percentile bar container (below the row, will be populated after percentile is computed)
      const percentileBarContainer = document.createElement("div");
      percentileBarContainer.className = "mv-percentile-bar-container";
      mvSection.appendChild(primaryRow);
      mvSection.appendChild(percentileBarContainer);

      // Compute percentile and update display asynchronously
      if (weightClass && data.wrestler_id) {
        computeFilteredMVRankAndPercentile(data.wrestler_id, weightClass, season).then(result => {
          if (result) {
            const { rank, percentile, total } = result;

            // Create percentile bar
            percentileBarContainer.innerHTML = "";
            const barWrapper = document.createElement("div");
            barWrapper.className = "mv-percentile-bar";
            const barFill = document.createElement("div");
            barFill.className = "mv-percentile-fill";
            barFill.style.width = `${percentile}%`;
            barWrapper.appendChild(barFill);
            percentileBarContainer.appendChild(barWrapper);

            // Add percentile text
            const percentileText = document.createElement("span");
            percentileText.className = "mv-percentile-text";
            // Top X% = (rank / total) * 100, rounded up
            const topPercent = Math.ceil((rank / total) * 100);
            percentileText.textContent = `Top ${topPercent}%`;
            percentileBarContainer.appendChild(percentileText);

            // Update rank badge
            if (rankBadgeLink) {
              rankBadgeLink.innerHTML = "";
              rankBadgeLink.appendChild(createMVRankBadge(rank));
              // Re-add tooltip after updating badge
              addTooltip(rankBadgeLink, "Per-match value above opponent expectation.");
            }
          } else {
            // Fallback: use raw rank and estimate percentile
            if (mv.rank_weight !== null && mv.rank_weight !== undefined) {
              // Estimate percentile from rank (rough approximation)
              let estimatedPercentile = 50;
              if (mv.rank_weight <= 3) {
                estimatedPercentile = 95;
              } else if (mv.rank_weight <= 10) {
                estimatedPercentile = 85;
              } else if (mv.rank_weight <= 20) {
                estimatedPercentile = 70;
              } else if (mv.rank_weight <= 33) {
                estimatedPercentile = 50;
              } else {
                estimatedPercentile = 30;
              }
              // Create basic percentile bar
              percentileBarContainer.innerHTML = "";
              const barWrapper = document.createElement("div");
              barWrapper.className = "mv-percentile-bar";
              const barFill = document.createElement("div");
              barFill.className = "mv-percentile-fill";
              barFill.style.width = `${estimatedPercentile}%`;
              barWrapper.appendChild(barFill);
              percentileBarContainer.appendChild(barWrapper);

              const percentileText = document.createElement("span");
              percentileText.className = "mv-percentile-text";
              percentileText.textContent = `Top ${100 - estimatedPercentile + 1}%`;
              percentileBarContainer.appendChild(percentileText);
            }
          }
        }).catch(err => {
          console.error("Error computing MV percentile:", err);
          // Keep basic display on error
          if (mv.rank_weight !== null && mv.rank_weight !== undefined) {
            const rankSpan = rankBadgeLink.querySelector(".mv-rank-value");
            if (rankSpan) {
              rankSpan.textContent = `#${mv.rank_weight}`;
            }
          }
        });
      }
    }

    // Season stats (compact text list)
    const statsHeading = document.createElement("div");
    statsHeading.className = "mv-season-heading";
    statsHeading.textContent = "Season stats";
    mvSection.appendChild(statsHeading);
    
    const statsContainer = document.createElement("div");
    statsContainer.className = "mv-season-stats";
    
    const record = data.record || {};
    const mAll = data.metrics || {};
    
    const addStat = (label, value) => {
      if (value === null || value === undefined || value === "") return;
      const row = document.createElement("div");
      row.className = "mv-season-stat-row";
      const labelEl = document.createElement("span");
      labelEl.className = "mv-season-stat-label";
      labelEl.textContent = `${label}:`;
      const valueEl = document.createElement("span");
      valueEl.className = "mv-season-stat-value";
      valueEl.textContent = value;
      row.appendChild(labelEl);
      row.appendChild(valueEl);
      statsContainer.appendChild(row);
    };
    
    addStat("Record", safe(record.overall));
    if (mAll.bonus_rate !== null && mAll.bonus_rate !== undefined) {
      addStat("Bonus Rate", percentFormatter(mAll.bonus_rate));
    }
    addStat("Pins", safe(mAll.pins));
    addStat("Tech Falls", safe(mAll.techs));
    addStat("Majors", safe(mAll.majors));
    addStat("vs Ranked", safe(record.vs_ranked));
    addStat("vs Top 10", safe(record.vs_top10));
    
    mvSection.appendChild(statsContainer);
    
    // ========================================
    // SKILL PROFILE SECTION (DataGolf-style, no card)
    // ========================================
    const m = data.metrics || {};
    const skillSection = document.getElementById("skill-section");
    skillSection.innerHTML = "";
    
    // Section header
    const skillHeader = document.createElement("div");
    skillHeader.className = "section-header";
    const skillTitle = document.createElement("h2");
    skillTitle.textContent = "Skill Profile";
    skillHeader.appendChild(skillTitle);
    skillSection.appendChild(skillHeader);
    
    // Divider
    const skillDivider = document.createElement("div");
    skillDivider.className = "section-divider";
    skillSection.appendChild(skillDivider);
    
    // Skill rows with bars (SI+, DF+, APR+) - baseline at 100
    const skillRowsContainer = document.createElement("div");
    skillRowsContainer.className = "skill-rows-container";
    let hasAnySkillMetric = false;

    // SI+ (Scoring)
    if (m.si_plus !== null && m.si_plus !== undefined) {
      const row = createSkillRowWithBaseline("SI+ (Scoring)", m.si_plus);
      skillRowsContainer.appendChild(row);
      hasAnySkillMetric = true;
    }

    // DF+ (Defense)
    if (m.df_plus !== null && m.df_plus !== undefined) {
      const row = createSkillRowWithBaseline("DF+ (Defense)", m.df_plus);
      skillRowsContainer.appendChild(row);
      hasAnySkillMetric = true;
    }

    // APR+ (Pin Rate)
    if (m.apr_plus !== null && m.apr_plus !== undefined) {
      const row = createSkillRowWithBaseline("APR+ (Pin Rate)", m.apr_plus);
      skillRowsContainer.appendChild(row);
      hasAnySkillMetric = true;
    }

    if (hasAnySkillMetric) {
      skillSection.appendChild(skillRowsContainer);

      // Synthesized profile description
      const profileDesc = generateSkillProfileDescription(m);
      if (profileDesc) {
        const descEl = document.createElement("p");
        descEl.className = "skill-profile-description";
        descEl.textContent = profileDesc;
        skillSection.appendChild(descEl);
      }
    } else {
      const empty = document.createElement("p");
      empty.className = "section-empty-state";
      empty.textContent = "Skill profile not available for this season.";
      skillSection.appendChild(empty);
    }
    
    // ========================================
    // MATCH IMPACT TIMELINE (PROMOTED - BEFORE CONTEXT)
    // ========================================
    renderRollingMbtTimeline(data, mv.mv_avg);
    
    // ========================================
    // MV CONTEXT (COMPRESSED, BELOW TIMELINE)
    // ========================================
    // MV Composition removed - keep section visible for divider, but render nothing
    renderMVContextCompressed(data, mv.mv_avg);
    
    // ========================================
    // EXPECTED NCAA IMPACT (xTP)
    // ========================================
    // Note: xTP data may need to be loaded separately from team xTP file
    // For now, hide the section if data is not available
    // TODO: Load xTP data from team xTP file if needed
    const xtpSection = document.getElementById("xtp-section");
    // Hide xTP section for now - will be populated when xTP data is available
    xtpSection.style.display = "none";
    
    // ========================================
    // MATCH HISTORY
    // ========================================
    renderMatchTable(data.match_list || [], mv.mv_avg);
  }
  
  function renderSkillMetric(container, label, value, leagueAvg, formatter) {
    const row = document.createElement("div");
    row.className = "skill-metric-row";
    
    const labelEl = document.createElement("div");
    labelEl.className = "skill-metric-label";
    labelEl.textContent = label + ":";
    row.appendChild(labelEl);
    
    const valueEl = document.createElement("div");
    valueEl.className = "skill-metric-value";
    
    if (value === null || value === undefined || value === "") {
      valueEl.textContent = "—";
    } else {
      const formattedValue = formatter ? formatter(value) : safe(value);
      
      if (leagueAvg !== null && leagueAvg !== undefined) {
        // Render with bar centered on league average
        const barContainer = document.createElement("div");
        barContainer.className = "skill-metric-bar-container";
        
        // Calculate bar position (centered on league average)
        // Positive values extend right, negative extend left
        const diff = value - leagueAvg;
        const maxDiff = 50; // Max deviation for scaling
        const pct = Math.min(Math.abs(diff) / maxDiff, 1) * 50; // Max 50% each direction
        
        // Zero line (league average)
        const zeroLine = document.createElement("div");
        zeroLine.className = "skill-metric-zero-line";
        barContainer.appendChild(zeroLine);
        
        // Value bar
        if (diff !== 0) {
          const bar = document.createElement("div");
          bar.className = `skill-metric-bar ${diff > 0 ? 'positive' : 'negative'}`;
          bar.style.width = `${pct}%`;
          if (diff > 0) {
            bar.style.left = '50%';
          } else {
            bar.style.right = '50%';
          }
          barContainer.appendChild(bar);
        }
        
        // Value label
        const valueLabel = document.createElement("div");
        valueLabel.className = `skill-metric-value-label ${diff >= 0 ? 'positive' : 'negative'}`;
        valueLabel.textContent = formattedValue;
        if (diff >= 0) {
          valueLabel.style.right = '0';
        } else {
          valueLabel.style.left = '0';
        }
        barContainer.appendChild(valueLabel);
        
        valueEl.appendChild(barContainer);
      } else {
        // No bar, just value
        valueEl.textContent = formattedValue;
      }
    }
    
    row.appendChild(valueEl);
    container.appendChild(row);
  }
  
  function renderImpactSummary(ob) {
    const el = document.getElementById("impact-summary");
    const lines = [];
  
    if (ob.win_over_highest_rank) {
      const w = ob.win_over_highest_rank;
      lines.push(
        `Best Win: #${safe(w.opponent_rank)} ${safe(w.opponent_name)} (${safe(w.method)})`
      );
    }
  
    if (ob.worst_loss) {
      const l = ob.worst_loss;
      lines.push(
        `Worst Loss: #${safe(l.opponent_rank)} ${safe(l.opponent_name)} (${safe(l.method)})`
      );
    }
  
    el.innerHTML = lines.map((l) => `<div>${l}</div>`).join("");
  }
  
  function createSkillRow(label, value, pct) {
    const row = document.createElement("div");
    row.className = "skill-row";
    
    const labelEl = document.createElement("div");
    labelEl.className = "skill-label";
    labelEl.textContent = label;
    row.appendChild(labelEl);
    
    const barContainer = document.createElement("div");
    barContainer.className = "skill-bar";
    const barFill = document.createElement("div");
    barFill.className = "skill-bar-fill";
    barFill.style.setProperty("--pct", pct);
    barContainer.appendChild(barFill);
    row.appendChild(barContainer);
    
    const valueEl = document.createElement("div");
    valueEl.className = "skill-value";
    valueEl.textContent = value.toFixed(1);
    row.appendChild(valueEl);
    
    return row;
  }
  
  function createSkillRowWithBaseline(label, value) {
    const row = document.createElement("div");
    row.className = "skill-row";
    
    // Row 1: Label only
    const labelRow = document.createElement("div");
    labelRow.className = "skill-label-row";
    const labelEl = document.createElement("div");
    labelEl.className = "skill-label";
    labelEl.textContent = label;
    labelRow.appendChild(labelEl);
    row.appendChild(labelRow);
    
    // Row 2: Value and bar together
    const valueBarRow = document.createElement("div");
    valueBarRow.className = "skill-value-bar-row";
    
    // Value with color coding
    const valueEl = document.createElement("div");
    valueEl.className = "skill-value";
    if (value < 95) {
      valueEl.classList.add("skill-value-low");
    } else if (value > 105) {
      valueEl.classList.add("skill-value-high");
    } else {
      valueEl.classList.add("skill-value-neutral");
    }
    valueEl.textContent = value.toFixed(1);
    valueBarRow.appendChild(valueEl);
    
    // Bar wrapper (container for bar and baseline)
    const barWrapper = document.createElement("div");
    barWrapper.className = "skill-bar-wrapper";
    
    // Baseline reference line at 100 (static visual marker)
    const baseline = document.createElement("div");
    baseline.className = "skill-baseline";
    barWrapper.appendChild(baseline);
    
    // Bar (always starts at 0, extends to value)
    const SKILL_MAX = 160;
    const barPct = Math.min((value / SKILL_MAX) * 100, 100);
    
    const bar = document.createElement("div");
    bar.className = "skill-bar";
    bar.style.setProperty("--bar-pct", `${barPct}%`);
    bar.style.width = `${barPct}%`;
    
    // Color class based on value (not direction)
    if (value < 95) {
      bar.classList.add("low");
    } else if (value <= 105) {
      bar.classList.add("neutral");
    } else {
      bar.classList.add("high");
    }
    
    barWrapper.appendChild(bar);
    valueBarRow.appendChild(barWrapper);
    
    row.appendChild(valueBarRow);
    
    return row;
  }
  
  function generateSkillProfileDescription(metrics) {
    const parts = [];
    
    // Bonus-driven vs decision-driven
    const bonusRate = metrics.bonus_rate;
    if (bonusRate !== null && bonusRate !== undefined) {
      if (bonusRate > 0.5) {
        parts.push("bonus-driven");
      } else {
        parts.push("decision-focused");
      }
    }
    
    // Scoring ability
    const siPlus = metrics.si_plus;
    if (siPlus !== null && siPlus !== undefined) {
      if (siPlus > 110) {
        parts.push("high-volume scorer");
      } else if (siPlus < 95) {
        parts.push("low-volume scorer");
      } else {
        parts.push("average scorer");
      }
    }
    
    // Defense
    const dfPlus = metrics.df_plus;
    if (dfPlus !== null && dfPlus !== undefined) {
      if (dfPlus > 110) {
        parts.push("strong defense");
      } else if (dfPlus < 95) {
        parts.push("weak defense");
      } else {
        parts.push("average defense");
      }
    }
    
    if (parts.length === 0) {
      return null;
    }
    
    return `Profile: ${parts.join(" with ")}.`;
  }
  
  function createQuickStat(label, value) {
    const stat = document.createElement("div");
    stat.className = "quick-stat";
    
    const labelEl = document.createElement("span");
    labelEl.textContent = label;
    stat.appendChild(labelEl);
    
    const valueEl = document.createElement("span");
    valueEl.className = "quick-stat-value";
    valueEl.textContent = value;
    stat.appendChild(valueEl);
    
    return stat;
  }
  
  function createMiniBadge(text) {
    const badge = document.createElement("span");
    badge.className = "mini-badge";
    badge.textContent = text;
    return badge;
  }
  
  function renderMVTrendIndicator(data, seasonMV) {
    const container = document.getElementById("mv-trend-indicator");
    container.innerHTML = "";
    
    if (!seasonMV || seasonMV === null || seasonMV === undefined) {
      return;
    }
    
    const matches = data.match_list || [];
    if (matches.length < 5) {
      return; // Not enough data
    }
    
    // Get last 5 matches (sorted by date descending)
    const sortedMatches = [...matches].sort((a, b) => (b.date || "").localeCompare(a.date || ""));
    const last5 = sortedMatches.slice(0, 5);
    
    // Estimate MV for last 5 matches (simplified - would need actual match MV data)
    // For now, use a placeholder calculation based on results
    // This is a simplified approximation
    let rollingSum = 0;
    let validMatches = 0;
    
    last5.forEach(match => {
      // Simplified: estimate MV based on result type
      // Win = positive, Loss = negative
      // Bonus wins = higher positive
      const isWin = match.result === "W";
      const method = (match.method || "").toUpperCase();
      let estimatedMV = 0;
      
      if (isWin) {
        if (method === "PIN" || method === "FALL" || method === "INJ") {
          estimatedMV = 4.0;
        } else if (method === "TF") {
          estimatedMV = 3.5;
        } else if (method === "MD") {
          estimatedMV = 2.5;
        } else {
          estimatedMV = 1.5;
        }
      } else {
        estimatedMV = -2.0; // Loss
      }
      
      rollingSum += estimatedMV;
      validMatches++;
    });
    
    if (validMatches === 0) {
      return;
    }
    
    const rollingMV = rollingSum / validMatches;
    const threshold = seasonMV * 0.05; // 5% threshold
    
    let trend = "stable";
    let trendText = "→";
    let trendClass = "mv-trend-stable";
    
    if (rollingMV >= seasonMV + threshold) {
      trend = "rising";
      trendText = "↑";
      trendClass = "mv-trend-rising";
    } else if (rollingMV <= seasonMV - threshold) {
      trend = "declining";
      trendText = "↓";
      trendClass = "mv-trend-declining";
    }
    
    const indicator = document.createElement("div");
    indicator.className = `mv-trend-indicator ${trendClass}`;
    indicator.textContent = trendText;
    indicator.setAttribute("title", "Based on last 5 matches vs season average TPAR");
    container.appendChild(indicator);
  }
  
  function renderMVContextCompressed(data, seasonMV) {
    // MV Composition removed - no longer displayed
    // Keep section visible for divider above Match History
    const container = document.getElementById("mv-context-compressed");
    if (!container) return;
    container.innerHTML = "";
    
    // Add divider at bottom of MV context section (above Match History)
    const divider = document.createElement("div");
    divider.className = "section-divider";
    container.appendChild(divider);
  }
  
  // Match Impact Timeline toggle handler (set up after page loads)
  function setupMatchImpactToggle() {
    const toggleLinks = document.querySelectorAll(".impact-toggle-link");
    toggleLinks.forEach(link => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const mode = link.dataset.mode;
        
        // Update active state
        toggleLinks.forEach(l => l.classList.remove("active"));
        link.classList.add("active");
        
        // Re-render chart with selected mode
        // For now, MV and xTP use same data structure
        // In future, xTP mode would load xTP data per match
        const container = document.getElementById("match-impact-chart-container");
        const matchDataStr = container.dataset.matchData;
        if (matchDataStr) {
          // Re-render with same data (xTP mode would use different data)
          // For now, just update the chart title/description
          console.log(`Switched to ${mode} mode`);
        }
      });
    });
  }
  
  // Initialize toggle after DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupMatchImpactToggle);
  } else {
    setupMatchImpactToggle();
  }
  
  function formatDateMMDDYY(dateStr) {
    if (!dateStr) return "—";
    try {
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) return dateStr; // Return original if invalid
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      const year = String(date.getFullYear()).slice(-2);
      return `${month}-${day}-${year}`;
    } catch (e) {
      return dateStr;
    }
  }
  
  function createOpponentRankBadge(rank) {
    if (rank === null || rank === undefined || rank === "") {
      const badge = document.createElement("span");
      badge.className = "rank-badge unr-badge";
      badge.textContent = "UNR";
      return badge;
    }
    
    const badge = document.createElement("span");
    badge.className = "rank-badge";
    
    // Medal badge rules: #1 gold, #2 silver, #3-5 bronze, #6-10 top (green), #11+ standard
    if (rank === 1) {
      badge.classList.add("medal-gold");
    } else if (rank === 2) {
      badge.classList.add("medal-silver");
    } else if (rank >= 3 && rank <= 5) {
      badge.classList.add("medal-bronze");
    } else if (rank >= 6 && rank <= 10) {
      badge.classList.add("top");
    } else {
      badge.classList.add("standard");
    }
    
    badge.textContent = `#${rank}`;
    return badge;
  }
  
  function createResultBadge(result, method) {
    const badge = document.createElement("span");
    badge.className = "result-badge";
    
    const isWin = result === "W";
    if (isWin) {
      badge.classList.add("result-win");
    } else {
      badge.classList.add("result-loss");
    }
    
    // Classify result type by checking result string first, then method field
    // This ensures correct classification even if Python code sets wrong method
    const resultStr = (result || "").toUpperCase();
    const methodStr = (method || "").toUpperCase();
    const combinedStr = `${resultStr} ${methodStr}`;
    
    let methodText;
    
    // Check result string first (most reliable)
    // Priority order matters - check most specific first
    
    // 1. Medical Forfeit (check for MFF indicators first)
    if (combinedStr.includes("M. FOR.") || combinedStr.includes("MFF") || 
        (combinedStr.includes("MEDICAL") && combinedStr.includes("FORFEIT"))) {
      methodText = "MFF";
    }
    // 2. Disqualification
    else if (combinedStr.includes("DQ") || combinedStr.includes("DISQUAL")) {
      methodText = "DQ";
    }
    // 3. Injury Default
    else if (combinedStr.includes("INJ") || combinedStr.includes("INJURY")) {
      methodText = "INJ";
    }
    // 4. Regular Forfeit (only if not already caught as medical forfeit)
    else if (combinedStr.includes("FORFEIT") || 
             (combinedStr.includes(" FF") && !combinedStr.includes("MFF"))) {
      methodText = "FF";
    }
    // 5. Technical Fall (check before regular fall/pin)
    else if (combinedStr.includes("TF") || combinedStr.includes("TECH") || 
             combinedStr.includes("TECHNICAL")) {
      methodText = "TF";
    }
    // 6. Fall/Pin (but not tech fall)
    else if ((combinedStr.includes("FALL") || combinedStr.includes(" PIN")) && 
             !combinedStr.includes("TF") && !combinedStr.includes("TECH")) {
      methodText = "FALL";
    }
    // 7. Major Decision
    else if (combinedStr.includes("MD") || combinedStr.includes("MAJOR")) {
      methodText = "MD";
    }
    // 8. Decision (including SV and TB - these are still decisions)
    else if (combinedStr.includes("DEC") || combinedStr.includes("DECISION") ||
             combinedStr.includes("SV-") || combinedStr.includes("TB-") ||
             combinedStr.includes("SUDDEN VICTORY") || combinedStr.includes("TIEBREAK")) {
      methodText = "DEC";
    }
    // 9. Fall back to method field if it exists and is valid
    else if (methodStr && methodStr !== "—" && methodStr !== "" && methodStr !== "DEF.") {
      methodText = safe(methodStr);
    }
    // 10. Unknown/Other (default)
    else {
      methodText = "O";
    }
    
    badge.textContent = methodText;
    
    // Tooltip: "Win by Technical Fall" or "Loss by Decision"
    const outcome = isWin ? "Win" : "Loss";
    const methodName = methodText === "DEC" ? "Decision" :
                      methodText === "MD" ? "Major Decision" :
                      methodText === "TF" ? "Technical Fall" :
                      methodText === "FALL" || methodText === "PIN" ? "Fall" :
                      methodText === "INJ" ? "Injury Default" :
                      methodText === "DQ" ? "Disqualification" :
                      methodText === "MFF" ? "Medical Forfeit" :
                      methodText === "FF" ? "Forfeit" :
                      methodText === "O" ? "Other" :
                      methodText;
    badge.setAttribute("title", `${outcome} by ${methodName}`);
    
    return badge;
  }
  
  function renderMatchTable(matches, seasonMV) {
    const tbody = document.querySelector("#match-table tbody");
    tbody.innerHTML = "";
  
    // Sort chronologically (oldest first) for timeline consistency
    const sortedMatches = [...matches].sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  
    sortedMatches.forEach((match) => {
      const tr = document.createElement("tr");
  
      // 1. Date (MM-DD-YY format)
      const dateTd = document.createElement("td");
      dateTd.textContent = formatDateMMDDYY(match.date);
      tr.appendChild(dateTd);
  
      // 2. Opponent (with link, .name styling)
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
  
      // 3. Opponent Team (muted secondary)
      const oppTeamTd = document.createElement("td");
      oppTeamTd.className = "metric-secondary";
      const oppTeamName = safe(match.opponent_team);
      if (oppTeamName && oppTeamName !== "—") {
        const teamSlug = teamNameToSlug(oppTeamName);
        const teamLink = document.createElement("a");
        teamLink.href = `/team.html?team=${teamSlug}`;
        teamLink.textContent = oppTeamName;
        oppTeamTd.appendChild(teamLink);
      } else {
        oppTeamTd.textContent = oppTeamName;
      }
      tr.appendChild(oppTeamTd);
      
      // 4. Opponent Rank (badge with medal rules)
      const oppRankTd = document.createElement("td");
      oppRankTd.appendChild(createOpponentRankBadge(match.opponent_rank));
      tr.appendChild(oppRankTd);
      
      // 5. Result (combined Result + Method as badge)
      const resultTd = document.createElement("td");
      resultTd.appendChild(createResultBadge(match.result, match.method));
      tr.appendChild(resultTd);
      
      // 6. MV Impact (right-aligned, tabular, color-coded)
      const impactTd = document.createElement("td");
      impactTd.className = "num";
      const mvImpact = match.mv_impact_v1 !== undefined ? match.mv_impact_v1 : match.mv_impact;
      if (mvImpact !== null && mvImpact !== undefined) {
        const impactText = mvImpact > 0 ? `+${mvImpact.toFixed(1)}` : mvImpact.toFixed(1);
        impactTd.textContent = impactText;
        impactTd.classList.add(mvImpact > 0 ? "impact-positive" : "impact-negative");
      } else {
        impactTd.textContent = "—";
      }
      tr.appendChild(impactTd);
      
      // 7. Score (muted secondary)
      const scoreTd = document.createElement("td");
      scoreTd.className = "metric-secondary num";
      scoreTd.textContent = safe(match.score);
      tr.appendChild(scoreTd);
  
      tbody.appendChild(tr);
    });
  }
  
  // NOTE: estimateMatchMVImpact has been removed.
  // MV impact is now computed in Python (compute_all_mat_values.py) and stored
  // directly in the match JSON as match.mv_impact. The frontend displays this
  // value verbatim without any calculations or heuristics.
  
  function renderRollingMbtTimeline(data, seasonMV) {
    const container = document.getElementById("match-impact-chart-container");
    container.innerHTML = '<span style="opacity:0.4;font-size:0.85em;padding:8px;display:block">Loading…</span>';

    const season = String(data.year || "2026");
    const wrestlerId = String(data.wrestler_id);

    // Bars use v1 per-match impact (mv_impact_v1 if MBT migration ran, else mv_impact).
    // MBT deltas are too small (~0.1) to drive bars on a ±6 scale — v1 gives +3–+6
    // for quality wins which is the right visual. MBT shows up in the headline and
    // dashed reference line (seasonMV). Trajectory line uses rolling MBT.
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

      // Build a date → MBT TPAR lookup from the rolling trajectory
      // rolling_mbt uses MM/DD/YYYY; match_list uses YYYY-MM-DD — normalize both to YYYY-MM-DD
      const toISO = s => {
        if (!s) return s;
        if (s.includes('-')) return s; // already YYYY-MM-DD
        const [m, d, y] = s.split('/');
        return `${y}-${m.padStart(2,'0')}-${d.padStart(2,'0')}`;
      };
      const mbtByDate = {};
      const timeline = allTimelines[wrestlerId] || [];
      timeline.forEach(pt => { mbtByDate[toISO(pt.date)] = pt.tpar; });

      // Build the white trajectory line points: for each match (in order),
      // look up the MBT TPAR at that date (carry forward if not found).
      let lastMbt = null;
      const matchMbt = matches.map(m => {
        const key = toISO(m.date);
        if (mbtByDate[key] !== undefined) lastMbt = mbtByDate[key];
        return lastMbt;
      });

      const chartHeight = 250;
      const containerWidth = container.clientWidth || 600;
      const padding = { top: 30, right: 20, bottom: 30, left: 20 };
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
      const xOf = i => matches.length === 1
        ? padding.left + plotWidth / 2
        : padding.left + (i / (matches.length - 1)) * plotWidth;

      // Gridlines
      [6, 4, 2, 0, -2, -4, -6].forEach(gv => {
        const gy = yOf(gv);
        if (gy < padding.top - 1 || gy > padding.top + plotHeight + 1) return;
        const gl = document.createElementNS("http://www.w3.org/2000/svg", "line");
        gl.setAttribute("x1", padding.left); gl.setAttribute("x2", padding.left + plotWidth);
        gl.setAttribute("y1", gy); gl.setAttribute("y2", gy);
        gl.setAttribute("stroke", gv === 0 ? "rgba(33,28,22,0.15)" : "rgba(33,28,22,0.08)");
        gl.setAttribute("stroke-width", "1");
        gl.setAttribute("class", "chart-gridline");
        svg.appendChild(gl);
      });

      // Season TPAR reference line (dashed yellow) — uses MBT final value
      if (seasonMV !== null && seasonMV !== undefined) {
        const flatY = yOf(seasonMV);
        const flat = document.createElementNS("http://www.w3.org/2000/svg", "line");
        flat.setAttribute("x1", padding.left); flat.setAttribute("x2", padding.left + plotWidth);
        flat.setAttribute("y1", flatY); flat.setAttribute("y2", flatY);
        flat.setAttribute("stroke", "rgba(200,150,40,0.85)");
        flat.setAttribute("stroke-width", "1.5");
        flat.setAttribute("stroke-dasharray", "5 4");
        flat.setAttribute("class", "season-avg-line");
        svg.appendChild(flat);
      }

      // Bars: v1 per-match impact (one per match)
      const barWidth = Math.max(3, plotWidth / matches.length - 2);
      const bars = matches.map((m, idx) => {
        const impact = m.mvImpact;
        const x = xOf(idx);
        const barHeight = Math.abs(impact) / chartMaxValue * (plotHeight / 2);
        const isPositive = impact >= 0;

        const bar = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        bar.setAttribute("x", x - barWidth / 2);
        bar.setAttribute("y", isPositive ? zeroY - barHeight : zeroY);
        bar.setAttribute("width", barWidth);
        bar.setAttribute("height", barHeight);
        bar.setAttribute("fill", isPositive ? "rgba(56,161,105,1)" : "rgba(197,48,48,1)");
        bar.setAttribute("opacity", "0.55");
        bar.setAttribute("class", "match-impact-bar");
        svg.appendChild(bar);
        return { element: bar, x, barHeight, isPositive, match: m, mbt: matchMbt[idx] };
      });

      // 5-match rolling average of per-match impacts (same reactive behavior as old chart)
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
        trajPath.setAttribute("stroke", "rgba(43,108,176,0.85)"); /* site accent blue -- was white, invisible since the light re-theme */
        trajPath.setAttribute("stroke-width", "2");
        trajPath.setAttribute("fill", "none");
        trajPath.setAttribute("class", "rolling-avg-line");
        svg.appendChild(trajPath);
      }

      // Hover dot on trajectory line
      const lineDot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      lineDot.setAttribute("r", "3");
      lineDot.setAttribute("fill", "rgba(43,108,176,1)");
      lineDot.setAttribute("class", "rolling-avg-dot");
      lineDot.setAttribute("opacity", "0");
      svg.appendChild(lineDot);

      container.appendChild(svg);

      // Hover: snap to nearest bar by X
      let activeIndex = -1;

      svg.addEventListener("mousemove", (e) => {
        const svgRect = svg.getBoundingClientRect();
        const mouseX = e.clientX - svgRect.left;
        const relX = mouseX - padding.left;
        const normX = Math.max(0, Math.min(1, relX / plotWidth));
        let index = Math.round(normX * (matches.length - 1));
        index = Math.max(0, Math.min(matches.length - 1, index));

        if (index !== activeIndex) {
          activeIndex = index;
          bars.forEach((b, i) => b.element.setAttribute("opacity", i === activeIndex ? "1.0" : "0.55"));
        }

        const b = bars[activeIndex];
        const m = b.match;
        const impactSign = m.mvImpact >= 0 ? '+' : '';
        const rollingVal = rollingMbt[activeIndex];
        const rollingStr = rollingVal !== null ? `${rollingVal >= 0 ? '+' : ''}${rollingVal.toFixed(2)}` : '—';
        const seasonAvgStr = seasonMV !== null && seasonMV !== undefined ? seasonMV.toFixed(2) : '—';
        const tooltipLines = [
          m.date,
          m.opponent || '',
          `TPAR Impact: ${impactSign}${m.mvImpact.toFixed(1)}`,
          `5-match avg TPAR: ${rollingStr}`,
          `Season TPAR: ${seasonAvgStr}`,
        ];
        const tooltipY = b.isPositive ? zeroY - b.barHeight - 12 : zeroY + b.barHeight + 12;
        showChartTooltip(e, tooltipLines.join('\n'), svg, b.x, tooltipY, m.mvImpact);

        lineDot.setAttribute("cx", b.x);
        lineDot.setAttribute("cy", yOf(rollingMbt[activeIndex]));
        lineDot.setAttribute("opacity", "1");
      });

      svg.addEventListener("mouseleave", () => {
        bars.forEach(b => b.element.setAttribute("opacity", "0.55"));
        lineDot.setAttribute("opacity", "0");
        activeIndex = -1;
        hideChartTooltip();
      });

    }).catch(() => {
      // Rolling MBT failed — fall back to bars only with season avg line
      container.innerHTML = "";
      _renderBarsOnly(data, seasonMV, container);
    });
  }

  function _renderBarsOnly(data, seasonMV, container) {
    const matches = (data.match_list || [])
      .map(m => ({ date: m.date || "", mvImpact: m.mv_impact_v1 !== undefined ? m.mv_impact_v1 : m.mv_impact, opponent: m.opponent_name }))
      .filter(m => m.mvImpact !== null && m.mvImpact !== undefined)
      .sort((a, b) => (a.date || "").localeCompare(b.date || ""));
    if (matches.length === 0) { container.textContent = "No match data available"; return; }

    const chartHeight = 250;
    const containerWidth = container.clientWidth || 600;
    const padding = { top: 30, right: 20, bottom: 30, left: 20 };
    const plotWidth = containerWidth - padding.left - padding.right;
    const plotHeight = chartHeight - padding.top - padding.bottom;
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", containerWidth); svg.setAttribute("height", chartHeight);
    svg.setAttribute("class", "match-impact-chart"); svg.style.display = "block";
    const maxAbs = Math.max(...matches.map(m => Math.abs(m.mvImpact || 0)), 1);
    const chartMaxValue = Math.max(6, maxAbs);
    const zeroY = padding.top + plotHeight / 2;
    const yOf = v => zeroY - (Math.max(-chartMaxValue, Math.min(chartMaxValue, v)) / chartMaxValue) * (plotHeight / 2);
    const xOf = i => matches.length === 1 ? padding.left + plotWidth / 2 : padding.left + (i / (matches.length - 1)) * plotWidth;
    [6,4,2,0,-2,-4,-6].forEach(gv => {
      const gy = yOf(gv); if (gy < padding.top-1 || gy > padding.top+plotHeight+1) return;
      const gl = document.createElementNS("http://www.w3.org/2000/svg","line");
      gl.setAttribute("x1",padding.left); gl.setAttribute("x2",padding.left+plotWidth);
      gl.setAttribute("y1",gy); gl.setAttribute("y2",gy);
      gl.setAttribute("stroke",gv===0?"rgba(33,28,22,0.15)":"rgba(33,28,22,0.08)"); gl.setAttribute("stroke-width","1");
      svg.appendChild(gl);
    });
    if (seasonMV !== null && seasonMV !== undefined) {
      const flatY = yOf(seasonMV);
      const flat = document.createElementNS("http://www.w3.org/2000/svg","line");
      flat.setAttribute("x1",padding.left); flat.setAttribute("x2",padding.left+plotWidth);
      flat.setAttribute("y1",flatY); flat.setAttribute("y2",flatY);
      flat.setAttribute("stroke","rgba(200,150,40,0.85)"); flat.setAttribute("stroke-width","1.5"); flat.setAttribute("stroke-dasharray","5 4");
      svg.appendChild(flat);
    }
    const barWidth = Math.max(3, plotWidth / matches.length - 2);
    matches.forEach((m, idx) => {
      const x = xOf(idx); const bh = Math.abs(m.mvImpact)/chartMaxValue*(plotHeight/2); const pos = m.mvImpact >= 0;
      const bar = document.createElementNS("http://www.w3.org/2000/svg","rect");
      bar.setAttribute("x",x-barWidth/2); bar.setAttribute("y",pos?zeroY-bh:zeroY);
      bar.setAttribute("width",barWidth); bar.setAttribute("height",bh);
      bar.setAttribute("fill",pos?"rgba(56,161,105,1)":"rgba(197,48,48,1)"); bar.setAttribute("opacity","0.55");
      svg.appendChild(bar);
    });
    container.appendChild(svg);
  }
  
  function showChartTooltip(event, text, svgElement, svgX, svgY, mvImpact) {
    // Remove existing tooltip
    hideChartTooltip();
    
    // Convert SVG coordinates to page coordinates
    const svgRect = svgElement.getBoundingClientRect();
    const pageX = svgRect.left + svgX;
    const pageY = svgRect.top + svgY;
    
    const tooltip = document.createElement("div");
    tooltip.className = "chart-tooltip";
    
    // Parse tooltip text into lines and format with color
    const lines = text.split('\n');
    lines.forEach((line, idx) => {
      const lineEl = document.createElement("div");
      
      // Color MV Impact line based on sign
      if (line.startsWith("TPAR Impact:")) {
        lineEl.innerHTML = line.replace(
          /TPAR Impact: ([\+\-]?[\d\.]+)/,
          (match, value) => {
            const isPositive = mvImpact >= 0;
            const color = isPositive ? "rgba(56, 161, 105, 0.9)" : "rgba(197, 48, 48, 0.9)";
            return `TPAR Impact: <span style="color: ${color}">${value}</span>`;
          }
        );
      } else {
        lineEl.textContent = line;
      }
      
      tooltip.appendChild(lineEl);
    });
    
    tooltip.style.position = "fixed";
    tooltip.style.left = `${pageX}px`;
    
    // Position above or below based on MV impact sign
    if (mvImpact >= 0) {
      // Above bar
      tooltip.style.top = `${pageY}px`;
      tooltip.style.transform = "translate(-50%, -100%)";
    } else {
      // Below bar
      tooltip.style.top = `${pageY}px`;
      tooltip.style.transform = "translate(-50%, 0)";
    }
    
    document.body.appendChild(tooltip);
    
    // Position adjustment to keep on screen
    const rect = tooltip.getBoundingClientRect();
    if (rect.left < 10) {
      tooltip.style.left = "10px";
      tooltip.style.transform = tooltip.style.transform.replace("translate(-50%", "translate(0");
    } else if (rect.right > window.innerWidth - 10) {
      tooltip.style.left = `${window.innerWidth - 10}px`;
      tooltip.style.transform = tooltip.style.transform.replace("translate(-50%", "translate(-100%");
    }
    
    // Adjust vertical position if tooltip goes off screen
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
    if (existing) {
      existing.remove();
    }
  }