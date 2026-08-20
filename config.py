import os

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SERVER_IP = os.getenv('SERVER_IP', '80.242.59.106')
SERVER_PORT = int(os.getenv('SERVER_PORT', '2303'))
TARGET_CHANNEL_ID = os.getenv('TARGET_CHANNEL_ID')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

EVENT_CHANNEL_ID = os.getenv('EVENT_CHANNEL_ID')
ANNOUNCE_CHANNEL_ID = os.getenv('ANNOUNCE_CHANNEL_ID')
PING_EVERYONE = os.getenv('PING_EVERYONE', 'True') == 'True'

# Новые переменные для приветствия и заявок
WELCOME_CHANNEL_ID = os.getenv('WELCOME_CHANNEL_ID')
ORGANIZATION_CHANNEL_ID = os.getenv('ORGANIZATION_CHANNEL_ID')
GUEST_ROLE_ID = os.getenv('GUEST_ROLE_ID')
FIGHTER_ROLE_ID = os.getenv('FIGHTER_ROLE_ID')

# Роли модераторов (через запятую)
MODERATOR_ROLE_IDS = [int(x) for x in os.getenv('MODERATOR_ROLE_IDS', '').split(',') if x.strip().isdigit()]

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN не задан!")
if not TARGET_CHANNEL_ID:
    raise ValueError("TARGET_CHANNEL_ID не задан!")

TARGET_CHANNEL_ID = int(TARGET_CHANNEL_ID)
if EVENT_CHANNEL_ID:
    EVENT_CHANNEL_ID = int(EVENT_CHANNEL_ID)
if ANNOUNCE_CHANNEL_ID:
    ANNOUNCE_CHANNEL_ID = int(ANNOUNCE_CHANNEL_ID)
if WELCOME_CHANNEL_ID:
    WELCOME_CHANNEL_ID = int(WELCOME_CHANNEL_ID)
if ORGANIZATION_CHANNEL_ID:
    ORGANIZATION_CHANNEL_ID = int(ORGANIZATION_CHANNEL_ID)
if GUEST_ROLE_ID:
    GUEST_ROLE_ID = int(GUEST_ROLE_ID)
if FIGHTER_ROLE_ID:
    FIGHTER_ROLE_ID = int(FIGHTER_ROLE_ID)

ALLOWED_TAGS = ["leg", "nrf", "g4s"]
