FROM python:3.11-slim

WORKDIR /app

# 1. Устанавливаем системный ffmpeg и libgomp1 (для faster-whisper)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 2. Устанавливаем Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Принудительно обновляем edge-tts до последней версии (важно!)
RUN pip install --no-cache-dir --upgrade edge-tts

# 4. Копируем код бота
COPY . .

# 5. Создаём папку для данных
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data && chmod 777 /app/data

# 6. Команда запуска
CMD ["python", "main.py"]
