// Page glue: event picker, weight tabs, URL state. Engine does the rest.
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  const view = BracketEngine.mount({ bracketEl: $("bracket"), navEl: $("nav") });
  let doc = null, current = null, index = null;
  const cache = {};

  function defaultCount() {
    const w = window.innerWidth;
    return w < 600 ? 2 : w < 900 ? 3 : 4;
  }
  function syncURL() {
    const w = view.getWindow();
    const p = new URLSearchParams({ event: $("event").value, w: current, from: w.start, n: w.count });
    history.replaceState(null, "", "?" + p.toString());
  }

  async function loadEvent(id) {
    const info = index.events.find((e) => e.id === id) || index.events[index.events.length - 1];
    $("event").value = info.id;
    cache[info.id] = cache[info.id] || fetch(info.file).then((r) => r.json());
    doc = await cache[info.id];
    $("title").textContent = doc.event.name;
    document.title = doc.event.short + " Bracket Viewer (Lab)";
    const tabs = $("weights");
    tabs.innerHTML = doc.brackets.map((b) =>
      `<button role="tab" type="button" data-id="${b.id}" aria-selected="false">${b.label}</button>`).join("");
    selectBracket(doc.brackets.some((b) => b.id === current) ? current : doc.brackets[0].id);
  }

  function selectBracket(id) {
    current = id;
    const b = doc.brackets.find((x) => x.id === id);
    document.querySelectorAll("#weights [role=tab]").forEach((t) => {
      const on = t.dataset.id === id;
      t.setAttribute("aria-selected", on);
      t.tabIndex = on ? 0 : -1;
    });
    view.load(doc, b);
    syncURL();
  }

  $("weights").addEventListener("click", (e) => {
    const t = e.target.closest("[role=tab]");
    if (t) selectBracket(t.dataset.id);
  });
  $("weights").addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const ids = doc.brackets.map((b) => b.id);
    const i = ids.indexOf(current) + (e.key === "ArrowRight" ? 1 : -1);
    if (i >= 0 && i < ids.length) { selectBracket(ids[i]); document.querySelector(`#weights [data-id="${ids[i]}"]`).focus(); }
  });
  $("event").addEventListener("change", () => loadEvent($("event").value));
  view.onWindowChange = syncURL;

  fetch("data/index.json").then((r) => r.json()).then(async (idx) => {
    index = idx;
    $("event").innerHTML = idx.events.slice().reverse().map((e) => `<option value="${e.id}">${e.name}</option>`).join("");
    current = params.get("w");
    const n = +params.get("n") || defaultCount();
    view.setWindow(+params.get("from") || 0, n, true);
    await loadEvent(params.get("event") || idx.events[idx.events.length - 1].id);
  });
})();
