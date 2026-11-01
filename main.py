import sys
import os

# ==================== ОЧИСТКА ЭКРАНА ПРИ СТАРТЕ ====================
# Отправляем ANSI-код очистки экрана и возврата курсора в начало
sys.stdout.write('\033[2J\033[H')
sys.stdout.flush()
# ==================================================================

import discord
from discord.ext import commands, tasks
import logging
import asyncio
import re
from config import DISCORD_TOKEN
from arma_monitor import update_status, cleanup_monitor
from ai_chat import on_ai_message, clear_history
import event_manager
from toggle_manager import get_status
from utils import has_moderator_role
import welcome_manager
from radio_manager import RadioManager, RadioControlView
import casino
import logging_manager
import activity_manager

# ==================== УМНЫЙ И ЧИСТЫЙ ФОРМАТТЕР ЛОГОВ ====================
class CleanEmojiFormatter(logging.Formatter):
    ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    EMOJI_CHECK = re.compile(r'^[\U0001F000-\U0001FFFF\u2600-\u27BF\u2190-\u21FF\u2300-\u23FF]')
    
    LEVEL_EMOJI = {
        logging.DEBUG: "🔍",
        logging.INFO: "✅",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🔥"
    }
    
    def format(self, record):
        message = self.ANSI_ESCAPE.sub('', record.getMessage())
        if not self.EMOJI_CHECK.match(message.strip()):
            emoji = self.LEVEL_EMOJI.get(record.levelno, "•")
            message = f"{emoji} {message}"
        timestamp = self.formatTime(record, self.datefmt)
        return f"[{timestamp}] {message}"

for logger_name in ['discord', 'discord.voice_state', 'discord.gateway', 'discord.client', 'discord.http', 'httpx', 'faster_whisper', 'edge_tts']:
    lg = logging.getLogger(logger_name)
    lg.handlers = []
    lg.propagate = True

handler = logging.StreamHandler()
handler.setFormatter(CleanEmojiFormatter(datefmt='%d.%m.%Y %H:%M'))

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
for h in root_logger.handlers[:]:
    root_logger.removeHandler(h)
root_logger.addHandler(handler)

logging.getLogger('discord').setLevel(logging.WARNING)
logging.getLogger('discord.voice_state').setLevel(logging.WARNING)
logging.getLogger('discord.gateway').setLevel(logging.WARNING)
logging.getLogger('discord.http').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('faster_whisper').setLevel(logging.WARNING)
logging.getLogger('edge_tts').setLevel(logging.WARNING)

logger = logging.getLogger("G4S")
# =======================================================================

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True
intents.voice_states = True
intents.moderation = True 

bot = commands.Bot(command_prefix='/', intents=intents)
bot.remove_command('help')

monitor_message = None
radio_manager = RadioManager()

async def setup_hook():
    try:
        await bot.load_extension("casino")
        logger.info("Модуль казино загружен.")
    except Exception as e:
        logger.error(f"Ошибка загрузки модуля казино: {e}")
        
    try:
        await bot.load_extension("activity_manager")
        logger.info("Модуль активности загружен.")
    except Exception as e:
        logger.error(f"Ошибка загрузки модуля активности: {e}")

bot.setup_hook = setup_hook

@bot.event
async def on_member_ban(guild, user):
    await logging_manager.on_member_ban(guild, user, bot)

@bot.event
async def on_member_remove(member):
    await logging_manager.on_member_remove(member, bot)

@bot.event
async def on_member_update(before, after):
    await logging_manager.on_member_update(before, after, bot)

@bot.event
async def on_voice_state_update(member, before, after):
    await logging_manager.on_voice_state_update(member, before, after, bot)

@bot.tree.command(name="help", description="Показать справку по боту")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛡️ Справка по боту G4S Сподручный",
        description="Вот что я умею:",
        color=discord.Color.blue()
    )
    embed.add_field(name="🤖 AI-чат", value="Напишите **`Ученый <вопрос>`** или упомяните меня. Очистка: **`/очистить`**.", inline=False)
    embed.add_field(name="🛡️ Мониторинг сервера Arma 3", value="Каждую минуту я обновляю информацию о сервере.", inline=False)
    embed.add_field(name="📻 Радио", value="В канале радио есть панель. Смена станции требует голосования.", inline=False)
    embed.add_field(name="🎰 Казино", value="Специальный канал с кнопками для игр.", inline=False)
    embed.add_field(name="📈 Активность", value="Канал со статистикой онлайна и сообщений.", inline=False)
    embed.add_field(name="📋 Заявки в отряд", value="При вступлении вы получите роль Гость и приветствие.", inline=False)
    embed.add_field(name="📅 События", value="Модераторы могут создавать смежки через кнопку.", inline=False)
    embed.set_footer(text="G4S Командование • v1.0 | Code by PAVUK")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="очистить", description="Очистить вашу историю диалога с AI")
async def slash_clear_history(interaction: discord.Interaction):
    success = await clear_history(interaction.user.id)
    if success:
        await interaction.response.send_message("🧹 Ваша история диалога с AI очищена.", ephemeral=True)
    else:
        await interaction.response.send_message("📭 У вас не было сохранённой истории.", ephemeral=True)

@bot.event
async def on_member_join(member):
    await welcome_manager.send_welcome_message(member)

@bot.event
async def on_ready():
    global monitor_message
    logger.info(f"Бот {bot.user.name} успешно запущен и готов к работе!")
    
    try:
        await bot.tree.sync()
        logger.info("Слеш-команды синхронизированы")
    except Exception as e:
        logger.error(f"Ошибка синхронизации слеш-команд: {e}")

    bot.add_listener(event_manager.on_reaction_add, 'on_reaction_add')
    bot.add_listener(event_manager.on_reaction_remove, 'on_reaction_remove')

    await event_manager.sync_events(bot)
    await cleanup_monitor(bot)
    monitor_message = await update_status(bot, None)
    await event_manager.cleanup_event_button(bot)
    await event_manager.setup_dashboard(bot, radio_manager)

    bot.add_view(RadioControlView(radio_manager))
    bot.loop.create_task(radio_manager.auto_start(bot))

    await casino.setup_casino_panel(bot)
    await activity_manager.setup_activity_panel(bot)

    if not update_status_task.is_running():
        update_status_task.start()
    bot.loop.create_task(event_manager.reminder_task(bot))

@tasks.loop(seconds=60)
async def update_status_task():
    global monitor_message
    monitor_message = await update_status(bot, monitor_message)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.content.startswith('/'):
        await bot.process_commands(message)
        return
    await on_ai_message(message, bot)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
