"use strict";
/* Test pochta qutisi: SMTP/SMS ulanmaganda kodlar shu yerda ko'rinadi. Faqat dev/demo va lokal tarmoqda ochiladi. */
(async () => {
  await boot("");
  const page = $("#page");
  async function load() {
    let d;
    try { d = await api("/api/dev/outbox"); }
    catch { page.innerHTML = `<div class="empty card"><h3>${esc(t("dev.unavailable"))}</h3><p>${esc(t("dev.unavailable_d"))}</p></div>`; return; }
    page.innerHTML = `<div class="page-head"><div><h1>${esc(t("dev.title"))}</h1><div class="muted">${esc(t("dev.sub"))}</div></div>
        <button class="btn btn-outline" id="reload">${esc(t("dev.refresh"))}</button></div>
      <div class="test-banner">${icon("info", 18)}<div><b>${esc(t("dev.banner_t"))}</b><span>${esc(t("dev.banner_b"))}</span></div></div>
      <div class="inbox">${d.items.length ? d.items.map((m) => {
        const code = (m.body.match(/\b\d{6}\b/) || [])[0];
        return `<article class="card mail"><div class="mail-head"><span class="tag ${m.channel === "sms" ? "tag-pending" : "tag-info"}">${m.channel === "sms" ? "SMS" : "Email"}</span>
          <b>${esc(m.to_addr)}</b><span class="spacer"></span><span class="small muted">${timeAgo(m.created_at)}</span></div>
          ${m.subject ? `<div class="mail-subj">${esc(m.subject)}</div>` : ""}
          ${code ? `<div class="mail-code"><span>${esc(code)}</span><button class="btn btn-sm btn-outline" data-copy="${esc(code)}">${esc(t("dev.copy"))}</button></div>` : ""}
          <pre class="mail-body">${esc(m.body)}</pre></article>`;
      }).join("") : `<div class="empty card">${esc(t("dev.empty"))}</div>`}</div>`;
    $("#reload").addEventListener("click", load);
    $$("[data-copy]").forEach((b) => b.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(b.dataset.copy); toast(t("dev.copied"), "ok"); } catch { toast(b.dataset.copy); }
    }));
  }
  load();
  setInterval(() => { if (!document.hidden) load(); }, 8000);
  document.addEventListener("langchange", load);
})();
