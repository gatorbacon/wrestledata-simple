// ========================================
// Team Championship Odds (full page)
// ========================================

const TO_SEASON = "2027"; // 2026-27 season -- independent of the site's resolveSeason() (still "2026")
const SCALE_MAX = 200; // fixed domain for the scoring-range bar, shared across every team

function toTeamNameToSlug(name) {
  if (!name) return "";
  return name.toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^\w_]/g, "")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function toRankBadge(rank) {
  if (rank === null || rank === undefined) return document.createTextNode("—");
  const badge = document.createElement("span");
  badge.className = "rank-badge";
  if (rank === 1) badge.classList.add("medal-gold");
  else if (rank === 2) badge.classList.add("medal-silver");
  else if (rank === 3) badge.classList.add("medal-bronze");
  else badge.classList.add("standard");
  badge.textContent = `#${rank}`;
  return badge;
}

function formatPct(pct) {
  if (pct === 0) return "—";
  if (pct <= 0.49) return "<1%";
  return `${Math.round(pct)}%`;
}

function ordinal(n) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

// Running total of team.p_place walked left-to-right (1st -> 10th): index p-1
// holds P(finish p-th or better). This is what the green median-bar visually
// represents, so the printed grid numbers use it too instead of the marginal
// (exactly-this-place) probability -- otherwise a heavy favorite reads as
// "green coverage, but 0%" on the cells past its typical finish.
function cumulativePlace(pPlace) {
  const cum = [];
  let running = 0;
  for (let p = 1; p <= 10; p++) {
    running += pPlace[String(p)] || 0;
    cum.push(running);
  }
  return cum;
}

// Where does cumulative probability cross 50%? Returns null if P(top10)
// itself never reaches 50% -- the true median lies past 10th, off the
// visible grid entirely.
function medianCrossingBarLength(cum) {
  for (let p = 1; p <= 10; p++) {
    const prev = p === 1 ? 0 : cum[p - 2];
    const total = cum[p - 1];
    if (total >= 50) {
      const pct = total - prev;
      const fracInto = pct > 0 ? (50 - prev) / pct : 0;
      const posFromLeft = ((p - 1) + fracInto) / 10 * 100;
      return 100 - posFromLeft; // bar fills right-to-left, so length = distance from the right edge
    }
  }
  return null;
}

function createPlaceGrid(team) {
  const cell = document.createElement("td");
  cell.className = "place-grid-cell";
  cell.colSpan = 10;

  const wrap = document.createElement("div");
  wrap.className = "place-grid-wrap";

  const cum = cumulativePlace(team.p_place);

  const barLength = medianCrossingBarLength(cum);
  if (barLength !== null) {
    const bar = document.createElement("div");
    bar.className = "median-bar";
    bar.style.width = `${barLength.toFixed(1)}%`;
    bar.title = `50% chance of finishing this well or better`;
    wrap.appendChild(bar);
  }

  const grid = document.createElement("div");
  grid.className = "place-grid";
  for (let p = 1; p <= 10; p++) {
    const pct = cum[p - 1];
    const span = document.createElement("span");
    span.className = "place-cell-label" + (pct <= 0.49 ? " dim" : "");
    span.textContent = formatPct(pct);
    span.title = `${formatPct(pct)} chance of finishing ${ordinal(p)} or better`;
    grid.appendChild(span);
  }
  wrap.appendChild(grid);

  cell.appendChild(wrap);
  return cell;
}

function createRangeBar(t) {
  const lo = t.p5, hi = t.p95, exp = t.expected;
  const loPct = (100 * lo) / SCALE_MAX;
  const hiPct = (100 * hi) / SCALE_MAX;
  const expPct = (100 * exp) / SCALE_MAX;
  const widthPct = hiPct - loPct;
  // Where the expected value sits within the lo-hi band, so the opacity
  // gradient below peaks there even when the distribution is skewed.
  const expPosInBand = widthPct > 0 ? Math.min(100, Math.max(0, ((expPct - loPct) / widthPct) * 100)) : 50;

  const wrap = document.createElement("div");
  wrap.className = "rangebar-container";
  wrap.innerHTML = `
    <div class="range-expected-big" style="left:${expPct.toFixed(2)}%">${exp.toFixed(0)}</div>
    <div class="rangebar" role="img" aria-label="90% confidence range ${lo.toFixed(0)} to ${hi.toFixed(0)}, expected ${exp.toFixed(0)}">
      <div class="rangebar-track"></div>
      <div class="rangebar-band" style="left:${loPct.toFixed(2)}%;width:${widthPct.toFixed(2)}%;background:linear-gradient(90deg, rgba(var(--accent-rgb),0.12) 0%, rgba(var(--accent-rgb),0.85) ${expPosInBand.toFixed(1)}%, rgba(var(--accent-rgb),0.12) 100%)"></div>
      <div class="rangebar-edge-tick" style="left:${loPct.toFixed(2)}%"></div>
      <div class="rangebar-edge-tick" style="left:${hiPct.toFixed(2)}%"></div>
      <div class="rangebar-tick" style="left:${expPct.toFixed(2)}%"></div>
      <div class="range-edge-label" style="left:${loPct.toFixed(2)}%">${lo.toFixed(0)}</div>
      <div class="range-edge-label" style="left:${hiPct.toFixed(2)}%">${hi.toFixed(0)}</div>
    </div>
  `;
  return wrap;
}

let allDates = [];
let currentDate = null;
let teamData = [];
let expandedTeam = null;

async function loadDateIndex() {
  try {
    const res = await fetch(`/data/team_odds/${TO_SEASON}/index.json`);
    if (!res.ok) throw new Error("no index");
    const data = await res.json();
    return data.dates || [];
  } catch {
    return [];
  }
}

function formatDateLabel(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function renderDateTabs() {
  const container = document.getElementById("date-tabs");
  container.innerHTML = "";
  allDates.forEach((date) => {
    const btn = document.createElement("button");
    btn.className = "weight-tab" + (date === currentDate ? " active" : "");
    btn.textContent = formatDateLabel(date);
    btn.addEventListener("click", () => {
      if (date === currentDate) return;
      currentDate = date;
      expandedTeam = null;
      renderDateTabs();
      loadTeamData(currentDate);
    });
    container.appendChild(btn);
  });
}

async function loadTeamData(date) {
  document.getElementById("season-info").textContent = "Loading…";
  try {
    const res = await fetch(`/data/team_odds/${TO_SEASON}/${date}.json`);
    if (!res.ok) throw new Error(`Failed to load ${date}`);
    const data = await res.json();
    teamData = data.teams || [];
    document.getElementById("season-info").textContent =
      `${formatDateLabel(date)} rankings · ${data.trials.toLocaleString()} simulated trials · ${teamData.length} teams`;
    renderLeaderboard();
  } catch (err) {
    console.error(err);
    document.getElementById("season-info").textContent = "Error loading data";
  }
}

function renderLeaderboard() {
  const sorted = [...teamData].sort((a, b) => b.expected - a.expected);
  const tbody = document.querySelector("#team-odds-table tbody");
  tbody.innerHTML = "";

  sorted.forEach((team, index) => {
    const rank = index + 1;
    const isExpanded = expandedTeam === team.team;

    const tr = document.createElement("tr");
    tr.className = `expandable-row ${isExpanded ? "expanded" : "collapsed"}`;

    const expandTd = document.createElement("td");
    const expandIcon = document.createElement("span");
    expandIcon.className = "expand-icon";
    expandTd.appendChild(expandIcon);
    tr.appendChild(expandTd);

    const rankTd = document.createElement("td");
    rankTd.appendChild(toRankBadge(rank));
    tr.appendChild(rankTd);

    const teamTd = document.createElement("td");
    teamTd.className = "name";
    const teamLink = document.createElement("a");
    teamLink.href = `/team.html?team=${toTeamNameToSlug(team.team)}`;
    teamLink.textContent = team.team;
    teamTd.appendChild(teamLink);
    tr.appendChild(teamTd);

    const rangeTd = document.createElement("td");
    rangeTd.appendChild(createRangeBar(team));
    tr.appendChild(rangeTd);

    tr.appendChild(createPlaceGrid(team));

    tbody.appendChild(tr);

    const toggle = (e) => {
      if (e.target.tagName === "A") return;
      expandedTeam = expandedTeam === team.team ? null : team.team;
      renderLeaderboard();
    };
    tr.addEventListener("click", toggle);
    expandIcon.addEventListener("click", (e) => {
      e.stopPropagation();
      toggle(e);
    });

    if (isExpanded) {
      const breakdownTr = document.createElement("tr");
      breakdownTr.className = "weight-breakdown expanded";
      const breakdownTd = document.createElement("td");
      breakdownTd.colSpan = 14;

      const breakdownTable = document.createElement("table");
      const thead = document.createElement("thead");
      const headerRow = document.createElement("tr");
      ["Wt", "Wrestler", "Rank", "Expected", "Min", "Max"].forEach((h) => {
        const th = document.createElement("th");
        th.textContent = h;
        headerRow.appendChild(th);
      });
      thead.appendChild(headerRow);
      breakdownTable.appendChild(thead);

      const tbody2 = document.createElement("tbody");
      (team.lineup_detail || []).forEach((w) => {
        const row = document.createElement("tr");
        const weightTd = document.createElement("td");
        weightTd.className = "wd-cell";
        weightTd.textContent = w.weight;
        row.appendChild(weightTd);

        const nameTd = document.createElement("td");
        nameTd.className = "wd-cell wd-name";
        if (w.rank !== null) {
          nameTd.textContent = w.name;
        } else {
          nameTd.innerHTML = '<span class="unranked-note">Unranked</span>';
        }
        row.appendChild(nameTd);

        const rankTd2 = document.createElement("td");
        rankTd2.className = "wd-cell";
        rankTd2.textContent = w.rank !== null ? `#${w.rank}` : "—";
        row.appendChild(rankTd2);

        const expTd = document.createElement("td");
        expTd.className = "wd-cell";
        expTd.textContent = Math.round(w.expected);
        row.appendChild(expTd);

        const minTd = document.createElement("td");
        minTd.className = "wd-cell";
        minTd.textContent = Math.round(w.p5);
        row.appendChild(minTd);

        const maxTd = document.createElement("td");
        maxTd.className = "wd-cell";
        maxTd.textContent = Math.round(w.p95);
        row.appendChild(maxTd);

        tbody2.appendChild(row);
      });
      breakdownTable.appendChild(tbody2);
      breakdownTd.appendChild(breakdownTable);
      breakdownTr.appendChild(breakdownTd);
      tbody.appendChild(breakdownTr);
    }
  });
}

async function init() {
  allDates = await loadDateIndex();
  if (allDates.length === 0) {
    document.getElementById("season-info").textContent = "No data available";
    return;
  }
  currentDate = allDates[0]; // index.json is newest-first
  renderDateTabs();
  await loadTeamData(currentDate);
}

document.addEventListener("DOMContentLoaded", init);
