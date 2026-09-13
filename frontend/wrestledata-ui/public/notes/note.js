// Single note page: reads ?slug=, loads the note's metadata from
// notes.json and its body blocks from /data/notes/body/<slug>.json.

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

  function renderBlocks(blocks) {
    return (blocks || [])
      .map(b => {
        if (b.type === "p") return `<p>${b.html != null ? b.html : escapeHtml(b.text)}</p>`;
        if (b.type === "img") {
          const caption = b.caption ? `<p class="note-img-caption">${escapeHtml(b.caption)}</p>` : "";
          return `<img src="${b.src}" alt="${escapeHtml(b.alt || "")}" loading="lazy" />${caption}`;
        }
        return "";
      })
      .join("");
  }

  async function load() {
    const slug = new URLSearchParams(window.location.search).get("slug");
    const titleEl = document.getElementById("note-title");
    const dateEl = document.getElementById("note-date");
    const bodyEl = document.getElementById("note-body");
    if (!slug) {
      titleEl.textContent = "Note not found";
      return;
    }
    try {
      const [notesRes, bodyRes] = await Promise.all([
        fetch("/data/notes/notes.json"),
        fetch(`/data/notes/body/${encodeURIComponent(slug)}.json`),
      ]);
      if (!notesRes.ok || !bodyRes.ok) throw new Error("Failed to load note");
      const notes = await notesRes.json();
      const meta = notes.find(n => n.slug === slug);
      const body = await bodyRes.json();

      titleEl.textContent = meta ? meta.title : slug;
      document.getElementById("note-title-tag").textContent = `${meta ? meta.title : slug} — MatSavant`;
      dateEl.textContent = meta ? formatDate(meta.date) : "";
      bodyEl.innerHTML = renderBlocks(body.blocks);
    } catch (err) {
      console.error("Error loading note:", err);
      titleEl.textContent = "Note not found";
    } finally {
      // Static pages fire their GA4 pageview automatically (see
      // header.js); this page's title isn't final until here.
      if (typeof window.sendPageView === "function") window.sendPageView();
    }
  }

  document.addEventListener("DOMContentLoaded", load);
})();
