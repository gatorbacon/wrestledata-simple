// ========================================
// Mobile (<768px) app-home
// ========================================
// Wires up the Field Notes rows + reuses the header's search on the mobile
// app-home block (see index.html). The 4 launcher tiles are icon + label
// only (no live data), so there is nothing to fetch for those.

(function () {
  "use strict";

  async function fetchJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to fetch ${url}`);
    return res.json();
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function formatNoteDate(iso) {
    const d = new Date(iso + "T00:00:00");
    if (isNaN(d)) return iso;
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  async function loadFieldNotes() {
    const list = document.getElementById("app-notes-list");
    const block = document.getElementById("app-notes-block");
    if (!list || !block) return;
    try {
      const notes = await fetchJSON("/data/notes/notes.json");
      const sorted = [...notes].sort((a, b) => (a.date < b.date ? 1 : -1)).slice(0, 3);
      if (!sorted.length) {
        block.hidden = true;
        return;
      }
      list.innerHTML = sorted
        .map(
          n => `
            <a class="app-notes-row" href="/notes/note.html?slug=${encodeURIComponent(n.slug)}">
              <span class="app-notes-row-title">${escapeHtml(n.title)}</span>
              <span class="app-notes-row-date">${formatNoteDate(n.date)}</span>
            </a>`
        )
        .join("");
    } catch {
      block.hidden = true;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById("app-home-section")) return;
    loadFieldNotes();
    if (typeof window.initHeaderSearch === "function") {
      window.initHeaderSearch("app-home-search-input", "app-home-search-dropdown");
    }
  });
})();
