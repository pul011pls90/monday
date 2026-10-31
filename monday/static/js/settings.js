/* Settings page: tabs remembered in the address (#profile, #exam, …) and choices that save as soon as they change. */
(() => {
  const tabs = [...document.querySelectorAll("[data-set-tab]")];
  const panes = [...document.querySelectorAll("[data-set-pane]")];
  if (!tabs.length) return;
  const show = (key) => {
    if (!panes.some((p) => p.dataset.setPane === key)) key = panes[0].dataset.setPane;
    panes.forEach((p) => { p.hidden = p.dataset.setPane !== key; });
    tabs.forEach((t) => {
      const on = t.dataset.setTab === key;
      t.classList.toggle("is-active", on);
      t.setAttribute("aria-selected", String(on));
    });
  };
  tabs.forEach((t) => t.addEventListener("click", (e) => {
    e.preventDefault();
    history.replaceState(null, "", "#" + t.dataset.setTab);
    show(t.dataset.setTab);
  }));
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));
  show(location.hash.slice(1));

  // theme, goal, days and switches: saved right away (days wait a moment so several can be ticked)
  document.querySelectorAll("form[data-autosave]").forEach((form) => {
    let timer;
    form.addEventListener("change", (e) => {
      clearTimeout(timer);
      const wait = e.target.type === "checkbox" && e.target.name === "study_days" ? 900 : 150;
      timer = setTimeout(() => form.requestSubmit ? form.requestSubmit() : form.submit(), wait);
    });
  });
})();
