import os

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SERVER_IP = os.getenv('SERVER_IP', '80.242.59.106')
SERVER_PORT = int(os.getenv('SERVER_PORT', '2303'))
TARGET_CHANNEL_ID = os.getenv('TARGET_CHANNEL_ID')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

if not DISCORD_TOKEN:
    raise ValueError("Переменная окружения DISCORD_TOKEN не задана!")
if not TARGET_CHANNEL_ID:
    raise ValueError("Переменная окружения TARGET_CHANNEL_ID не задана!")
if not DEEPSEEK_API_KEY:
    print("⚠️ Внимание: DEEPSEEK_API_KEY не задан. AI-функции будут недоступны.")

TARGET_CHANNEL_ID = int(TARGET_CHANNEL_ID)
ALLOWED_TAGS = ["leg", "nrf", "g4s"]