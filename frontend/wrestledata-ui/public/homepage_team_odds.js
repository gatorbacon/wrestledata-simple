// ========================================
// Homepage: Team Championship Odds preview (top 10, links to /team_odds.html)
// Shares the .rangebar / .place-medal-* / expand-row CSS in styles.css with
// team_odds.js -- always shows the newest available date (no date picker,
// that's a full-page-only feature).
// ========================================

const HTO_SEASON = "2027";
const HTO_SCALE_MAX = 200;

let htoTeams = [];
let htoExpandedTeam = null;

function htoTeamNameToSlug(name) {
  if (!name) return "";
  return name.toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^\w_]/g, "")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function htoRankBadge(rank) {
  const badge = document.createElement("span");
  badge.className = "rank-badge";
  if (rank === 1) badge.classList.add("medal-gold");
  else if (rank === 2) badge.classList.add("medal-silver");
  else if (rank === 3) badge.classList.add("medal-bronze");
  else badge.classList.add("standard");
  badge.textContent = `#${rank}`;
  return badge;
}

function htoFormatPct(pct) {
  if (pct === 0) return "—";
  if (pct <= 0.49) return "<1%";
  return `${Math.round(pct)}%`;
}

function htoOrdinal(n) {
  const s = ["th", "st", "nd", "rd"], v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

// Running total of team.p_place walked left-to-right (1st -> 10th): index p-1
// holds P(finish p-th or better). This is what the green median-bar visually
// represents, so the printed grid numbers use it too instead of the marginal
// (exactly-this-place) probability -- otherwise a heavy favorite reads as
// "green coverage, but 0%" on the cells past its typical finish.
function htoCumulativePlace(pPlace) {
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
function htoMedianCrossingBarLength(cum) {
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

function htoCreatePlaceGrid(team) {
  const cell = document.createElement("td");
  cell.className = "place-grid-cell";
  cell.colSpan = 10;

  const wrap = document.createElement("div");
  wrap.className = "place-grid-wrap";

  const cum = htoCumulativePlace(team.p_place);

  const barLength = htoMedianCrossingBarLength(cum);
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
    span.textContent = htoFormatPct(pct);
    span.title = `${htoFormatPct(pct)} chance of finishing ${htoOrdinal(p)} or better`;
    grid.appendChild(span);
  }
  wrap.appendChild(grid);

  cell.appendChild(wrap);
  return cell;
}

function htoRangeBar(t) {
  const lo = t.p5, hi = t.p95, exp = t.expected;
  const loPct = (100 * lo) / HTO_SCALE_MAX;
  const hiPct = (100 * hi) / HTO_SCALE_MAX;
  const expPct = (100 * exp) / HTO_SCALE_MAX;
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

function htoRenderTable() {
  const tbody = document.querySelector("#team-odds-preview-table tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  htoTeams.forEach((team, i) => {
    const rank = i + 1;
    const isExpanded = htoExpandedTeam === team.team;

    const tr = document.createElement("tr");
    tr.className = `expandable-row ${isExpanded ? "expanded" : "collapsed"}`;

    const expandTd = document.createElement("td");
    const expandIcon = document.createElement("span");
    expandIcon.className = "expand-icon";
    expandTd.appendChild(expandIcon);
    tr.appendChild(expandTd);

    const rankTd = document.createElement("td");
    rankTd.appendChild(htoRankBadge(rank));
    tr.appendChild(rankTd);

    const teamTd = document.createElement("td");
    teamTd.className = "name";
    const teamLink = document.createElement("a");
    teamLink.href = `/team.html?team=${htoTeamNameToSlug(team.team)}`;
    teamLink.textContent = team.team;
    teamTd.appendChild(teamLink);
    tr.appendChild(teamTd);

    const rangeTd = document.createElement("td");
    rangeTd.appendChild(htoRangeBar(team));
    tr.appendChild(rangeTd);

    tr.appendChild(htoCreatePlaceGrid(team));

    tbody.appendChild(tr);

    const toggle = (e) => {
      if (e.target.tagName === "A") return;
      htoExpandedTeam = htoExpandedTeam === team.team ? null : team.team;
      htoRenderTable();
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

async function loadTeamOddsPreview() {
  const infoEl = document.getElementById("team-odds-preview-info");
  const tbody = document.querySelector("#team-odds-preview-table tbody");
  if (!tbody) return;

  try {
    const idxRes = await fetch(`/data/team_odds/${HTO_SEASON}/index.json`);
    if (!idxRes.ok) throw new Error("no index");
    const idx = await idxRes.json();
    const newestDate = (idx.dates || [])[0];
    if (!newestDate) throw new Error("no dates");

    const res = await fetch(`/data/team_odds/${HTO_SEASON}/${newestDate}.json`);
    if (!res.ok) throw new Error("no data file");
    const data = await res.json();
    htoTeams = (data.teams || []).slice().sort((a, b) => b.expected - a.expected).slice(0, 10);

    if (infoEl) {
      const label = new Date(newestDate + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
      infoEl.textContent = `${label} rankings · top 10 of ${data.teams.length} teams`;
    }

    htoRenderTable();
  } catch (err) {
    console.error("Error loading team odds preview:", err);
    if (infoEl) infoEl.textContent = "Data unavailable";
  }
}

document.addEventListener("DOMContentLoaded", loadTeamOddsPreview);
