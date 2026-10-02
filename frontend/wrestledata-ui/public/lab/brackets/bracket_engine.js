// Bracket viewer engine. Format-agnostic: renders the schema documented in
// scripts/brackets/build_ncaa_bracket_archive.py (copied from labs/bracket_viewer/ and extended:
// wrestler keys come from `k` when present, a match may have no recorded winner (w: null)).
// No dependencies, no build step.
//
//   const v = BracketEngine.mount({ bracketEl, navEl });
//   v.load(eventDoc, bracket);        // eventDoc = {sections, columns, ...}, bracket = {matches}
//   v.setWindow(start, count);        // which shared columns are visible
//   v.onWindowChange = (start, count) => {...};
//
// Navigator: a strip with one cell per column and a draggable window. Drag the body to
// slide, drag either edge to widen/narrow, click a cell to center on it, arrows/+/- via keys.
// Re-render is a string rebuild of ~64 absolutely-positioned boxes, i.e. effectively instant.
(function (global) {
  "use strict";

  const ROW_H = 24;            // one wrestler row
  const FOOT_H = 16;           // result line
  const BOX_H = ROW_H * 2 + FOOT_H;
  const GAP_Y = 14;            // min vertical gap between boxes in a column
  const HEAD_H = 30;           // section heading
  const MAX_BOX_W = 330;
  const MIN_BOX_W = 150;
  const MAX_STEP_EXTRA = 110;  // extra connector room beyond the box when there's spare width

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function mount({ bracketEl, navEl }) {
    const st = {
      ev: null, matches: [], byId: new Map(), keyOf: new Map(),
      start: 0, count: 3, nCols: 0, pinned: null,
    };
    const api = { onWindowChange: null };

    // ---------- data ----------
    api.load = function (ev, bracket) {
      st.ev = ev;
      st.matches = bracket.matches;
      st.byId = new Map(st.matches.map((m) => [m.id, m]));
      st.nCols = ev.columns.length;
      st.pinned = null;
      st.keyOf = new Map();
      st.start = Math.min(st.start, Math.max(0, st.nCols - st.count));
      buildNav();
      render();
    };

    api.setWindow = function (start, count, silent) {
      count = Math.max(1, Math.min(st.nCols, count));
      start = Math.max(0, Math.min(st.nCols - count, start));
      if (start === st.start && count === st.count && !silent) return;
      st.start = start; st.count = count;
      positionWindow();
      render();
      if (api.onWindowChange && !silent) api.onWindowChange(start, count);
    };
    api.getWindow = () => ({ start: st.start, count: st.count });
    api.rerender = () => render();

    // ---------- navigator ----------
    let navWin = null, navCells = null;

    function buildNav() {
      const cols = st.ev.columns;
      const secs = st.ev.sections;
      navEl.innerHTML =
        `<div class="nav-track" tabindex="0" role="group" aria-label="Rounds shown. Arrow keys move, plus and minus resize.">` +
        cols.map((c, i) => `<button type="button" class="nav-cell" data-i="${i}" tabindex="-1">` +
          secs.map((s) => `<span class="nav-lbl nav-${esc(s.id)}${c[s.id] ? "" : " nav-none"}">${esc(c[s.id] || "—")}</span>`).join("") +
          `</button>`).join("") +
        `<div class="nav-win" role="presentation"><span class="nav-h nav-h-l"></span><span class="nav-h nav-h-r"></span></div></div>` +
        `<div class="nav-btns"><button type="button" data-a="less" title="Show fewer rounds" aria-label="Show fewer rounds">−</button>` +
        `<button type="button" data-a="more" title="Show more rounds" aria-label="Show more rounds">+</button>` +
        `<button type="button" data-a="all">All</button></div>`;
      const track = navEl.querySelector(".nav-track");
      navWin = navEl.querySelector(".nav-win");
      navCells = track;
      positionWindow();

      const cellW = () => track.clientWidth / st.nCols;
      let drag = null;

      track.addEventListener("pointerdown", (e) => {
        const onL = e.target.classList.contains("nav-h-l");
        const onR = e.target.classList.contains("nav-h-r");
        const inWin = e.target.closest(".nav-win");
        if (!inWin) return;
        drag = { mode: onL ? "l" : onR ? "r" : "move", x0: e.clientX, s0: st.start, c0: st.count };
        track.setPointerCapture(e.pointerId);
        navWin.classList.add("dragging");
        e.preventDefault();
      });
      track.addEventListener("pointermove", (e) => {
        if (!drag) return;
        const d = Math.round((e.clientX - drag.x0) / cellW());
        if (drag.mode === "move") {
          api.setWindow(drag.s0 + d, drag.c0);
        } else if (drag.mode === "l") {
          const end = drag.s0 + drag.c0;
          const ns = Math.max(0, Math.min(end - 1, drag.s0 + d));
          api.setWindow(ns, end - ns);
        } else {
          api.setWindow(drag.s0, Math.max(1, drag.c0 + d));
        }
      });
      const endDrag = () => { drag = null; navWin.classList.remove("dragging"); };
      track.addEventListener("pointerup", endDrag);
      track.addEventListener("pointercancel", endDrag);

      track.addEventListener("click", (e) => {
        const cell = e.target.closest(".nav-cell");
        if (!cell || e.target.closest(".nav-win")) return;
        const i = +cell.dataset.i;
        api.setWindow(Math.round(i - (st.count - 1) / 2), st.count);
      });
      track.addEventListener("keydown", (e) => {
        if (e.key === "ArrowLeft") { api.setWindow(st.start - 1, st.count); e.preventDefault(); }
        else if (e.key === "ArrowRight") { api.setWindow(st.start + 1, st.count); e.preventDefault(); }
        else if (e.key === "+" || e.key === "=") { api.setWindow(st.start, st.count + 1); e.preventDefault(); }
        else if (e.key === "-" || e.key === "_") { api.setWindow(st.start, st.count - 1); e.preventDefault(); }
      });
      navEl.querySelector(".nav-btns").addEventListener("click", (e) => {
        const a = e.target.closest("button")?.dataset.a;
        if (a === "less") api.setWindow(st.start, st.count - 1);
        else if (a === "more") api.setWindow(st.start, st.count + 1);
        else if (a === "all") api.setWindow(0, st.nCols);
      });
    }

    function positionWindow() {
      if (!navWin) return;
      const pct = 100 / st.nCols;
      navWin.style.left = `${st.start * pct}%`;
      navWin.style.width = `${st.count * pct}%`;
      navEl.querySelectorAll(".nav-cell").forEach((c, i) =>
        c.classList.toggle("in", i >= st.start && i < st.start + st.count));
    }

    // ---------- rendering ----------
    function keyFor(w) {
      const k = w.k != null ? "k:" + w.k : w.n + "|" + w.t;
      let id = st.keyOf.get(k);
      if (id == null) { id = st.keyOf.size + 1; st.keyOf.set(k, id); }
      return id;
    }

    function rowHTML(w, isWinner, top, isDrop) {
      const k = keyFor(w);
      return `<div class="brk-row${isWinner ? " win" : ""}${isDrop ? " drop" : ""}" data-k="${k}" data-wk="${esc(w.k != null ? "k:" + w.k : "")}" style="top:${top}px" ` +
        (isDrop ? `title="Dropped in from the championship bracket"` : "") + `>` +
        `<span class="brk-seed">${w.s != null ? esc(w.s) : ""}</span>` +
        `<span class="brk-name">${esc(w.n)}</span>` +
        `<span class="brk-team">${esc(w.t)}</span></div>`;
    }

    function render() {
      if (!st.ev) return;
      const W = Math.max(280, bracketEl.clientWidth);
      const c0 = st.start, c1 = st.start + st.count - 1;
      const n = st.count;
      const boxW = Math.max(MIN_BOX_W, Math.min(MAX_BOX_W, (W - (n - 1) * 26) / n));
      let step = n > 1 ? Math.max(boxW + 26, Math.min((W - boxW) / (n - 1), boxW + MAX_STEP_EXTRA)) : 0;
      const totalW = boxW + (n - 1) * step;
      const left0 = Math.max(0, (W - totalW) / 2);
      const planeW = Math.max(W, totalW);
      const xOf = (c) => left0 + (c - c0) * step;

      let html = "";
      for (const sec of st.ev.sections) {
        const vis = st.matches.filter((m) => m.s === sec.id && m.c >= c0 && m.c <= c1);
        if (!vis.length) continue;

        // vertical scale: tightest visible column decides px per unit
        const cols = new Map();
        vis.forEach((m) => { (cols.get(m.c) || cols.set(m.c, []).get(m.c)).push(m.y); });
        let unit = BOX_H + GAP_Y;
        cols.forEach((ys) => {
          ys.sort((a, b) => a - b);
          let d = Infinity;
          for (let i = 1; i < ys.length; i++) d = Math.min(d, ys[i] - ys[i - 1]);
          if (d < Infinity && d > 0) unit = Math.max(unit, (BOX_H + GAP_Y) / d);
        });
        const ymin = Math.min(...vis.map((m) => m.y));
        const ymax = Math.max(...vis.map((m) => m.y));
        const topOf = (m) => (m.y - ymin) * unit;
        const height = (ymax - ymin) * unit + BOX_H;
        const shown = new Set(vis.map((m) => m.id));

        // column headers
        let heads = "";
        for (let c = c0; c <= c1; c++) {
          const lbl = st.ev.columns[c] && st.ev.columns[c][sec.id];
          if (lbl && cols.has(c)) heads += `<div class="brk-colhead" style="left:${xOf(c)}px;width:${boxW}px">${esc(lbl)}</div>`;
        }

        // connectors (same section, adjacent visible columns only)
        let edges = "";
        for (const m of vis) {
          ["a", "b"].forEach((side, si) => {
            const f = m[side].f;
            if (!f) return;
            const src = st.byId.get(f[0]);
            if (!src || src.s !== sec.id || !shown.has(src.id) || src.c !== m.c - 1) return;
            const x1 = xOf(src.c) + boxW, y1 = topOf(src) + ROW_H;
            const x2 = xOf(m.c), y2 = topOf(m) + (si === 0 ? ROW_H / 2 : ROW_H + ROW_H / 2);
            const xm = (x1 + x2) / 2;
            const w = !src.w ? m[side] : f[1] === "W" ? src[src.w] : src[src.w === "a" ? "b" : "a"];
            edges += `<path class="brk-edge${f[1] === "L" ? " loser" : ""}" data-k="${keyFor(w)}" ` +
              `d="M${x1} ${y1}H${xm}V${y2}H${x2}"/>`;
          });
        }

        let boxes = "";
        for (const m of vis) {
          const t = topOf(m);
          const dropA = m.a.f && st.byId.get(m.a.f[0]) && st.byId.get(m.a.f[0]).s !== m.s;
          const dropB = m.b.f && st.byId.get(m.b.f[0]) && st.byId.get(m.b.f[0]).s !== m.s;
          boxes += `<div class="brk-match" style="left:${xOf(m.c)}px;top:${t}px;width:${boxW}px" data-id="${esc(m.id)}">` +
            (m.lbl ? `<div class="brk-lbl">${esc(m.lbl)}</div>` : "") +
            rowHTML(m.a, m.w === "a", 0, dropA) +
            rowHTML(m.b, m.w === "b", ROW_H, dropB) +
            `<div class="brk-res">${esc(m.res || (m.w ? "" : "result not recorded"))}</div></div>`;
        }

        html += `<section class="brk-section"><h3>${esc(sec.label)}</h3>` +
          `<div class="brk-stage" style="height:${height + HEAD_H}px;width:${planeW}px">` +
          heads +
          `<div class="brk-plane" style="top:${HEAD_H}px;height:${height}px;width:${planeW}px">` +
          `<svg class="brk-edges" width="${planeW}" height="${height}">${edges}</svg>${boxes}</div></div></section>`;
      }
      bracketEl.innerHTML = html || `<p class="brk-empty">No matches in these rounds.</p>`;
      applyHighlight(st.pinned);
    }

    // ---------- highlight (hover / tap to pin) ----------
    let hl = null;
    function applyHighlight(k) {
      hl = k;
      bracketEl.classList.toggle("has-hl", k != null);
      bracketEl.querySelectorAll(".hl").forEach((el) => el.classList.remove("hl"));
      if (k != null) bracketEl.querySelectorAll(`[data-k="${k}"]`).forEach((el) => el.classList.add("hl"));
    }
    bracketEl.addEventListener("mouseover", (e) => {
      const r = e.target.closest(".brk-row");
      if (r && r.dataset.k !== String(hl)) applyHighlight(r.dataset.k);
    });
    bracketEl.addEventListener("mouseout", (e) => {
      if (!e.target.closest(".brk-row")) return;
      const to = e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest(".brk-row");
      if (!to) applyHighlight(st.pinned);
    });
    bracketEl.addEventListener("click", (e) => {
      const r = e.target.closest(".brk-row");
      if (!r) { st.pinned = null; applyHighlight(null); return; }
      st.pinned = st.pinned === r.dataset.k ? null : r.dataset.k;
      applyHighlight(st.pinned);
    });

    let raf = 0;
    new ResizeObserver(() => { cancelAnimationFrame(raf); raf = requestAnimationFrame(render); }).observe(bracketEl);
    return api;
  }

  global.BracketEngine = { mount };
})(window);
