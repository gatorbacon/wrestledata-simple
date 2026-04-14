// ========================================
// Freshman of the Year Watch Page
// ========================================

function safe(v, fn) {
  if (v === null || v === undefined || v === "") return "—";
  return fn ? fn(v) : v;
}

function resolveSeason() {
  return "2026"; // Or make dynamic later
}

function teamNameToSlug(teamName) {
  if (!teamName) return null;
  return teamName.toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

async function fetchJSON(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.statusText}`);
  }
  return response.json();
}

// ========================================
// Gradient Color (DG-style: 0 → near-black, 50 → muted green, 80+ → strong green)
// ========================================
function getScoreColor(score) {
  // Clamp to 0-100
  const t = Math.max(0, Math.min(100, score)) / 100.0;
  
  // Near-black at 0, muted green at 50, strong green at 80+
  if (t <= 0.5) {
    // 0 → near-black (#1a1a1a), 0.5 → muted green (#2d5a3d)
    const r = Math.round(26 + (45 - 26) * (t * 2));
    const g = Math.round(26 + (90 - 26) * (t * 2));
    const b = Math.round(26 + (61 - 26) * (t * 2));
    return `rgb(${r}, ${g}, ${b})`;
  } else if (t <= 0.8) {
    // 0.5 → muted green (#2d5a3d), 0.8 → strong green (#1a6e22)
    const localT = (t - 0.5) / 0.3;
    const r = Math.round(45 + (26 - 45) * localT);
    const g = Math.round(90 + (110 - 90) * localT);
    const b = Math.round(61 + (34 - 61) * localT);
    return `rgb(${r}, ${g}, ${b})`;
  } else {
    // 0.8+ → strong green (#1a6e22)
    return "rgb(26, 110, 34)";
  }
}

// Cache for team abbreviations
const teamAbbreviationCache = new Map();

async function getTeamAbbreviation(teamName) {
  if (!teamName) return null;
  
  // Check cache first
  if (teamAbbreviationCache.has(teamName)) {
    return teamAbbreviationCache.get(teamName);
  }
  
  try {
    const teamSlug = teamNameToSlug(teamName);
    if (!teamSlug) {
      teamAbbreviationCache.set(teamName, null);
      return null;
    }
    
    const teamData = await fetchJSON(`/data/teams/${teamSlug}.json`);
    const abbreviation = teamData.abbreviation || null;
    teamAbbreviationCache.set(teamName, abbreviation);
    return abbreviation;
  } catch (error) {
    // Team file not found or error loading
    teamAbbreviationCache.set(teamName, null);
    return null;
  }
}

// ========================================
// Render Freshman Table
// ========================================
async function renderFreshmanTable(data) {
  if (!data || !data.rows || data.rows.length === 0) {
    const tbody = document.querySelector("#freshman-table tbody");
    tbody.innerHTML = `
      <tr>
        <td colspan="11" style="text-align: center; padding: 2em; color: var(--muted);">
          No data available
        </td>
      </tr>
    `;
    return;
  }

  const tbody = document.querySelector("#freshman-table tbody");
  tbody.innerHTML = "";

  // Pre-load all team abbreviations
  const teamNames = [...new Set(data.rows.map(row => row.team).filter(Boolean))];
  await Promise.all(teamNames.map(teamName => getTeamAbbreviation(teamName)));

  // Calculate max values for gradient normalization
  const maxValues = {
    win_pct: Math.max(...data.rows.map(r => r.metrics?.win_pct || 0)),
    bonus_pct: Math.max(...data.rows.map(r => r.metrics?.bonus_pct || 0)),
    fall_pct: Math.max(...data.rows.map(r => r.metrics?.fall_pct || 0)),
    ranked_wins: Math.max(...data.rows.map(r => r.metrics?.ranked_wins || 0)),
    top10_wins: Math.max(...data.rows.map(r => r.metrics?.top10_wins || 0)),
    ranked_bonus_pct: Math.max(...data.rows.map(r => r.metrics?.ranked_bonus_pct || 0)),
    fresh_score: Math.max(...data.rows.map(r => r.fresh_score || 0))
  };

  data.rows.forEach((row) => {
    const tr = document.createElement("tr");

    // Rank
    const rankTd = document.createElement("td");
    rankTd.textContent = safe(row.rank);
    tr.appendChild(rankTd);

    // Name + Team Abbreviation (combined)
    const nameTd = document.createElement("td");
    nameTd.className = "name";
    
    // Name link (teal, already styled)
    if (row.wrestler_id) {
      const nameLink = document.createElement("a");
      nameLink.href = `/wrestler.html?id=${row.wrestler_id}`;
      nameLink.textContent = safe(row.name);
      nameTd.appendChild(nameLink);
    } else {
      const nameSpan = document.createElement("span");
      nameSpan.textContent = safe(row.name);
      nameTd.appendChild(nameSpan);
    }
    
    // Team abbreviation link (different color, smaller, not bold)
    if (row.team) {
      const abbreviation = teamAbbreviationCache.get(row.team);
      const teamSlug = teamNameToSlug(row.team);
      
      if (abbreviation && teamSlug) {
        const space = document.createTextNode(" ");
        nameTd.appendChild(space);
        
        const abbrevSpan = document.createElement("span");
        abbrevSpan.style.fontSize = "0.85em";
        abbrevSpan.style.fontWeight = "400";
        abbrevSpan.textContent = "(";
        nameTd.appendChild(abbrevSpan);
        
        const teamLink = document.createElement("a");
        teamLink.href = `/team.html?team=${teamSlug}`;
        teamLink.textContent = abbreviation;
        teamLink.style.color = "var(--muted)"; // Use muted color (different from teal name link)
        teamLink.style.fontSize = "0.85em";
        teamLink.style.fontWeight = "400";
        teamLink.style.textDecoration = "none";
        teamLink.addEventListener("mouseenter", () => {
          teamLink.style.color = "var(--accent)";
          teamLink.style.textDecoration = "underline";
        });
        teamLink.addEventListener("mouseleave", () => {
          teamLink.style.color = "var(--muted)";
          teamLink.style.textDecoration = "none";
        });
        nameTd.appendChild(teamLink);
        
        const closeParen = document.createTextNode(")");
        nameTd.appendChild(closeParen);
      } else if (teamSlug) {
        // Fallback: show team name if no abbreviation found
        const space = document.createTextNode(" ");
        nameTd.appendChild(space);
        
        const teamLink = document.createElement("a");
        teamLink.href = `/team.html?team=${teamSlug}`;
        teamLink.textContent = `(${row.team})`;
        teamLink.style.color = "var(--muted)";
        teamLink.style.fontSize = "0.85em";
        teamLink.style.fontWeight = "400";
        teamLink.style.textDecoration = "none";
        teamLink.addEventListener("mouseenter", () => {
          teamLink.style.color = "var(--accent)";
          teamLink.style.textDecoration = "underline";
        });
        teamLink.addEventListener("mouseleave", () => {
          teamLink.style.color = "var(--muted)";
          teamLink.style.textDecoration = "none";
        });
        nameTd.appendChild(teamLink);
      }
    }
    
    tr.appendChild(nameTd);

    // Weight
    const weightTd = document.createElement("td");
    weightTd.textContent = safe(row.weight);
    tr.appendChild(weightTd);

    // W–L Record
    const recordTd = document.createElement("td");
    recordTd.textContent = safe(row.record);
    tr.appendChild(recordTd);

    // Win% - gradient based on percentage of max (scaled to 75% max gradient)
    const winPctTd = document.createElement("td");
    winPctTd.className = "score-col";
    const winPct = row.metrics?.win_pct || 0;
    const winPctPercent = maxValues.win_pct > 0 ? (winPct / maxValues.win_pct) * 75 : 0;
    winPctTd.style.backgroundColor = getScoreColor(winPctPercent);
    winPctTd.textContent = safe(winPct, (v) => Math.round(v * 100) + "%");
    tr.appendChild(winPctTd);

    // Bonus% - gradient based on percentage of max (scaled to 75% max gradient)
    const bonusPctTd = document.createElement("td");
    bonusPctTd.className = "score-col";
    const bonusPct = row.metrics?.bonus_pct || 0;
    const bonusPctPercent = maxValues.bonus_pct > 0 ? (bonusPct / maxValues.bonus_pct) * 75 : 0;
    bonusPctTd.style.backgroundColor = getScoreColor(bonusPctPercent);
    bonusPctTd.textContent = safe(bonusPct, (v) => Math.round(v * 100) + "%");
    tr.appendChild(bonusPctTd);

    // Pin% - gradient based on percentage of max (scaled to 75% max gradient)
    const pinPctTd = document.createElement("td");
    pinPctTd.className = "score-col";
    const fallPct = row.metrics?.fall_pct || 0;
    const fallPctPercent = maxValues.fall_pct > 0 ? (fallPct / maxValues.fall_pct) * 75 : 0;
    pinPctTd.style.backgroundColor = getScoreColor(fallPctPercent);
    pinPctTd.textContent = safe(fallPct, (v) => Math.round(v * 100) + "%");
    tr.appendChild(pinPctTd);

    // Ranked Wins - gradient based on percentage of max (scaled to 75% max gradient)
    const rkwTd = document.createElement("td");
    rkwTd.className = "score-col";
    const rankedWins = row.metrics?.ranked_wins || 0;
    const rankedWinsPercent = maxValues.ranked_wins > 0 ? (rankedWins / maxValues.ranked_wins) * 75 : 0;
    rkwTd.style.backgroundColor = getScoreColor(rankedWinsPercent);
    rkwTd.textContent = safe(rankedWins);
    tr.appendChild(rkwTd);

    // Top 10 Wins - gradient based on percentage of max (scaled to 75% max gradient)
    const top10wTd = document.createElement("td");
    top10wTd.className = "score-col";
    const top10Wins = row.metrics?.top10_wins || 0;
    const top10WinsPercent = maxValues.top10_wins > 0 ? (top10Wins / maxValues.top10_wins) * 75 : 0;
    top10wTd.style.backgroundColor = getScoreColor(top10WinsPercent);
    top10wTd.textContent = safe(top10Wins);
    tr.appendChild(top10wTd);

    // Ranked Bonus% - gradient based on percentage of max (scaled to 75% max gradient)
    const rkbonPctTd = document.createElement("td");
    rkbonPctTd.className = "score-col";
    const rankedBonusPct = row.metrics?.ranked_bonus_pct || 0;
    const rankedBonusPctPercent = maxValues.ranked_bonus_pct > 0 ? (rankedBonusPct / maxValues.ranked_bonus_pct) * 75 : 0;
    rkbonPctTd.style.backgroundColor = getScoreColor(rankedBonusPctPercent);
    rkbonPctTd.textContent = safe(rankedBonusPct, (v) => Math.round(v * 100) + "%");
    tr.appendChild(rkbonPctTd);

    // FreshScore - Gold/Silver/Bronze badges based on rank
    const freshScoreTd = document.createElement("td");
    freshScoreTd.className = "score-col";
    freshScoreTd.style.textAlign = "center";
    
    const freshScore = row.fresh_score || 0;
    const rank = row.rank;
    
    // Create badge based on rank: #1 gold, #2 silver, #3-5 bronze, others no badge
    if (rank === 1) {
      const badge = document.createElement("span");
      badge.className = "rank-badge medal-gold";
      badge.textContent = safe(freshScore, (v) => v.toFixed(2));
      freshScoreTd.appendChild(badge);
    } else if (rank === 2) {
      const badge = document.createElement("span");
      badge.className = "rank-badge medal-silver";
      badge.textContent = safe(freshScore, (v) => v.toFixed(2));
      freshScoreTd.appendChild(badge);
    } else if (rank >= 3 && rank <= 5) {
      const badge = document.createElement("span");
      badge.className = "rank-badge medal-bronze";
      badge.textContent = safe(freshScore, (v) => v.toFixed(2));
      freshScoreTd.appendChild(badge);
    } else {
      // No badge for ranks 6+
      freshScoreTd.textContent = safe(freshScore, (v) => v.toFixed(2));
    }
    
    tr.appendChild(freshScoreTd);

    tbody.appendChild(tr);
  });
}

// ========================================
// Initialize Page
// ========================================
async function init() {
  const season = resolveSeason();

  try {
    // Update season info
    document.getElementById("season-info").textContent = `Season ${season}`;

    // Load and render data
    const data = await fetchJSON(`/data/awards/freshman/${season}/freshman_${season}.json`);

    // Validate data structure
    if (!data || !Array.isArray(data.rows)) {
      throw new Error("Invalid data structure: missing 'rows' array");
    }

    // Update description
    if (data.description) {
      document.getElementById("description").textContent = data.description;
    }

    // Render table
    await renderFreshmanTable(data);
  } catch (error) {
    console.error("Error loading Freshman of the Year data:", error);
    console.error("Error stack:", error.stack);
    const tbody = document.querySelector("#freshman-table tbody");
    if (!tbody) {
      console.error("Could not find #freshman-table tbody");
      return;
    }
    tbody.innerHTML = `
      <tr>
        <td colspan="11" style="text-align: center; padding: 2em; color: var(--muted);">
          Error loading data: ${error.message}
        </td>
      </tr>
    `;
  }
}

// Initialize when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

