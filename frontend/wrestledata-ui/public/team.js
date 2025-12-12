function getQueryParam(key) {
    const params = new URLSearchParams(window.location.search);
    return params.get(key);
  }
  
  // Pretty URL: /team/virginia_tech
  function getPrettyRouteTeam() {
    const parts = window.location.pathname.split("/").filter(Boolean);
    if (parts.length === 2 && parts[0] === "team") return parts[1];
    return null;
  }
  
  function loadTeam(teamSlug) {
    const url = `/teams/${teamSlug}.json`;
  
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`Team JSON not found: ${url}`);
        return res.json();
      })
      .then((data) => renderTeamPage(data))
      .catch((err) => {
        document.getElementById("team-name").textContent = "Team Not Found";
        document.getElementById("team-meta").textContent = err.message;
      });
  }
  
  function safe(v, fn) {
    if (v === null || v === undefined || v === "") return "—";
    return fn ? fn(v) : v;
  }
  
  function percent(v) {
    return (v * 100).toFixed(1) + "%";
  }
  
  function renderTeamPage(data) {
    document.getElementById("team-name").textContent = safe(data.team_name);
    document.getElementById("team-meta").textContent = 
      `#${safe(data.team_rank)} · ${safe(data.conference)} · ${safe(data.dual_record)} record`;
  
    const tm = data.team_metrics || {};
  
    document.getElementById("tm-pf7").textContent = safe(tm.avg_pf7);
    document.getElementById("tm-pa7").textContent = safe(tm.avg_pa7);
    document.getElementById("tm-pd7").textContent = safe(tm.avg_pd7);
    document.getElementById("tm-bonus").textContent = safe(tm.bonus_rate, percent);
    document.getElementById("tm-pin").textContent = safe(tm.pin_rate, percent);
    document.getElementById("tm-tech").textContent = safe(tm.tech_rate, percent);
    document.getElementById("tm-ranked-pct").textContent = safe(tm.ranked_win_pct, percent);
  
    // Highlights block
    const h = data.team_highlights || {};
    const highlightsDiv = document.getElementById("team-highlights");
    highlightsDiv.innerHTML = `
      <div><strong>Best Win:</strong> ${safe(h.best_win)}</div>
      <div><strong>Best Upset:</strong> ${safe(h.best_upset)}</div>
      <div><strong>Most Dominant Weight:</strong> ${safe(h.most_dominant_weight)}</div>
      <div><strong>Weakest Weight:</strong> ${safe(h.weakest_weight)}</div>
    `;
  
    renderRosterTable(data.roster || []);
  }
  
  function renderRosterTable(roster) {
    const tbody = document.querySelector("#roster-table tbody");
    tbody.innerHTML = "";
  
    roster.sort((a, b) => a.weight_class - b.weight_class);
  
    roster.forEach((w) => {
      const tr = document.createElement("tr");
  
      const add = (v) => {
        const td = document.createElement("td");
        td.textContent = safe(v);
        tr.appendChild(td);
      };
  
      add(w.weight_class);
  
      // Name with link
      const nameTd = document.createElement("td");
      const a = document.createElement("a");
      //a.href = `/wrestler/${w.wrestler_id}`;
      a.href = `/wrestler.html?id=${w.wrestler_id}`;
      a.textContent = w.name;
      nameTd.appendChild(a);
      tr.appendChild(nameTd);
  
      add(w.current_rank ? `#${w.current_rank}` : "—");
      add(w.record);
      add(w.vs_ranked);
      add(w.pd7);
      add(percent(w.bonus_rate));
      add(w.best_win);
      add(w.worst_loss);
  
      tbody.appendChild(tr);
    });
  }
  
  // Initialize
  document.addEventListener("DOMContentLoaded", () => {
    const pretty = getPrettyRouteTeam();
    const q = getQueryParam("team");
  
    const teamSlug = pretty || q;
  
    if (!teamSlug) {
      document.getElementById("team-name").textContent = "No team selected.";
      return;
    }
  
    loadTeam(teamSlug);
  });