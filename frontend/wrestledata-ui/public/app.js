// ===============================
// Helpers
// ===============================

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
    // MV PANEL (DataGolf-style)
    // ========================================
    const mv = (data.metrics || {}).mat_value || {};
    const weightClass = data.weight_class;
    const mvPanel = document.getElementById("mv-panel");
    mvPanel.innerHTML = "";
    
    // A) Header row
    const headerRow = document.createElement("div");
    headerRow.className = "mv-header";
    
    const title = document.createElement("h2");
    title.textContent = "Mat Value (MV)";
    const tooltipIcon = document.createElement("span");
    tooltipIcon.className = "tooltip-icon";
    tooltipIcon.setAttribute("data-tooltip", "mv");
    tooltipIcon.textContent = "ⓘ";
    title.appendChild(tooltipIcon);
    headerRow.appendChild(title);
    
    const headerLink = document.createElement("a");
    headerLink.className = "mv-header-link";
    let leaderboardUrl = "/leaderboards/mat_value.html";
    if (weightClass) {
      leaderboardUrl += `?weight=${weightClass}`;
    }
    headerLink.href = leaderboardUrl;
    headerLink.textContent = "View MV Leaderboard";
    headerRow.appendChild(headerLink);
    mvPanel.appendChild(headerRow);
    
    // B) Primary metric row
    const primaryRow = document.createElement("div");
    primaryRow.className = "mv-primary-row";
    
    const mvValueContainer = document.createElement("div");
    mvValueContainer.className = "mv-value-container";
    
    const mvValue = document.createElement("div");
    mvValue.className = "mv-value";
    if (mv.mv_avg !== null && mv.mv_avg !== undefined) {
      mvValue.textContent = mv.mv_avg.toFixed(3);
    } else {
      mvValue.textContent = "—";
    }
    mvValueContainer.appendChild(mvValue);
    
    // Subtle MV bar under the number (contextual, scales with MV value)
    if (mv.mv_avg !== null && mv.mv_avg !== undefined) {
      const mvBarWrapper = document.createElement("div");
      mvBarWrapper.className = "mv-value-bar-wrapper";
      const mvBar = document.createElement("div");
      mvBar.className = "mv-value-bar";
      // Scale bar based on MV value (max ~6.0 for context)
      const MAX_MV_FOR_BAR = 6.0;
      const barWidth = Math.min(Math.abs(mv.mv_avg) / MAX_MV_FOR_BAR, 1) * 100;
      mvBar.style.width = `${barWidth}%`;
      mvBarWrapper.appendChild(mvBar);
      mvValueContainer.appendChild(mvBarWrapper);
    }
    
    primaryRow.appendChild(mvValueContainer);
    
    // MV Rank (Weight) - prominent badge with explicit label
    const badgesContainer = document.createElement("div");
    badgesContainer.className = "mv-badges";
    
    if (mv.rank_weight !== null && mv.rank_weight !== undefined && weightClass) {
      const rankLabel = document.createElement("span");
      rankLabel.className = "mv-rank-label";
      rankLabel.textContent = `MV Rank (${weightClass} lbs): `;
      badgesContainer.appendChild(rankLabel);
      badgesContainer.appendChild(createMVRankBadge(mv.rank_weight));
    }
    
    primaryRow.appendChild(badgesContainer);
    mvPanel.appendChild(primaryRow);
    
    // Contextual sublabel (e.g., "Top 10% at 149 lbs") - directly beneath MV
    if (mv.rank_weight !== null && mv.rank_weight !== undefined && weightClass) {
      // Calculate percentile (simplified - would need total wrestlers in weight class)
      // For now, estimate based on rank ranges
      let percentileText = "";
      if (mv.rank_weight <= 3) {
        percentileText = "Top 5%";
      } else if (mv.rank_weight <= 10) {
        percentileText = "Top 10%";
      } else if (mv.rank_weight <= 20) {
        percentileText = "Top 20%";
      } else if (mv.rank_weight <= 33) {
        percentileText = "Top 33%";
      } else {
        percentileText = "Top 50%";
      }
      
      const sublabel = document.createElement("div");
      sublabel.className = "mv-sublabel";
      sublabel.textContent = `${percentileText} at ${weightClass} lbs`;
      mvValueContainer.appendChild(sublabel);
    }
    
    // C) Description text (reduced opacity)
    const description = document.createElement("p");
    description.className = "mv-description";
    description.textContent = "Mat Value (MV) estimates a wrestler's per-match impact relative to opponent expectation.";
    mvPanel.appendChild(description);
    
    // D) Action links (chips)
    const actionsContainer = document.createElement("div");
    actionsContainer.className = "profile-actions";
    
    // View MV Leaderboard (this weight)
    if (weightClass) {
      const action1 = document.createElement("a");
      action1.className = "profile-action";
      action1.href = `/leaderboards/mat_value.html?weight=${weightClass}`;
      action1.textContent = "View MV Leaderboard (this weight)";
      actionsContainer.appendChild(action1);
    }
    
    // View xTP Team Impact
    const teamNameForAction = data.team;
    if (teamNameForAction) {
      const teamSlug = teamNameToSlug(teamNameForAction);
      const action2 = document.createElement("a");
      action2.className = "profile-action";
      action2.href = `/team.html?team=${teamSlug}#xtp-section`;
      action2.textContent = "View xTP Team Impact";
      actionsContainer.appendChild(action2);
    }
    
    // Compare vs Ranked Opponents
    const action3 = document.createElement("a");
    action3.className = "profile-action";
    action3.href = `/leaderboards/mat_value.html${weightClass ? `?weight=${weightClass}` : ''}`;
    action3.textContent = "Compare vs Ranked Opponents";
    actionsContainer.appendChild(action3);
    
    mvPanel.appendChild(actionsContainer);
    
    // ========================================
    // SKILL PROFILE PANEL (DataGolf-style)
    // ========================================
    const m = data.metrics || {};
    const skillPanel = document.getElementById("skill-panel");
    skillPanel.innerHTML = "";
    
    // Title
    const skillTitle = document.createElement("h2");
    skillTitle.textContent = "Skill Profile";
    skillPanel.appendChild(skillTitle);
    
    // Helper text (ties to MV)
    const skillHelper = document.createElement("p");
    skillHelper.className = "skill-helper";
    skillHelper.textContent = "These metrics explain how the wrestler generates Mat Value.";
    skillPanel.appendChild(skillHelper);
    
    // Skill rows with bars (SI+, DF+, APR+)
    const skillRowsContainer = document.createElement("div");
    
    // Helper function to calculate bar percentage
    const calculateBarPct = (value) => {
      if (value === null || value === undefined) return 0;
      // Clamp range: 80 to 150
      // pct = clamp((value - 80) / 70, 0, 1) * 100
      const clamped = Math.max(0, Math.min(1, (value - 80) / 70));
      return clamped * 100;
    };
    
    // SI+
    if (m.si_plus !== null && m.si_plus !== undefined) {
      const row = createSkillRow("SI+", m.si_plus, calculateBarPct(m.si_plus));
      skillRowsContainer.appendChild(row);
    }
    
    // DF+
    if (m.df_plus !== null && m.df_plus !== undefined) {
      const row = createSkillRow("DF+", m.df_plus, calculateBarPct(m.df_plus));
      skillRowsContainer.appendChild(row);
    }
    
    // APR+
    if (m.apr_plus !== null && m.apr_plus !== undefined) {
      const row = createSkillRow("APR+", m.apr_plus, calculateBarPct(m.apr_plus));
      skillRowsContainer.appendChild(row);
    }
    
    skillPanel.appendChild(skillRowsContainer);
    
    // Quick Stats (no bars)
    const quickStatsContainer = document.createElement("div");
    quickStatsContainer.className = "quick-stats";
    
    if (m.bonus_rate !== null && m.bonus_rate !== undefined) {
      quickStatsContainer.appendChild(createQuickStat("Bonus Rate", percentFormatter(m.bonus_rate)));
    }
    if (m.pin_rate !== null && m.pin_rate !== undefined) {
      quickStatsContainer.appendChild(createQuickStat("Pin Rate", percentFormatter(m.pin_rate)));
    }
    if (m.majors !== null && m.majors !== undefined) {
      quickStatsContainer.appendChild(createQuickStat("Majors", safe(m.majors)));
    }
    if (m.techs !== null && m.techs !== undefined) {
      quickStatsContainer.appendChild(createQuickStat("Tech Falls", safe(m.techs)));
    }
    if (m.pins !== null && m.pins !== undefined) {
      quickStatsContainer.appendChild(createQuickStat("Pins", safe(m.pins)));
    }
    
    skillPanel.appendChild(quickStatsContainer);
    
    // Record badges
    const r = data.record || {};
    const recordBadges = document.createElement("div");
    recordBadges.className = "record-badges";
    
    if (r.overall) {
      recordBadges.appendChild(createMiniBadge(`Overall ${safe(r.overall)}`));
    }
    if (r.vs_ranked) {
      recordBadges.appendChild(createMiniBadge(`vs Ranked ${safe(r.vs_ranked)}`));
    }
    if (r.vs_top10) {
      recordBadges.appendChild(createMiniBadge(`vs Top-10 ${safe(r.vs_top10)}`));
    }
    if (r.vs_top25) {
      recordBadges.appendChild(createMiniBadge(`vs Top-25 ${safe(r.vs_top25)}`));
    }
    
    skillPanel.appendChild(recordBadges);
    
    // ========================================
    // MV CONTEXT BLOCK
    // ========================================
    renderMVContext(data, mv.mv_avg);
    
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
    // MATCH IMPACT TIMELINE
    // ========================================
    renderMatchImpactTimeline(data, mv.mv_avg);
    
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
  
  function renderMVContext(data, seasonMV) {
    const container = document.getElementById("mv-context-rows");
    container.innerHTML = "";
    
    const ob = data.opponent_breakdown || {};
    const matches = data.match_list || [];
    const m = data.metrics || {};
    
    // 1. Best Win (by MV impact)
    const bestWinRow = document.createElement("div");
    bestWinRow.className = "mv-context-row";
    const bestWinLabel = document.createElement("span");
    bestWinLabel.className = "mv-context-label";
    bestWinLabel.textContent = "Best Win (by MV impact):";
    bestWinRow.appendChild(bestWinLabel);
    
    const bestWinValue = document.createElement("span");
    bestWinValue.className = "mv-context-value";
    if (ob.win_over_highest_rank) {
      const w = ob.win_over_highest_rank;
      const rankText = w.opponent_rank ? `#${w.opponent_rank} ` : "";
      bestWinValue.textContent = `${rankText}${safe(w.opponent_name)} (${safe(w.method)})`;
    } else {
      bestWinValue.textContent = "—";
    }
    bestWinRow.appendChild(bestWinValue);
    container.appendChild(bestWinRow);
    
    // 2. Worst Loss
    const worstLossRow = document.createElement("div");
    worstLossRow.className = "mv-context-row";
    const worstLossLabel = document.createElement("span");
    worstLossLabel.className = "mv-context-label";
    worstLossLabel.textContent = "Worst Loss:";
    worstLossRow.appendChild(worstLossLabel);
    
    const worstLossValue = document.createElement("span");
    worstLossValue.className = "mv-context-value";
    if (ob.worst_loss) {
      const l = ob.worst_loss;
      const rankText = l.opponent_rank ? `#${l.opponent_rank} ` : "";
      worstLossValue.textContent = `${rankText}${safe(l.opponent_name)} (${safe(l.method)})`;
    } else {
      // Check if undefeated
      const hasLoss = matches.some(m => m.result === "L");
      worstLossValue.textContent = hasLoss ? "—" : "None (undefeated)";
    }
    worstLossRow.appendChild(worstLossValue);
    container.appendChild(worstLossRow);
    
    // 3. Median Opponent Rank
    const medianRankRow = document.createElement("div");
    medianRankRow.className = "mv-context-row";
    const medianRankLabel = document.createElement("span");
    medianRankLabel.className = "mv-context-label";
    medianRankLabel.textContent = "Median Opponent Rank:";
    medianRankRow.appendChild(medianRankLabel);
    
    const medianRankValue = document.createElement("span");
    medianRankValue.className = "mv-context-value";
    const rankedOpponents = matches
      .map(m => m.opponent_rank)
      .filter(r => r !== null && r !== undefined && r !== "");
    
    if (rankedOpponents.length > 0) {
      rankedOpponents.sort((a, b) => a - b);
      const mid = Math.floor(rankedOpponents.length / 2);
      const median = rankedOpponents.length % 2 === 0
        ? (rankedOpponents[mid - 1] + rankedOpponents[mid]) / 2
        : rankedOpponents[mid];
      medianRankValue.textContent = `#${Math.round(median)}`;
    } else {
      medianRankValue.textContent = "N/A";
    }
    medianRankRow.appendChild(medianRankValue);
    container.appendChild(medianRankRow);
    
    // 4. MV Composition
    const compositionRow = document.createElement("div");
    compositionRow.className = "mv-context-row";
    const compositionLabel = document.createElement("span");
    compositionLabel.className = "mv-context-label";
    compositionLabel.textContent = "MV Composition:";
    compositionLabel.setAttribute("title", "Percentage of MV contributed by bonus wins (pins, techs, majors) vs decisions");
    compositionRow.appendChild(compositionLabel);
    
    const compositionValue = document.createElement("span");
    compositionValue.className = "mv-context-value";
    
    // Calculate composition from match data
    let bonusWins = 0;
    let decisions = 0;
    matches.forEach(match => {
      if (match.result === "W") {
        const method = (match.method || "").toUpperCase();
        if (method === "PIN" || method === "FALL" || method === "TF" || method === "MD" || method === "INJ") {
          bonusWins++;
        } else {
          decisions++;
        }
      }
    });
    
    const totalWins = bonusWins + decisions;
    if (totalWins > 0) {
      const bonusPct = Math.round((bonusWins / totalWins) * 100);
      const decisionPct = 100 - bonusPct;
      compositionValue.textContent = `Bonus-driven (${bonusPct}%) | Decisions (${decisionPct}%)`;
    } else {
      compositionValue.textContent = "—";
    }
    compositionRow.appendChild(compositionValue);
    container.appendChild(compositionRow);
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
  
  function renderMatchTable(matches, seasonMV) {
    const tbody = document.querySelector("#match-table tbody");
    tbody.innerHTML = "";
  
    // Sort chronologically (oldest first) for timeline consistency
    const sortedMatches = [...matches].sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  
    sortedMatches.forEach((match) => {
      const tr = document.createElement("tr");
  
      const add = (v) => {
        const td = document.createElement("td");
        td.textContent = safe(v);
        tr.appendChild(td);
      };
  
      add(match.date);
  
      // Opponent with link
      const oppTd = document.createElement("td");
      if (match.opponent_id) {
        const a = document.createElement("a");
        a.href = `/wrestler.html?id=${match.opponent_id}`;
        a.textContent = safe(match.opponent_name);
        oppTd.appendChild(a);
      } else {
        oppTd.textContent = safe(match.opponent_name);
      }
      tr.appendChild(oppTd);
  
      // Opponent team with link
      const oppTeamTd = document.createElement("td");
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
      add(match.opponent_team_rank ? "#" + match.opponent_team_rank : "—");
      add(match.opponent_weight);
      
      // Opponent rank with badge if ranked
      const oppRankTd = document.createElement("td");
      if (match.opponent_rank) {
        oppRankTd.appendChild(createRankBadge(match.opponent_rank));
      } else {
        oppRankTd.textContent = "—";
      }
      tr.appendChild(oppRankTd);
      
      // Result
      const resultTd = document.createElement("td");
      resultTd.textContent = safe(match.result);
      tr.appendChild(resultTd);
      
      add(match.method);
      
      // Impact column (MV delta) - use stored value from JSON
      const impactTd = document.createElement("td");
      impactTd.className = "num match-impact-cell";
      const mvImpact = match.mv_impact;
      if (mvImpact !== null && mvImpact !== undefined) {
        const impactText = mvImpact > 0 ? `+${mvImpact.toFixed(1)}` : mvImpact.toFixed(1);
        impactTd.textContent = impactText;
        impactTd.className += mvImpact > 0 ? " impact-positive" : mvImpact < 0 ? " impact-negative" : "";
        impactTd.setAttribute("title", "Contribution to season Mat Value from this match");
      } else {
        impactTd.textContent = "—";
      }
      tr.appendChild(impactTd);
      
      add(match.score);
      add(match.duration);
      add(match.event);
  
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
    
    // Create SVG chart
    const chartHeight = 200;
    const chartWidth = Math.max(600, matchData.length * 20);
    const padding = { top: 20, right: 20, bottom: 20, left: 20 };
    const plotWidth = chartWidth - padding.left - padding.right;
    const plotHeight = chartHeight - padding.top - padding.bottom;
    
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", chartWidth);
    svg.setAttribute("height", chartHeight);
    svg.setAttribute("class", "match-impact-chart");
    svg.style.display = "block";
    
    // Find max absolute value for scaling
    const maxAbsValue = Math.max(...matchData.map(m => Math.abs(m.mvImpact || 0)), 1);
    const zeroY = padding.top + plotHeight / 2;
    
    // Draw zero line
    const zeroLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
    zeroLine.setAttribute("x1", padding.left);
    zeroLine.setAttribute("y1", zeroY);
    zeroLine.setAttribute("x2", padding.left + plotWidth);
    zeroLine.setAttribute("y2", zeroY);
    zeroLine.setAttribute("stroke", "var(--border)");
    zeroLine.setAttribute("stroke-width", "1");
    svg.appendChild(zeroLine);
    
    // Calculate rolling average (last 5 matches)
    const rollingAverages = [];
    for (let i = 0; i < matchData.length; i++) {
      const startIdx = Math.max(0, i - 4);
      const window = matchData.slice(startIdx, i + 1);
      const avg = window.reduce((sum, m) => sum + (m.mvImpact || 0), 0) / window.length;
      rollingAverages.push(avg);
    }
    
    // Draw rolling average line
    if (rollingAverages.length > 1) {
      const avgPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
      let pathData = "";
      rollingAverages.forEach((avg, idx) => {
        const x = padding.left + (idx / (matchData.length - 1)) * plotWidth;
        const y = zeroY - (avg / maxAbsValue) * (plotHeight / 2);
        if (idx === 0) {
          pathData = `M ${x} ${y}`;
        } else {
          pathData += ` L ${x} ${y}`;
        }
      });
      avgPath.setAttribute("d", pathData);
      avgPath.setAttribute("stroke", "var(--muted)");
      avgPath.setAttribute("stroke-width", "1.5");
      avgPath.setAttribute("fill", "none");
      svg.appendChild(avgPath);
    }
    
    // Draw bars
    matchData.forEach((match, idx) => {
      const x = padding.left + (idx / (matchData.length - 1)) * plotWidth;
      const barWidth = Math.max(2, plotWidth / matchData.length - 2);
      const barHeight = Math.abs(match.mvImpact) / maxAbsValue * (plotHeight / 2);
      const isPositive = match.mvImpact >= 0;
      
      const bar = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      bar.setAttribute("x", x - barWidth / 2);
      bar.setAttribute("y", isPositive ? zeroY - barHeight : zeroY);
      bar.setAttribute("width", barWidth);
      bar.setAttribute("height", barHeight);
      bar.setAttribute("fill", isPositive ? "rgba(0, 194, 168, 0.4)" : "rgba(220, 90, 90, 0.4)");
      bar.setAttribute("class", "match-impact-bar");
      
      // Tooltip data
      const rankText = match.opponentRank ? `#${match.opponentRank} ` : "";
      const tooltipText = `${match.date}\n${rankText}${match.opponent}\n${match.result} (${match.method || "N/A"})\nMV: ${match.mvImpact > 0 ? '+' : ''}${match.mvImpact.toFixed(1)}`;
      bar.setAttribute("data-tooltip", tooltipText);
      
      // Add hover event
      bar.addEventListener("mouseenter", (e) => {
        showChartTooltip(e, tooltipText, x, isPositive ? zeroY - barHeight : zeroY + barHeight);
      });
      bar.addEventListener("mouseleave", () => {
        hideChartTooltip();
      });
      
      svg.appendChild(bar);
    });
    
    container.appendChild(svg);
    
    // Store match data for toggle functionality
    container.dataset.matchData = JSON.stringify(matchData);
  }
  
  function showChartTooltip(event, text, x, y) {
    // Remove existing tooltip
    hideChartTooltip();
    
    const tooltip = document.createElement("div");
    tooltip.className = "chart-tooltip";
    tooltip.textContent = text;
    tooltip.style.position = "absolute";
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y - 10}px`;
    tooltip.style.transform = "translate(-50%, -100%)";
    
    document.body.appendChild(tooltip);
    
    // Position adjustment to keep on screen
    const rect = tooltip.getBoundingClientRect();
    if (rect.left < 10) {
      tooltip.style.left = "10px";
      tooltip.style.transform = "translate(0, -100%)";
    } else if (rect.right > window.innerWidth - 10) {
      tooltip.style.left = `${window.innerWidth - x - 10}px`;
      tooltip.style.transform = "translate(-100%, -100%)";
    }
  }
  
  function hideChartTooltip() {
    const existing = document.querySelector(".chart-tooltip");
    if (existing) {
      existing.remove();
    }
  }