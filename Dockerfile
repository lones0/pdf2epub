FROM python:3.11-slim

# Calibre'i ve ebook-convert için gereken bağımlılıkları kur
RUN apt-get update && apt-get install -y --no-install-recommends \
    calibre \
    xz-utils \
    libegl1 \
    libopengl0 \
    libxcomposite1 \
    libxkbcommon0 \
    libnss3 \
    libxdamage1 \
    libxrandr2 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV QT_QPA_PLATFORM=offscreen

EXPOSE 5000
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --timeout 300 app:app"]
