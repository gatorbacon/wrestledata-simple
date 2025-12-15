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
  
    // Record
    const r = data.record || {};
    document.getElementById("record-overall").textContent = safe(r.overall);
    document.getElementById("record-ranked").textContent = safe(r.vs_ranked);
    document.getElementById("record-top10").textContent = safe(r.vs_top10);
    document.getElementById("record-top25").textContent = safe(r.vs_top25);
  
    // Metrics summary cards
    const m = data.metrics || {};
    document.getElementById("metric-bonus-rate").textContent = safe(m.bonus_rate, percentFormatter);
    document.getElementById("metric-pin-rate").textContent = safe(m.pin_rate, percentFormatter);
    document.getElementById("metric-majors").textContent = safe(m.majors);
    document.getElementById("metric-techs").textContent = safe(m.techs);
    document.getElementById("metric-pins").textContent = safe(m.pins);
  
    document.getElementById("metric-pf7").textContent = safe(m.pf7);
    document.getElementById("metric-pa7").textContent = safe(m.pa7);
    document.getElementById("metric-pd7").textContent = safe(m.pd7);
    document.getElementById("metric-si-plus").textContent = safe(m.si_plus);
    document.getElementById("metric-df-plus").textContent = safe(m.df_plus);
    document.getElementById("metric-apr-plus").textContent = safe(m.apr_plus);
    
    // Mat Value
    const mv = m.mat_value || {};
    if (!m.mat_value) {
      console.log("Mat Value not found in profile. Available metrics keys:", Object.keys(m));
    } else {
      console.log("Mat Value found:", mv);
    }
    // MV with bar visualization
    const mvEl = document.getElementById("metric-mv");
    if (mv.mv_avg !== null && mv.mv_avg !== undefined) {
      // For wrestler profile, we need a reference max - use a reasonable default
      // or compute from all wrestlers if available. For now, use a fixed scale.
      // A typical MV range is -5 to +8, so we'll use 10 as a reasonable max
      const maxMV = 10;
      const mvBar = createMetricBar(mv.mv_avg, maxMV);
      mvEl.innerHTML = "";
      mvEl.appendChild(mvBar);
    } else {
      mvEl.textContent = "—";
    }
    
    // MV Ranks with badges
    const rankWeight = mv.rank_weight;
    const rankWeightEl = document.getElementById("metric-mv-rank-weight");
    rankWeightEl.innerHTML = "";
    rankWeightEl.appendChild(createRankBadge(rankWeight));
    
    const rankOverall = mv.rank_overall;
    const rankOverallEl = document.getElementById("metric-mv-rank-overall");
    rankOverallEl.innerHTML = "";
    rankOverallEl.appendChild(createRankBadge(rankOverall));
    
    // MV Leaderboard link
    const leaderboardLinkEl = document.getElementById("mv-leaderboard-link");
    const weightClass = data.weight_class;
    let leaderboardUrl = "/leaderboards/mat_value.html";
    if (weightClass) {
      leaderboardUrl += `?weight=${weightClass}`;
    }
    const link = document.createElement("a");
    link.href = leaderboardUrl;
    link.textContent = "View MV Leaderboard";
    link.style.fontSize = "0.9em";
    link.style.color = "#4a90e2";
    leaderboardLinkEl.appendChild(link);
  
    renderImpactSummary(data.opponent_breakdown || {});
    renderMatchTable(data.match_list || []);
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
  
  function renderMatchTable(matches) {
    const tbody = document.querySelector("#match-table tbody");
    tbody.innerHTML = "";
  
    matches.sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  
    matches.forEach((match) => {
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
      add(match.opponent_rank ? "#" + match.opponent_rank : "—");
      add(match.result);
      add(match.method);
      add(match.score);
      add(match.duration);
      add(match.event);
  
      tbody.appendChild(tr);
    });
  }