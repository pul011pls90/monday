/* Monday — admin: person card slides in without reloading; "⋯" menus close on outside click. */
(function () {
  "use strict";
  const panel = document.querySelector("[data-person-panel]");
  const body = panel && panel.querySelector("[data-panel-body]");
  const close = () => {
    if (!panel) return;
    panel.hidden = true;
    const url = new URL(window.location.href);
    url.searchParams.delete("user");
    history.replaceState(null, "", url);
  };
  document.addEventListener("click", async (e) => {
    const link = e.target.closest("[data-panel-link]");
    if (link && panel && window.fetch) {
      e.preventDefault();
      link.closest("details") && link.closest("details").removeAttribute("open");
      const url = new URL(link.href);
      url.searchParams.set("fragment", "1");
      try {
        const res = await fetch(url, { credentials: "same-origin" });
        if (!res.ok) throw new Error();
        body.innerHTML = await res.text();
        panel.hidden = false;
        url.searchParams.delete("fragment");
        history.replaceState(null, "", url);
        if (window.MondayRenderMath) window.MondayRenderMath(body);
      } catch (_) { window.location.href = link.href; }
      return;
    }
    if (e.target.closest("[data-panel-close]")) { e.preventDefault(); close(); return; }
    document.querySelectorAll("details.menu[open]").forEach((d) => { if (!d.contains(e.target)) d.removeAttribute("open"); });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    document.querySelectorAll("details.menu[open]").forEach((d) => d.removeAttribute("open"));
    if (panel && !panel.hidden) close();
  });
})();
