// Shared lollipop/bubble DPG chart renderer -- reused by the single-
// wrestler view and the team-roster view. Pure function of a wrestler
// object ({seasons: [{year, team, team_slug, team_abbr, dpg, matches,
// rank, record}, ...]}) and a team-color map. Color is purely per-season
// team_slug -- no query-team concept here (that's specific to the
// transfer report, which has its own copy of this logic).
(function (global) {
  'use strict';

  const MIN_R = 14, MAX_R = 40;
  const YEAR_PITCH = 92;
  const PLOT_H = 250;
  const MARGIN = { top: 34, right: 34, bottom: 78, left: 52 };
  const QUALIFY_MIN_MATCHES = 6;
  const DEFAULT_COLOR = { hex: '#6b6153', stroke: false };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  }

  function hexToRgba(hex, alpha) {
    const h = hex.replace('#', '');
    const r = parseInt(h.substring(0, 2), 16), g = parseInt(h.substring(2, 4), 16), b = parseInt(h.substring(4, 6), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  }

  function textColorFor(hex) {
    const h = hex.replace('#', '');
    const r = parseInt(h.substring(0, 2), 16) / 255, g = parseInt(h.substring(2, 4), 16) / 255, b = parseInt(h.substring(4, 6), 16) / 255;
    const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    return lum > 0.6 ? '#211c16' : '#ffffff';
  }

  function radiusFor(matches) {
    const n = Math.max(2, Math.min(matches, 28));
    const t = (Math.sqrt(n) - Math.sqrt(2)) / (Math.sqrt(28) - Math.sqrt(2));
    return MIN_R + t * (MAX_R - MIN_R);
  }

  function niceStep(range) {
    const raw = range / 5;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    const step = norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10;
    return step * mag;
  }

  function colorFor(slug, colorMap) {
    return (colorMap.teams && colorMap.teams[slug]) || colorMap.default || DEFAULT_COLOR;
  }

  function buildYearSeries(wrestler) {
    const years = wrestler.seasons.map(s => s.year);
    const minY = Math.min(...years), maxY = Math.max(...years);
    const out = [];
    for (let y = minY; y <= maxY; y++) {
      out.push({ year: y, season: wrestler.seasons.find(s => s.year === y) || null });
    }
    return out;
  }

  function qualifyingSeasons(wrestler) {
    return wrestler.seasons.filter(s => s.matches >= QUALIFY_MIN_MATCHES);
  }

  function matchWeightedAvg(seasons) {
    const totalMatches = seasons.reduce((a, s) => a + s.matches, 0);
    if (!totalMatches) return null;
    return seasons.reduce((a, s) => a + s.dpg * s.matches, 0) / totalMatches;
  }

  // y-domain from qualifying (n>=6) seasons only -- a low-match season must
  // never set the y-max.
  function yDomain(qualifying) {
    const qualVals = qualifying.map(s => s.dpg);
    let lo = Math.min(0, ...(qualVals.length ? qualVals : [0]));
    let hi = Math.max(0, ...(qualVals.length ? qualVals : [0]));
    const pad = Math.max((hi - lo) * 0.28, 0.8);
    lo -= pad; hi += pad;
    return [lo, hi];
  }

  function buildChartSVG(wrestler, colorMap) {
    const series = buildYearSeries(wrestler);
    const qualifying = qualifyingSeasons(wrestler);
    const [yLo, yHi] = yDomain(qualifying);

    const width = MARGIN.left + MARGIN.right + Math.max(series.length - 1, 0) * YEAR_PITCH + 2 * MAX_R;
    const height = MARGIN.top + PLOT_H + MARGIN.bottom;

    const xScale = (i) => MARGIN.left + MAX_R + i * YEAR_PITCH;
    const yScale = (v) => MARGIN.top + PLOT_H - ((v - yLo) / (yHi - yLo)) * PLOT_H;
    const zeroY = yScale(0);
    const plotRight = width - MARGIN.right;

    let svg = `<svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg" font-family="Inter, system-ui, sans-serif">`;

    const step = niceStep(yHi - yLo);
    const firstTick = Math.ceil(yLo / step) * step;
    for (let v = firstTick; v <= yHi + 1e-9; v += step) {
      const y = yScale(v);
      if (Math.abs(v) < step / 1000) continue;
      svg += `<line x1="${MARGIN.left}" x2="${plotRight}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke="#e7e1d5" stroke-width="1"/>`;
      svg += `<text x="${MARGIN.left - 10}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="12" fill="#6b6153">${(Math.round(v * 10) / 10).toFixed(1)}</text>`;
    }
    svg += `<text x="4" y="${MARGIN.top - 12}" font-size="12" fill="#6b6153" font-weight="700">DPG</text>`;

    svg += `<line x1="${MARGIN.left}" x2="${plotRight}" y1="${zeroY.toFixed(1)}" y2="${zeroY.toFixed(1)}" stroke="#211c16" stroke-width="2.5"/>`;
    svg += `<text x="${MARGIN.left - 10}" y="${(zeroY + 4).toFixed(1)}" text-anchor="end" font-size="12" fill="#6b6153">0</text>`;

    series.forEach((entry, i) => {
      const x = xScale(i);
      if (!entry.season) {
        svg += `<text x="${x.toFixed(1)}" y="${(zeroY + 30).toFixed(1)}" text-anchor="middle" font-size="12" fill="#8f8574" font-style="italic">DNP</text>`;
        return;
      }
      const s = entry.season;
      const color = colorFor(s.team_slug, colorMap);
      const r = radiusFor(s.matches);
      const qualifies = s.matches >= QUALIFY_MIN_MATCHES;
      const cy = qualifies
        ? yScale(s.dpg)
        : Math.max(MARGIN.top + r + 2, Math.min(yScale(s.dpg), MARGIN.top + PLOT_H - r - 2));

      svg += `<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${zeroY.toFixed(1)}" y2="${cy.toFixed(1)}" stroke="#a39a89" stroke-width="1"/>`;

      const tipData = [
        `data-tooltip="1"`,
        `data-year="${esc(entry.year)}"`,
        `data-team="${esc(s.team)}"`,
        `data-matches="${esc(s.matches)}"`,
        `data-record="${esc(s.record != null ? s.record : '—')}"`,
        `data-rank="${esc(s.rank != null ? '#' + s.rank : 'NR')}"`,
        `data-dpg="${esc((s.dpg > 0 ? '+' : '') + s.dpg.toFixed(2))}"`,
      ].join(' ');

      if (qualifies) {
        const strokeAttr = color.stroke ? `stroke="#211c16" stroke-width="1.5"` : `stroke="none"`;
        svg += `<circle cx="${x.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r.toFixed(1)}" fill="${hexToRgba(color.hex, 0.78)}" ${strokeAttr} ${tipData}/>`;
      } else {
        svg += `<circle cx="${x.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r.toFixed(1)}" fill="${hexToRgba(color.hex, 0.18)}" stroke="${color.hex}" stroke-width="2" stroke-dasharray="3,2" ${tipData}/>`;
      }

      const labelUp = cy >= zeroY;
      const labelY = labelUp ? cy - r - 22 : cy + r + 16;
      const sign = s.dpg > 0 ? '+' : '';
      svg += `<text x="${x.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="middle" font-size="12" fill="#211c16" font-weight="700">${esc(entry.year)} ${esc(s.team_abbr)}</text>`;
      svg += `<text x="${x.toFixed(1)}" y="${(labelY + 15).toFixed(1)}" text-anchor="middle" font-size="12" fill="#6b6153">${sign}${s.dpg.toFixed(2)}${qualifies ? '' : ' *'}</text>`;
    });

    series.forEach((entry, i) => {
      const x = xScale(i);
      svg += `<text x="${x.toFixed(1)}" y="${height - 16}" text-anchor="middle" font-size="12" fill="#6b6153">${esc(entry.year)}</text>`;
    });
    svg += `<line x1="${MARGIN.left}" x2="${plotRight}" y1="${height - MARGIN.bottom + 26}" y2="${height - MARGIN.bottom + 26}" stroke="#e7e1d5" stroke-width="1"/>`;

    svg += `</svg>`;
    return svg;
  }

  let tooltipEl = null;
  function getTooltip() {
    if (!tooltipEl) {
      tooltipEl = document.createElement('div');
      tooltipEl.className = 'rv-tooltip';
      document.body.appendChild(tooltipEl);
    }
    return tooltipEl;
  }

  function wireTooltips(chartWrap) {
    const tip = getTooltip();
    chartWrap.querySelectorAll('circle[data-tooltip]').forEach(circle => {
      circle.addEventListener('mouseenter', () => {
        const d = circle.dataset;
        tip.innerHTML = `
          <div class="tt-head">${esc(d.year)} &middot; ${esc(d.team)}</div>
          <div class="tt-row"><span class="tt-label">Matches</span><span class="tt-value">${esc(d.matches)}</span></div>
          <div class="tt-row"><span class="tt-label">Record</span><span class="tt-value">${esc(d.record)}</span></div>
          <div class="tt-row"><span class="tt-label">Final rank</span><span class="tt-value">${esc(d.rank)}</span></div>
          <div class="tt-row"><span class="tt-label">DPG</span><span class="tt-value">${esc(d.dpg)}</span></div>
        `;
        tip.classList.add('visible');
      });
      circle.addEventListener('mousemove', (e) => {
        const pad = 14;
        let x = e.clientX + pad, y = e.clientY + pad;
        const rect = tip.getBoundingClientRect();
        if (x + rect.width > window.innerWidth - 8) x = e.clientX - rect.width - pad;
        if (y + rect.height > window.innerHeight - 8) y = e.clientY - rect.height - pad;
        tip.style.left = `${x}px`;
        tip.style.top = `${y}px`;
      });
      circle.addEventListener('mouseleave', () => {
        tip.classList.remove('visible');
      });
    });
  }

  global.WrestlerChart = {
    DEFAULT_COLOR, QUALIFY_MIN_MATCHES,
    esc, hexToRgba, textColorFor, colorFor,
    qualifyingSeasons, matchWeightedAvg,
    buildChartSVG, wireTooltips,
  };
})(window);
