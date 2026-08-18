import discord
from discord.ext import commands, tasks
from config import DISCORD_TOKEN
from arma_monitor import update_status, cleanup_monitor
from ai_chat import on_ai_message
import event_manager
import quotes_manager

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command('help')

monitor_message = None

# ==================== КОМАНДА HELP ====================
@bot.command(name='help')
async def help_command(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    embed = discord.Embed(
        title="🛡️ Справка по боту G4S Сподручный",
        description="Вот что я умею:",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="🤖 AI-чат",
        value="Напишите **`Ученый <вопрос>`** или **`Учёный <вопрос>`**, или просто упомяните меня, чтобы задать вопрос.",
        inline=False
    )
    embed.add_field(
        name="🛡️ Мониторинг сервера Arma 3",
        value="Каждую минуту я обновляю информацию о сервере в специальном канале.",
        inline=False
    )
    embed.add_field(
        name="📝 Цитатник",
        value=(
            "Доступные команды:\n"
            "`!цитата` – случайная цитата\n"
            "`!цитаты [ник]` – цитаты пользователя\n"
            "`!добавить` – в ответ на сообщение, чтобы добавить его как цитату\n"
            "`!добавить <текст>` – добавить цитату вручную (автор – вы)\n"
            "`!удалить_цитату <id>` – удалить цитату (только для модераторов)"
        ),
        inline=False
    )
    embed.add_field(
        name="❓ Эта справка",
        value="Используйте **`!help`** в любом канале.",
        inline=False
    )
    embed.set_footer(text="G4S Сподручный • v1.0")

    try:
        await ctx.author.send(embed=embed)
    except discord.Forbidden:
        await ctx.send(
            f"{ctx.author.mention}, ваши ЛС закрыты. Включите их, чтобы получить справку.",
            delete_after=15
        )
    except Exception as e:
        await ctx.send(f"❌ Не удалось отправить справку: {e}", delete_after=10)

# ==================== КОМАНДЫ ЦИТАТНИКА ====================
@bot.command(name='цитата')
async def random_quote(ctx):
    quote = await quotes_manager.get_random_quote()
    if not quote:
        await ctx.send("📭 Цитат пока нет. Добавьте первую с помощью `!добавить`.")
        return
    embed = discord.Embed(
        title="📜 Случайная цитата",
        description=f"\"{quote['text']}\"",
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Автор: {quote['author_name']} • ID: {quote['id']}")
    await ctx.send(embed=embed)

@bot.command(name='цитаты')
async def user_quotes(ctx, *, user: discord.User = None):
    if user is None:
        user = ctx.author
    quotes = await quotes_manager.get_user_quotes(user.id)
    if not quotes:
        await ctx.send(f"📭 У пользователя {user.display_name} нет цитат.")
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
        embed.set_footer(text=f"Показано 10 из {len(quotes)} цитат.")
    await ctx.send(embed=embed)

@bot.command(name='добавить', aliases=['добавить_цитату'])
async def add_quote_cmd(ctx, *, text: str = None):
    """
    Добавляет цитату.
    Если команда вызвана в ответ на сообщение (без текста) – берётся текст того сообщения и его автор.
    Если указан текст – добавляется этот текст, автором считается автор команды.
    """
    ref = ctx.message.reference
    if ref is not None:
        try:
            replied_msg = await ctx.channel.fetch_message(ref.message_id)
        except discord.NotFound:
            await ctx.send("❌ Сообщение, на которое вы ответили, не найдено.", delete_after=10)
            return
        except Exception as e:
            await ctx.send(f"❌ Ошибка при получении сообщения: {e}", delete_after=10)
            return

        quote_text = replied_msg.content
        if not quote_text:
            await ctx.send("❌ В этом сообщении нет текста для цитаты.", delete_after=10)
            return
        author_id = replied_msg.author.id
        author_name = replied_msg.author.display_name

        quote_id = await quotes_manager.add_quote(author_id, author_name, quote_text)
        await ctx.send(f"✅ Цитата добавлена (ID: {quote_id})")
        return

    if text:
        if len(text) > 500:
            await ctx.send("❌ Слишком длинная цитата (максимум 500 символов).", delete_after=10)
            return
        quote_id = await quotes_manager.add_quote(ctx.author.id, ctx.author.display_name, text)
        await ctx.send(f"✅ Цитата добавлена (ID: {quote_id})")
        return

    await ctx.send(
        "❌ Чтобы добавить цитату, либо ответьте на сообщение и напишите `!добавить`, либо укажите текст: `!добавить <текст>`.",
        delete_after=15
    )

@bot.command(name='удалить_цитату')
async def remove_quote_cmd(ctx, quote_id: int):
    if not ctx.author.guild_permissions.manage_messages:
        await ctx.send("❌ У вас недостаточно прав для удаления цитаты.", delete_after=10)
        return

    success = await quotes_manager.remove_quote(quote_id)
    if success:
        await ctx.send(f"✅ Цитата с ID {quote_id} удалена.")
    else:
        await ctx.send(f"❌ Цитата с ID {quote_id} не найдена.")

# ==================== СОБЫТИЯ И ЗАДАЧИ ====================
@bot.event
async def on_ready():
    global monitor_message
    print(f'🛡️ Бот {bot.user.name} успешно запущен и готов к работе!')

    bot.add_listener(event_manager.on_reaction_add, 'on_reaction_add')
    bot.add_listener(event_manager.on_reaction_remove, 'on_reaction_remove')

    await event_manager.sync_events(bot)

    await cleanup_monitor(bot)
    monitor_message = await update_status(bot, None)

    await event_manager.cleanup_event_button(bot)

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
    if message.content.startswith('!'):
        await bot.process_commands(message)
        return
    await on_ai_message(message, bot)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
