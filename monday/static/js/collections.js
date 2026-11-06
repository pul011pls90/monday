/* Сборники: the results follow the search box while typing. The page itself renders each result, so filters, sorting and
   the forgiving search work the same as after pressing Enter; only the parts marked data-live are swapped. */
(() => {
  const form = document.querySelector("form[role=search]");
  const input = form && form.querySelector("input[name=q]");
  if (!input) return;
  const WAIT = 220;
  let timer = null, running = null;

  const address = () => {
    const params = new URLSearchParams();
    new FormData(form).forEach((value, key) => { if (value) params.set(key, value); });
    const query = params.toString();
    return location.pathname + (query ? `?${query}` : "");
  };

  async function refresh() {
    if (running) running.abort();
    const mine = running = new AbortController();
    const url = address();
    try {
      const res = await fetch(url, { signal: mine.signal, headers: { "X-Requested-With": "fetch" } });
      if (!res.ok || res.redirected) { location.href = url; return; }   // e.g. the session ended: let the page handle it
      const next = new DOMParser().parseFromString(await res.text(), "text/html");
      document.querySelectorAll("[data-live]").forEach((part) => {
        const fresh = next.querySelector(`[data-live="${part.dataset.live}"]`);
        if (fresh) part.innerHTML = fresh.innerHTML;
      });
      history.replaceState(null, "", url);
    } catch (e) {
      if (e.name !== "AbortError") location.href = url;
    }
  }

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(refresh, WAIT);
  });
  form.addEventListener("submit", (e) => {   // Enter: same result, right away, and the cursor stays in the box
    e.preventDefault();
    clearTimeout(timer);
    refresh();
  });
})();
