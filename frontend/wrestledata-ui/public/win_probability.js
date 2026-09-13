// Win-probability Lab page: renders precomputed per-event traces (see
// scripts/win_prob/export_matches_for_site.py) as small-multiple SVG charts.
// Scrubbing is via a fixed readout row under each chart, not a floating
// tooltip -- a floating box clips against the card edge near the top/right
// of the chart (found 2026-09-13), and pinning a hover to a ~4px dot is a
// fragile target anyway. Hovering ANYWHERE over the plot scrubs the whole
// timeline instead of requiring a precise hit on a dot.
(function () {
  "use strict";

  const DATA_URL = "/data/win_prob/2026_ncaa_finals.json";
  const PERIOD_LABELS = { "1": "1st", "2": "2nd", "3": "3rd", OT1: "OT", OT2: "TB", OT3: "UTB" };
  // Must match PERIOD_LENGTH_SEC in scripts/win_prob/compute_match_win_prob.py
  const PERIOD_LENGTH_SEC = { "1": 180, "2": 120, "3": 120, OT1: 120, OT2: 30, OT3: 30 };
  const PERIOD_ORDER = ["1", "2", "3", "OT1", "OT2", "OT3"];
  const NEXT_PERIOD = Object.fromEntries(PERIOD_ORDER.slice(0, -1).map((p, i) => [p, PERIOD_ORDER[i + 1]]));

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  // "choice_N" is the boundary moment that STARTS period N+1, not a moment
  // inside period N -- same convention as compute_match_win_prob.py.
  function realPeriod(label) {
    if (String(label).startsWith("choice_")) {
      const base = label.split("_")[1];
      return NEXT_PERIOD[base] || base;
    }
    return label;
  }

  function fmtClock(sec) {
    const mm = Math.floor(sec / 60), ss = String(Math.floor(sec % 60)).padStart(2, "0");
    return `${mm}:${ss}`;
  }

  // Match-elapsed seconds isn't a wrestling clock -- convert to time
  // REMAINING in the current (real) period, the way a scoreboard counts down.
  function periodClock(match, atSec, periodLabel) {
    const period = realPeriod(periodLabel);
    const start = match.period_starts[period] || 0;
    const length = PERIOD_LENGTH_SEC[period] || 120;
    const remaining = Math.max(0, length - (atSec - start));
    return { label: PERIOD_LABELS[period] || period, clock: fmtClock(remaining) };
  }

  // "escape" -> "Escape", "near_fall" -> "Near fall"
  function formatAction(action) {
    const s = action.replace(/_/g, " ");
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  function formatLastEvent(match, event) {
    if (event.action === "match_start") return "Opening whistle";
    if (event.scorer) {
      const pts = event.score_points > 1 ? ` +${event.score_points}` : "";
      return `${formatAction(event.action)}${pts} &mdash; ${event.scorer.split(" ").pop()}`;
    }
    if (event.action === "choice" || event.action === "defer") {
      const actorName = (event.actor_is_subject ? match.subject_name : match.opponent_name).split(" ").pop();
      if (event.action === "defer") return `${actorName} defers choice`;
      const choice = (event.raw_text || "").toLowerCase();
      return `${actorName} takes ${choice || "choice"}`;
    }
    if (event.action === "stalling" || event.action === "caution") return formatAction(event.action) + " call";
    return formatAction(event.action);
  }

  function readoutHTML(match, atSec, winProb, event) {
    const favored = winProb >= 0.5 ? match.subject_name : match.opponent_name;
    const pct = (winProb >= 0.5 ? winProb : 1 - winProb) * 100;
    const { label, clock } = periodClock(match, atSec, event.period);
    return `
      <span class="wp-ro-item"><span class="wp-ro-label">Period</span>${label}, ${clock}</span>
      <span class="wp-ro-item"><span class="wp-ro-label">Score</span>${event.subject_score}&ndash;${event.opponent_score}</span>
      <span class="wp-ro-item"><span class="wp-ro-label">Last event</span>${formatLastEvent(match, event)}</span>
      <span class="wp-ro-item wp-ro-prob"><span class="wp-ro-label">Win prob</span>${favored.split(" ").pop()} ${pct.toFixed(1)}%</span>
    `;
  }

  function renderChart(container, readout, match) {
    const W = 400, H = 220;
    const M = { top: 10, right: 8, bottom: 22, left: 28 };
    const plotW = W - M.left - M.right;
    const plotH = H - M.top - M.bottom;
    const matchEnd = match.match_length_sec;

    const bad = css("--bad") || "#c53030";
    const accent = css("--accent") || "#2b6cb0";
    const border = css("--border") || "#e7e1d5";
    const muted2 = css("--muted-2") || "#8f8574";
    const panel = css("--panel") || "#fff";

    function x(t) { return M.left + (t / matchEnd) * plotW; }
    function y(p) { return M.top + (1 - p) * plotH; }
    function xToT(px) { return Math.max(0, Math.min(matchEnd, ((px - M.left) / plotW) * matchEnd)); }

    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("preserveAspectRatio", "xMinYMin meet");

    function el(tag, attrs) {
      const e = document.createElementNS(svgNS, tag);
      for (const k in attrs) e.setAttribute(k, attrs[k]);
      return e;
    }

    // gridlines
    [0, 0.5, 1].forEach((v) => {
      const yy = y(v);
      svg.appendChild(el("line", { x1: M.left, x2: W - M.right, y1: yy, y2: yy, stroke: v === 0.5 ? muted2 : border, "stroke-width": 1, "stroke-dasharray": v === 0.5 ? "2 3" : "none" }));
      const t = svg.appendChild(el("text", { x: M.left - 6, y: yy + 3, "text-anchor": "end", "font-size": "8.5", fill: muted2 }));
      t.textContent = Math.round(v * 100) + "%";
    });

    // period separators + labels
    // strictly LESS than matchEnd -- a period whose start lands exactly at
    // the match's true end was never actually entered (e.g. a bout decided
    // right at the period-3 buzzer has OT1's nominal start equal to
    // matchEnd; a "<=" here rendered a zero-width "OT" label on every
    // non-OT match, and similarly a phantom "TB"/"UTB" on an OT-decided one).
    const periodEntries = Object.entries(match.period_starts).filter(([, s]) => s < matchEnd).sort((a, b) => a[1] - b[1]);
    periodEntries.forEach(([p, start], i) => {
      if (start > 0) svg.appendChild(el("line", { x1: x(start), x2: x(start), y1: M.top, y2: H - M.bottom, stroke: border, "stroke-width": 1 }));
      const nextStart = i < periodEntries.length - 1 ? periodEntries[i + 1][1] : matchEnd;
      const mid = (start + Math.min(nextStart, matchEnd)) / 2;
      const t = svg.appendChild(el("text", { x: x(mid), y: H - 8, "text-anchor": "middle", "font-size": "8.5", fill: muted2 }));
      t.textContent = PERIOD_LABELS[p] || p;
    });

    const stepped = match.trace.map((p) => ({ t: p.elapsed_sec, p: p.win_prob }));

    // area fill split at 50%
    function areaPath(side) {
      const pts = [];
      for (let i = 0; i < stepped.length; i++) {
        const clamped = side === "good" ? Math.max(stepped[i].p, 0.5) : Math.min(stepped[i].p, 0.5);
        pts.push(`${x(stepped[i].t)},${y(clamped)}`);
      }
      for (let i = stepped.length - 1; i >= 0; i--) pts.push(`${x(stepped[i].t)},${y(0.5)}`);
      return pts.join(" ");
    }
    svg.appendChild(el("polygon", { points: areaPath("good"), fill: accent, opacity: "0.13" }));
    svg.appendChild(el("polygon", { points: areaPath("bad"), fill: bad, opacity: "0.13" }));

    // curve, colored per segment by which side is favored
    for (let i = 0; i < stepped.length - 1; i++) {
      const a = stepped[i], b = stepped[i + 1];
      const color = (a.p + b.p) / 2 >= 0.5 ? accent : bad;
      svg.appendChild(el("line", { x1: x(a.t), y1: y(a.p), x2: x(b.t), y2: y(b.p), stroke: color, "stroke-width": 2, "stroke-linecap": "round" }));
    }

    // event dots (visual markers only -- scrubbing below covers the whole plot)
    const realEvents = match.events.filter((e) => !["match_start", "choice", "defer"].includes(e.action));
    realEvents.forEach((e) => {
      svg.appendChild(el("circle", { cx: x(e.elapsed_sec), cy: y(e.win_prob), r: 3.4, fill: e.win_prob >= 0.5 ? accent : bad, stroke: panel, "stroke-width": 1.3 }));
    });

    const crosshair = el("line", { x1: 0, x2: 0, y1: M.top, y2: H - M.bottom, stroke: muted2, "stroke-width": 1, "stroke-dasharray": "2 2", opacity: "0" });
    svg.appendChild(crosshair);

    // full-plot-area scrub target -- hover ANYWHERE over the chart, not just
    // a tiny dot, and the readout below updates to that moment.
    const scrubArea = el("rect", { x: M.left, y: M.top, width: plotW, height: plotH, fill: "transparent", style: "cursor:crosshair" });
    svg.appendChild(scrubArea);

    // container already holds the .wp-readout div (see renderCard) -- insert
    // the svg before it rather than clearing innerHTML.
    container.insertBefore(svg, container.firstChild);

    function eventAt(t) {
      let last = match.events[0];
      for (const e of match.events) {
        if (e.elapsed_sec > t) break;
        last = e;
      }
      return last;
    }

    function winProbAt(t) {
      // trace is densely resampled (every few seconds) -- linear-interpolate
      // between the two bracketing points for a smooth scrub.
      let lo = stepped[0], hi = stepped[stepped.length - 1];
      for (let i = 0; i < stepped.length - 1; i++) {
        if (stepped[i].t <= t && stepped[i + 1].t >= t) { lo = stepped[i]; hi = stepped[i + 1]; break; }
      }
      if (hi.t === lo.t) return lo.p;
      const frac = (t - lo.t) / (hi.t - lo.t);
      return lo.p + frac * (hi.p - lo.p);
    }

    function setDefault() {
      const last = stepped[stepped.length - 1];
      readout.innerHTML = readoutHTML(match, last.t, last.p, eventAt(last.t));
      crosshair.style.opacity = "0";
    }

    function scrub(clientX) {
      const rect = svg.getBoundingClientRect();
      const px = ((clientX - rect.left) / rect.width) * W;
      const t = xToT(px);
      const winProb = winProbAt(t);
      readout.innerHTML = readoutHTML(match, t, winProb, eventAt(t));
      crosshair.setAttribute("x1", x(t));
      crosshair.setAttribute("x2", x(t));
      crosshair.style.opacity = "1";
    }

    scrubArea.addEventListener("mousemove", (ev) => scrub(ev.clientX));
    scrubArea.addEventListener("mouseleave", setDefault);
    scrubArea.addEventListener("touchmove", (ev) => { scrub(ev.touches[0].clientX); ev.preventDefault(); }, { passive: false });
    scrubArea.addEventListener("touchend", setDefault);

    setDefault();
  }

  function renderCard(match) {
    const card = document.createElement("div");
    card.className = "wp-card";
    card.innerHTML = `
      <div class="wp-head">
        <h2>${match.subject_name} vs ${match.opponent_name}</h2>
        <span class="wp-weight">${match.weight} lbs</span>
      </div>
      <p class="wp-score">Final: <b>${match.subject_name}</b> ${match.final_subject_score}&ndash;${match.final_opponent_score} <b>${match.opponent_name}</b></p>
      <div class="wp-canvas-wrap"></div>
      <div class="wp-readout"></div>
      <div class="wp-legend">
        <span><i style="background:var(--accent)"></i>${match.subject_name.split(" ").pop()} favored</span>
        <span><i style="background:var(--bad)"></i>${match.opponent_name.split(" ").pop()} favored</span>
      </div>
    `;
    const wrap = card.querySelector(".wp-canvas-wrap");
    const readout = card.querySelector(".wp-readout");
    renderChart(wrap, readout, match);
    return card;
  }

  async function init() {
    const grid = document.getElementById("wp-grid");
    const intro = document.getElementById("wp-intro");
    const method = document.getElementById("wp-method");
    try {
      const res = await fetch(DATA_URL);
      const data = await res.json();
      intro.innerHTML = `<b>${data.matches.length} matches.</b> Each chart tracks the eventual champion's win probability (blue = favored, red = trailing) from the opening whistle to the final horn. Hover or drag across a chart to scrub through the match -- the readout below reacts to the clock and riding time continuously, not just to points scored.`;
      data.matches.forEach((m) => grid.appendChild(renderCard(m)));
      method.innerHTML = `<b>Model:</b> logistic regression trained on 121k+ event-states from every 2024&ndash;2026 NCAA D1 tournament (nationals + every conference). Features: score differential &times; how much of the whole match is left (not just the current period &mdash; a lead compounds sharply in the closing seconds), both wrestlers' season DPG, position, stalling warnings, riding-time net advantage, and coin-flip choice. Win probability is a state read, not a forecast of what happens next &mdash; it updates continuously as the clock and riding time move, plus a jump at every scored point.`;
    } catch (err) {
      intro.textContent = "Couldn't load win-probability data.";
      console.error(err);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
