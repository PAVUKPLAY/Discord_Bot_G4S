import os


def _env_id(name: str, *, required: bool = False):
    value = os.getenv(name, '').strip()
    if not value:
        if required:
            raise ValueError(f"Переменная окружения {name} не задана!")
        return None
    try:
        result = int(value)
    except ValueError as exc:
        raise ValueError(f"Переменная окружения {name} должна содержать числовой ID.") from exc
    if result <= 0:
        raise ValueError(f"Переменная окружения {name} должна быть положительным ID.")
    return result


# Bothost передаёт токен под DISCORD_BOT_TOKEN. DISCORD_TOKEN оставлен
# основным именем для совместимости с существующей конфигурацией.
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN') or os.getenv('DISCORD_BOT_TOKEN')
GUILD_ID = _env_id('GUILD_ID')

SERVER_IP = os.getenv('SERVER_IP', '80.242.59.106')
SERVER_PORT = int(os.getenv('SERVER_PORT', '2303'))
TARGET_CHANNEL_ID = _env_id('TARGET_CHANNEL_ID', required=True)
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

EVENT_CHANNEL_ID = _env_id('EVENT_CHANNEL_ID')
ANNOUNCE_CHANNEL_ID = _env_id('ANNOUNCE_CHANNEL_ID')
PING_EVERYONE = os.getenv('PING_EVERYONE', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}

WELCOME_CHANNEL_ID = _env_id('WELCOME_CHANNEL_ID')
ORGANIZATION_CHANNEL_ID = _env_id('ORGANIZATION_CHANNEL_ID')
GUEST_ROLE_ID = _env_id('GUEST_ROLE_ID')
FIGHTER_ROLE_ID = _env_id('FIGHTER_ROLE_ID')

MODERATOR_ROLE_IDS = []
for _role_id in os.getenv('MODERATOR_ROLE_IDS', '').split(','):
    if _role_id.strip():
        try:
            _parsed_role_id = int(_role_id.strip())
        except ValueError as exc:
            raise ValueError('MODERATOR_ROLE_IDS должен быть списком числовых ID через запятую.') from exc
        if _parsed_role_id <= 0:
            raise ValueError('Все ID в MODERATOR_ROLE_IDS должны быть положительными.')
        MODERATOR_ROLE_IDS.append(_parsed_role_id)

# === Логирование ===
LOG_CHANNEL_ID = _env_id('LOG_CHANNEL_ID')

# === Радио ===
RADIO_VOICE_CHANNEL_ID = _env_id('RADIO_VOICE_CHANNEL_ID')

RADIO_TEXT_CHANNEL_ID = _env_id('RADIO_TEXT_CHANNEL_ID')

RADIO_DEFAULT_STATION = os.getenv('RADIO_DEFAULT_STATION', 'Radio Record')
RADIO_DEFAULT_VOLUME = float(os.getenv('RADIO_DEFAULT_VOLUME', '0.5'))
if not 0 <= RADIO_DEFAULT_VOLUME <= 2:
    raise ValueError('RADIO_DEFAULT_VOLUME должен быть в диапазоне от 0 до 2.')

# === Казино ===
CASINO_CHANNEL_ID = _env_id('CASINO_CHANNEL_ID')

# === Активность ===
ACTIVITY_CHANNEL_ID = _env_id('ACTIVITY_CHANNEL_ID')

# === Проверки обязательных переменных ===
if not DISCORD_TOKEN:
    raise ValueError('Не задан DISCORD_TOKEN или DISCORD_BOT_TOKEN!')

ALLOWED_TAGS = ["leg", "nrf", "g4s"]
