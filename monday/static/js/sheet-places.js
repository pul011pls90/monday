/* Where a formula sheet shows: each switch saves on its own, so a test in progress never reloads. */
(() => {
  document.addEventListener("change", async (e) => {
    const box = e.target.closest("[data-sheet-place]");
    if (!box) return;
    const token = (document.querySelector("input[name=csrf_token]") || {}).value || "";
    const body = new URLSearchParams({ csrf_token: token, place: box.dataset.sheetPlace, on: box.checked ? "1" : "" });
    const sheet = box.closest("[data-sheet]");
    const show = () => sheet.classList.toggle("is-off", !sheet.querySelector("[data-sheet-place]:checked"));
    show();
    try {
      const res = await fetch(box.dataset.url, { method: "POST", body, headers: { "X-CSRFToken": token }, credentials: "same-origin" });
      if (!res.ok) throw new Error(res.status);
    } catch (_) {
      box.checked = !box.checked;   // not saved: show the real state
      show();
    }
  });
})();
