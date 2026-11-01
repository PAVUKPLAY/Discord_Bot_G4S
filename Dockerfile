FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системный ffmpeg и libgomp1 (для faster-whisper)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY . .

# Создаём папку для данных
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data && chmod 777 /app/data

# Команда запуска
CMD ["python", "main.py"]
