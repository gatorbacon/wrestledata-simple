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
    // Get gender from URL or default
    const gender = getGenderFromURL();
    
    // Load the full MV dataset (HS path)
    const url = `/data/mat_value/${gender}/${season}/mat_value_${season}.json`;
    console.log(`[HS Wrestler] Loading MV data from ${url}...`);
    
    const res = await fetch(url);
    if (!res.ok) {
      console.warn(`[HS Wrestler] Failed to load MV data: ${res.status}`);
      return null;
    }
    
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
    console.error("[HS Wrestler] Error computing filtered MV rank and percentile:", err);
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
  // Fetch Wrestler JSON (HS KY)
  // ===============================
  // Note: hs_config.js must be loaded before this file
  
  async function loadWrestlerProfile(id) {
    const gender = getGenderFromURL();
    const season = getSeasonFromURL();

    try {
      const profileUrl = `/data/wrestlers/${gender}/${season}/by_id/${id}.json`;
      const profileResponse = await fetch(profileUrl);
      if (!profileResponse.ok) {
        if (profileResponse.status === 404) {
          document.getElementById("wrestler-name").textContent = "Wrestler Not Found";
          document.getElementById("wrestler-meta").textContent = `Wrestler ID ${id} not found in HS ${gender} profiles for season ${season}`;
          return;
        }
        throw new Error(`Failed to load profile: ${profileResponse.status} ${profileResponse.statusText}`);
      }
      const profile = await profileResponse.json();

      // Auto-upgrade to unified career view when a career profile exists
      const careerId = profile.career && profile.career.career_id;
      if (careerId) {
        await loadCareerProfile(careerId);
        return;
      }

      // Fallback: no career profile — render single-season view
      renderWrestlerProfile(profile);
    } catch (err) {
      document.getElementById("wrestler-name").textContent = "Error Loading Profile";
      document.getElementById("wrestler-meta").textContent = err.message || "Failed to load wrestler profile";
    }
  }
  
  // ===============================
  // Career Profile (multi-season)
  // ===============================

  async function loadCareerProfile(careerId) {
    const gender = getGenderFromURL();
    try {
      const url = `/data/careers/${gender}/${careerId}.json`;
      const resp = await fetch(url);
      if (!resp.ok) {
        if (resp.status === 404) {
          document.getElementById("wrestler-name").textContent = "Career Not Found";
          document.getElementById("wrestler-meta").textContent = `No career profile for ${careerId}`;
          return;
        }
        throw new Error(`${resp.status} ${resp.statusText}`);
      }
      const data = await resp.json();
      renderCareerProfile(data);
    } catch (err) {
      document.getElementById("wrestler-name").textContent = "Error Loading Career";
      document.getElementById("wrestler-meta").textContent = err.message || "Failed to load career profile";
    }
  }

  function renderCareerProfile(data) {
    const gender = getGenderFromURL();
    const seasons = data.seasons || [];
    const mostRecent = seasons[0]; // sorted newest first

    // === Header ===
    document.getElementById("wrestler-name").textContent = data.canonical_name || "—";
    const _titleTeam = (mostRecent && mostRecent.team) ? mostRecent.team : null;
    const _titleGenderLabel = gender === "girls" ? "Kentucky Girls High School Wrestling" : "Kentucky High School Wrestling";
    document.title = _titleTeam
      ? `${data.canonical_name} | ${_titleGenderLabel} | ${_titleTeam} | KentuckyMat`
      : `${data.canonical_name} | ${_titleGenderLabel} | KentuckyMat`;
    sendPageView();
    const _cr = data.career_record || {};
    const _crWins = _cr.wins ?? 0;
    const _crLosses = _cr.losses ?? 0;
    const _crPct = _cr.win_pct != null ? `(${_cr.win_pct.toFixed(3)})` : "";
    const _crRecord = `${_crWins}-${_crLosses} ${_crPct}`.trim();
    const _metaTeamPart = _titleTeam ? `, ${_titleTeam}` : "";
    const _metaGenderPart = gender === "girls" ? "Kentucky girls high school wrestling" : "Kentucky high school wrestling";
    setMetaDescription(`${data.canonical_name} career record ${_crRecord}, ${_metaGenderPart}${_metaTeamPart}. Full match history, stats, and season breakdowns on KentuckyMat.`);
    setCanonicalURL(window.location.href);

    const taglineEl = document.getElementById("wrestler-tagline");
    taglineEl.innerHTML = "";
    if (mostRecent) {
      // Rank pill — most important secondary info, visually dominant
      if (mostRecent.current_rank != null) {
        const rankPill = document.createElement("span");
        rankPill.className = "career-header-rank-pill";
        rankPill.textContent = `#${mostRecent.current_rank}`;
        taglineEl.appendChild(rankPill);
        taglineEl.appendChild(document.createTextNode(" "));
      }
      // Weight · Team on same line, muted
      const infoSpan = document.createElement("span");
      infoSpan.className = "career-header-info";
      if (mostRecent.weight_class) infoSpan.appendChild(document.createTextNode(`${mostRecent.weight_class} lbs`));
      if (mostRecent.team) {
        if (mostRecent.weight_class) infoSpan.appendChild(document.createTextNode(" · "));
        const teamLink = document.createElement("a");
        teamLink.href = buildPageURL("team.html", gender, { team: teamNameToSlug(mostRecent.team) });
        teamLink.textContent = mostRecent.team;
        infoSpan.appendChild(teamLink);
      }
      taglineEl.appendChild(infoSpan);
    }

    // Team is now in tagline — clear meta to avoid a third line
    const metaEl = document.getElementById("wrestler-meta");
    metaEl.innerHTML = "";

    // === Hide NCAA/unused sections ===
    ["mv-section", "match-impact-section", "skill-section", "mv-context-section", "xtp-section"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = "none";
    });
    const summaryGrid = document.querySelector(".profile-summary-grid");
    if (summaryGrid) summaryGrid.style.display = "none";

    // === Clear existing dynamic sections ===
    [".section--match-history", "#career-profile-section", "#career-summary-section", "#season-stats-section"].forEach(sel => {
      const el = document.querySelector(sel);
      if (el) el.remove();
    });

    // === Build career section ===
    const pageContainer = document.querySelector(".page-container");
    const section = document.createElement("section");
    section.id = "career-profile-section";
    section.className = "section";
    pageContainer.appendChild(section);

    // Career Record
    const cr = data.career_record || {};
    if (cr.wins != null) {
      const recordBlock = document.createElement("div");
      recordBlock.style.cssText = "margin-bottom: 12px;";
      const lbl = document.createElement("div");
      lbl.style.cssText = "font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;";
      lbl.textContent = "Career Record";
      const pctStr = cr.win_pct != null ? ` (${cr.win_pct.toFixed(3).replace(/^0\./, '.')})` : "";
      const val = document.createElement("div");
      val.style.cssText = "font-size: 1.125rem; line-height: 1.5;";
      val.innerHTML = `<strong>${cr.wins ?? 0}–${cr.losses ?? 0}</strong><span style="color:var(--muted)">${pctStr}</span>`;
      recordBlock.appendChild(lbl);
      recordBlock.appendChild(val);
      section.appendChild(recordBlock);
    }

    // Career Summary table (only if more than one season)
    if (seasons.length > 1) {
      const summaryTitle = document.createElement("h2");
      summaryTitle.className = "section-title-career-summary";
      summaryTitle.textContent = "Career Summary";
      section.appendChild(summaryTitle);

      const summaryHr = document.createElement("hr");
      summaryHr.className = "career-header-rule";
      section.appendChild(summaryHr);

      const table = document.createElement("table");
      table.className = "career-summary-table career-summary-desktop";
      table.style.cssText = "width:100%;font-size:0.875rem;margin-top:8px;margin-bottom:16px;";
      const thead = document.createElement("thead");
      thead.innerHTML = "<tr><th>Season</th><th>Grade</th><th>Team</th><th>Record</th><th>Regional Place</th><th>State Place</th></tr>";
      table.appendChild(thead);
      const tbody = document.createElement("tbody");

      // Mobile cards list (parallel to table)
      const summaryCards = document.createElement("div");
      summaryCards.className = "career-summary-cards career-summary-mobile";
      summaryCards.style.cssText = "margin-top:12px;margin-bottom:28px;";

      seasons.forEach((s, idx) => {
        const gradeStr = _gradeLabel(s.grade);
        const regionalTracked = s.regional_data_tracked !== false;
        const regStr = !regionalTracked ? "N/A" : (s.regional_place != null ? ordinal(s.regional_place) : "—");
        const stateStr = s.state_place != null ? ordinal(s.state_place) : "—";

        // Desktop table row
        const tr = document.createElement("tr");
        tr.style.cursor = "pointer";
        if (idx === 0) tr.classList.add("active-season-row");
        const cells = [
          { text: String(s.season) },
          { text: gradeStr },
          { text: s.team || "—", isTeam: true, team: s.team },
          { text: s.record || "—" },
          { text: regStr },
          { text: stateStr },
        ];
        cells.forEach(cell => {
          const td = document.createElement("td");
          if (cell.isTeam && cell.team) {
            const a = document.createElement("a");
            a.href = buildPageURL("team.html", gender, { team: teamNameToSlug(cell.team) });
            a.textContent = cell.team;
            a.onclick = e => e.stopPropagation();
            td.appendChild(a);
          } else {
            td.textContent = cell.text;
          }
          tr.appendChild(td);
        });
        tr.addEventListener("click", () => activateSeason(idx));
        tbody.appendChild(tr);

        // Mobile card: [left: season+team] [right: Record | Reg | State cells]
        const card = document.createElement("div");
        card.className = "career-summary-card" + (idx === 0 ? " active" : "");
        card.style.cursor = "pointer";

        // Left: season/grade + team
        const cardLeft = document.createElement("div");
        cardLeft.className = "career-summary-card-left";

        const seasonGrade = document.createElement("div");
        seasonGrade.className = "career-summary-card-season";
        seasonGrade.textContent = `${s.season} · ${gradeStr}`;
        cardLeft.appendChild(seasonGrade);

        if (s.team) {
          const teamA = document.createElement("a");
          teamA.href = buildPageURL("team.html", gender, { team: teamNameToSlug(s.team) });
          teamA.textContent = s.team;
          teamA.className = "career-summary-card-team";
          teamA.onclick = e => e.stopPropagation();
          cardLeft.appendChild(teamA);
        }
        card.appendChild(cardLeft);

        // Right: labeled cells — Record | Reg | State
        const cardRight = document.createElement("div");
        cardRight.className = "career-summary-card-right";

        const mkLabeledCell = (label, content) => {
          const cell = document.createElement("div");
          cell.className = "career-summary-place-cell";
          const lbl = document.createElement("span");
          lbl.className = "career-summary-place-label";
          lbl.textContent = label;
          cell.appendChild(lbl);
          cell.appendChild(content);
          return cell;
        };

        const mkMedalOrDash = (place, tracked = true) => {
          if (place != null && place >= 1 && place <= 8) {
            const img = document.createElement("img");
            img.src = `/img/medals/${place}.png`;
            img.width = 22; img.height = 22;
            img.alt = ordinal(place);
            img.style.display = "block";
            return img;
          }
          const dash = document.createElement("span");
          dash.className = "career-summary-place-dash";
          dash.textContent = !tracked ? "N/A" : (place != null ? ordinal(place) : "—");
          return dash;
        };

        // Record cell
        const recVal = document.createElement("span");
        recVal.className = "career-summary-card-record";
        recVal.textContent = s.record || "—";
        cardRight.appendChild(mkLabeledCell("Record", recVal));

        cardRight.appendChild(mkLabeledCell("Reg", mkMedalOrDash(s.regional_place, s.regional_data_tracked !== false)));
        cardRight.appendChild(mkLabeledCell("State", mkMedalOrDash(s.state_place)));
        card.appendChild(cardRight);

        card.addEventListener("click", () => {
          summaryCards.querySelectorAll(".career-summary-card").forEach((c, i) => c.classList.toggle("active", i === idx));
          activateSeason(idx);
        });
        summaryCards.appendChild(card);
      });

      table.appendChild(tbody);
      section.appendChild(table);
      section.appendChild(summaryCards);
    }

    // Season tabs — desktop only (mobile tabs are injected inside the panel)
    if (seasons.length > 0) {
      const tabsDiv = document.createElement("div");
      tabsDiv.className = "season-tabs season-tabs--desktop";
      tabsDiv.id = "season-tabs";
      seasons.forEach((s, idx) => {
        const btn = document.createElement("button");
        btn.className = "season-tab" + (idx === 0 ? " active" : "");
        btn.textContent = s.season;
        btn.addEventListener("click", () => activateSeason(idx));
        tabsDiv.appendChild(btn);
      });
      section.appendChild(tabsDiv);
    }

    // Season panel
    const panelDiv = document.createElement("div");
    panelDiv.id = "season-panel";
    section.appendChild(panelDiv);

    // Activate default (most recent) season
    if (seasons.length > 0) activateSeason(0);

    // ─── inner helpers ───────────────────────────────────────────────────────

    function activateSeason(idx) {
      const seasonData = seasons[idx];
      if (!seasonData) return;

      // Update tabs
      document.querySelectorAll("#season-tabs .season-tab").forEach((btn, i) => {
        btn.classList.toggle("active", i === idx);
      });
      // Update summary table row highlight
      document.querySelectorAll("#career-profile-section .career-summary-table tbody tr").forEach((tr, i) => {
        tr.classList.toggle("active-season-row", i === idx);
      });

      _renderSeasonPanel(seasonData, panelDiv, gender);
    }

    function _renderSeasonPanel(seasonData, container, gender) {
      container.innerHTML = "";
      const matches = [...(seasonData.matches || [])].sort((a, b) => (a.date || "").localeCompare(b.date || ""));

      // Compute season stats from matches
      let wins = 0, losses = 0, forfeitWins = 0, falls = 0, techs = 0, mds = 0;
      let vsTop25W = 0, vsTop25L = 0, vsTop10W = 0, vsTop10L = 0;
      matches.forEach(m => {
        const isWin = m.result === "W";
        if (isWin) wins++; else losses++;
        const rank = m.opponent_rank;
        if (rank && rank <= 25) isWin ? vsTop25W++ : vsTop25L++;
        if (rank && rank <= 10) isWin ? vsTop10W++ : vsTop10L++;
        if (isWin && (m.method === "FF" || isForfeitMatch(m))) { forfeitWins++; return; }
        if (isWin && m.method === "FALL") falls++;
        if (isWin && m.method === "TF") techs++;
        if (isWin && m.method === "MD") mds++;
      });
      const total = wins + losses;
      const bonuses = falls + techs + mds;
      const winsActual = wins - forfeitWins; // exclude forfeits from bonus/pin rate denominator

      // Stats header
      const statsTitle = document.createElement("h2");
      statsTitle.className = "section-title-season-stats";
      statsTitle.textContent = `${seasonData.season} Season Stats`;
      statsTitle.style.marginTop = "24px";
      container.appendChild(statsTitle);

      // Mobile season tabs (injected below title, hidden on desktop)
      if (seasons.length > 0) {
        const mobileTabs = document.createElement("div");
        mobileTabs.className = "season-tabs season-tabs--mobile";
        seasons.forEach((s, i) => {
          const btn = document.createElement("button");
          btn.className = "season-tab" + (i === seasons.indexOf(seasonData) ? " active" : "");
          btn.textContent = s.season;
          btn.addEventListener("click", () => activateSeason(i));
          mobileTabs.appendChild(btn);
        });
        container.appendChild(mobileTabs);
      }

      const statsHr = document.createElement("hr");
      statsHr.className = "section-rule";
      container.appendChild(statsHr);

      const statsGrid = document.createElement("div");
      statsGrid.className = "stats-grid-newspaper";

      const mkRow = (label, value) => {
        if (value === null || value === undefined) return null;
        const row = document.createElement("div");
        row.style.cssText = "display:grid;grid-template-columns:1fr auto;align-items:baseline;padding:2px 0;gap:4px;";
        const lbl = document.createElement("span"); lbl.className = "stat-label-newspaper"; lbl.textContent = label;
        const val = document.createElement("span"); val.className = "stat-value-newspaper"; val.textContent = value;
        row.appendChild(lbl); row.appendChild(val);
        return row;
      };

      const colStyle = "display:flex;flex-direction:column;gap:0;";
      const col1 = document.createElement("div"); col1.style.cssText = colStyle; col1.className = "stats-col stats-col--sep";
      const col2 = document.createElement("div"); col2.style.cssText = colStyle; col2.className = "stats-col stats-col--sep";
      const col3 = document.createElement("div"); col3.style.cssText = colStyle; col3.className = "stats-col";

      const addRow = (col, label, value) => { const r = mkRow(label, value); if (r) col.appendChild(r); };
      // Col 1: core performance
      addRow(col1, "Season Rank", seasonData.current_rank != null ? `#${seasonData.current_rank}` : null);
      addRow(col1, "Record", total > 0 ? `${wins}–${losses}` : null);
      addRow(col1, "Win %", total > 0 ? (wins / total * 100).toFixed(1) + "%" : null);
      // Col 2: opponent quality
      addRow(col2, "vs Top 25", vsTop25W + vsTop25L > 0 ? `${vsTop25W}-${vsTop25L}` : null);
      addRow(col2, "vs Top 10", vsTop10W + vsTop10L > 0 ? `${vsTop10W}-${vsTop10L}` : null);
      addRow(col2, "Bonus Rate", winsActual > 0 ? (bonuses / winsActual * 100).toFixed(1) + "%" : null);
      // Col 3: bonus breakdown
      addRow(col3, "Falls", falls > 0 ? String(falls) : null);
      addRow(col3, "Tech Falls", techs > 0 ? String(techs) : null);
      addRow(col3, "Pin Rate", falls > 0 && winsActual > 0 ? (falls / winsActual * 100).toFixed(1) + "%" : null);

      statsGrid.appendChild(col1);
      statsGrid.appendChild(col2);
      statsGrid.appendChild(col3);
      container.appendChild(statsGrid);

      const statsEndHr = document.createElement("hr");
      statsEndHr.className = "section-rule";
      statsEndHr.style.marginTop = "8px";
      container.appendChild(statsEndHr);

      // Match history header
      const matchHeader = document.createElement("div");
      matchHeader.className = "section-header";
      const matchTitle = document.createElement("h2");
      matchTitle.textContent = `${seasonData.season} Match History`;
      matchHeader.appendChild(matchTitle);
      container.appendChild(matchHeader);

      const matchHr = document.createElement("hr");
      matchHr.className = "section-rule";
      container.appendChild(matchHr);

      if (matches.length === 0) {
        const empty = document.createElement("p");
        empty.className = "metric-secondary";
        empty.style.padding = "12px 0";
        empty.textContent = "No match data available for this season.";
        container.appendChild(empty);
        return;
      }

      const tableWrap = document.createElement("div");
      tableWrap.className = "table-wrapper match-table-desktop";
      const table = document.createElement("table");
      table.className = "career-match-table";
      const hasRankCol = seasonData.season >= 2026;
      table.innerHTML = `<thead><tr>
        <th>Date</th><th>Opponent</th>${hasRankCol ? '<th class="opp-rank-th">Rank</th>' : ''}<th class="career-col-wt" style="text-align:right">Wt</th>
        <th>Opponent Team</th><th>Result</th><th style="text-align:right">Score</th>
      </tr></thead>`;
      const tbody = document.createElement("tbody");

      matches.forEach(match => {
        const tr = document.createElement("tr");
        const isForfeit = isForfeitMatch(match);

        const dateTd = document.createElement("td");
        dateTd.textContent = formatDateMMDDYY(match.date);
        tr.appendChild(dateTd);

        const oppTd = document.createElement("td");
        oppTd.className = "name-cell";
        if (match.opponent_ky && match.opponent_id) {
          const a = document.createElement("a");
          a.href = match.opponent_career_id
            ? buildPageURL("wrestler.html", gender, { career_id: match.opponent_career_id })
            : buildPageURL("wrestler.html", gender, { id: match.opponent_id, season: match.season });
          a.textContent = safe(match.opponent_name || "Unknown");
          oppTd.appendChild(a);
        } else {
          oppTd.textContent = safe(match.opponent_name || "Unknown");
        }
        tr.appendChild(oppTd);

        if (hasRankCol) {
          const rankTd = document.createElement("td");
          rankTd.className = "opp-rank-td";
          if (!match.opponent_ky) {
            const na = document.createElement("span");
            na.className = "opp-rank-na";
            na.textContent = "N/A";
            rankTd.appendChild(na);
          } else if (match.opponent_rank == null) {
            rankTd.textContent = "—";
          } else {
            const pill = document.createElement("span");
            pill.className = "opp-rank-pill";
            const r = match.opponent_rank;
            if (r === 1) pill.classList.add("opp-rank-gold");
            else if (r === 2) pill.classList.add("opp-rank-silver");
            else if (r === 3) pill.classList.add("opp-rank-bronze");
            else if (r <= 10) pill.classList.add("opp-rank-top10");
            else pill.classList.add("opp-rank-other");
            pill.textContent = `#${r}`;
            rankTd.appendChild(pill);
          }
          tr.appendChild(rankTd);
        }

        const weightTd = document.createElement("td");
        weightTd.className = "metric-secondary num career-col-wt";
        weightTd.textContent = match.weight_class || "—";
        tr.appendChild(weightTd);

        const oppTeamTd = document.createElement("td");
        oppTeamTd.className = "metric-secondary";
        const oppTeam = match.opponent_team || "";
        const truncTeam = t => t.length > 30 ? t.substring(0, 30) + "…" : t;
        if (oppTeam && match.opponent_ky) {
          const tl = document.createElement("a");
          tl.href = buildPageURL("team.html", gender, { team: teamNameToSlug(oppTeam) });
          tl.textContent = truncTeam(oppTeam);
          if (oppTeam.length > 30) tl.title = oppTeam;
          oppTeamTd.appendChild(tl);
        } else {
          oppTeamTd.textContent = oppTeam ? truncTeam(oppTeam) : "—";
          if (oppTeam.length > 30) oppTeamTd.title = oppTeam;
        }
        tr.appendChild(oppTeamTd);

        const resultTd = document.createElement("td");
        resultTd.appendChild(createResultBadge(match.result, isForfeit ? "FF" : match.method));
        tr.appendChild(resultTd);

        const scoreTd = document.createElement("td");
        scoreTd.className = "metric-secondary num";
        scoreTd.textContent = match.score || "—";
        tr.appendChild(scoreTd);

        tbody.appendChild(tr);
      });

      table.appendChild(tbody);
      tableWrap.appendChild(table);
      container.appendChild(tableWrap);

      // ── Mobile card list (2-line per match) ──────────────────────────────
      const mobileCards = document.createElement("div");
      mobileCards.className = "match-cards-mobile";

      matches.forEach(match => {
        const isForfeit = isForfeitMatch(match);
        const oppTeam = match.opponent_team || "";
        const truncTeam = t => t.length > 22 ? t.substring(0, 22) + "…" : t;

        const card = document.createElement("div");
        card.className = "match-card";

        // Line 1: Name · rank pill · result badge + score
        const line1 = document.createElement("div");
        line1.className = "match-card-line1";

        const nameSpan = document.createElement("span");
        nameSpan.className = "match-card-name";
        if (match.opponent_ky && match.opponent_id) {
          const a = document.createElement("a");
          a.href = match.opponent_career_id
            ? buildPageURL("wrestler.html", gender, { career_id: match.opponent_career_id })
            : buildPageURL("wrestler.html", gender, { id: match.opponent_id, season: match.season });
          a.textContent = safe(match.opponent_name || "Unknown");
          nameSpan.appendChild(a);
        } else {
          nameSpan.textContent = safe(match.opponent_name || "Unknown");
        }
        line1.appendChild(nameSpan);

        if (hasRankCol && match.opponent_ky && match.opponent_rank != null) {
          const pill = document.createElement("span");
          pill.className = "opp-rank-pill";
          const r = match.opponent_rank;
          if (r === 1) pill.classList.add("opp-rank-gold");
          else if (r === 2) pill.classList.add("opp-rank-silver");
          else if (r === 3) pill.classList.add("opp-rank-bronze");
          else if (r <= 10) pill.classList.add("opp-rank-top10");
          else pill.classList.add("opp-rank-other");
          pill.textContent = `#${r}`;
          line1.appendChild(pill);
        }

        const resultWrap = document.createElement("span");
        resultWrap.className = "match-card-result";
        resultWrap.appendChild(createResultBadge(match.result, isForfeit ? "FF" : match.method));
        const scoreSpan = document.createElement("span");
        scoreSpan.className = "match-card-score";
        scoreSpan.textContent = match.score || "—";
        resultWrap.appendChild(scoreSpan);
        line1.appendChild(resultWrap);
        card.appendChild(line1);

        // Line 2: [Team · weight] [date right-aligned under result]
        const line2 = document.createElement("div");
        line2.className = "match-card-line2";

        const line2Left = document.createElement("span");
        line2Left.className = "match-card-line2-left";

        if (oppTeam && match.opponent_ky) {
          const tl = document.createElement("a");
          tl.href = buildPageURL("team.html", gender, { team: teamNameToSlug(oppTeam) });
          tl.textContent = truncTeam(oppTeam);
          tl.className = "match-card-team-link";
          line2Left.appendChild(tl);
        } else if (oppTeam) {
          const ts = document.createElement("span");
          ts.textContent = truncTeam(oppTeam);
          line2Left.appendChild(ts);
        }

        if (match.weight_class) {
          const wt = document.createElement("span");
          wt.className = "match-card-meta";
          wt.textContent = (oppTeam ? " · " : "") + match.weight_class;
          line2Left.appendChild(wt);
        }

        line2.appendChild(line2Left);

        if (match.date) {
          const dateSpan = document.createElement("span");
          dateSpan.className = "match-card-date";
          dateSpan.textContent = formatDateMMDDYY(match.date);
          line2.appendChild(dateSpan);
        }

        card.appendChild(line2);
        mobileCards.appendChild(card);
      });

      container.appendChild(mobileCards);
    }
  }

  function _gradeLabel(grade) {
    if (grade == null || grade === "") return "—";
    const n = parseInt(grade, 10);
    if (isNaN(n)) return String(grade);
    return { 12: "Sr.", 11: "Jr.", 10: "So.", 9: "Fr.", 8: "8th", 7: "7th" }[n] || String(grade);
  }

  function ordinal(n) {
    const s = ["th","st","nd","rd"], v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  }

  // ===============================
  // Rendering
  // ===============================
  
  // Helper function to check if we're on HS site
  function isHSSite() {
    // Check if hs_config.js is loaded (HS site indicator)
    return typeof HS_CONFIG !== 'undefined';
  }
  
  function renderWrestlerProfile(data) {
    console.log("[RENDER] renderWrestlerProfile called");
    const isHS = isHSSite();
    console.log("[RENDER] isHS =", isHS, "HS_CONFIG =", typeof HS_CONFIG);
    
    document.getElementById("wrestler-name").textContent = safe(data.name);
    const _wsGender = getGenderFromURL();
    const _wsGenderLabel = _wsGender === "girls" ? "Kentucky Girls High School Wrestling" : "Kentucky High School Wrestling";
    const _wsTeam = safe(data.team);
    document.title = _wsTeam
      ? `${safe(data.name)} | ${_wsGenderLabel} | ${_wsTeam} | KentuckyMat`
      : `${safe(data.name)} | ${_wsGenderLabel} | KentuckyMat`;
    sendPageView();
    const _wsMetaGender = _wsGender === "girls" ? "Kentucky girls high school wrestling" : "Kentucky high school wrestling";
    const _wsTeamPart = _wsTeam ? `, ${_wsTeam}` : "";
    setMetaDescription(`${safe(data.name)}, ${_wsMetaGender}${_wsTeamPart}. Full match history, stats, and season breakdowns on KentuckyMat.`);
    setCanonicalURL(window.location.href);

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
    const season = safe(data.year) || getSeasonFromURL();
    const gender = getGenderFromURL();
    if (teamName && teamName !== "—") {
      const teamSlug = teamNameToSlug(teamName);
      const teamLink = document.createElement("a");
      teamLink.href = buildPageURL('team.html', gender, { team: teamSlug });
      teamLink.textContent = teamName;
      metaEl.innerHTML = "";
      metaEl.appendChild(teamLink);
      metaEl.appendChild(document.createTextNode(` · Season ${season}`));
    } else {
      metaEl.textContent = `Season ${season}`;
    }
  
    // Hide advanced analytics sections for HS
    console.log("[DEBUG] About to check isHS, value:", isHS);
    if (isHS) {
      console.log("[HS Profile] HS site detected, rendering HS-specific sections");
      console.log("[HS Profile] Career data check:", {
        hasCareer: !!data.career,
        hasSeasonSummary: !!data.season_summary,
        career: data.career,
        seasonSummary: data.season_summary
      });
      
      // Hide the entire profile summary grid (TPAR, Timeline, Skill Profile)
      const profileGrid = document.querySelector(".profile-summary-grid");
      if (profileGrid) {
        profileGrid.style.display = "none";
      }
      document.getElementById("mv-section").style.display = "none";
      document.getElementById("match-impact-section").style.display = "none";
      document.getElementById("skill-section").style.display = "none";
      document.getElementById("mv-context-section").style.display = "none";
      
      // Render Career Summary for HS (if available)
      console.log("[HS Profile] Calling renderCareerSummary");
      renderCareerSummary(data);
      
      // Render simplified Season Stats for HS
      console.log("[HS Profile] Calling renderSimplifiedSeasonStats");
      renderSimplifiedSeasonStats(data);
    } else {
    // ========================================
      // MV SECTION (DataGolf-style, no card) - NCAA only
    // ========================================
    const summaryGridEl = document.querySelector(".profile-summary-grid");
    if (summaryGridEl) summaryGridEl.style.display = "";
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
    tooltipIcon.textContent = "→";
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
    
    // Add helper text below divider (moved from header)
    const helperText = document.createElement("div");
    helperText.className = "mv-helper-text";
    helperText.textContent = "Estimated team points contributed above a replacement-level starter";
    helperText.style.cssText = "font-size: 0.875rem; color: var(--muted); font-weight: 400; margin: 0 0 12px 0; line-height: 1.4;";
    mvSection.appendChild(helperText);
    
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
    addTooltip(rankBadgeLink, "TPAR: Per-match impact above replacement.");
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
    
    // Synthesized profile description (moved to immediately after divider)
    const profileDesc = generateSkillProfileDescription(m);
    if (profileDesc) {
      const descEl = document.createElement("p");
      descEl.className = "skill-profile-description";
      descEl.textContent = profileDesc;
      descEl.style.cssText = "font-size: 0.875rem; color: var(--muted); font-weight: 400; margin: 0 0 12px 0; line-height: 1.4;";
      skillSection.appendChild(descEl);
    }
    
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
    
    // ========================================
    // MATCH IMPACT TIMELINE (PROMOTED - BEFORE CONTEXT) - NCAA only
    // ========================================
    renderMatchImpactTimeline(data, mv.mv_avg);
    
    // ========================================
    // MV CONTEXT (COMPRESSED, BELOW TIMELINE) - NCAA only
    // ========================================
    // MV Composition removed - keep section visible for divider, but render nothing
    renderMVContextCompressed(data, mv.mv_avg);
    }
    
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
    // Update Match History title with current year
    const matchHistorySection = document.querySelector(".section--match-history");
    if (matchHistorySection) {
      const matchHistoryHeader = matchHistorySection.querySelector("h2");
      if (matchHistoryHeader) {
        const season = data.year || getSeasonFromURL();
        matchHistoryHeader.textContent = season ? `${season} Match History` : "Match History";
        matchHistoryHeader.className = "section-title-newspaper";
      }
    }
    
    const seasonMV = isHS ? null : mv.mv_avg;
    renderMatchTable(data.match_list || [], seasonMV, isHS);

    // Match Data Notice (system notice below matches): last update date + instructional copy
    const noteEl = document.getElementById("match-data-note");
    if (noteEl) {
      const rawDate = data.profile_generated_at;
      if (rawDate) {
        const dateObj = new Date(rawDate + "T12:00:00");
        const formattedDate = dateObj.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
        noteEl.innerHTML = [
          '<p class="system-notice__title">Match Data Notice</p>',
          '<p class="system-notice__line1"><strong>Last data update:</strong> ' + formattedDate + '</p>',
          '<p class="system-notice__line2">If a match is missing here, it means it had not been entered into TrackWrestling by the coach as of that date. Before contacting KentuckyMat about a missing match, please confirm with the coach that the result has been entered.</p>'
        ].join("");
        noteEl.style.display = "block";
      } else {
        noteEl.style.display = "none";
      }
    }
  }
  
  // Helper function to calculate winning percentage from record string
  function calculateWinPercentage(recordStr) {
    if (!recordStr || typeof recordStr !== 'string') return null;
    const match = recordStr.match(/(\d+)-(\d+)/);
    if (!match) return null;
    const wins = parseInt(match[1], 10);
    const losses = parseInt(match[2], 10);
    const total = wins + losses;
    if (total === 0) return null;
    return (wins / total) * 100;
  }

  // Career Summary for HS (compact table of season history)
  // Version: 2024-01-XX - Added career summary table
  function renderCareerSummary(data) {
    console.log("=== CAREER SUMMARY FUNCTION CALLED ===");
    console.log("[Career Summary] Function called with data:", data);
    
    // Only render if career data exists
    if (!data.career || !data.season_summary || !Array.isArray(data.season_summary) || data.season_summary.length === 0) {
      console.log("[Career Summary] Skipping - no career data available", {
        hasCareer: !!data.career,
        hasSeasonSummary: !!data.season_summary,
        seasonSummaryLength: data.season_summary?.length
      });
      return;
    }
    
    console.log("[Career Summary] Rendering career summary", data.career, data.season_summary);

    // Create a new section for Career Summary if it doesn't exist
    let careerSummarySection = document.getElementById("career-summary-section");
    if (!careerSummarySection) {
      careerSummarySection = document.createElement("section");
      careerSummarySection.id = "career-summary-section";
      careerSummarySection.className = "section";
      
      // Insert after header, before any existing sections
      // Try to insert after the header, before match history or season stats
      const header = document.querySelector(".header");
      const matchHistorySection = document.querySelector(".section--match-history");
      const seasonStatsSection = document.getElementById("season-stats-section");
      
      if (header && header.nextSibling) {
        // Insert right after header
        header.parentNode.insertBefore(careerSummarySection, header.nextSibling);
      } else if (seasonStatsSection && seasonStatsSection.parentNode) {
        // Insert before season stats if it exists
        seasonStatsSection.parentNode.insertBefore(careerSummarySection, seasonStatsSection);
      } else if (matchHistorySection && matchHistorySection.parentNode) {
        // Insert before match history as fallback
        matchHistorySection.parentNode.insertBefore(careerSummarySection, matchHistorySection);
      } else {
        // Final fallback: append to page container
        const pageContainer = document.querySelector(".page-container");
        if (pageContainer) {
          pageContainer.appendChild(careerSummarySection);
        }
      }
      
      console.log("[Career Summary] Section created and inserted");
    }
    
    careerSummarySection.innerHTML = "";
    
    // Render Career Record if available
    if (data.career_record) {
      const careerRecordDiv = document.createElement("div");
      careerRecordDiv.className = "career-record";
      careerRecordDiv.style.cssText = "margin-bottom: 24px;";
      
      const label = document.createElement("div");
      label.className = "career-record-label";
      label.textContent = "Career Record";
      label.style.cssText = "font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;";
      careerRecordDiv.appendChild(label);
      
      const value = document.createElement("div");
      value.className = "career-record-value";
      const wins = data.career_record.wins || 0;
      const losses = data.career_record.losses || 0;
      const winPct = data.career_record.win_pct || 0;
      // Format win percentage: 0.885 -> .885 (remove leading zero)
      const winPctFormatted = winPct.toFixed(3).replace(/^0\./, '.');
      value.innerHTML = `<strong>${wins}–${losses}</strong> <span style="color: var(--muted);">(${winPctFormatted})</span>`;
      value.style.cssText = "font-size: 1.125rem; line-height: 1.5;";
      careerRecordDiv.appendChild(value);
      
      careerSummarySection.appendChild(careerRecordDiv);
    }
    
    // Section header - newspaper style, more prominent for historical anchor
    const header = document.createElement("h2");
    header.className = "section-title-career-summary";
    header.textContent = "Career Summary";
    careerSummarySection.appendChild(header);
    
    // Thin horizontal rule directly under header (archive anchor)
    const headerRule = document.createElement("hr");
    headerRule.className = "career-header-rule";
    careerSummarySection.appendChild(headerRule);
    
    // Create table directly (no wrapper, no card styling)
    const table = document.createElement("table");
    table.className = "career-summary-table";
    table.style.cssText = "width: 100%; font-size: 0.875rem; margin-top: 12px;";
    
    // Table header
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    const headers = ["Season", "Grade", "Team", "Record", "Regional Place", "State Place"];
    headers.forEach(headerText => {
      const th = document.createElement("th");
      th.textContent = headerText;
      th.style.cssText = "text-align: left; padding: 8px 12px; font-weight: 600; color: var(--muted); border-bottom: 1px solid var(--border);";
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);
    
    // Table body
    const tbody = document.createElement("tbody");
    
    // Sort seasons descending (most recent first) - already sorted in JSON but ensure it
    const sortedSeasons = [...data.season_summary].sort((a, b) => b.season - a.season);
    
    sortedSeasons.forEach(seasonData => {
      const row = document.createElement("tr");
      row.style.cssText = "border-bottom: 1px solid var(--border);";
      
      // Helper to format cell value (use — for null/undefined)
      const formatValue = (value) => {
        if (value === null || value === undefined || value === "") {
          return "—";
        }
        return String(value);
      };
      
      // Season
      const seasonCell = document.createElement("td");
      seasonCell.textContent = formatValue(seasonData.season);
      seasonCell.style.cssText = "padding: 8px 12px; color: var(--text);";
      row.appendChild(seasonCell);
      
      // Grade (convert integer to abbreviation)
      const gradeCell = document.createElement("td");
      const formatGrade = (grade) => {
        if (grade === null || grade === undefined || grade === "") {
          return "—";
        }
        const gradeNum = parseInt(grade, 10);
        if (isNaN(gradeNum)) {
          return String(grade); // Return as-is if not a number
        }
        switch (gradeNum) {
          case 12: return "Sr.";
          case 11: return "Jr.";
          case 10: return "So.";
          case 9: return "Fr.";
          case 8: return "8th";
          case 7: return "7th";
          default: return String(grade); // Fallback to original value
        }
      };
      gradeCell.textContent = formatGrade(seasonData.grade);
      gradeCell.style.cssText = "padding: 8px 12px; color: var(--text);";
      row.appendChild(gradeCell);
      
      // Team
      const teamCell = document.createElement("td");
      teamCell.textContent = formatValue(seasonData.team);
      teamCell.style.cssText = "padding: 8px 12px; color: var(--text);";
      row.appendChild(teamCell);
      
      // Record
      const recordCell = document.createElement("td");
      recordCell.textContent = formatValue(seasonData.record);
      recordCell.style.cssText = "padding: 8px 12px; color: var(--text);";
      row.appendChild(recordCell);
      
      // Regional Place
      const regionalCell = document.createElement("td");
      regionalCell.textContent = formatValue(seasonData.regional_place);
      regionalCell.style.cssText = "padding: 8px 12px; color: var(--text);";
      row.appendChild(regionalCell);
      
      // State Place
      const stateCell = document.createElement("td");
      stateCell.textContent = formatValue(seasonData.state_place);
      stateCell.style.cssText = "padding: 8px 12px; color: var(--text);";
      row.appendChild(stateCell);
      
      tbody.appendChild(row);
    });
    
    table.appendChild(tbody);
    careerSummarySection.appendChild(table);
    
    // Add horizontal rule after Career Summary
    const hr = document.createElement("hr");
    hr.className = "section-rule";
    careerSummarySection.appendChild(hr);
  }

  // Simplified Season Stats for HS (standalone section)
  function renderSimplifiedSeasonStats(data) {
    // Create a new section for Season Stats if it doesn't exist
    let seasonStatsSection = document.getElementById("season-stats-section");
    if (!seasonStatsSection) {
      seasonStatsSection = document.createElement("section");
      seasonStatsSection.id = "season-stats-section";
      seasonStatsSection.className = "section";
      
      // Insert after xtp/mv-context, before ad container (ad is between Season Stats and Match History)
      const adContainer = document.getElementById("wrestler-ad-container");
      const matchHistorySection = document.querySelector(".section--match-history");
      const insertBefore = adContainer || matchHistorySection;
      if (insertBefore && insertBefore.parentNode) {
        insertBefore.parentNode.insertBefore(seasonStatsSection, insertBefore);
      }
    }
    
    seasonStatsSection.innerHTML = "";
    
    // Section header - dynamic year, newspaper style, emphasized as current chapter
    const header = document.createElement("h2");
    header.className = "section-title-season-stats";
    // Get most recent season from career.seasons or fall back to data.year
    let mostRecentSeason = data.year;
    if (data.career && Array.isArray(data.career.seasons) && data.career.seasons.length > 0) {
      // Seasons are already sorted descending in JSON
      mostRecentSeason = data.career.seasons[0];
    }
    header.textContent = mostRecentSeason ? `${mostRecentSeason} Season Stats` : "Season Stats";
    seasonStatsSection.appendChild(header);
    
    // Add muted subtitle to reinforce "current chapter" importance
    const subtitle = document.createElement("div");
    subtitle.className = "season-stats-subtitle";
    subtitle.textContent = "Most recent season";
    seasonStatsSection.appendChild(subtitle);
    
    // Add horizontal rule after Season Stats
    const hr = document.createElement("hr");
    hr.className = "section-rule";
    // Will be appended after stats grid
    
    // Stats grid (2 columns) - newspaper style spacing
    const statsGrid = document.createElement("div");
    statsGrid.className = "stats-grid-newspaper";
    
    const record = data.record || {};
    const m = data.metrics || {};
    
    // Debug: Log data to console
    console.log("[HS Season Stats] Full data:", data);
    console.log("[HS Season Stats] Record:", record);
    console.log("[HS Season Stats] Metrics:", m);
    
    // Helper function to create a stat row
    const createStatRow = (label, value) => {
      if (value === null || value === undefined) return null;
      // Convert to string and check if empty
      const valueStr = String(value).trim();
      if (valueStr === "" || valueStr === "—") return null;
      
      const statRow = document.createElement("div");
      statRow.style.cssText = "display: flex; justify-content: space-between; align-items: baseline; padding: 4px 0;";
      
      const labelEl = document.createElement("span");
      labelEl.className = "stat-label-newspaper";
      labelEl.textContent = label;
      
      const valueEl = document.createElement("span");
      valueEl.className = "stat-value-newspaper";
      valueEl.textContent = valueStr;
      
      statRow.appendChild(labelEl);
      statRow.appendChild(valueEl);
      return statRow;
    };
    
    // Column 1: Record, vs Top 25, vs Top 10, Winning Percentage
    const col1 = document.createElement("div");
    col1.style.cssText = "display: flex; flex-direction: column; gap: 0;";
    
    // Record
    const recordValue = record.overall;
    if (recordValue) {
      const row = createStatRow("Record", recordValue);
      if (row) col1.appendChild(row);
    }
    
    // vs Top 25
    const vsTop25 = record.vs_top25;
    if (vsTop25) {
      const row = createStatRow("vs Top 25", vsTop25);
      if (row) col1.appendChild(row);
    }
    
    // vs Top 10
    const vsTop10 = record.vs_top10;
    if (vsTop10) {
      const row = createStatRow("vs Top 10", vsTop10);
      if (row) col1.appendChild(row);
    }
    
    // Winning Percentage
    if (recordValue) {
      const winPct = calculateWinPercentage(recordValue);
      if (winPct !== null) {
        const row = createStatRow("Win %", winPct.toFixed(1) + "%");
        if (row) col1.appendChild(row);
      }
    }
    
    // Column 2: Bonus Rate, Falls (pins), Tech Falls, Pin Rate
    const col2 = document.createElement("div");
    col2.style.cssText = "display: flex; flex-direction: column; gap: 0;";
    
    // Bonus Rate
    if (m.bonus_rate !== null && m.bonus_rate !== undefined) {
      const row = createStatRow("Bonus Rate", percentFormatter(m.bonus_rate));
      if (row) col2.appendChild(row);
    }
    
    // Falls (pins)
    if (m.pins !== null && m.pins !== undefined) {
      const row = createStatRow("Falls", String(m.pins));
      if (row) col2.appendChild(row);
    }
    
    // Tech Falls
    if (m.techs !== null && m.techs !== undefined) {
      const row = createStatRow("Tech Falls", String(m.techs));
      if (row) col2.appendChild(row);
    }
    
    // Pin Rate
    if (m.pin_rate !== null && m.pin_rate !== undefined) {
      const row = createStatRow("Pin Rate", percentFormatter(m.pin_rate));
      if (row) col2.appendChild(row);
    }
    
    // Always append both columns, even if empty (for consistent layout)
    statsGrid.appendChild(col1);
    statsGrid.appendChild(col2);
    seasonStatsSection.appendChild(statsGrid);
    
    // Append horizontal rule after stats grid
    seasonStatsSection.appendChild(hr);
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
      // Parse date string explicitly as local date to avoid timezone issues
      // Handle both "YYYY-MM-DD" (ISO) and "MM/DD/YYYY" formats
      let year, month, day;
      
      if (dateStr.includes("-")) {
        // ISO format: "2025-12-13"
        const parts = dateStr.split("-");
        year = parseInt(parts[0], 10);
        month = parseInt(parts[1], 10);
        day = parseInt(parts[2], 10);
      } else if (dateStr.includes("/")) {
        // Slash format: "12/13/2025" or "12/13/25"
        const parts = dateStr.split("/");
        month = parseInt(parts[0], 10);
        day = parseInt(parts[1], 10);
        year = parseInt(parts[2], 10);
        // Handle 2-digit years
        if (year < 100) {
          year += 2000;
        }
      } else {
        // Fallback to Date constructor
        const date = new Date(dateStr);
        if (isNaN(date.getTime())) return dateStr;
        year = date.getFullYear();
        month = date.getMonth() + 1;
        day = date.getDate();
      }
      
      // Validate parsed values
      if (isNaN(year) || isNaN(month) || isNaN(day)) {
        return dateStr;
      }
      
      const monthStr = String(month).padStart(2, "0");
      const dayStr = String(day).padStart(2, "0");
      const yearStr = String(year).slice(-2);
      return `${monthStr}-${dayStr}-${yearStr}`;
    } catch (e) {
      return dateStr;
    }
  }
  
  // Helper function to detect forfeit matches
  function isForfeitMatch(match) {
    if (!match) return false;
    const result = (match.result || "").toUpperCase();
    const method = (match.method || "").toUpperCase();
    const opponentName = (match.opponent_name || "").trim().toUpperCase();
    const summary = (match.summary || "").toUpperCase();
    
    // Check if result starts with "For" (e.g., "For.", "For")
    if (result.startsWith("FOR")) {
      return true;
    }
    // Check if method starts with "For" (e.g., "For.", "For", "Forfeit", "FF")
    if (method.startsWith("FOR") || method === "FF") {
      return true;
    }
    // Check if summary contains "over Unknown"
    if (summary.includes("OVER UNKNOWN")) {
      return true;
    }
    // Check if opponent_name is "Unknown" AND no real method (actual forfeits have no pin/fall/dec)
    const realMethods = ["FALL", "PIN", "DEC", "MD", "TF", "INJ", "DQ"];
    if (opponentName === "UNKNOWN" && !realMethods.includes(method)) {
      return true;
    }
    return false;
  }

  // Helper function to extract team name from event field
  function getForfeitOpponentTeam(event) {
    if (!event) return "Forfeit";
    // Match pattern "vs. <TEAM_NAME>"
    const match = event.match(/vs\.\s*(.+)/i);
    if (match && match[1]) {
      return match[1].trim();
    }
    return "Forfeit";
  }

  function createOpponentRankBadge(rank, isOutOfState = false) {
    // For out-of-state wrestlers, always show "N/A" regardless of rank
    if (isOutOfState) {
      const badge = document.createElement("span");
      badge.className = "rank-badge unr-badge out-of-state-badge";
      badge.textContent = "N/A";
      return badge;
    }
    
    // For in-state wrestlers without rank, show "UNR"
    if (rank === null || rank === undefined || rank === "") {
      const badge = document.createElement("span");
      badge.className = "rank-badge unr-badge";
      badge.textContent = "UNR";
      return badge;
    }
    
    // For in-state wrestlers with rank, show the rank badge
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
  
  function renderMatchTable(matches, seasonMV, isHS = false) {
    const tbody = document.querySelector("#match-table tbody");
    tbody.innerHTML = "";
    
    // Hide MI Impact column header for HS
    if (isHS) {
      const matchTable = document.querySelector("#match-table");
      if (matchTable) {
        const headerRow = matchTable.querySelector("thead tr");
        if (headerRow) {
          const headers = headerRow.querySelectorAll("th");
          headers.forEach((th) => {
            if (th.textContent.trim() === "MI Impact" || th.classList.contains("mi-impact-header")) {
              th.style.display = "none";
            }
          });
        }
      }
    }
  
    // Sort chronologically (oldest first) for timeline consistency
    const sortedMatches = [...matches].sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  
    sortedMatches.forEach((match) => {
      const tr = document.createElement("tr");

      // Check if this is a forfeit match
      const isForfeit = isForfeitMatch(match);
      
      // Check if opponent is out-of-state:
      // OUTSTATE_ prefix is the authoritative marker — used consistently across all seasons.
      // The old null-rank heuristic caused false positives for historical seasons (no rankings data).
      const isOutOfState = !!(match.opponent_id && match.opponent_id.startsWith("OUTSTATE_"));
      
      // Add class for out-of-state rows (for styling)
      if (isOutOfState) {
        tr.classList.add("out-of-state-row");
      }
      
      // Determine display values
      let displayOpponent, displayOpponentTeam, displayOpponentRank, displayResult, displayMethod, displayMVImpact;
      
      // Use match data directly, but override method to "FF" if it's a forfeit
      displayOpponent = match.opponent_name || "Unknown";
      displayOpponentTeam = match.opponent_team || "Unknown";
      displayOpponentRank = match.opponent_rank;
      displayResult = match.result; // Preserve W/L from match data
      displayMethod = isForfeit ? "FF" : match.method; // Override to FF for forfeits
      displayMVImpact = isForfeit ? null : match.mv_impact; // No MV impact for forfeits
  
      // 1. Date (MM-DD-YY format)
      const dateTd = document.createElement("td");
      dateTd.textContent = formatDateMMDDYY(match.date);
      tr.appendChild(dateTd);
  
      // 2. Opponent (with link, .name styling)
      const oppTd = document.createElement("td");
      oppTd.className = "name-cell";
      const gender = getGenderFromURL();
      // Create link if opponent_id exists (even for forfeits, if opponent_id is available)
      // Only skip link for out-of-state opponents without opponent_id
      if (match.opponent_id && !isOutOfState) {
        const a = document.createElement("a");
        a.href = buildPageURL('wrestler.html', gender, { id: match.opponent_id });
        a.textContent = safe(displayOpponent);
        oppTd.appendChild(a);
      } else {
        oppTd.textContent = safe(displayOpponent);
      }
      tr.appendChild(oppTd);
  
      // 3. Weight Class
      const weightTd = document.createElement("td");
      weightTd.className = "metric-secondary num";
      const matchWeight = match.weight_class;
      weightTd.textContent = matchWeight ? safe(matchWeight) : "—";
      tr.appendChild(weightTd);
  
      // 4. Opponent Team (muted secondary)
      const oppTeamTd = document.createElement("td");
      oppTeamTd.className = "metric-secondary";
      let oppTeamName = safe(displayOpponentTeam);
      // Truncate team name to 25 characters max
      const MAX_TEAM_NAME_LENGTH = 25;
      if (oppTeamName && oppTeamName.length > MAX_TEAM_NAME_LENGTH) {
        oppTeamName = oppTeamName.substring(0, MAX_TEAM_NAME_LENGTH) + "...";
      }
      // For out-of-state teams, don't create a link (no team profiles for out-of-state schools)
      if (oppTeamName && oppTeamName !== "—" && oppTeamName !== "Forfeit" && !isOutOfState) {
        const teamSlug = teamNameToSlug(displayOpponentTeam); // Use original name for slug, not truncated
        const teamLink = document.createElement("a");
        teamLink.href = buildPageURL('team.html', gender, { team: teamSlug });
        teamLink.textContent = oppTeamName; // Display truncated name
        teamLink.setAttribute("title", displayOpponentTeam); // Show full name on hover
        oppTeamTd.appendChild(teamLink);
      } else {
        oppTeamTd.textContent = oppTeamName;
      }
      tr.appendChild(oppTeamTd);
      
      // 5. Opponent Rank (badge with medal rules)
      // For forfeits, show "—" instead of "UNR"
      // For out-of-state opponents, show "N/A" instead of "UNR"
      const oppRankTd = document.createElement("td");
      if (isForfeit) {
        oppRankTd.textContent = "—";
      } else if (isOutOfState) {
        oppRankTd.appendChild(createOpponentRankBadge(displayOpponentRank, true)); // Pass true to show "N/A"
      } else {
        oppRankTd.appendChild(createOpponentRankBadge(displayOpponentRank));
      }
      tr.appendChild(oppRankTd);
      
      // 6. Result (combined Result + Method as badge)
      // For forfeits, create a custom badge with "FF" and win styling
      const resultTd = document.createElement("td");
      // Use createResultBadge for all matches (including forfeits) to correctly show W/L
      resultTd.appendChild(createResultBadge(displayResult, displayMethod));
      tr.appendChild(resultTd);
      
      // 7. MV Impact (right-aligned, tabular, color-coded) - NCAA only
      // For HS, skip this column entirely
      if (!isHS) {
      const impactTd = document.createElement("td");
      impactTd.className = "num";
        if (isForfeit) {
          impactTd.textContent = "—";
        } else if (displayMVImpact !== null && displayMVImpact !== undefined) {
          const impactText = displayMVImpact > 0 ? `+${displayMVImpact.toFixed(1)}` : displayMVImpact.toFixed(1);
        impactTd.textContent = impactText;
          impactTd.classList.add(displayMVImpact > 0 ? "impact-positive" : "impact-negative");
      } else {
        impactTd.textContent = "—";
      }
      tr.appendChild(impactTd);
      }
      
      // 8. Score (muted secondary)
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
          `TPAR Impact: ${impactSign}${impactValue}`,
          `Season Avg TPAR: ${seasonAvgStr}`
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
      
      // Color TPAR Impact line based on sign
      if (line.startsWith("TPAR Impact:")) {
        lineEl.innerHTML = line.replace(
          /TPAR Impact: ([\+\-]?[\d\.]+)/,
          (match, value) => {
            const isPositive = mvImpact >= 0;
            const color = isPositive ? "rgba(0, 194, 168, 0.9)" : "rgba(220, 90, 90, 0.9)";
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