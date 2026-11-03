"""Server xabarlarini uch tilga o'girish (uz — asosiy, ru, en).

Til so'rovdagi `lang` cookie'sidan (frontend til almashtirgichi o'rnatadi), bo'lmasa Accept-Language'dan olinadi.
Xabarlar o'zbekcha shablon bilan yoziladi: tr("Kamida {n} ta belgi", n=12).
"""
import re
from contextvars import ContextVar

LANGS = ("uz", "ru", "en")
current_lang: ContextVar[str] = ContextVar("current_lang", default="uz")


def detect_lang(cookie_header: str, accept_language: str) -> str:
    for part in (cookie_header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == "lang" and v in LANGS:
            return v
    al = (accept_language or "").lower()
    for code in ("uz", "ru", "en"):
        if al.startswith(code):
            return code
    return "uz"


def uz_typo(s: str) -> str:
    """O'zbek lotin imlosi: oʻ, gʻ (U+02BB) va tutuq belgisi ʼ (U+02BC)."""
    s = re.sub(r"([OoGg])'", lambda m: m.group(1) + "\u02bb", s)
    return re.sub(r"(?<=[A-Za-z\u02bb])'(?=[A-Za-z])", "\u02bc", s)


def tr(msg: str, **kw) -> str:
    lang = current_lang.get()
    if lang == "uz":
        msg = uz_typo(msg)
    else:
        pair = CATALOG.get(msg)
        if pair:
            msg = pair[0] if lang == "ru" else pair[1]
    return msg.format(**kw) if kw else msg


# o'zbekcha shablon -> (ruscha, inglizcha)
CATALOG: dict[str, tuple[str, str]] = {
    # umumiy
    "Avval tizimga kiring": ("Сначала войдите в систему", "Please sign in first"),
    "Bu amal uchun huquqingiz yo'q": ("У вас нет прав на это действие", "You don't have permission for this action"),
    "CSRF tekshiruvidan o'tmadi": ("Проверка CSRF не пройдена", "CSRF check failed"),
    "API manzili topilmadi": ("Адрес API не найден", "API endpoint not found"),
    "Serverda kutilmagan xato yuz berdi": ("На сервере произошла непредвиденная ошибка", "An unexpected server error occurred"),
    "So'rov tanasi JSON formatida bo'lishi kerak": ("Тело запроса должно быть в формате JSON", "Request body must be JSON"),
    "So'rov tanasi obyekt bo'lishi kerak": ("Тело запроса должно быть объектом", "Request body must be an object"),
    "'{name}' parametri son bo'lishi kerak": ("Параметр '{name}' должен быть числом", "Parameter '{name}' must be a number"),
    "'{name}' sana formati YYYY-MM-DD bo'lishi kerak": ("Дата '{name}' должна быть в формате ГГГГ-ММ-ДД", "Date '{name}' must be YYYY-MM-DD"),
    "Ma'lumotlar noto'g'ri": ("Неверные данные", "Invalid data"),
    # validatsiya
    "Majburiy maydon": ("Обязательное поле", "Required field"),
    "Kamida {n} ta belgi bo'lishi kerak": ("Должно быть не менее {n} символов", "Must be at least {n} characters"),
    "Ko'pi bilan {n} ta belgi bo'lishi mumkin": ("Не более {n} символов", "At most {n} characters"),
    "Qiymat {n} dan kichik bo'lmasligi kerak": ("Значение должно быть не меньше {n}", "Value must be at least {n}"),
    "Qiymat {n} dan katta bo'lmasligi kerak": ("Значение должно быть не больше {n}", "Value must be at most {n}"),
    "Ruxsat etilgan qiymatlardan birini tanlang": ("Выберите одно из допустимых значений", "Choose one of the allowed values"),
    "Son kiritilishi kerak": ("Введите число", "Enter a number"),
    "Sana noto'g'ri (YYYY-MM-DD)": ("Неверная дата (ГГГГ-ММ-ДД)", "Invalid date (YYYY-MM-DD)"),
    "Ortiqcha maydon": ("Лишнее поле", "Unexpected field"),
    "Qiymat noto'g'ri": ("Неверное значение", "Invalid value"),
    "Email manzil noto'g'ri": ("Неверный адрес email", "Invalid email address"),
    "Telefon raqam noto'g'ri": ("Неверный номер телефона", "Invalid phone number"),
    "Parol juda keng tarqalgan — boshqasini tanlang": ("Пароль слишком распространён — выберите другой", "This password is too common — choose another"),
    "Parol email manzilingizni o'z ichiga olmasligi kerak": ("Пароль не должен содержать ваш email", "Password must not contain your email"),
    "Foydalanish shartlariga rozilik majburiy": ("Необходимо согласие с условиями использования", "You must accept the terms of use"),
    "Noma'lum qulaylik: {key}": ("Неизвестное удобство: {key}", "Unknown feature: {key}"),
    "Maksimal muddat minimaldan kam bo'lmasligi kerak": ("Максимальный срок не может быть меньше минимального", "Maximum period cannot be less than minimum"),
    # auth
    "Bu email bilan allaqachon ro'yxatdan o'tilgan": ("Этот email уже зарегистрирован", "This email is already registered"),
    "Juda ko'p urinish. 5 daqiqadan so'ng qayta urinib ko'ring": ("Слишком много попыток. Повторите через 5 минут", "Too many attempts. Try again in 5 minutes"),
    "Email yoki parol noto'g'ri": ("Неверный email или пароль", "Invalid email or password"),
    "Hisobingiz administrator tomonidan bloklangan": ("Ваш аккаунт заблокирован администратором", "Your account has been blocked by an administrator"),
    "Eski parol noto'g'ri": ("Старый пароль неверен", "Current password is incorrect"),
    # e'lonlar
    "E'lon topilmadi": ("Объявление не найдено", "Listing not found"),
    "Bu e'lon sizga tegishli emas": ("Это объявление вам не принадлежит", "This listing doesn't belong to you"),
    "Tugash sanasi boshlanish sanasidan oldin bo'lmasligi kerak": ("Дата окончания не может быть раньше даты начала", "End date cannot be before start date"),
    "Bu avtomobilda tasdiqlangan kelgusi bronlar bor. Avval ularni yakunlang yoki e'lonni vaqtincha yashiring": ("У этого автомобиля есть подтверждённые будущие брони. Завершите их или временно скройте объявление", "This car has confirmed upcoming bookings. Complete them first or temporarily hide the listing"),
    "Rasm tanlanmagan": ("Изображение не выбрано", "No image selected"),
    "Bitta e'longa ko'pi bilan {n} ta rasm yuklash mumkin": ("К одному объявлению можно загрузить не более {n} фото", "You can upload at most {n} photos per listing"),
    "Har bir rasm {n} MB dan oshmasligi kerak": ("Каждое фото должно быть не больше {n} МБ", "Each photo must be at most {n} MB"),
    "Faqat JPG, PNG yoki WEBP rasm yuklash mumkin": ("Можно загружать только JPG, PNG или WEBP", "Only JPG, PNG or WEBP images are allowed"),
    "Rasm topilmadi": ("Изображение не найдено", "Image not found"),
    # bron
    "O'tib ketgan sanani bron qilib bo'lmaydi": ("Нельзя бронировать прошедшую дату", "You can't book a past date"),
    "Bu avtomobil uchun ijara muddati {min}–{max} kun": ("Срок аренды этого автомобиля {min}–{max} дней", "Rental period for this car is {min}–{max} days"),
    "Avtomobil topilmadi yoki hozir ijaraga berilmaydi": ("Автомобиль не найден или сейчас не сдаётся", "Car not found or not available for rent right now"),
    "O'z avtomobilingizni bron qila olmaysiz": ("Нельзя забронировать собственный автомобиль", "You can't book your own car"),
    "Tanlangan sanalarda avtomobil band. Kalendardan bo'sh kunlarni tanlang": ("На выбранные даты автомобиль занят. Выберите свободные дни в календаре", "The car is booked on these dates. Pick free days in the calendar"),
    "Bu sanalar uchun sizda allaqachon kutilayotgan so'rov bor": ("У вас уже есть ожидающий запрос на эти даты", "You already have a pending request for these dates"),
    "Bir vaqtda ko'pi bilan {n} ta kutilayotgan so'rov yuborish mumkin": ("Одновременно можно иметь не более {n} ожидающих запросов", "You can have at most {n} pending requests at a time"),
    "Bu avtomobilda yetkazib berish xizmati yo'q": ("У этого автомобиля нет доставки", "This car has no delivery service"),
    "Bron topilmadi": ("Бронь не найдена", "Booking not found"),
    "Bu bron sizning avtomobilingizga tegishli emas": ("Эта бронь не относится к вашему автомобилю", "This booking is not for your car"),
    "Faqat kutilayotgan bronni tasdiqlash mumkin": ("Подтвердить можно только ожидающую бронь", "Only pending bookings can be confirmed"),
    "Boshlanish sanasi o'tib ketgan. So'rovni rad eting": ("Дата начала прошла. Отклоните запрос", "The start date has passed. Reject the request"),
    "Bu sanalarda boshqa tasdiqlangan bron bor": ("На эти даты уже есть другая подтверждённая бронь", "Another confirmed booking exists for these dates"),
    "Faqat kutilayotgan bronni rad etish mumkin": ("Отклонить можно только ожидающую бронь", "Only pending bookings can be rejected"),
    "Bu bron sizga tegishli emas": ("Эта бронь вам не принадлежит", "This booking doesn't belong to you"),
    "Bu bronni bekor qilib bo'lmaydi": ("Эту бронь нельзя отменить", "This booking can't be cancelled"),
    "Ijara boshlangan — bekor qilish uchun egasi bilan bog'laning": ("Аренда началась — для отмены свяжитесь с владельцем", "The rental has started — contact the owner to cancel"),
    # sharh, xabar
    "Sharhni faqat ijara yakunlangandan keyin qoldirish mumkin": ("Отзыв можно оставить только после завершения аренды", "You can review only after the rental is completed"),
    "Bu ijara uchun sharh allaqachon qoldirilgan": ("Отзыв на эту аренду уже оставлен", "A review for this rental already exists"),
    "Sharh topilmadi": ("Отзыв не найден", "Review not found"),
    "Faqat avtomobil egasi javob bera oladi": ("Ответить может только владелец автомобиля", "Only the car owner can reply"),
    "O'zingizga xabar yubora olmaysiz": ("Нельзя отправить сообщение самому себе", "You can't message yourself"),
    "Qabul qiluvchi topilmadi": ("Получатель не найден", "Recipient not found"),
    "Foydalanuvchi topilmadi": ("Пользователь не найден", "User not found"),
    "Juda ko'p xabar. Biroz kuting": ("Слишком много сообщений. Подождите немного", "Too many messages. Please wait a moment"),
    # admin
    "O'zingizni bloklay olmaysiz": ("Нельзя заблокировать самого себя", "You can't block yourself"),
    "Boshqa administratorni bloklab bo'lmaydi": ("Нельзя заблокировать другого администратора", "You can't block another administrator"),
    "Komissiya 0% dan 30% gacha bo'lishi kerak": ("Комиссия должна быть от 0% до 30%", "Commission must be between 0% and 30%"),
    # akkaunt, kodlar
    "Bu telefon raqam bilan allaqachon ro'yxatdan o'tilgan": ("Этот номер телефона уже зарегистрирован", "This phone number is already registered"),
    "Login yoki parol noto'g'ri": ("Неверный логин или пароль", "Invalid login or password"),
    "Parol noto'g'ri": ("Неверный пароль", "Incorrect password"),
    "Kodni qayta yuborish uchun {n} soniya kuting": ("Повторно отправить код можно через {n} сек.", "Wait {n} seconds before requesting a new code"),
    "Bugun juda ko'p kod so'raldi. Ertaga qayta urinib ko'ring": ("Сегодня запрошено слишком много кодов. Попробуйте завтра", "Too many codes requested today. Try again tomorrow"),
    "Kod noto'g'ri yoki muddati tugagan. Yangi kod so'rang": ("Код неверный или истёк. Запросите новый", "The code is invalid or expired. Request a new one"),
    "Kod noto'g'ri. Qolgan urinishlar: {n}": ("Неверный код. Осталось попыток: {n}", "Wrong code. Attempts left: {n}"),
    "Kod 6 ta raqamdan iborat bo'lishi kerak": ("Код должен состоять из 6 цифр", "The code must be 6 digits"),
    "Agar bunday akkaunt mavjud bo'lsa, tasdiqlash kodi yuborildi": ("Если такой аккаунт существует, код подтверждения отправлен", "If such an account exists, a confirmation code has been sent"),
    "Parolni tiklash xizmati hozircha sozlanmagan. Administratorga murojaat qiling": ("Восстановление пароля пока не настроено. Обратитесь к администратору", "Password recovery isn't configured yet. Please contact an administrator"),
    "Bu kanal orqali yuborish hozircha sozlanmagan": ("Отправка через этот канал пока не настроена", "Sending through this channel isn't configured yet"),
    "Faol bronlaringiz bor. Avval ularni yakunlang yoki bekor qiling": ("У вас есть активные брони. Сначала завершите или отмените их", "You have active bookings. Complete or cancel them first"),
    "So'rov hajmi juda katta": ("Слишком большой запрос", "Request is too large"),
    # to'lovlar
    "Bu to'lov usuli hozircha ulanmagan": ("Этот способ оплаты пока не подключён", "This payment method isn't connected yet"),
    "To'lov faqat owner tasdiqlagan bron uchun mumkin": ("Оплатить можно только бронь, подтверждённую владельцем", "You can pay only for a booking confirmed by the owner"),
    "Bu bron allaqachon to'langan": ("Эта бронь уже оплачена", "This booking is already paid"),
    "Bu bron uchun to'lov muddati o'tgan": ("Срок оплаты этой брони истёк", "The payment period for this booking has passed"),
    "To'lov topilmadi": ("Платёж не найден", "Payment not found"),
    "Bu to'lovni yakunlab bo'lmaydi": ("Этот платёж нельзя завершить", "This payment can't be completed"),
    "Bu to'lov qaytarish kutilayotgan holatda emas": ("Этот платёж не ожидает возврата", "This payment isn't awaiting a refund"),
    "Summa owner balansidan katta": ("Сумма превышает баланс владельца", "Amount exceeds the owner's balance"),
    # band kunlar, shikoyatlar
    "Bu sanalarda tasdiqlangan bron bor — ularni yopib bo'lmaydi": ("На эти даты есть подтверждённая бронь — закрыть их нельзя", "These dates have a confirmed booking and can't be blocked"),
    "Shikoyat obyekti topilmadi": ("Объект жалобы не найден", "Report target not found"),
    "Siz bu haqda allaqachon shikoyat yuborgansiz": ("Вы уже отправили жалобу на это", "You've already reported this"),
}


# ---- v3: bekor qilish siyosati, pul yechish so'rovlari, maslahatchi, hisobotlar ----
CATALOG.update({
    "Karta raqamining oxirgi 4 raqamini kiriting": ("Введите последние 4 цифры карты", "Enter the last 4 digits of the card"),
    "Ikkala sanani ham tanlang yoki ikkalasini ham bo'sh qoldiring": ("Выберите обе даты или оставьте обе пустыми", "Pick both dates or leave both empty"),
    "Noma'lum qulaylik": ("Неизвестная опция", "Unknown feature"),
    "Bron topilmadi": ("Бронь не найдена", "Booking not found"),
    "Bu bron sizga tegishli emas": ("Эта бронь вам не принадлежит", "This booking isn't yours"),
    "Summa mavjud balansdan katta: {n}": ("Сумма больше доступного баланса: {n}", "Amount exceeds the available balance: {n}"),
    "Sizda ko'rib chiqilayotgan so'rov bor. Avval u yakunlansin": ("У вас уже есть заявка на рассмотрении. Дождитесь её решения", "You already have a request under review. Please wait for it to be processed"),
    "So'rov topilmadi": ("Заявка не найдена", "Request not found"),
    "Bu so'rov allaqachon ko'rib chiqilgan": ("Эта заявка уже обработана", "This request has already been processed"),
    "Rad etish sababini yozing": ("Укажите причину отказа", "Please give a reason for rejecting"),
    "Davr 366 kundan oshmasligi kerak": ("Период не должен превышать 366 дней", "The period can't exceed 366 days"),
    "Hisobot turi noto'g'ri": ("Неверный тип отчёта", "Invalid report type"),
    "Filtr qiymati noto'g'ri": ("Неверное значение фильтра", "Invalid filter value"),
    "Administrator akkauntiga bu amalni qo'llab bo'lmaydi": ("Это действие нельзя применить к администратору", "This action can't be applied to an administrator"),
    "Sababini yozing (kamida 3 belgi)": ("Укажите причину (минимум 3 символа)", "Write a reason (at least 3 characters)"),
})

CATALOG.update({  # CSV ustunlari va holatlar
    "Bron №": ("Бронь №", "Booking #"), "Boshlanish": ("Начало", "Start"), "Tugash": ("Окончание", "End"), "Kunlar": ("Дней", "Days"),
    "Avtomobil": ("Автомобиль", "Car"), "Shahar": ("Город", "City"), "Holat": ("Статус", "Status"), "To'lov": ("Оплата", "Payment"),
    "Kunlik narx": ("Цена в день", "Daily price"), "Yetkazib berish": ("Доставка", "Delivery"), "Jami": ("Итого", "Total"),
    "Qaytarilgan": ("Возвращено", "Refunded"), "Komissiya": ("Комиссия", "Commission"), "Owner ulushi": ("Доля владельца", "Owner share"),
    "Ijarachi": ("Арендатор", "Renter"), "Owner": ("Владелец", "Owner"),
    "Kutilmoqda": ("Ожидает", "Pending"), "Tasdiqlangan": ("Подтверждена", "Approved"), "Yakunlangan": ("Завершена", "Completed"),
    "Rad etilgan": ("Отклонена", "Rejected"), "Bekor qilingan": ("Отменена", "Cancelled"), "Joyida": ("На месте", "On site"),
    "Onlayn to'langan": ("Оплачено онлайн", "Paid online"), "Qaytarish kutilmoqda": ("Ожидает возврата", "Refund pending"),
})

CATALOG.update({  # v4: komissiya qarzi
    "Summa komissiya qarzidan katta": ("Сумма больше долга по комиссии", "Amount exceeds the fee owed"),
    "Komissiya qarzi hisobidan": ("В счёт долга по комиссии", "Against the commission owed"),
})

CATALOG.update({  # v4: hududlar
    "Viloyatni tanlang": ("Выберите область", "Choose a region"),
    "Viloyat ro'yxatda yo'q": ("Такой области нет в списке", "This region isn't in the list"),
    "Tuman yoki shaharni tanlang": ("Выберите район или город", "Choose a district or city"),
    "Bu tuman tanlangan viloyatga tegishli emas": ("Этот район не относится к выбранной области", "This district doesn't belong to the selected region"),
})

CATALOG.update({  # v4: nizolar va kanallar
    "Nizo topilmadi": ("Спор не найден", "Dispute not found"),
    "Bu bron bo'yicha nizo ochib bo'lmaydi": ("По этой брони нельзя открыть спор", "A dispute can't be opened for this booking"),
    "Nizo ijara tugaganidan keyin {n} kun ichida ochiladi": ("Спор можно открыть в течение {n} дней после окончания аренды", "A dispute can be opened within {n} days after the rental ends"),
    "Bu bron bo'yicha ochiq nizo bor": ("По этой брони уже есть открытый спор", "This booking already has an open dispute"),
    "Javobni faqat ikkinchi tomon yozadi": ("Ответ пишет только вторая сторона", "Only the other party can reply"),
    "Nizo yopilgan": ("Спор закрыт", "The dispute is closed"),
    "Nizoni faqat uni ochgan foydalanuvchi qaytarib oladi": ("Отозвать спор может только тот, кто его открыл", "Only the person who opened the dispute can withdraw it"),
    "Nizo allaqachon ko'rib chiqilmoqda yoki yopilgan": ("Спор уже рассматривается или закрыт", "The dispute is already in review or closed"),
    "Faqat nizo ishtirokchisini bloklash mumkin": ("Заблокировать можно только участника спора", "Only a party to the dispute can be blocked"),
    "Kanal sozlanmagan": ("Канал не настроен", "Channel isn't configured"),
})

CATALOG.update({  # v5: parol qoidalari
    "Parol kamida {n} ta belgidan iborat bo'lsin": ("Пароль должен содержать не менее {n} символов", "Password must be at least {n} characters"),
    "Kamida bitta katta harf (A–Z) bo'lsin": ("Нужна хотя бы одна заглавная буква (A–Z)", "Add at least one uppercase letter (A–Z)"),
    "Kamida bitta kichik harf (a–z) bo'lsin": ("Нужна хотя бы одна строчная буква (a–z)", "Add at least one lowercase letter (a–z)"),
    "Kamida bitta raqam (0–9) bo'lsin": ("Нужна хотя бы одна цифра (0–9)", "Add at least one digit (0–9)"),
    "Kamida bitta belgi (! @ # - _ . kabi) bo'lsin": ("Нужен хотя бы один символ (! @ # - _ .)", "Add at least one symbol (! @ # - _ .)"),
    "Kamida bitta administrator qolishi kerak": ("Должен остаться хотя бы один администратор", "At least one administrator must remain"),
    "Dalolatnoma allaqachon tasdiqlangan": ("Акт уже подтверждён", "The handover record is already confirmed"),
    "Bu karta allaqachon qo'shilgan": ("Эта карта уже добавлена", "This card is already added"),
    "Topshirish dalolatnomasini ijara boshlanishiga 1 kun qolganda to'ldirish mumkin": ("Акт передачи можно заполнить за 1 день до начала аренды", "The pick-up record can be filled from 1 day before the rental"),
    "Dalolatnoma faqat tasdiqlangan bron uchun to'ldiriladi": ("Акт заполняется только для подтверждённой брони", "Handover records are only for approved bookings"),
    "Email xizmati sozlanmagan. Administratorga murojaat qiling": ("Email не настроен. Обратитесь к администратору", "Email isn't configured. Contact an administrator"),
    "Shartnoma shartlariga roziligingizni belgilang": ("Отметьте согласие с условиями договора", "Tick that you agree to the contract terms"),
    "O'zingizni o'chira olmaysiz": ("Нельзя удалить самого себя", "You can't delete yourself"),
    "Hujjat turi noto'g'ri": ("Неверный тип документа", "Invalid document type"),
    "Dalolatnoma topilmadi": ("Акт не найден", "Handover record not found"),
    "Bu shartnomani hozir imzolab bo'lmaydi": ("Этот договор сейчас нельзя подписать", "This contract can't be signed now"),
    "Avval ikkala tomon shartnomani imzolashi kerak": ("Сначала договор должны подписать обе стороны", "Both parties must sign the contract first"),
    "Davlat raqamini 01A123BC yoki 01123ABC ko'rinishida yozing": ("Укажите госномер в виде 01A123BC или 01123ABC", "Enter the plate as 01A123BC or 01123ABC"),
    "Qaytarishdagi probeg olishdagidan kam bo'lishi mumkin emas": ("Пробег при возврате не может быть меньше, чем при получении", "Return mileage can't be lower than at pick-up"),
    "Bu dalolatnoma allaqachon to'ldirilgan": ("Этот акт уже заполнен", "This handover record is already filled in"),
    "Hujjat topilmadi": ("Документ не найден", "Document not found"),
    "Shartnoma bron tasdiqlangandan keyin tuziladi": ("Договор составляется после подтверждения брони", "The contract is created once the booking is approved"),
    "Shablonda majburiy maydon yo'q: {f}": ("В шаблоне нет обязательного поля: {f}", "The template is missing a required field: {f}"),
    "Pasport yoki ID karta seriya va raqamini kiriting": ("Укажите серию и номер паспорта или ID-карты", "Enter the passport or ID card series and number"),
    "O'z huquqingizni o'zgartira olmaysiz": ("Нельзя менять собственные права", "You can't change your own role"),
    "Hujjatning amal qilish muddati tugagan": ("Срок действия документа истёк", "The document has expired"),
    "Sana noto'g'ri": ("Неверная дата", "Invalid date"),
    "E'tirozingizni yozing (kamida 5 belgi)": ("Опишите возражение (минимум 5 символов)", "Describe your objection (at least 5 characters)"),
    "Karta topilmadi": ("Карта не найдена", "Card not found"),
    "Guvohnoma raqami, toifasi va amal qilish muddatini kiriting": ("Укажите номер, категории и срок действия прав", "Enter the licence number, categories and expiry date"),
    "Fayl topilmadi": ("Файл не найден", "File not found"),
    "Karta raqami noto'g'ri": ("Неверный номер карты", "Invalid card number"),
    "Avval mashinani topshirish dalolatnomasi to'ldirilishi kerak": ("Сначала нужно заполнить акт передачи машины", "The pick-up record must be filled in first"),
    "Probeg va yoqilg'i darajasini kiriting": ("Укажите пробег и уровень топлива", "Enter the mileage and fuel level"),
    "Ko'pi bilan 5 ta karta qo'shish mumkin": ("Можно добавить не более 5 карт", "You can add up to 5 cards"),
    "Shartnoma topilmadi": ("Договор не найден", "Contract not found"),
    "Shikastni izohda yozing: qayerda va qanday": ("Опишите повреждение: где и какое", "Describe the damage: where and what"),
    "Bu mashinani faqat hujjatlari (haydovchilik guvohnomasi va pasport/ID) tasdiqlangan foydalanuvchi ijaraga ola oladi. Sozlamalar → Hujjatlar bo'limida yuklang": ("Эту машину могут арендовать только пользователи с подтверждёнными документами (права и паспорт/ID). Загрузите их в Настройки → Документы", "Only users with verified documents (driving licence and passport/ID) can rent this car. Upload them in Settings → Documents"),
    "Kartaning amal qilish muddati tugagan yoki noto'g'ri": ("Срок действия карты истёк или указан неверно", "The card has expired or the date is invalid"),
    "Dalolatnomani ikkinchi tomon tasdiqlaydi": ("Акт подтверждает другая сторона", "The other party confirms the record"),
    "Foydalanuvchining faol bronlari bor. Avval ularni bekor qiling": ("У пользователя есть активные брони. Сначала отмените их", "The user has active bookings. Cancel them first"),
    "Amal qilish muddatini OO/YY ko'rinishida yozing": ("Укажите срок действия как ММ/ГГ", "Enter the expiry as MM/YY"),
    "Kamida 4 ta rasm yuklang: old, orqa, ikki yon tomon (salon va probeg ham tavsiya etiladi)": ("Загрузите минимум 4 фото: спереди, сзади и с двух сторон (желательно также салон и пробег)", "Upload at least 4 photos: front, back and both sides (interior and odometer recommended)"),
    "Shartnoma matni o'zgartirilgan — tasdiqlab bo'lmaydi": ("Текст договора изменён — подтвердить нельзя", "The contract text was altered — it can't be approved"),
    "Bloklangan foydalanuvchini admin qilib bo'lmaydi": ("Заблокированного пользователя нельзя сделать админом", "A blocked user can't be made an admin"),
    "Joylashuv aniqlanmadi": ("Местоположение не определено", "Location not detected"),
})

# v8: bron oldidan profil tayyorligi, admin foydalanuvchini boshqaradi
CATALOG.update({
    "Bron qilishdan oldin profilingizni to'ldiring: {what}": ("Перед бронированием заполните профиль: {what}", "Complete your profile before booking: {what}"),
    "ism va familiya": ("имя и фамилия", "full name"),
    "telefon raqami": ("номер телефона", "phone number"),
    "email yoki telefonni tasdiqlash": ("подтверждение email или телефона", "email or phone verification"),
    "hujjatlar": ("документы", "documents"),
})
