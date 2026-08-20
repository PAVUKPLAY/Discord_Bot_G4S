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

# ==================== СЛЕШ-КОМАНДА HELP ====================
@bot.tree.command(name='help', description='Показать справку по боту')
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
            "Для очистки истории диалога используйте **`/очистить`** (или `/clear`).\n"
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
            "Доступные команды (все с префиксом `/`):\n"
            "`/цитата` – случайная цитата\n"
            "`/цитаты [ник]` – цитаты пользователя\n"
            "`/добавить` – в ответ на сообщение, чтобы добавить его как цитату\n"
            "`/добавить <текст>` – добавить цитату вручную (автор – вы)\n"
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
        name="❓ Эта справка",
        value="Используйте **`/help`** в любом канале.",
        inline=False
    )
    embed.set_footer(text="G4S Командование • v1.0")

    await interaction.response.send_message(embed=embed, ephemeral=True)
    logger.info(f"Пользователь {interaction.user} запросил справку")

# ==================== ПРЕФИКСНЫЕ КОМАНДЫ ====================
@bot.command(name='цитата')
async def random_quote(ctx):
    if not get_status("quotes_enabled", True):
        await ctx.send("📝 Цитатник в данный момент **выключен**. Включите его через панель управления.", delete_after=10)
        return
    try:
        await ctx.message.delete()
    except:
        pass
    quote = await quotes_manager.get_random_quote()
    if not quote:
        await ctx.send("📭 Цитат пока нет. Добавьте первую с помощью `/добавить`.", delete_after=10)
        logger.info(f"Запрос случайной цитаты от {ctx.author}: база пуста")
        return
    embed = discord.Embed(
        title="📜 Случайная цитата",
        description=f"\"{quote['text']}\"",
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Автор: {quote['author_name']} • ID: {quote['id']} • G4S Командование")
    await ctx.send(embed=embed)
    logger.info(f"Пользователь {ctx.author} получил случайную цитату ID {quote['id']}")

@bot.command(name='цитаты')
async def user_quotes(ctx, *, user: discord.User = None):
    if not get_status("quotes_enabled", True):
        await ctx.send("📝 Цитатник в данный момент **выключен**. Включите его через панель управления.", delete_after=10)
        return
    try:
        await ctx.message.delete()
    except:
        pass
    if user is None:
        user = ctx.author
    quotes = await quotes_manager.get_user_quotes(user.id)
    if not quotes:
        await ctx.send(f"📭 У пользователя {user.display_name} нет цитат.", delete_after=10)
        logger.info(f"Запрос цитат пользователя {user.display_name} от {ctx.author}: нет цитат")
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
    await ctx.send(embed=embed)
    logger.info(f"Пользователь {ctx.author} запросил цитаты {user.display_name} (всего {len(quotes)})")

@bot.command(name='добавить', aliases=['добавить_цитату'])
async def add_quote_cmd(ctx, *, text: str = None):
    if not get_status("quotes_enabled", True):
        await ctx.send("📝 Цитатник в данный момент **выключен**. Включите его через панель управления.", delete_after=10)
        return
    try:
        await ctx.message.delete()
    except:
        pass
    ref = ctx.message.reference
    if ref is not None:
        try:
            replied_msg = await ctx.channel.fetch_message(ref.message_id)
        except discord.NotFound:
            await ctx.send("❌ Сообщение, на которое вы ответили, не найдено.", delete_after=10)
            logger.error(f"Ошибка добавления цитаты: сообщение не найдено (пользователь {ctx.author})")
            return
        except Exception as e:
            await ctx.send(f"❌ Ошибка при получении сообщения: {e}", delete_after=10)
            logger.error(f"Ошибка получения сообщения для цитаты: {e}")
            return

        quote_text = replied_msg.content
        if not quote_text:
            await ctx.send("❌ В этом сообщении нет текста для цитаты.", delete_after=10)
            logger.warning(f"Попытка добавить цитату из пустого сообщения от {ctx.author}")
            return
        author_id = replied_msg.author.id
        author_name = replied_msg.author.display_name

        quote_id = await quotes_manager.add_quote(author_id, author_name, quote_text)
        await ctx.send(f"✅ Цитата добавлена (ID: {quote_id})")
        logger.info(f"Цитата добавлена пользователем {ctx.author} (автор {author_name}, ID {quote_id})")
        return

    if text:
        if len(text) > 500:
            await ctx.send("❌ Слишком длинная цитата (максимум 500 символов).", delete_after=10)
            logger.warning(f"Попытка добавить слишком длинную цитату от {ctx.author}")
            return
        quote_id = await quotes_manager.add_quote(ctx.author.id, ctx.author.display_name, text)
        await ctx.send(f"✅ Цитата добавлена (ID: {quote_id})")
        logger.info(f"Цитата добавлена пользователем {ctx.author} (ID {quote_id})")
        return

    await ctx.send(
        "❌ Чтобы добавить цитату, либо ответьте на сообщение и напишите `/добавить`, либо укажите текст: `/добавить <текст>`.",
        delete_after=15
    )
    logger.info(f"Неверное использование команды /добавить пользователем {ctx.author}")

@bot.command(name='удалить_цитату')
async def remove_quote_cmd(ctx, quote_id: int):
    if not get_status("quotes_enabled", True):
        await ctx.send("📝 Цитатник в данный момент **выключен**. Включите его через панель управления.", delete_after=10)
        return
    try:
        await ctx.message.delete()
    except:
        pass
    if not has_moderator_role(ctx.author):
        await ctx.send("❌ У вас недостаточно прав для удаления цитаты.", delete_after=10)
        logger.warning(f"Пользователь {ctx.author} пытался удалить цитату без прав")
        return

    success = await quotes_manager.remove_quote(quote_id)
    if success:
        await ctx.send(f"✅ Цитата с ID {quote_id} удалена.")
        logger.info(f"Цитата ID {quote_id} удалена пользователем {ctx.author}")
    else:
        await ctx.send(f"❌ Цитата с ID {quote_id} не найдена.")
        logger.warning(f"Попытка удалить несуществующую цитату ID {quote_id} пользователем {ctx.author}")

@bot.command(name='очистить', aliases=['clear'])
async def clear_history_cmd(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    user_id = ctx.author.id
    success = await clear_history(user_id)
    if success:
        await ctx.send("🧹 Ваша история диалога с AI очищена.", delete_after=10)
        logger.info(f"Пользователь {ctx.author} очистил свою AI-историю")
    else:
        await ctx.send("📭 У вас не было сохранённой истории диалога.", delete_after=10)
        logger.info(f"Пользователь {ctx.author} попытался очистить историю, но её не было")

# ==================== СОБЫТИЯ ====================
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
