/* Monday — Support attachments UI: picker, clipboard paste, drag-and-drop, canvas pre-resize, progress, lightbox. */
(function () {
  "use strict";

  const form = document.querySelector("[data-sup-form]");
  if (!form) return;

  const MAX_FILES = 3;
  const MAX_RAW_BYTES = 10 * 1024 * 1024;
  const MAX_TOTAL_BYTES = 5 * 1024 * 1024;
  const MAX_SIDE = 1600;
  const ALLOWED_MIMES = new Set(["image/jpeg", "image/png", "image/webp"]);
  const ALLOWED_EXT_RE = /\.(?:jpe?g|png|webp)$/i;
  const BLOCKED_EXT_RE = /\.(?:svgz?|gif|heic|heif|pdf|html?|txt|exe)$/i;

  const fileInput = form.querySelector("[data-sup-input]");
  const pickBtn = form.querySelector("[data-sup-pick]");
  const dropZone = form.querySelector("[data-sup-drop]");
  const previewsList = form.querySelector("[data-sup-previews]");
  const errorBox = form.querySelector("[data-sup-error]");
  const progressBox = form.querySelector("[data-sup-progress]");
  const progressBar = form.querySelector("[data-sup-bar]");
  const progressText = form.querySelector("[data-sup-progress-text]");
  const countEl = form.querySelector("[data-sup-count]");
  const msgInput = form.querySelector("#sup-message");
  const submitBtn = form.querySelector("[data-sup-submit]");

  /** @type {{id: number, blob: Blob, name: string, previewUrl: string}[]} */
  let queue = [];
  let nextId = 1;
  let busy = false;

  function showError(msg) {
    if (!errorBox) return;
    if (!msg) {
      errorBox.textContent = "";
      errorBox.hidden = true;
      return;
    }
    errorBox.textContent = msg;
    errorBox.hidden = false;
  }

  function formatKb(bytes) {
    if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " МБ";
    return Math.max(1, Math.round(bytes / 1024)) + " КБ";
  }

  function totalQueuedBytes() {
    return queue.reduce((sum, item) => sum + item.blob.size, 0);
  }

  function syncCounter() {
    if (countEl) {
      countEl.textContent = queue.length ? `${queue.length} / ${MAX_FILES}` : "";
      countEl.hidden = queue.length === 0;
    }
  }

  function renderPreviews() {
    if (!previewsList) return;
    previewsList.innerHTML = "";
    previewsList.hidden = queue.length === 0;
    syncCounter();

    queue.forEach((item, idx) => {
      const li = document.createElement("li");
      li.className = "sup-preview";

      const thumbBtn = document.createElement("button");
      thumbBtn.type = "button";
      thumbBtn.className = "sup-preview__thumb";
      thumbBtn.setAttribute("aria-label", `Просмотреть изображение ${idx + 1}`);
      thumbBtn.setAttribute("data-lightbox-trigger", "");

      const img = document.createElement("img");
      img.src = item.previewUrl;
      img.alt = `Вложение ${idx + 1}`;
      img.setAttribute("data-lightbox", "");
      img.setAttribute("data-lightbox-src", item.previewUrl);
      thumbBtn.appendChild(img);

      const meta = document.createElement("span");
      meta.className = "sup-preview__meta";
      meta.textContent = formatKb(item.blob.size);

      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "sup-preview__remove";
      removeBtn.setAttribute("aria-label", `Удалить изображение ${idx + 1}`);
      removeBtn.textContent = "×";
      removeBtn.addEventListener("click", () => {
        URL.revokeObjectURL(item.previewUrl);
        queue = queue.filter((q) => q.id !== item.id);
        showError("");
        renderPreviews();
      });

      li.appendChild(thumbBtn);
      li.appendChild(meta);
      li.appendChild(removeBtn);
      previewsList.appendChild(li);
    });
  }

  function isSupportedImageFile(file) {
    if (!file) return false;
    const type = String(file.type || "").toLowerCase();
    const name = String(file.name || "");
    if (BLOCKED_EXT_RE.test(name)) return false;
    if (type) {
      return ALLOWED_MIMES.has(type);
    }
    return ALLOWED_EXT_RE.test(name);
  }

  function canvasPreResize(file) {
    return new Promise((resolve) => {
      const objUrl = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        try {
          const w = img.naturalWidth || img.width;
          const h = img.naturalHeight || img.height;
          if (!w || !h) {
            URL.revokeObjectURL(objUrl);
            resolve(file);
            return;
          }
          const maxDim = Math.max(w, h);
          const scale = maxDim > MAX_SIDE ? MAX_SIDE / maxDim : 1;
          const tw = Math.max(1, Math.round(w * scale));
          const th = Math.max(1, Math.round(h * scale));

          const canvas = document.createElement("canvas");
          canvas.width = tw;
          canvas.height = th;
          const ctx = canvas.getContext("2d");
          if (!ctx) {
            URL.revokeObjectURL(objUrl);
            resolve(file);
            return;
          }
          ctx.drawImage(img, 0, 0, tw, th);
          canvas.toBlob(
            (webpBlob) => {
              URL.revokeObjectURL(objUrl);
              if (webpBlob && (scale < 1 || webpBlob.size < file.size)) {
                resolve(webpBlob);
              } else {
                resolve(file);
              }
            },
            "image/webp",
            0.85
          );
        } catch (_e) {
          URL.revokeObjectURL(objUrl);
          resolve(file);
        }
      };
      img.onerror = () => {
        URL.revokeObjectURL(objUrl);
        resolve(file);
      };
      img.src = objUrl;
    });
  }

  async function addFiles(fileList) {
    const incoming = Array.from(fileList || []).filter(Boolean);
    if (!incoming.length) return;
    showError("");

    for (const file of incoming) {
      if (queue.length >= MAX_FILES) {
        showError(`Можно прикрепить не более ${MAX_FILES} изображений к одному сообщению.`);
        break;
      }
      if (!isSupportedImageFile(file)) {
        showError("Поддерживаются только изображения JPEG, PNG и WebP (SVG и GIF не поддерживаются).");
        continue;
      }
      if (file.size > MAX_RAW_BYTES) {
        showError("Файл слишком большой (максимум 10 МБ).");
        continue;
      }
      const processedBlob = await canvasPreResize(file);
      if (totalQueuedBytes() + processedBlob.size > MAX_TOTAL_BYTES) {
        showError("Общий размер вложений превышает 5 МБ.");
        continue;
      }
      const outName = `image-${nextId}.webp`;
      queue.push({
        id: nextId++,
        blob: processedBlob,
        name: outName,
        previewUrl: URL.createObjectURL(processedBlob),
      });
    }
    renderPreviews();
  }

  pickBtn?.addEventListener("click", () => {
    if (busy || !fileInput) return;
    fileInput.value = "";
    fileInput.click();
  });

  fileInput?.addEventListener("change", () => {
    if (fileInput.files && fileInput.files.length) {
      addFiles(fileInput.files);
    }
  });

  // Drag-and-drop
  if (dropZone) {
    ["dragenter", "dragover"].forEach((evName) => {
      dropZone.addEventListener(evName, (e) => {
        e.preventDefault();
        dropZone.classList.add("is-dragover");
      });
    });
    ["dragleave", "dragend"].forEach((evName) => {
      dropZone.addEventListener(evName, (e) => {
        if (e.target === dropZone || !dropZone.contains(e.relatedTarget)) {
          dropZone.classList.remove("is-dragover");
        }
      });
    });
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("is-dragover");
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
        addFiles(e.dataTransfer.files);
      }
    });
  }

  // Clipboard paste (Ctrl/Cmd+V screenshot) anywhere on support form/page
  document.addEventListener("paste", (e) => {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items || !items.length) return;
    const files = [];
    for (const item of items) {
      if (item.kind === "file" && String(item.type || "").startsWith("image/")) {
        const f = item.getAsFile();
        if (f) files.push(f);
      }
    }
    if (files.length) {
      e.preventDefault();
      addFiles(files);
    }
  });

  function setProgress(active, pct, label) {
    if (!progressBox) return;
    progressBox.hidden = !active;
    if (progressBar) progressBar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    if (progressText) progressText.textContent = label || "";
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    if (busy) return;
    showError("");

    const msgVal = (msgInput ? msgInput.value : "").trim();
    if (!msgVal && queue.length === 0) {
      showError("Опишите ваш вопрос или прикрепите изображение.");
      msgInput?.focus();
      return;
    }
    if (queue.length > MAX_FILES) {
      showError(`Можно прикрепить не более ${MAX_FILES} изображений к одному сообщению.`);
      return;
    }
    if (totalQueuedBytes() > MAX_TOTAL_BYTES) {
      showError("Общий размер вложений превышает 5 МБ.");
      return;
    }

    const fd = new FormData();
    const csrf = form.querySelector('input[name="csrf_token"]');
    const subj = form.querySelector('[name="subject"]');
    if (csrf) fd.append("csrf_token", csrf.value);
    if (subj) fd.append("subject", subj.value);
    fd.append("message", msgInput ? msgInput.value : "");
    queue.forEach((item) => {
      fd.append("images", item.blob, item.name);
    });

    busy = true;
    if (submitBtn) submitBtn.disabled = true;
    setProgress(true, queue.length ? 5 : 50, queue.length ? "Загрузка… 5%" : "Отправка…");

    const xhr = new XMLHttpRequest();
    xhr.open("POST", form.action, true);
    xhr.setRequestHeader("X-Requested-With", "fetch");
    xhr.setRequestHeader("Accept", "application/json");

    xhr.upload.addEventListener("progress", (ev) => {
      if (!ev.lengthComputable) return;
      const pct = Math.min(99, Math.max(5, Math.round((ev.loaded / ev.total) * 100)));
      setProgress(true, pct, `Загрузка… ${pct}%`);
    });

    xhr.onload = () => {
      busy = false;
      if (submitBtn) submitBtn.disabled = false;
      let payload = null;
      try {
        payload = JSON.parse(xhr.responseText || "{}");
      } catch (_e) {}

      if (xhr.status >= 200 && xhr.status < 300 && payload && payload.ok) {
        setProgress(true, 100, "Готово!");
        window.location.assign(payload.redirect || window.location.pathname);
        return;
      }
      setProgress(false, 0, "");
      if (xhr.status === 413) {
        showError((payload && payload.error) || "Общий размер запроса превышает 5 МБ.");
        return;
      }
      if (xhr.status === 429) {
        showError("Слишком много отправок. Попробуйте немного позже.");
        return;
      }
      showError((payload && payload.error) || "Не удалось отправить сообщение. Проверьте файлы и попробуйте снова.");
    };

    xhr.onerror = () => {
      busy = false;
      if (submitBtn) submitBtn.disabled = false;
      setProgress(false, 0, "");
      showError("Ошибка сети. Проверьте подключение и попробуйте снова.");
    };

    xhr.send(fd);
  });

  window.MondaySupport = {
    addFiles: addFiles,
    getQueueLength: () => queue.length,
    isSupportedImageFile: isSupportedImageFile,
  };
})();
