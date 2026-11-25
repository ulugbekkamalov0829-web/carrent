FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Tashkent \
    APP_ENV=production \
    DATA_DIR=/data

WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Loyiha tuzilishi: backend/ (Python server) va frontend/ (sahifalar, JS, CSS, rasmlar)
COPY backend/app ./backend/app
COPY backend/scripts ./backend/scripts
COPY frontend ./frontend
WORKDIR /app/backend

# Xavfsizlik: ilova root bo'lmagan foydalanuvchi nomidan ishlaydi
RUN useradd --create-home appuser && mkdir -p /data && chown -R appuser /data
USER appuser
VOLUME ["/data"]
EXPOSE 8000

# Baza Supabase'dan tiklanadi (sozlangan bo'lsa); SEED_DEMO=true va baza bo'sh bo'lsa — namuna ma'lumotlar (backend/app/main.py)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
