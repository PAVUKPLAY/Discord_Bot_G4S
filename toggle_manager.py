import json
import os
import logging
import tempfile

logger = logging.getLogger(__name__)

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

os.makedirs(DATA_DIR, exist_ok=True)

def load_settings():
    logger.info(f"Загрузка настроек из {SETTINGS_FILE}")
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Ожидался объект настроек.")
            logger.info("Настройки загружены.")
            return data
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.error(f"Ошибка загрузки настроек: {e}")
            return {}
    logger.warning(f"Файл {SETTINGS_FILE} не найден — используются значения по умолчанию")
    return {}

def save_settings(settings):
    os.makedirs(DATA_DIR, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="settings_", suffix=".tmp", dir=DATA_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, SETTINGS_FILE)
        logger.info(f"Настройки сохранены: {settings}")
    except Exception as e:
        logger.error(f"Ошибка сохранения настроек: {e}")
        raise
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

settings = load_settings()

def get_status(feature: str, default: bool = True) -> bool:
    return settings.get(feature, default)

def set_status(feature: str, value: bool):
    settings[feature] = value
    save_settings(settings)
    logger.info(f"Функция {feature} {'включена' if value else 'выключена'}")
