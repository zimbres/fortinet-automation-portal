(() => {
  "use strict";
  const key = "portal-theme";
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  let choice;
  try { choice = localStorage.getItem(key); } catch (_) { /* Storage may be unavailable. */ }
  if (choice !== "light" && choice !== "dark") choice = null;
  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    const label = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
    document.querySelectorAll(".theme-toggle").forEach((button) => {
      button.setAttribute("aria-label", label);
      button.title = label;
    });
  }
  // Set before the stylesheet loads to prevent a flash of the wrong theme.
  apply(choice || (media.matches ? "dark" : "light"));
  document.addEventListener("DOMContentLoaded", () => apply(document.documentElement.dataset.theme));
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".theme-toggle")) return;
    choice = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    try { localStorage.setItem(key, choice); } catch (_) { /* Keep the choice for this page. */ }
    apply(choice);
  });
  media.addEventListener("change", () => { if (!choice) apply(media.matches ? "dark" : "light"); });
  window.addEventListener("storage", (event) => {
    if (event.key !== key) return;
    choice = event.newValue === "light" || event.newValue === "dark" ? event.newValue : null;
    apply(choice || (media.matches ? "dark" : "light"));
  });
})();
