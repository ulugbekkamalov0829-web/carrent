"use strict";
const FEATURE_KEYS = ["ac", "climate", "child_seat", "isofix", "camera", "carplay", "cruise", "heated_seats", "roof_rack", "pets_ok"];

(async () => {
  await boot("cars");
  const state = new URLSearchParams(location.search);
  const form = $("#filterForm");
  const today = isoDate(new Date());
  $("#start").min = today; $("#end").min = today;

  const drawChips = () => {
    const checked = new Set((state.get("features") || "").split(",").filter(Boolean));
    $$("#featureChips input:checked").forEach((i) => checked.add(i.value));
    $("#featureChips").innerHTML = FEATURE_KEYS.map((k) =>
      `<label><input type="checkbox" value="${k}" ${checked.has(k) ? "checked" : ""}><span>${esc(t("feature." + k))}</span></label>`).join("");
  };
  drawChips();

  const meta = await api("/api/meta");
  $("#brand").insertAdjacentHTML("beforeend", meta.brands.map((b) => `<option>${esc(b)}</option>`).join(""));
  // Marka yoki model: CarRent'dagi barcha mashinalar nomi taklif qilinadi
  $("#carNames").innerHTML = [...meta.brands.map((b) => `<option value="${esc(b)}">`),
    ...meta.models.map((m) => `<option value="${esc(m.brand)} ${esc(m.model)}">${esc(t("filter.n_listings", { n: m.count }))}</option>`)].join("");
  const counts = Object.fromEntries(meta.cities.map((c) => [c.city, c.count]));
  const places = await Places.bind($("#city"), $("#district"), { region: state.get("city") || "", district: state.get("district") || "", any: true, counts });

  // URL'dagi filtrlarni formaga qaytaramiz (havolani ulashish mumkin)
  for (const el of form.elements) {
    if (!el.name || !state.has(el.name) || el.name === "city" || el.name === "district") continue;
    if (el.type === "checkbox") el.checked = state.get(el.name) === el.value; else el.value = state.get(el.name);
  }
  if (state.has("sort")) $("#sort").value = state.get("sort");

  function collect(page = 1) {
    const p = new URLSearchParams();
    for (const el of form.elements) {
      if (!el.name) continue;
      if (el.type === "checkbox") { if (el.checked) p.set(el.name, el.value); }
      else if (el.dataset.money !== undefined) { if (moneyVal(el.value)) p.set(el.name, moneyVal(el.value)); }
      else if (el.value) p.set(el.name, el.value.trim());
    }
    const feats = $$("#featureChips input:checked").map((i) => i.value);
    if (feats.length) p.set("features", feats.join(","));
    if ($("#sort").value !== "new") p.set("sort", $("#sort").value);
    if (page > 1) p.set("page", page);
    return p;
  }

  let last = null;
  async function load(page = 1) {
    const p = collect(page);
    if (p.get("start") && p.get("end") && p.get("end") < p.get("start")) { toast(t("err.dates_order"), "error"); return; }
    history.replaceState(null, "", "/cars.html" + (p.toString() ? "?" + p : ""));
    $("#cars").innerHTML = Array(6).fill(`<div class="skeleton" style="height:340px"></div>`).join("");
    try { last = { data: await api("/api/cars?" + p), p }; draw(); }
    catch (e) { $("#cars").innerHTML = `<div class="empty card" style="grid-column:1/-1">${esc(e.message)}</div>`; }
  }

  function draw() {
    if (!last) return;
    const { data, p } = last;
    const days = p.get("start") && p.get("end") ? daysBetween(p.get("start"), p.get("end")) : 0;
    const qs = days ? `&start=${encodeURIComponent(p.get("start"))}&end=${encodeURIComponent(p.get("end"))}` : "";
    $("#resultInfo").textContent = t("cars.found", { n: data.total }) + (days ? " · " + t("cars.free_between", { a: fmtDate(p.get("start")), b: fmtDate(p.get("end")) }) : "");
    $("#applyFilters").textContent = t("cars.show_n", { n: data.total });
    $("#cars").innerHTML = data.items.length ? data.items.map((c) => carCard(c, { days, qs })).join("") : `
      <div class="empty card" style="grid-column:1/-1"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
      <h3>${esc(t("cars.empty"))}</h3><p>${esc(t("cars.empty_hint"))}</p><button class="btn btn-outline" id="emptyReset">${esc(t("cars.reset"))}</button></div>`;
    $("#emptyReset")?.addEventListener("click", reset);
    $("#pager").innerHTML = data.pages > 1 ? Array.from({ length: data.pages }, (_, i) => i + 1)
      .map((i) => `<button class="btn btn-sm ${i === data.page ? "" : "btn-outline"}" data-page="${i}" aria-label="${esc(t("cars.page", { n: i }))}">${i}</button>`).join("") : "";
  }

  function reset() { form.reset(); $("#district").innerHTML = ""; $("#city").dispatchEvent(new Event("change")); $$("#featureChips input").forEach((i) => (i.checked = false)); $("#sort").value = "new"; load(); }

  $("#pager").addEventListener("click", (e) => { const b = e.target.closest("[data-page]"); if (b) { load(+b.dataset.page); scrollTo({ top: 0, behavior: "smooth" }); } });
  let timer;
  form.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(load, 350); });
  $("#featureChips").addEventListener("change", () => load());
  $("#sort").addEventListener("change", () => load());
  $("#start").addEventListener("change", () => { $("#end").min = $("#start").value; if ($("#end").value && $("#end").value < $("#start").value) $("#end").value = $("#start").value; });
  $("#resetFilters").addEventListener("click", reset);
  $("#filtersToggle").addEventListener("click", () => $("#filters").classList.add("open"));
  $("#applyFilters").addEventListener("click", () => $("#filters").classList.remove("open"));
  applyMasks(form);
  document.addEventListener("langchange", () => { drawChips(); places.refresh(); draw(); });
  load(+(state.get("page") || 1));
})();
