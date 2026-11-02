"use strict";
const FEATURES = ["ac", "climate", "bluetooth", "usb", "phone_charger", "carplay", "navigation", "wifi", "camera", "camera360", "parking_sensors", "dashcam", "cruise", "lane_assist", "keyless", "heated_seats", "ventilated_seats", "leather", "sunroof", "child_seat", "isofix", "roof_rack", "winter_tires", "pets_ok", "abs", "airbags"];
const ANGLES = ["front", "back", "side", "interior", "dashboard", "trunk"];
const LABELS = [...ANGLES, "other"];

(async () => {
  await boot("");
  await guard("user");
  let id = Number(new URLSearchParams(location.search).get("id")) || null;
  const form = $("#carForm");
  let step = 1, car = null, images = [], queue = [], meta = null;
  $("#year").max = new Date().getFullYear() + 1;
  $("#year").value = new Date().getFullYear() - 2;

  const drawFeatures = () => {
    const sel = new Set($$("#features input:checked").map((i) => i.value).concat(car?.features || []));
    $("#features").innerHTML = FEATURES.map((k) => `<label><input type="checkbox" value="${k}" ${sel.has(k) ? "checked" : ""}><span>${esc(t("feature." + k))}</span></label>`).join("");
    if (car) car.features = [];   // birinchi chizishdan keyin holat checkboxlarda saqlanadi
  };

  meta = await api("/api/meta");
  const MAX_IMAGES = meta.max_images || 10, MAX_MB = meta.max_image_mb || 8;
  if (id) {
    car = await api(`/api/cars/${id}`);
    if (!car.is_mine) { location.replace("/dashboard.html#cars"); return; }
    $("#formTitle").dataset.i18n = "form.title_edit";
    for (const el of form.elements) if (el.name && el.name in car && el.type !== "checkbox") el.value = car[el.name] ?? "";
    $("#require_docs").checked = !!car.require_docs;
    $("#hasDelivery").checked = car.delivery_price !== null;
    $("#delivery_price").disabled = car.delivery_price === null;
    images = car.images;
  } else $("#require_docs").checked = true;    // yangi e'londa tavsiya: faqat hujjati tasdiqlanganlar
  drawFeatures();
  applyI18n();
  // Viloyat -> tuman (tahrirlashda saqlangan qiymat; yangi e'londa — egasining o'z hududi)
  await Places.bind($("#city"), $("#district"), { region: car?.city || Auth.user.region || "", district: car?.district || (car ? "" : Auth.user.district || "") });
  document.addEventListener("langchange", () => Places.bind($("#city"), $("#district"), { region: $("#city").value, district: $("#district").value }));
  applyMasks(form);
  // Model takliflari: tanlangan markadagi CarRent modellari + ommabop modellar
  const COMMON_MODELS = { Chevrolet: ["Cobalt", "Gentra", "Nexia 3", "Spark", "Malibu", "Tracker", "Onix", "Damas", "Lacetti", "Captiva", "Equinox", "Tahoe"],
    Kia: ["K5", "Sportage", "Sonet", "Carnival", "Seltos", "Sorento"], Hyundai: ["Sonata", "Elantra", "Tucson", "Santa Fe", "Creta"],
    Toyota: ["Camry", "Corolla", "RAV4", "Land Cruiser", "Prado"], BYD: ["Song Plus", "Han", "Chazor", "Seagull", "Tang"],
    Ravon: ["Nexia R3", "Gentra", "R2"], Lada: ["Granta", "Vesta", "Niva"] };
  const drawModels = () => {
    const b = form.brand.value.trim().toLowerCase();
    const fromSite = (meta.models || []).filter((m) => m.brand.toLowerCase() === b).map((m) => m.model);
    const common = Object.entries(COMMON_MODELS).find(([k]) => k.toLowerCase() === b)?.[1] || [];
    $("#modelList").innerHTML = [...new Set([...fromSite, ...common])].map((m) => `<option value="${esc(m)}">`).join("");
  };
  form.brand.addEventListener("input", drawModels); drawModels();
  const drawCommission = () => { $("#commissionNote").textContent = t("form.commission_note", { pct: meta.commission_bps / 100 }); };
  drawCommission();

  // ---------- Joylashuv: xaritadan tanlash yoki "Mening joylashuvim" ----------
  let picker = null;
  const showLoc = () => { const a = form.lat.value, b = form.lng.value; $("#locInfo").textContent = a && b ? `${(+a).toFixed(5)}, ${(+b).toFixed(5)}` : t("map.not_set"); };
  $("#myLoc").innerHTML = `${icon("search", 15)} ${esc(t("map.my_location"))}`;
  const initPicker = async () => {
    if (picker) { setTimeout(() => picker.map.invalidateSize(), 50); return; }
    try {
      picker = await MapKit.picker($("#pickMap"), { lat: car?.lat ?? null, lng: car?.lng ?? null, region: form.city.value,
        onPick: (a, b) => { form.lat.value = a; form.lng.value = b; showLoc(); } });
    } catch (err) { $("#pickMap").innerHTML = `<div class="empty small">${esc(err.message)}</div>`; }
    showLoc();
  };
  $("#myLoc").addEventListener("click", async (e) => {
    await withLoading(e.currentTarget, async () => {
      try { const p = await MapKit.locate(); await initPicker(); picker?.set(p.lat, p.lng, true); toast(t("map.located", { m: p.acc }), "ok"); }
      catch (err) { toast(err.message, "error"); }
    });
  });
  $("#clearLoc").addEventListener("click", () => { form.lat.value = ""; form.lng.value = ""; picker?.clear(); showLoc(); });
  form.city.addEventListener("change", () => { if (picker && !form.lat.value) picker.center(form.city.value); });

  $("#hasDelivery").addEventListener("change", (e) => { $("#delivery_price").disabled = !e.target.checked; if (e.target.checked && !$("#delivery_price").value) $("#delivery_price").value = fmtMoneyInput(50000); });

  // ---------- Bosqichlar ----------
  const REQUIRED = { 1: ["brand", "model", "year", "seats"], 3: ["city", "district"], 4: ["price_per_day"] };
  function validStep(n) {
    let ok = true;
    for (const name of REQUIRED[n] || []) {
      const el = form.elements[name], field = el.closest(".field");
      $$(".err", field).forEach((x) => x.remove()); el.removeAttribute("aria-invalid");
      if (!el.value.trim() || !el.checkValidity()) {
        ok = false; el.setAttribute("aria-invalid", "true");
        const d = document.createElement("div"); d.className = "err"; d.textContent = el.validationMessage || t("val.required"); field.append(d);
      }
    }
    if (n === 4 && +form.max_days.value < +form.min_days.value) { toast(t("val.days"), "error"); ok = false; }
    return ok;
  }
  function go(n) {
    step = n;
    $$("[data-pane]").forEach((p) => p.classList.toggle("hidden", +p.dataset.pane !== n));
    $$("#steps li").forEach((li) => { const s = +li.dataset.step; li.classList.toggle("on", s === n); li.classList.toggle("done", s < n); });
    $("#prevBtn").style.visibility = n === 1 ? "hidden" : "visible";
    $("#nextBtn").classList.toggle("hidden", n === 6);
    $("#publishBtn").classList.toggle("hidden", n !== 6);
    $("#draftBtn").classList.toggle("hidden", n !== 6);
    if (n === 6) drawPreview();
    if (n === 3) initPicker();
    form.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  $("#nextBtn").addEventListener("click", () => { if (validStep(step)) go(step + 1); });
  $("#prevBtn").addEventListener("click", () => go(Math.max(1, step - 1)));
  $("#steps").addEventListener("click", (e) => {
    const li = e.target.closest("[data-step]"); if (!li) return;
    const target = +li.dataset.step;
    for (let s = 1; s < target; s++) if (!validStep(s)) { go(s); return; }
    go(target);
  });

  // ---------- Tavsiya etiladigan narx ----------
  $("#suggestBtn").addEventListener("click", async () => {
    const box = $("#suggestBox");
    const feats = $$("#features input:checked").map((i) => i.value).join(",");
    const p = new URLSearchParams({ brand: form.brand.value, model: form.model.value, year: form.year.value, city: form.city.value, body_type: form.body_type.value, features: feats });
    if (id) p.set("exclude", id);
    const r = await api("/api/pricing/suggest?" + p);
    if (!r.suggested) { box.innerHTML = `<div class="suggest">${esc(t("price.no_data"))}</div>`; return; }
    const factors = r.factors.map((f) => t("factor." + f.code, { n: f.n, pct: f.pct, level: f.level ? t("level." + f.level) : "" })).filter(Boolean);
    box.innerHTML = `<div class="suggest"><div><b>${esc(t("price.suggested"))}: ${money(r.suggested)}</b> ${esc(t("car.per_day"))}</div>
      <div class="small">${esc(t("price.range", { a: money(r.low), b: money(r.high) }))}</div>
      <div class="small muted" style="margin-top:6px">${esc(t("price.confidence_" + r.confidence))}</div>
      <ul class="small muted" style="margin:6px 0 8px;padding-left:18px">${factors.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>
      <button type="button" class="btn btn-sm" id="applySuggest">${esc(t("price.apply"))}</button></div>`;
    $("#applySuggest").addEventListener("click", () => { form.price_per_day.value = fmtMoneyInput(r.suggested); toast(t("price.applied"), "ok"); });
  });

  // ---------- Rasmlar: burchaklar ro'yxati, kamera, siqish, tartiblash, yorliq, asosiy rasm ----------
  $("#dzIco").innerHTML = icon("plus", 26); $("#camIco").innerHTML = icon("camera", 20);
  const used = () => new Set([...images, ...queue].map((x) => x.label));
  const nextLabel = () => ANGLES.find((a) => !used().has(a)) || "other";
  function drawAngles() {
    const u = used();
    $("#angles").innerHTML = ANGLES.map((a) => `<span class="angle ${u.has(a) ? "ok" : ""}">${icon(u.has(a) ? "check" : "camera", 14)}${esc(t("img.label_" + a))}</span>`).join("")
      + `<span class="angle-count">${images.length + queue.length} / ${MAX_IMAGES}</span>`;
    $("#dzHint").textContent = t("form.drop_hint2", { n: MAX_IMAGES, mb: MAX_MB });
  }
  function photoCard(item, i, kind, list) {
    const isCover = kind === "s" && i === 0;
    const status = kind === "q" ? `<span class="tag ${item.error ? "tag-bad" : "tag-pending"} ptag">${esc(item.error ? t("form.upload_failed") : item.progress ? item.progress + "%" : t("form.queued"))}</span>` : "";
    return `<div class="photo ${isCover ? "is-cover" : ""}" draggable="true" data-kind="${kind}" data-i="${i}">
      <div class="photo-img"><img src="${esc(item.path || item.url)}" alt="${esc(t("img.label_" + item.label))}">
        ${isCover ? `<span class="tag tag-info ptag">★ ${esc(t("form.cover"))}</span>` : status}
        ${kind === "q" ? `<div class="bar" style="width:${item.progress || 0}%"></div>` : ""}</div>
      <div class="photo-tools">
        <select class="input" data-label aria-label="${esc(t("img.label"))}">${LABELS.map((l) => `<option value="${l}" ${l === item.label ? "selected" : ""}>${esc(t("img.label_" + l))}</option>`).join("")}</select>
        <div class="photo-btns">
          <button type="button" class="icon-btn ghost" data-move="-1" ${i === 0 ? "disabled" : ""} aria-label="${esc(t("form.move_left"))}">${icon("arrowl", 16)}</button>
          <button type="button" class="icon-btn ghost" data-move="1" ${i === list.length - 1 ? "disabled" : ""} aria-label="${esc(t("form.move_right"))}">${icon("arrowr", 16)}</button>
          ${kind === "s" && !isCover ? `<button type="button" class="icon-btn ghost" data-cover aria-label="${esc(t("form.make_cover"))}" title="${esc(t("form.make_cover"))}">${icon("star", 16)}</button>` : ""}
          ${kind === "q" && item.error ? `<button type="button" class="icon-btn ghost" data-retry aria-label="${esc(t("form.retry"))}">↻</button>` : ""}
          <button type="button" class="icon-btn ghost danger" data-del aria-label="${esc(t("common.delete"))}">${icon("trash", 16)}</button>
        </div></div></div>`;
  }
  function drawImages() {
    $("#uploaded").innerHTML = images.map((im, i) => photoCard(im, i, "s", images)).join("") + queue.map((q, i) => photoCard(q, i, "q", queue)).join("")
      || `<div class="photo-empty">${icon("camera", 30)}<span>${esc(t("form.no_photos"))}</span></div>`;
    drawAngles();
  }
  drawImages();

  async function addFiles(files) {
    for (const raw of files) {
      if (images.length + queue.length >= MAX_IMAGES) { toast(t("form.max_images", { n: MAX_IMAGES }), "error"); break; }
      if (!/^image\//.test(raw.type)) { toast(t("form.bad_type", { name: raw.name }), "error"); continue; }
      const f = await compressImage(raw, 1920);
      if (!["image/jpeg", "image/png", "image/webp"].includes(f.type)) { toast(t("form.bad_type", { name: raw.name }), "error"); continue; }
      if (f.size > MAX_MB * 1024 * 1024) { toast(t("form.too_big", { name: raw.name, n: MAX_MB }), "error"); continue; }
      queue.push({ file: f, url: URL.createObjectURL(f), progress: 0, error: false, label: nextLabel() });
      drawImages();
    }
    if (id) uploadQueue(id);
  }

  function uploadOne(carId, q) {
    return new Promise((resolve) => {
      const fd = new FormData(); fd.append("images", q.file); fd.append("labels", q.label);
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/cars/${carId}/images`);
      xhr.setRequestHeader("X-Requested-With", "fetch");
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) { q.progress = Math.round((e.loaded / e.total) * 100); drawImages(); } };
      xhr.onload = () => {
        if (xhr.status < 300) { images = JSON.parse(xhr.responseText).images; queue = queue.filter((x) => x !== q); URL.revokeObjectURL(q.url); }
        else { q.error = true; try { toast(JSON.parse(xhr.responseText).detail, "error"); } catch {} }
        drawImages(); resolve();
      };
      xhr.onerror = () => { q.error = true; toast(t("err.network"), "error"); drawImages(); resolve(); };
      xhr.send(fd);
    });
  }
  let uploading = null;
  async function uploadQueue(carId) {
    if (uploading) await uploading;
    uploading = (async () => { for (const q of [...queue]) if (!q.error) await uploadOne(carId, q); })();
    await uploading; uploading = null;
    return queue.filter((q) => q.error).length === 0;
  }
  const saveOrder = async () => { if (id && images.length) images = (await api(`/api/cars/${id}/images/order`, { method: "PUT", body: { ids: images.map((x) => x.id) } })).images; };
  async function move(kind, from, to) {
    const list = kind === "s" ? images : queue;
    if (to < 0 || to >= list.length || from === to) return;
    list.splice(to, 0, list.splice(from, 1)[0]);
    drawImages();
    if (kind === "s") { try { await saveOrder(); drawImages(); } catch (err) { toast(err.message, "error"); } }
  }

  $("#images").addEventListener("change", (e) => { addFiles([...e.target.files]); e.target.value = ""; });
  $("#cameraInput").addEventListener("change", (e) => { addFiles([...e.target.files]); e.target.value = ""; });
  const dz = $("#dropzone");
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", (e) => addFiles([...e.dataTransfer.files]));

  const grid = $("#uploaded");
  const itemOf = (el) => { const c = el.closest(".photo"); return c && { kind: c.dataset.kind, i: +c.dataset.i, card: c }; };
  grid.addEventListener("click", async (e) => {
    const it = itemOf(e.target); if (!it) return;
    const list = it.kind === "s" ? images : queue, item = list[it.i];
    try {
      if (e.target.closest("[data-move]")) await move(it.kind, it.i, it.i + +e.target.closest("[data-move]").dataset.move);
      else if (e.target.closest("[data-cover]")) { images = (await api(`/api/cars/${id}/images/${item.id}/cover`, { method: "POST" })).images; drawImages(); toast(t("form.cover_set"), "ok"); }
      else if (e.target.closest("[data-del]")) {
        if (it.kind === "s") { if (!(await confirmBox(t("form.delete_photo"), t("common.delete"), true))) return; await api(`/api/cars/${id}/images/${item.id}`, { method: "DELETE" }); images.splice(it.i, 1); }
        else { URL.revokeObjectURL(item.url); queue.splice(it.i, 1); }
        drawImages();
      } else if (e.target.closest("[data-retry]")) { item.error = false; item.progress = 0; drawImages(); if (id) await uploadOne(id, item); }
    } catch (err) { toast(err.message, "error"); }
  });
  grid.addEventListener("change", async (e) => {
    if (!e.target.matches("[data-label]")) return;
    const it = itemOf(e.target), list = it.kind === "s" ? images : queue, item = list[it.i];
    item.label = e.target.value; drawAngles();
    if (it.kind === "s") { try { await api(`/api/cars/${id}/images/${item.id}`, { method: "PATCH", body: { label: item.label } }); } catch (err) { toast(err.message, "error"); } }
  });
  // Sichqoncha bilan sudrab tartiblash (kompyuterda); telefonda ← → tugmalari
  let dragFrom = null;
  grid.addEventListener("dragstart", (e) => { const it = itemOf(e.target); if (!it || e.target.closest("select")) return; dragFrom = it; it.card.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; });
  grid.addEventListener("dragend", () => { $$(".photo.dragging, .photo.drop-on", grid).forEach((x) => x.classList.remove("dragging", "drop-on")); });
  grid.addEventListener("dragover", (e) => { const it = itemOf(e.target); if (dragFrom && it && it.kind === dragFrom.kind) { e.preventDefault(); $$(".photo.drop-on", grid).forEach((x) => x.classList.remove("drop-on")); it.card.classList.add("drop-on"); } });
  grid.addEventListener("drop", (e) => { const it = itemOf(e.target); if (dragFrom && it && it.kind === dragFrom.kind) { e.preventDefault(); move(it.kind, dragFrom.i, it.i); } dragFrom = null; });

  // ---------- Ko'rib chiqish va saqlash ----------
  function body(active) {
    const d = formData(form);
    const num = (v) => (v === "" || v === undefined ? null : Number(v));
    return {
      brand: d.brand, model: d.model, year: +d.year, color: d.color || null, body_type: d.body_type, seats: +d.seats, transmission: d.transmission,
      fuel: d.fuel, engine_l: num(d.engine_l), mileage_km: num(d.mileage_km), drive: d.drive || null,
      features: $$("#features input:checked").map((i) => i.value), city: d.city, district: d.district || null, description: d.description || null,
      price_per_day: +d.price_per_day, deposit: num(d.deposit) || 0, min_days: +d.min_days || 1, max_days: +d.max_days || 30,
      km_limit: num(d.km_limit), delivery_price: $("#hasDelivery").checked ? num(d.delivery_price) ?? 0 : null, is_active: active,
      lat: num(d.lat), lng: num(d.lng), address: d.address || null, plate: d.plate || null, fuel_policy: d.fuel_policy || "same",
      tank_l: num(d.tank_l), fuel_price: num(d.fuel_price), extra_km_price: num(d.extra_km_price), require_docs: $("#require_docs").checked,
    };
  }
  function drawPreview() {
    const b = body(true);
    const fake = { ...b, id: id || 0, cover: images[0]?.path || queue[0]?.url, rating: car?.rating, reviews_count: car?.reviews_count || 0, owner_id: Auth.user.id, is_demo: 0 };
    $("#preview").innerHTML = carCard(fake).replace(/href="[^"]*"/g, 'href="#" tabindex="-1"');
    $("#previewTerms").innerHTML = `<div class="terms-list">
      <div><span class="muted">${esc(t("terms.deposit"))}</span><b>${b.deposit ? money(b.deposit) : esc(t("terms.none"))}</b></div>
      <div><span class="muted">${esc(t("terms.period"))}</span><b>${esc(t("terms.days_range", { a: b.min_days, b: b.max_days }))}</b></div>
      <div><span class="muted">${esc(t("terms.km"))}</span><b>${b.km_limit ? `${b.km_limit} ${esc(t("unit.km_day"))}` : esc(t("terms.unlimited"))}</b></div>
      <div><span class="muted">${esc(t("terms.delivery"))}</span><b>${b.delivery_price !== null ? money(b.delivery_price) : esc(t("terms.no_delivery"))}</b></div>
      <div><span class="muted">${esc(t("field.features"))}</span><b>${b.features.length}</b></div>
      <div><span class="muted">${esc(t("form.s5"))}</span><b>${images.length + queue.length}</b></div></div>`;
  }

  async function save(active, btn) {
    for (const s of [1, 3, 4]) if (!validStep(s)) { go(s); return; }
    await withLoading(btn, async () => {
      try {
        const saved = await api(id ? `/api/cars/${id}` : "/api/cars", { method: id ? "PUT" : "POST", body: body(active) });
        if (!id) { id = saved.id; history.replaceState(null, "", `/car-form.html?id=${saved.id}`); }
        const allUploaded = await uploadQueue(saved.id);
        if (!allUploaded) { toast(t("form.saved_some_failed"), "error"); go(5); return; }
        toast(t(active ? "form.published" : "form.draft_saved"), "ok");
        setTimeout(() => (location.href = active ? `/car.html?id=${saved.id}` : "/dashboard.html?mode=owner#cars"), 600);
      } catch (err) {
        showFieldErrors(form, err); toast(err.message, "error");
        const bad = (err.errors || [])[0]?.field;
        const pane = bad && form.elements[bad]?.closest("[data-pane]");
        if (pane) go(+pane.dataset.pane);
      }
    });
  }
  form.addEventListener("submit", (e) => { e.preventDefault(); save(true, $("#publishBtn")); });
  $("#draftBtn").addEventListener("click", () => save(false, $("#draftBtn")));
  const descCount = () => { $("#descCount").textContent = `${form.description.value.length} / 2000`; };
  form.description.addEventListener("input", descCount); descCount();
  document.addEventListener("langchange", () => { drawFeatures(); drawCommission(); drawImages(); if (step === 6) drawPreview(); });
  go(1);
})();
