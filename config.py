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

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN не задан!")
if not TARGET_CHANNEL_ID:
    raise ValueError("TARGET_CHANNEL_ID не задан!")
if not EVENT_CHANNEL_ID:
    print("⚠️ EVENT_CHANNEL_ID не задан. Функция создания смежек отключена.")
if not ANNOUNCE_CHANNEL_ID:
    print("⚠️ ANNOUNCE_CHANNEL_ID не задан. Объявления о смежках не будут отправляться.")

TARGET_CHANNEL_ID = int(TARGET_CHANNEL_ID)
if EVENT_CHANNEL_ID:
    EVENT_CHANNEL_ID = int(EVENT_CHANNEL_ID)
if ANNOUNCE_CHANNEL_ID:
    ANNOUNCE_CHANNEL_ID = int(ANNOUNCE_CHANNEL_ID)

ALLOWED_TAGS = ["leg", "nrf", "g4s"]
