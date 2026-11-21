/* Client-side display-only FX conversion for Finance & CRM pages (all DB writes stay in KGS). */
(function () {
  const STORAGE_KEY = "monday_display_currency";
  const CACHE_KEY = "monday_fx_rates_v1";
  const CACHE_TTL_MS = 15 * 60 * 1000;
  const CURRENCIES = ["KGS", "USD", "EUR", "KZT", "RUB"];
  const SYMBOLS = {
    KGS: "KGS",
    USD: "$",
    EUR: "€",
    KZT: "₸",
    RUB: "₽",
  };

  function getSavedCurrency() {
    try {
      const c = (localStorage.getItem(STORAGE_KEY) || "KGS").toUpperCase();
      return CURRENCIES.includes(c) ? c : "KGS";
    } catch (_) {
      return "KGS";
    }
  }

  function saveCurrency(cur) {
    try {
      localStorage.setItem(STORAGE_KEY, cur);
    } catch (_) {}
  }

  function formatInt(n) {
    return Math.round(n)
      .toString()
      .replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
  }

  function formatConverted(amountKgs, cur, rate) {
    const absVal = Math.abs(amountKgs) * rate;
    if (cur === "KGS") {
      return formatInt(Math.abs(amountKgs)) + " KGS";
    }
    let formatted;
    if (cur === "USD" || cur === "EUR") {
      formatted = absVal >= 1000
        ? formatInt(absVal)
        : absVal.toFixed(absVal >= 100 ? 1 : 2).replace(/\.00$/, "");
      return SYMBOLS[cur] + formatted;
    }
    formatted = formatInt(absVal);
    return formatted + " " + SYMBOLS[cur];
  }

  function readCachedRates() {
    try {
      const raw = sessionStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      const obj = JSON.parse(raw);
      if (!obj || !obj.data || !obj.data.rates || Date.now() - (obj.ts || 0) > CACHE_TTL_MS) return null;
      return obj.data;
    } catch (_) {
      return null;
    }
  }

  function writeCachedRates(data) {
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), data }));
    } catch (_) {}
  }

  async function loadRates(endpoint) {
    const cached = readCachedRates();
    if (cached) return cached;
    const resp = await fetch(endpoint, { credentials: "same-origin" });
    if (!resp.ok) throw new Error("FX fetch failed: " + resp.status);
    const data = await resp.json();
    if (!data || !data.rates) throw new Error("Invalid FX response");
    writeCachedRates(data);
    return data;
  }

  function syncButtons(cur) {
    document.querySelectorAll("[data-fx-currency]").forEach((btn) => {
      const active = btn.dataset.fxCurrency === cur;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function renderAmounts(cur, fxData) {
    const rate = cur === "KGS" ? 1 : Number((fxData && fxData.rates && fxData.rates[cur]) || 0);
    const badge = document.querySelector("[data-fx-badge]");
    if (badge) {
      if (cur === "KGS") {
        badge.hidden = true;
      } else {
        badge.hidden = false;
        const unitKgs = fxData && fxData.kgs_per_unit && fxData.kgs_per_unit[cur];
        const srcText = fxData && fxData.source === "NBKR" ? "Курс НБКР" : "Ориентировочный курс";
        badge.textContent = unitKgs
          ? `${srcText}: 1 ${cur} = ${Number(unitKgs).toFixed(2)} KGS`
          : srcText;
      }
    }

    document.querySelectorAll("[data-kgs-amount]").forEach((el) => {
      const raw = Number(el.dataset.kgsAmount);
      if (Number.isNaN(raw)) return;
      const prefix = el.dataset.kgsPrefix || "";
      const kgsFormatted = prefix + formatInt(Math.abs(raw)) + " KGS";
      if (cur === "KGS" || !rate) {
        el.textContent = kgsFormatted;
        el.removeAttribute("title");
        const nextHint = el.nextElementSibling;
        if (nextHint && nextHint.classList.contains("fx-kgs-hint")) {
          nextHint.remove();
        }
        return;
      }

      const converted = prefix + formatConverted(raw, cur, rate);
      el.textContent = converted;
      el.title = "≈ " + kgsFormatted;
      let hint = el.nextElementSibling;
      if (!hint || !hint.classList.contains("fx-kgs-hint")) {
        hint = document.createElement("small");
        hint.className = "fx-kgs-hint";
        el.insertAdjacentElement("afterend", hint);
      }
      hint.textContent = "≈ " + kgsFormatted;
    });
  }

  function initFinanceFx() {
    const switcher = document.querySelector("[data-fx-switcher]");
    if (!switcher) return;
    const endpoint = switcher.dataset.fxEndpoint || "/api/fx/rates";
    let currentRates = null;

    async function applyCurrency(cur) {
      if (!CURRENCIES.includes(cur)) cur = "KGS";
      saveCurrency(cur);
      syncButtons(cur);
      if (cur === "KGS") {
        renderAmounts("KGS", currentRates);
        return;
      }
      if (!currentRates) {
        try {
          currentRates = await loadRates(endpoint);
        } catch (_) {
          renderAmounts("KGS", null);
          return;
        }
      }
      renderAmounts(cur, currentRates);
    }

    switcher.querySelectorAll("[data-fx-currency]").forEach((btn) => {
      btn.addEventListener("click", () => applyCurrency(btn.dataset.fxCurrency));
    });

    applyCurrency(getSavedCurrency());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initFinanceFx);
  } else {
    initFinanceFx();
  }
})();
