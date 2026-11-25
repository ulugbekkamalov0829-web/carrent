/* Elektron shartnoma hujjati: matn (sarlavhalar, bandlar), imzolar, elektron muhr va QR-kod.
   Shartnoma sahifasida ham, admin panelda ham shu ko'rinish ishlatiladi; chop etish (PDF) uchun A4 uslubi. */
"use strict";

const ContractDoc = {
  /** Shartnoma matni: "# " — sarlavha, "## " — bo'lim; qolgani bandlar. Hammasi esc() orqali — HTML kiritib bo'lmaydi */
  body(text) {
    return text.split(/\n/).map((line) => {
      const l = line.trim();
      if (!l) return "";
      if (l.startsWith("# ")) return `<h1>${esc(l.slice(2))}</h1>`;
      if (l.startsWith("## ")) return `<h2>${esc(l.slice(3))}</h2>`;
      const m = l.match(/^(\d+\.\d+\.)\s*(.*)$/);
      return m ? `<p class="cl"><b>${esc(m[1])}</b> ${esc(m[2])}</p>` : `<p>${esc(l)}</p>`;
    }).join("");
  },

  /** Doira shaklidagi elektron muhr (SVG): matn aylana bo'ylab */
  stamp(c) {
    const date = (c.approved_at || "").slice(0, 10).split("-").reverse().join(".");
    return `<svg class="e-stamp" viewBox="0 0 200 200" role="img" aria-label="${esc(t("ctr.stamp_aria"))}">
      <defs><path id="stTop" d="M 30 100 A 70 70 0 0 1 170 100"/><path id="stBot" d="M 22 100 A 78 78 0 0 0 178 100"/></defs>
      <circle cx="100" cy="100" r="94" fill="none" stroke="currentColor" stroke-width="4"/>
      <circle cx="100" cy="100" r="64" fill="none" stroke="currentColor" stroke-width="2"/>
      <text font-size="12.5" font-weight="800" letter-spacing="1.6" fill="currentColor"><textPath href="#stTop" startOffset="50%" text-anchor="middle">CARRENT PLATFORMASI</textPath></text>
      <text font-size="11.5" font-weight="700" letter-spacing="1.4" fill="currentColor"><textPath href="#stBot" startOffset="50%" text-anchor="middle">${esc(t("ctr.stamp_ring"))}</textPath></text>
      <text x="100" y="92" font-size="15" font-weight="800" text-anchor="middle" fill="currentColor">✓ ${esc(t("ctr.stamp_ok"))}</text>
      <text x="100" y="112" font-size="12" text-anchor="middle" fill="currentColor">${esc(c.number)}</text>
      <text x="100" y="130" font-size="12" text-anchor="middle" fill="currentColor">${esc(date)}</text></svg>`;
  },

  qr(url) {
    if (typeof qrcode !== "function") return "";
    const q = qrcode(0, "M"); q.addData(url); q.make();
    return q.createSvgTag({ cellSize: 3, margin: 2, scalable: true });
  },

  sig(label, name, at) {
    return `<div class="sig ${at ? "ok" : ""}"><div class="small muted">${esc(label)}</div><b>${esc(name)}</b>
      ${at ? `<div class="sig-mark">${icon("check", 14)} ${esc(t("ctr.signed_at", { d: at }))}</div>` : `<div class="sig-wait">${esc(t("ctr.not_signed"))}</div>`}</div>`;
  },

  html(c) {
    const url = location.origin + c.verify_path;
    const approved = c.status === "approved";
    return `<article class="contract-paper" id="paper">
      <header class="cp-head"><div class="cp-logo">${icon("car", 22)} Car<b>Rent</b></div><div class="small">№ ${esc(c.number)}<br>${fmtDate(c.created_at)}</div></header>
      <div class="cp-body">${this.body(c.body)}</div>
      <section class="cp-sigs">
        ${this.sig(t("ctr.owner"), c.booking.owner_name, c.owner_signed_at)}
        ${this.sig(t("ctr.renter"), c.booking.renter_name, c.renter_signed_at)}
      </section>
      <footer class="cp-foot">
        <div class="cp-verify">${approved ? this.stamp(c) : `<div class="stamp-wait">${icon("shield", 26)}<span>${esc(t(c.status === "cancelled" ? "ctr.cancelled" : "ctr.stamp_after"))}</span></div>`}</div>
        <div class="cp-qr">${approved ? this.qr(url) : ""}<div class="small">${approved ? esc(t("ctr.qr_hint")) : ""}</div></div>
        <div class="cp-meta small"><div><b>${esc(t("ctr.hash"))}:</b> <code>${esc(c.body_hash.slice(0, 32))}…</code></div>
          ${approved ? `<div><b>${esc(t("ctr.approved_by"))}:</b> ${esc(c.approved_by || "")} · ${esc(c.approved_at || "")}</div>` : ""}
          <div>${esc(t("ctr.legal_note"))}</div></div>
      </footer></article>`;
  },
};
