"""v5 tarjimalari: parol qoidalari, kod muddati, kabinetlar bo'yicha bildirishnomalar, tezkor bron, admin filtrlari.
Format build_locales.T bilan bir xil — kalit: (uz, ru, en). OVERRIDE5 — mavjud kalitlarning yangi matni."""

T5 = {
    # ---- parol qoidalari ----
    "pw.r_len": ("Kamida {n} ta belgi", "Не менее {n} символов", "At least {n} characters"),
    "pw.r_upper": ("Kamida bitta katta harf (A–Z)", "Хотя бы одна заглавная буква (A–Z)", "At least one uppercase letter (A–Z)"),
    "pw.r_lower": ("Kamida bitta kichik harf (a–z)", "Хотя бы одна строчная буква (a–z)", "At least one lowercase letter (a–z)"),
    "pw.r_digit": ("Kamida bitta raqam (0–9)", "Хотя бы одна цифра (0–9)", "At least one digit (0–9)"),
    "pw.r_symbol": ("Kamida bitta belgi: ! @ # - _ .", "Хотя бы один символ: ! @ # - _ .", "At least one symbol: ! @ # - _ ."),
    "pw.s_len": ("{n}+ belgi", "{n}+ символов", "{n}+ characters"),
    "pw.s_upper": ("Katta harf (A–Z)", "Заглавная (A–Z)", "Uppercase (A–Z)"),
    "pw.s_lower": ("Kichik harf (a–z)", "Строчная (a–z)", "Lowercase (a–z)"),
    "pw.s_digit": ("Raqam (0–9)", "Цифра (0–9)", "Digit (0–9)"),
    "pw.s_symbol": ("Belgi (! @ # -)", "Символ (! @ # -)", "Symbol (! @ # -)"),
    "pw.met": ("bajarildi", "выполнено", "done"),
    "pw.unmet": ("bajarilmagan", "не выполнено", "not yet"),

    # ---- kodlar ----
    "otp.expires_in": ("Kod {t} dan keyin eskiradi", "Код истечёт через {t}", "Code expires in {t}"),
    "otp.expired": ("Kod muddati tugadi — yangisini so'rang", "Срок кода истёк — запросите новый", "The code has expired — request a new one"),
    "forgot.other_way": ("Boshqa usul / manzil", "Другой способ / адрес", "Another method / address"),
    "chan.not_real_email": ("Email xizmati hali ulanmagan — kod haqiqiy pochtaga bormadi, faqat test qutisiga yozildi.",
                            "Email ещё не подключён — код не ушёл на почту, он записан только в тестовый ящик.",
                            "Email isn't connected yet — the code wasn't emailed, it only went to the test inbox."),
    "chan.not_real_sms": ("SMS xizmati hali ulanmagan — kod telefoningizga bormadi, faqat test qutisiga yozildi.",
                          "SMS ещё не подключены — код не ушёл на телефон, он записан только в тестовый ящик.",
                          "SMS isn't connected yet — the code wasn't texted, it only went to the test inbox."),
    "chan.unavailable": ("Bu usul hozircha ulanmagan", "Этот способ пока не подключён", "This method isn't connected yet"),

    # ---- kabinetlar bo'yicha bildirishnomalar ----
    "notif.for_owner": ("Owner kabineti", "Кабинет владельца", "Owner account"),
    "notif.for_renter": ("Ijarachi kabineti", "Кабинет арендатора", "Renter account"),
    "notif.for_all": ("Umumiy", "Общее", "General"),
    "notif.other_mode": ("{mode}da {n} ta yangi — o'tish", "{mode}: новых {n} — перейти", "{n} new in {mode} — switch"),
    "notif.empty_mode": ("{mode} uchun bildirishnoma yo'q", "Уведомлений для раздела «{mode}» нет", "No notifications for {mode}"),
    "notif.tap_switch": ("Bosing — {mode}ga o'tasiz", "Нажмите — перейдёте в «{mode}»", "Tap to switch to {mode}"),
    "chat.ctx_owner": ("Mening mashinam", "Моя машина", "My car"),
    "chat.ctx_renter": ("Ijara", "Аренда", "Rental"),

    # ---- admin ----
    "admin.renters": ("Ijarachilar", "Арендаторы", "Renters"),
    "admin.new_week": ("7 kunda yangi", "Новые за 7 дней", "New this week"),
    "admin.no_users": ("Bu filtr bo'yicha foydalanuvchi yo'q", "Пользователей по этому фильтру нет", "No users for this filter"),

    # ---- hududlar ----
    "regions.soon": ("Tez orada", "Скоро", "Coming soon"),
    "regions.soon_hint": ("Bu hududda birinchi e'lon joylanishi bilan ro'yxat faollashadi", "Регион станет активным после первого объявления", "Becomes active once the first car is listed here"),

    # ---- tezkor bron ----
    "qb.own_car": ("Bu sizning mashinangiz", "Это ваш автомобиль", "This is your own car"),
    "qb.pick_dates": ("Kalendardan sanalarni tanlang", "Выберите даты в календаре", "Pick dates on the calendar"),
    "qb.check": ("Narx va so'rov", "Цена и заявка", "Price & request"),
    "qb.pick_hint": ("Avval olish, keyin qaytarish kunini bosing. Band kunlar tanlanmaydi.", "Сначала нажмите день получения, затем день возврата. Занятые дни недоступны.", "Tap the pick-up day, then the return day. Busy days can't be selected."),
    "qb.note_ph": ("Masalan: aeroportdan olib ketaman, soat 10:00", "Например: заберу в аэропорту в 10:00", "e.g. I'll pick it up at the airport at 10:00"),
    "qb.send": ("Bron so'rovini yuborish", "Отправить заявку", "Send booking request"),
    "qb.how": ("Owner 24 soat ichida tasdiqlaydi. Pul hozir yechilmaydi — tasdiqlangach onlayn yoki joyida to'laysiz.",
               "Владелец подтвердит в течение 24 часов. Деньги сейчас не списываются — оплата после подтверждения онлайн или на месте.",
               "The owner confirms within 24 hours. Nothing is charged now — pay online or on site after confirmation."),
    "qb.full_page": ("Rasmlar, shartlar va sharhlar", "Фото, условия и отзывы", "Photos, terms and reviews"),
    "qb.sent_t": ("So'rov yuborildi!", "Заявка отправлена!", "Request sent!"),
    "qb.sent_b": ("{car}: {a} — {b}. Owner javobini bildirishnoma orqali olasiz.", "{car}: {a} — {b}. Ответ владельца придёт уведомлением.", "{car}: {a} — {b}. You'll get the owner's reply as a notification."),
}

OVERRIDE5 = {
    "regions.title": ("Barcha hududlar", "Все регионы", "All regions"),
}
