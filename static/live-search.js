(() => {
  "use strict";
  function enhance(root) {
    if (root.dataset.paginationReady) return;
    root.dataset.paginationReady = "true";
    const rows = Array.from(root.querySelectorAll("[data-filter-row]"));
    const input = Array.from(document.querySelectorAll("[data-local-search]")).find((item) => item.dataset.localSearch === `#${root.id}`);
    const empty = root.querySelector("[data-filter-empty]");
    const pager = root.querySelector("[data-table-pagination]");
    const nav = pager?.querySelector("[data-page-navigation]");
    const summary = pager?.querySelector("[data-page-summary]");
    const numbers = pager?.querySelector("[data-page-numbers]");
    const pageSize = Math.max(1, Number(root.dataset.pageSize) || 25);
    let page = 1;
    let totalPages = 1;

    function renderNumbers() {
      if (!numbers) return;
      numbers.replaceChildren();
      const pages = new Set([1, totalPages]);
      for (let value = page - 2; value <= page + 2; value++) {
        if (value > 0 && value <= totalPages) pages.add(value);
      }
      let previous = 0;
      Array.from(pages).sort((a, b) => a - b).forEach((value) => {
        if (previous && value - previous > 1) {
          const gap = document.createElement("span");
          gap.className = "pagination-ellipsis";
          gap.textContent = "…";
          gap.setAttribute("aria-hidden", "true");
          numbers.append(gap);
        }
        const button = document.createElement("button");
        button.type = "button";
        button.className = "button";
        button.dataset.pageNumber = String(value);
        button.textContent = String(value);
        button.setAttribute("aria-label", `Page ${value}`);
        if (value === page) button.setAttribute("aria-current", "page");
        numbers.append(button);
        previous = value;
      });
    }

    function render() {
      const query = (input?.value || "").trim().toLowerCase();
      const matching = rows.filter((row) => row.textContent.toLowerCase().includes(query));
      totalPages = Math.max(1, Math.ceil(matching.length / pageSize));
      page = Math.min(page, totalPages);
      rows.forEach((row) => { row.hidden = true; });
      const start = (page - 1) * pageSize;
      matching.slice(start, start + pageSize).forEach((row) => { row.hidden = false; });
      if (empty) empty.hidden = matching.length !== 0;
      if (!pager) return;
      pager.hidden = false;
      summary.textContent = `Showing ${matching.length ? start + 1 : 0}–${Math.min(start + pageSize, matching.length)} of ${matching.length} ${root.dataset.paginationResource || "rows"}`;
      nav.hidden = totalPages <= 1;
      nav.querySelector('[data-page-action="previous"]').disabled = page === 1;
      nav.querySelector('[data-page-action="next"]').disabled = page === totalPages;
      renderNumbers();
    }

    input?.addEventListener("input", () => { page = 1; render(); });
    pager?.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-page-action], button[data-page-number]");
      if (!button || button.disabled) return;
      if (button.dataset.pageNumber) page = Number(button.dataset.pageNumber);
      else page += button.dataset.pageAction === "next" ? 1 : -1;
      page = Math.max(1, Math.min(page, totalPages));
      render();
      if (button.dataset.pageNumber) numbers.querySelector('[aria-current="page"]')?.focus();
    });
    render();
  }

  function initialize(scope) {
    if (scope.matches?.("[data-paginated-table]")) enhance(scope);
    scope.querySelectorAll("[data-paginated-table]").forEach(enhance);
    // Keep immediate local filtering available for tables without pagination.
    document.querySelectorAll("[data-local-search]").forEach((input) => {
      const root = document.querySelector(input.dataset.localSearch);
      if (!root || root.hasAttribute("data-paginated-table") || input.dataset.searchReady) return;
      input.dataset.searchReady = "true";
      const rows = Array.from(root.querySelectorAll("[data-filter-row]"));
      const empty = root.querySelector("[data-filter-empty]");
      function filter() {
        const query = input.value.trim().toLowerCase();
        let shown = 0;
        rows.forEach((row) => {
          row.hidden = !row.textContent.toLowerCase().includes(query);
          if (!row.hidden) shown++;
        });
        if (empty) empty.hidden = shown !== 0;
      }
      input.addEventListener("input", filter);
      filter();
    });
  }
  initialize(document);
  document.addEventListener("htmx:load", (event) => initialize(event.detail.elt));
})();
