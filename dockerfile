FROM python:3.10-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование файлов бота
COPY bot.py .
COPY config.py .
COPY data.json .
COPY users_db.json .

# Создание папки для фото
RUN mkdir -p photos

# Создание папки для логов
RUN mkdir -p logs

# Переменные окружения (опционально)
ENV PYTHONUNBUFFERED=1

# Запуск бота
CMD ["python", "bot.py"]
