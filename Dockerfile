FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Tashkent \
    APP_ENV=production \
    DATA_DIR=/data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY scripts ./scripts

# Xavfsizlik: ilova root bo'lmagan foydalanuvchi nomidan ishlaydi
RUN useradd --create-home appuser && mkdir -p /data && chown -R appuser /data
USER appuser
VOLUME ["/data"]
EXPOSE 8000

# SEED_DEMO=true bo'lsa, bo'sh bazani demo ma'lumotlar bilan to'ldiradi
CMD ["sh", "-c", "if [ \"$SEED_DEMO\" = \"true\" ]; then python -m scripts.seed; fi; uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
