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

bot = commands.Bot(command_prefix='/', intents=intents)
bot.remove_command('help')

monitor_message = None
radio_manager = RadioManager()

# ==================== СЛЕШ-КОМАНДЫ ====================

@bot.tree.command(name="help", description="Показать справку по боту")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛡️ Справка по боту G4S Сподручный",
        description="Вот что я умею:",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="🤖 AI-чат",
        value=(
            "Напишите **`Ученый <вопрос>`** или **`Учёный <вопрос>`**, или просто упомяните меня, чтобы задать вопрос.\n"
            "Для очистки истории диалога используйте **`/очистить`**.\n"
            "Управление включением/выключением AI – через панель управления в канале событий."
        ),
        inline=False
    )
    embed.add_field(
        name="🛡️ Мониторинг сервера Arma 3",
        value="Каждую минуту я обновляю информацию о сервере в специальном канале.\nУправление через панель управления.",
        inline=False
    )
    embed.add_field(
        name="📻 Радио",
        value="Бот автоматически заходит в голосовой канал и играет станцию по умолчанию.\n"
              "В текстовом канале есть панель с кнопками «Сменить станцию», «Пауза/Играть», «Остановить».",
        inline=False
    )
    embed.add_field(
        name="📋 Заявки в отряд",
        value=(
            "При вступлении на сервер ты получишь роль **Гость** и приветственное сообщение.\n"
            "Нажми **«Подать заявку»**, заполни форму – модерация рассмотрит её.\n"
            "После принятия ты получишь роль **Боец**!"
        ),
        inline=False
    )
    embed.add_field(
        name="📅 События (смежки)",
        value="Модераторы могут создавать смежки через кнопку в канале событий. Участники подтверждают участие реакциями ✅ / ❌.",
        inline=False
    )
    embed.set_footer(text="G4S Командование • v1.0")
    await interaction.response.send_message(embed=embed, ephemeral=True)
    logger.info(f"Пользователь {interaction.user} запросил справку")

@bot.tree.command(name="очистить", description="Очистить вашу историю диалога с AI")
async def slash_clear_history(interaction: discord.Interaction):
    user_id = interaction.user.id
    success = await clear_history(user_id)
    if success:
        await interaction.response.send_message("🧹 Ваша история диалога с AI очищена.", ephemeral=True)
        logger.info(f"Пользователь {interaction.user} очистил свою AI-историю")
    else:
        await interaction.response.send_message("📭 У вас не было сохранённой истории диалога.", ephemeral=True)

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
    await event_manager.setup_dashboard(bot)

    # === Радио ===
    bot.add_view(RadioControlView(radio_manager))
    bot.loop.create_task(radio_manager.auto_start(bot))

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
