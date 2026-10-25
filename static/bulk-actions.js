(() => {
  "use strict";
  function enhance(root) {
    if (!root || root.dataset.bulkReady) return;
    root.dataset.bulkReady = "true";
    const all = root.querySelector("[data-select-all]");
    const boxes = Array.from(root.querySelectorAll("[data-object-select]"));
    const count = root.querySelector("[data-selection-count]");
    const button = root.querySelector("[data-delete-selected]");
    function update() {
      const selected = boxes.filter((box) => box.checked).length;
      all.checked = selected > 0 && selected === boxes.length;
      all.indeterminate = selected > 0 && selected < boxes.length;
      count.textContent = `${selected} selected (maximum 500)`;
      button.disabled = selected === 0 || selected > 500;
    }
    root.addEventListener("change", (event) => {
      if (event.target === all) boxes.forEach((box) => { box.checked = all.checked; });
      update();
    });
    update();
  }
  enhance(document.getElementById("bulk-object-selection"));
  document.addEventListener("htmx:load", () => enhance(document.getElementById("bulk-object-selection")));
})();
