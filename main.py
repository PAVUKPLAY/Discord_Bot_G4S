import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
from config import DISCORD_TOKEN
from arma_monitor import update_status, cleanup_monitor
from ai_chat import on_ai_message, clear_history
import event_manager
import quotes_manager
from toggle_manager import get_status
from utils import has_moderator_role
import welcome_manager
import bunker_advanced as ba

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

bot = commands.Bot(command_prefix='/', intents=intents)
bot.remove_command('help')

monitor_message = None
active_games = {}  # channel_id -> ba.AdvancedGame

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
        name="📝 Цитатник",
        value=(
            "Доступные команды:\n"
            "`/цитата` – случайная цитата\n"
            "`/цитаты [ник]` – цитаты пользователя\n"
            "`/добавить <текст>` – добавить цитату (автор – вы)\n"
            "`/удалить_цитату <id>` – удалить цитату (только для модераторов)\n"
            "Управление включением/выключением цитатника – через панель управления."
        ),
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
        name="🎲 Игра Бункер",
        value=(
            "Создайте игру с помощью `/bunker_create`.\n"
            "Присоединяйтесь к голосовому каналу и нажмите кнопку «Присоединиться».\n"
            "Когда все готовы, нажмите «Начать игру» – начнётся пошаговый процесс с открытием карт и голосованием."
        ),
        inline=False
    )
    embed.add_field(
        name="❓ Эта справка",
        value="Используйте **`/help`** в любом канале.",
        inline=False
    )
    embed.set_footer(text="G4S Командование • v1.0")
    await interaction.response.send_message(embed=embed, ephemeral=True)
    logger.info(f"Пользователь {interaction.user} запросил справку")

@bot.tree.command(name="цитата", description="Показать случайную цитату")
async def slash_random_quote(interaction: discord.Interaction):
    if not get_status("quotes_enabled", True):
        await interaction.response.send_message("📝 Цитатник в данный момент **выключен**. Включите его через панель управления.", ephemeral=True)
        return
    quote = await quotes_manager.get_random_quote()
    if not quote:
        await interaction.response.send_message("📭 Цитат пока нет. Добавьте первую с помощью `/добавить`.", ephemeral=True)
        return
    embed = discord.Embed(
        title="📜 Случайная цитата",
        description=f"\"{quote['text']}\"",
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Автор: {quote['author_name']} • ID: {quote['id']} • G4S Командование")
    await interaction.response.send_message(embed=embed)
    logger.info(f"Пользователь {interaction.user} получил случайную цитату ID {quote['id']}")

@bot.tree.command(name="цитаты", description="Показать цитаты пользователя")
async def slash_user_quotes(interaction: discord.Interaction, user: discord.User = None):
    if not get_status("quotes_enabled", True):
        await interaction.response.send_message("📝 Цитатник в данный момент **выключен**. Включите его через панель управления.", ephemeral=True)
        return
    if user is None:
        user = interaction.user
    quotes = await quotes_manager.get_user_quotes(user.id)
    if not quotes:
        await interaction.response.send_message(f"📭 У пользователя {user.display_name} нет цитат.", ephemeral=True)
        return
    embed = discord.Embed(
        title=f"📜 Цитаты {user.display_name}",
        color=discord.Color.blue()
    )
    for q in quotes[:10]:
        embed.add_field(
            name=f"ID {q['id']}",
            value=f"\"{q['text']}\"",
            inline=False
        )
    if len(quotes) > 10:
        embed.set_footer(text=f"Показано 10 из {len(quotes)} цитат. • G4S Командование")
    else:
        embed.set_footer(text="G4S Командование")
    await interaction.response.send_message(embed=embed)
    logger.info(f"Пользователь {interaction.user} запросил цитаты {user.display_name} (всего {len(quotes)})")

@bot.tree.command(name="добавить", description="Добавить новую цитату (автор – вы)")
async def slash_add_quote(interaction: discord.Interaction, text: str):
    if not get_status("quotes_enabled", True):
        await interaction.response.send_message("📝 Цитатник в данный момент **выключен**. Включите его через панель управления.", ephemeral=True)
        return
    if len(text) > 500:
        await interaction.response.send_message("❌ Слишком длинная цитата (максимум 500 символов).", ephemeral=True)
        return
    quote_id = await quotes_manager.add_quote(interaction.user.id, interaction.user.display_name, text)
    await interaction.response.send_message(f"✅ Цитата добавлена (ID: {quote_id})", ephemeral=True)
    logger.info(f"Цитата добавлена пользователем {interaction.user} (ID {quote_id})")

@bot.tree.command(name="удалить_цитату", description="Удалить цитату по ID (только для модераторов)")
async def slash_remove_quote(interaction: discord.Interaction, quote_id: int):
    if not get_status("quotes_enabled", True):
        await interaction.response.send_message("📝 Цитатник в данный момент **выключен**. Включите его через панель управления.", ephemeral=True)
        return
    if not has_moderator_role(interaction.user):
        await interaction.response.send_message("❌ У вас недостаточно прав для удаления цитаты.", ephemeral=True)
        return
    success = await quotes_manager.remove_quote(quote_id)
    if success:
        await interaction.response.send_message(f"✅ Цитата с ID {quote_id} удалена.", ephemeral=True)
        logger.info(f"Цитата ID {quote_id} удалена пользователем {interaction.user}")
    else:
        await interaction.response.send_message(f"❌ Цитата с ID {quote_id} не найдена.", ephemeral=True)

@bot.tree.command(name="очистить", description="Очистить вашу историю диалога с AI")
async def slash_clear_history(interaction: discord.Interaction):
    user_id = interaction.user.id
    success = await clear_history(user_id)
    if success:
        await interaction.response.send_message("🧹 Ваша история диалога с AI очищена.", ephemeral=True)
        logger.info(f"Пользователь {interaction.user} очистил свою AI-историю")
    else:
        await interaction.response.send_message("📭 У вас не было сохранённой истории диалога.", ephemeral=True)

# ==================== КОМАНДЫ БУНКЕРА ====================

@bot.tree.command(name="bunker_create", description="Создать новую игру Бункер в этом канале")
@app_commands.describe(max_players="Максимальное количество игроков (по умолчанию 6)")
async def bunker_create(interaction: discord.Interaction, max_players: int = 6):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ У вас недостаточно прав.", ephemeral=True)
        return
    if interaction.channel_id in active_games:
        await interaction.response.send_message("❌ В этом канале уже есть игра.", ephemeral=True)
        return
    game = ba.AdvancedGame(interaction.guild, interaction.channel, max_players)
    await game.create_channels()
    active_games[interaction.channel_id] = game
    embed = discord.Embed(
        title="🎮 Игра Бункер создана!",
        description=f"Максимум игроков: {max_players}\nПрисоединяйтесь к голосовому каналу `{game.voice_channel.name}` и нажмите кнопку ниже.",
        color=discord.Color.green()
    )
    view = ba.LobbyView(game)
    await interaction.response.send_message(embed=embed, view=view)
    logger.info(f"Игра Бункер создана в канале {interaction.channel_id} пользователем {interaction.user}")

@bot.tree.command(name="bunker_end_advanced", description="Принудительно завершить игру в этом канале")
async def bunker_end_advanced(interaction: discord.Interaction):
    game = active_games.get(interaction.channel_id)
    if not game:
        await interaction.response.send_message("❌ Нет активной игры.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ У вас недостаточно прав.", ephemeral=True)
        return
    await game.finish_game()
    del active_games[interaction.channel_id]
    await interaction.response.send_message("✅ Игра завершена.", ephemeral=True)

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
