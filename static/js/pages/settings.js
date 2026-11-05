"use strict";
(async () => {
  await boot("settings");
  await guard("user", "admin");
  const meta = await api("/api/meta").catch(() => ({}));
  const body = $("#setBody");
  const SECTIONS = [["profile", "set.profile", "user"], ["verify", "set.verify", "shield"], ["documents", "docs.title", "idcard"], ["cards", "cards.title", "card"],
    ["security", "set.security", "lock"],
    ["notifications", "set.notifications", "bell"], ["privacy", "set.privacy", "eye"], ["language", "set.language", "globe"], ["danger", "set.danger", "trash"]];
  const u = () => Auth.user;
  const can = { email: meta.email_real || meta.dev_inbox, sms: meta.sms_real || meta.dev_inbox };

  function nav() {
    $("#setNav").setAttribute("aria-label", t("nav.settings"));
    $("#setNav").innerHTML = SECTIONS.filter(([k]) => !["danger", "documents", "cards"].includes(k) || u().role !== "admin")
      .map(([k, key, ico]) => `<a href="#${k}" class="${k === "danger" ? "danger" : ""}" data-sec="${k}">${icon(ico, 18)}${esc(t(key))}</a>`).join("");
  }
  const card = (id, title, sub, inner, cls = "") => `<section class="card card-pad ${cls}" id="${id}"><div class="set-head"><div><h2>${esc(title)}</h2>${sub ? `<p>${esc(sub)}</p>` : ""}</div></div>${inner}</section>`;
  const vTag = (ok) => ok ? `<span class="verified">${icon("check", 13)} ${esc(t("verify.ok"))}</span>` : `<span class="tag tag-pending">${esc(t("verify.no"))}</span>`;

  // Bron sahifasidan "To'ldirish" bosib kelgan bo'lsa — qaytish tugmasi (faqat sayt ichidagi manzil)
  const back = new URLSearchParams(location.search).get("back");
  const backOk = back && back.startsWith("/") && !back.startsWith("//");
  function draw() {
    nav();
    const me = u(), p = me.notify_prefs || {};
    body.innerHTML =
      card("profile", t("set.profile"), t("set.profile_sub"), `
        <div class="avatar-edit">${avatarHtml(me)}<div><label class="btn btn-outline btn-sm" for="avFile" style="margin:0">${icon("camera", 16)} ${esc(t("set.avatar_pick"))}</label>
          <input type="file" id="avFile" accept="image/jpeg,image/png,image/webp" class="sr-only"><div class="hint">${esc(t("hint.avatar"))}</div></div></div>
        <form id="pForm" novalidate style="max-width:620px">
          <div class="field"><label for="pn">${esc(t("field.full_name"))}</label><input class="input" id="pn" name="full_name" value="${esc(me.full_name)}" required data-hint="hint.full_name"></div>
          <div class="grid-2"><div class="field"><label for="pp">${esc(t("field.phone"))}</label><input class="input" type="tel" id="pp" name="phone" value="${esc(me.phone || "")}" required placeholder="+998 90 123 45 67" data-hint="hint.phone_change"></div>
          <div></div>
          <div class="field"><label for="pr">${esc(t("place.region"))}</label><select class="input" id="pr" name="region" data-hint="hint.region"></select></div>
          <div class="field"><label for="pdist">${esc(t("place.district"))}</label><select class="input" id="pdist" name="district"></select></div></div>
          <button class="btn">${esc(t("common.save"))}</button></form>`) +
      card("verify", t("set.verify"), t("set.verify_sub"), `
        <div class="status-row"><span class="ico-box">${icon("mail")}</span><div class="grow"><b>${esc(me.email)}</b><span class="small muted">${esc(t("field.email"))}</span></div>
          ${vTag(me.email_verified)}${me.email_verified ? "" : `<button class="btn btn-sm" data-vstart="email" ${can.email ? "" : "disabled"}>${esc(t("verify.send"))}</button>`}
          <button class="btn btn-sm btn-outline" id="emailChangeBtn" ${can.email ? "" : "disabled"}>${esc(t("set.change_email"))}</button>
          <div class="verify-box hidden" id="vbox-email"></div></div>
        <div class="status-row"><span class="ico-box">${icon("phone")}</span><div class="grow"><b>${esc(me.phone ? fmtPhone(me.phone) : "—")}</b><span class="small muted">${esc(t("field.phone"))}</span></div>
          ${vTag(me.phone_verified)}${me.phone_verified || !me.phone ? "" : `<button class="btn btn-sm" data-vstart="sms" ${can.sms ? "" : "disabled"}>${esc(t("verify.send_sms"))}</button>`}
          <div class="verify-box hidden" id="vbox-sms"></div></div>
        ${!can.email || !can.sms ? `<p class="small muted" style="margin:10px 0 0">${esc(t(!can.email ? "set.channels_off" : "set.sms_off"))}</p>` : ""}
        <div class="verify-box hidden" id="emailChangeBox" style="margin-top:12px"></div>`) +
      (me.role === "admin" ? "" : card("documents", t("docs.title"), t("docs.sub"), `<div id="docsBox"><div class="skeleton" style="height:180px"></div></div>`)
        + card("cards", t("cards.title"), t("cards.sub"), `<div id="cardsBox"><div class="skeleton" style="height:140px"></div></div>`)) +
      card("security", t("set.security"), t("set.security_sub"), `
        <form id="pwForm" novalidate style="max-width:520px">
          <div class="field"><label for="op">${esc(t("sec.current"))}</label><div class="pw-wrap"><input class="input" type="password" id="op" name="old_password" autocomplete="current-password" required><button type="button" class="pw-eye" data-pw="op"></button></div></div>
          <div class="field"><label for="np">${esc(t("sec.new"))}</label><div class="pw-wrap"><input class="input" type="password" id="np" name="new_password" autocomplete="new-password" required minlength="8"><button type="button" class="pw-eye" data-pw="np"></button></div></div>
          <button class="btn">${esc(t("sec.update"))}</button><p class="small muted" style="margin-top:8px">${esc(t("set.pw_note"))}</p></form>
        <h3 style="margin-top:22px">${icon("lock", 18)} ${esc(t("lock.title"))}</h3>
        <div id="pinBox" class="pin-box">${IS_APP ? `<div class="skeleton" style="height:50px"></div>` : `<div class="notice small">${icon("info", 15)} ${esc(t("lock.web_note"))}
          ${Install.available() ? ` <button type="button" class="linkbtn" id="pinInstall">${esc(t("pwa.install"))}</button>` : ""}</div>`}</div>
        ${IS_APP ? `<h3 style="margin-top:22px">${icon("finger", 18)} ${esc(t("pk.title"))}</h3><p class="small muted">${esc(t("pk.sub"))}</p>
        <div id="pkBox"><div class="skeleton" style="height:60px"></div></div>` : ""}
        <h3 style="margin-top:22px">${esc(t("set.sessions"))}</h3><p class="small muted">${esc(t("set.sessions_sub"))}</p>
        <div id="sessions"><div class="skeleton" style="height:80px"></div></div>
        <button class="btn btn-outline btn-sm" id="logoutAll" style="margin-top:10px">${esc(t("set.logout_all"))}</button>`) +
      card("notifications", t("set.notifications"), t("set.notifications_sub"), `
        <form id="nForm">
          ${sw("email_booking", p.email_booking, "set.n_email_booking", "set.n_email_booking_d", !can.email)}
          ${sw("email_messages", p.email_messages, "set.n_email_messages", "set.n_email_messages_d", !can.email)}
          ${sw("sms_booking", p.sms_booking, "set.n_sms_booking", "set.n_sms_booking_d", !can.sms)}
          ${!meta.email_real || !meta.sms_real ? `<p class="small muted" style="margin:8px 0 0">${esc(t(meta.dev_inbox ? "set.n_dev" : "set.n_off"))}</p>` : ""}
        </form>`) +
      card("privacy", t("set.privacy"), t("set.privacy_sub"), `
        <form id="prForm">${sw("show_phone", me.show_phone, "set.show_phone", "set.show_phone_d")}${sw("marketing_ok", me.marketing_ok, "set.marketing", "set.marketing_d")}</form>`) +
      card("language", t("set.language"), t("set.language_sub"), `<div class="lang-cards">${I18N.langs.map((l) =>
        `<button type="button" data-setlang="${l}" class="${l === I18N.lang ? "on" : ""}"><b>${l.toUpperCase()}</b>${esc(I18N.names[l])}</button>`).join("")}</div>`) +
      (me.role === "admin" ? "" : card("danger", t("set.danger"), t("set.danger_sub"), `
        <form id="delForm" novalidate style="max-width:520px"><div class="field"><label for="dp">${esc(t("field.password"))}</label>
          <div class="pw-wrap"><input class="input" type="password" id="dp" autocomplete="current-password" required data-hint="hint.delete"><button type="button" class="pw-eye" data-pw="dp"></button></div></div>
          <button class="btn btn-danger">${icon("trash", 16)} ${esc(t("set.delete"))}</button></form>`, "danger-zone"));
    applyHints(body); bindPasswordToggles(body);
    newPw = pwChecklist($("#np")); pwGenerator($("#np"));
    bind(); loadSessions(); showSection();
    if (me.role !== "admin") { loadDocs(); loadCards(); }
    loadPasskeys(); loadPin();
  }

  // ---------------- Hujjatlar: guvohnoma, pasport/ID, selfi ----------------
  const DOCS = [["license", "idcard"], ["id_card", "user"], ["selfie", "camera"]];
  const docTag = (st) => `<span class="tag ${st === "approved" ? "tag-ok" : st === "pending" ? "tag-pending" : st === "rejected" ? "tag-bad" : "tag-hidden"}">${esc(t("docs.st_" + (st || "none")))}</span>`;
  // ---------------- Barmoq izi / yuz bilan kirish ----------------
  async function loadPin() {
    $("#pinInstall")?.addEventListener("click", () => Install.run());
    const box = $("#pinBox"); if (!box || !IS_APP) return;
    const st = await api("/api/me/pin?device_id=" + AppLock.device()).catch(() => ({ set: false }));
    box.innerHTML = `<div class="pk-item">${icon("lock", 20)}<div><b>${esc(t(st.set ? "lock.on" : "lock.off"))}</b>
      <div class="small muted">${esc(t("lock.desc"))}</div></div>
      <button class="btn btn-sm btn-soft" id="pinChange">${esc(t(st.set ? "lock.change" : "lock.set_btn"))}</button></div>`;
    $("#pinChange").addEventListener("click", async () => { if (await AppLock.setup(false)) loadPin(); });
  }

  async function loadPasskeys() {
    const box = $("#pkBox"); if (!box) return;
    const { items } = await api("/api/passkeys");
    const can = await Passkey.canPlatform();
    box.innerHTML = `${items.length ? `<div class="pk-list">${items.map((p) => `<div class="pk-item">${icon("finger", 20)}<div><b>${esc(p.name || t("pk.device"))}</b>
        <div class="small muted">${esc(t("pk.added", { d: fmtDate(p.created_at) }))}${p.last_used ? " · " + esc(t("pk.used", { d: timeAgo(p.last_used) })) : ""}</div></div>
        <button class="linkbtn danger" data-pkdel="${p.id}">${esc(t("common.delete"))}</button></div>`).join("")}</div>` : ""}
      ${can ? `<button class="btn btn-soft" id="pkAdd" style="margin-top:8px">${icon("finger", 16)} ${esc(t(items.length ? "pk.add_more" : "pk.enable"))}</button>`
        : `<div class="notice small">${esc(t(Passkey.supported() ? "pk.no_sensor" : "pk.unsupported"))}</div>`}`;
    $("#pkAdd")?.addEventListener("click", async (e) => {
      await withLoading(e.currentTarget, async () => {
        try { await Passkey.register(); toast(t("pk.enabled"), "ok"); loadPasskeys(); }
        catch (err) { if (err.name !== "NotAllowedError") toast(err.message || t("pk.failed"), "error"); }
      });
    });
    box.onclick = async (e) => {
      const d = e.target.closest("[data-pkdel]");
      if (d && await confirmBox(t("pk.del_confirm"), t("common.delete"), true)) {
        await api(`/api/passkeys/${d.dataset.pkdel}`, { method: "DELETE" });
        try { localStorage.removeItem("cr.passkey"); } catch { /* */ }
        loadPasskeys(); loadPin();
      }
    };
  }

  // ---------------- JSHSHIR va pasport: avtomatik tekshiruv ----------------
  async function identityBlock() {
    const st = await api("/api/me/identity").catch(() => null);
    const done = st && st.identity_status !== "none";
    return `<div class="id-check card">
      <div class="row" style="justify-content:space-between"><b>${icon("idcard", 18)} ${esc(t("idc.title"))}</b>${done ? `<span class="verified">${icon("check", 13)} ${esc(t("idc.checked"))}</span>` : ""}</div>
      <p class="small muted" style="margin:6px 0 10px">${esc(t("idc.sub"))}</p>
      ${done ? `<div class="doc-meta small">${st.pinfl_mask ? `<span>${esc(t("idc.pinfl"))}: ${esc(st.pinfl_mask)}</span>` : ""}${st.passport_mask ? `<span>${esc(t("idc.passport"))}: ${esc(st.passport_mask)}</span>` : ""}
        ${st.birth_date ? `<span>${esc(t("idc.born"))}: ${fmtDate(st.birth_date)}</span><span>${esc(t(st.gender === "m" ? "idc.male" : "idc.female"))}</span>` : ""}</div>` : ""}
      <form id="idForm" class="id-form ${done ? "hidden" : ""}" novalidate>
        <div class="field"><label for="idPinfl">${esc(t("idc.pinfl"))}</label><input class="input" id="idPinfl" inputmode="numeric" maxlength="14" autocomplete="off" placeholder="31505900010012" value="">
          <div class="hint show small muted" id="idPinflHint">${esc(t("idc.pinfl_hint"))}</div></div>
        <div class="id-or">${esc(t("idc.or"))}</div>
        <div class="field"><label for="idPass">${esc(t("idc.passport"))}</label><input class="input caps" id="idPass" maxlength="11" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="AD 1234567"></div>
        <button class="btn btn-sm">${icon("shield", 15)} ${esc(t("idc.check"))}</button></form>
      ${done ? `<button class="linkbtn" id="idEdit">${esc(t("common.edit"))}</button>` : ""}
      <p class="small muted" style="margin:10px 0 0">${icon("info", 13)} ${esc(t("idc.myid"))}</p></div>`;
  }
  function bindIdentity() {
    const pin = $("#idPinfl"); if (!pin) return;
    $("#idEdit")?.addEventListener("click", () => { $("#idForm").classList.remove("hidden"); $("#idEdit").remove(); });
    // Yozish davomida: JSHSHIR ichidan tug'ilgan sana va jins o'qiladi
    pin.addEventListener("input", () => {
      pin.value = pin.value.replace(/\D/g, "").slice(0, 14);
      const p = pin.value, c = { 3: 1900, 4: 1900, 5: 2000, 6: 2000 }[p[0]];
      let msg = t("idc.pinfl_hint");
      if (p.length >= 7 && c) {
        const d = new Date(c + +p.slice(5, 7), +p.slice(3, 5) - 1, +p.slice(1, 3));
        msg = d.getDate() === +p.slice(1, 3) && d.getMonth() === +p.slice(3, 5) - 1 ? t("idc.parsed", { d: fmtDate(isoDate(d)), g: t(+p[0] % 2 ? "idc.male" : "idc.female") }) : t("idc.bad_date");
      } else if (p.length && !c) msg = t("idc.bad_first");
      $("#idPinflHint").textContent = msg;
    });
    // Telefon klaviaturasi so'zni "yig'ib" turganda (IME) qiymatni qayta yozmaymiz — aks holda harflar yo'qolardi
    $("#idPass").addEventListener("blur", (e) => { e.target.value = e.target.value.toUpperCase().replace(/[^A-Z0-9 ]/g, ""); });
    $("#idForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      await withLoading($("#idForm .btn"), async () => {
        const pv = $("#idPass").value.toUpperCase().replace(/[^A-Z0-9]/g, "");
        if (!pin.value && !pv) { toast(t("idc.need_one"), "error"); return; }
        try { await api("/api/me/identity", { method: "PUT", body: { pinfl: pin.value || null, passport: pv || null } }); toast(t("idc.ok"), "ok"); loadDocs(); }
        catch (err) { toast(err.message, "error"); }
      });
    });
  }

  async function loadDocs() {
    const box = $("#docsBox"); if (!box) return;
    const [d, idHtml] = await Promise.all([api("/api/me/documents"), identityBlock()]);
    Auth.user.docs_status = d.status;
    box.innerHTML = idHtml + `<div class="docs-banner st-${d.status}">${icon(d.status === "verified" ? "check" : d.status === "rejected" ? "flag" : "shield", 20)}
        <div><b>${esc(t("docs.overall_" + d.status))}</b><div class="small">${esc(t("docs.why"))}</div></div></div>
      <div class="docs-grid">${DOCS.map(([k, ico]) => { const x = d.docs[k];
        return `<div class="doc-card card">
          <div class="row" style="justify-content:space-between"><b>${icon(ico, 18)} ${esc(t("docs.k_" + k))}</b>${docTag(x?.expired ? "rejected" : x?.status)}</div>
          <p class="small muted" style="margin:6px 0">${esc(t("docs.h_" + k))}</p>
          ${x ? `<div class="doc-meta small">${x.number_mask ? `<span>№ ${esc(x.number_mask)}</span>` : ""}${x.categories ? `<span>${esc(t("docs.cat"))}: ${esc(x.categories)}</span>` : ""}${x.expires_on ? `<span>${esc(t("docs.until"))}: ${fmtDate(x.expires_on)}</span>` : ""}</div>
            <div class="doc-thumbs">${x.files.map((f) => `<a href="/api/files/${esc(f)}" target="_blank" rel="noopener"><img src="/api/files/${esc(f)}" alt="" loading="lazy"></a>`).join("")}</div>
            ${x.status === "rejected" || x.expired ? `<div class="notice small" style="margin-top:8px">${esc(x.expired ? t("docs.expired") : t("docs.rejected", { r: x.reject_reason || "" }))}</div>` : ""}` : ""}
          ${!x || x.status !== "approved" || x.expired ? `<form class="doc-form" data-kind="${k}" novalidate>
            ${k !== "selfie" ? `<div class="field"><label>${esc(t(k === "license" ? "docs.lic_no" : "docs.id_no"))}</label><input class="input" name="number" maxlength="30" required placeholder="${k === "license" ? "AF 1234567" : "AD 1234567"}" autocomplete="off"></div>` : ""}
            ${k === "license" ? `<div class="grid-2"><div class="field"><label>${esc(t("docs.cat"))}</label><input class="input" name="categories" maxlength="20" placeholder="B, C" required></div>
              <div class="field"><label>${esc(t("docs.until"))}</label><input class="input" type="date" name="expires_on" required min="${isoDate(new Date())}"></div></div>` : ""}
            <div class="field"><label>${esc(t(k === "selfie" ? "docs.selfie_photo" : "docs.photos"))}</label>
              <input class="input" type="file" name="files" accept="image/*" ${k === "selfie" ? 'capture="user"' : ""} multiple required></div>
            <button class="btn btn-sm">${icon("plus", 15)} ${esc(t(x ? "docs.reupload" : "docs.upload"))}</button></form>` : ""}
        </div>`; }).join("")}</div>
      <p class="small muted" style="margin-top:12px">${icon("lock", 14)} ${esc(t("docs.privacy"))}</p>`;
    bindIdentity();
    $$(".doc-form", box).forEach((f) => f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const fd = new FormData();
      fd.append("kind", f.dataset.kind);
      for (const n of ["number", "categories", "expires_on"]) if (f.elements[n]) fd.append(n, f.elements[n].value.trim());
      const files = [...f.elements.files.files].slice(0, 3);
      if (!files.length) { toast(t("docs.pick_files"), "error"); return; }
      for (const x of files) fd.append("files", await compressImage(x, 1800));
      await withLoading($("button", f), async () => {
        try { await api("/api/me/documents", { method: "POST", form: fd }); toast(t("docs.sent"), "ok"); loadDocs(); }
        catch (err) { toast(err.message, "error"); }
      });
    }));
  }

  // ---------------- Bank kartalari (faqat maskalangan ko'rinishda saqlanadi) ----------------
  const BRAND = { uzcard: "UZCARD", humo: "HUMO", visa: "VISA", mastercard: "Mastercard", other: "" };
  async function loadCards() {
    const box = $("#cardsBox"); if (!box) return;
    const { items } = await api("/api/me/cards");
    box.innerHTML = `<div class="bank-cards">${items.map((c) => `<div class="bank-card b-${c.brand}">
        <div class="bc-top"><b>${esc(BRAND[c.brand] || "")}</b>${c.is_default ? `<span class="bc-def">${esc(t("cards.default"))}</span>` : ""}</div>
        <div class="bc-num">${esc(c.first6.slice(0, 4))} ${esc(c.first6.slice(4))}•• •••• ${esc(c.last4)}</div>
        <div class="bc-bot"><span>${esc(c.holder || "")}</span><span>${String(c.exp_month).padStart(2, "0")}/${String(c.exp_year).slice(2)}</span></div>
        <div class="bc-acts">${c.is_default ? "" : `<button class="linkbtn" data-cdef="${c.id}">${esc(t("cards.make_default"))}</button>`}<button class="linkbtn danger" data-cdel="${c.id}">${esc(t("common.delete"))}</button></div></div>`).join("")}
      </div>
      ${items.length < 5 ? `<div class="pay-add card" id="payAdd">
        <div class="pay-stage">
          <div class="cc3d" id="cc3d"><div class="cc-glow"></div><div class="cc-inner">
            <div class="cc-face cc-front"><div class="cc-row"><span class="cc-chip"></span><span class="cc-nfc">)))</span><b class="cc-brand" id="ccBrand">CARD</b></div>
              <div class="cc-num" id="ccNum">•••• •••• •••• ••••</div>
              <div class="cc-row cc-meta"><div><small>${esc(t("cards.holder"))}</small><span id="ccHold">${esc(t("cards.holder_ph"))}</span></div><div><small>${esc(t("cards.exp_short"))}</small><span id="ccExp">••/••</span></div></div></div>
            <div class="cc-face cc-back"><div class="cc-strip"></div><div class="cc-back-body" id="ccBack">${icon("lock", 18)}<span>${esc(t("cards.back_note"))}</span></div></div>
          </div></div>
          <div class="pay-auth hidden" id="payAuth"><span class="spin"></span><b>${esc(t("cards.checking"))}</b><small id="payAuthSub"></small></div>
          <ul class="pay-trust"><li>${icon("shield", 15)} ${esc(t("cards.trust1"))}</li><li>${icon("lock", 15)} ${esc(t("cards.trust2"))}</li></ul>
        </div>
        <form class="pay-form" id="cardForm" novalidate>
          <h3>${esc(t("cards.add_title"))}</h3><p class="small muted">${esc(t("cards.add_sub"))}</p>
          <div class="field"><label for="cHold">${esc(t("cards.holder"))}</label><div class="in-ico">${icon("user", 17)}<input class="input" id="cHold" name="holder" autocomplete="cc-name" maxlength="60" placeholder="ALISHER KARIMOV"></div></div>
          <div class="field"><label for="cNum">${esc(t("cards.number"))}</label><div class="in-ico">${icon("card", 17)}<input class="input" id="cNum" name="number" inputmode="numeric" autocomplete="cc-number" placeholder="8600 1234 5678 9012" maxlength="23" required><b class="in-brand" id="cBrand"></b></div></div>
          <div class="field"><label for="cExp">${esc(t("cards.exp"))}</label><div class="in-ico">${icon("calendar", 17)}<input class="input" id="cExp" name="exp" inputmode="numeric" autocomplete="cc-exp" placeholder="MM/YY" maxlength="5" required></div></div>
          ${items.length ? `<label class="check pay-save"><input type="checkbox" name="make_default" value="1"><span><b>${esc(t("cards.make_default_new"))}</b><small>${esc(t("cards.make_default_hint"))}</small></span></label>` : ""}
          <button class="btn btn-block pay-btn" id="cardSave">${icon("lock", 16)} <span>${esc(t("cards.add"))}</span> →</button>
          <p class="small muted pay-note">${icon("shield", 13)} ${esc(t("cards.no_cvv"))}</p>
        </form></div>` : ""}
      <p class="small muted" style="margin-top:12px">${icon("lock", 14)} ${esc(t("cards.safe"))}</p>`;
    const num = $("#cNum"), exp = $("#cExp"), hold = $("#cHold"), cc = $("#cc3d");
    const brandOf = (d) => /^(8600|5614)/.test(d) ? "uzcard" : /^9860/.test(d) ? "humo" : /^4/.test(d) ? "visa" : /^(5[1-5]|2[2-7])/.test(d) ? "mastercard" : "";
    const paint = () => {
      if (!cc) return;
      const d = num.value.replace(/\D/g, "");
      const b = brandOf(d);
      cc.className = "cc3d" + (b ? " b-" + b : "");
      $("#ccBrand").textContent = BRAND[b] || "CARD";
      $("#cBrand").textContent = BRAND[b] || "";
      const shown = (d + "•".repeat(Math.max(0, 16 - d.length))).slice(0, Math.max(16, d.length));
      $("#ccNum").innerHTML = shown.replace(/(.{4})(?=.)/g, "$1 ").split("").map((ch) => ch === " " ? `<i class="sp"></i>` : `<i class="${/\d/.test(ch) ? "on" : ""}">${ch}</i>`).join("");
      $("#ccHold").textContent = hold.value.trim().toUpperCase() || t("cards.holder_ph");
      $("#ccExp").textContent = exp.value || "••/••";
    };
    num?.addEventListener("input", () => { const d = num.value.replace(/\D/g, "").slice(0, 19); num.value = d.replace(/(\d{4})(?=\d)/g, "$1 "); paint(); });
    exp?.addEventListener("input", () => { const d = exp.value.replace(/\D/g, "").slice(0, 4); exp.value = d.length > 2 ? d.slice(0, 2) + "/" + d.slice(2) : d; paint(); });
    hold?.addEventListener("input", paint);
    // Karta egasi va raqam yozilganda — old tomoni; xavfsizlik eslatmasiga bosilganda — orqa tomoni
    [num, exp, hold].forEach((el) => el?.addEventListener("focus", () => cc.classList.remove("flip")));
    $(".pay-note")?.addEventListener("click", () => cc.classList.toggle("flip"));
    // Kursor bilan biroz egiladi (jonli effekt), telefonda o'chiq
    $(".pay-stage")?.addEventListener("pointermove", (e) => {
      if (e.pointerType !== "mouse") return;
      const r = cc.getBoundingClientRect();
      cc.style.setProperty("--rx", `${((e.clientY - r.top) / r.height - .5) * -10}deg`);
      cc.style.setProperty("--ry", `${((e.clientX - r.left) / r.width - .5) * 14}deg`);
    });
    $(".pay-stage")?.addEventListener("pointerleave", () => { cc.style.setProperty("--rx", "0deg"); cc.style.setProperty("--ry", "0deg"); });
    paint();
    $("#cardForm")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = formData(e.target); body.make_default = !!e.target.make_default?.checked;
      const d = num.value.replace(/\D/g, "");
      $("#payAuthSub").textContent = `${BRAND[brandOf(d)] || ""} •••• ${d.slice(-4)}`;
      $("#payAdd").classList.add("authing"); $("#payAuth").classList.remove("hidden");
      const wait = new Promise((r) => setTimeout(r, 900));
      try {
        await api("/api/me/cards", { method: "POST", body }); await wait;
        $("#payAdd").classList.replace("authing", "paid");
        $("#payAuth").innerHTML = `<span class="pay-ok">${icon("check", 30)}</span><b>${esc(t("cards.added"))}</b>`;
        setTimeout(loadCards, 1400);
      } catch (err) { await wait; $("#payAdd").classList.remove("authing"); $("#payAuth").classList.add("hidden"); toast(err.message, "error"); }
    });
    box.onclick = async (e) => {
      const d = e.target.closest("[data-cdel]"), f = e.target.closest("[data-cdef]");
      try {
        if (d && await confirmBox(t("cards.delete_confirm"), t("common.delete"), true)) { await api(`/api/me/cards/${d.dataset.cdel}`, { method: "DELETE" }); loadCards(); }
        if (f) { await api(`/api/me/cards/${f.dataset.cdef}/default`, { method: "POST" }); loadCards(); }
      } catch (err) { toast(err.message, "error"); }
    };
  }
  let newPw;
  /** Har bir bo'lim alohida oyna: faqat tanlangani ko'rinadi (uzun bitta sahifa emas) */
  function showSection() {
    const ids = $$(".settings-body > section").map((x) => x.id);
    const cur = ids.includes(location.hash.slice(1)) ? location.hash.slice(1) : "profile";
    $$(".settings-body > section").forEach((x) => x.classList.toggle("hidden", x.id !== cur));
    if (backOk && !$("#backBar")) body.insertAdjacentHTML("afterbegin", `<div class="ready-back card card-pad" id="backBar">${icon("info", 16)} <span>${esc(t("ready.back_hint"))}</span>
      <a class="btn btn-sm" href="${esc(back)}">← ${esc(t("ready.back_btn"))}</a></div>`);
    $$("#setNav a").forEach((a) => { a.classList.toggle("active", a.dataset.sec === cur); a.toggleAttribute("aria-current", a.dataset.sec === cur); });
    const sec = SECTIONS.find(([k]) => k === cur);
    document.title = `${t(sec[1])} — ${t("nav.settings")} — CarRent`;
  }
  window.addEventListener("hashchange", () => { showSection(); scrollTo({ top: 0, behavior: "smooth" }); });
  function sw(name, on, tKey, dKey, disabled = false) {
    return `<label class="switch"><span class="txt"><b>${esc(t(tKey))}</b><span>${esc(t(dKey))}</span></span>
      <input type="checkbox" name="${name}" ${on ? "checked" : ""} ${disabled ? "disabled" : ""}></label>`;
  }

  async function savePrefs() {
    const me = u(), n = $("#nForm"), pr = $("#prForm");
    const bodyData = { show_phone: pr.show_phone.checked, marketing_ok: pr.marketing_ok.checked,
      email_booking: n.email_booking.checked, email_messages: n.email_messages.checked, sms_booking: n.sms_booking.checked };
    try { const r = await api("/api/me/prefs", { method: "PUT", body: bodyData }); Object.assign(me, r.user); toast(t("common.saved"), "ok"); }
    catch (err) { toast(err.message, "error"); }
  }

  // Kod kiritish bloki (tasdiqlash yoki email almashtirish uchun)
  function codeBox(box, sentTo, onSubmit, onResend) {
    box.classList.remove("hidden");
    box.innerHTML = `<p class="small" style="margin-top:0">${esc(t("verify.sent_to", { to: sentTo }))}</p><div class="otp-host"></div><div class="code-timer"></div>
      <div class="row" style="margin-top:12px"><button class="btn btn-sm" data-ok>${esc(t("verify.confirm"))}</button>
      <button type="button" class="linkbtn" data-resend>${esc(t("otp.resend"))}</button>
      ${meta.dev_inbox ? `<a class="linkbtn" href="/dev-inbox.html" target="_blank" rel="noopener">${esc(t("dev.open_inbox"))}</a>` : ""}</div>`;
    const otp = otpField($(".otp-host", box), () => $("[data-ok]", box).click());
    otp.focus();
    codeTimer($(".code-timer", box), (meta.code_ttl_min || 3) * 60);
    cooldown($("[data-resend]", box), 60, "otp.resend");
    $("[data-ok]", box).addEventListener("click", async () => {
      if (otp.value.length !== 6) { otp.error(); return; }
      try { await onSubmit(otp.value); } catch (err) { otp.error(); toast(err.message, "error"); }
    });
    $("[data-resend]", box).addEventListener("click", async () => {
      try { await onResend(); toast(t("otp.sent"), "ok"); cooldown($("[data-resend]", box), 60, "otp.resend"); codeTimer($(".code-timer", box), (meta.code_ttl_min || 3) * 60); } catch (err) { toast(err.message, "error"); }
    });
  }

  function bind() {
    Places.bind($("#pr"), $("#pdist"), { region: u().region || "", district: u().district || "" });
    applyMasks($("#pForm"));
    $("#pForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = formData(e.target);
      if (d.region && !d.district) { toast(t("place.need_district"), "error"); return; }
      try { const r = await api("/api/auth/me", { method: "PUT", body: { full_name: d.full_name, phone: d.phone, region: d.region || null, district: d.district || null } });
        const phoneChanged = r.user.phone !== u().phone; Object.assign(Auth.user, r.user); toast(t(phoneChanged ? "set.phone_reverify" : "common.saved"), "ok"); renderNavInner(); draw(); }
      catch (err) { showFieldErrors(e.target, err); toast(err.message, "error"); }
    });
    $("#avFile").addEventListener("change", async (e) => {
      const f = e.target.files[0]; if (!f) return;
      if (f.size > 10 * 1024 * 1024) { toast(t("img.too_big", { n: 10 }), "error"); return; }
      const fd = new FormData(); fd.append("avatar", await compressImage(f, 800));
      try { const r = await api("/api/me/avatar", { method: "POST", form: fd }); Object.assign(Auth.user, r.user); toast(t("common.saved"), "ok"); renderNavInner(); draw(); }
      catch (err) { toast(err.message, "error"); }
    });
    $$("[data-vstart]").forEach((b) => b.addEventListener("click", async () => {
      const ch = b.dataset.vstart;
      const start = () => api("/api/me/verify/start", { method: "POST", body: { channel: ch } });
      try {
        const r = await withLoading(b, start);
        codeBox($("#vbox-" + ch), r.sent_to, async (code) => {
          const res = await api("/api/me/verify/confirm", { method: "POST", body: { channel: ch, code } });
          Object.assign(Auth.user, res.user); toast(t("verify.done"), "ok"); draw();
        }, start);
      } catch (err) { toast(err.message, "error"); }
    }));
    $("#emailChangeBtn").addEventListener("click", () => {
      const box = $("#emailChangeBox"); box.classList.remove("hidden");
      box.innerHTML = `<form id="ecForm" novalidate><div class="grid-2"><div class="field"><label for="ecE">${esc(t("set.new_email"))}</label><input class="input" type="email" id="ecE" required placeholder="new@example.com" data-hint="hint.new_email"></div>
        <div class="field"><label for="ecP">${esc(t("field.password"))}</label><div class="pw-wrap"><input class="input" type="password" id="ecP" required autocomplete="current-password" data-hint="hint.confirm_pw"><button type="button" class="pw-eye" data-pw="ecP"></button></div></div></div>
        <button class="btn btn-sm">${esc(t("verify.send"))}</button></form>`;
      applyHints(box); bindPasswordToggles(box); $("#ecE").focus();
      $("#ecForm").addEventListener("submit", async (e) => {
        e.preventDefault();
        const start = () => api("/api/me/email/start", { method: "POST", body: { new_email: $("#ecE").value.trim(), password: $("#ecP").value } });
        try {
          const r = await withLoading($("#ecForm .btn"), start);
          codeBox(box, r.sent_to, async (code) => {
            const res = await api("/api/me/email/confirm", { method: "POST", body: { code } });
            Object.assign(Auth.user, res.user); toast(t("set.email_changed"), "ok"); renderNavInner(); draw();
          }, start);
        } catch (err) { showFieldErrors(e.target, err); toast(err.message, "error"); }
      });
    });
    $("#pwForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!newPw.valid()) { showFieldErrors(e.target, { errors: [{ field: "new_password", msg: newPw.firstError() }] }); return; }
      try { await api("/api/auth/change-password", { method: "POST", body: formData(e.target) }); e.target.reset(); $("#np").dispatchEvent(new Event("input")); toast(t("sec.updated"), "ok"); loadSessions(); }
      catch (err) { showFieldErrors(e.target, err); toast(err.message, "error"); }
    });
    $("#logoutAll").addEventListener("click", async () => {
      if (!(await confirmBox(t("set.logout_all_confirm"), t("common.yes")))) return;
      try { await api("/api/me/logout-all", { method: "POST" }); toast(t("set.logged_out_all"), "ok"); loadSessions(); } catch (err) { toast(err.message, "error"); }
    });
    $$("#nForm input, #prForm input").forEach((i) => i.addEventListener("change", savePrefs));
    $$("[data-setlang]").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.setlang)));
    $("#delForm")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!$("#dp").value) { toast(t("val.password"), "error"); return; }
      if (!(await confirmBox(t("set.delete_confirm"), t("set.delete"), true))) return;
      try { const r = await api("/api/me/delete", { method: "POST", body: { password: $("#dp").value } }); toast(t(r.mode === "deleted" ? "set.deleted_full" : "set.deleted"), "ok"); setTimeout(() => (location.href = "/"), 1200); }
      catch (err) { toast(err.message, "error"); }
    });
  }

  function device(ua) {
    ua = ua || "";
    const os = /Android/i.test(ua) ? "Android" : /iPhone|iPad/i.test(ua) ? "iOS" : /Windows/i.test(ua) ? "Windows" : /Mac OS/i.test(ua) ? "macOS" : /Linux/i.test(ua) ? "Linux" : "";
    const br = /Edg\//.test(ua) ? "Edge" : /OPR\//.test(ua) ? "Opera" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "";
    return [br, os].filter(Boolean).join(" · ") || t("set.unknown_device");
  }
  async function loadSessions() {
    const { items } = await api("/api/me/sessions");
    $("#sessions").innerHTML = items.map((s) => `<div class="session"><span class="ico-box">${icon(/Android|iPhone/i.test(s.user_agent || "") ? "phone" : "grid")}</span>
      <div class="grow"><b>${esc(device(s.user_agent))}</b><span class="small muted">${esc(s.ip || "")} · ${esc(t("set.last_seen"))}: ${timeAgo(s.last_seen)}</span></div>
      ${s.current ? `<span class="tag tag-ok">${esc(t("set.this_device"))}</span>` : `<button class="btn btn-sm btn-outline" data-revoke="${esc(s.id)}">${esc(t("set.revoke"))}</button>`}</div>`).join("");
    $$("[data-revoke]").forEach((b) => b.addEventListener("click", async () => {
      try { await api(`/api/me/sessions/${encodeURIComponent(b.dataset.revoke)}`, { method: "DELETE" }); toast(t("common.done"), "ok"); loadSessions(); } catch (err) { toast(err.message, "error"); }
    }));
  }
  draw();
  document.addEventListener("langchange", draw);
})();
