// Shared "Lab · not a ranking" stamp for pages that live in /lab. Markup
// only -- does not touch the host page's own JS/data logic. Per the site
// redesign: lab pages never link out from Rankings or a wrestler/team
// profile until promoted, and they carry this stamp everywhere they appear.

(function () {
  "use strict";

  const STYLE = `
    .lab-stamp-bar { max-width: 1100px; margin: 0 auto; padding: 14px 16px 0; }
    .lab-stamp {
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em;
      color: var(--muted); background: var(--panel-2); border: 1px solid var(--border);
      border-radius: 999px; padding: 4px 10px;
    }
    .lab-stamp a { color: inherit; text-decoration: underline; }
  `;

  function init() {
    const styleTag = document.createElement("style");
    styleTag.textContent = STYLE;
    document.head.appendChild(styleTag);

    const bar = document.createElement("div");
    bar.className = "lab-stamp-bar";
    bar.innerHTML = `<span class="lab-stamp">🧪 Lab · not a ranking · see <a href="/lab/index.html">all Lab pages</a></span>`;

    const header = document.getElementById("site-header");
    if (header) {
      header.insertAdjacentElement("afterend", bar);
    } else {
      document.body.insertAdjacentElement("afterbegin", bar);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setTimeout(init, 0));
  } else {
    setTimeout(init, 0);
  }
})();
