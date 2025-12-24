// ========================================
// Hodge Trophy Watch Page
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

// ========================================
// Render Hodge Table
// ========================================
async function renderHodgeTable(data) {
  if (!data || !data.rows || data.rows.length === 0) {
    const eligibleTbody = document.querySelector("#eligible-tbody");
    eligibleTbody.innerHTML = `
      <tr>
        <td colspan="12" style="text-align: center; padding: 2em; color: var(--muted);">
          No data available
        </td>
      </tr>
    `;
    return;
  }

  // Split into eligible and ineligible
  const eligibleRows = data.rows.filter(r => r.eligible);
  const ineligibleRows = data.rows.filter(r => !r.eligible);

  const eligibleTbody = document.querySelector("#eligible-tbody");
  const ineligibleTbody = document.querySelector("#ineligible-tbody");
  
  eligibleTbody.innerHTML = "";
  ineligibleTbody.innerHTML = "";

  // Pre-load all team abbreviations
  const teamNames = [...new Set(data.rows.map(row => row.team).filter(Boolean))];
  await Promise.all(teamNames.map(teamName => getTeamAbbreviation(teamName)));

  // Render eligible rows
  eligibleRows.forEach((row) => {
    const tr = createHodgeRow(row, false);
    eligibleTbody.appendChild(tr);
  });

  // Render ineligible rows
  ineligibleRows.forEach((row) => {
    const tr = createHodgeRow(row, true);
    ineligibleTbody.appendChild(tr);
  });
}

function createHodgeRow(row, isIneligible) {
  const tr = document.createElement("tr");
  if (isIneligible) {
    tr.classList.add("ineligible-row");
    if (row.eligibility_reason) {
      tr.setAttribute("title", row.eligibility_reason);
    }
  }

  const comp = row.components;

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

  // Record Pair - W–L (raw) + Score (normalized)
  const recordPairTd = document.createElement("td");
  recordPairTd.className = "pair-cell";
  recordPairTd.setAttribute("colspan", "2");
  const recordPairWrapper = document.createElement("div");
  recordPairWrapper.className = "pair-wrapper";
  const recordRawDiv = document.createElement("div");
  recordRawDiv.className = "cell raw";
  recordRawDiv.textContent = `${comp.record.raw.wins}–${comp.record.raw.losses}`;
  const recordScoreDiv = document.createElement("div");
  recordScoreDiv.className = "cell normalized";
  recordScoreDiv.textContent = safe(comp.record.score, (v) => v.toFixed(1));
  recordScoreDiv.style.backgroundColor = getScoreColor(comp.record.score);
  recordScoreDiv.setAttribute("title", `Normalized score: ${comp.record.score.toFixed(1)} × ${comp.record.weight} = ${comp.record.contribution.toFixed(2)}`);
  recordPairWrapper.appendChild(recordRawDiv);
  recordPairWrapper.appendChild(recordScoreDiv);
  recordPairTd.appendChild(recordPairWrapper);
  tr.appendChild(recordPairTd);

  // Quality Pair - Ranked Wins (raw) + Score (normalized)
  const qualityPairTd = document.createElement("td");
  qualityPairTd.className = "pair-cell";
  qualityPairTd.setAttribute("colspan", "2");
  const qualityPairWrapper = document.createElement("div");
  qualityPairWrapper.className = "pair-wrapper";
  const qualityRawDiv = document.createElement("div");
  qualityRawDiv.className = "cell raw";
  qualityRawDiv.textContent = safe(comp.quality.raw.ranked_wins);
  const qualityScoreDiv = document.createElement("div");
  qualityScoreDiv.className = "cell normalized";
  qualityScoreDiv.textContent = safe(comp.quality.score, (v) => v.toFixed(1));
  qualityScoreDiv.style.backgroundColor = getScoreColor(comp.quality.score);
  qualityScoreDiv.setAttribute("title", `Normalized score: ${comp.quality.score.toFixed(1)} × ${comp.quality.weight} = ${comp.quality.contribution.toFixed(2)}`);
  qualityPairWrapper.appendChild(qualityRawDiv);
  qualityPairWrapper.appendChild(qualityScoreDiv);
  qualityPairTd.appendChild(qualityPairWrapper);
  tr.appendChild(qualityPairTd);

  // Dominance Pair - Avg TP (raw) + Score (normalized)
  const domPairTd = document.createElement("td");
  domPairTd.className = "pair-cell";
  domPairTd.setAttribute("colspan", "2");
  const domPairWrapper = document.createElement("div");
  domPairWrapper.className = "pair-wrapper";
  const domRawDiv = document.createElement("div");
  domRawDiv.className = "cell raw";
  domRawDiv.textContent = safe(comp.dominance.raw.avg_team_points, (v) => v.toFixed(2));
  const domScoreDiv = document.createElement("div");
  domScoreDiv.className = "cell normalized";
  domScoreDiv.textContent = safe(comp.dominance.score, (v) => v.toFixed(1));
  domScoreDiv.style.backgroundColor = getScoreColor(comp.dominance.score);
  domScoreDiv.setAttribute("title", `Normalized score: ${comp.dominance.score.toFixed(1)} × ${comp.dominance.weight} = ${comp.dominance.contribution.toFixed(2)}`);
  domPairWrapper.appendChild(domRawDiv);
  domPairWrapper.appendChild(domScoreDiv);
  domPairTd.appendChild(domPairWrapper);
  tr.appendChild(domPairTd);

  // Pins Pair - Pin % (raw) + Score (normalized)
  const pinsPairTd = document.createElement("td");
  pinsPairTd.className = "pair-cell";
  pinsPairTd.setAttribute("colspan", "2");
  const pinsPairWrapper = document.createElement("div");
  pinsPairWrapper.className = "pair-wrapper";
  const pinsRawDiv = document.createElement("div");
  pinsRawDiv.className = "cell raw";
  pinsRawDiv.textContent = safe(comp.pins.raw.pin_pct, (v) => Math.round(v * 100) + "%");
  const pinsScoreDiv = document.createElement("div");
  pinsScoreDiv.className = "cell normalized";
  pinsScoreDiv.textContent = safe(comp.pins.score, (v) => v.toFixed(1));
  pinsScoreDiv.style.backgroundColor = getScoreColor(comp.pins.score);
  pinsScoreDiv.setAttribute("title", `Normalized score: ${comp.pins.score.toFixed(1)} × ${comp.pins.weight} = ${comp.pins.contribution.toFixed(2)}`);
  pinsPairWrapper.appendChild(pinsRawDiv);
  pinsPairWrapper.appendChild(pinsScoreDiv);
  pinsPairTd.appendChild(pinsPairWrapper);
  tr.appendChild(pinsPairTd);

  // Hodge Score (bold)
  const hodgeScoreTd = document.createElement("td");
  hodgeScoreTd.style.fontWeight = "600";
  hodgeScoreTd.textContent = safe(row.hodge_score, (v) => v.toFixed(2));
  tr.appendChild(hodgeScoreTd);

  return tr;
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
    const data = await fetchJSON(`/data/awards/hodge/${season}/hodge_${season}.json`);

    // Update description
    if (data.description) {
      document.getElementById("description").textContent = data.description;
    }

    // Render table
    await renderHodgeTable(data);
  } catch (error) {
    console.error("Error loading Hodge Trophy data:", error);
    const eligibleTbody = document.querySelector("#eligible-tbody");
    eligibleTbody.innerHTML = `
      <tr>
        <td colspan="12" style="text-align: center; padding: 2em; color: var(--muted);">
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
