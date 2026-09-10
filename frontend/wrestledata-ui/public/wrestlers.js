// Wrestlers directory landing page: search + weight-pill Spotlight, styled
// to match the Teams page's tile grid (color strip, photo, name, team).
// Ranking is editorial rank (p4p.json's per-weight "rank" field), not DPG.

(function () {
  "use strict";

  const P4P_SEASON = "2027";
  const WEIGHTS = [125, 133, 141, 149, 157, 165, 174, 184, 197, 285];

  let weightsData = null; // { "125": [...], ... } each sorted by rank asc
  let teamColors = {}; // team_slug -> hex
  let currentPill = "all"; // "all", "top1", or a weight string

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // ---------- Search ----------

  function initDirectorySearch() {
    const input = document.getElementById("directory-search-input");
    const dropdown = document.getElementById("directory-search-dropdown");
    if (!input || !dropdown) return;
    if (typeof Fuse === "undefined" || !window.SEARCH_INDEX) return;

    const fuse = new Fuse(window.SEARCH_INDEX.filter(r => r.type === "wrestler"), {
      keys: [
        { name: "name", weight: 0.6 },
        { name: "searchTokens", weight: 0.4 },
      ],
      threshold: 0.4,
      ignoreLocation: true,
      minMatchCharLength: 2,
    });

    input.addEventListener("input", () => {
      const query = input.value.trim();
      if (query.length < 2) {
        dropdown.style.display = "none";
        return;
      }
      const results = fuse.search(query).slice(0, 10).map(r => r.item);
      if (results.length === 0) {
        dropdown.innerHTML = '<div class="search-result-item search-result-empty">No results found</div>';
        dropdown.style.display = "block";
        return;
      }
      dropdown.innerHTML = results
        .map(
          item => `
        <div class="search-result" data-url="${item.url}">
          <div class="search-name">${escapeHtml(item.name)}</div>
          <div class="search-secondary">${escapeHtml(item.secondary || "")}</div>
        </div>`
        )
        .join("");
      dropdown.style.display = "block";
      dropdown.querySelectorAll(".search-result").forEach(el => {
        el.addEventListener("click", () => {
          const url = el.getAttribute("data-url");
          if (url) window.location.href = url;
        });
      });
    });

    document.addEventListener("click", e => {
      if (!e.target.closest(".directory-hero")) dropdown.style.display = "none";
    });

    input.focus();
  }

  // ---------- Weight pills ----------

  function renderPills() {
    const container = document.getElementById("weight-pills");
    if (!container) return;
    const items = [
      { key: "all", label: "All" },
      { key: "top1", label: "#1's" },
      ...WEIGHTS.map(w => ({ key: String(w), label: String(w) })),
    ];
    container.innerHTML = items
      .map(it => `<button type="button" class="weight-pill${it.key === currentPill ? " is-active" : ""}" data-pill="${it.key}">${it.label}</button>`)
      .join("");
    container.querySelectorAll(".weight-pill").forEach(btn => {
      btn.addEventListener("click", () => {
        currentPill = btn.getAttribute("data-pill");
        renderPills();
        renderSpotlight();
      });
    });
  }

  // ---------- Tiles ----------

  function tileHtml(w) {
    const color = teamColors[w.team_slug];
    const style = color ? ` style="--team-accent:${color}"` : "";
    const img = w.photo_url
      ? `<img class="team-tile-logo" src="${w.photo_url}" alt="" onerror="this.style.display='none';" />`
      : "";
    return `
      <a class="team-tile" href="/wrestler.html?id=${w.wrestler_id}"${style}>
        ${img}
        <div class="team-tile-body">
          <div class="team-tile-name">${escapeHtml(w.name)}</div>
          <div class="team-tile-stat">${escapeHtml(w.team || "")}</div>
        </div>
      </a>`;
  }

  function renderSpotlight() {
    const container = document.getElementById("spotlight-sections");
    if (!container || !weightsData) return;

    if (currentPill === "all") {
      container.innerHTML = WEIGHTS.map(w => {
        const tiles = (weightsData[String(w)] || []).slice(0, 8);
        return `
          <div class="conf-section">
            <p class="conf-section-title">${w}</p>
            <div class="team-tile-grid">${tiles.map(tileHtml).join("")}</div>
          </div>`;
      }).join("");
    } else if (currentPill === "top1") {
      const tiles = WEIGHTS.map(w => (weightsData[String(w)] || [])[0]).filter(Boolean);
      container.innerHTML = `
        <div class="conf-section">
          <p class="conf-section-title">#1's</p>
          <div class="team-tile-grid">${tiles.map(tileHtml).join("")}</div>
        </div>`;
    } else {
      const tiles = (weightsData[currentPill] || []).slice(0, 8);
      container.innerHTML = `
        <div class="conf-section">
          <p class="conf-section-title">${currentPill}</p>
          <div class="team-tile-grid">${tiles.map(tileHtml).join("") || "<p>No data for this weight.</p>"}</div>
        </div>`;
    }
  }

  async function loadData() {
    try {
      const [p4pRes, colorsRes] = await Promise.all([
        fetch(`/data/p4p/${P4P_SEASON}.json`),
        fetch("/data/team_colors.json"),
      ]);
      if (!p4pRes.ok) throw new Error("Failed to load P4P data");
      const data = await p4pRes.json();
      weightsData = {};
      WEIGHTS.forEach(w => {
        const list = (data.weights && data.weights[String(w)]) || [];
        weightsData[String(w)] = [...list].sort((a, b) => (a.rank || 999) - (b.rank || 999));
      });

      if (colorsRes.ok) {
        const colorsData = await colorsRes.json();
        Object.entries(colorsData.teams || {}).forEach(([slug, c]) => {
          teamColors[slug] = c.hex;
        });
      }

      renderSpotlight();
    } catch (err) {
      console.error("Error loading spotlight:", err);
      const container = document.getElementById("spotlight-sections");
      if (container) container.innerHTML = "<p>Unable to load spotlight.</p>";
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    initDirectorySearch();
    renderPills();
    loadData();
  });
})();
