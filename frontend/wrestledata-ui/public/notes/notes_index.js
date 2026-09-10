// Notes index: reverse-chronological list from /data/notes/notes.json.

(function () {
  "use strict";

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function formatDate(iso) {
    const d = new Date(iso + "T00:00:00");
    if (isNaN(d)) return iso;
    return d.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });
  }

  async function load() {
    const list = document.getElementById("notes-list");
    if (!list) return;
    try {
      const res = await fetch("/data/notes/notes.json");
      if (!res.ok) throw new Error("Failed to load notes");
      const notes = await res.json();
      const sorted = [...notes].sort((a, b) => (a.date < b.date ? 1 : -1));
      if (sorted.length === 0) {
        list.innerHTML = "<p>No notes yet.</p>";
        return;
      }
      list.innerHTML = sorted
        .map(n => {
          const thumb = n.images && n.images[0]
            ? `<img class="note-list-thumb" src="${n.images[0]}" alt="" loading="lazy" />`
            : "";
          return `
            <a class="note-list-item" href="/notes/note.html?slug=${encodeURIComponent(n.slug)}">
              <div class="note-list-date">${formatDate(n.date)}</div>
              <h2 class="note-list-title">${escapeHtml(n.title)}</h2>
              <p class="note-list-hook">${escapeHtml(n.hook || "")}</p>
              ${thumb}
            </a>`;
        })
        .join("");
    } catch (err) {
      console.error("Error loading notes:", err);
      list.innerHTML = "<p>Unable to load notes.</p>";
    }
  }

  document.addEventListener("DOMContentLoaded", load);
})();
