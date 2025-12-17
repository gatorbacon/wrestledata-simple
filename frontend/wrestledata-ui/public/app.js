// ===============================
// Helpers
// ===============================

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
    const url = `/mat_value/${season}/mat_value_${season}.json`;
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
  
  function loadWrestlerProfile(id) {
    const url = `/wrestlers/2026/by_id/${id}.json`;
  
    fetch(url)
      .then(res => {
        if (!res.ok) throw new Error("Could not load wrestler JSON");
        return res.json();
      })
      .then(data => renderWrestlerProfile(data))
      .catch(err => {
        console.error("Error loading:", err);
        document.getElementById("wrestler-name").textContent = "Not Found";
        document.getElementById("wrestler-meta").textContent = err.message;
      });
  }
  
  // ===============================
  // Rendering
  // ===============================
  
  function renderWrestlerProfile(data) {
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
  
    // Render team name as link
    const metaEl = document.getElementById("wrestler-meta");
    const teamName = safe(data.team);
    const season = safe(data.year);
    if (teamName && teamName !== "—") {
      const teamSlug = teamNameToSlug(teamName);
      const teamLink = document.createElement("a");
      teamLink.href = `/team.html?team=${teamSlug}`;
      teamLink.textContent = teamName;
      metaEl.innerHTML = "";
      metaEl.appendChild(teamLink);
      metaEl.appendChild(document.createTextNode(` · Season ${season}`));
    } else {
      metaEl.textContent = `Season ${season}`;
    }
  
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
    title.textContent = "Mat Value (MV)";
    const tooltipIcon = document.createElement("span");
    tooltipIcon.className = "tooltip-icon";
    tooltipIcon.setAttribute("data-tooltip", "mv");
    tooltipIcon.textContent = "ⓘ";
    title.appendChild(tooltipIcon);
    headerRow.appendChild(title);
    
    // MV leaderboard URL (used by rank badge link only)
    let leaderboardUrl = "/leaderboards/mat_value.html";
    if (weightClass) {
      leaderboardUrl += `?weight=${weightClass}`;
    }
    mvSection.appendChild(headerRow);
    
    // Divider
    const divider = document.createElement("div");
    divider.className = "section-divider";
    mvSection.appendChild(divider);
    
    // B) Primary metric row
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
    if (mv.mv_avg !== null && mv.mv_avg !== undefined) {
      const sign = mv.mv_avg >= 0 ? "+" : "";
      mvValue.textContent = `${sign}${mv.mv_avg.toFixed(3)}`;
    } else {
      mvValue.textContent = "—";
    }
    primaryRow.appendChild(mvValue);
    
    // Percentile bar container (below the row, will be populated after percentile is computed)
    const percentileBarContainer = document.createElement("div");
    percentileBarContainer.className = "mv-percentile-bar-container";
    mvSection.appendChild(primaryRow);
    mvSection.appendChild(percentileBarContainer);
    
    // Compute percentile and update display asynchronously
    if (mv.mv_avg !== null && mv.mv_avg !== undefined && weightClass && data.wrestler_id) {
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
          const rankSpan = rankContainer.querySelector(".mv-rank-value");
          if (rankSpan) {
            rankSpan.textContent = `#${mv.rank_weight}`;
          }
        }
      });
    } else if (mv.mv_avg !== null && mv.mv_avg !== undefined) {
      // No wrestler_id, but we have MV - show basic display (neutral)
      mvValue.className = "mv-number";
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
    
    // SI+ (Scoring)
    if (m.si_plus !== null && m.si_plus !== undefined) {
      const row = createSkillRowWithBaseline("SI+ (Scoring)", m.si_plus);
      skillRowsContainer.appendChild(row);
    }
    
    // DF+ (Defense)
    if (m.df_plus !== null && m.df_plus !== undefined) {
      const row = createSkillRowWithBaseline("DF+ (Defense)", m.df_plus);
      skillRowsContainer.appendChild(row);
    }
    
    // APR+ (Pin Rate)
    if (m.apr_plus !== null && m.apr_plus !== undefined) {
      const row = createSkillRowWithBaseline("APR+ (Pin Rate)", m.apr_plus);
      skillRowsContainer.appendChild(row);
    }
    
    skillSection.appendChild(skillRowsContainer);
    
    // Synthesized profile description
    const profileDesc = generateSkillProfileDescription(m);
    if (profileDesc) {
      const descEl = document.createElement("p");
      descEl.className = "skill-profile-description";
      descEl.textContent = profileDesc;
      skillSection.appendChild(descEl);
    }
    
    // ========================================
    // MATCH IMPACT TIMELINE (PROMOTED - BEFORE CONTEXT)
    // ========================================
    renderMatchImpactTimeline(data, mv.mv_avg);
    
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
    indicator.setAttribute("title", "Based on last 5 matches vs season average Mat Value");
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
    
    // Display only method (DEC, MD, TF, FALL, etc.)
    const methodText = safe(method || "—").toUpperCase();
    badge.textContent = methodText;
    
    // Tooltip: "Win by Technical Fall" or "Loss by Decision"
    const outcome = isWin ? "Win" : "Loss";
    const methodName = methodText === "DEC" ? "Decision" :
                      methodText === "MD" ? "Major Decision" :
                      methodText === "TF" ? "Technical Fall" :
                      methodText === "FALL" || methodText === "PIN" ? "Fall" :
                      methodText === "INJ" ? "Injury Default" :
                      methodText === "DQ" ? "Disqualification" :
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
      const mvImpact = match.mv_impact;
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
  
  function renderMatchImpactTimeline(data, seasonMV) {
    const container = document.getElementById("match-impact-chart-container");
    container.innerHTML = "";
    
    const matches = data.match_list || [];
    if (matches.length === 0) {
      container.textContent = "No match data available";
      return;
    }
    
    // Sort matches chronologically (oldest first)
    const sortedMatches = [...matches].sort((a, b) => (a.date || "").localeCompare(b.date || ""));
    
    // Use stored mv_impact from JSON (computed in Python)
    const matchData = sortedMatches.map(match => {
      const mvImpact = match.mv_impact;
      return {
        date: match.date,
        opponent: match.opponent_name,
        opponentRank: match.opponent_rank,
        result: match.result,
        method: match.method,
        mvImpact: mvImpact,
      };
    }).filter(m => m.mvImpact !== null && m.mvImpact !== undefined);
    
    if (matchData.length === 0) {
      container.textContent = "No valid match data for visualization";
      return;
    }
    
    // Create SVG chart (increased height for prominence)
    const chartHeight = 250;
    // Make chart width responsive to available container width to avoid clipping
    const containerWidth = container.clientWidth || 600;
    const chartWidth = containerWidth;
    const padding = { top: 30, right: 20, bottom: 30, left: 20 };
    const plotWidth = chartWidth - padding.left - padding.right;
    const plotHeight = chartHeight - padding.top - padding.bottom;
    
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", chartWidth);
    svg.setAttribute("height", chartHeight);
    svg.setAttribute("class", "match-impact-chart");
    svg.style.display = "block";
    
    // Find max absolute value for scaling
    const maxAbsValue = Math.max(...matchData.map(m => Math.abs(m.mvImpact || 0)), 1);
    const chartMaxValue = Math.max(6, maxAbsValue); // Use at least 6 for fixed gridlines
    const zeroY = padding.top + plotHeight / 2;
    
    // Draw horizontal gridlines at fixed MV values: +6, +4, +2, 0, -2, -4, -6
    const gridValues = [6, 4, 2, 0, -2, -4, -6];
    
    gridValues.forEach(gridValue => {
      const gridY = zeroY - (gridValue / chartMaxValue) * (plotHeight / 2);
      
      // Only draw if within chart bounds
      if (gridY >= padding.top && gridY <= padding.top + plotHeight) {
        const gridline = document.createElementNS("http://www.w3.org/2000/svg", "line");
        gridline.setAttribute("x1", padding.left);
        gridline.setAttribute("y1", gridY);
        gridline.setAttribute("x2", padding.left + plotWidth);
        gridline.setAttribute("y2", gridY);
        
        if (gridValue === 0) {
          // Zero line slightly more prominent
          gridline.setAttribute("stroke", "rgba(255,255,255,0.12)");
          gridline.setAttribute("stroke-width", "1");
        } else {
          // Other gridlines subtle
          gridline.setAttribute("stroke", "rgba(255,255,255,0.06)");
          gridline.setAttribute("stroke-width", "1");
        }
        
        gridline.setAttribute("class", "chart-gridline");
        svg.appendChild(gridline);
      }
    });
    
    // Calculate rolling average (last 5 matches) - season average MV line
    const rollingAverages = [];
    for (let i = 0; i < matchData.length; i++) {
      const startIdx = Math.max(0, i - 4);
      const window = matchData.slice(startIdx, i + 1);
      const avg = window.reduce((sum, m) => sum + (m.mvImpact || 0), 0) / window.length;
      rollingAverages.push(avg);
    }
    
    // Draw bars with default opacity (drawn first so white line appears on top)
    const bars = [];
    matchData.forEach((match, idx) => {
      const x = padding.left + (idx / (matchData.length - 1)) * plotWidth;
      const barWidth = Math.max(3, plotWidth / matchData.length - 2);
      const barHeight = Math.abs(match.mvImpact) / chartMaxValue * (plotHeight / 2);
      const isPositive = match.mvImpact >= 0;
      
      const bar = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      bar.setAttribute("x", x - barWidth / 2);
      bar.setAttribute("y", isPositive ? zeroY - barHeight : zeroY);
      bar.setAttribute("width", barWidth);
      bar.setAttribute("height", barHeight);
      bar.setAttribute("fill", isPositive ? "rgba(0, 194, 168, 1)" : "rgba(220, 90, 90, 1)");
      bar.setAttribute("opacity", "0.55"); // Default opacity (DataGolf-style)
      bar.setAttribute("class", "match-impact-bar");
      bar.setAttribute("data-index", idx);
      bar.setAttribute("data-x", x);
      bar.setAttribute("data-is-positive", isPositive);
      bar.setAttribute("data-bar-height", barHeight);
      
      bars.push({
        element: bar,
        index: idx,
        x: x,
        match: match,
        isPositive: isPositive,
        barHeight: barHeight
      });
      
      svg.appendChild(bar);
    });
    
    // Draw rolling average line AFTER bars (so it appears in front)
    if (rollingAverages.length > 1) {
      const avgPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
      let pathData = "";
      rollingAverages.forEach((avg, idx) => {
        const x = padding.left + (idx / (matchData.length - 1)) * plotWidth;
        const y = zeroY - (avg / chartMaxValue) * (plotHeight / 2);
        if (idx === 0) {
          pathData = `M ${x} ${y}`;
        } else {
          pathData += ` L ${x} ${y}`;
        }
      });
      avgPath.setAttribute("d", pathData);
      avgPath.setAttribute("stroke", "rgba(255,255,255,0.6)");
      avgPath.setAttribute("stroke-width", "1.5");
      avgPath.setAttribute("fill", "none");
      avgPath.setAttribute("class", "rolling-avg-line");
      svg.appendChild(avgPath);
    }
    
    // Create dot element for white line (will be positioned on hover)
    const lineDot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    lineDot.setAttribute("r", "3");
    lineDot.setAttribute("fill", "rgba(255,255,255,0.9)");
    lineDot.setAttribute("class", "rolling-avg-dot");
    lineDot.setAttribute("opacity", "0");
    svg.appendChild(lineDot);
    
    container.appendChild(svg);
    
    // Store match data and bars for hover interaction
    container.dataset.matchData = JSON.stringify(matchData);
    container.dataset.bars = JSON.stringify(bars.map(b => ({
      index: b.index,
      x: b.x,
      match: b.match
    })));
    
    // DataGolf-style hover snap: single mousemove listener on SVG
    let activeIndex = -1;
    
    svg.addEventListener("mousemove", (e) => {
      const svgRect = svg.getBoundingClientRect();
      const mouseX = e.clientX - svgRect.left;
      
      // Convert mouse X to nearest match index (global hover zone)
      const relativeX = mouseX - padding.left;
      const normalizedX = Math.max(0, Math.min(1, relativeX / plotWidth));
      let index = Math.round(normalizedX * (matchData.length - 1));
      index = Math.max(0, Math.min(matchData.length - 1, index));
      
      // Only update if index changed
      if (index !== activeIndex) {
        activeIndex = index;
        
        // Update bar opacities (no color change, only opacity)
        bars.forEach((bar, idx) => {
          if (idx === activeIndex) {
            bar.element.setAttribute("opacity", "1.0");
          } else {
            bar.element.setAttribute("opacity", "0.55");
          }
        });
      }
      
      // Always update tooltip and dot position
      const activeMatch = matchData[activeIndex];
      const activeBar = bars[activeIndex];
      if (activeMatch && activeBar) {
        // Get season average MV at this index
        const seasonAvgMV = rollingAverages[activeIndex];
        
        // Format date as YYYY-MM-DD
        const dateStr = activeMatch.date || "";
        
        // Build tooltip with 4 lines
        const impactValue = activeMatch.mvImpact.toFixed(1);
        const impactSign = activeMatch.mvImpact > 0 ? '+' : '';
        const seasonAvgStr = seasonAvgMV !== undefined ? seasonAvgMV.toFixed(1) : '—';
        
        const tooltipLines = [
          dateStr,
          activeMatch.opponent,
          `MV Impact: ${impactSign}${impactValue}`,
          `Season Avg MV: ${seasonAvgStr}`
        ];
        const tooltipText = tooltipLines.join('\n');
        
        // Tooltip positioning: above for positive, below for negative
        const tooltipY = activeBar.isPositive 
          ? zeroY - activeBar.barHeight - 12  // Above bar
          : zeroY + activeBar.barHeight + 12;  // Below bar
        
        showChartTooltip(e, tooltipText, svg, activeBar.x, tooltipY, activeMatch.mvImpact);
        
        // Update white line dot position
        if (rollingAverages.length > activeIndex) {
          const dotX = activeBar.x;
          const dotY = zeroY - (seasonAvgMV / chartMaxValue) * (plotHeight / 2);
          lineDot.setAttribute("cx", dotX);
          lineDot.setAttribute("cy", dotY);
          lineDot.setAttribute("opacity", "1");
        }
      }
    });
    
    svg.addEventListener("mouseleave", () => {
      // Reset all bars to default opacity
      bars.forEach(bar => {
        bar.element.setAttribute("opacity", "0.55");
      });
      // Hide dot
      lineDot.setAttribute("opacity", "0");
      activeIndex = -1;
      hideChartTooltip();
    });
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
      if (line.startsWith("MV Impact:")) {
        lineEl.innerHTML = line.replace(
          /MV Impact: ([\+\-]?[\d\.]+)/,
          (match, value) => {
            const isPositive = mvImpact >= 0;
            const color = isPositive ? "rgba(0, 194, 168, 0.9)" : "rgba(220, 90, 90, 0.9)";
            return `MV Impact: <span style="color: ${color}">${value}</span>`;
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