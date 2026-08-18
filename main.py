import discord
from discord.ext import commands, tasks
from config import DISCORD_TOKEN
from arma_monitor import update_status
from ai_chat import on_ai_message
import event_manager

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
monitor_message = None

# ==================== КОМАНДА HELP ====================
@bot.command(name='help')
async def help_command(ctx):
    """Показывает справку по всем функциям бота и удаляет сообщение."""
    # Удаляем сообщение пользователя (если есть права)
    try:
        await ctx.message.delete()
    except:
        pass  # если прав нет, просто игнорируем

    # Формируем красивый embed
    embed = discord.Embed(
        title="🛡️ Справка по боту G4S Спортивный",
        description="Вот что я умею:",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="🤖 AI-чат",
        value="Напишите **`Ученый <вопрос>`** или **`Учёный <вопрос>`**, или просто упомяните меня (например, `@G4S Спортивный БОТ привет`), чтобы задать вопрос. Я отвечу с использованием DeepSeek.",
        inline=False
    )
    embed.add_field(
        name="🛡️ Мониторинг сервера Arma 3",
        value="Каждую минуту я обновляю информацию о сервере в специальном канале: статус, онлайн, нагрузка и списки игроков с разбивкой по фракциям.",
        inline=False
    )
    embed.add_field(
        name="📅 Создание смежек",
        value="В канале управления есть кнопка **«Создать смежку»**. Нажмите её, заполните форму (название, дата, время). Я опубликую объявление в канале анонсов. Чтобы подтвердить участие, поставьте реакцию ✅ или ❌ на сообщении. Списки обновляются автоматически.",
        inline=False
    )
    embed.add_field(
        name="🔔 Напоминания о смежках",
        value="За 24 часа до события я отправлю напоминание с упоминанием @everyone (если это включено в настройках).",
        inline=False
    )
    embed.add_field(
        name="❓ Эта справка",
        value="Используйте **`!help`** в любом канале, чтобы снова увидеть это сообщение.",
        inline=False
    )
    embed.set_footer(text="G4S Спортивный БОТ • v1.0")

    # Пытаемся отправить в личные сообщения
    try:
        await ctx.author.send(embed=embed)
    except discord.Forbidden:
        # Если ЛС закрыты, отправляем в канал с упоминанием и удаляем через 15 сек
        msg = await ctx.send(
            f"{ctx.author.mention}, ваши личные сообщения закрыты. Включите их, чтобы получить справку.",
            delete_after=15
        )
    except Exception as e:
        await ctx.send(f"❌ Не удалось отправить справку: {e}", delete_after=10)

# ==================== СОБЫТИЯ И ЗАДАЧИ ====================
@bot.event
async def on_ready():
    print(f'🛡️ Бот {bot.user.name} успешно запущен и готов к работе!')
    bot.add_listener(event_manager.on_reaction_add, 'on_reaction_add')
    bot.add_listener(event_manager.on_reaction_remove, 'on_reaction_remove')
    await event_manager.sync_events(bot)
    if not update_status_task.is_running():
        update_status_task.start()
    await event_manager.setup_event_button(bot)
    bot.loop.create_task(event_manager.reminder_task(bot))

@tasks.loop(seconds=60)
async def update_status_task():
    global monitor_message
    monitor_message = await update_status(bot, monitor_message)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    # Если сообщение начинается с '!', обрабатываем как команду
    if message.content.startswith('!'):
        await bot.process_commands(message)
        return
    # Иначе передаём AI-обработчику
    await on_ai_message(message, bot)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
