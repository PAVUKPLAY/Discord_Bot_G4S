FROM python:3.11-slim

WORKDIR /app

# 1. Устанавливаем системный ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 2. Устанавливаем Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Копируем код бота
COPY . .

# 4. Создаём папку для данных (если используется)
RUN mkdir -p /app/data && chmod 777 /app/data

# 5. Команда запуска
CMD ["python", "main.py"]
