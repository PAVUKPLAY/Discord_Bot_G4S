import json
import os
import logging

logger = logging.getLogger(__name__)

# Берем путь из переменной окружения DATA_DIR или используем /app/data (постоянный том Bothost)
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

# Убедимся, что папка существует
os.makedirs(DATA_DIR, exist_ok=True)

def load_settings():
    logger.info(f"Загрузка настроек из {SETTINGS_FILE}")
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                logger.info(f"Настройки загружены: {data}")
                return data
            except Exception as e:
                logger.error(f"Ошибка загрузки настроек: {e}")
                return {}
    logger.warning(f"Файл {SETTINGS_FILE} не найден — используются значения по умолчанию")
    return {}

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno()) # Гарантируем запись на диск
        logger.info(f"Настройки сохранены: {settings}")
    except Exception as e:
        logger.error(f"Ошибка сохранения настроек: {e}")
        raise

settings = load_settings()

def get_status(feature: str, default: bool = True) -> bool:
    return settings.get(feature, default)

def set_status(feature: str, value: bool):
    settings[feature] = value
    save_settings(settings)
    logger.info(f"Функция {feature} {'включена' if value else 'выключена'}")
