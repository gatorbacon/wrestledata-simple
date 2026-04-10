// ========================================
// KY HS Configuration
// Centralized config for all HS pages
// ========================================

const HS_CONFIG = {
  defaultSeason: '2026',
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
// Helper Functions
// ========================================

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

