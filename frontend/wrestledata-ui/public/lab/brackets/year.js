// NCAA Bracket Archive, one tournament year: weight tabs (bracket, bad-point table or placewinners only)
// plus a Team Scores tab. Data: data/{year}.json from scripts/brackets/build_ncaa_bracket_archive.py.
// URL state: ?y=1979&w=150 (w=team for the Team Scores tab). Every round is always shown (TJ, 2026-10-01: no
// rounds navigator); on narrow screens the bracket scrolls sideways inside its own box.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const params = new URLSearchParams(location.search);
  // the engine still builds its navigator strip; give it a detached element so nothing shows
  const view = BracketEngine.mount({ bracketEl: $("bracket"), navEl: document.createElement("div") });
  const PLACE = ["", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th"];
  let doc = null, current = null, year = null;

  function syncURL() {
    const p = new URLSearchParams({ y: year, w: current });
    history.replaceState(null, "", "?" + p.toString());
  }

  function fmtDates(d) {
    const ds = (Array.isArray(d) ? d : [d]).filter(Boolean).map((x) => new Date(x + "T12:00:00"));
    if (!ds.length || ds.some(isNaN)) return Array.isArray(d) ? d.join(" – ") : String(d);
    const md = (x) => x.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    const a = ds[0], b = ds[ds.length - 1];
    if (a.getTime() === b.getTime()) return `${md(a)}, ${a.getFullYear()}`;
    return a.getMonth() === b.getMonth() ? `${md(a)}–${b.getDate()}, ${b.getFullYear()}` : `${md(a)} – ${md(b)}, ${b.getFullYear()}`;
  }

  function header(idx) {
    const ev = doc.event;
    $("title").textContent = ev.name;
    document.title = `${ev.year} NCAA Wrestling Championships (Lab) — MatSavant`;
    const facts = [];
    if (ev.host) facts.push(`<span>Host <b>${esc(ev.host)}</b></span>`);
    if (ev.dates) facts.push(`<span><b>${esc(fmtDates(ev.dates))}</b></span>`);
    if (ev.team_champion) facts.push(`<span>${esc(ev.team_champion_label || "Team champion")} <b>${esc(ev.team_champion)}</b></span>`);
    if (ev.outstanding_wrestler) facts.push(`<span>Outstanding Wrestler <b>${esc(ev.outstanding_wrestler)}</b></span>`);
    if (ev.gorriaran_award) facts.push(`<span>Gorriaran Award <b>${esc(ev.gorriaran_award)}</b></span>`);
    facts.push(`<span>Format <b>${esc(ev.model_label)}</b></span>`);
    facts.push(`<span>Source <b>${esc(ev.source)}</b></span>`);
    $("facts").innerHTML = facts.join("");
    $("notes").innerHTML = (doc.notes || []).map((n) => `<li>${esc(n)}</li>`).join("");
    const ys = idx.years.map((y) => y.year), i = ys.indexOf(ev.year);
    const link = (y, lbl) => y ? `<a href="?y=${y}">${lbl}</a>` : `<span>${lbl}</span>`;
    $("yearnav").innerHTML = link(ys[i - 1], `‹ ${ys[i - 1] || ""}`) + link(ys[i + 1], `${ys[i + 1] || ""} ›`);
  }

  function tabs() {
    const t = doc.weights.map((w) =>
      `<button role="tab" type="button" data-id="${esc(w.id)}" aria-selected="false">${esc(w.label)}</button>`);
    t.push(`<button role="tab" type="button" class="tab-team" data-id="team" aria-selected="false">Team Scores</button>`);
    $("tabs").innerHTML = t.join("");
  }

  // ---------- one weight ----------
  function placesHTML(w) {
    if (!w.placements || !w.placements.length) return "";
    return `<div class="bk-places"><h3>Placewinners</h3>` + w.placements.map((p) =>
      `<div class="bk-place" data-pk="${esc(p.k == null ? "" : "k:" + p.k)}"><span class="bk-place-n">${PLACE[p.place] || p.place}</span>` +
      `<span class="bk-place-w">${esc(p.n)}${p.s ? ` <span class="bk-place-t">(${esc(p.s)})</span>` : ""} ` +
      `<span class="bk-place-t">${esc(p.t)}</span></span></div>`).join("") + `</div>`;
  }
  function badPointsHTML(w) {
    let h = `<p class="bk-ts-note">No bracket this year: wrestlers were paired round by round and collected bad points for each bout, ` +
      `and a wrestler was out once his total reached the limit. Bad points are shown as printed on the sheet.</p>`;
    for (const r of w.rounds) {
      h += `<div class="bk-bp-round"><h3>${esc(r.label)}</h3><div class="bk-table-wrap"><table class="bk-table"><thead><tr>` +
        `<th>Winner</th><th>Loser</th><th>Result</th><th class="num">Bad pts (W–L)</th></tr></thead><tbody>` +
        r.bouts.map((b) => `<tr><td class="bk-bp-w">${esc(b.w.n)} <span class="bk-place-t">${esc(b.w.t)}</span></td>` +
          `<td>${esc(b.l.n)} <span class="bk-place-t">${esc(b.l.t)}</span></td><td>${esc(b.res)}</td>` +
          `<td class="num">${b.wbp ?? ""}–${b.lbp ?? ""}${b.wbt != null ? ` <span class="bk-place-t">(tot ${b.wbt}–${b.lbt})</span>` : ""}</td></tr>`).join("") +
        `</tbody></table></div></div>`;
    }
    return h;
  }

  function selectTab(id) {
    current = id;
    document.querySelectorAll("#tabs [role=tab]").forEach((t) => {
      const on = t.dataset.id === id;
      t.setAttribute("aria-selected", on);
      t.tabIndex = on ? 0 : -1;
    });
    const isTeam = id === "team";
    $("panel-team").hidden = !isTeam;
    $("panel-weight").hidden = isTeam;
    if (isTeam) { renderTeam(); syncURL(); return; }
    const w = doc.weights.find((x) => x.id === id);
    $("places").innerHTML = placesHTML(w);
    $("wnotes").innerHTML = [...(w.notes || []), ...(w.discrepancies || []).map((d) => typeof d === "string" ? d : d.note || d.detail || JSON.stringify(d))]
      .map((n) => `<li>${esc(n)}</li>`).join("");
    const isBracket = w.kind === "bracket";
    $("bracket-wrap").hidden = !isBracket;
    $("other").innerHTML = w.kind === "badpoints" ? badPointsHTML(w)
      : w.kind === "summary" ? `<p class="bk-ts-note">Only the placewinners survive for this year; the source has no bouts.</p>` : "";
    if (isBracket) {
      view.load({ sections: w.sections, columns: w.columns }, { matches: w.matches });
      view.setWindow(0, w.columns.length, true);   // all rounds
      view.rerender();
    }
    syncURL();
  }

  // ---------- team scores ----------
  let showAll = false;
  function renderTeam() {
    const ts = doc.team_scores;
    if (!ts.rows.length) {
      $("panel-team").innerHTML = `<p class="bk-ts-note">${esc(ts.note || "No team scores for this year.")}</p>`;
      return;
    }
    const kindNote = ts.kind === "printed"
      ? (ts.official === false ? "Unofficial team scores as printed on the summary page." : "Team scores as printed on the official summary.")
      : "";
    const rows = ts.rows;
    const limit = showAll ? rows.length : Math.max(10, rows.filter((r) => !r.calc && r.rank <= 10).length);
    const hasChamps = rows.some((r) => r.champions);
    let body = "";
    rows.slice(0, limit).forEach((r, i) => {
      const prev = rows[i - 1];
      const flag = r.flag ? ` <span class="bk-flag" title="${esc(r.flag)}">⚑</span>`
        : r.calc_points != null ? ` <span class="bk-flag" title="${esc(`Printed ${r.points}; the bouts add up to ${r.calc_points}.`)}">⚑</span>` : "";
      body += `<tr class="${r.calc ? "calc" : ""}${r.calc && prev && !prev.calc ? " sep" : ""}">` +
        `<td class="num">${r.tied ? "T-" : ""}${r.rank}</td><td>${esc(r.team)}${flag}</td>` +
        `<td class="num">${r.points}</td>${hasChamps ? `<td class="num">${r.champions || ""}</td>` : ""}</tr>`;
    });
    $("panel-team").innerHTML =
      `<p class="bk-ts-note">${esc(ts.note || kindNote)}</p>` +
      `<div class="bk-table-wrap"><table class="bk-table"><thead><tr><th class="num">#</th><th>Team</th>` +
      `<th class="num">Points</th>${hasChamps ? `<th class="num">Champs</th>` : ""}</tr></thead><tbody>${body}</tbody></table></div>` +
      (rows.length > limit || showAll ? `<button type="button" class="bk-more" id="ts-more">${showAll ? "Show top 10" : `Show all ${rows.length} teams`}</button>` : "") +
      (rows.some((r) => r.flag || r.calc_points != null) ? `<p class="bk-ts-note">⚑ = the printed summary and the bouts disagree; hover or tap the flag for details.</p>` : "");
    const more = $("ts-more");
    if (more) more.addEventListener("click", () => { showAll = !showAll; renderTeam(); });
  }
  $("panel-team").addEventListener("click", (e) => {
    const f = e.target.closest(".bk-flag");
    if (f) toggleFlagNote(f);
  });
  function toggleFlagNote(f) {   // tap shows the flag text inline (no hover on phones)
    const next = f.nextElementSibling;
    if (next && next.classList.contains("bk-flag-text")) { next.remove(); return; }
    f.insertAdjacentHTML("afterend", `<div class="bk-flag-text bk-ts-note">${esc(f.title)}</div>`);
  }

  // placewinner strip highlights that wrestler's path
  $("places").addEventListener("click", (e) => {
    const p = e.target.closest(".bk-place");
    if (!p || !p.dataset.pk) return;
    const row = document.querySelector(`#bracket .brk-row[data-wk="${CSS.escape(p.dataset.pk)}"]`);
    if (row) row.click();
  });

  $("tabs").addEventListener("click", (e) => {
    const t = e.target.closest("[role=tab]");
    if (t) selectTab(t.dataset.id);
  });
  $("tabs").addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const ids = [...doc.weights.map((w) => w.id), "team"];
    const i = ids.indexOf(current) + (e.key === "ArrowRight" ? 1 : -1);
    if (i >= 0 && i < ids.length) { selectTab(ids[i]); document.querySelector(`#tabs [data-id="${ids[i]}"]`).focus(); }
  });

  fetch("data/index.json").then((r) => r.json()).then(async (idx) => {
    const ys = idx.years.map((y) => y.year);
    year = +params.get("y");
    if (!ys.includes(year)) year = ys[ys.length - 1];
    doc = await fetch(`data/${year}.json`).then((r) => r.json());
    header(idx);
    tabs();
    const want = params.get("w");
    selectTab(want === "team" || doc.weights.some((w) => w.id === want) ? want : doc.weights[0].id);
  }).catch((err) => {
    $("title").textContent = "Couldn't load this year";
    console.error(err);
  });
})();
