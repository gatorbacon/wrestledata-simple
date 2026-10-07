// ========================================
// KY HS Configuration
// Centralized config for all HS pages
// ========================================

const HS_CONFIG = {
  // THE yearly switch (docs/kentuckymat_preseason_rankings.md, "Site 'preseason state'").
  // 'preseason': from the preseason rankings drop until the first in-season ranking.
  // 'season': from the first in-season ranking through state and the summer,
  //           until next year's preseason ({season: 2028, phase: 'preseason'}).
  siteSeason: { season: 2027, phase: 'preseason' },

  // Season whose match data pages load by default; set from siteSeason below.
  defaultSeason: null,
  defaultGender: 'boys', // Fallback if not in URL
  
  genders: {
    boys: {
      weights: [106, 113, 120, 126, 132, 138, 144, 150, 157, 165, 175, 190, 215, 285],
      defaultWeight: 106
    },
    girls: {
      weights: [100, 107, 114, 120, 126, 132, 138, 145, 152, 165, 185, 235],
      defaultWeight: 100
    }
  },
  
  dataPaths: {
    rankings: '/data/public_rankings', // Legacy path (deprecated)
    rankingsArchive: '/data/rankings', // New archive structure (top 40/24 only)
    rankingsFull: '/data/rankings_full', // Full rankings (ALL ranked wrestlers)
    matrix: '/data/matrix',
    xtp: '/data/xtp'
  }
};

// ========================================
// Past seasons (rankings-style pages)
// ========================================

/** Seasons with published rankings drops (written by create_rankings_release.py), newest first. */
async function loadPublishedSeasons(gender) {
  try {
    const resp = await fetch(`${HS_CONFIG.dataPaths.rankingsArchive}/${gender}/seasons.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!resp.ok) return [];
    const data = await resp.json();
    return (data.seasons || []).map(s => String(s.season));
  } catch (e) {
    return [];
  }
}

/**
 * Fill `el` with the page's season context:
 *  - past-season view (opts.isPast): "{season} {opts.what} (past season)" + "← Back to current {what}"
 *  - otherwise: opts.lines (plain-text notes) + "Past seasons: 2026, ..." links
 * Links go to `opts.page` (e.g. 'rankings.html') with ?season=YYYY.
 */
async function renderSeasonContext(el, opts) {
  if (!el) return;
  el.innerHTML = '';
  const addLine = () => {
    const line = document.createElement('div');
    line.className = 'rankings-context-line';
    el.appendChild(line);
    return line;
  };
  if (opts.isPast) {
    const line = addLine();
    const banner = document.createElement('span');
    banner.className = 'past-season-banner';
    banner.textContent = `${opts.season} ${opts.what} (past season)`;
    line.appendChild(banner);
    line.appendChild(document.createTextNode(' '));
    const back = document.createElement('a');
    back.href = buildPageURL(opts.page, opts.gender, {});
    back.textContent = `← Back to current ${opts.what}`;
    line.appendChild(back);
  } else {
    (opts.lines || []).forEach(text => { addLine().textContent = text; });
    const past = (await loadPublishedSeasons(opts.gender)).filter(s => s !== getSiteSeason());
    if (past.length) {
      const line = addLine();
      line.appendChild(document.createTextNode('Past seasons: '));
      past.forEach((s, i) => {
        if (i) line.appendChild(document.createTextNode(', '));
        const a = document.createElement('a');
        a.href = buildPageURL(opts.page, opts.gender, { season: s });
        a.textContent = s;
        line.appendChild(a);
      });
    }
  }
  el.style.display = el.childNodes.length ? 'block' : 'none';
}

/**
 * Preseason view of a team-standings page (Team Tournament, Team Duals): the
 * note plus one link to last season's final standings, nothing else (TJ,
 * 2026-10-07: the whole site is in 2027 mode; 2026 only on an explicit click).
 * Hides the page's table section and anything matched by `hideSelectors`.
 */
function renderPreseasonStandingsNote(el, opts) {
  if (!el) return;
  const stats = getStatsSeason();
  el.innerHTML = '';
  const box = createComingSoonBlock();
  const line = document.createElement('div');
  line.className = 'coming-soon-link';
  const a = document.createElement('a');
  a.href = buildPageURL(opts.page, opts.gender, { season: stats });
  a.textContent = `See the ${stats} final standings →`;
  line.appendChild(a);
  box.appendChild(line);
  el.appendChild(box);
  el.style.display = 'block';
  (opts.hideSelectors || []).forEach(sel => {
    document.querySelectorAll(sel).forEach(node => { node.style.display = 'none'; });
  });
  const seasonEl = document.getElementById('season-info');
  if (seasonEl) {
    const g = opts.gender.charAt(0).toUpperCase() + opts.gender.slice(1);
    seasonEl.textContent = `${getSiteSeason()} Preseason — ${g}`;
  }
}

// ========================================
// Helper Functions
// ========================================

/** True between the preseason rankings drop and the first in-season ranking. */
function isPreseason() {
  return HS_CONFIG.siteSeason.phase === 'preseason';
}

/** The season the site is "in" (2027 in both its preseason and season phases). */
function getSiteSeason() {
  return String(HS_CONFIG.siteSeason.season);
}

/**
 * The season with real match data: last season during the preseason (no
 * matches yet), otherwise the site season. Pages showing records/stats use it.
 */
function getStatsSeason() {
  const s = HS_CONFIG.siteSeason.season;
  return String(isPreseason() ? s - 1 : s);
}

HS_CONFIG.defaultSeason = getStatsSeason();

/**
 * "Coming Soon" block for features that wait for real lineups in the preseason
 * (Team Tournament, Team Duals, team page projection, Dual Predictor). Kept
 * short on purpose (TJ, 2026-10-07: "people will understand").
 */
function createComingSoonBlock(title = 'Coming Soon') {
  const box = document.createElement('div');
  box.className = 'coming-soon-block';
  const h = document.createElement('div');
  h.className = 'coming-soon-title';
  h.textContent = title;
  const p = document.createElement('div');
  p.className = 'coming-soon-sub';
  p.textContent = 'Expected in early December, after the season begins.';
  box.appendChild(h);
  box.appendChild(p);
  return box;
}

/**
 * Get gender from URL query parameter
 * @returns {string} 'boys' or 'girls' (defaults to 'boys')
 */
function getGenderFromURL() {
  const params = new URLSearchParams(window.location.search);
  const gender = params.get('gender');
  return (gender === 'boys' || gender === 'girls') ? gender : HS_CONFIG.defaultGender;
}

/**
 * Get season from URL query parameter or use default
 * @returns {string} Season year (e.g., '2026')
 */
function getSeasonFromURL() {
  const params = new URLSearchParams(window.location.search);
  return params.get('season') || HS_CONFIG.defaultSeason;
}

/**
 * Get weight from URL query parameter or use gender default
 * @param {string} gender - 'boys' or 'girls'
 * @returns {number} Weight class
 */
function getWeightFromURL(gender) {
  const params = new URLSearchParams(window.location.search);
  const weightParam = params.get('weight');
  const validWeights = HS_CONFIG.genders[gender].weights;
  const defaultWeight = HS_CONFIG.genders[gender].defaultWeight;
  
  if (!weightParam) {
    return defaultWeight;
  }
  
  const weight = parseInt(weightParam);
  return validWeights.includes(weight) ? weight : defaultWeight;
}

/**
 * Get valid weights for a gender
 * @param {string} gender - 'boys' or 'girls'
 * @returns {number[]} Array of valid weight classes
 */
function getWeightsForGender(gender) {
  return HS_CONFIG.genders[gender]?.weights || HS_CONFIG.genders[HS_CONFIG.defaultGender].weights;
}

/**
 * Build data URL for rankings
 * @param {string} gender - 'boys' or 'girls'
 * @param {string} season - Season year
 * @param {number} weight - Weight class
 * @returns {string} Full URL path
 */
function buildRankingsURL(gender, season, weight) {
  return `${HS_CONFIG.dataPaths.rankings}/${gender}/${season}/${weight}.json`;
}

/**
 * Build data URL for matrix
 * @param {string} gender - 'boys' or 'girls'
 * @param {string} season - Season year
 * @param {number} weight - Weight class
 * @returns {string} Full URL path
 */
function buildMatrixURL(gender, season, weight) {
  return `${HS_CONFIG.dataPaths.matrix}/${gender}/${season}/${weight}.json`;
}

/**
 * Build data URL for xTP
 * @param {string} gender - 'boys' or 'girls'
 * @param {string} season - Season year
 * @returns {string} Full URL path
 */
function buildXTPURL(gender, season) {
  return `${HS_CONFIG.dataPaths.xtp}/${gender}/${season}/xtp_teams_${season}.json`;
}

/**
 * Build page URL with gender parameter preserved
 * @param {string} page - Page name (e.g., 'rankings.html', 'matrix.html')
 * @param {string} gender - 'boys' or 'girls'
 * @param {object} additionalParams - Additional query parameters (e.g., {weight: 106})
 * @returns {string} Full URL with query parameters
 */
function buildPageURL(page, gender, additionalParams = {}) {
  const params = new URLSearchParams();
  params.set('gender', gender);
  
  Object.entries(additionalParams).forEach(([key, value]) => {
    if (value !== null && value !== undefined) {
      params.set(key, value.toString());
    }
  });
  
  return `${page}?${params.toString()}`;
}

function sendPageView() {
  if (typeof gtag === 'function') {
    gtag('event', 'page_view', {
      page_title: document.title,
      page_location: window.location.href,
    });
  }
}

function setMetaDescription(content) {
  let tag = document.querySelector('meta[name="description"]');
  if (!tag) {
    tag = document.createElement('meta');
    tag.setAttribute('name', 'description');
    document.head.appendChild(tag);
  }
  tag.setAttribute('content', content);
}

function setCanonicalURL(url) {
  let tag = document.querySelector('link[rel="canonical"]');
  if (!tag) {
    tag = document.createElement('link');
    tag.setAttribute('rel', 'canonical');
    document.head.appendChild(tag);
  }
  tag.setAttribute('href', url);
}

// Static pages don't set dynamic titles — fire pageview for them on load
// Dynamic pages (wrestler, team, rankings, leaderboards) call sendPageView() themselves after setting title
const _dynamicPages = ['wrestler.html', 'team.html', 'rankings.html', 'leaderboards.html', 'recruiting.html'];
const _isStaticPage = !_dynamicPages.some(p => window.location.pathname.includes(p));
if (_isStaticPage) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', sendPageView);
  } else {
    sendPageView();
  }
}

