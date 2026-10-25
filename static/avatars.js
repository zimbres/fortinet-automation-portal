(() => {
  "use strict";
  document.addEventListener("error", (event) => {
    if (event.target.matches?.("img[data-avatar-image]")) event.target.hidden = true;
  }, true);
  document.querySelectorAll("img[data-avatar-image]").forEach((image) => {
    if (image.complete && image.naturalWidth === 0) image.hidden = true;
  });
})();
