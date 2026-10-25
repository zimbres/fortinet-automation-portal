(() => {
  "use strict";

  function enhance(root) {
    if (root.dataset.transferReady) return;
    const source = root.querySelector("select[multiple]");
    const ui = root.querySelector(".transfer-select__ui");
    if (!source || !ui) return;
    const options = Array.from(source.options);
    const indexes = new Map(options.map((option,index) => [option,String(index)]));
    const labels = Array.from(source.labels || []);
    const caption = (labels[0]?.textContent || source.name).trim().replace(/:$/, "");
    const required = source.required;
    const highlighted = new Set();
    const lists = {};
    const filters = {};
    const buttons = {};
    const status = root.querySelector(".transfer-select__status");
    const sides = ["available", "selected"];
    const disabled = option => source.disabled || option.disabled || option.parentElement.disabled;

    for (const side of sides) {
      lists[side] = root.querySelector(`[data-transfer-list="${side}"]`);
      filters[side] = root.querySelector(`[data-transfer-filter="${side}"]`);
      lists[side].setAttribute("aria-label", `${caption}: ${side} items`);
      filters[side].setAttribute("aria-label", `Filter ${side} ${caption}`);
      filters[side].disabled = source.disabled;
      lists[side].disabled = source.disabled;
      lists[side].addEventListener("change", () => {
        for (const option of options) if (inSide(option,side)) highlighted.delete(option);
        for (const item of lists[side].selectedOptions) {
          const option=options[Number(item.value)];
          if (option && !item.disabled) highlighted.add(option);
        }
        updateButtons();
      });
    }
    for (const action of ["add", "add-all", "remove", "remove-all"]) {
      buttons[action] = root.querySelector(`[data-transfer-action="${action}"]`);
    }

    const inSide = (option, side) => option.selected === (side === "selected");
    const matches = (option, side) => option.text.toLocaleLowerCase().includes(filters[side].value.trim().toLocaleLowerCase());

    function updateButtons() {
      for (const [side, action] of [["available", "add"], ["selected", "remove"]]) {
        buttons[action].disabled = !options.some(option => inSide(option, side) && highlighted.has(option) && !disabled(option));
        buttons[`${action}-all`].disabled = !options.some(option => inSide(option, side) && matches(option, side) && !disabled(option));
        buttons[`${action}-all`].querySelector("span").textContent = `${action === "add" ? "Add" : "Remove"} all${filters[side].value.trim() ? " shown" : ""}`;
      }
    }

    function render() {
      for (const side of sides) {
        const all = options.filter(option => inSide(option, side));
        const shown = all.filter(option => matches(option, side));
        const fragment = document.createDocumentFragment();
        for (const option of shown) {
          const item = document.createElement("option");
          item.value = indexes.get(option);
          item.textContent = option.text;
          item.title = option.text;
          item.selected = highlighted.has(option);
          item.disabled = disabled(option);
          fragment.append(item);
        }
        if (!shown.length) {
          const empty = document.createElement("option");
          empty.disabled = true;
          empty.textContent = all.length ? "No matching items." : side === "selected" ? "No items selected." : "No available items.";
          fragment.append(empty);
        }
        lists[side].replaceChildren(fragment);
        root.querySelector(`[data-transfer-count="${side}"]`).textContent = shown.length === all.length ? String(all.length) : `${shown.length} of ${all.length}`;
      }
      filters.available.setCustomValidity(required && !source.disabled && !options.some(option => option.selected) ? "Add at least one item to Selected." : "");
      updateButtons();
    }

    function move(action) {
      const side = action.startsWith("add") ? "available" : "selected";
      const all = action.endsWith("-all");
      let moved = 0;
      for (const option of options) {
        if (!inSide(option, side) || disabled(option) || !(all ? matches(option, side) : highlighted.has(option))) continue;
        option.selected = side === "available";
        highlighted.delete(option);
        moved += 1;
      }
      render();
      status.textContent = `${moved} ${moved === 1 ? "item" : "items"} ${side === "available" ? "added" : "removed"}. ${options.filter(option => option.selected).length} selected.`;
      source.dispatchEvent(new Event("change", {bubbles: true}));
    }

    for (const action of Object.keys(buttons)) buttons[action].addEventListener("click", () => move(action));
    for (const side of sides) {
      filters[side].addEventListener("input", () => {
        for (const option of options) if (inSide(option,side)) highlighted.delete(option);
        render();
      });
      filters[side].addEventListener("keydown", event => {
        if (event.key === "Enter") event.preventDefault();
      });
    }
    source.addEventListener("change", render);
    source.form?.addEventListener("reset", () => setTimeout(() => {
      highlighted.clear();
      for (const side of sides) filters[side].value = "";
      status.textContent = "";
      render();
    }, 0));
    ui.setAttribute("role", "group");
    ui.setAttribute("aria-label", caption);
    if (source.hasAttribute("aria-invalid")) ui.setAttribute("aria-invalid", source.getAttribute("aria-invalid"));
    if (source.hasAttribute("aria-describedby")) ui.setAttribute("aria-describedby", source.getAttribute("aria-describedby"));
    for (const label of labels) label.htmlFor = filters.available.id;
    source.required = false;
    source.hidden = true;
    ui.hidden = false;
    root.dataset.transferReady = "true";
    render();
  }

  function initialize(scope) {
    if (scope.matches?.("[data-transfer-select]")) enhance(scope);
    scope.querySelectorAll("[data-transfer-select]").forEach(enhance);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => initialize(document));
  else initialize(document);
  document.addEventListener("htmx:load", event => initialize(event.detail.elt));
})();
