import discord
from discord.ext import commands, tasks
import logging
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

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

# ==================== ЗАГРУЗКА РАСШИРЕНИЙ (ДО ЗАПУСКА) ====================
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

# ==================== ГЛОБАЛЬНЫЕ СЛУШАТЕЛИ (ЛОГИРОВАНИЕ) ====================
# Переписываем лямбды на асинхронные обертки
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

# ==================== СЛЕШ-КОМАНДЫ ====================

@bot.tree.command(name="help", description="Показать справку по боту")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛡️ Справка по боту G4S Сподручный",
        description="Вот что я умею:",
        color=discord.Color.blue()
    )
    embed.add_field(name="🤖 AI-чат", value="Напишите **`Ученый <вопрос>`** или упомяните меня. Очистка: **`/очистить`**.", inline=False)
    embed.add_field(name="🛡️ Мониторинг сервера Arma 3", value="Каждую минуту я обновляю информацию о сервере в канале мониторинга.", inline=False)
    embed.add_field(name="📻 Радио", value="В канале радио есть панель. Смена станции требует голосования.", inline=False)
    embed.add_field(name="🎰 Казино", value="Специальный канал с кнопками для игр.", inline=False)
    embed.add_field(name="📈 Активность", value="Канал со статистикой онлайна и сообщений.", inline=False)
    embed.add_field(name="📋 Заявки в отряд", value="При вступлении на сервер вы получите роль Гость и приветствие.", inline=False)
    embed.add_field(name="📅 События", value="Модераторы могут создавать смежки через кнопку в канале событий.", inline=False)
    embed.set_footer(text="G4S Командование • v1.0 | Code by PAVUK")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="очистить", description="Очистить вашу историю диалога с AI")
async def slash_clear_history(interaction: discord.Interaction):
    success = await clear_history(interaction.user.id)
    if success:
        await interaction.response.send_message("🧹 Ваша история диалога с AI очищена.", ephemeral=True)
    else:
        await interaction.response.send_message("📭 У вас не было сохранённой истории.", ephemeral=True)

# ==================== СОБЫТИЯ И ЗАДАЧИ ====================

@bot.event
async def on_member_join(member):
    await welcome_manager.send_welcome_message(member)

@bot.event
async def on_ready():
    global monitor_message
    logger.info(f'Бот {bot.user.name} успешно запущен и готов к работе!')
    
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
