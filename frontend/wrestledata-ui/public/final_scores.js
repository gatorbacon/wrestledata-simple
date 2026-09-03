// ========================================
// Every Final Score (NCAA D1 wrestling)
// ========================================

const FS_BASE = "/data/final_scores";

const NO_SCORE_DISPLAY = {
  "Fall": "Pin",
  "M.": "Medical forfeit",
  "Inj.": "Injury default",
  "NC": "No contest",
  "For.": "Forfeit",
  "MFFL": "Match forfeit",
  "Def.": "Default",
  "DQ": "Disqualification",
  "other": "Other/unparsed",
};

function fsInt(n) {
  return n.toLocaleString();
}

function fsScore(w, l, winCap, loseCap) {
  const wl = w === winCap ? `${winCap}+` : String(w);
  const ll = l === loseCap ? `${loseCap}+` : String(l);
  return `${wl}–${ll}`;
}

// Win/loss-rate bar gradient: red (0%) -> yellow (50%) -> green (100%).
// Unrelated to the era-coding gradient used on the trend charts below --
// this one always means "worse odds -> better odds" regardless of era.
function winbarColor(t) {
  const RED = [197, 48, 48], YEL = [236, 201, 75], GRN = [56, 161, 105];
  let c0, c1, lt;
  if (t <= 0.5) { c0 = RED; c1 = YEL; lt = t / 0.5; }
  else { c0 = YEL; c1 = GRN; lt = (t - 0.5) / 0.5; }
  const r = Math.round(c0[0] + (c1[0] - c0[0]) * lt);
  const g = Math.round(c0[1] + (c1[1] - c0[1]) * lt);
  const b = Math.round(c0[2] + (c1[2] - c0[2]) * lt);
  return `rgb(${r},${g},${b})`;
}

// ---- Heatmap gradient (rare -> common) ----
const HEAT_STOPS = [
  [0.00, [43, 108, 176]],
  [0.25, [56, 161, 105]],
  [0.50, [236, 201, 75]],
  [0.75, [237, 137, 54]],
  [1.00, [197, 48, 48]],
];
function heatLerp(a, b, t) { return a + (b - a) * t; }
function heatColorAt(t) {
  t = Math.max(0, Math.min(1, t));
  for (let i = 0; i < HEAT_STOPS.length - 1; i++) {
    const [t0, c0] = HEAT_STOPS[i], [t1, c1] = HEAT_STOPS[i + 1];
    if (t >= t0 && t <= t1) {
      const localT = (t - t0) / (t1 - t0);
      const r = Math.round(heatLerp(c0[0], c1[0], localT));
      const g = Math.round(heatLerp(c0[1], c1[1], localT));
      const b = Math.round(heatLerp(c0[2], c1[2], localT));
      return `rgb(${r},${g},${b})`;
    }
  }
  const last = HEAT_STOPS[HEAT_STOPS.length - 1][1];
  return `rgb(${last.join(",")})`;
}

function drawGrid(data) {
  const GRID = data.grid;
  const WIN_CAP = data.win_cap;
  const LOSE_CAP = data.lose_cap;
  const CELL = 26;
  const PAD_LEFT = 46;
  const PAD_BOTTOM = 30;
  const PAD_TOP = 10;
  const PAD_RIGHT = 10;
  const cols = WIN_CAP + 1;
  const rows = LOSE_CAP + 1;

  const canvas = document.getElementById("score-grid");
  const tooltip = document.getElementById("grid-tooltip");
  const dpr = window.devicePixelRatio || 1;
  const widthCss = PAD_LEFT + cols * CELL + PAD_RIGHT;
  const heightCss = PAD_TOP + rows * CELL + PAD_BOTTOM;
  canvas.style.width = widthCss + "px";
  canvas.style.height = heightCss + "px";
  canvas.width = widthCss * dpr;
  canvas.height = heightCss * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  let maxCount = 0;
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) maxCount = Math.max(maxCount, GRID[r][c]);

  function xForCol(c) { return PAD_LEFT + c * CELL; }
  function yForRow(r) { return PAD_TOP + (rows - 1 - r) * CELL; }

  function draw() {
    ctx.clearRect(0, 0, widthCss, heightCss);
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const x = xForCol(c), y = yForRow(r);
        const impossible = r >= c;
        const count = GRID[r][c];
        if (impossible) {
          ctx.fillStyle = "#e7e1d5";
        } else if (count === 0) {
          ctx.fillStyle = "#ffffff";
        } else {
          const t = Math.log(count) / Math.log(maxCount);
          ctx.fillStyle = heatColorAt(t);
        }
        ctx.fillRect(x, y, CELL - 1, CELL - 1);
      }
    }
    ctx.fillStyle = "#6b6153";
    ctx.font = "10px -apple-system, sans-serif";
    ctx.textAlign = "center";
    for (let c = 0; c < cols; c++) {
      const label = c === WIN_CAP ? WIN_CAP + "+" : String(c);
      ctx.fillText(label, xForCol(c) + (CELL - 1) / 2, PAD_TOP + rows * CELL + 16);
    }
    ctx.textAlign = "right";
    for (let r = 0; r < rows; r++) {
      const label = r === LOSE_CAP ? LOSE_CAP + "+" : String(r);
      ctx.fillText(label, PAD_LEFT - 8, yForRow(r) + (CELL - 1) / 2 + 3);
    }
    ctx.save();
    ctx.translate(12, PAD_TOP + (rows * CELL) / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = "center";
    ctx.font = "11px -apple-system, sans-serif";
    ctx.fillStyle = "#8f8574";
    ctx.fillText("LOSER'S SCORE", 0, 0);
    ctx.restore();
    ctx.textAlign = "center";
    ctx.fillStyle = "#8f8574";
    ctx.font = "11px -apple-system, sans-serif";
    ctx.fillText("WINNER'S SCORE", PAD_LEFT + (cols * CELL) / 2, PAD_TOP + rows * CELL + 28);
  }
  draw();

  canvas.onmousemove = (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const c = Math.floor((mx - PAD_LEFT) / CELL);
    const rFromTop = Math.floor((my - PAD_TOP) / CELL);
    const r = rows - 1 - rFromTop;
    if (c < 0 || c >= cols || r < 0 || r >= rows || r >= c) {
      tooltip.style.opacity = 0;
      return;
    }
    const count = GRID[r][c];
    const wLabel = c === WIN_CAP ? WIN_CAP + "+" : c;
    const lLabel = r === LOSE_CAP ? LOSE_CAP + "+" : r;
    if (count === 0) {
      tooltip.innerHTML = `<b>${wLabel}–${lLabel}</b> · never happened`;
    } else {
      const pct = ((100 * count) / data.total_scored_matches).toFixed(2);
      tooltip.innerHTML = `<b>${wLabel}–${lLabel}</b> · ${fsInt(count)} matches (${pct}%)`;
    }
    tooltip.style.left = mx + "px";
    tooltip.style.top = my + "px";
    tooltip.style.opacity = 1;
  };
  canvas.onmouseleave = () => { tooltip.style.opacity = 0; };
}

// ---- Season panel (intro, side tables, points table) ----

function renderSeasonPanel(data) {
  document.getElementById("fs-intro").innerHTML =
    `Every decided NCAA Division I dual-meet and tournament bout from the ` +
    `${data.label} season, plotted by winner's score (across) and loser's ` +
    `score (up), colored by how often that exact final score happened. ` +
    `<b>${fsInt(data.total_scored_matches)} matches</b> ended with a running ` +
    `numeric score (decisions, majors, tech falls, sudden victory, tiebreakers) ` +
    `across <b>${data.unique_combos}</b> distinct final scores.`;

  document.getElementById("side-totals").innerHTML = `
    <div class="stat-row"><span>Decided matches</span><span class="v">${fsInt(data.total_decided_matches)}</span></div>
    <div class="stat-row"><span>Ended with a score</span><span class="v">${fsInt(data.total_scored_matches)}</span></div>
    <div class="stat-row"><span>Distinct final scores</span><span class="v">${data.unique_combos}</span></div>
  `;

  const topBody = document.getElementById("top-combos-body");
  topBody.innerHTML = "";
  data.top_combos.forEach((c) => {
    const pct = (100 * c.count) / data.total_scored_matches;
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="score">${fsScore(c.winner, c.loser, data.win_cap, data.lose_cap)}</td><td>${fsInt(c.count)}</td><td>${pct.toFixed(1)}%</td>`;
    topBody.appendChild(tr);
  });

  const noScore = Object.entries(data.stoppage_breakdown)
    .filter(([k]) => k in NO_SCORE_DISPLAY)
    .sort((a, b) => b[1] - a[1]);
  const stoppageBody = document.getElementById("stoppage-body");
  stoppageBody.innerHTML = "";
  noScore.forEach(([k, v]) => {
    const pct = (100 * v) / data.total_decided_matches;
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${NO_SCORE_DISPLAY[k]}</td><td>${fsInt(v)}</td><td>${pct.toFixed(1)}%</td>`;
    stoppageBody.appendChild(tr);
  });

  const ptsBody = document.getElementById("points-table-body");
  ptsBody.innerHTML = "";
  let crossoverDone = false;
  for (let p = 0; p <= 17; p++) {
    const wins = data.points_wins[p] || 0;
    const losses = data.points_losses[p] || 0;
    const total = wins + losses;
    const pct = total ? (100 * wins) / total : 0;
    const label = p < 17 ? String(p) : "17+";
    let cls = "";
    if (!crossoverDone && pct >= 50) { cls = " crossover"; crossoverDone = true; }
    const tr = document.createElement("tr");
    tr.className = cls.trim();
    tr.innerHTML = `
      <td class="pts">${label}</td><td>${fsInt(wins)}</td><td>${fsInt(losses)}</td>
      <td><div class="winbar-wrap"><div class="winbar-track"><div class="winbar-fill" style="width:${pct.toFixed(1)}%;background:${winbarColor(pct / 100)}"></div></div>
      <span class="winbar-label">${pct.toFixed(1)}%</span></div></td>
    `;
    ptsBody.appendChild(tr);
  }

  document.getElementById("fs-method").innerHTML = `
    <p><b>Methodology (score grid):</b> built from full match-by-match logs for all ${data.team_count} tracked NCAA D1 programs for the ${data.label} season. Each match is deduplicated across both wrestlers' logs. Scores above ${data.win_cap} (winner) or ${data.lose_cap} (loser) are folded into a "${data.win_cap}+"/"${data.lose_cap}+" edge &mdash; together these outliers are a small fraction of matches. Falls, injury defaults, forfeits, disqualifications, and no-contests have no running score and are excluded from the grid (see "How the rest ended").</p>
    <p><b>Methodology (win rate by points):</b> same underlying scored-match data, re-sliced by one wrestler's own point total regardless of the final margin.</p>
  `;

  drawGrid(data);
}

// ---- Season tabs / data loading ----

let fsSeasons = [];
let fsCurrentSeason = null;
const fsSeasonCache = {};

function renderSeasonTabs() {
  [document.getElementById("season-tabs"), document.getElementById("season-tabs-bottom")].forEach((container) => {
    container.innerHTML = "";
    fsSeasons.forEach((s) => {
      const btn = document.createElement("button");
      btn.className = "weight-tab" + (s.season === fsCurrentSeason ? " active" : "");
      btn.textContent = s.label;
      btn.addEventListener("click", () => selectSeason(s.season));
      container.appendChild(btn);
    });
  });
}

async function selectSeason(season) {
  if (season === fsCurrentSeason) return;
  fsCurrentSeason = season;
  renderSeasonTabs();
  await loadSeasonData(season);
}

async function loadSeasonData(season) {
  try {
    if (!fsSeasonCache[season]) {
      const res = await fetch(`${FS_BASE}/${season}.json`);
      if (!res.ok) throw new Error(`Failed to load ${season}`);
      fsSeasonCache[season] = await res.json();
    }
    renderSeasonPanel(fsSeasonCache[season]);
  } catch (err) {
    console.error(err);
  }
}

// ---- Trend charts (era-coded, small-sample-flagged) ----

// Era boundaries derived from the real season year, not an array index --
// so 2027+ data lands in the "2024-present" era automatically with no
// code change here.
function eraOfSeason(y) { return y < 2016 ? 0 : (y <= 2023 ? 1 : 2); }
const ERA_COLORS = ["#9aa5b1", "#2b6cb0", "#ed8936"];
const ERA_LABELS = ["pre-2016", "2016–23", "2024–present"];
// 2020-21 (COVID-shortened season, ~1/3 the usual match volume): kept in
// every chart since it's real data, but drawn hollow/dashed and excluded
// from era averages so it doesn't read as an equal-weight data point.
function isSmallSample(y) { return y === 2021; }
const SMALL_SAMPLE_COLOR = "#cbc7bf";

function eraAverages(years, arr) {
  const buckets = [[], [], []];
  years.forEach((y, i) => {
    if (isSmallSample(y)) return;
    buckets[eraOfSeason(y)].push(arr[i]);
  });
  return buckets.map((b) => (b.length ? b.reduce((s, v) => s + v, 0) / b.length : NaN));
}

function eraDeltaText(values, suffix, decimals) {
  return values.filter((v) => !Number.isNaN(v)).map((v) => v.toFixed(decimals) + suffix).join(" → ");
}

let fsTrend = null;

async function loadTrend() {
  try {
    const res = await fetch(`${FS_BASE}/trend.json`);
    if (!res.ok) throw new Error("Failed to load trend.json");
    fsTrend = await res.json();
    drawMarginChart();
    drawRateChart("trend-tf", "tt-tf", "callout-tf", "tech_fall_rate", "Tech fall rate");
    drawRateChart("trend-md", "tt-md", "callout-md", "major_decision_rate", "Major decision rate");
    drawRateChart("trend-pin", "tt-pin", "callout-pin", "pin_rate", "Pin rate");
  } catch (err) {
    console.error(err);
  }
}

function drawMarginChart() {
  const canvas = document.getElementById("trend-margin");
  const tooltip = document.getElementById("tt-margin");
  const seasons = fsTrend.seasons;
  const years = fsTrend.season_years;
  const n = seasons.length;
  const winner = fsTrend.winner, loser = fsTrend.loser;
  const margin = winner.map((w, i) => w - loser[i]);

  const PAD_LEFT = 42, PAD_RIGHT = 16, PAD_TOP = 16, PAD_BOTTOM = 32;
  const PLOT_W = 1000, PLOT_H = 260;
  const widthCss = PAD_LEFT + PLOT_W + PAD_RIGHT;
  const heightCss = PAD_TOP + PLOT_H + PAD_BOTTOM;
  const dpr = window.devicePixelRatio || 1;
  canvas.style.width = widthCss + "px";
  canvas.style.height = heightCss + "px";
  canvas.width = widthCss * dpr;
  canvas.height = heightCss * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const yMax = Math.ceil(Math.max(...winner) + 1);
  function y(v) { return PAD_TOP + PLOT_H * (1 - v / yMax); }

  const groupW = PLOT_W / n;
  const barW = Math.min(20, groupW * 0.32);

  function draw() {
    ctx.clearRect(0, 0, widthCss, heightCss);

    const ticks = 5;
    ctx.font = "10px -apple-system, sans-serif";
    for (let t = 0; t <= ticks; t++) {
      const v = (yMax * t) / ticks;
      const yy = y(v);
      ctx.strokeStyle = "#e7e1d5";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(PAD_LEFT, yy);
      ctx.lineTo(PAD_LEFT + PLOT_W, yy);
      ctx.stroke();
      ctx.fillStyle = "#6b6153";
      ctx.textAlign = "right";
      ctx.fillText(v.toFixed(0), PAD_LEFT - 8, yy + 3);
    }

    for (let i = 0; i < n; i++) {
      const small = isSmallSample(years[i]);
      const color = ERA_COLORS[eraOfSeason(years[i])];
      const cx = PAD_LEFT + groupW * i + groupW / 2;
      const yBase = y(0);
      const wRect = [cx - barW - 1.5, y(winner[i]), barW, yBase - y(winner[i])];
      const lRect = [cx + 1.5, y(loser[i]), barW, yBase - y(loser[i])];

      if (small) {
        ctx.strokeStyle = SMALL_SAMPLE_COLOR;
        ctx.lineWidth = 1.2;
        ctx.setLineDash([3, 2]);
        ctx.strokeRect(...wRect);
        ctx.strokeRect(...lRect);
        ctx.setLineDash([]);
      } else {
        ctx.fillStyle = color;
        ctx.fillRect(...wRect);
        ctx.globalAlpha = 0.4;
        ctx.fillRect(...lRect);
        ctx.globalAlpha = 1;
      }

      ctx.fillStyle = "#211c16";
      ctx.font = "10px -apple-system, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(seasons[i], cx, PAD_TOP + PLOT_H + 18);
    }

    for (let i = 1; i < n; i++) {
      const cx0 = PAD_LEFT + groupW * (i - 1) + groupW / 2, yy0 = y(margin[i - 1]);
      const cx1 = PAD_LEFT + groupW * i + groupW / 2, yy1 = y(margin[i]);
      const dashed = isSmallSample(years[i - 1]) || isSmallSample(years[i]);
      ctx.lineWidth = 2.2;
      ctx.strokeStyle = dashed ? SMALL_SAMPLE_COLOR : "#211c16";
      ctx.setLineDash(dashed ? [5, 4] : []);
      ctx.beginPath();
      ctx.moveTo(cx0, yy0);
      ctx.lineTo(cx1, yy1);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    for (let i = 0; i < n; i++) {
      const cx = PAD_LEFT + groupW * i + groupW / 2, yy = y(margin[i]);
      const small = isSmallSample(years[i]);
      ctx.beginPath();
      ctx.arc(cx, yy, 3, 0, Math.PI * 2);
      ctx.fillStyle = small ? SMALL_SAMPLE_COLOR : "#211c16";
      ctx.fill();
      ctx.strokeStyle = small ? SMALL_SAMPLE_COLOR : "#fff";
      ctx.lineWidth = small ? 1 : 1.2;
      ctx.stroke();
    }

    ctx.fillStyle = "#8f8574";
    ctx.font = "11px -apple-system, sans-serif";
    ctx.textAlign = "center";
    ctx.save();
    ctx.translate(14, PAD_TOP + PLOT_H / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("POINTS", 0, 0);
    ctx.restore();
  }
  draw();

  canvas.onmousemove = (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    if (mx < PAD_LEFT || mx > PAD_LEFT + PLOT_W || my < PAD_TOP || my > PAD_TOP + PLOT_H) {
      tooltip.style.opacity = 0;
      return;
    }
    let idx = Math.floor((mx - PAD_LEFT) / groupW);
    idx = Math.max(0, Math.min(n - 1, idx));
    const smallNote = isSmallSample(years[idx]) ? "<br><i>Small sample (COVID-shortened) — excluded from era averages</i>" : "";
    tooltip.innerHTML = `<b>${seasons[idx]}</b> (${ERA_LABELS[eraOfSeason(years[idx])]})<br>Winner ${winner[idx].toFixed(2)} · Loser ${loser[idx].toFixed(2)} · Margin ${margin[idx].toFixed(2)}${smallNote}`;
    tooltip.style.left = mx + "px";
    tooltip.style.top = my + "px";
    tooltip.style.opacity = 1;
  };
  canvas.onmouseleave = () => { tooltip.style.opacity = 0; };

  const w = eraAverages(years, winner), l = eraAverages(years, loser), m = eraAverages(years, margin);
  document.getElementById("callout-margin").innerHTML =
    `<b>Margin of victory</b> (winner &minus; loser), era averages: ${eraDeltaText(m, " pts", 1)}<br>` +
    `Winner avg: ${eraDeltaText(w, "", 1)} · Loser avg: ${eraDeltaText(l, "", 1)}`;
}

function drawRateChart(canvasId, tooltipId, calloutId, key, label) {
  const canvas = document.getElementById(canvasId);
  const tooltip = document.getElementById(tooltipId);
  const seasons = fsTrend.seasons;
  const years = fsTrend.season_years;
  const n = seasons.length;
  const data = fsTrend[key];

  const PAD_LEFT = 32, PAD_RIGHT = 10, PAD_TOP = 12, PAD_BOTTOM = 26;
  const PLOT_W = 250, PLOT_H = 150;
  const widthCss = PAD_LEFT + PLOT_W + PAD_RIGHT;
  const heightCss = PAD_TOP + PLOT_H + PAD_BOTTOM;
  const dpr = window.devicePixelRatio || 1;
  canvas.style.width = widthCss + "px";
  canvas.style.height = heightCss + "px";
  canvas.width = widthCss * dpr;
  canvas.height = heightCss * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const dataMin = Math.min(...data), dataMax = Math.max(...data);
  const pad = Math.max((dataMax - dataMin) * 0.18, 0.6);
  const yMin = Math.max(0, dataMin - pad), yMax = dataMax + pad;
  function y(v) { return PAD_TOP + PLOT_H * (1 - (v - yMin) / (yMax - yMin)); }

  const stepX = PLOT_W / (n - 1);
  function x(i) { return PAD_LEFT + stepX * i; }

  function draw() {
    ctx.clearRect(0, 0, widthCss, heightCss);

    const ticks = 4;
    ctx.font = "9px -apple-system, sans-serif";
    for (let t = 0; t <= ticks; t++) {
      const v = yMin + ((yMax - yMin) * t) / ticks, yy = y(v);
      ctx.strokeStyle = "#e7e1d5";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(PAD_LEFT, yy);
      ctx.lineTo(PAD_LEFT + PLOT_W, yy);
      ctx.stroke();
      ctx.fillStyle = "#6b6153";
      ctx.textAlign = "right";
      ctx.fillText(v.toFixed(0) + "%", PAD_LEFT - 6, yy + 3);
    }

    for (let i = 1; i < n; i++) {
      const dashed = isSmallSample(years[i - 1]) || isSmallSample(years[i]);
      ctx.lineWidth = 1.6;
      ctx.strokeStyle = dashed ? SMALL_SAMPLE_COLOR : "#c9c0ad";
      ctx.setLineDash(dashed ? [4, 3] : []);
      ctx.beginPath();
      ctx.moveTo(x(i - 1), y(data[i - 1]));
      ctx.lineTo(x(i), y(data[i]));
      ctx.stroke();
    }
    ctx.setLineDash([]);

    for (let i = 0; i < n; i++) {
      const xx = x(i), yy = y(data[i]);
      const small = isSmallSample(years[i]);
      ctx.beginPath();
      ctx.arc(xx, yy, 3, 0, Math.PI * 2);
      ctx.fillStyle = small ? SMALL_SAMPLE_COLOR : ERA_COLORS[eraOfSeason(years[i])];
      ctx.fill();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    ctx.fillStyle = "#6b6153";
    ctx.font = "8px -apple-system, sans-serif";
    ctx.textAlign = "center";
    for (let i = 0; i < n; i += 2) ctx.fillText(seasons[i], x(i), PAD_TOP + PLOT_H + 12);
  }
  draw();

  canvas.onmousemove = (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    if (mx < PAD_LEFT || mx > PAD_LEFT + PLOT_W || my < PAD_TOP || my > PAD_TOP + PLOT_H) {
      tooltip.style.opacity = 0;
      return;
    }
    let idx = Math.round((mx - PAD_LEFT) / stepX);
    idx = Math.max(0, Math.min(n - 1, idx));
    const smallNote = isSmallSample(years[idx]) ? "<br><i>Small sample — excluded from era average</i>" : "";
    tooltip.innerHTML = `<b>${seasons[idx]}</b> (${ERA_LABELS[eraOfSeason(years[idx])]}): ${data[idx].toFixed(1)}%${smallNote}`;
    tooltip.style.left = x(idx) + "px";
    tooltip.style.top = y(data[idx]) + "px";
    tooltip.style.opacity = 1;
  };
  canvas.onmouseleave = () => { tooltip.style.opacity = 0; };

  const e = eraAverages(years, data);
  document.getElementById(calloutId).innerHTML = `<b>${label}</b>, era averages: ${eraDeltaText(e, "%", 1)}`;
}

// ---- Init ----

async function init() {
  try {
    const res = await fetch(`${FS_BASE}/index.json`);
    if (!res.ok) throw new Error("Failed to load index.json");
    const idx = await res.json();
    fsSeasons = idx.seasons || [];
  } catch (err) {
    console.error(err);
    return;
  }
  if (fsSeasons.length === 0) return;
  fsCurrentSeason = fsSeasons[0].season; // index.json is newest-first
  renderSeasonTabs();
  await loadSeasonData(fsCurrentSeason);
  loadTrend();
}

document.addEventListener("DOMContentLoaded", init);
