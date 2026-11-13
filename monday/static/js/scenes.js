/* Monday — rolling odometer countdown: days : hours : minutes : seconds. */
(function () {
  "use strict";
  const box = document.querySelector("[data-countdown][data-seconds]");
  if (!box) return;

  const end = Date.now() + Number(box.dataset.seconds) * 1000;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const units = {
    d: box.querySelector('[data-odo="d"]'),
    h: box.querySelector('[data-odo="h"]'),
    m: box.querySelector('[data-odo="m"]'),
    s: box.querySelector('[data-odo="s"]'),
  };
  const prev = { d: "", h: "", m: "", s: "" };
  const pad = (n) => String(n).padStart(2, "0");

  function setUnit(key, str) {
    const el = units[key];
    if (!el || prev[key] === str) return;
    const oldStr = prev[key];
    prev[key] = str;

    if (!oldStr || oldStr.length !== str.length || reduce) {
      el.innerHTML = "";
      for (const ch of str) {
        const slot = document.createElement("span");
        slot.className = "mhb-odo__slot";
        slot.innerHTML = `<span class="mhb-odo__reel"><span>${ch}</span></span>`;
        el.appendChild(slot);
      }
      return;
    }

    const slots = el.querySelectorAll(".mhb-odo__slot");
    for (let i = 0; i < str.length; i++) {
      if (oldStr[i] === str[i]) continue;
      const slot = slots[i];
      const reel = document.createElement("span");
      reel.className = "mhb-odo__reel is-rolling";
      reel.innerHTML = `<span>${str[i]}</span><span>${oldStr[i]}</span>`;
      reel.style.transform = "translateY(-50%)";
      slot.innerHTML = "";
      slot.appendChild(reel);
      requestAnimationFrame(() => {
        reel.style.transform = "translateY(0%)";
      });
    }
  }

  function tick() {
    const left = Math.max(0, Math.round((end - Date.now()) / 1000));
    setUnit("d", pad(Math.floor(left / 86400)));
    setUnit("h", pad(Math.floor((left % 86400) / 3600)));
    setUnit("m", pad(Math.floor((left % 3600) / 60)));
    setUnit("s", pad(left % 60));
    if (left === 0) {
      setTimeout(() => location.reload(), 1500);
      return;
    }
    setTimeout(tick, 1000 - (Date.now() % 1000));
  }

  tick();
})();
