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
