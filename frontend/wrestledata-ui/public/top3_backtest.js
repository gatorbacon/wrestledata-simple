const SVG_NS = "http://www.w3.org/2000/svg";
// Hardcoded to match styles.css's --pill-3/--pill-1/--bad token values.
// The site's [data-theme="dark"] palette is currently dormant (no page sets
// the attribute), so these stay correct as long as that remains true.
const TEAM_COLOR_HEX = ["#2b6cb0", "#ed8936", "#c53030"];

let seasonIndex = [];
let currentSeason = null;

async function init() {
  const idx = await fetch("/data/top3_backtest/index.json").then((r) => r.json());
  seasonIndex = idx.seasons.sort((a, b) => a.season - b.season);
  currentSeason = seasonIndex[seasonIndex.length - 1].season;
  renderSeasonTabs();
  await loadSeason(currentSeason);
}

function renderSeasonTabs() {
  const container = document.getElementById("season-tabs");
  container.innerHTML = "";
  seasonIndex.forEach((s) => {
    const btn = document.createElement("button");
    btn.className = "weight-tab" + (s.season === currentSeason ? " active" : "");
    btn.textContent = s.label;
    btn.setAttribute("role", "tab");
    btn.addEventListener("click", () => {
      currentSeason = s.season;
      renderSeasonTabs();
      loadSeason(currentSeason);
    });
    container.appendChild(btn);
  });
}

async function loadSeason(season) {
  const data = await fetch(`/data/top3_backtest/${season}.json`).then((r) => r.json());
  renderLegend(data);
  renderChart(data);
  renderTable(data);
  renderMethodology();
}

function renderLegend(data) {
  const row = document.getElementById("legend-row");
  row.innerHTML = "";
  data.top3_teams.forEach((t, i) => {
    const item = document.createElement("div");
    item.className = "bt-legend-item";
    item.innerHTML = `<span class="bt-swatch" style="background:${TEAM_COLOR_HEX[i]}"></span>${t.team} <span class="real">(real: ${t.real_score})</span>`;
    row.appendChild(item);
  });
}

function renderMethodology() {
  document.getElementById("methodology").innerHTML =
    "<b>Methodology:</b> for each real season snapshot, each team's roster uses that month's real FloWrestling rank per weight, " +
    "priced from the rank-based score distribution, adjusted by the team's program-strength offset, plus an individual track-record " +
    "modifier for any nationally top-3-ranked wrestler on the roster (upside-only, using the best of their 1-year or 2-year prior " +
    "scoring average, capped so a lower-ranked wrestler can never out-project the wrestler ranked above them). The individual-modifier " +
    "regression is refit for this chart excluding the shown season's own transition, so it never sees that season's own outcome. " +
    "The tournament-stage point uses each team's real final seed instead of a rank snapshot.";
}

function renderTable(data) {
  const head = document.getElementById("results-head");
  head.innerHTML = "<th>Team</th>" + data.labels.map((l) => `<th class="num">${l}</th>`).join("") + '<th class="num">Real Final</th>';

  const body = document.getElementById("results-body");
  body.innerHTML = "";
  data.top3_teams.forEach((t) => {
    const series = data.series[t.team];
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td style="font-weight:700;">${t.team}</td>` +
      series.map((pt) => `<td class="num">${pt.exp == null ? "—" : Math.round(pt.exp)}</td>`).join("") +
      `<td class="num" style="font-weight:700;">${t.real_score}</td>`;
    body.appendChild(tr);
  });
}

function el(tag, attrs) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

// Mirrors teamNameToSlug() in frontend/hs-ky-ui/public/app.js so logo
// filenames follow the same convention used elsewhere in the codebase.
function teamSlug(name) {
  return (name || "")
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/[^\w_]/g, "")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
}

let logoIdSeq = 0;

function renderChart(data) {
  const wrap = document.getElementById("chart-wrap");
  wrap.innerHTML = "";

  const W = 1030, H = 500;
  const padL = 56, padR = 110, padT = 24, padB = 40;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const labels = data.labels;
  const n = labels.length;
  const xFor = (i) => padL + (plotW * i) / (n - 1);

  // y scale: 0 to a round number above the max seen value
  let maxVal = 0;
  data.top3_teams.forEach((t) => {
    data.series[t.team].forEach((pt) => {
      if (pt.p95 != null) maxVal = Math.max(maxVal, pt.p95);
      if (pt.exp != null) maxVal = Math.max(maxVal, pt.exp);
    });
    maxVal = Math.max(maxVal, t.real_score);
  });
  const yMax = Math.ceil((maxVal * 1.08) / 50) * 50;
  const yFor = (v) => padT + plotH - (plotH * v) / yMax;

  const svg = el("svg", {
    viewBox: `0 0 ${W} ${H}`,
    role: "img",
    "aria-label": `Line chart of projected team points by month for ${data.label}'s top 3 teams, with real final results marked`,
  });
  svg.style.width = "100%";
  svg.style.height = "auto";

  const gridGroup = el("g", {});
  for (let v = 0; v <= yMax; v += 50) {
    const y = yFor(v);
    gridGroup.appendChild(el("line", { class: "bt-gridline", x1: padL, y1: y, x2: W - padR, y2: y }));
    const t = el("text", { class: "bt-axis-label", x: padL - 12, y: y + 4, "text-anchor": "end" });
    t.textContent = v;
    gridGroup.appendChild(t);
  }
  svg.appendChild(gridGroup);
  svg.appendChild(el("line", { class: "bt-axis-line", x1: padL, y1: padT + plotH, x2: W - padR, y2: padT + plotH }));

  labels.forEach((lbl, i) => {
    const t = el("text", { class: "bt-cat-label", x: xFor(i), y: H - 8 });
    t.textContent = lbl;
    svg.appendChild(t);
  });

  const lastX = xFor(n - 1);
  const badgeCx = lastX + 30; // logo circle center, out in the right margin
  const R = 11;               // logo circle radius

  // top3_teams is already sorted descending by real_score, so trueY (which
  // grows as score shrinks) is already ascending -- a single forward pass
  // is enough to push badges apart when two teams' real scores land close
  // together on the y-axis (they'd otherwise overlap).
  const minGap = 2 * R + 6;
  let prevY = -Infinity;
  const badgeYs = data.top3_teams.map((t) => {
    const trueY = yFor(t.real_score);
    const y = trueY - prevY < minGap ? prevY + minGap : trueY;
    prevY = y;
    return { trueY, y };
  });

  data.top3_teams.forEach((t, teamIdx) => {
    const color = TEAM_COLOR_HEX[teamIdx];
    const series = data.series[t.team];

    const bandPts = [];
    series.forEach((pt, i) => { if (pt.p95 != null) bandPts.push(`${xFor(i)},${yFor(pt.p95)}`); });
    for (let i = series.length - 1; i >= 0; i--) { if (series[i].p5 != null) bandPts.push(`${xFor(i)},${yFor(series[i].p5)}`); }
    if (bandPts.length) svg.appendChild(el("polygon", { points: bandPts.join(" "), fill: color, "fill-opacity": 0.14 }));

    const linePts = series.map((pt, i) => (pt.exp != null ? `${xFor(i)},${yFor(pt.exp)}` : null)).filter(Boolean).join(" ");
    svg.appendChild(el("polyline", { points: linePts, fill: "none", stroke: color, "stroke-width": 2.6 }));
    series.forEach((pt, i) => {
      if (pt.exp == null) return;
      svg.appendChild(el("circle", { cx: xFor(i), cy: yFor(pt.exp), r: 3.2, fill: color }));
    });

    // End-of-line real-result badge: a small dot at the TRUE data position
    // (yFor(real_score) -- this is the bug that was here before, it used
    // to just stack badges by team index regardless of actual value),
    // connected by a leader line to the logo badge, which may be nudged
    // vertically to avoid overlapping a neighboring team's badge.
    const { trueY, y: badgeY } = badgeYs[teamIdx];
    svg.appendChild(el("circle", { cx: lastX, cy: trueY, r: 2.6, fill: color }));
    svg.appendChild(el("line", { x1: lastX, y1: trueY, x2: badgeCx - R, y2: badgeY, stroke: color, "stroke-width": 1.3, "stroke-opacity": 0.7 }));

    const slug = teamSlug(t.team);
    const clipId = `bt-logo-clip-${logoIdSeq++}`;
    svg.appendChild(el("clipPath", { id: clipId })).appendChild(el("circle", { cx: badgeCx, cy: badgeY, r: R }));
    svg.appendChild(el("circle", { cx: badgeCx, cy: badgeY, r: R, fill: "var(--panel)", stroke: color, "stroke-width": 2 }));
    const img = el("image", {
      x: badgeCx - R, y: badgeY - R, width: 2 * R, height: 2 * R,
      "clip-path": `url(#${clipId})`, preserveAspectRatio: "xMidYMid meet",
    });
    img.setAttributeNS("http://www.w3.org/1999/xlink", "href", `/assets/team_logos/${slug}.svg`);
    img.addEventListener("error", () => img.remove(), { once: true }); // no logo yet for this team -- fine, just show the ring
    svg.appendChild(img);

    const valText = el("text", { class: "bt-badge-value", x: badgeCx + R + 6, y: badgeY + 4, fill: color });
    valText.textContent = t.real_score;
    svg.appendChild(valText);
  });

  wrap.appendChild(svg);
}

document.addEventListener("DOMContentLoaded", init);
