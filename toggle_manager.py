import json
import os
import logging

logger = logging.getLogger(__name__)

SETTINGS_FILE = "settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception as e:
                logger.error(f"Ошибка загрузки настроек: {e}")
                return {}
    return {}

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

settings = load_settings()

def get_status(feature: str, default: bool = True) -> bool:
    return settings.get(feature, default)

def set_status(feature: str, value: bool):
    settings[feature] = value
    save_settings(settings)
    logger.info(f"Функция {feature} {'включена' if value else 'выключена'}")
