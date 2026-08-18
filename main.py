import discord
from discord.ext import commands, tasks
from config import DISCORD_TOKEN
from arma_monitor import update_status
from ai_chat import on_ai_message

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)
monitor_message = None

@bot.event
async def on_ready():
    print(f'🛡️ Бот {bot.user.name} успешно запущен и готов к работе!')
    if not update_status_task.is_running():
        update_status_task.start()

@tasks.loop(seconds=60)
async def update_status_task():
    global monitor_message
    monitor_message = await update_status(bot, monitor_message)

@bot.event
async def on_message(message):
    await on_ai_message(message, bot)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)