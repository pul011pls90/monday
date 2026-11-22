/* Monday — Admin Analytics Dashboard JS */
(function () {
  "use strict";

  const root = document.querySelector("[data-analytics-root]");
  if (!root) return;

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
  const currentUserId = parseInt(root.dataset.currentUserId || "0", 10);

  const URLS = {
    summary: root.dataset.summaryUrl,
    visits: root.dataset.visitsUrl,
    live: root.dataset.liveUrl,
    exportCsv: root.dataset.exportUrl,
    userTpl: root.dataset.userUrlTpl,
    visitTpl: root.dataset.visitUrlTpl,
    blockTpl: root.dataset.blockUrlTpl,
  };

  const state = {
    mainTab: "overview",
    chartDays: 30,
    kind: "all",
    liveKind: "all",
    page: 1,
    perPage: 25,
    chartInstance: null,
    lastChartData: null,
    liveTimer: null,
  };

  const esc = (v) =>
    String(v ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const fmtDuration = (sec) => {
    const s = Math.max(0, Math.round(Number(sec) || 0));
    if (s < 60) return `${s} с`;
    const m = Math.floor(s / 60);
    const rem = s % 60;
    if (m < 60) return `${m} м ${rem ? rem + " с" : ""}`.trim();
    const h = Math.floor(m / 60);
    return `${h} ч ${m % 60} м`;
  };

  const fmtDateTime = (iso) => {
    if (!iso) return "—";
    const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const cssVar = (name, fallback) => {
    const val = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return val || fallback;
  };

  const updateKpis = (kpis) => {
    if (!kpis) return;
    Object.entries(kpis).forEach(([k, v]) => {
      root.querySelectorAll(`[data-kpi="${k}"]`).forEach((el) => {
        el.textContent = String(v);
      });
    });
  };

  /* ------------------------------------------------------------ Charts */
  const drawFallbackLineChart = (canvas, series) => {
    const rect = canvas.parentElement.getBoundingClientRect();
    const w = Math.max(300, Math.floor(rect.width || 560));
    const h = 230;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const padL = 36, padR = 14, padT = 16, padB = 28;
    const pw = w - padL - padR;
    const ph = h - padT - padB;
    const maxY = Math.max(1, ...series.map((d) => d.visits));
    const accent = cssVar("--accent", "#1F4FE0");
    const okColor = cssVar("--ok", "#1E8E5A");
    const lineColor = cssVar("--line", "#E4E4E1");
    const muted = cssVar("--muted", "#5E5E5E");

    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 1;
    ctx.fillStyle = muted;
    ctx.font = "11px sans-serif";
    for (let i = 0; i <= 4; i++) {
      const y = padT + (ph * i) / 4;
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(w - padR, y);
      ctx.stroke();
      const val = Math.round(maxY * (1 - i / 4));
      ctx.fillText(String(val), 4, y + 4);
    }

    const plotLine = (vals, color) => {
      if (!vals.length) return;
      ctx.strokeStyle = color;
      ctx.lineWidth = 2.5;
      ctx.beginPath();
      vals.forEach((v, idx) => {
        const x = padL + (vals.length === 1 ? pw / 2 : (pw * idx) / (vals.length - 1));
        const y = padT + ph * (1 - v / maxY);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
    };

    plotLine(series.map((d) => d.visits), accent);
    plotLine(series.map((d) => d.unique_visitors), okColor);

    if (series.length) {
      ctx.fillStyle = muted;
      ctx.fillText(series[0].label, padL, h - 8);
      if (series.length > 2) {
        const mid = series[Math.floor(series.length / 2)];
        ctx.fillText(mid.label, padL + pw / 2 - 14, h - 8);
      }
      ctx.fillText(series[series.length - 1].label, w - padR - 32, h - 8);
    }
  };

  const renderDailyChart = (series) => {
    state.lastChartData = series;
    const canvas = document.getElementById("an-daily-chart");
    if (!canvas) return;

    if (typeof window.Chart !== "function") {
      drawFallbackLineChart(canvas, series);
      return;
    }

    const accent = cssVar("--accent", "#1F4FE0");
    const okColor = cssVar("--ok", "#1E8E5A");
    const gridColor = cssVar("--line", "#E4E4E1");
    const tickColor = cssVar("--muted", "#5E5E5E");

    if (state.chartInstance) {
      state.chartInstance.destroy();
      state.chartInstance = null;
    }

    state.chartInstance = new window.Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels: series.map((d) => d.label),
        datasets: [
          {
            label: "Визиты",
            data: series.map((d) => d.visits),
            borderColor: accent,
            backgroundColor: accent + "22",
            borderWidth: 2.5,
            tension: 0.3,
            fill: true,
            pointRadius: series.length > 35 ? 1.5 : 3,
            pointHoverRadius: 5,
          },
          {
            label: "Уникальные",
            data: series.map((d) => d.unique_visitors),
            borderColor: okColor,
            backgroundColor: "transparent",
            borderWidth: 2,
            borderDash: [4, 3],
            tension: 0.3,
            pointRadius: series.length > 35 ? 1 : 2.5,
            pointHoverRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            position: "top",
            align: "end",
            labels: { color: tickColor, boxWidth: 12, font: { size: 12, weight: "600" } },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: tickColor, maxTicksLimit: 10, font: { size: 11 } },
          },
          y: {
            beginAtZero: true,
            grid: { color: gridColor },
            ticks: { color: tickColor, precision: 0, font: { size: 11 } },
          },
        },
      },
    });
  };

  const renderHeatmap = (hm) => {
    const host = root.querySelector("[data-heatmap]");
    if (!host || !hm || !hm.matrix) return;
    const peak = Math.max(1, hm.peak || 1);

    let html = "";
    hm.matrix.forEach((row, dIdx) => {
      html += `<div class="an-hm-row"><span class="an-hm-day">${esc(hm.days[dIdx])}</span>`;
      row.forEach((val, hour) => {
        const ratio = val / peak;
        let bg = "var(--surface-2)";
        if (val > 0) {
          const pct = Math.max(18, Math.round(ratio * 100));
          bg = `color-mix(in srgb, var(--accent) ${pct}%, var(--surface))`;
        }
        const hLabel = `${String(hour).padStart(2, "0")}:00`;
        html += `<span class="an-hm-cell" style="background:${bg}" title="${esc(hm.days[dIdx])} ${hLabel} · ${val} виз."></span>`;
      });
      html += "</div>";
    });

    html += '<div class="an-hm-hours"><span></span>';
    for (let h = 0; h < 24; h++) {
      html += `<span>${h % 3 === 0 ? h : ""}</span>`;
    }
    html += "</div>";
    host.innerHTML = html;
  };

  const loadSummary = async () => {
    const params = new URLSearchParams({ days: String(state.chartDays) });
    const res = await fetch(`${URLS.summary}?${params}`, { credentials: "same-origin" });
    if (!res.ok) return;
    const data = await res.json();
    updateKpis(data.kpis);
    if (data.charts) {
      renderDailyChart(data.charts.daily_series || []);
      renderHeatmap(data.charts.heatmap);
      const lbl = root.querySelector("[data-chart-range-label]");
      if (lbl) lbl.textContent = `За последние ${state.chartDays} дней`;
    }
  };

  /* ------------------------------------------------------------ Filter + Data Grid */
  const collectFilterParams = (includePage = true) => {
    const form = root.querySelector("[data-filter-form]");
    const p = new URLSearchParams();
    p.set("kind", state.kind);
    if (form) {
      new FormData(form).forEach((val, key) => {
        const v = String(val || "").trim();
        if (v) p.set(key, v);
      });
    }
    if (includePage) {
      p.set("page", String(state.page));
      p.set("per_page", String(state.perPage));
    }
    return p;
  };

  const updateExportHref = () => {
    const a = root.querySelector("[data-export-link]");
    if (a) a.href = `${URLS.exportCsv}?${collectFilterParams(false).toString()}`;
  };

  const renderVisitsTable = (data) => {
    const tbody = root.querySelector("[data-visits-body]");
    const meta = root.querySelector("[data-visits-meta]");
    const pager = root.querySelector("[data-visits-pager]");
    if (!tbody) return;

    const items = data.items || [];
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="small muted" style="text-align:center;padding:28px">Пока нет визитов по выбранным фильтрам. Визиты фиксируются для учеников, учителей, ассистентов и гостей (админы не учитываются).</td></tr>';
    } else {
      tbody.innerHTML = items
        .map((it) => {
          const geo = [it.country, it.city].filter(Boolean).join(", ") || it.region || "—";
          const dev = [it.device_type, it.os, it.browser].filter(Boolean).join(" · ");
          const roleBadge = !it.is_anonymous
            ? `<span class="an-pill">${esc(it.role)}</span>`
            : `<span class="an-pill">Аноним</span>`;
          const examBadge = it.exam ? `<span class="an-pill an-pill--accent">${esc(it.exam)}</span>` : "";
          const blkBadge = it.is_blocked ? `<span class="an-pill an-pill--bad">блок</span>` : "";
          const onlineDot = it.is_online ? '<span class="an-live-dot" title="Онлайн сейчас"></span>' : "";
          const rowAttr = it.user_id ? `data-open-user="${it.user_id}"` : `data-open-visit="${esc(it.visit_id)}"`;

          return `<tr ${rowAttr} class="${it.is_blocked ? "is-blocked" : ""}">
            <td>
              <div class="an-who">
                <span class="avatar avatar--sm">${esc(it.user_initials || "?")}</span>
                <div class="an-who__meta">
                  <span class="an-who__name">${onlineDot}${esc(it.user_name)} ${roleBadge} ${examBadge} ${blkBadge}</span>
                  <span class="an-who__sub">${esc(it.user_email || `cookie:${it.session_cookie_id}`)}</span>
                </div>
              </div>
            </td>
            <td>${esc(geo)}</td>
            <td class="small">${esc(dev || "—")}</td>
            <td class="small num">${esc(fmtDateTime(it.started_at))}</td>
            <td class="num">${esc(fmtDuration(it.duration_seconds))}</td>
            <td><span class="an-pill num">${it.page_count}</span></td>
          </tr>`;
        })
        .join("");
    }

    if (meta) {
      meta.textContent = `Всего визитов: ${data.total} · стр. ${data.page} из ${data.pages}`;
    }
    if (pager) {
      const btns = [];
      if (data.page > 1) {
        btns.push(`<button type="button" class="btn btn--secondary btn--sm" data-page="${data.page - 1}">← Назад</button>`);
      }
      if (data.page < data.pages) {
        btns.push(`<button type="button" class="btn btn--secondary btn--sm" data-page="${data.page + 1}">Вперёд →</button>`);
      }
      pager.innerHTML = btns.join("");
    }
  };

  const loadVisits = async () => {
    updateExportHref();
    const params = collectFilterParams(true);
    const res = await fetch(`${URLS.visits}?${params}`, { credentials: "same-origin" });
    if (!res.ok) return;
    const data = await res.json();
    renderVisitsTable(data);
  };

  /* ------------------------------------------------------------ Live Feed */
  const loadLiveFeed = async () => {
    const params = new URLSearchParams({ limit: "40", kind: state.liveKind });
    const res = await fetch(`${URLS.live}?${params}`, { credentials: "same-origin" });
    if (!res.ok) return;
    const data = await res.json();
    updateKpis(data.kpis);

    const list = root.querySelector("[data-live-list]");
    if (!list) return;
    const items = data.items || [];
    if (!items.length) {
      list.innerHTML = '<p class="small muted">Пока нет зафиксированных визитов.</p>';
      return;
    }

    list.innerHTML = items
      .map((it) => {
        const geo = [it.country, it.city].filter(Boolean).join(", ") || "—";
        const dev = [it.device_type, it.browser].filter(Boolean).join(" · ");
        const statusPill = it.is_online
          ? '<span class="an-pill an-pill--ok"><span class="an-live-dot"></span>Онлайн</span>'
          : `<span class="small muted num">${esc(fmtDateTime(it.ended_at))}</span>`;
        const rowAttr = it.user_id ? `data-open-user="${it.user_id}"` : `data-open-visit="${esc(it.visit_id)}"`;

        return `<article class="an-feed__row" ${rowAttr}>
          <div class="an-who">
            <span class="avatar avatar--sm">${esc(it.user_initials || "?")}</span>
            <div class="an-who__meta">
              <span class="an-who__name">${esc(it.user_name)} ${it.exam ? `<span class="an-pill an-pill--accent">${esc(it.exam)}</span>` : ""}</span>
              <span class="an-who__sub">${esc(it.user_email || `Аноним (${it.session_cookie_id})`)}</span>
            </div>
          </div>
          <span class="an-path-badge an-feed__path" title="${esc(it.last_path)}">${esc(it.last_path || "/")}</span>
          <span class="small an-feed__geo">${esc(geo)}</span>
          <span class="small muted an-feed__dev">${esc(dev)}</span>
          <div>${statusPill}</div>
        </article>`;
      })
      .join("");
  };

  /* ------------------------------------------------------------ Slide-out Drawer */
  const drawer = document.querySelector("[data-an-drawer]");
  const drawerTitle = drawer?.querySelector("[data-drawer-title]");
  const drawerBody = drawer?.querySelector("[data-drawer-body]");

  const closeDrawer = () => {
    if (drawer) drawer.hidden = true;
  };

  const renderTimeline = (visits) => {
    if (!visits || !visits.length) {
      return '<p class="small muted">Визитов пока нет.</p>';
    }
    return `<div class="an-timeline">${visits
      .map((v) => {
        const geo = [v.country, v.city].filter(Boolean).join(", ") || "—";
        const dev = [v.device_type, v.os, v.browser].filter(Boolean).join(" · ");
        const pagesHtml = (v.pages || [])
          .map(
            (pg) => `<li>
              <code title="${esc(pg.path)}">${esc(pg.path)}</code>
              <span class="small muted num">${pg.time_spent_seconds ? fmtDuration(pg.time_spent_seconds) : fmtDateTime(pg.created_at)}</span>
            </li>`
          )
          .join("");
        return `<div class="an-tl-visit">
          <div class="an-tl-visit__head">
            <b class="num">${esc(fmtDateTime(v.started_at))}</b>
            <span class="small muted">${esc(geo)} · ${esc(dev)} · ${esc(fmtDuration(v.duration_seconds))}</span>
          </div>
          ${v.referer ? `<div class="small muted" style="word-break:break-all">Источник: ${esc(v.referer)}</div>` : ""}
          ${pagesHtml ? `<ul class="an-tl-pages">${pagesHtml}</ul>` : ""}
        </div>`;
      })
      .join("")}</div>`;
  };

  const openUserDrawer = async (userId) => {
    if (!drawer || !drawerBody) return;
    drawerTitle.textContent = "Профиль и визиты";
    drawerBody.innerHTML = '<p class="small muted">Загрузка карточки…</p>';
    drawer.hidden = false;

    const url = URLS.userTpl.replace(/0$/, String(userId));
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) {
      drawerBody.innerHTML = '<p class="small muted">Не удалось загрузить профиль.</p>';
      return;
    }
    const d = await res.json();
    const p = d.profile;
    const l = d.learning;
    const isSelf = p.id === currentUserId;

    drawerBody.innerHTML = `<div class="person">
      <div class="person__head">
        <span class="avatar avatar--lg">${esc(p.initials)}</span>
        <div class="stack-sm" style="gap:4px;min-width:0">
          <b class="person__name">${esc(p.name)}</b>
          <span class="small muted">${esc(p.email)}</span>
          <div class="chips">
            <span class="tag tag--soft">${esc(p.role)}</span>
            ${p.exam ? `<span class="tag tag--line">${esc(p.exam)}</span>` : ""}
            ${p.is_blocked ? '<span class="tag tag--bad" data-drawer-blk-tag>заблокирован</span>' : ""}
          </div>
        </div>
      </div>

      <dl class="kv small">
        <dt>Школа</dt><dd>${esc(p.school || "—")}</dd>
        <dt>Класс</dt><dd>${esc(p.grade || "—")}</dd>
        <dt>Экзамен</dt><dd>${esc(p.exam || "—")}${p.goal_score ? ` · цель ${esc(p.goal_score)}` : ""}</dd>
        <dt>Регион</dt><dd>${esc([p.country, p.region].filter(Boolean).join(", ") || "—")}</dd>
        <dt>Учитель</dt><dd>${esc((p.teachers || []).join(", ") || "—")}</dd>
        <dt>Визиты</dt><dd class="num">${p.total_visits} · ср. ${esc(fmtDuration(p.average_visit_duration))}</dd>
        <dt>Входы</dt><dd class="num">${p.login_count || 0} (${p.auth_provider === "google" ? "Google" : "Email / пароль"})</dd>
        ${p.recent_logins && p.recent_logins.length ? `<dt>Посл. устройство</dt><dd>${esc([p.recent_logins[0].device_type, p.recent_logins[0].os, p.recent_logins[0].browser].filter(Boolean).join(" · "))} · ${esc(fmtDateTime(p.recent_logins[0].created_at))}</dd>` : ""}
      </dl>

      <div class="person__nums">
        <div><b class="num">${l.attempts_count}</b><span class="small muted">попыток</span></div>
        <div><b class="num">${l.answered_questions}</b><span class="small muted">ответов</span></div>
        <div><b class="num">${l.accuracy_pct}%</b><span class="small muted">точность</span></div>
      </div>
      <div class="person__nums">
        <div><b class="num">${l.streak_days}</b><span class="small muted">серия дней</span></div>
        <div><b class="num">${l.mastery_pct !== null ? l.mastery_pct + "%" : "—"}</b><span class="small muted">освоено</span></div>
        <div><b class="num">${l.predicted !== null ? l.predicted : "—"}</b><span class="small muted">прогноз</span></div>
      </div>

      ${!isSelf ? `<section class="stack-sm">
        <h3 class="eyebrow">Действия</h3>
        <button type="button" class="btn ${p.is_blocked ? "btn--secondary" : "btn--danger-line"}" data-toggle-block data-user-id="${p.id}" data-blocked="${p.is_blocked ? "1" : "0"}">
          ${p.is_blocked ? "Разблокировать пользователя" : "Заблокировать пользователя"}
        </button>
      </section>` : ""}

      <section class="stack-sm">
        <h3 class="eyebrow">Хронология визитов и страниц</h3>
        ${renderTimeline(d.timeline)}
      </section>
    </div>`;
  };

  const openVisitDrawer = async (visitId) => {
    if (!drawer || !drawerBody) return;
    drawerTitle.textContent = "Анонимный визит";
    drawerBody.innerHTML = '<p class="small muted">Загрузка визита…</p>';
    drawer.hidden = false;

    const url = URLS.visitTpl.replace("__VID__", encodeURIComponent(visitId));
    const res = await fetch(url, { credentials: "same-origin" });
    if (!res.ok) {
      drawerBody.innerHTML = '<p class="small muted">Не удалось загрузить визит.</p>';
      return;
    }
    const d = await res.json();
    if (d.kind === "user" && d.profile) {
      return openUserDrawer(d.profile.id);
    }
    const v = d.visit;
    drawerBody.innerHTML = `<div class="person">
      <div class="person__head">
        <span class="avatar avatar--lg">?</span>
        <div class="stack-sm" style="gap:4px">
          <b class="person__name">Анонимный посетитель</b>
          <span class="small muted">Cookie ID: ${esc(v.session_cookie_id)}</span>
        </div>
      </div>
      <dl class="kv small">
        <dt>Локация</dt><dd>${esc([v.country, v.city].filter(Boolean).join(", ") || "—")}</dd>
        <dt>Устройство</dt><dd>${esc([v.device_type, v.os, v.browser].filter(Boolean).join(" · "))}</dd>
        <dt>Язык</dt><dd>${esc(v.language || "—")}</dd>
        <dt>Длительность</dt><dd class="num">${esc(fmtDuration(v.duration_seconds))} (${v.page_count} стр.)</dd>
        <dt>Источник</dt><dd style="word-break:break-all">${esc(v.referer || "Прямой заход")}</dd>
      </dl>
      <section class="stack-sm">
        <h3 class="eyebrow">Просмотренные страницы</h3>
        ${renderTimeline([{ ...v, pages: d.pages }])}
      </section>
    </div>`;
  };

  /* ------------------------------------------------------------ Event Wiring */
  root.querySelectorAll("[data-main-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.mainTab = btn.dataset.mainTab;
      root.querySelectorAll("[data-main-tab]").forEach((b) => {
        const on = b === btn;
        b.classList.toggle("is-active", on);
        b.setAttribute("aria-selected", String(on));
      });
      root.querySelectorAll("[data-tab-pane]").forEach((p) => {
        p.hidden = p.dataset.tabPane !== state.mainTab;
      });
      if (state.mainTab === "live") {
        loadLiveFeed();
        if (!state.liveTimer) {
          state.liveTimer = setInterval(() => {
            if (!document.hidden && state.mainTab === "live") loadLiveFeed();
          }, 5000);
        }
      } else if (state.liveTimer) {
        clearInterval(state.liveTimer);
        state.liveTimer = null;
      }
    });
  });

  root.querySelectorAll("[data-chart-days]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.chartDays = parseInt(btn.dataset.chartDays, 10) || 30;
      root.querySelectorAll("[data-chart-days]").forEach((b) => b.classList.toggle("is-active", b === btn));
      loadSummary();
    });
  });

  root.querySelectorAll("[data-kind-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.kind = btn.dataset.kindTab;
      state.page = 1;
      root.querySelectorAll("[data-kind-tab]").forEach((b) => b.classList.toggle("is-active", b === btn));
      loadVisits();
    });
  });

  root.querySelectorAll("[data-live-kind]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.liveKind = btn.dataset.liveKind;
      root.querySelectorAll("[data-live-kind]").forEach((b) => b.classList.toggle("is-active", b === btn));
      loadLiveFeed();
    });
  });

  root.querySelector("[data-live-refresh]")?.addEventListener("click", loadLiveFeed);

  let searchTimer = null;
  root.querySelectorAll("[data-filter-input]").forEach((el) => {
    const evt = el.tagName === "INPUT" && el.type === "search" ? "input" : "change";
    el.addEventListener(evt, () => {
      state.page = 1;
      if (evt === "input") {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(loadVisits, 250);
      } else {
        loadVisits();
      }
    });
  });

  root.querySelector("[data-filter-reset]")?.addEventListener("click", () => {
    root.querySelector("[data-filter-form]")?.reset();
    state.kind = "all";
    state.page = 1;
    root.querySelectorAll("[data-kind-tab]").forEach((b) => b.classList.toggle("is-active", b.dataset.kindTab === "all"));
    loadVisits();
  });

  const handleClick = async (e) => {
    const pagerBtn = e.target.closest("[data-page]");
    if (pagerBtn) {
      state.page = parseInt(pagerBtn.dataset.page, 10) || 1;
      loadVisits();
      return;
    }
    const blkBtn = e.target.closest("[data-toggle-block]");
    if (blkBtn) {
      const uid = blkBtn.dataset.userId;
      const nextBlocked = blkBtn.dataset.blocked !== "1";
      blkBtn.disabled = true;
      try {
        const res = await fetch(URLS.blockTpl.replace(/\/0\/block$/, `/${encodeURIComponent(uid)}/block`), {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
          body: JSON.stringify({ blocked: nextBlocked }),
        });
        if (res.ok) {
          await openUserDrawer(uid);
          loadVisits();
        }
      } finally {
        blkBtn.disabled = false;
      }
      return;
    }
    if (e.target.closest("[data-drawer-close]")) {
      closeDrawer();
      return;
    }
    const userRow = e.target.closest("[data-open-user]");
    if (userRow) {
      openUserDrawer(userRow.dataset.openUser);
      return;
    }
    const visitRow = e.target.closest("[data-open-visit]");
    if (visitRow) {
      openVisitDrawer(visitRow.dataset.openVisit);
    }
  };
  root.addEventListener("click", handleClick);
  if (drawer && !root.contains(drawer)) {
    drawer.addEventListener("click", handleClick);
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drawer && !drawer.hidden) closeDrawer();
  });

  // Re-theme Chart.js seamlessly when light/dark theme flips
  new MutationObserver(() => {
    if (state.lastChartData) renderDailyChart(state.lastChartData);
  }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  loadSummary();
  loadVisits();
})();
