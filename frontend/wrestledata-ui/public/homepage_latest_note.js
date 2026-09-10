// Homepage "Latest Note" card: pulls the newest entry from notes.json.

(function () {
  "use strict";

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  async function load() {
    const section = document.getElementById("latest-note-section");
    if (!section) return;
    try {
      const res = await fetch("/data/notes/notes.json");
      if (!res.ok) throw new Error("Failed to load notes");
      const notes = await res.json();
      if (!notes.length) return;
      const latest = [...notes].sort((a, b) => (a.date < b.date ? 1 : -1))[0];

      document.getElementById("latest-note-link").href = `/notes/note.html?slug=${encodeURIComponent(latest.slug)}`;
      document.getElementById("latest-note-title").textContent = latest.title;
      document.getElementById("latest-note-hook").textContent = latest.hook || "";
      section.hidden = false;
    } catch (err) {
      console.error("Error loading latest note:", err);
    }
  }

  document.addEventListener("DOMContentLoaded", load);
})();
