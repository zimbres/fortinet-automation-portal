(() => {
  "use strict";
  const saved = new Map();

  document.addEventListener("htmx:beforeRequest", (event) => {
    const region = event.detail.elt;
    if (!region.matches("[data-live-refresh]")) return;
    // Polling must not disturb a focused action, a selection, or a background tab.
    const selection = window.getSelection();
    if (document.hidden || region.contains(document.activeElement) ||
        (selection && !selection.isCollapsed && region.contains(selection.anchorNode))) {
      event.preventDefault();
    }
  });

  document.addEventListener("htmx:beforeSwap", (event) => {
    if (event.detail.xhr.status === 403 && event.detail.xhr.getResponseHeader("X-Portal-Access-Denied") === "1") {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
      return;
    }
    const region = event.detail.target;
    if (!region.matches("[data-live-refresh], [data-search-results]") || !event.detail.shouldSwap) return;
    // A login redirect has no matching fragment. Open it as a complete page.
    const response = new DOMParser().parseFromString(event.detail.xhr.responseText, "text/html");
    if (!response.getElementById(region.id)) {
      event.detail.shouldSwap = false;
      const url = event.detail.xhr.responseURL;
      if (url && new URL(url).origin === location.origin) location.assign(url);
      return;
    }
    saved.set(region.id, {
      details: Array.from(region.querySelectorAll("details[id][open]"), (item) => item.id),
      tables: Array.from(region.querySelectorAll(".table-wrap"), (item) => item.scrollLeft),
    });
  });

  document.addEventListener("htmx:afterSwap", () => {
    const main = document.getElementById("main");
    if (main?.querySelector("[data-access-denied]")) {
      const heading = main.querySelector("h1, h2");
      if (heading) {
        heading.setAttribute("tabindex", "-1");
        heading.focus();
      }
    }
    for (const [id, state] of saved) {
      const region = document.getElementById(id);
      if (!region) continue;
      for (const detailId of state.details) {
        const detail = document.getElementById(detailId);
        if (detail && region.contains(detail)) detail.open = true;
      }
      region.querySelectorAll(".table-wrap").forEach((table, index) => {
        table.scrollLeft = state.tables[index] || 0;
      });
      saved.delete(id);
    }
  });
})();
