/* CarRent — umumiy modul: tarjimalar (uz/ru/en), API, autentifikatsiya, header, kalendar, kartochkalar */
"use strict";

// ---------- Xavfsiz HTML (XSS himoyasi): foydalanuvchi matni har doim esc() orqali chiqadi ----------
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ================= Tarjimalar =================
const I18N = {
  langs: ["uz", "ru", "en"],
  names: { uz: "O‘zbekcha", ru: "Русский", en: "English" },
  locales: { uz: "uz-UZ", ru: "ru-RU", en: "en-US" },
  lang: "uz", dict: {}, base: {},
  async load(lang) {
    const get = async (l) => (await fetch(`/locales/${l}.json`, { cache: "no-cache" })).json();
    if (!Object.keys(this.base).length) this.base = await get("uz");
    this.dict = lang === "uz" ? this.base : await get(lang);
    this.lang = lang;
    document.documentElement.lang = lang;
  },
  initial(userLang) {
    let saved = null;
    try { saved = localStorage.getItem("lang"); } catch {}
    const cookie = (document.cookie.match(/(?:^|;\s*)lang=(\w+)/) || [])[1];
    // Boshlang'ich til — o'zbekcha (brauzer tili hisobga olinmaydi, foydalanuvchi o'zi tanlaydi)
    return [userLang, saved, cookie, "uz"].find((l) => this.langs.includes(l));
  },
};

/** Tarjima: kalit yetishmasa o'zbekchaga qaytadi; texnik kalit foydalanuvchiga ko'rsatilmaydi. */
function t(key, params) {
  let s = I18N.dict[key] ?? I18N.base[key];
  if (s === undefined) { console.warn("i18n: kalit yo'q", key); return ""; }
  if (params) s = s.replace(/\{(\w+)\}/g, (_, k) => (params[k] ?? ""));
  return s;
}

/** HTML'dagi statik matnlar: data-i18n, data-i18n-placeholder, data-i18n-aria, data-i18n-title */
function applyI18n(root = document) {
  $$("[data-i18n]", root).forEach((el) => { el.textContent = t(el.dataset.i18n); });
  $$("[data-i18n-html]", root).forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); }); // faqat bizning tarjima fayllarimizdan
  $$("[data-i18n-placeholder]", root).forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  $$("[data-i18n-aria]", root).forEach((el) => { el.setAttribute("aria-label", t(el.dataset.i18nAria)); });
  $$("[data-i18n-title]", root).forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  const title = $("title[data-i18n-doc]");
  if (title) document.title = t(title.dataset.i18nDoc) + " — CarRent";
}

/** Til almashtirish: sahifa qayta yuklanmaydi, forma qiymatlari va filtrlar joyida qoladi. */
async function setLang(lang) {
  if (!I18N.langs.includes(lang) || lang === I18N.lang) return;
  await I18N.load(lang);
  try { localStorage.setItem("lang", lang); } catch {}
  document.cookie = `lang=${lang}; path=/; max-age=31536000; samesite=lax`;
  api("/api/me/lang", { method: "PATCH", body: { lang } }).catch(() => {});
  if (Auth.user) Auth.user.lang = lang;
  applyI18n();
  renderNavInner();
  document.dispatchEvent(new CustomEvent("langchange", { detail: lang }));
}

// ================= API =================
/** O'rnatilgan ilova (telefon yoki kompyuterdagi PWA) — saytdan farqli: uzoq sessiya + ekran PIN kodi */
const IS_APP = matchMedia("(display-mode: standalone)").matches || matchMedia("(display-mode: window-controls-overlay)").matches || navigator.standalone === true;

async function api(path, { method = "GET", body, form } = {}) {
  const opts = { method, headers: { "X-Requested-With": "fetch", ...(IS_APP ? { "X-App-Mode": "app" } : {}) }, credentials: "same-origin" };
  if (form) opts.body = form;
  else if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  let res;
  try { res = await fetch(path, opts); }
  catch { throw new Error(t("err.network")); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.detail || t("err.generic", { code: res.status }));
    err.status = res.status; err.errors = data.errors || [];
    throw err;
  }
  return data;
}

// ================= Formatlash (locale bo'yicha) =================
// O'zbekcha va ruscha: 600 000 (bo'shliq bilan), inglizcha: 600,000
const numFmt = () => new Intl.NumberFormat(I18N.lang === "en" ? "en-US" : "ru-RU");
const money = (n) => `${numFmt().format(Math.round(Number(n) || 0))} ${t("currency")}`;
const shortMoney = (n) => {
  n = Number(n) || 0;
  if (n >= 1e6) return `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1).replace(/\.0$/, "")} ${t("unit.mln")}`;
  if (n >= 1e3) return `${Math.round(n / 1e3)} ${t("unit.k")}`;
  return String(n);
};
/** Sana ko'rinishi: DD.MM.YYYY */
function fmtDate(s) {
  if (!s) return "";
  const [y, m, d] = s.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}
function timeAgo(s) {
  const sec = (Date.now() - new Date(s.replace(" ", "T") + "Z")) / 1000;
  if (sec < 60) return t("time.now");
  if (sec < 3600) return t("time.min", { n: Math.floor(sec / 60) });
  if (sec < 86400) return t("time.hour", { n: Math.floor(sec / 3600) });
  if (sec < 86400 * 7) return t("time.day", { n: Math.floor(sec / 86400) });
  return fmtDate(s);
}
const isoDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const daysBetween = (a, b) => Math.round((new Date(b + "T00:00:00") - new Date(a + "T00:00:00")) / 864e5) + 1;
const stars = (r) => { const n = Math.round(r || 0); return "★".repeat(n) + "☆".repeat(5 - n); };
const initials = (name) => (name || "?").split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
const statusTag = (s) => `<span class="tag tag-${esc(s)}">${esc(t("status." + s))}</span>`;
const carName = (c) => `${c.brand} ${c.model}`;

// ================= Telefon shabloni va pul summalarini ajratish =================
/** "+998 90 123 45 67" ko'rinishi: yozish paytida bo'shliqlar avtomatik qo'yiladi, +998 o'chib ketmaydi */
function fmtPhone(v) {
  let d = String(v || "").replace(/\D/g, "");
  if (d.startsWith("998")) d = d.slice(3);
  else if (d.length > 9 && d.startsWith("8")) d = d.slice(1);
  d = d.slice(0, 9);
  const parts = [d.slice(0, 2), d.slice(2, 5), d.slice(5, 7), d.slice(7, 9)].filter(Boolean);
  return "+998" + (parts.length ? " " + parts.join(" ") : " ");
}
/** 600000 -> "600 000" (yozish paytida ham) */
const fmtMoneyInput = (v) => { const d = String(v ?? "").replace(/\D/g, "").replace(/^0+(?=\d)/, ""); return d ? d.replace(/\B(?=(\d{3})+(?!\d))/g, " ") : ""; };
const moneyVal = (v) => { const d = String(v ?? "").replace(/\D/g, ""); return d ? +d : null; };

/** Qayta formatlash: kursor o'sha raqamdan keyin qoladi (o'rtadan tahrirlash ham buzilmaydi) */
function reformatKeepingCaret(el, fmt) {
  const phone = fmt === fmtPhone;
  const pos = el.selectionStart ?? el.value.length;
  const prefix = (v) => (phone && v.startsWith("+998") ? 4 : 0);
  let n = el.value.slice(prefix(el.value), pos).replace(/\D/g, "").length;   // kursorgacha bo'lgan raqamlar
  el.value = fmt(el.value);
  let at = prefix(el.value);
  if (phone && at && el.value[at] === " ") at++;
  for (let i = at; i < el.value.length && n > 0; i++) { if (/\d/.test(el.value[i])) n--; at = i + 1; }
  try { el.setSelectionRange(at, at); } catch {}
}
const isPhoneInput = (el) => el.matches?.("input[type=tel], input[data-phone]");
const isMoneyInput = (el) => el.matches?.("input[data-money]");
document.addEventListener("input", (e) => {
  const el = e.target;
  if (isPhoneInput(el)) reformatKeepingCaret(el, fmtPhone);
  else if (isMoneyInput(el)) reformatKeepingCaret(el, fmtMoneyInput);
});
document.addEventListener("focusin", (e) => { if (isPhoneInput(e.target) && !e.target.value) e.target.value = "+998 "; });
document.addEventListener("focusout", (e) => { if (isPhoneInput(e.target) && e.target.value.replace(/\D/g, "") === "998") e.target.value = ""; });
/** Sahifa chizilgandan keyin mavjud qiymatlarni formatlash (masalan, profildagi telefon) */
function applyMasks(root = document) {
  $$("input[type=tel], input[data-phone]", root).forEach((el) => { if (el.value) el.value = fmtPhone(el.value); });
  $$("input[data-money]", root).forEach((el) => { el.value = fmtMoneyInput(el.value); el.setAttribute("inputmode", "numeric"); el.autocomplete = "off"; });
}

// ================= Viloyat va tumanlar =================
const Places = {
  data: null,
  async load() {
    if (!this.data) this.data = await (await fetch("/geo/regions.json")).json();
    return this.data;
  },
  regionName(key) {
    const r = this.data?.regions.find((x) => x.key === key);
    return !r ? (key || "") : I18N.lang === "uz" ? uzTypo(r.key) : r[I18N.lang] || r.key;
  },
  label(region, district) { return [district ? uzTypo(district) : "", this.regionName(region)].filter(Boolean).join(", "); },
  /** Viloyat tanlansa — faqat shu viloyat tumanlari; o'zgartirilsa ro'yxat yangilanadi.
      Tuman maydoni viloyat tanlanmaguncha yashirin (tanlangach o'zi chiqadi). Telefonda — pastdan chiqadigan tanlash oynasi. */
  async bind(regionSel, districtSel, { region = "", district = "", any = false, counts = null, short = false } = {}) {
    await this.load();
    const fillRegions = () => {
      regionSel.innerHTML = `<option value="">${esc(t(short ? "place.region" : any ? "search.any_city" : "place.pick_region"))}</option>` +
        this.data.regions.map((r) => `<option value="${esc(r.key)}" ${counts ? `data-n="${counts[r.key] || 0}"` : ""}>${esc(this.regionName(r.key))}${counts && counts[r.key] ? ` · ${esc(t("place.n_cars", { n: counts[r.key] }))}` : ""}</option>`).join("");
    };
    const field = short ? null : districtSel.closest(".field");
    const fillDistricts = (keep) => {
      const r = this.data.regions.find((x) => x.key === regionSel.value);
      districtSel.innerHTML = `<option value="">${esc(t(short ? "place.district_short" : r ? (any ? "place.any_district" : "place.pick_district") : "place.region_first"))}</option>` +
        (r ? r.districts.map((d) => `<option value="${esc(d)}">${esc(uzTypo(d))}</option>`).join("") : "");
      districtSel.disabled = !r;
      if (keep && r?.districts.includes(keep)) districtSel.value = keep;
      if (field) { field.classList.toggle("place-hidden", !r); if (r && !keep) field.classList.add("place-reveal"); }
    };
    fillRegions();
    regionSel.value = this.data.regions.some((r) => r.key === region) ? region : "";
    fillDistricts(district);
    regionSel.onchange = () => { fillDistricts(""); regionSel.dispatchEvent(new CustomEvent("placechange", { bubbles: true })); };
    SheetSelect.attach(regionSel, { counts }); SheetSelect.attach(districtSel);
    return { refresh: () => { const r = regionSel.value, d = districtSel.value; fillRegions(); regionSel.value = r; fillDistricts(d); } };
  },
};

/** Telefonda uzun ro'yxatli select o'rniga pastdan chiqadigan chiroyli oyna (tizimning oddiy ro'yxati emas) */
const SheetSelect = {
  attach(sel, { counts = null } = {}) {
    if (sel.dataset.sheet) return;
    sel.dataset.sheet = "1";
    const wrap = document.createElement("span"); wrap.className = "sheet-wrap";
    sel.parentNode.insertBefore(wrap, sel); wrap.append(sel);
    const hit = document.createElement("button"); hit.type = "button"; hit.className = "sheet-hit"; hit.tabIndex = -1; hit.setAttribute("aria-hidden", "true");
    wrap.append(hit);
    hit.addEventListener("click", () => { if (!sel.disabled) this.open(sel, counts); });
  },
  open(sel, counts) {
    const bg = document.createElement("div"); bg.className = "sheet-bg";
    const label = sel.closest(".field")?.querySelector("label")?.textContent || sel.getAttribute("aria-label") || "";
    const opts = [...sel.options];
    bg.innerHTML = `<div class="sheet" role="dialog" aria-modal="true"><div class="sheet-grab"></div><div class="sheet-head"><b>${esc(label)}</b>
      <button type="button" class="icon-btn ghost" data-close aria-label="${esc(t("common.close"))}">${icon("close")}</button></div>
      ${opts.length > 10 ? `<input class="input sheet-find" type="search" placeholder="${esc(t("common.search"))}…">` : ""}
      <div class="sheet-list">${opts.map((o) => { const n = o.dataset.n; return `<button type="button" class="sheet-opt ${o.value === sel.value ? "on" : ""} ${n === "0" ? "dim" : ""}" data-v="${esc(o.value)}">
        <span>${esc(n !== undefined ? o.textContent.split(" · ")[0] : o.textContent)}</span>${n && n !== "0" ? `<em>${esc(t("place.n_cars", { n }))}</em>` : ""}${o.value === sel.value ? icon("check", 18) : ""}</button>`; }).join("")}</div></div>`;
    document.body.append(bg);
    requestAnimationFrame(() => bg.classList.add("in"));
    const close = () => { bg.classList.remove("in"); setTimeout(() => bg.remove(), 220); };
    bg.addEventListener("click", (e) => {
      if (e.target === bg || e.target.closest("[data-close]")) return close();
      const b = e.target.closest(".sheet-opt");
      if (b) { sel.value = b.dataset.v; sel.dispatchEvent(new Event("change", { bubbles: true })); sel.dispatchEvent(new Event("input", { bubbles: true })); close(); }
    });
    $(".sheet-find", bg)?.addEventListener("input", (e) => { const q = e.target.value.toLowerCase(); $$(".sheet-opt", bg).forEach((b) => b.classList.toggle("hidden", !b.textContent.toLowerCase().includes(q))); });
    $(".sheet-opt.on", bg)?.scrollIntoView({ block: "center" });
  },
};
/** O'zbek lotin tipografiyasi: o' g' -> oʻ gʻ (faqat ko'rsatish uchun, qiymat o'zgarmaydi) */
const uzTypo = (s) => String(s || "").replace(/([OoGg])'/g, "$1ʻ").replace(/(?<=[A-Za-zʻ])'(?=[A-Za-z])/g, "ʼ");

// ================= Rasm bo'lmaganda avtomobil illyustratsiyasi =================
const PALETTE = ["#1e40af", "#0e7490", "#b45309", "#be123c", "#4d7c0f", "#6d28d9", "#0f766e", "#334155"];
function carArt(car) {
  const c = PALETTE[(car.id || 0) % PALETTE.length];
  return `<svg viewBox="0 0 320 200" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${esc(carName(car))}">
    <defs><linearGradient id="g${car.id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f0f4ff"/><stop offset="1" stop-color="#e3eaff"/></linearGradient></defs>
    <rect width="320" height="200" fill="url(#g${car.id})"/><circle cx="262" cy="46" r="20" fill="#dbe5ff"/>
    <rect y="152" width="320" height="48" fill="#dfe5f3"/><rect x="0" y="171" width="320" height="2" fill="#cfd7ea"/>
    <path d="M52 140 L66 104 Q72 92 86 90 L128 86 Q140 70 160 66 L214 64 Q232 64 244 80 L262 104 Q276 108 278 122 L280 140 Z" fill="${c}"/>
    <path d="M136 88 Q146 74 162 72 L196 71 L196 88 Z M204 71 L214 71 Q228 72 236 86 L240 90 L204 90 Z" fill="#eef3ff" opacity=".92"/>
    <rect x="252" y="112" width="18" height="7" rx="3" fill="#fde68a"/><rect x="58" y="114" width="12" height="6" rx="3" fill="#fca5a5"/>
    <circle cx="100" cy="142" r="21" fill="#1f2937"/><circle cx="100" cy="142" r="9" fill="#cbd5e1"/>
    <circle cx="236" cy="142" r="21" fill="#1f2937"/><circle cx="236" cy="142" r="9" fill="#cbd5e1"/>
    <text x="16" y="30" font-family="Segoe UI, sans-serif" font-size="17" font-weight="700" fill="#1f2937">${esc(car.brand || "")}</text>
    <text x="16" y="50" font-family="Segoe UI, sans-serif" font-size="13" fill="#4b5563">${esc(car.model || "")}</text></svg>`;
}
const carImage = (car, path) => (path || car.cover) ? `<img src="${esc(path || car.cover)}" alt="${esc(carName(car))}" loading="lazy">` : carArt(car);
const HEART = `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 21s-7.5-4.6-9.6-9.3C.9 8.1 3.3 4.5 7 4.5c2 0 3.6 1.1 5 2.8 1.4-1.7 3-2.8 5-2.8 3.7 0 6.1 3.6 4.6 7.2C19.5 16.4 12 21 12 21z"/></svg>`;
const HEART_O = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 21s-7.5-4.6-9.6-9.3C.9 8.1 3.3 4.5 7 4.5c2 0 3.6 1.1 5 2.8 1.4-1.7 3-2.8 5-2.8 3.7 0 6.1 3.6 4.6 7.2C19.5 16.4 12 21 12 21z"/></svg>`;

/** Avtomobil kartochkasi — bosh sahifa, qidiruv, sevimlilar va tavsiyalarda bir xil */
/** Uzoq muddat chegirmasi (server bilan bir xil qoida): kunlar soniga mos eng katta pog'ona */
const discPct = (c, days) => Object.entries(c.discounts || {}).reduce((best, [k, p]) => (days >= +k ? Math.max(best, +p) : best), 0);
const maxDisc = (c) => Math.max(0, ...Object.values(c.discounts || {}).map(Number));
function carCard(c, { days = 0, qs = "", reason = false } = {}) {
  const href = `/car.html?id=${c.id}${qs}`;
  const own = Auth.user && Auth.user.id === c.owner_id;
  return `<article class="card car-card">
    <a class="car-thumb cover-link" href="${href}" tabindex="-1" aria-hidden="true">${carImage(c)}
      <span class="tags">${maxDisc(c) ? `<span class="tag tag-disc">${icon("tag", 12)} −${maxDisc(c)}%</span>` : ""}${c.fuel === "electric" ? `<span class="tag tag-electric">⚡ ${esc(t("fuel.electric"))}</span>` : ""}</span></a>
    ${own ? "" : `<button class="fav-btn ${c.is_favorite ? "on" : ""}" data-fav="${c.id}" aria-pressed="${!!c.is_favorite}" aria-label="${esc(t(c.is_favorite ? "fav.remove" : "fav.add"))}">${c.is_favorite ? HEART : HEART_O}</button>`}
    <div class="car-body">
      <a class="car-title" href="${href}">${esc(carName(c))} <span class="muted small">${esc(c.year)}</span></a>
      ${reason && c.reason ? `<span class="reason">${esc(t("reason." + c.reason))}</span>` : ""}
      <div class="car-meta"><span class="chip" title="${esc(Places.label(c.city, c.district))}">📍 ${esc(c.district ? uzTypo(c.district) : Places.regionName(c.city))}</span><span class="chip">${esc(t("trans." + c.transmission))}</span>
        <span class="chip">${esc(t("fuel." + c.fuel))}</span><span class="chip">${esc(t("car.seats_n", { n: c.seats }))}</span></div>
      <div class="car-foot">
        <div class="price">${money(c.price_per_day)} <small>${esc(t("car.per_day"))}</small>
          ${days ? `<div class="small muted">${esc(t("car.for_days", { n: days }))}: ${money(days * c.price_per_day * (100 - discPct(c, days)) / 100)}${discPct(c, days) ? ` <b class="disc-ink">−${discPct(c, days)}%</b>` : ""}</div>` : ""}</div>
        <div class="small">${c.rating ? `<span class="stars">★</span> <b>${c.rating}</b> <span class="muted">(${c.reviews_count})</span>` : `<span class="muted">${esc(t("car.new"))}</span>`}</div>
      </div>
      <div class="car-actions"><a class="btn btn-outline btn-sm" href="${href}">${esc(t("car.details"))}</a>
        ${own ? "" : `<a class="btn btn-sm" href="${href}#book" data-quickbook="${c.id}">${icon("calendar", 15)} ${esc(t("car.book"))}</a>`}</div>
    </div></article>`;
}

// Sevimlilar tugmasi — barcha sahifalarda bitta delegat
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-fav]");
  if (!b) return;
  e.preventDefault();
  if (!Auth.user) { location.href = "/auth.html?next=" + encodeURIComponent(location.pathname + location.search) + "#login"; return; }
  const on = b.classList.contains("on");
  try {
    await api(`/api/favorites/${b.dataset.fav}`, { method: on ? "DELETE" : "PUT" });
    $$(`[data-fav="${b.dataset.fav}"]`).forEach((x) => {
      x.classList.toggle("on", !on); x.innerHTML = on ? HEART_O : HEART; x.setAttribute("aria-pressed", String(!on));
      x.setAttribute("aria-label", t(on ? "fav.add" : "fav.remove"));
    });
    toast(t(on ? "fav.removed" : "fav.added"), "ok");
    document.dispatchEvent(new CustomEvent("favchange"));
  } catch (err) { toast(err.message, "error"); }
});

// ================= Toast, modal, formalar =================
function toast(msg, type = "") {
  if (!msg) return;
  let box = $(".toasts");
  if (!box) { box = document.createElement("div"); box.className = "toasts"; box.setAttribute("aria-live", "polite"); document.body.append(box); }
  const el = document.createElement("div"); el.className = "toast " + type; el.textContent = msg; box.append(el);
  setTimeout(() => el.remove(), 4200);
}
function confirmBox(text, okText, danger = false) {
  return new Promise((resolve) => {
    const bg = document.createElement("div"); bg.className = "modal-bg";
    bg.innerHTML = `<div class="modal card card-pad" role="dialog" aria-modal="true"><p style="margin-top:0;white-space:pre-line">${esc(text)}</p>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-outline" data-v="0">${esc(t("common.cancel"))}</button>
      <button class="btn ${danger ? "btn-danger" : ""}" data-v="1">${esc(okText || t("common.yes"))}</button></div></div>`;
    bg.addEventListener("click", (e) => { const v = e.target.dataset.v; if (v !== undefined || e.target === bg) { bg.remove(); resolve(v === "1"); } });
    document.body.append(bg); $("[data-v='1']", bg).focus();
  });
}
function showFieldErrors(form, err) {
  $$(".err", form).forEach((e) => e.remove());
  $$("[aria-invalid]", form).forEach((e) => e.removeAttribute("aria-invalid"));
  (err.errors || []).forEach((e) => {
    const input = e.field && form.querySelector(`[name="${CSS.escape(e.field)}"]`);
    const field = input?.closest(".field");
    if (field) { input.setAttribute("aria-invalid", "true"); const d = document.createElement("div"); d.className = "err"; d.textContent = e.msg; field.append(d); }
  });
}
function formData(form) {
  const o = {};
  new FormData(form).forEach((v, k) => {
    const el = form.elements[k];
    if (el && el.dataset?.money !== undefined) { o[k] = String(moneyVal(v) ?? ""); return; }
    o[k] = typeof v === "string" ? v.trim() : v;
  });
  return o;
}
async function withLoading(btn, fn) {
  btn.disabled = true; btn.classList.add("loading");
  try { return await fn(); } finally { btn.disabled = false; btn.classList.remove("loading"); }
}

// ================= Autentifikatsiya =================
const Auth = {
  user: null,
  async load() {
    try { this.user = (await api("/api/auth/me")).user; } catch { this.user = null; }
    return this.user;
  },
  async logout() { await api("/api/auth/logout", { method: "POST" }).catch(() => {}); location.href = "/"; },
  async setMode(mode) {
    const { user } = await api("/api/me/mode", { method: "PATCH", body: { mode } });
    this.user = user;
    document.dispatchEvent(new CustomEvent("modechange", { detail: mode }));
    return user;
  },
};

async function guard(...roles) {
  const u = Auth.user;
  if (!u) { location.href = "/auth.html?next=" + encodeURIComponent(location.pathname + location.search + location.hash) + "#login"; throw new Error("auth"); }
  if (roles.length && !roles.includes(u.role)) { location.href = "/dashboard.html"; throw new Error("role"); }
  return u;
}

/** Parolni brauzer/telefon xotirasiga saqlash (Chrome, Android: Credential Management API; Safari forma orqali o'zi taklif qiladi) */
const Creds = {
  async save(id, password, name) {
    try { if (window.PasswordCredential && id && password) await navigator.credentials.store(new PasswordCredential({ id, password, name: name || id })); } catch { /* foydalanuvchi rad etdi */ }
  },
  async fill(loginEl, pwEl) {
    try {
      if (!window.PasswordCredential || loginEl.value) return;
      const c = await navigator.credentials.get({ password: true, mediation: "optional" });
      if (c && c.password) { loginEl.value = c.id; pwEl.value = c.password; loginEl.dispatchEvent(new Event("input")); }
    } catch { /* qo'llab-quvvatlanmaydi */ }
  },
};

/** Barmoq izi / yuz bilan kirish (WebAuthn passkey) */
const Passkey = {
  supported: () => !!(window.PublicKeyCredential && navigator.credentials?.create && isSecureContext),
  enabledHere() { try { return localStorage.getItem("cr.passkey") === "1"; } catch { return false; } },
  b64: (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""),
  unb64: (s) => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), (c) => c.charCodeAt(0)),
  async canPlatform() { try { return this.supported() && await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable(); } catch { return false; } },
  async register(name = "") {
    const o = await api("/api/passkeys/register/options", { method: "POST" });
    const cred = await navigator.credentials.create({ publicKey: {
      ...o, challenge: this.unb64(o.challenge), user: { ...o.user, id: this.unb64(o.user.id) },
      excludeCredentials: o.excludeCredentials.map((c) => ({ ...c, id: this.unb64(c.id) })) } });
    const r = cred.response;
    const res = await api("/api/passkeys/register", { method: "POST", body: { id: cred.id, name,
      clientDataJSON: this.b64(r.clientDataJSON), attestationObject: this.b64(r.attestationObject) } });
    try { localStorage.setItem("cr.passkey", "1"); } catch { /* */ }
    return res;
  },
  async login() {
    const o = await api("/api/passkeys/login/options", { method: "POST" });
    const cred = await navigator.credentials.get({ publicKey: { challenge: this.unb64(o.challenge), rpId: o.rpId, timeout: o.timeout, userVerification: "required", allowCredentials: [] } });
    const r = cred.response;
    const res = await api("/api/passkeys/login", { method: "POST", body: { id: cred.id, clientDataJSON: this.b64(r.clientDataJSON),
      authenticatorData: this.b64(r.authenticatorData), signature: this.b64(r.signature) } });
    try { localStorage.setItem("cr.passkey", "1"); } catch { /* */ }
    return res;
  },
  /** Parol bilan kirgandan yoki ro'yxatdan o'tgandan keyin: keyingi sahifada bank ilovalaridagidek "Barmoq izini ulaysizmi?" */
  offerAfterLogin(next) {
    if (!this.supported() || this.enabledHere()) return next;
    try { sessionStorage.setItem("cr.pkOffer", "1"); localStorage.removeItem("cr.pkLater"); } catch { /* */ }
    return next;
  },
  async maybeOffer() {
    if (!IS_APP || !Auth.user || this.enabledHere() || !this.supported()) return;
    let want = false;
    try {
      want = sessionStorage.getItem("cr.pkOffer") === "1";
      sessionStorage.removeItem("cr.pkOffer");
      // Telefonda: kirgan foydalanuvchiga ham vaqti-vaqti bilan (rad etgan bo'lsa — 3 kundan keyin) eslatamiz
      const later = +(localStorage.getItem("cr.pkLater") || 0);
      if (!want && matchMedia("(pointer: coarse)").matches && Date.now() - later > 3 * 864e5 && !sessionStorage.getItem("cr.pkAsked")) want = true;
    } catch { return; }
    if (!want || !(await this.canPlatform())) return;
    try { sessionStorage.setItem("cr.pkAsked", "1"); } catch { /* */ }
    // Serverda shu akkauntga allaqachon barmoq izi ulangan bo'lsa (masalan, boshqa brauzerdan) — so'ramaymiz
    try { const { items } = await api("/api/passkeys"); if (items.length && /(iPhone|Android)/.test(navigator.userAgent) && items.some((p) => navigator.userAgent.includes(p.name))) return; } catch { /* */ }
    const bg = document.createElement("div"); bg.className = "sheet-bg pk-sheet";
    bg.innerHTML = `<div class="sheet pk-offer" role="dialog" aria-modal="true"><div class="sheet-grab"></div>
      <div class="pk-big">${icon("finger", 44)}</div>
      <h3>${esc(t("pk.offer_t"))}</h3><p class="muted">${esc(t("pk.offer_b"))}</p>
      <button class="btn btn-block btn-lg" id="pkYes">${icon("finger", 18)} ${esc(t("pk.enable_now"))}</button>
      <button class="btn btn-block btn-outline" data-close>${esc(t("pk.later"))}</button></div>`;
    document.body.append(bg);
    requestAnimationFrame(() => bg.classList.add("in"));
    const close = () => { bg.classList.remove("in"); setTimeout(() => bg.remove(), 220); };
    bg.addEventListener("click", async (e) => {
      if (e.target === bg || e.target.closest("[data-close]")) { try { localStorage.setItem("cr.pkLater", String(Date.now())); } catch { /* */ } close(); return; }
      const yes = e.target.closest("#pkYes");
      if (yes) {
        yes.disabled = true;
        try {
          await this.register();   // telefonning o'z barmoq izi / Face ID oynasi chiqadi
          bg.querySelector(".sheet").innerHTML = `<div class="pk-big ok">${icon("check", 44)}</div><h3>${esc(t("pk.enabled"))}</h3><p class="muted">${esc(t("pk.enabled_b"))}</p>
            <button class="btn btn-block" data-close>${esc(t("common.done"))}</button>`;
        } catch (err) { yes.disabled = false; if (err.name !== "NotAllowedError") toast(err.message || t("pk.failed"), "error"); }
      }
    });
  },
};

/** "Ilovani o'rnatish" (PWA): Android/Chrome — tizim oynasi; iPhone — qo'llanma */
const Install = {
  evt: null,
  standalone: () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true,
  ios: () => /iphone|ipad|ipod/i.test(navigator.userAgent),
  available() { return !this.standalone() && (this.evt || this.ios()); },
  async run() {
    if (this.evt) { this.evt.prompt(); await this.evt.userChoice.catch(() => null); this.evt = null; renderNavInner(); return; }
    const bg = document.createElement("div"); bg.className = "modal-bg";
    bg.innerHTML = `<div class="modal card card-pad" role="dialog" aria-modal="true"><h3>${icon("download", 18)} ${esc(t("pwa.title"))}</h3>
      <ol class="pwa-steps"><li>${esc(t("pwa.ios1"))}</li><li>${esc(t("pwa.ios2"))}</li><li>${esc(t("pwa.ios3"))}</li></ol>
      <div class="row" style="justify-content:flex-end"><button class="btn" data-close>${esc(t("common.close"))}</button></div></div>`;
    document.body.append(bg);
    bg.addEventListener("click", (e) => { if (e.target === bg || e.target.closest("[data-close]")) bg.remove(); });
  },
};
window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); Install.evt = e; if (typeof renderNavInner === "function" && $(".topbar")) renderNavInner(); });

/** Foydalanish yo'riqnomasi: har bo'limda "?" — o'sha bo'limga tegishli qism ochiladi (kompyuter va telefonda) */
const Help = {
  TOPICS: ["start", "search", "book", "dates", "bookings", "contract", "handover", "pay", "cards", "docs", "add_car", "discounts", "owner", "reports", "messages", "advisor", "security", "admin"],
  ICONS: { start: "home", search: "search", book: "calendar", dates: "calendar", bookings: "list", contract: "doc", handover: "key", pay: "card", cards: "card",
    docs: "idcard", add_car: "plus", discounts: "tag", owner: "car", reports: "chart", messages: "chat", advisor: "spark", security: "finger", admin: "shield" },
  /** Joriy sahifaga mos bo'lim */
  context() {
    const p = location.pathname, h = location.hash.slice(1).split("/")[0];
    if (p.startsWith("/admin")) return h === "analytics" ? "reports" : h === "contracts" ? "contract" : h === "documents" ? "docs" : "admin";
    if (p.startsWith("/car-form")) return "add_car";
    if (p.startsWith("/car.html")) return "book";
    if (p.startsWith("/cars")) return "search";
    if (p.startsWith("/contract")) return "contract";
    if (p.startsWith("/handover")) return "handover";
    if (p.startsWith("/pay") || p.startsWith("/receipt")) return "pay";
    if (p.startsWith("/messages")) return "messages";
    if (p.startsWith("/advisor")) return "advisor";
    if (p.startsWith("/settings")) return { cards: "cards", documents: "docs", security: "security" }[h] || "security";
    if (p.startsWith("/dashboard")) return { bookings: "bookings", analytics: "reports", cars: "owner", calendar: "owner", earnings: "owner", payments: "pay" }[h] || (Auth.user?.active_mode === "owner" ? "owner" : "bookings");
    return "start";
  },
  button(topic) { return `<button type="button" class="help-btn" data-help="${topic}" aria-label="${esc(t("help.open"))}" title="${esc(t("help.open"))}">?</button>`; },
  open(topic = this.context()) {
    $("#helpDrawer")?.remove();
    const el = document.createElement("div"); el.id = "helpDrawer"; el.className = "help-wrap";
    const steps = (k) => t(`help.${k}.b`).split("|").map((x) => `<li>${esc(x.trim())}</li>`).join("");
    el.innerHTML = `<div class="help-scrim" data-close></div><aside class="help-drawer" role="dialog" aria-modal="true" aria-labelledby="helpTitle">
      <header><span class="help-badge">?</span><div><small>${esc(t("help.guide"))}</small><h3 id="helpTitle"></h3></div><button class="icon-btn ghost" data-close aria-label="${esc(t("common.close"))}">${icon("close")}</button></header>
      <nav class="help-topics">${this.TOPICS.filter((k) => k !== "admin" || Auth.user?.role === "admin").map((k) => `<button type="button" data-topic="${k}">${icon(this.ICONS[k], 15)}<span>${esc(t(`help.${k}.t`))}</span></button>`).join("")}</nav>
      <div class="help-body" id="helpBody"></div></aside>`;
    document.body.append(el);
    const show = (k) => {
      $("#helpTitle", el).textContent = t(`help.${k}.t`);
      $("#helpBody", el).innerHTML = `<p class="help-lead">${esc(t(`help.${k}.l`))}</p><ol class="help-steps">${steps(k)}</ol>`;
      $$("[data-topic]", el).forEach((b) => b.classList.toggle("on", b.dataset.topic === k));
      $(`[data-topic="${k}"]`, el)?.scrollIntoView({ block: "nearest", inline: "center" });
    };
    show(this.TOPICS.includes(topic) ? topic : "start");
    requestAnimationFrame(() => el.classList.add("in"));
    el.addEventListener("click", (e) => {
      const tb = e.target.closest("[data-topic]"); if (tb) show(tb.dataset.topic);
      if (e.target.closest("[data-close]")) { el.classList.remove("in"); setTimeout(() => el.remove(), 250); }
    });
    document.addEventListener("keydown", function esc_(e) { if (e.key === "Escape") { el.remove(); document.removeEventListener("keydown", esc_); } });
  },
};
document.addEventListener("click", (e) => { const b = e.target.closest("[data-help]"); if (b) { e.preventDefault(); Help.open(b.dataset.help || undefined); } });

/** Sayt (brauzer) orqali: har yangi tashrifda email va parol qayta so'raladi.
    Tashrif = shu brauzer oynasidagi sessiya; boshqa joydagi havoladan (Telegram, qidiruv...) kelinsa — yangi tashrif. */
const Visit = {
  mark() { try { sessionStorage.setItem("cr.visit", "1"); } catch { /* */ } },
  mustRelogin() {
    if (location.pathname.startsWith("/auth")) return false;
    let inVisit = false;
    try { inVisit = sessionStorage.getItem("cr.visit") === "1"; } catch { return false; }
    const fromHere = document.referrer && new URL(document.referrer).origin === location.origin;
    return !inVisit && !fromHere;
  },
  async relogin() {
    await api("/api/auth/logout", { method: "POST" }).catch(() => {});
    location.replace("/auth.html?next=" + encodeURIComponent(location.pathname + location.search + location.hash) + "&again=1#login");
  },
};

/** Ilova ekran qulfi: bank ilovalaridagidek PIN kod (4 raqam) va barmoq izi.
    Ro'yxatdan o'tgan/kirgan zahoti PIN o'rnatish majburiy; ilova har ochilganda va 1 daqiqadan ko'p fonda turgach — qulf. */
const AppLock = {
  LOCK_AFTER_MS: 60 * 1000,
  device() {
    try {
      let d = localStorage.getItem("cr.dev");
      if (!d) { const a = new Uint8Array(18); crypto.getRandomValues(a); d = "d" + [...a].map((x) => x.toString(16).padStart(2, "0")).join(""); localStorage.setItem("cr.dev", d); }
      return d;
    } catch { return "dnostorage00000000000"; }
  },
  async check(user) {
    let st;
    try { st = await api("/api/me/pin?device_id=" + this.device()); } catch { document.documentElement.classList.remove("app-locked"); return; }
    try { st.set ? localStorage.setItem("cr.pinUser", String(user.id)) : localStorage.removeItem("cr.pinUser"); } catch { /* */ }
    if (!st.set) { await this.setup(true); Passkey.maybeOffer(); return; }
    let unlocked = false;
    try { unlocked = sessionStorage.getItem("cr.unlocked") === String(user.id) && Date.now() - +(sessionStorage.getItem("cr.hiddenAt") || 0) < this.LOCK_AFTER_MS; } catch { /* */ }
    if (!unlocked) await this.lock(user);
    document.documentElement.classList.remove("app-locked");
    this.watch(user);
  },
  watch(user) {
    if (this._w) return; this._w = true;
    document.addEventListener("visibilitychange", () => {
      try {
        if (document.hidden) sessionStorage.setItem("cr.hiddenAt", String(Date.now()));
        else if (Date.now() - +(sessionStorage.getItem("cr.hiddenAt") || Date.now()) > this.LOCK_AFTER_MS) { sessionStorage.removeItem("cr.unlocked"); this.lock(user); }
      } catch { /* */ }
    });
  },
  pad(title, sub, { bio = false, footer = "" } = {}) {
    const el = document.createElement("div"); el.className = "lock-screen";
    el.innerHTML = `<div class="lock-box"><div class="lock-logo"><span class="logo-mark">${LOGO}</span></div>
      <h2>${esc(title)}</h2><p class="lock-sub">${esc(sub)}</p>
      <div class="lock-dots"><i></i><i></i><i></i><i></i></div><p class="lock-err" aria-live="assertive"></p>
      <div class="lock-keys">${[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => `<button type="button" data-k="${n}">${n}</button>`).join("")}
        ${bio ? `<button type="button" class="lk-bio" data-bio aria-label="${esc(t("pk.login"))}">${icon("finger", 28)}</button>` : "<span></span>"}
        <button type="button" data-k="0">0</button><button type="button" class="lk-del" data-del aria-label="${esc(t("common.delete"))}">⌫</button></div>
      ${footer}</div>`;
    document.body.append(el);
    requestAnimationFrame(() => el.classList.add("in"));
    return el;
  },
  /** 4 xonali kod kiritish: ekrandagi tugmalar yoki klaviatura */
  input(el, onDone) {
    let v = "";
    const dots = $$(".lock-dots i", el);
    const paint = () => dots.forEach((d, i) => d.classList.toggle("on", i < v.length));
    const push = (k) => { if (v.length >= 4) return; v += k; paint(); if (v.length === 4) setTimeout(() => { const x = v; v = ""; onDone(x, () => { paint(); }); paint(); }, 120); };
    el.addEventListener("click", (e) => { const b = e.target.closest("[data-k]"); if (b) { navigator.vibrate?.(8); push(b.dataset.k); } if (e.target.closest("[data-del]")) { v = v.slice(0, -1); paint(); } });
    const key = (e) => { if (/^\d$/.test(e.key)) push(e.key); else if (e.key === "Backspace") { v = v.slice(0, -1); paint(); } };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  },
  shake(el, msg) {
    $(".lock-err", el).textContent = msg || "";
    const d = $(".lock-dots", el); d.classList.remove("bad"); void d.offsetWidth; d.classList.add("bad"); navigator.vibrate?.([40, 40, 40]);
  },
  close(el) { el.classList.remove("in"); setTimeout(() => el.remove(), 250); },
  /** PIN o'rnatish (majburiy): ikki marta kiritiladi */
  setup(mandatory) {
    return new Promise((resolve) => {
      document.documentElement.classList.remove("app-locked");
      const el = this.pad(t("lock.set_t"), t("lock.set_sub"), { footer: mandatory ? `<p class="lock-note">${icon("shield", 14)} ${esc(t("lock.why"))}</p>` : `<button type="button" class="linkbtn lock-link" data-cancel>${esc(t("common.cancel"))}</button>` });
      let first = null;
      const off = this.input(el, async (pin) => {
        if (!first) {
          if (/^(\d)\1{3}$/.test(pin) || "0123456789".includes(pin) || "9876543210".includes(pin)) { this.shake(el, t("lock.weak")); return; }
          first = pin; $("h2", el).textContent = t("lock.repeat_t"); $(".lock-sub", el).textContent = t("lock.repeat_sub"); $(".lock-err", el).textContent = ""; return;
        }
        if (pin !== first) { first = null; $("h2", el).textContent = t("lock.set_t"); $(".lock-sub", el).textContent = t("lock.set_sub"); this.shake(el, t("lock.mismatch")); return; }
        try {
          await api("/api/me/pin", { method: "PUT", body: { device_id: this.device(), pin } });
          try { localStorage.setItem("cr.pinUser", String(Auth.user.id)); sessionStorage.setItem("cr.unlocked", String(Auth.user.id)); } catch { /* */ }
          off(); this.close(el); toast(t("lock.saved"), "ok"); resolve(true);
        } catch (err) { first = null; $("h2", el).textContent = t("lock.set_t"); this.shake(el, err.message); }
      });
      el.querySelector("[data-cancel]")?.addEventListener("click", () => { off(); this.close(el); resolve(false); });
    });
  },
  /** Qulf ekrani: PIN yoki barmoq izi */
  lock(user) {
    if ($(".lock-screen.unlock")) return Promise.resolve();
    return new Promise((resolve) => {
      const bio = Passkey.enabledHere() && Passkey.supported();
      const el = this.pad(t("lock.hello", { name: (user.full_name || "").split(" ")[0] }), t(bio ? "lock.enter_or_bio" : "lock.enter"),
        { bio, footer: `<button type="button" class="linkbtn lock-link" data-other>${esc(t("lock.other"))}</button>` });
      el.classList.add("unlock");
      const done = () => { try { sessionStorage.setItem("cr.unlocked", String(user.id)); sessionStorage.removeItem("cr.hiddenAt"); } catch { /* */ } off(); this.close(el); document.documentElement.classList.remove("app-locked"); resolve(); };
      const off = this.input(el, async (pin) => {
        try { await api("/api/me/pin/verify", { method: "POST", body: { device_id: this.device(), pin } }); done(); }
        catch (err) {
          if (err.status === 403) { toast(err.message, "error"); try { localStorage.removeItem("cr.pinUser"); } catch { /* */ } location.href = "/auth.html#login"; return; }
          this.shake(el, err.message);
        }
      });
      const tryBio = async () => { try { await Passkey.login(); done(); } catch (err) { if (err.name !== "NotAllowedError" && err.name !== "AbortError") this.shake(el, err.message); } };
      el.querySelector("[data-bio]")?.addEventListener("click", tryBio);
      el.querySelector("[data-other]").addEventListener("click", () => Auth.logout());
      if (bio) setTimeout(tryBio, 350);
    });
  },
};

/** Har sahifa boshida: foydalanuvchi, til, header va footer */
async function boot(active = "", { bare = false } = {}) {
  const [user] = await Promise.all([Auth.load(), I18N.load(I18N.initial(null)), Places.load().catch(() => null)]);
  const lang = I18N.initial(user?.lang);
  if (lang !== I18N.lang) await I18N.load(lang);
  if (user && user.lang !== I18N.lang) user.lang = I18N.lang;
  Nav.active = active; Nav.bare = bare;
  renderNav();
  applyI18n();
  applyHints();
  DateField.enhance();
  applyMasks();
  renderFooter();
  mustChangeBanner(user);
  if (user && !IS_APP && Visit.mustRelogin()) { await Visit.relogin(); throw new Error("relogin"); }
  if (user) Visit.mark();
  if (user && IS_APP) await AppLock.check(user);
  return user;
}

/** Admin vaqtinchalik parol bergan bo'lsa — har sahifada yangi parol o'rnatishni eslatadi */
function mustChangeBanner(user) {
  if (!user?.must_change_pw || document.getElementById("pwBanner")) return;
  const main = document.querySelector("main") || document.body;
  main.insertAdjacentHTML("afterbegin", `<div class="notice pw-banner" id="pwBanner" role="alert">${icon("lock", 16)} <span>${esc(t("pw.must_change"))}</span>
    <a class="btn btn-sm" href="/settings.html#security">${esc(t("pw.must_change_btn"))}</a></div>`);
}

// ================= Ilova qobig'i: chap panel (desktop), yuqori panel, pastki tablar (telefon) =================
const LOGO = `<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 17h14M6 17l1.5-5.5A2 2 0 0 1 9.4 10h5.2a2 2 0 0 1 1.9 1.5L18 17"/><circle cx="8" cy="17.5" r="1.6"/><circle cx="16" cy="17.5" r="1.6"/><path d="M4 13h2M18 13h2"/></svg>`;
const ICON_PATHS = {
  moon: "M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z",
  sun: "M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  chevron: "M9 6l6 6-6 6",
  finger: "M6.8 5.2A8.5 8.5 0 0 1 20.5 12M3.6 15.5A8.5 8.5 0 0 1 4.6 8.6M8 12a4 4 0 0 1 8 0v1.5a13 13 0 0 0 .9 4.5M12 12v2a14 14 0 0 1-2.5 7.5M6.2 18.6A12 12 0 0 0 8 12M15 21.2a16 16 0 0 0 1.2-3",
  help: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM9.1 9a3 3 0 0 1 5.8 1c0 2-3 2.5-3 4.5M12 17.5h.01",
  tag: "M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8zM7.5 7.5h.01",
  image: "M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zM3 16l5-5 4 4 3-3 6 6M15.5 9.5h.01",
  drop: "M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z",
  home: "M3 11.5 12 4l9 7.5M5 10v10h5v-6h4v6h5V10",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
  info: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v6M12 7.5v.5",
  grid: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  list: "M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01",
  heart: "M12 20s-7-4.4-9-9C1.6 7.6 4 4.5 7.3 4.5c2 0 3.5 1.1 4.7 2.7 1.2-1.6 2.7-2.7 4.7-2.7 3.3 0 5.7 3.1 4.3 6.5-2 4.6-9 9-9 9z",
  chat: "M4 5h16v11H9l-5 4z",
  car: "M5 17h14M6 17l1.5-5.5A2 2 0 0 1 9.4 10h5.2a2 2 0 0 1 1.9 1.5L18 17M8 17.5v.5M16 17.5v.5M4 13h2M18 13h2",
  plus: "M12 5v14M5 12h14",
  calendar: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  wallet: "M3 7h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H3zM3 7V5a2 2 0 0 1 2-2h11M16 13.5h.01",
  star: "M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z",
  bell: "M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0",
  gear: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  users: "M16 20v-1.5a3.5 3.5 0 0 0-3.5-3.5h-5A3.5 3.5 0 0 0 4 18.5V20M10 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM20 20v-1.5a3.5 3.5 0 0 0-2.5-3.4M15.5 4.2a3.5 3.5 0 0 1 0 6.6",
  flag: "M5 21V4M5 4h11l-2 4 2 4H5",
  card: "M3 6h18v12H3zM3 10h18M7 15h3",
  chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  log: "M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h5",
  logout: "M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10",
  menu: "M4 6h16M4 12h16M4 18h16",
  close: "M6 6l12 12M18 6 6 18",
  globe: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  swap: "M7 7h12l-3-3M17 17H5l3 3",
  shield: "M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z",
  camera: "M4 8h3l2-3h6l2 3h3v11H4zM12 10a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z",
  check: "M5 12.5 10 17l9-10",
  phone: "M5 3h4l2 5-2.5 1.5a11 11 0 0 0 6 6L16 13l5 2v4a2 2 0 0 1-2 2A17 17 0 0 1 3 5a2 2 0 0 1 2-2z",
  mail: "M3 5h18v14H3zM3 6l9 7 9-7",
  lock: "M6 11h12v10H6zM8 11V7a4 4 0 0 1 8 0v4",
  receipt: "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h3",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z",
  eyeoff: "M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6C3.8 8.4 2 12 2 12s3.5 7 10 7c1.6 0 3-.4 4.3-1M9.9 9.9a3 3 0 0 0 4.2 4.2",
  arrowl: "M15 5l-7 7 7 7", arrowr: "M9 5l7 7-7 7",
  fuel: "M4 21V5a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v16M3 21h12M7 8h4M14 10h2a2 2 0 0 1 2 2v4a1.5 1.5 0 0 0 3 0V9l-3-3",
  seat: "M7 3.5a1.5 1.5 0 0 1 3 0V12h5.5a2 2 0 0 1 2 2v6M7 3.5V14a2 2 0 0 0 2 2h7M5 21h13",
  gauge: "M12 14l4-4M3.5 18a9 9 0 1 1 17 0",
  pin: "M12 21s-7-6.2-7-12a7 7 0 0 1 14 0c0 5.8-7 12-7 12zM12 11.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
  road: "M5 21 9 3M19 21 15 3M12 5v2M12 11v2M12 17v2",
  palette: "M12 3a9 9 0 1 0 0 18c1 0 1.5-.8 1.5-1.5 0-1-.8-1.3-.8-2.2 0-.9.7-1.3 1.6-1.3H16a5 5 0 0 0 5-5c0-4.4-4-8-9-8zM7.5 11.5h.01M10 7.5h.01M15 7.5h.01",
  engine: "M4 10h2V8h3V6h6v2h2l2 3h2v5h-2l-2 3H9l-2-2H6v-3H4z",
  doc: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6",
  pen: "M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4",
  qr: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 14h2v2h-2zM14 18h2v2h-2zM18 18h2v2h-2z",
  idcard: "M3 5h18v14H3zM8.5 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM5.5 16a3 3 0 0 1 6 0M14 9h4M14 13h4",
  key: "M15 7a4 4 0 1 0-3.4 6L4 20.5V21h3v-2h2v-2h2l1.6-1.6A4 4 0 0 0 15 7zM16 7h.01",
  dots: "M12 5h.01M12 12h.01M12 19h.01",
  trend: "M3 17l6-6 4 4 8-8M15 7h6v6",
  dollar: "M12 3v18M16.5 7.5c0-1.9-2-3-4.5-3S7.5 5.6 7.5 7.5s2 2.6 4.5 3.1 4.5 1.4 4.5 3.4-2 3.5-4.5 3.5-4.5-1.3-4.5-3.3",
  spark: "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18",
  download: "M12 4v11M7 10l5 5 5-5M5 20h14",
  print: "M7 9V3h10v6M7 17H4v-7h16v7h-3M7 14h10v7H7z",
  bulb: "M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z",
};
const icon = (name, size = 20) => `<svg class="ico" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ICON_PATHS[name] || ""}"/></svg>`;

/** Kabinet bo'limlari — chap panel va kabinet sahifasi bitta ro'yxatdan foydalanadi */
const CABINET = {
  renter: [["overview", "nav.tab_overview", "grid"], ["bookings", "dash.my_bookings", "list"], ["payments", "dash.my_payments", "card"],
           ["favorites", "dash.favorites", "heart"], ["analytics", "rep.title", "chart"], ["disputes", "nav.disputes", "flag"]],
  owner: [["overview", "dash.owner_overview", "grid"], ["cars", "dash.my_cars", "car"], ["bookings", "dash.requests", "list"],
          ["calendar", "dash.calendar", "calendar"], ["earnings", "dash.earnings", "wallet"], ["analytics", "rep.title", "chart"],
          ["reviews", "dash.reviews", "star"], ["disputes", "nav.disputes", "flag"]],
};
// Admin menyusi guruhlarga bo'lingan: kamroq ko'z yugurtirib kerakli bo'limni topish oson
const ADMIN_GROUPS = [
  ["admin.g_main", [["stats", "admin.dashboard", "grid"], ["analytics", "rep.title", "chart"]]],
  ["admin.g_people", [["users", "admin.users", "users"], ["documents", "docs.admin_tab", "idcard"]]],
  ["admin.g_rentals", [["cars", "admin.cars", "car"], ["bookings", "admin.bookings", "list"], ["contracts", "ctr.admin_tab", "doc"]]],
  ["admin.g_money", [["payments", "admin.payments", "card"], ["finance", "admin.finance", "wallet"]]],
  ["admin.g_issues", [["disputes", "admin.disputes", "shield"], ["reports", "admin.reports", "flag"], ["reviews", "admin.reviews", "star"]]],
  ["admin.g_system", [["channels", "admin.channels", "mail"], ["audit", "admin.audit", "log"]]],
];
const ADMIN_TABS = ADMIN_GROUPS.flatMap(([, tabs]) => tabs);

const Nav = { active: "", poller: null, bare: false, summary: {} };

function avatarHtml(u, cls = "") {
  return u?.avatar ? `<img class="avatar ${cls}" src="${esc(u.avatar)}" alt="">` : `<span class="avatar ${cls}">${esc(initials(u?.full_name))}</span>`;
}

function renderNav() {
  if (!$(".topbar")) {
    document.body.insertAdjacentHTML("afterbegin", `${Nav.bare ? "" : `<aside class="side" id="side" aria-label=""></aside><div class="side-scrim" id="sideScrim"></div>`}
      <header class="topbar"></header>`);
    if (!Nav.bare) document.body.insertAdjacentHTML("beforeend", `<nav class="tabbar" id="tabbar"></nav>`);
    document.body.classList.add(Nav.bare ? "is-bare" : "has-side");
    $("#sideScrim")?.addEventListener("click", () => toggleSide(false));
    window.addEventListener("hashchange", markActive);
  }
  renderNavInner();
  if (Auth.user && !Nav.poller) { pollSummary(); Nav.poller = setInterval(pollSummary, 10000); }
}

function toggleSide(open) {
  document.body.classList.toggle("side-open", open);
  $("#side")?.setAttribute("aria-hidden", open ? "false" : "");
}

function sideLink(href, key, ico, { badge = "", cls = "" } = {}) {
  return `<a href="${href}" class="side-link ${cls}" data-href="${href}" data-tip="${esc(t(key))}">${icon(ico)}<span>${esc(t(key))}</span>${badge ? `<span class="cnt hidden" id="${badge}"></span>` : ""}</a>`;
}

/** Ko'rinish sozlamalari (shu brauzerda): tungi rejim, chap panel yig'ilgan/ochiq, yopilgan bo'limlar */
const Theme = {
  get(k, d) { try { return localStorage.getItem("cr." + k) ?? d; } catch { return d; } },
  put(k, v) { try { localStorage.setItem("cr." + k, v); } catch { /* maxfiy rejim */ } },
  isDark() { return document.documentElement.dataset.theme === "dark"; },
  set(mode) {
    document.documentElement.dataset.theme = mode; this.put("theme", mode);
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", mode === "dark" ? "#0b1220" : "#1e3a8a");
  },
  init() {
    const saved = this.get("theme", "");
    document.documentElement.dataset.theme = saved === "dark" ? "dark" : "light";   // standart — yorug' (foydalanuvchi o'zi yoqadi)
    if (this.get("rail", "0") === "1") document.body.classList.add("side-rail");
  },
  collapse(on) { document.body.classList.toggle("side-rail", on); this.put("rail", on ? "1" : "0"); },
  closedGroups() { return (this.get("closed", "") || "").split(",").filter(Boolean); },
  closeGroup(id, closed) { const s = new Set(this.closedGroups()); closed ? s.add(id) : s.delete(id); this.put("closed", [...s].join(",")); },
};
Theme.init();
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) && $("#sideSearch") && innerWidth >= 1024) {
    e.preventDefault(); if (document.body.classList.contains("side-rail")) Theme.collapse(false); $("#sideSearch").focus();
  }
});

function renderNavInner() {
  const u = Auth.user;
  const admin = u?.role === "admin", mode = u?.active_mode || "renter";
  // ---- yuqori panel ----
  const top = $(".topbar");
  if (top) {
    top.innerHTML = `${Nav.bare ? "" : `<button class="icon-btn ghost only-mobile" id="sideOpen" aria-label="${esc(t("nav.menu"))}">${icon("menu", 22)}</button>`}
      <a href="/" class="logo ${Nav.bare ? "" : "only-mobile"}"><span class="logo-mark">${LOGO}</span><span>Car<b>Rent</b></span></a>
      ${u && !admin && !Nav.bare ? `<span class="mode-chip only-desktop">${icon(mode === "owner" ? "car" : "user", 16)}${esc(t("mode." + mode))}</span>` : ""}
      <span class="spacer"></span>
      ${Nav.bare ? "" : `<button class="icon-btn ghost help-top" data-help="" aria-label="${esc(t("help.open"))}" title="${esc(t("help.open"))}">${icon("help")}</button>`}
      <div class="menu-wrap"><button class="icon-btn ghost" id="langBtn" aria-haspopup="true" aria-label="${esc(t("nav.language"))}">${icon("globe")}<span class="lang-code">${I18N.lang.toUpperCase()}</span></button></div>
      ${u ? `<div class="menu-wrap"><button class="icon-btn ghost" id="bellBtn" aria-label="${esc(t("nav.notifications"))}">${icon("bell")}<span class="badge-dot hidden" id="notifBadge"></span></button></div>
        <a class="only-desktop top-user" href="/settings.html" aria-label="${esc(t("nav.settings"))}">${avatarHtml(u)}</a>`
      : Nav.bare ? "" : `<a href="/auth.html#login" class="btn btn-sm btn-outline">${esc(t("nav.login"))}</a><a href="/auth.html#register" class="btn btn-sm only-desktop">${esc(t("nav.register"))}</a>`}`;
    $("#sideOpen")?.addEventListener("click", () => toggleSide(true));
    $("#langBtn").addEventListener("click", (e) => openMenu(e, langMenu));
    $("#bellBtn")?.addEventListener("click", (e) => openMenu(e, notifMenu, true));
  }
  if (Nav.bare) return;
  // ---- chap panel: shishasimon, yig'iladigan (ikonka qatori <-> to'liq menyu), qidiruv, bo'limlar, tungi rejim ----
  const side = $("#side");
  side.setAttribute("aria-label", t("nav.menu"));
  const group = (id, labelKey, links, { open = true } = {}) => {
    const closed = Theme.closedGroups().includes(id);
    return `<div class="side-group ${closed && open !== "always" ? "" : "open"}" data-g="${id}">
      <button type="button" class="side-label" aria-expanded="${closed ? "false" : "true"}"><span>${esc(t(labelKey))}</span>${icon("chevron", 14)}</button>
      <div class="side-sub">${links}</div></div>`;
  };
  let nav = group("main", "nav.section_main", sideLink("/", "nav.home", "home") + sideLink("/cars.html", "nav.cars", "search")
    + (admin ? "" : sideLink("/advisor.html", "nav.advisor", "spark")) + sideLink("/info.html", "nav.info", "info"));
  if (u && admin) {
    nav += ADMIN_GROUPS.map(([g, tabs]) => group(g, g,
      tabs.map(([k, key, ico]) => sideLink(`/admin.html#${k}`, key, ico, { badge: k === "reports" ? "repBadge" : k === "documents" ? "docBadge" : k === "contracts" ? "ctrBadge" : "" })).join(""))).join("");
  } else if (u) {
    nav += group("cab-" + mode, mode === "owner" ? "nav.section_owner" : "nav.section_renter",
      CABINET[mode].map(([k, key, ico]) => sideLink(`/dashboard.html#${k}`, key, ico, { badge: k === "bookings" && mode === "owner" ? "reqBadge" : "" })).join("")
      + sideLink("/messages.html", "nav.messages", "chat", { badge: "msgBadge" }));
  }
  if (u && admin) nav += group("msg", "nav.section_comm", sideLink("/messages.html", "nav.messages", "chat", { badge: "msgBadge" }));
  if (u && !admin && mode === "owner") nav += `<a class="btn btn-block side-cta" href="/car-form.html" data-tip="${esc(t("nav.add_car"))}">${icon("plus", 18)}<span>${esc(t("nav.add_car"))}</span></a>`;
  if (!u) nav += `<div class="side-promo"><b>${esc(t("side.promo_t"))}</b><p>${esc(t("side.promo_b"))}</p><a class="btn btn-sm btn-block" href="/auth.html#register">${esc(t("nav.register"))}</a></div>`;

  let bottom = "";
  if (u && !admin) bottom += `<div class="side-mode"><div class="side-mini-label">${esc(t("mode.label"))}</div>
    <div class="mode-switch dark" role="group" aria-label="${esc(t("mode.label"))}"><button data-mode="renter" class="${mode === "renter" ? "on" : ""}" data-tip="${esc(t("mode.renter"))}">${icon("user", 16)}<span>${esc(t("mode.renter"))}</span></button>
    <button data-mode="owner" class="${mode === "owner" ? "on" : ""}" data-tip="${esc(t("mode.owner"))}">${icon("car", 16)}<span>${esc(t("mode.owner"))}</span></button></div></div>`;
  if (Install.available()) bottom += `<button type="button" class="side-link side-install" id="installBtn" data-tip="${esc(t("pwa.install"))}">${icon("download")}<span>${esc(t("pwa.install"))}</span></button>`;
  if (u) bottom += sideLink("/settings.html", "nav.settings", "gear");
  bottom += `<label class="side-link side-night" data-tip="${esc(t("nav.night"))}">${icon("moon")}<span>${esc(t("nav.night"))}</span>
    <input type="checkbox" class="switch" id="nightToggle" ${Theme.isDark() ? "checked" : ""} aria-label="${esc(t("nav.night"))}"></label>`;
  if (u) bottom += `<div class="side-user">${avatarHtml(u)}<div class="who"><b>${esc(u.full_name)}</b><span>${esc(u.email)}</span></div>
      <button class="icon-btn ghost" id="logoutBtn" aria-label="${esc(t("nav.logout"))}" data-tip="${esc(t("nav.logout"))}">${icon("logout")}</button></div>`;
  else bottom += sideLink("/auth.html#login", "nav.login", "user");

  side.innerHTML = `<div class="side-head"><a href="/" class="logo"><span class="logo-mark">${LOGO}</span><span class="logo-text"><span>Car<b>Rent</b></span><small>${esc(t(admin ? "nav.ws_admin" : u ? "mode." + mode : "nav.ws_guest"))}</small></span></a>
      <button class="side-collapse only-desktop" id="sideCollapse" aria-label="${esc(t("nav.collapse"))}" title="${esc(t("nav.collapse"))}">${icon("chevron", 14)}</button>
      <button class="icon-btn ghost only-mobile" id="sideClose" aria-label="${esc(t("common.close"))}">${icon("close")}</button></div>
    <label class="side-search" data-tip="${esc(t("nav.search_pages"))}">${icon("search", 17)}<input type="search" id="sideSearch" placeholder="${esc(t("nav.search_pages"))}" autocomplete="off"><kbd class="only-desktop">/</kbd></label>
    <nav class="side-nav">${nav}<div class="side-empty hidden" id="sideEmpty">${esc(t("nav.search_none"))}</div></nav><div class="side-bottom">${bottom}</div>`;
  $("#sideClose").addEventListener("click", () => toggleSide(false));
  $("#sideCollapse").addEventListener("click", () => Theme.collapse(!document.body.classList.contains("side-rail")));
  $("#logoutBtn")?.addEventListener("click", () => Auth.logout());
  $("#installBtn")?.addEventListener("click", () => Install.run());
  $("#nightToggle").addEventListener("change", (e) => Theme.set(e.target.checked ? "dark" : "light"));
  $$("[data-mode]", side).forEach((b) => b.addEventListener("click", () => switchMode(b.dataset.mode)));
  $$(".side-group > .side-label", side).forEach((b) => b.addEventListener("click", () => {
    if (document.body.classList.contains("side-rail")) return;
    const g = b.parentElement, open = !g.classList.contains("open");
    g.classList.toggle("open", open); b.setAttribute("aria-expanded", open);
    Theme.closeGroup(g.dataset.g, !open);
  }));
  const search = $("#sideSearch");
  search.addEventListener("focus", () => { if (document.body.classList.contains("side-rail")) Theme.collapse(false); });
  search.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    let shown = 0;
    $$(".side-group", side).forEach((g) => {
      let any = false;
      $$(".side-link", g).forEach((a) => { const hit = !q || a.textContent.toLowerCase().includes(q); a.classList.toggle("hidden", !hit); any ||= hit; shown += hit; });
      g.classList.toggle("hidden", !any);
      if (q && any) g.classList.add("searching"); else g.classList.remove("searching");
    });
    $("#sideEmpty").classList.toggle("hidden", !q || shown > 0);
  });
  search.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { const first = $$(".side-group:not(.hidden) .side-link:not(.hidden)", side)[0]; if (first) location.href = first.getAttribute("href"); else location.href = "/cars.html?q=" + encodeURIComponent(search.value.trim()); }
    if (e.key === "Escape") { search.value = ""; search.dispatchEvent(new Event("input")); search.blur(); }
  });
  side.addEventListener("click", (e) => { if (e.target.closest("a")) toggleSide(false); });

  // ---- pastki tablar (telefon) ----
  const tab = (href, key, ico, badge = "") => `<a href="${href}" data-href="${href}">${icon(ico, 22)}<span>${esc(t(key))}</span>${badge ? `<i class="cnt hidden" id="${badge}"></i>` : ""}</a>`;
  let tabs;
  if (!u) tabs = tab("/", "nav.home", "home") + tab("/cars.html", "nav.search", "search") + tab("/info.html", "nav.info", "info") + tab("/auth.html#login", "nav.login", "user");
  else if (admin) tabs = tab("/admin.html#stats", "admin.dashboard", "chart") + tab("/admin.html#reports", "admin.reports", "flag", "repBadgeM") + tab("/messages.html", "nav.messages", "chat", "msgBadgeM");
  else if (mode === "owner") tabs = tab("/dashboard.html#overview", "nav.tab_overview", "grid") + tab("/dashboard.html#cars", "nav.tab_mycars", "car")
    + tab("/dashboard.html#bookings", "nav.tab_requests", "list", "reqBadgeM") + tab("/messages.html", "nav.messages", "chat", "msgBadgeM");
  else tabs = tab("/", "nav.home", "home") + tab("/cars.html", "nav.search", "search") + tab("/dashboard.html#bookings", "nav.tab_bookings", "list")
    + tab("/messages.html", "nav.messages", "chat", "msgBadgeM");
  $("#tabbar").innerHTML = tabs + `<button type="button" id="tabMenu">${icon("menu", 22)}<span>${esc(t("nav.menu"))}</span></button>`;
  $("#tabMenu").addEventListener("click", () => toggleSide(true));
  markActive();
  if (Nav.summary) applySummary(Nav.summary);
}

/** Joriy sahifaga mos havolani belgilash (kabinet va admin tablari hash bo'yicha) */
function markActive() {
  const here = location.pathname === "/index.html" ? "/" : location.pathname;
  for (const box of [$(".side"), $(".tabbar")]) {
    if (!box) continue;
    const links = $$("[data-href]", box);
    links.forEach((a) => a.classList.remove("active"));
    const h1 = location.hash.split("/")[0];
    let pick = links.filter((a) => a.dataset.href === here + location.hash);
    if (!pick.length && h1) pick = links.filter((a) => a.dataset.href === here + h1 || a.dataset.href === here + h1 + "s");
    if (!pick.length) pick = links.filter((a) => a.dataset.href.split("#")[0] === here).slice(0, 1);
    if (!pick.length && Nav.active) pick = links.filter((a) => a.dataset.href === "/" + Nav.active + ".html");
    pick.forEach((a) => a.classList.add("active"));
  }
}

async function switchMode(mode) {
  if (Auth.user.active_mode === mode) return;
  await Auth.setMode(mode);
  toast(t(mode === "owner" ? "mode.to_owner" : "mode.to_renter"), "ok");
  toggleSide(false);
  if (location.pathname === "/dashboard.html") { history.replaceState(null, "", "/dashboard.html#overview"); renderNavInner(); document.dispatchEvent(new CustomEvent("modeview")); }
  else location.href = "/dashboard.html#overview";
}

function openMenu(e, builder, wide = false) {
  e.stopPropagation();
  const wrap = e.currentTarget.parentElement;
  const open = $(".dropdown", wrap);
  $$(".dropdown").forEach((d) => d.remove());
  if (open) return;
  const dd = document.createElement("div"); dd.className = "dropdown" + (wide ? " wide" : "");
  wrap.append(dd);
  builder(dd);
  const close = (ev) => { if (!dd.contains(ev.target)) { dd.remove(); document.removeEventListener("click", close); } };
  setTimeout(() => document.addEventListener("click", close));
}

function langMenu(dd) {
  dd.innerHTML = I18N.langs.map((l) => `<button class="item ${l === I18N.lang ? "active" : ""}" data-lang="${l}"><b>${l.toUpperCase()}</b> ${esc(I18N.names[l])}</button>`).join("");
  dd.addEventListener("click", (e) => { const b = e.target.closest("[data-lang]"); if (b) { dd.remove(); setLang(b.dataset.lang); } });
}

function notifText(n) {
  const p = { ...n.params };
  if (p.total !== undefined) p.total = money(p.total);
  if (p.start) p.start = fmtDate(p.start);
  if (p.end) p.end = fmtDate(p.end);
  if (p.rating) p.stars = "★".repeat(p.rating);
  if (p.what) p.what = t("sec.what_" + p.what) || p.what;
  if (p.reason) p.reason = t("report.reason_" + p.reason) || p.reason;
  return { title: t(`notif.${n.type}.t`, p), body: t(`notif.${n.type}.b`, p) };
}

// ================= Bildirishnomalar: kabinetlar bo'yicha ajratilgan =================
/** Joriy foydalanuvchi qaysi kabinetda turibdi: admin | renter | owner */
const curMode = () => (Auth.user?.role === "admin" ? "admin" : Auth.user?.active_mode || "renter");
/** Bildirishnoma joriy kabinetga tegishlimi ("any" — hamma joyda ko'rinadi) */
const inMode = (n) => !n.mode || n.mode === "any" || n.mode === curMode();
const otherMode = () => (curMode() === "owner" ? "renter" : "owner");
const modeLabel = (m) => t(m === "owner" ? "notif.for_owner" : m === "renter" ? "notif.for_renter" : m === "admin" ? "nav.admin" : "notif.for_all");

function notifIcon(n) {
  if (n.actor_name) return n.actor_avatar ? `<img class="avatar" src="${esc(n.actor_avatar)}" alt="">` : `<span class="avatar">${esc(initials(n.actor_name))}</span>`;
  const ico = n.type.startsWith("payment") || n.type.startsWith("payout") || n.type.startsWith("fee") ? "wallet"
    : n.type.startsWith("booking") ? "calendar" : n.type.startsWith("dispute") ? "shield" : n.type.startsWith("review") ? "star" : "bell";
  return `<span class="avatar ico">${icon(ico, 18)}</span>`;
}

/** Bitta bildirishnoma qatori: kimdan, qaysi kabinet uchun, nima bo'ldi */
function notifRow(n) {
  const x = notifText(n);
  return `<a class="notif ${n.is_read ? "" : "unread"}" href="${esc(n.link || "#")}" data-id="${n.id}" data-mode="${esc(n.mode || "any")}">
    ${notifIcon(n)}<div class="nb"><div class="nh"><b>${esc(n.actor_name || "CarRent")}</b>${n.mode && n.mode !== "any" ? `<span class="mode-tag m-${n.mode}">${esc(modeLabel(n.mode))}</span>` : ""}</div>
    <div class="t">${esc(x.title)}</div><div class="b">${esc(x.body)}</div><div class="small muted">${timeAgo(n.created_at)}</div></div></a>`;
}

/** Bosilganda: kerak bo'lsa avval tegishli kabinetga o'tadi, keyin havolani ochadi */
async function openNotif(n, ev) {
  ev?.preventDefault();
  api(`/api/notifications/${n.id}/read`, { method: "POST" }).catch(() => {});
  if (Auth.user?.role !== "admin" && (n.mode === "owner" || n.mode === "renter") && n.mode !== Auth.user.active_mode) {
    await Auth.setMode(n.mode); toast(t(n.mode === "owner" ? "mode.to_owner" : "mode.to_renter"), "ok");
  }
  location.href = n.link || "/dashboard.html#notifications";
}

async function notifMenu(dd) {
  dd.innerHTML = `<div class="dropdown-head"><b>${esc(t("nav.notifications"))}</b><button class="btn btn-sm btn-outline" id="readAll">${esc(t("notif.read_all"))}</button></div>
    <div class="dropdown-list"><div class="empty small">${esc(t("common.loading"))}</div></div>`;
  const data = await api("/api/notifications");
  const mine = data.items.filter(inMode), other = data.items.filter((n) => !inMode(n));
  const otherUnread = other.filter((n) => !n.is_read).length;
  $(".dropdown-list", dd).innerHTML = (otherUnread && Auth.user.role !== "admin"
      ? `<button class="notif-switch" id="toOther">${icon("swap", 16)} ${esc(t("notif.other_mode", { n: otherUnread, mode: modeLabel(otherMode()) }))}</button>` : "")
    + (mine.length ? mine.map(notifRow).join("") : `<div class="empty small">${esc(t("notif.empty_mode", { mode: modeLabel(curMode()) }))}</div>`);
  $$(".notif", dd).forEach((a) => a.addEventListener("click", (e) => openNotif(data.items.find((n) => n.id == a.dataset.id), e)));
  $("#toOther", dd)?.addEventListener("click", () => switchMode(otherMode()));
  $("#readAll", dd).addEventListener("click", async () => { await api("/api/notifications/read-all", { method: "POST" }); dd.remove(); pollSummary(); });
}

/** Telegram uslubidagi oyna: yangi xabar/bildirishnoma kelganda pastki burchakda chiqadi */
function notifPopup(n) {
  let box = $(".np-stack");
  if (!box) { box = document.createElement("div"); box.className = "np-stack"; box.setAttribute("aria-live", "polite"); document.body.append(box); }
  const x = notifText(n);
  const el = document.createElement("div");
  el.className = "np" + (inMode(n) ? "" : " other");
  el.setAttribute("role", "status");
  el.innerHTML = `${notifIcon(n)}<div class="nb"><div class="nh"><b>${esc(n.actor_name || "CarRent")}</b>
      ${n.mode && n.mode !== "any" ? `<span class="mode-tag m-${n.mode}">${esc(modeLabel(n.mode))}</span>` : ""}<span class="muted small">${esc(t("time.now"))}</span></div>
    <div class="t">${esc(x.title)}</div><div class="b">${esc(n.type === "message" && n.params?.preview ? n.params.preview : x.body)}</div>
    ${inMode(n) ? "" : `<div class="hint-sw">${icon("swap", 13)} ${esc(t("notif.tap_switch", { mode: modeLabel(n.mode) }))}</div>`}</div>
    <button class="np-x" aria-label="${esc(t("common.close"))}">${icon("close", 16)}</button>`;
  el.addEventListener("click", (e) => { if (e.target.closest(".np-x")) { el.remove(); return; } openNotif(n, e); });
  box.prepend(el);
  while (box.children.length > 3) box.lastElementChild.remove();
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 350); }, 9000);
}

function applySummary(s) {
  const set = (ids, n) => ids.forEach((id) => { const el = $(id); if (!el) return; el.textContent = n > 9 ? "9+" : n; el.classList.toggle("hidden", !n); });
  // Faqat joriy kabinet + umumiy; boshqa kabinetdagi yangiliklar rejim tugmasida nuqta bo'lib ko'rinadi
  const nb = s.notif_by_mode || {}, mb = s.msg_by_mode || {}, m = curMode();
  const cnt = (by, mode) => (by[mode] || 0) + (by.any || 0) - (mode === "any" ? by.any || 0 : 0);
  set(["#notifBadge"], s.notif_by_mode ? cnt(nb, m) : s.unread_notifications);
  set(["#msgBadge", "#msgBadgeM"], s.msg_by_mode ? cnt(mb, m) : s.unread_messages);
  if (Auth.user?.role !== "admin") $$("[data-mode]").forEach((b) => {
    const k = b.dataset.mode, n = k === m ? 0 : (nb[k] || 0) + (mb[k] || 0);
    let dot = $(".mode-dot", b);
    if (!dot && n) { dot = document.createElement("i"); dot.className = "mode-dot"; b.append(dot); }
    if (dot) { dot.textContent = n > 9 ? "9+" : n; dot.classList.toggle("hidden", !n); dot.title = t("notif.other_mode", { n, mode: modeLabel(k) }); }
  });
  set(["#reqBadge", "#reqBadgeM"], s.pending_requests); set(["#repBadge", "#repBadgeM"], s.open_reports);
  set(["#docBadge"], s.pending_docs); set(["#ctrBadge"], s.contracts_to_approve);
}

async function pollSummary() {
  if (document.hidden || !Auth.user) return;
  try {
    const s = await api("/api/me/summary");
    Nav.summary = s; applySummary(s);
    // Yangi bildirishnomalar — oyna bilan (birinchi yuklanishda eski xabarlar ko'rsatilmaydi)
    if (Nav.lastNotif === undefined) Nav.lastNotif = s.last_notification_id || 0;
    else if (s.last_notification_id > Nav.lastNotif) {
      const after = Nav.lastNotif; Nav.lastNotif = s.last_notification_id;
      const { items } = await api(`/api/notifications?after=${after}`);
      const skipChat = location.pathname === "/messages.html";
      items.reverse().filter((n) => !(skipChat && n.type === "message" && n.link?.includes(`user=${new URLSearchParams(location.search).get("user")}`)))
        .forEach(notifPopup);
    }
    document.dispatchEvent(new CustomEvent("summary", { detail: s }));
  } catch (e) { if (e.status === 401) location.reload(); }
}

function renderFooter() {
  if (Nav.bare) return;
  let f = $("footer.footer");
  if (!f) { f = document.createElement("footer"); f.className = "footer"; (document.querySelector("main") || document.body).after(f); }
  const draw = () => {
    f.innerHTML = `<div class="container"><div class="footer-grid">
      <div><a href="/" class="logo"><span class="logo-mark">${LOGO}</span><span>Car<b>Rent</b></span></a><p style="margin-top:10px">${esc(t("brand.slogan"))}</p></div>
      <div><h4>${esc(t("footer.platform"))}</h4><a href="/cars.html">${esc(t("nav.cars"))}</a><a href="/info.html#how">${esc(t("nav.how"))}</a><a href="/car-form.html">${esc(t("footer.become_owner"))}</a></div>
      <div><h4>${esc(t("footer.company"))}</h4><a href="/info.html#about">${esc(t("nav.about"))}</a><a href="/info.html#pricing">${esc(t("nav.pricing"))}</a><a href="/info.html#contact">${esc(t("nav.contact"))}</a></div>
      <div><h4>${esc(t("footer.legal"))}</h4><a href="/info.html#terms">${esc(t("footer.terms"))}</a><a href="/info.html#privacy">${esc(t("footer.privacy"))}</a><a href="/info.html#safety">${esc(t("info.safety"))}</a></div>
      </div><div class="footer-bottom"><span>© ${new Date().getFullYear()} CarRent</span><span>${esc(t("footer.note"))}</span></div></div>`;
  };
  draw();
  document.addEventListener("langchange", draw);
}

// ================= Sana maydoni: KK.OO.YYYY ko'rinishida, o'z kalendari bilan =================
/* Brauzerning type="date" maydoni tizim tilida (masalan, "дд.мм.гггг") ko'rinadi. Shuning uchun matnli maydon +
   raqamli namuna (masalan, 30.10.2026) ishlatiladi. Asl input yashirin bo'lib qoladi va ISO qiymat (2026-10-30) saqlaydi —
   sahifa kodi $("#start").value orqali avvalgidek ishlaydi. */
const DateField = {
  toIso(text) {
    const m = String(text || "").trim().match(/^(\d{1,2})[./\-\s](\d{1,2})[./\-\s](\d{4})$/);
    if (!m) return null;
    const d = new Date(+m[3], +m[2] - 1, +m[1]);
    return d.getDate() === +m[1] && d.getMonth() === +m[2] - 1 ? isoDate(d) : null;
  },
  sample(minIso) {
    const d = minIso ? new Date(minIso + "T00:00:00") : new Date();
    d.setDate(d.getDate() + 1);
    return fmtDate(isoDate(d));
  },
  enhance(root = document) { $$('input[type="date"]', root).forEach((el) => DateField.wrap(el)); },
  wrap(el) {
    const id = el.id || "d" + Math.random().toString(36).slice(2, 8);
    const vis = document.createElement("input");
    vis.className = el.className + " date-text"; vis.id = id + "Text"; vis.inputMode = "numeric"; vis.autocomplete = "off";
    vis.maxLength = 10; vis.required = el.required; vis.setAttribute("aria-describedby", id + "Fmt");
    const wrap = document.createElement("div"); wrap.className = "date-wrap";
    const btn = document.createElement("button"); btn.type = "button"; btn.className = "date-btn"; btn.innerHTML = icon("calendar", 18);
    const fmtHint = document.createElement("span"); fmtHint.className = "sr-only"; fmtHint.id = id + "Fmt";
    el.replaceWith(wrap); wrap.append(vis, btn, fmtHint, el);
    el.type = "hidden"; el.required = false;
    const label = document.querySelector(`label[for="${CSS.escape(id)}"]`); if (label) label.htmlFor = vis.id;
    const desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
    const paint = () => { vis.placeholder = DateField.sample(el.min); btn.setAttribute("aria-label", t("date.pick")); fmtHint.textContent = t("date.format"); };
    // Dastur qiymat o'rnatsa ham ko'rinadigan maydon yangilanadi
    Object.defineProperty(el, "value", { get() { return desc.get.call(this); }, set(v) { desc.set.call(this, v || ""); vis.value = v ? fmtDate(v) : ""; vis.removeAttribute("aria-invalid"); } });
    if (desc.get.call(el)) vis.value = fmtDate(desc.get.call(el));
    paint(); document.addEventListener("langchange", paint);
    new MutationObserver(paint).observe(el, { attributes: true, attributeFilter: ["min"] });
    const commit = (iso, fire = true) => {
      if (iso && el.min && iso < el.min) iso = null;
      if (iso && el.max && iso > el.max) iso = null;
      const prev = desc.get.call(el);
      desc.set.call(el, iso || "");
      if (fire && prev !== (iso || "")) { el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true })); }
      return iso;
    };
    vis.addEventListener("input", () => {
      // Avtomatik nuqta: 30102026 -> 30.10.2026
      const digits = vis.value.replace(/\D/g, "").slice(0, 8);
      let out = digits.slice(0, 2); if (digits.length > 2) out += "." + digits.slice(2, 4); if (digits.length > 4) out += "." + digits.slice(4);
      if (/^\d{1,2}[./-]\d{1,2}[./-]\d{4}$/.test(vis.value)) out = vis.value.replace(/[/-]/g, ".");
      vis.value = out;
      if (out.length === 10) { const iso = commit(DateField.toIso(out)); vis.setAttribute("aria-invalid", iso ? "false" : "true"); }
      else if (!out) commit(null);
    });
    vis.addEventListener("focus", () => setTimeout(() => vis.select(), 0));
    vis.addEventListener("blur", () => {
      if (!vis.value) { commit(null); vis.removeAttribute("aria-invalid"); return; }
      const iso = commit(DateField.toIso(vis.value));
      if (!iso) { vis.setAttribute("aria-invalid", "true"); toast(el.min && DateField.toIso(vis.value) ? t("date.too_early", { d: fmtDate(el.min) }) : t("date.invalid"), "error"); }
      else vis.value = fmtDate(iso);
    });
    btn.addEventListener("click", (e) => { e.stopPropagation(); DateField.popup(wrap, el, (iso) => { commit(iso); vis.value = fmtDate(iso); vis.removeAttribute("aria-invalid"); }); });
  },
  popup(wrap, el, pick) {
    $$(".date-pop").forEach((p) => p.remove());
    const cur = el.value || el.min || isoDate(new Date());
    let month = new Date(cur.slice(0, 7) + "-01T00:00:00");
    const pop = document.createElement("div"); pop.className = "date-pop card"; pop.setAttribute("role", "dialog");
    const draw = () => {
      const y = month.getFullYear(), m = month.getMonth();
      const first = (new Date(y, m, 1).getDay() + 6) % 7, days = new Date(y, m + 1, 0).getDate();
      let cells = t("cal.dow").split(",").map((d) => `<span class="cal-dow">${esc(d)}</span>`).join("") + "<span></span>".repeat(first);
      for (let d = 1; d <= days; d++) {
        const iso = isoDate(new Date(y, m, d));
        const off = (el.min && iso < el.min) || (el.max && iso > el.max);
        cells += `<button type="button" data-d="${iso}" class="${iso === el.value ? "sel" : ""} ${iso === isoDate(new Date()) ? "today" : ""}" ${off ? "disabled" : ""}>${d}</button>`;
      }
      pop.innerHTML = `<div class="cal-head"><button type="button" class="icon-btn ghost" data-m="-1" aria-label="${esc(t("cal.prev"))}">${icon("arrowl", 18)}</button>
        <b>${esc(t("cal.months").split(",")[m])} ${y}</b><button type="button" class="icon-btn ghost" data-m="1" aria-label="${esc(t("cal.next"))}">${icon("arrowr", 18)}</button></div>
        <div class="date-grid">${cells}</div>`;
    };
    draw();
    pop.addEventListener("click", (e) => {
      e.stopPropagation();
      const nav = e.target.closest("[data-m]"); if (nav) { month = new Date(month.getFullYear(), month.getMonth() + +nav.dataset.m, 1); draw(); return; }
      const d = e.target.closest("[data-d]"); if (d && !d.disabled) { pick(d.dataset.d); pop.remove(); }
    });
    wrap.append(pop);
    const close = (ev) => { if (!pop.contains(ev.target)) { pop.remove(); document.removeEventListener("click", close); } };
    setTimeout(() => document.addEventListener("click", close));
    pop.querySelector("button.sel, button.today:not(:disabled), .date-grid button:not(:disabled)")?.focus();
  },
};

// ================= Forma maydonlari uchun izohlar =================
/** data-hint="kalit" bo'lgan maydon ostiga izoh chiqaradi (tilga mos). */
function applyHints(root = document) {
  $$("[data-hint]", root).forEach((input) => {
    const field = input.closest(".field") || input.parentElement;
    let h = field.querySelector(":scope > .hint[data-auto]");
    if (!h) { h = document.createElement("div"); h.className = "hint"; h.dataset.auto = "1"; h.id = (input.id || input.name) + "Hint"; field.append(h); input.setAttribute("aria-describedby", h.id); }
    h.textContent = t(input.dataset.hint);
  });
}
document.addEventListener("langchange", () => applyHints());

/** Parolni ko'rsatish/yashirish tugmalari: <button data-pw="inputId"> */
function bindPasswordToggles(root = document) {
  $$("[data-pw]", root).forEach((b) => {
    const input = $("#" + b.dataset.pw);
    const paint = () => { const hidden = input.type === "password"; b.innerHTML = icon(hidden ? "eye" : "eyeoff", 18); b.setAttribute("aria-label", t(hidden ? "auth.show" : "auth.hide")); };
    b.addEventListener("click", () => { input.type = input.type === "password" ? "text" : "password"; paint(); input.focus(); });
    paint(); document.addEventListener("langchange", paint);
  });
}

// ================= PWA: telefonga o'rnatish =================
if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}

// ================= Kalendar =================
class BookingCalendar {
  constructor(root, carId, { selectable = false, onSelect = () => {} } = {}) {
    Object.assign(this, { root, carId, selectable, onSelect });
    const now = new Date(); this.month = new Date(now.getFullYear(), now.getMonth(), 1);
    this.start = null; this.end = null; this.ranges = []; this.today = isoDate(now);
    root.addEventListener("click", (e) => this.handle(e));
    document.addEventListener("langchange", () => this.render());
  }
  async load() {
    const to = new Date(this.month.getFullYear(), this.month.getMonth() + 4, 0);
    const data = await api(`/api/cars/${this.carId}/calendar?from=${isoDate(this.month)}&to=${isoDate(to)}`);
    this.ranges = data.ranges; this.today = data.today; this.render();
  }
  statusOf(iso) {
    let st = null;
    for (const r of this.ranges) if (r.start_date <= iso && iso <= r.end_date) {
      if (r.status === "approved") return "booked";
      st = r.status === "blocked" ? "blocked" : st || "pending";
    }
    return st;
  }
  render() {
    const y = this.month.getFullYear(), m = this.month.getMonth();
    const first = (new Date(y, m, 1).getDay() + 6) % 7, days = new Date(y, m + 1, 0).getDate();
    let cells = t("cal.dow").split(",").map((d) => `<div class="cal-dow">${esc(d)}</div>`).join("");
    for (let i = 0; i < first; i++) cells += `<div class="cal-day empty"></div>`;
    for (let d = 1; d <= days; d++) {
      const iso = isoDate(new Date(y, m, d)); const st = this.statusOf(iso); const cls = ["cal-day"]; const past = iso < this.today;
      if (past) cls.push("past"); else if (st) cls.push(st);
      if (iso === this.today) cls.push("today");
      if (this.start && (iso === this.start || iso === this.end)) cls.push("sel");
      else if (this.start && this.end && iso > this.start && iso < this.end) cls.push("range");
      const disabled = past || !!st;
      const title = st ? t("cal." + st) : past ? "" : t("cal.free");
      cells += `<button type="button" class="${cls.join(" ")}" data-date="${iso}" ${disabled ? "disabled" : ""} title="${esc(title)}" aria-label="${fmtDate(iso)} ${esc(title)}">${d}</button>`;
    }
    const now = new Date(); const canPrev = this.month > new Date(now.getFullYear(), now.getMonth(), 1);
    this.root.innerHTML = `<div class="cal-head"><button type="button" class="btn btn-sm btn-outline" data-nav="-1" ${canPrev ? "" : "disabled"} aria-label="${esc(t("cal.prev"))}">‹</button>
      <b>${esc(t("cal.months").split(",")[m])} ${y}</b><button type="button" class="btn btn-sm btn-outline" data-nav="1" aria-label="${esc(t("cal.next"))}">›</button></div>
      <div class="cal-grid">${cells}</div>
      <div class="cal-legend"><span><i style="background:var(--success-soft)"></i>${esc(t("cal.free"))}</span><span><i style="background:var(--danger-soft)"></i>${esc(t("cal.booked"))}</span>
      <span><i style="background:#fde7bd"></i>${esc(t("cal.pending"))}</span><span><i style="background:#d9dde5"></i>${esc(t("cal.blocked"))}</span>${this.selectable ? `<span><i style="background:var(--primary)"></i>${esc(t("cal.selected"))}</span>` : ""}</div>`;
  }
  handle(e) {
    const nav = e.target.closest("[data-nav]");
    if (nav) { this.month = new Date(this.month.getFullYear(), this.month.getMonth() + Number(nav.dataset.nav), 1); this.load(); return; }
    const day = e.target.closest(".cal-day[data-date]");
    if (!day || day.disabled || !this.selectable) return;
    const iso = day.dataset.date;
    if (!this.start || this.end || iso < this.start) { this.start = iso; this.end = null; }
    else {
      for (let d = new Date(this.start + "T00:00:00"); isoDate(d) <= iso; d.setDate(d.getDate() + 1)) {
        if (this.statusOf(isoDate(d))) { toast(t("cal.range_busy"), "error"); return; }
      }
      this.end = iso;
    }
    this.render(); this.onSelect(this.start, this.end || this.start);
  }
  setRange(s, e) {
    this.start = s || null; this.end = e || null;
    if (s) {
      const d = new Date(s + "T00:00:00"), m = new Date(d.getFullYear(), d.getMonth(), 1);
      if (m.getTime() !== this.month.getTime()) { this.month = m; this.load(); return; }
    }
    this.render();
  }
}

document.addEventListener("keydown", (e) => { if (e.key === "Escape") $$(".dropdown, .modal-bg").forEach((x) => x.remove()); });

// ================= Bir martalik kod (6 ta katakcha) =================
/** 6 xonali kod maydoni: avtomatik keyingi katakka o'tadi, butun kodni joylashtirish (paste) va SMS avtoto'ldirishni qo'llaydi. */
function otpField(root, onComplete = () => {}) {
  root.classList.add("otp");
  root.innerHTML = Array.from({ length: 6 }, (_, i) => `<input inputmode="numeric" pattern="[0-9]*" maxlength="1" autocomplete="${i ? "off" : "one-time-code"}"
    aria-label="${esc(t("otp.digit", { n: i + 1 }))}">`).join("");
  const boxes = $$("input", root);
  const value = () => boxes.map((b) => b.value).join("");
  const fill = (str, from = 0) => {
    const d = str.replace(/\D/g, "").slice(0, 6 - from).split("");
    d.forEach((ch, k) => (boxes[from + k].value = ch));
    boxes[Math.min(from + d.length, 5)].focus();
    root.classList.remove("bad");
    if (value().length === 6) onComplete(value());
  };
  boxes.forEach((b, i) => {
    b.addEventListener("input", () => { const v = b.value; b.value = ""; if (v) fill(v, i); });
    b.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && !b.value && i) { boxes[i - 1].value = ""; boxes[i - 1].focus(); e.preventDefault(); }
      if (e.key === "ArrowLeft" && i) boxes[i - 1].focus();
      if (e.key === "ArrowRight" && i < 5) boxes[i + 1].focus();
    });
    b.addEventListener("paste", (e) => { e.preventDefault(); fill((e.clipboardData || window.clipboardData).getData("text"), i); });
    b.addEventListener("focus", () => b.select());
  });
  return {
    get value() { return value(); },
    clear() { boxes.forEach((b) => (b.value = "")); boxes[0].focus(); },
    error() { root.classList.remove("bad"); void root.offsetWidth; root.classList.add("bad"); },
    focus() { boxes[0].focus(); },
  };
}

/** Qayta yuborish tugmasi uchun teskari sanoq */
function cooldown(btn, sec, labelKey) {
  let n = sec;
  btn.disabled = true;
  const tick = () => {
    if (n <= 0) { btn.disabled = false; btn.textContent = t(labelKey); clearInterval(timer); return; }
    btn.textContent = t("otp.resend_in", { n }); n--;
  };
  const timer = setInterval(tick, 1000); tick();
}

// ================= Rasmni brauzerda kichraytirish (yuklash tezroq, trafik kam) =================
/** Katta suratni maxSide pikselgacha kichraytirib JPEG qiladi. Server baribir qayta kodlaydi va EXIF'ni o'chiradi. */
async function compressImage(file, maxSide = 1920, quality = 0.86) {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type)) return file;
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const k = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
    if (k === 1 && file.size < 1.5 * 1024 * 1024) { bmp.close?.(); return file; }
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    bmp.close?.();
    const blob = await new Promise((r) => c.toBlob(r, "image/jpeg", quality));
    return blob ? new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" }) : file;
  } catch { return file; }
}

// ================= Galereya: to'liq ekran, klaviatura va barmoq bilan surish =================
function swipe(el, onDir) {
  let x0 = null, y0 = 0;
  el.addEventListener("touchstart", (e) => { x0 = e.touches[0].clientX; y0 = e.touches[0].clientY; }, { passive: true });
  el.addEventListener("touchend", (e) => {
    if (x0 === null) return;
    const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0; x0 = null;
    if (Math.abs(dx) > 45 && Math.abs(dx) > Math.abs(dy)) onDir(dx < 0 ? 1 : -1);
  }, { passive: true });
}
function lightbox(images, start = 0, onChange = () => {}) {
  let i = start;
  const bg = document.createElement("div"); bg.className = "lightbox"; bg.setAttribute("role", "dialog"); bg.setAttribute("aria-modal", "true");
  const draw = () => {
    const im = images[i];
    bg.innerHTML = `<button class="lb-close" aria-label="${esc(t("common.close"))}">${icon("close", 24)}</button>
      <figure><img src="${esc(im.path)}" alt=""><figcaption>${im.label ? esc(t("img.label_" + im.label)) + " · " : ""}${i + 1} / ${images.length}</figcaption></figure>
      ${images.length > 1 ? `<button class="lb-nav prev" data-d="-1" aria-label="${esc(t("cal.prev"))}">${icon("arrowl", 28)}</button><button class="lb-nav next" data-d="1" aria-label="${esc(t("cal.next"))}">${icon("arrowr", 28)}</button>` : ""}
      <div class="lb-strip">${images.map((x, k) => `<button data-k="${k}" class="${k === i ? "on" : ""}"><img src="${esc(x.path)}" alt=""></button>`).join("")}</div>`;
  };
  const step = (d) => { i = (i + d + images.length) % images.length; draw(); onChange(i); };
  const key = (e) => { if (e.key === "ArrowRight") step(1); if (e.key === "ArrowLeft") step(-1); if (e.key === "Escape") close(); };
  const close = () => { bg.remove(); document.removeEventListener("keydown", key); document.body.style.overflow = ""; };
  bg.addEventListener("click", (e) => {
    const d = e.target.closest("[data-d]"), k = e.target.closest("[data-k]");
    if (d) step(+d.dataset.d); else if (k) { i = +k.dataset.k; draw(); onChange(i); }
    else if (e.target.closest(".lb-close") || e.target === bg) close();
  });
  swipe(bg, step);
  document.addEventListener("keydown", key);
  document.body.style.overflow = "hidden";
  draw(); document.body.append(bg); $(".lb-close", bg).focus();
}

// ================= Shikoyat yuborish =================
function reportModal(targetType, targetId) {
  const reasons = ["fake", "fraud", "wrong_info", "abuse", "spam", "other"];
  const bg = document.createElement("div"); bg.className = "modal-bg";
  bg.innerHTML = `<form class="modal card card-pad" role="dialog" aria-modal="true"><h3>${esc(t("report.title"))}</h3><p class="small muted">${esc(t("report.sub"))}</p>
    <div class="pay-options">${reasons.map((r, k) => `<label class="pay-opt"><input type="radio" name="reason" value="${r}" ${k ? "" : "checked"}><span><b>${esc(t("report.reason_" + r))}</b></span></label>`).join("")}</div>
    <div class="field" style="margin-top:12px"><label for="rpC">${esc(t("report.comment"))}</label><textarea class="input" id="rpC" maxlength="1000" placeholder="${esc(t("report.comment_ph"))}"></textarea></div>
    <div class="row" style="justify-content:flex-end"><button type="button" class="btn btn-outline" data-close>${esc(t("common.cancel"))}</button><button class="btn btn-danger">${esc(t("report.send"))}</button></div></form>`;
  document.body.append(bg);
  bg.addEventListener("click", (e) => { if (e.target === bg || e.target.matches("[data-close]")) bg.remove(); });
  $("form", bg).addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await api("/api/reports", { method: "POST", body: { target_type: targetType, target_id: targetId, reason: new FormData(e.target).get("reason"), comment: $("#rpC").value.trim() || null } });
      bg.remove(); toast(t("report.sent"), "ok");
    } catch (err) { toast(err.message, "error"); }
  });
}

// ================= Parol qoidalari (server bilan bir xil: app/schemas.py PW_RULES) =================
const PW_MIN = 8;
const PW_RULES = [
  ["len", (v) => v.length >= PW_MIN],
  ["upper", (v) => /\p{Lu}/u.test(v)],
  ["lower", (v) => /\p{Ll}/u.test(v)],
  ["digit", (v) => /\d/.test(v)],
  ["symbol", (v) => /[^\p{L}\p{N}\s]/u.test(v)],
];
/** Parol maydoni ostida qoidalar ro'yxati: bajarilgan qoida yashil ✓ bo'ladi. Qaytaradi: { valid() } */
function pwChecklist(input, { compact = false } = {}) {
  const box = document.createElement("ul");
  box.className = "pw-rules" + (compact ? " compact" : "");
  box.setAttribute("aria-live", "polite");
  const field = input.closest(".field") || input.parentElement;
  field.append(box);
  const draw = () => {
    const v = input.value;
    box.innerHTML = PW_RULES.map(([k, test]) => {
      const okv = test(v);
      return `<li class="${okv ? "ok" : v ? "no" : ""}" title="${esc(t("pw.r_" + k, { n: PW_MIN }))}"><span class="mark" aria-hidden="true">${okv ? "✓" : "•"}</span>${esc(t((compact ? "pw.s_" : "pw.r_") + k, { n: PW_MIN }))}<span class="sr-only">${esc(t(okv ? "pw.met" : "pw.unmet"))}</span></li>`;
    }).join("");
    box.classList.toggle("all-ok", PW_RULES.every(([, test]) => test(v)));
  };
  input.addEventListener("input", draw);
  document.addEventListener("langchange", draw);
  draw();
  return { valid: () => PW_RULES.every(([, test]) => test(input.value)), firstError: () => {
    const miss = PW_RULES.find(([, test]) => !test(input.value)); return miss ? t("pw.r_" + miss[0], { n: PW_MIN }) : "";
  } };
}

/** Ishonchli parol: 14 belgi, katta/kichik harf, raqam va belgi albatta bor; o'xshash belgilar (0/O, l/1) ishlatilmaydi */
function strongPassword(len = 14) {
  const sets = ["ABCDEFGHJKLMNPQRSTUVWXYZ", "abcdefghijkmnpqrstuvwxyz", "23456789", "!@#$%&*?+=-_"];
  const rnd = (n) => { const a = new Uint32Array(1); crypto.getRandomValues(a); return a[0] % n; };
  const all = sets.join("");
  // Har turdan kamida bittadan, belgilardan esa kamida 2–3 ta (masalan: Kp7#vR2!mQ9@xT)
  const chars = sets.map((x) => x[rnd(x.length)]);
  for (let k = 0; k < 2; k++) chars.push(sets[3][rnd(sets[3].length)]);
  while (chars.length < len) chars.push(all[rnd(all.length)]);
  for (let i = chars.length - 1; i > 0; i--) { const j = rnd(i + 1); [chars[i], chars[j]] = [chars[j], chars[i]]; }
  return chars.join("");
}

/** Parol maydoni ostida "Ishonchli parol yaratish" tugmasi: parolni yaratadi, ko'rsatadi va nusxalaydi */
function pwGenerator(input) {
  const btn = document.createElement("button");
  btn.type = "button"; btn.className = "linkbtn pw-gen";
  const paint = () => { btn.innerHTML = `${icon("key", 15)} ${esc(t("pw.generate"))}`; };
  paint(); document.addEventListener("langchange", paint);
  (input.closest(".field") || input.parentElement).append(btn);
  btn.addEventListener("click", async () => {
    const pw = strongPassword();
    input.value = pw; input.type = "text";
    input.dispatchEvent(new Event("input", { bubbles: true }));
    try { await navigator.clipboard.writeText(pw); toast(t("pw.generated_copied"), "ok"); } catch { toast(t("pw.generated"), "ok"); }
  });
}

/** Kod amal qilish muddati: "Kod 2:47 dan keyin eskiradi" — tugasa qizil va qayta so'rashni taklif qiladi */
function codeTimer(el, seconds) {
  clearInterval(el._timer);
  const end = Date.now() + seconds * 1000;
  const tick = () => {
    const left = Math.max(0, Math.round((end - Date.now()) / 1000));
    const mm = Math.floor(left / 60), ss = String(left % 60).padStart(2, "0");
    el.classList.toggle("expired", !left);
    el.classList.toggle("soon", left > 0 && left <= 30);
    el.textContent = left ? t("otp.expires_in", { t: `${mm}:${ss}` }) : t("otp.expired");
    if (!left) clearInterval(el._timer);
  };
  tick();
  el._timer = setInterval(tick, 1000);
}

// ================= Tezkor bron oynasi ("Band qilish") — "Batafsil" sahifasidan farqli =================
// "Batafsil" — mashina haqida to'liq ma'lumot (rasmlar, shartlar, sharhlar). "Band qilish" — sahifadan chiqmasdan:
// kalendardan bo'sh kunlarni tanlash, aniq narx hisobi va so'rov yuborish.
async function quickBook(carId) {
  if (!Auth.user) { location.href = "/auth.html?next=" + encodeURIComponent(`/car.html?id=${carId}#book`) + "#login"; return; }
  const bg = document.createElement("div"); bg.className = "modal-bg";
  bg.innerHTML = `<div class="modal card qb" role="dialog" aria-modal="true" aria-labelledby="qbT"><div class="skeleton" style="height:420px"></div></div>`;
  document.body.append(bg);
  const close = () => bg.remove();
  bg.addEventListener("click", (e) => { if (e.target === bg || e.target.closest("[data-close]")) close(); });
  let car;
  try { car = await api(`/api/cars/${carId}`); } catch (err) { close(); toast(err.message, "error"); return; }
  if (car.is_mine) { close(); toast(t("qb.own_car"), "error"); return; }
  const box = $(".qb", bg);
  const st = { start: null, end: null, delivery: false, quote: null };
  box.innerHTML = `<div class="qb-head">${carImage(car, car.images?.[0]?.path)}<div><h3 id="qbT">${esc(carName(car))} <span class="muted small">${car.year}</span></h3>
      <div class="small muted">📍 ${esc(Places.label(car.city, car.district))} · ${esc(t("terms.days_range", { a: car.min_days, b: car.max_days }))}</div>
      <div class="price">${money(car.price_per_day)} <small>${esc(t("car.per_day"))}</small></div></div>
      <button class="icon-btn ghost" data-close aria-label="${esc(t("common.close"))}">${icon("close")}</button></div>
    <div class="qb-body"><div><div class="qb-step"><b>1</b> ${esc(t("qb.pick_dates"))}</div><div id="qbCal"></div></div>
      <form id="qbForm" novalidate><div class="qb-step"><b>2</b> ${esc(t("qb.check"))}</div>
        <div id="qbSum" class="qb-sum"><p class="muted small">${esc(t("qb.pick_hint"))}</p></div>
        ${car.delivery_price !== null ? `<label class="check" style="margin:10px 0"><input type="checkbox" id="qbDel"><span>${esc(t("book.delivery", { price: money(car.delivery_price) }))}</span></label>` : ""}
        <div class="field"><label for="qbNote">${esc(t("booking.note"))} <span class="muted small">(${esc(t("common.optional"))})</span></label>
          <textarea class="input" id="qbNote" maxlength="500" rows="2" placeholder="${esc(t("qb.note_ph"))}"></textarea></div>
        <button class="btn btn-block btn-lg" id="qbSend" disabled>${esc(t("qb.send"))}</button>
        <p class="small muted" style="margin:8px 0 0">${esc(t("qb.how"))}</p>
        <a class="small" href="/car.html?id=${car.id}">${esc(t("qb.full_page"))} →</a></form></div>`;
  const cal = new BookingCalendar($("#qbCal", box), car.id, { selectable: true, onSelect: (s, e) => { st.start = s; st.end = e; requote(); } });
  cal.load();
  $("#qbDel", box)?.addEventListener("change", (e) => { st.delivery = e.target.checked; requote(); });
  async function requote() {
    if (!st.start) return;
    const sum = $("#qbSum", box), btn = $("#qbSend", box);
    try {
      const q = st.quote = await api(`/api/cars/${car.id}/quote?start=${st.start}&end=${st.end}&delivery=${st.delivery ? 1 : 0}`);
      const okDays = q.within_limits, okFree = q.available;
      sum.innerHTML = `<div class="sum-row"><span>${fmtDate(st.start)} → ${fmtDate(st.end)}</span><b>${esc(t("car.days_n", { n: q.days }))}</b></div>
        <div class="sum-row"><span>${money(q.price_per_day)} × ${q.days}</span><span>${money(q.rent)}</span></div>
        ${q.delivery ? `<div class="sum-row"><span>${esc(t("book.delivery_fee"))}</span><span>${money(q.delivery)}</span></div>` : ""}
        <div class="sum-row total"><span>${esc(t("booking.total"))}</span><span>${money(q.total)}</span></div>
        ${q.deposit ? `<div class="sum-row sub"><span>${esc(t("book.deposit"))}</span><span>${money(q.deposit)}</span></div>` : ""}
        ${!okFree ? `<div class="notice" style="margin-top:8px">${esc(t("cal.range_busy"))}</div>` : !okDays ? `<div class="notice" style="margin-top:8px">${esc(t("terms.days_range", { a: car.min_days, b: car.max_days }))}</div>` : ""}`;
      btn.disabled = !(okFree && okDays);
    } catch (err) { sum.innerHTML = `<div class="notice">${esc(err.message)}</div>`; btn.disabled = true; }
  }
  $("#qbForm", box).addEventListener("submit", async (e) => {
    e.preventDefault();
    await withLoading($("#qbSend", box), async () => {
      try {
        const b = await api("/api/bookings", { method: "POST", body: { car_id: car.id, start_date: st.start, end_date: st.end, delivery: st.delivery, note: $("#qbNote", box).value.trim() || null } });
        if (Auth.user.active_mode !== "renter") await Auth.setMode("renter");
        box.innerHTML = `<div class="qb-done"><div class="success-burst">${icon("check", 34)}</div><h3>${esc(t("qb.sent_t"))}</h3>
          <p class="muted">${esc(t("qb.sent_b", { car: carName(car), a: fmtDate(b.start_date), b: fmtDate(b.end_date) }))}</p>
          <div class="row" style="justify-content:center"><button class="btn btn-outline" data-close>${esc(t("common.close"))}</button>
          <a class="btn" href="/dashboard.html?mode=renter#bookings">${esc(t("dash.my_bookings"))}</a></div></div>`;
      } catch (err) { toast(err.message, "error"); }
    });
  });
}
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-quickbook]");
  if (!b) return;
  e.preventDefault(); quickBook(+b.dataset.quickbook);
});
