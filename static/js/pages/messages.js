"use strict";
(async () => {
  await boot("");
  const me = await guard();
  const params = new URLSearchParams(location.search);
  let current = Number(params.get("user")) || null;
  const aboutCar = Number(params.get("car")) || null;
  let lastId = 0, convs = [], msgs = [], partner = null;

  // Suhbatlar kabinet bo'yicha: ijarachi sifatida (boshqalarning mashinasi) yoki owner sifatida (o'z mashinangiz)
  const urlMode = params.get("mode");
  if (urlMode && ["renter", "owner"].includes(urlMode) && me.role !== "admin" && urlMode !== me.active_mode) await Auth.setMode(urlMode);
  let filter = me.role === "admin" ? "all" : "mode";
  async function loadConvs() { convs = (await api("/api/messages")).items; drawConvs(); }
  function drawTabs() {
    if (me.role === "admin") return;
    const cm = curMode(), other = convs.filter((c) => c.ctx && c.ctx !== cm && c.unread).reduce((a, c) => a + c.unread, 0);
    $("#convTabs").innerHTML = `<button class="${filter === "mode" ? "on" : ""}" data-f="mode">${esc(modeLabel(cm))}</button>
      <button class="${filter === "all" ? "on" : ""}" data-f="all">${esc(t("common.all"))}${other ? ` <i class="cnt">${other}</i>` : ""}</button>`;
  }
  function drawConvs() {
    drawTabs();
    const q = $("#convSearch").value.trim().toLowerCase();
    const list = convs.filter((c) => (filter === "all" || !c.ctx || c.ctx === curMode() || c.other_id === current)
      && (!q || c.other_name.toLowerCase().includes(q) || c.last_body.toLowerCase().includes(q)));
    $("#convs").innerHTML = list.length ? list.map((c) => `
      <a class="conv ${c.other_id === current ? "active" : ""}" href="?user=${c.other_id}" data-user="${c.other_id}">
        <span class="avatar">${esc(initials(c.other_name))}</span>
        <div class="info"><b>${esc(c.other_name)}</b>${c.ctx ? ` <span class="mode-tag m-${c.ctx}">${esc(t(c.ctx === "owner" ? "chat.ctx_owner" : "chat.ctx_renter"))}</span>` : ""}<div class="last">${c.last_is_mine ? esc(t("chat.you")) + ": " : ""}${esc(c.last_body)}</div></div>
        ${c.unread ? `<span class="cnt">${c.unread}</span>` : ""}</a>`).join("")
      : `<div class="empty small">${esc(t(q ? "chat.no_results" : "chat.empty"))}</div>`;
  }

  $("#convTabs").addEventListener("click", (e) => { const b = e.target.closest("[data-f]"); if (b) { filter = b.dataset.f; drawConvs(); } });
  document.addEventListener("summary", () => loadConvs().catch(() => {}));
  async function openThread(userId) {
    current = userId; lastId = 0; msgs = [];
    $("#chat").classList.add("has-thread");
    const data = await api(`/api/messages/${userId}`);
    partner = data.partner;
    $("#thread").innerHTML = `<div class="thread-head"><a class="btn btn-sm btn-outline back-btn" href="/messages.html" aria-label="${esc(t("common.back"))}">‹</a>
        <span class="avatar">${esc(initials(partner.full_name))}</span><b>${esc(partner.full_name)}</b></div>
      <div class="thread-body" id="tbody" aria-live="polite"></div>
      <form class="thread-form" id="sendForm"><textarea class="input" name="body" maxlength="2000" placeholder="${esc(t("chat.placeholder"))}" aria-label="${esc(t("chat.placeholder"))}" required></textarea>
        <button class="btn" aria-label="${esc(t("common.send"))}">➤</button></form>`;
    append(data.items);
    if (!data.items.length) $("#tbody").innerHTML = `<div class="empty small" id="noMsg">${esc(t("chat.start"))}</div>`;
    const form = $("#sendForm"), ta = $("textarea", form);
    ta.focus();
    ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = ta.value.trim(); if (!body) return;
      ta.value = "";
      try { await api("/api/messages", { method: "POST", body: { to_user_id: userId, body, car_id: aboutCar } }); await poll(); loadConvs(); }
      catch (err) { ta.value = body; toast(err.message, "error"); }
    });
    loadConvs();
  }

  const bubble = (m) => `<div class="bubble ${m.sender_id === me.id ? "mine" : ""}">`
    + (m.car_title ? `<div class="about">🚗 ${esc(m.car_title)}</div>` : "")
    + `<div class="text">${esc(m.body)}</div><div class="time">${timeAgo(m.created_at)}${m.sender_id === me.id ? (m.is_read ? " · ✓✓" : " · ✓") : ""}</div></div>`;
  function append(items) {
    const box = $("#tbody"); if (!box || !items.length) return;
    $("#noMsg")?.remove();
    msgs = msgs.concat(items);
    box.insertAdjacentHTML("beforeend", items.map(bubble).join(""));
    lastId = items[items.length - 1].id;
    box.scrollTop = box.scrollHeight;
  }
  async function poll() {
    if (!current || document.hidden) return;
    try { append((await api(`/api/messages/${current}?after=${lastId}`)).items); } catch {}
  }

  $("#convs").addEventListener("click", (e) => {
    const a = e.target.closest("[data-user]"); if (!a) return;
    e.preventDefault(); history.pushState(null, "", `?user=${a.dataset.user}`); openThread(+a.dataset.user);
  });
  $("#convSearch").addEventListener("input", drawConvs);
  window.addEventListener("popstate", () => location.reload());
  document.addEventListener("langchange", () => { drawConvs(); if (current) { const box = $("#tbody"); if (box) box.innerHTML = msgs.map(bubble).join(""); } });

  await loadConvs();
  if (current && current !== me.id) await openThread(current);
  setInterval(poll, 4000);
  setInterval(loadConvs, 15000);
})();
