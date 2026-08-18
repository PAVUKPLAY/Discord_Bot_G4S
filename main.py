import discord
from discord.ext import commands, tasks
from config import DISCORD_TOKEN
from arma_monitor import update_status
from ai_chat import on_ai_message
import event_manager

intents = discord.Intents.default()
intents.message_content = True
# Включаем интенты для реакций
intents.reactions = True
intents.members = True  # чтобы получать информацию о пользователях

bot = commands.Bot(command_prefix='!', intents=intents)
monitor_message = None

@bot.event
async def on_ready():
    print(f'🛡️ Бот {bot.user.name} успешно запущен и готов к работе!')
    # Регистрируем обработчики реакций из event_manager
    bot.add_listener(event_manager.on_reaction_add, 'on_reaction_add')
    bot.add_listener(event_manager.on_reaction_remove, 'on_reaction_remove')
    # Синхронизируем существующие события
    await event_manager.sync_events(bot)
    # Запускаем задачи
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
    await on_ai_message(message, bot)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
