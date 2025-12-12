// ===============================
// Helpers
// ===============================

function safe(value, formatter) {
    if (value === null || value === undefined || value === "") return "—";
    return formatter ? formatter(value) : value;
  }
  
  function percentFormatter(v) {
    return (v * 100).toFixed(1) + "%";
  }
  
  function resolveSeason() {
    return "2026"; // Or make dynamic later
  }
  
  // ===============================
  // Fetch Wrestler JSON
  // ===============================
  
  function loadWrestlerProfile(id) {
    const url = `/wrestlers/2026/by_id/${id}.json`;
  
    fetch(url)
      .then(res => {
        if (!res.ok) throw new Error("Could not load wrestler JSON");
        return res.json();
      })
      .then(data => renderWrestlerProfile(data))
      .catch(err => {
        console.error("Error loading:", err);
        document.getElementById("wrestler-name").textContent = "Not Found";
        document.getElementById("wrestler-meta").textContent = err.message;
      });
  }
  
  // ===============================
  // Rendering
  // ===============================
  
  function renderWrestlerProfile(data) {
    document.getElementById("wrestler-name").textContent = safe(data.name);
    document.getElementById("wrestler-tagline").textContent =
      `#${safe(data.current_rank)} at ${safe(data.weight_class)} lbs`;
  
    document.getElementById("wrestler-meta").textContent =
      `${safe(data.team)} · Season ${safe(data.year)}`;
  
    // Record
    const r = data.record || {};
    document.getElementById("record-overall").textContent = safe(r.overall);
    document.getElementById("record-ranked").textContent = safe(r.vs_ranked);
    document.getElementById("record-top10").textContent = safe(r.vs_top10);
    document.getElementById("record-top25").textContent = safe(r.vs_top25);
  
    // Metrics summary cards
    const m = data.metrics || {};
    document.getElementById("metric-bonus-rate").textContent = safe(m.bonus_rate, percentFormatter);
    document.getElementById("metric-pin-rate").textContent = safe(m.pin_rate, percentFormatter);
    document.getElementById("metric-majors").textContent = safe(m.majors);
    document.getElementById("metric-techs").textContent = safe(m.techs);
    document.getElementById("metric-pins").textContent = safe(m.pins);
  
    document.getElementById("metric-pf7").textContent = safe(m.pf7);
    document.getElementById("metric-pa7").textContent = safe(m.pa7);
    document.getElementById("metric-pd7").textContent = safe(m.pd7);
    document.getElementById("metric-si-plus").textContent = safe(m.si_plus);
    document.getElementById("metric-df-plus").textContent = safe(m.df_plus);
    document.getElementById("metric-apr-plus").textContent = safe(m.apr_plus);
  
    renderImpactSummary(data.opponent_breakdown || {});
    renderMatchTable(data.match_list || []);
  }
  
  function renderImpactSummary(ob) {
    const el = document.getElementById("impact-summary");
    const lines = [];
  
    if (ob.win_over_highest_rank) {
      const w = ob.win_over_highest_rank;
      lines.push(
        `Best Win: #${safe(w.opponent_rank)} ${safe(w.opponent_name)} (${safe(w.method)})`
      );
    }
  
    if (ob.worst_loss) {
      const l = ob.worst_loss;
      lines.push(
        `Worst Loss: #${safe(l.opponent_rank)} ${safe(l.opponent_name)} (${safe(l.method)})`
      );
    }
  
    el.innerHTML = lines.map((l) => `<div>${l}</div>`).join("");
  }
  
  function renderMatchTable(matches) {
    const tbody = document.querySelector("#match-table tbody");
    tbody.innerHTML = "";
  
    matches.sort((a, b) => (b.date || "").localeCompare(a.date || ""));
  
    matches.forEach((match) => {
      const tr = document.createElement("tr");
  
      const add = (v) => {
        const td = document.createElement("td");
        td.textContent = safe(v);
        tr.appendChild(td);
      };
  
      add(match.date);
  
      // Opponent with link
      const oppTd = document.createElement("td");
      if (match.opponent_id) {
        const a = document.createElement("a");
        a.href = `/wrestler.html?id=${match.opponent_id}`;
        a.textContent = safe(match.opponent_name);
        oppTd.appendChild(a);
      } else {
        oppTd.textContent = safe(match.opponent_name);
      }
      tr.appendChild(oppTd);
  
      add(match.opponent_team);
      add(match.opponent_team_rank ? "#" + match.opponent_team_rank : "—");
      add(match.opponent_weight);
      add(match.opponent_rank ? "#" + match.opponent_rank : "—");
      add(match.result);
      add(match.method);
      add(match.score);
      add(match.duration);
      add(match.event);
  
      tbody.appendChild(tr);
    });
  }