// ========================================
// Homepage P4P (pound-for-pound) + per-weight rankings table
// ========================================
// Rank order comes straight from FloWrestling's own rankings pages; record
// is "0-0" for everyone since the season hasn't started -- bonus rate, pin
// rate, and TPAR are each wrestler's real numbers from the most recently
// completed season (see scripts/rankings/build_p4p_rankings.py for why).
// Tabs (P4P / 125 / 133 / ... / 285) swap which already-loaded list
// renders -- one fetch on page load, same convention as the other
// weight-tabbed panels on this page (e.g. TPAR Leaders).

const P4P_SEASON = "2027";
let p4pData = null;

function p4pSafe(v, fmt) {
  if (v === null || v === undefined || v === "") return "—";
  return fmt ? fmt(v) : v;
}

function p4pPct(v) {
  return p4pSafe(v, n => `${(n * 100).toFixed(1)}%`);
}

function p4pNum(v) {
  return p4pSafe(v, n => n.toFixed(1));
}

async function loadP4PRankings() {
  try {
    const res = await fetch(`/data/p4p/${P4P_SEASON}.json`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function p4pListFor(weight) {
  if (!p4pData) return [];
  if (weight === "p4p") return p4pData.p4p || [];
  return (p4pData.weights || {})[weight] || [];
}

function renderP4PTable(weight) {
  const tbody = document.querySelector("#p4p-table tbody");
  if (!tbody) return;

  const list = p4pListFor(weight);
  tbody.innerHTML = list.map(w => {
    const nameCell = w.wrestler_id
      ? `<a href="/wrestler.html?id=${w.wrestler_id}">${w.name}</a>`
      : w.name;
    const teamCell = w.team_slug
      ? `<a class="p4p-team-cell" href="/team.html?team=${w.team_slug}">` +
        `<img class="p4p-team-crest" src="/assets/team_logos/${w.team_slug}.svg" alt="" ` +
        `onerror="if(!this.dataset.fb){this.dataset.fb=1;this.src='/assets/team_logos/${w.team_slug}.png';}else{this.remove();}">` +
        `<span>${w.team}</span></a>`
      : w.team;
    return (
      `<tr>` +
      `<td class="rank-cell"><span class="rank-badge ${w.rank <= 3 ? `medal-${["gold", "silver", "bronze"][w.rank - 1]}` : "standard"}">#${w.rank}</span></td>` +
      `<td class="name">${nameCell}</td>` +
      `<td>${teamCell}</td>` +
      `<td>${w.record}</td>` +
      `<td class="num">${p4pPct(w.bonus_rate)}</td>` +
      `<td class="num">${p4pPct(w.pin_rate)}</td>` +
      `<td class="num">${p4pNum(w.tpar)}</td>` +
      `</tr>`
    );
  }).join("");
}

function setupP4PTabs() {
  document.querySelectorAll("#p4p-weight-tabs .hp-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("#p4p-weight-tabs .hp-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      renderP4PTable(tab.dataset.weight);
    });
  });
}

function renderP4PRankings(data) {
  const section = document.getElementById("p4p-section");
  if (!data || !data.p4p || !data.p4p.length) {
    if (section) section.hidden = true;
    return;
  }

  p4pData = data;
  setupP4PTabs();
  renderP4PTable("p4p");
}

document.addEventListener("DOMContentLoaded", async () => {
  const data = await loadP4PRankings();
  renderP4PRankings(data);
});
