/* Monday — admin: "⋯" row action menus close cleanly on outside click & Escape (drawer handled by components/drawer.js). */
(function () {
  "use strict";
  document.addEventListener("click", (e) => {
    document.querySelectorAll("details.menu[open]").forEach((d) => {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    document.querySelectorAll("details.menu[open]").forEach((d) => d.removeAttribute("open"));
  });
})();
