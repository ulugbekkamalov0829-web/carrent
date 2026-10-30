/* Hisobotlar: owner, ijarachi va admin uchun bitta modul.
   Davr tanlanadi -> server raqamlarni va oddiy tildagi xulosalarni qaytaradi -> bu yerda chiroyli ko'rinishda chiziladi.
   Har bir ko'rsatkich yonida "bu nima degani" izohi bor; CSV (Excel) va chop etish (PDF) tugmalari. */
"use strict";

const Reports = {
  state: { preset: "month", from: "", to: "" },

  presets() {
    const d = new Date(), y = d.getFullYear(), m = d.getMonth();
    const iso = isoDate, ago = (n) => iso(new Date(y, m, d.getDate() - n));
    return {
      week: [ago(6), iso(d)], month: [iso(new Date(y, m, 1)), iso(d)], last_month: [iso(new Date(y, m - 1, 1)), iso(new Date(y, m, 0))],
      d30: [ago(29), iso(d)], q: [ago(89), iso(d)], year: [iso(new Date(y, 0, 1)), iso(d)],
    };
  },

  range() {
    if (this.state.preset !== "custom") [this.state.from, this.state.to] = this.presets()[this.state.preset];
    return [this.state.from, this.state.to];
  },

  async render(view, kind) {
    try { const saved = JSON.parse(localStorage.getItem("rep.state") || "null"); if (saved?.preset) this.state = saved; } catch {}
    const [from, to] = this.range();
    const qs = `from=${from}&to=${to}`;
    const r = await api(`/api/analytics/${kind}?${qs}`);
    view.innerHTML = `<div class="rep">
      ${this.toolbar(kind, qs)}
      <div class="rep-period">${icon("calendar", 16)} <b>${fmtDate(r.period.from)} — ${fmtDate(r.period.to)}</b>
        <span class="muted">· ${esc(t("rep.days_n", { n: r.period.days }))} · ${esc(t("rep.compared", { a: fmtDate(r.prev.from), b: fmtDate(r.prev.to) }))}</span></div>
      <div class="print-only rep-print-head"><b>CarRent — ${esc(t("rep.title"))}: ${esc(t("rep.kind_" + kind))}</b><span>${esc(Auth.user.full_name)} · ${fmtDate(r.generated)}</span></div>
      ${this.insights(r.insights)}
      <div class="stats rep-kpis">${r.kpis.map((k) => this.kpi(k)).join("")}</div>
      <div class="card card-pad rep-chart-card"><div class="row" style="justify-content:space-between"><h3 style="margin:0">${esc(t("rep.chart_" + r.series_label))}</h3>
        <span class="small muted">${esc(t(r.series.unit === "day" ? "rep.by_day" : "rep.by_month"))}</span></div>
        ${this.chart(r.series, r.series2)}</div>
      ${this.tables(kind, r)}
      <p class="small muted rep-foot">${icon("info", 14)} ${esc(t("rep.rule"))}</p>
    </div>`;
    this.bind(view, kind);
  },

  toolbar(kind, qs) {
    const p = this.state.preset;
    return `<div class="rep-toolbar no-print">
      <div class="chips" role="group" aria-label="${esc(t("rep.period"))}">${["week", "month", "last_month", "d30", "q", "year", "custom"].map((k) =>
        `<button type="button" class="chip-btn ${p === k ? "on" : ""}" data-preset="${k}">${esc(t("rep.p_" + k))}</button>`).join("")}</div>
      <form class="rep-custom ${p === "custom" ? "" : "hidden"}" id="repCustom">
        <input class="input" type="date" id="repFrom" value="${esc(this.state.from)}" aria-label="${esc(t("rep.from"))}" required>
        <span class="muted">—</span>
        <input class="input" type="date" id="repTo" value="${esc(this.state.to)}" aria-label="${esc(t("rep.to"))}" required>
        <button class="btn btn-sm">${esc(t("rep.show"))}</button></form>
      <span class="spacer"></span>
      <a class="btn btn-sm btn-outline" href="/api/analytics/${kind}.csv?${qs}" download>${icon("download", 16)} ${esc(t("rep.csv"))}</a>
      <button type="button" class="btn btn-sm btn-outline" id="repPrint">${icon("print", 16)} ${esc(t("rep.print"))}</button>
    </div>`;
  },

  fmt(v, f) {
    if (v === null || v === undefined) return "—";
    if (f === "money") return money(v);
    if (f === "pct") return `${v}%`;
    return numFmt().format(v);
  },

  kpi(k) {
    let delta = "";
    if (k.change !== null && k.change !== undefined) {
      const up = k.change > 0, good = k.change === 0 ? null : up === k.up_good;
      delta = `<span class="delta ${good === null ? "" : good ? "good" : "bad"}">${up ? "▲" : k.change < 0 ? "▼" : "•"} ${Math.abs(k.change)}%</span>`;
    } else if (!k.prev && k.value) delta = `<span class="delta new">${esc(t("rep.new"))}</span>`;
    return `<div class="card stat rep-kpi"><div class="k">${esc(t("rep.k_" + k.code))}</div>
      <div class="v">${k.fmt === "money" ? `${esc(numFmt().format(Math.round(k.value || 0)))}<small class="unit">${esc(t("currency"))}</small>` : esc(this.fmt(k.value, k.fmt))}</div>
      <div class="s">${delta} <span class="muted">${esc(t("rep.was", { v: this.fmt(k.prev, k.fmt) }))}</span></div>
      <div class="rep-hint">${esc(t("rep.h_" + k.code))}</div></div>`;
  },

  insightText(i) {
    const p = { ...(i.params || {}) };
    const moneyKeys = i.code === "rating" ? ["sum", "prev", "fee", "market"] : ["sum", "prev", "fee", "market", "avg"];
    for (const key of moneyKeys) if (typeof p[key] === "number") p[key] = money(p[key]);
    if (p.wd !== undefined) p.wd = t("rep.wd").split(",")[p.wd];
    if (p.body) p.body = t("body." + p.body);
    return t("rep.i_" + i.code, p);
  },

  insights(list) {
    if (!list.length) return "";
    const ico = { good: "check", warn: "flag", info: "bulb", action: "bell" };
    return `<div class="card card-pad rep-insights"><h3>${icon("bulb", 18)} ${esc(t("rep.insights"))}</h3><ul>
      ${list.map((i) => `<li class="ins ins-${i.kind}"><span class="ins-ico">${icon(ico[i.kind] || "info", 16)}</span>
        <span>${esc(this.insightText(i))}${i.link ? ` <a href="${esc(i.link)}" class="no-print">${esc(t("rep.open"))} →</a>` : ""}</span></li>`).join("")}</ul></div>`;
  },

  chart(series, series2) {
    const pts = series.points, max = Math.max(1, ...pts.map((p) => p.v));
    const months = t("cal.months_short").split(",");
    const label = (k) => series.unit === "day" ? k.slice(8) : months[+k.slice(5, 7) - 1];
    const every = pts.length > 40 ? 5 : pts.length > 16 ? 2 : 1;
    const total = pts.reduce((a, p) => a + p.v, 0);
    if (!total) return `<div class="empty" style="padding:30px 10px">${esc(t("rep.no_chart"))}</div>`;
    const fees = series2 ? Object.fromEntries(series2.points.map((p) => [p.k, p.v])) : null;
    return `<div class="chart rep-bars ${pts.length > 16 ? "dense" : ""}" role="img" aria-label="${esc(t("rep.chart_aria", { sum: money(total) }))}">${pts.map((p, i) => {
      const h = p.v ? Math.max(3, (p.v / max) * 100) : 0;
      const feeH = fees && p.v ? (fees[p.k] / p.v) * 100 : 0;
      const tip = `${series.unit === "day" ? fmtDate(p.k) : p.k}: ${money(p.v)} · ${t("chart.bookings_n", { n: p.n })}`;
      return `<div class="bar-wrap" title="${esc(tip)}"><span class="val">${p.v && pts.length <= 16 ? shortMoney(p.v) : ""}</span>
        <div class="bar" style="height:${h}%">${fees ? `<div class="fee" style="height:${feeH}%"></div>` : ""}<div class="net" style="flex:1"></div></div>
        <span class="lbl">${i % every === 0 ? esc(label(p.k)) : ""}</span></div>`;
    }).join("")}</div>
    ${fees ? `<div class="legend"><span><i style="background:var(--primary)"></i>${esc(t("rep.legend_owner"))}</span><span><i style="background:#93a9ec"></i>${esc(t("rep.legend_fee"))}</span></div>` : ""}
    <div class="small muted" style="margin-top:6px">${esc(t("rep.chart_total", { sum: money(total) }))}</div>`;
  },

  table(title, head, body, empty = "rep.no_rows") {
    return `<div class="card rep-table"><div class="card-pad" style="padding-bottom:0"><h3>${esc(t(title))}</h3></div>
      ${body.length ? `<div class="table-wrap"><table class="table responsive"><thead><tr>${head.map((h) => `<th>${esc(t(h))}</th>`).join("")}</tr></thead>
      <tbody>${body.map((row) => `<tr>${row.map((c, i) => `<td data-label="${esc(t(head[i]))}">${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
      : `<div class="empty">${esc(t(empty))}</div>`}</div>`;
  },

  share(v, total) { return total ? `<div class="share"><i style="width:${Math.round((v / total) * 100)}%"></i></div>` : ""; },

  tables(kind, r) {
    const T = r.tables;
    if (kind === "owner") {
      const tot = T.per_car.reduce((a, c) => a + c.payout, 0);
      return this.table("rep.t_per_car", ["col.car", "rep.c_trips", "rep.c_busy", "col.occupancy", "col.revenue", "rep.c_income"],
        T.per_car.map((c) => [`<a href="/car.html?id=${c.id}">${esc(c.title)}</a><div class="small muted">${esc(c.city)}${c.rating ? ` · ★ ${c.rating}` : ""}</div>`,
          c.trips, `${c.busy_days} / ${c.busy_days + c.idle_days}`,
          `<span class="occ ${c.occupancy < 25 ? "low" : c.occupancy >= 60 ? "high" : ""}">${c.occupancy}%</span>`, money(c.gross),
          `<b>${money(c.payout)}</b>${this.share(c.payout, tot)}`]), "rep.no_cars");
    }
    if (kind === "renter") {
      const tot = T.by_body.reduce((a, x) => a + x.spent, 0);
      return `<div class="two-col">${this.table("rep.t_by_body", ["rep.c_body", "rep.c_trips", "rep.c_spent"],
          T.by_body.map((x) => [esc(t("body." + x.key)), x.trips, `${money(x.spent)}${this.share(x.spent, tot)}`]))}
        ${this.table("rep.t_by_city", ["col.city", "rep.c_trips", "rep.c_spent"], T.by_city.map((x) => [esc(x.key), x.trips, money(x.spent)]))}</div>
        ${this.table("rep.t_trips", ["col.car", "col.dates", "rep.c_days", "booking.total", "col.status"],
          T.trips.map((x) => [`<a href="/car.html?id=${x.car_id}">${esc(x.title)}</a>`, `<span class="small">${fmtDate(x.start_date)} → ${fmtDate(x.end_date)}</span>`,
            x.days, money(x.total_price), statusTag(x.status)]))}`;
    }
    const gmv = T.by_city.reduce((a, x) => a + x.gmv, 0);
    const f = T.funnel, created = Object.values(f).reduce((a, x) => a + x, 0);
    const provName = (k) => (k === "test" ? t("pay.test_name") : k === "click" ? "Click" : "Payme");
    return `<div class="two-col">
        ${this.table("rep.t_by_city", ["col.city", "rep.c_trips", "rep.c_gmv", "rep.c_fee"],
          T.by_city.map((x) => [esc(x.key), x.trips, `${money(x.gmv)}${this.share(x.gmv, gmv)}`, money(x.commission)]))}
        <div class="card card-pad"><h3>${esc(t("rep.t_funnel"))}</h3>
          ${created ? `<div class="funnel">${["pending", "approved", "completed", "rejected", "cancelled"].map((s) =>
            `<div class="fn"><span>${esc(t("status." + s))}</span><div class="track"><i class="st-${s}" style="width:${(f[s] / created) * 100}%"></i></div><b>${f[s]}</b></div>`).join("")}</div>
            <p class="small muted" style="margin:10px 0 0">${esc(t("rep.funnel_note", { n: created }))}</p>` : `<div class="empty">${esc(t("rep.no_rows"))}</div>`}</div>
      </div>
      <div class="two-col">
        ${this.table("rep.t_top_owners", ["col.owner", "rep.c_trips", "rep.c_income", "rep.c_fee"],
          T.top_owners.map((o) => [`<b>${esc(o.name)}</b>`, o.trips, money(o.payout), money(o.commission)]))}
        ${this.table("rep.t_top_cars", ["col.car", "rep.c_trips", "rep.c_gmv"],
          T.top_cars.map((c) => [`<a href="/car.html?id=${c.id}">${esc(c.title)}</a><div class="small muted">${esc(c.city)}</div>`, c.trips, money(c.gmv)]))}
      </div>
      ${this.table("rep.t_providers", ["pay.method", "rep.c_count", "pay.amount"], T.providers.map((p) => [esc(provName(p.key)), p.n, money(p.amount)]), "rep.no_online")}`;
  },

  bind(view, kind) {
    const save = () => { try { localStorage.setItem("rep.state", JSON.stringify(this.state)); } catch {} };
    $$("[data-preset]", view).forEach((b) => b.addEventListener("click", () => {
      this.state.preset = b.dataset.preset;
      if (b.dataset.preset === "custom") {
        if (!this.state.from) [this.state.from, this.state.to] = this.presets().month;
        save(); $$("[data-preset]", view).forEach((x) => x.classList.toggle("on", x === b)); $("#repCustom").classList.remove("hidden"); return;
      }
      save(); this.render(view, kind).catch((e) => toast(e.message, "error"));
    }));
    $("#repCustom")?.addEventListener("submit", (e) => {
      e.preventDefault();
      const a = $("#repFrom").value, b = $("#repTo").value;
      if (!a || !b) { toast(t("date.invalid"), "error"); return; }
      this.state = { preset: "custom", from: a <= b ? a : b, to: a <= b ? b : a };
      save(); this.render(view, kind).catch((err) => toast(err.message, "error"));
    });
    $("#repPrint")?.addEventListener("click", () => window.print());
  },
};
