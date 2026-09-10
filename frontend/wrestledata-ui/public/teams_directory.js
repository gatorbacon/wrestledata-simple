// Teams directory landing page: search + conference-pill filter + every D1
// team grouped by conference. Search re-implements the header's Fuse setup
// locally (results-only dropdown, no header search bar dependency) so this
// page works even if header.js's search init changes.
//
// Conference membership: see /data/team_conferences.json -- the live
// team-list scrape doesn't capture conference (docs/matsavant.md, Known
// Gotcha #12), so this is backfilled from the last scrape that did. xTP is
// the 2026 season (completed); teams missing from that fall back to 2027
// preseason title probability (p_1st) from team_odds.

const XTP_SEASON = "2026";
const TEAM_ODDS_SEASON = "2027";
const CONF_ORDER = ["Big Ten", "Big 12", "ACC", "EIWA", "MAC", "SoCon"];

let TEAM_DIRECTORY = {}; // slug -> { name, conference }
let TEAM_COLORS = {}; // slug -> { hex }
let TEAM_XTP = {}; // slug -> xTP value
let TEAM_TITLE_PCT = {}; // slug -> p_1st value
let currentConf = "all";

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function teamNameToSlug(teamName) {
  if (!teamName) return "";
  let slug = teamName.toLowerCase();
  slug = slug.replace(/\s+/g, "_");
  slug = slug.replace(/[^\w_]/g, "");
  slug = slug.replace(/_+/g, "_");
  slug = slug.replace(/^_+|_+$/g, "");
  return slug;
}

// ---------- Search ----------

function initDirectorySearch() {
  const input = document.getElementById("directory-search-input");
  const dropdown = document.getElementById("directory-search-dropdown");
  if (!input || !dropdown) return;
  if (typeof Fuse === "undefined" || !window.SEARCH_INDEX) return;

  const fuse = new Fuse(window.SEARCH_INDEX.filter(r => r.type === "team"), {
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

// ---------- Conference pills ----------

function renderPills() {
  const container = document.getElementById("conf-pills");
  if (!container) return;
  const present = new Set(Object.values(TEAM_DIRECTORY).map(t => t.conference));
  const extras = [...present].filter(c => c && !CONF_ORDER.includes(c)).sort();
  const confs = ["All", ...CONF_ORDER.filter(c => present.has(c)), ...extras];

  container.innerHTML = confs
    .map(c => {
      const key = c === "All" ? "all" : c;
      return `<button type="button" class="conf-pill${key === currentConf ? " is-active" : ""}" data-conf="${escapeHtml(key)}">${escapeHtml(c)}</button>`;
    })
    .join("");
  container.querySelectorAll(".conf-pill").forEach(btn => {
    btn.addEventListener("click", () => {
      currentConf = btn.getAttribute("data-conf");
      renderPills();
      renderSections();
    });
  });
}

// ---------- Team tiles ----------

function statLine(slug) {
  if (TEAM_XTP[slug] != null) return `${TEAM_XTP[slug].toFixed(1)} xTP`;
  if (TEAM_TITLE_PCT[slug] != null) return `${TEAM_TITLE_PCT[slug].toFixed(1)}% to win it all`;
  return "No projection yet";
}

function tileHtml(slug, team) {
  const color = TEAM_COLORS[slug];
  const style = color ? ` style="--team-accent:${color}"` : "";
  return `
    <a class="team-tile" href="/team.html?team=${encodeURIComponent(slug)}"${style}>
      <img class="team-tile-logo" src="/assets/team_logos/${slug}.svg" alt=""
           onerror="if(!this.dataset.fb){this.dataset.fb='1';this.src='/assets/team_logos/${slug}.png';}else{this.style.display='none';}" />
      <div class="team-tile-body">
        <div class="team-tile-name">${escapeHtml(team.name)}</div>
        <div class="team-tile-stat">${statLine(slug)}</div>
      </div>
    </a>`;
}

function renderSections() {
  const container = document.getElementById("conf-sections");
  if (!container) return;

  const byConf = {};
  Object.entries(TEAM_DIRECTORY).forEach(([slug, team]) => {
    const conf = team.conference || "Other";
    if (currentConf !== "all" && conf !== currentConf) return;
    if (!byConf[conf]) byConf[conf] = [];
    byConf[conf].push([slug, team]);
  });

  const present = Object.keys(byConf);
  const extras = present.filter(c => !CONF_ORDER.includes(c)).sort();
  const orderedConfs = [...CONF_ORDER.filter(c => byConf[c]), ...extras.filter(c => byConf[c])];

  container.innerHTML = orderedConfs
    .map(conf => {
      const teams = [...byConf[conf]].sort((a, b) => a[1].name.localeCompare(b[1].name));
      return `
        <div class="conf-section">
          <p class="conf-section-title">${escapeHtml(conf)}</p>
          <div class="team-tile-grid">${teams.map(([slug, team]) => tileHtml(slug, team)).join("")}</div>
        </div>`;
    })
    .join("");
}

// ---------- Data loading ----------

async function loadData() {
  try {
    const [dirRes, colorsRes, xtpRes] = await Promise.all([
      fetch("/data/team_directory.json"),
      fetch("/data/team_colors.json"),
      fetch(`/data/xtp/${XTP_SEASON}/xtp_teams_${XTP_SEASON}.json`),
    ]);
    if (!dirRes.ok) throw new Error("Failed to load team directory");
    TEAM_DIRECTORY = await dirRes.json();

    if (colorsRes.ok) {
      const colorsData = await colorsRes.json();
      Object.entries(colorsData.teams || {}).forEach(([slug, c]) => {
        TEAM_COLORS[slug] = c.hex;
      });
    }

    if (xtpRes.ok) {
      const xtpData = await xtpRes.json();
      (xtpData.teams || []).forEach(t => {
        TEAM_XTP[teamNameToSlug(t.team)] = t.team_xTP;
      });
    }

    // Title % fallback: only fetch if some teams still need it.
    const stillMissing = Object.keys(TEAM_DIRECTORY).some(slug => TEAM_XTP[slug] == null);
    if (stillMissing) {
      const idxRes = await fetch(`/data/team_odds/${TEAM_ODDS_SEASON}/index.json`);
      if (idxRes.ok) {
        const idx = await idxRes.json();
        const latestDate = (idx.dates || [])[idx.dates.length - 1];
        if (latestDate) {
          const oddsRes = await fetch(`/data/team_odds/${TEAM_ODDS_SEASON}/${latestDate}.json`);
          if (oddsRes.ok) {
            const oddsData = await oddsRes.json();
            (oddsData.teams || []).forEach(t => {
              TEAM_TITLE_PCT[teamNameToSlug(t.team)] = t.p_1st;
            });
          }
        }
      }
    }

    renderPills();
    renderSections();
  } catch (err) {
    console.error("Error loading teams directory:", err);
    const container = document.getElementById("conf-sections");
    if (container) container.innerHTML = "<p>Unable to load teams.</p>";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initDirectorySearch();
  loadData();
});
