// Shared event tab bar for the NCAA event shell (/events/ncaa.html) and its
// six archive sections, which used to be flat items in the "Tournaments"
// dropdown. Injected as markup only -- does not touch any page's own JS/data
// logic, so the existing analytics pages stay exactly as they were.
//
// To add another event later, add a new *_TABS array + a lookup for its
// pages, following the NCAA pattern below.

(function () {
  "use strict";

  const NCAA_ARCHIVE_TABS = [
    { label: "Seed Analysis", url: "/ncaa_report.html" },
    { label: "Scoring Trends", url: "/ncaa_scoring_trends.html" },
    { label: "Team Leaderboard", url: "/ncaa_team_leaderboard.html" },
    { label: "Team Analysis", url: "/ncaa_team_report.html" },
    { label: "Conference Leaderboard", url: "/ncaa_conf_leaderboard.html" },
    { label: "Conference Analysis", url: "/ncaa_conf_analysis.html" },
  ];
  const NCAA_LIVE_URL = "/ncaa_live.html";
  const NCAA_HUB_URL = "/events/ncaa.html";

  const STYLE = `
    .event-tabs { max-width: 1100px; margin: 0 auto; padding: 16px 16px 0; }
    .event-tabs-top { display: flex; gap: 8px; border-bottom: 1px solid var(--border); margin-bottom: 10px; }
    .event-tabs-top a {
      padding: 8px 4px; font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.03em; color: var(--muted); text-decoration: none; border-bottom: 2px solid transparent;
    }
    .event-tabs-top a:hover { color: var(--text); }
    .event-tabs-top a.is-active { color: var(--accent); border-bottom-color: var(--accent); }
    .event-tabs-sub { display: flex; flex-wrap: wrap; gap: 6px 14px; padding-bottom: 12px; }
    .event-tabs-sub a {
      font-size: 0.8rem; color: var(--muted); text-decoration: none; padding: 4px 0;
    }
    .event-tabs-sub a:hover { color: var(--text); }
    .event-tabs-sub a.is-active { color: var(--text); font-weight: 700; }
  `;

  function currentPath() {
    return window.location.pathname.replace(/\/$/, "").toLowerCase();
  }

  function isCurrent(url) {
    return currentPath() === url.toLowerCase();
  }

  function buildHTML() {
    const onLive = isCurrent(NCAA_LIVE_URL);
    const topHtml = `
      <div class="event-tabs-top">
        <a href="${NCAA_LIVE_URL}" class="${onLive ? "is-active" : ""}">Live</a>
        <a href="${NCAA_HUB_URL}" class="${onLive ? "" : "is-active"}">Archive</a>
      </div>`;
    const subHtml = onLive
      ? ""
      : `<div class="event-tabs-sub">${NCAA_ARCHIVE_TABS.map(
          t => `<a href="${t.url}" class="${isCurrent(t.url) ? "is-active" : ""}">${t.label}</a>`
        ).join("")}</div>`;
    return `<div class="event-tabs">${topHtml}${subHtml}</div>`;
  }

  function init() {
    const styleTag = document.createElement("style");
    styleTag.textContent = STYLE;
    document.head.appendChild(styleTag);

    const header = document.getElementById("site-header");
    if (header) {
      header.insertAdjacentHTML("afterend", buildHTML());
    } else {
      document.body.insertAdjacentHTML("afterbegin", buildHTML());
    }
  }

  // header.js inserts #site-header on DOMContentLoaded; run just after.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
  } else {
    setTimeout(init, 0);
  }
})();
