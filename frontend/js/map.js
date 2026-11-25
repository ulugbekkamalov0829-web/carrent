/* Xarita: Leaflet (loyiha ichida, /vendor/leaflet) + OpenStreetMap xaritasi.
   - show():   mashina turgan joyni ko'rsatadi
   - picker(): e'lon formasida joyni xaritadan tanlash (bosish yoki markerni surish) va "Mening joylashuvim"
   - links():  shu nuqtani Yandex Xarita, Google Maps yoki telefondagi xarita ilovasida ochish / marshrut qurish
   - locate(): brauzer orqali joriy joylashuv (foydalanuvchi ruxsat bersa) */
"use strict";

const MapKit = {
  _p: null,
  // Hududlar markazi — mashinaning aniq nuqtasi bo'lmasa, xarita shu yerda ochiladi
  centers: {
    "Toshkent shahri": [41.3111, 69.2797], "Toshkent viloyati": [41.0, 69.6], "Andijon": [40.7821, 72.3442], "Buxoro": [39.7747, 64.4286],
    "Farg'ona": [40.3864, 71.7864], "Jizzax": [40.1158, 67.8422], "Xorazm": [41.5500, 60.6333], "Namangan": [40.9983, 71.6726],
    "Navoiy": [40.1039, 65.3792], "Qashqadaryo": [38.8606, 65.7891], "Qoraqalpog'iston": [42.4600, 59.6100], "Samarqand": [39.6542, 66.9597],
    "Sirdaryo": [40.4897, 68.7842], "Surxondaryo": [37.2242, 67.2783],
  },

  load() {
    if (window.L) return Promise.resolve();
    if (this._p) return this._p;
    this._p = new Promise((resolve, reject) => {
      const css = document.createElement("link");
      css.rel = "stylesheet"; css.href = "/vendor/leaflet/leaflet.css";
      document.head.append(css);
      const s = document.createElement("script");
      s.src = "/vendor/leaflet/leaflet.js";
      s.onload = () => { L.Icon.Default.imagePath = "/vendor/leaflet/images/"; resolve(); };
      s.onerror = () => { this._p = null; reject(new Error(t("map.load_failed"))); };
      document.head.append(s);
    });
    return this._p;
  },

  _base(el, lat, lng, zoom) {
    const map = L.map(el, { scrollWheelZoom: false, attributionControl: true }).setView([lat, lng], zoom);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
    }).addTo(map);
    // Sahifa aylantirilayotganda xarita "ushlab qolmasin": g'ildirak bilan zoom faqat xarita bosilgandan keyin
    map.on("click focus", () => map.scrollWheelZoom.enable());
    map.on("mouseout", () => map.scrollWheelZoom.disable());
    setTimeout(() => map.invalidateSize(), 60);
    return map;
  },

  async show(el, { lat, lng, region, zoom = 15, label = "", approx = null } = {}) {
    await this.load();
    const exact = lat != null && lng != null;
    const [la, ln] = exact ? [lat, lng] : (approx || this.centers[region] || this.centers["Toshkent shahri"]);
    const map = this._base(el, la, ln, exact ? zoom : approx ? 13 : 11);
    if (exact) L.marker([la, ln]).addTo(map).bindPopup(esc(label || t("map.here")));
    else L.circle([la, ln], { radius: approx ? 900 : 4000, color: "#1e40af", fillOpacity: .1, weight: 1 }).addTo(map);
    return map;
  },

  async picker(el, { lat, lng, region, onPick = () => {} } = {}) {
    await this.load();
    const exact = lat != null && lng != null;
    const [la, ln] = exact ? [lat, lng] : (this.centers[region] || this.centers["Toshkent shahri"]);
    const map = this._base(el, la, ln, exact ? 16 : 11);
    let marker = null;
    const set = (a, b, fly = false) => {
      a = +(+a).toFixed(6); b = +(+b).toFixed(6);
      if (!marker) {
        marker = L.marker([a, b], { draggable: true }).addTo(map);
        marker.on("dragend", () => { const p = marker.getLatLng(); set(p.lat, p.lng); });
      } else marker.setLatLng([a, b]);
      if (fly) map.setView([a, b], Math.max(map.getZoom(), 16));
      onPick(a, b);
    };
    if (exact) set(la, ln);
    map.on("click", (e) => set(e.latlng.lat, e.latlng.lng));
    return { map, set, clear: () => { if (marker) { map.removeLayer(marker); marker = null; } }, center: (r) => map.setView(this.centers[r] || [la, ln], 11) };
  },

  locate() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) return reject(new Error(t("map.geo_unsupported")));
      navigator.geolocation.getCurrentPosition(
        (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude, acc: Math.round(p.coords.accuracy) }),
        (e) => reject(new Error(t(e.code === 1 ? "map.geo_denied" : e.code === 3 ? "map.geo_timeout" : "map.geo_failed"))),
        { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 });
    });
  },

  isIOS: () => /iPhone|iPad|iPod/i.test(navigator.userAgent),
  isAndroid: () => /Android/i.test(navigator.userAgent),

  urls(lat, lng, label = "") {
    const q = encodeURIComponent(label || `${lat},${lng}`);
    return {
      yandex: `https://yandex.uz/maps/?pt=${lng},${lat}&z=16&l=map`,
      yandexRoute: `https://yandex.uz/maps/?rtext=~${lat},${lng}&rtt=auto`,
      google: `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`,
      googleRoute: `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`,
      device: this.isIOS() ? `https://maps.apple.com/?ll=${lat},${lng}&q=${q}` : `geo:${lat},${lng}?q=${lat},${lng}(${q})`,
    };
  },

  /** "Qayerda ochish" tugmalari: Yandex, Google, telefon ilovasi va marshrut */
  links(lat, lng, label = "") {
    const u = this.urls(lat, lng, label);
    const phone = this.isIOS() || this.isAndroid();
    return `<div class="map-links">
      <a class="btn btn-sm btn-outline" href="${esc(u.yandex)}" target="_blank" rel="noopener"><span class="mk-y">Я</span> ${esc(t("map.open_yandex"))}</a>
      <a class="btn btn-sm btn-outline" href="${esc(u.google)}" target="_blank" rel="noopener"><span class="mk-g">G</span> ${esc(t("map.open_google"))}</a>
      ${phone ? `<a class="btn btn-sm btn-outline" href="${esc(u.device)}">${icon("phone", 15)} ${esc(t("map.open_phone"))}</a>` : ""}
      <a class="btn btn-sm" href="${esc(u.yandexRoute)}" target="_blank" rel="noopener">${icon("arrowr", 15)} ${esc(t("map.route"))}</a></div>`;
  },
};
