/* Front-end logic: image selection/previews, validation, job polling. */
(() => {
  const cfg = window.APP_CONFIG;
  const $ = (s) => document.querySelector(s);
  const form = $("#property-form");
  const dropzone = $("#dropzone"), fileInput = $("#file-input"), replaceInput = $("#replace-input");
  const previews = $("#previews"), countEl = $("#image-count");
  const errorsEl = $("#errors"), genBtn = $("#generate");
  const emptyEl = $("#empty"), progressEl = $("#progress"), doneEl = $("#done");
  const barFill = $("#bar-fill"), progressMsg = $("#progress-msg");

  /** @type {File[]} */
  let files = [];
  let replaceIndex = null;
  let pollTimer = null;

  // ---------- helpers ----------
  const extOf = (name) => (name.includes(".") ? name.split(".").pop().toLowerCase() : "");
  const showErrors = (list) => {
    errorsEl.hidden = !list.length;
    if (!list.length) return;
    errorsEl.innerHTML = "<strong>Fix the following and try again:</strong><ul>" +
      list.map((e) => `<li>${e.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]))}</li>`).join("") + "</ul>";
    errorsEl.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  const checkFile = (f) => {
    if (!cfg.exts.includes(extOf(f.name))) return `'${f.name}' is not supported. Use JPG, JPEG or PNG.`;
    if (!["image/jpeg", "image/png"].includes(f.type)) return `'${f.name}' does not look like a JPG or PNG image.`;
    if (f.size > cfg.maxMB * 1024 * 1024) return `'${f.name}' is larger than ${cfg.maxMB} MB.`;
    if (f.size === 0) return `'${f.name}' is empty.`;
    return null;
  };

  // ---------- image list ----------
  function addFiles(list) {
    const problems = [];
    for (const f of list) {
      const err = checkFile(f);
      if (err) { problems.push(err); continue; }
      if (files.length >= cfg.max) { problems.push(`You can add at most ${cfg.max} photos. Remove one to add another.`); break; }
      files.push(f);
    }
    showErrors([...new Set(problems)]);
    renderPreviews();
  }

  function renderPreviews() {
    previews.innerHTML = "";
    files.forEach((f, i) => {
      const li = document.createElement("li");
      const url = URL.createObjectURL(f);
      li.innerHTML = `<span class="num">${i + 1}</span><img alt="Photo ${i + 1} preview" src="${url}">` +
        `<div class="cap"><span title="${f.name.replace(/"/g, "")}">${f.name.replace(/[<>&"]/g, "")}</span>` +
        `<span><button type="button" class="replace" data-i="${i}">Replace</button> ` +
        `<button type="button" class="remove" data-i="${i}">Remove</button></span></div>`;
      li.querySelector("img").onload = () => URL.revokeObjectURL(url);
      previews.appendChild(li);
    });
    const n = files.length;
    const ok = n >= cfg.min && n <= cfg.max;
    countEl.className = "count" + (ok ? " ok" : "");
    countEl.textContent = n === 0 ? "No photos added yet."
      : ok ? `${n} photos added. Ready.` : `${n} of at least ${cfg.min} photos added. Add ${cfg.min - n} more.`;
  }

  previews.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    const i = Number(b.dataset.i);
    if (b.classList.contains("remove")) { files.splice(i, 1); renderPreviews(); }
    else { replaceIndex = i; replaceInput.value = ""; replaceInput.click(); }
  });
  replaceInput.addEventListener("change", () => {
    const f = replaceInput.files[0];
    if (!f || replaceIndex === null) return;
    const err = checkFile(f);
    if (err) showErrors([err]); else { files[replaceIndex] = f; showErrors([]); renderPreviews(); }
    replaceIndex = null;
  });

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
  fileInput.addEventListener("click", (e) => e.stopPropagation());
  fileInput.addEventListener("change", () => { addFiles([...fileInput.files]); fileInput.value = ""; });
  ["dragenter", "dragover"].forEach((ev) => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("drag"); }));
  dropzone.addEventListener("drop", (e) => addFiles([...e.dataTransfer.files]));

  // ---------- sample (synthetic) data ----------
  $("#fill-sample").addEventListener("click", () => {
    const sample = {
      property_name: "Azure Heights Residency", location: "Lakeview Road, Sample City", price: "$385,000",
      property_type: "Apartment", bedrooms: "3", bathrooms: "2", area: "1850",
      features: "Covered parking\nRooftop garden\n24/7 security\nFitness studio",
      contact: "Sample Realty Team\n+00 000 000 0000\nhello@example.com", cta: "Book a private viewing",
    };
    for (const [k, v] of Object.entries(sample)) form.elements[k].value = v;
  });

  // ---------- submit ----------
  function validateClient() {
    const errs = [];
    form.querySelectorAll("[required]").forEach((el) => {
      const bad = !el.value.trim();
      el.classList.toggle("invalid", bad);
      if (bad) errs.push(`${el.closest("label").childNodes[0].textContent.trim()} is required.`);
    });
    if (files.length < cfg.min || files.length > cfg.max)
      errs.push(`Add between ${cfg.min} and ${cfg.max} photos (you have ${files.length}).`);
    return errs;
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const errs = validateClient();
    showErrors(errs);
    if (errs.length) return;

    const fd = new FormData(form);
    files.forEach((f) => fd.append("images", f, f.name));
    setBusy(true);
    try {
      const res = await fetch("/api/generate", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({ ok: false, errors: ["The server sent an unexpected reply."] }));
      if (!res.ok || !data.ok) { showErrors(data.errors || ["Could not start the video."]); setBusy(false); return; }
      poll(data.job_id);
    } catch (err) {
      showErrors(["Could not reach the server. Is the app still running?"]);
      setBusy(false);
    }
  });

  function setBusy(busy) {
    genBtn.disabled = busy;
    genBtn.textContent = busy ? "Rendering…" : "Generate video";
    emptyEl.hidden = busy || !doneEl.hidden;
    progressEl.hidden = !busy;
    if (busy) { doneEl.hidden = true; barFill.style.width = "2%"; progressMsg.textContent = "Starting…"; $("#result").scrollIntoView({ behavior: "smooth", block: "nearest" }); }
  }

  function poll(jobId) {
    clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      try {
        const res = await fetch(`/api/status/${jobId}`);
        if (!res.ok) throw new Error("status");
        const job = await res.json();
        barFill.style.width = `${Math.max(2, Math.round(job.progress * 100))}%`;
        progressMsg.textContent = job.message;
        if (job.status === "done") { clearInterval(pollTimer); finish(jobId, job); }
        else if (job.status === "error") { clearInterval(pollTimer); setBusy(false); emptyEl.hidden = false; showErrors([job.message]); }
      } catch {
        clearInterval(pollTimer); setBusy(false); emptyEl.hidden = false;
        showErrors(["Lost contact with the server while rendering."]);
      }
    }, 1000);
  }

  function finish(jobId, job) {
    setBusy(false);
    emptyEl.hidden = true; progressEl.hidden = true; doneEl.hidden = false;
    $("#player").src = `/api/video/${jobId}?t=${Date.now()}`;
    $("#download").href = `/download/${jobId}`;
    renderScript(job.script);
    showErrors([]);
  }

  function renderScript(s) {
    const esc = (t) => String(t).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
    const list = (a) => "<ul>" + a.map((x) => `<li>${esc(x)}</li>`).join("") + "</ul>";
    $("#script-body").innerHTML =
      `<span class="tag-pill">${s.source === "ai" ? "Written by AI from your facts" : "Template script"}</span>` +
      (s.note ? `<p>${esc(s.note)}</p>` : "") +
      `<dl><dt>Headline</dt><dd>${esc(s.headline)}</dd><dt>Tagline</dt><dd>${esc(s.tagline)}</dd>` +
      `<dt>Scene captions</dt><dd>${list(s.captions)}</dd><dt>Highlights</dt><dd>${list(s.highlights)}</dd>` +
      `<dt>Closing message</dt><dd>${esc(s.closing)}</dd></dl>`;
  }

  form.addEventListener("input", (e) => e.target.classList && e.target.classList.remove("invalid"));
  renderPreviews();
})();
