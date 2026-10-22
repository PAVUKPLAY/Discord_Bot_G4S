import discord
from discord import ui
from discord.ext import commands, tasks
import sqlite3
import os
import time
import logging
from datetime import datetime
from pathlib import Path
from config import ACTIVITY_CHANNEL_ID

logger = logging.getLogger(__name__)

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = Path(DATA_DIR) / "activity_data.sqlite3"

def fmt_time(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    if h > 0:
        return f"{h} ч. {m} мин."
    return f"{m} мин."

class ActivityStore:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self._init_db()

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self):
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS activity (
                    user_id INTEGER PRIMARY KEY,
                    voice_total INTEGER DEFAULT 0,
                    messages_total INTEGER DEFAULT 0,
                    voice_daily INTEGER DEFAULT 0,
                    messages_daily INTEGER DEFAULT 0,
                    last_date TEXT
                )
            """)

    def _check_daily_reset(self, con, user_id):
        today = datetime.now().strftime("%Y-%m-%d")
        row = con.execute("SELECT last_date FROM activity WHERE user_id=?", (user_id,)).fetchone()
        if row and row["last_date"] != today:
            con.execute("UPDATE activity SET voice_daily=0, messages_daily=0, last_date=? WHERE user_id=?", (today, user_id))
        elif not row:
            con.execute("INSERT INTO activity (user_id, last_date) VALUES (?, ?)", (user_id, today))

    def add_activity(self, user_id: int, voice_sec: int = 0, messages: int = 0):
        with self._connect() as con:
            self._check_daily_reset(con, user_id)
            con.execute("""
                UPDATE activity 
                SET voice_total = voice_total + ?, messages_total = messages_total + ?,
                    voice_daily = voice_daily + ?, messages_daily = messages_daily + ?
                WHERE user_id = ?
            """, (voice_sec, messages, voice_sec, messages, user_id))

    def get_user_stats(self, user_id: int):
        with self._connect() as con:
            self._check_daily_reset(con, user_id)
            return con.execute("SELECT * FROM activity WHERE user_id=?", (user_id,)).fetchone()

    def get_leaderboard(self, daily: bool = False, limit: int = 10):
        col_v = "voice_daily" if daily else "voice_total"
        col_m = "messages_daily" if daily else "messages_total"
        with self._connect() as con:
            return con.execute(f"""
                SELECT user_id, {col_v} as voice, {col_m} as msgs 
                FROM activity 
                WHERE {col_v} > 0 OR {col_m} > 0
                ORDER BY {col_v} DESC LIMIT ?
            """, (limit,)).fetchall()

class ActivityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = ActivityStore()
        self.voice_sessions = {}
        self.sync_task.start()

    def cog_unload(self):
        self.sync_task.cancel()

    @tasks.loop(minutes=5)
    async def sync_task(self):
        now = time.time()
        for user_id, join_time in list(self.voice_sessions.items()):
            duration = int(now - join_time)
            if duration > 0:
                await self.bot.loop.run_in_executor(None, self.store.add_activity, user_id, duration, 0)
                self.voice_sessions[user_id] = now

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if not member.bot:
                        self.voice_sessions[member.id] = time.time()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return
        now = time.time()
        if before.channel is None and after.channel is not None:
            self.voice_sessions[member.id] = now
        elif before.channel is not None and after.channel is None:
            join_time = self.voice_sessions.pop(member.id, now)
            duration = int(now - join_time)
            if duration > 0:
                await self.bot.loop.run_in_executor(None, self.store.add_activity, member.id, duration, 0)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return
        await self.bot.loop.run_in_executor(None, self.store.add_activity, message.author.id, 0, 1)

class ActivityView(ui.View):
    def __init__(self, cog: ActivityCog):
        super().__init__(timeout=None)
        self.cog = cog

    @ui.button(label="📊 Моя активность", style=discord.ButtonStyle.primary, custom_id="act_my")
    async def my_activity(self, interaction: discord.Interaction, button: ui.Button):
        stats = await interaction.client.loop.run_in_executor(None, self.cog.store.get_user_stats, interaction.user.id)
        embed = discord.Embed(title="📊 Ваша активность", color=discord.Color.blue())
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        if not stats:
            embed.description = "У вас пока нет активности."
        else:
            embed.add_field(name="🎙️ В голосовых (всего)", value=f"`{fmt_time(stats['voice_total'])}`", inline=True)
            embed.add_field(name="💬 Сообщений (всего)", value=f"`{stats['messages_total']} шт.`", inline=True)
            embed.add_field(name="🎙️ В голосовых (сегодня)", value=f"`{fmt_time(stats['voice_daily'])}`", inline=True)
            embed.add_field(name="💬 Сообщений (сегодня)", value=f"`{stats['messages_daily']} шт.`", inline=True)
        embed.set_footer(text="Code by PAVUK")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="🕒 24 часа", style=discord.ButtonStyle.secondary, custom_id="act_daily")
    async def daily_leaders(self, interaction: discord.Interaction, button: ui.Button):
        rows = await interaction.client.loop.run_in_executor(None, self.cog.store.get_leaderboard, True, 10)
        embed = discord.Embed(title="🔥 Самые активные за 24 часа", color=discord.Color.orange())
        if not rows:
            embed.description = "За последние 24 часа активности не было."
        else:
            lines = []
            for i, row in enumerate(rows, 1):
                member = interaction.guild.get_member(row["user_id"])
                name = member.display_name if member else f"Игрок {row['user_id']}"
                lines.append(f"**{i}.** {discord.utils.escape_markdown(name)} | 🎙️ {fmt_time(row['voice'])} | 💬 {row['msgs']}")
            embed.description = "\n".join(lines)
        embed.set_footer(text="Code by PAVUK")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="🏆 Лидеры", style=discord.ButtonStyle.success, custom_id="act_total")
    async def total_leaders(self, interaction: discord.Interaction, button: ui.Button):
        rows = await interaction.client.loop.run_in_executor(None, self.cog.store.get_leaderboard, False, 10)
        embed = discord.Embed(title="🏆 Лучшие бойцы (За всё время)", color=discord.Color.gold())
        if not rows:
            embed.description = "База активности пока пуста."
        else:
            lines = []
            for i, row in enumerate(rows, 1):
                member = interaction.guild.get_member(row["user_id"])
                name = member.display_name if member else f"Игрок {row['user_id']}"
                lines.append(f"**{i}.** {discord.utils.escape_markdown(name)} | 🎙️ {fmt_time(row['voice'])} | 💬 {row['msgs']}")
            embed.description = "\n".join(lines)
        embed.set_footer(text="Code by PAVUK")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ActivityCog(bot))

async def setup_activity_panel(bot: commands.Bot):
    if not ACTIVITY_CHANNEL_ID: return
    cog = bot.get_cog("ActivityCog")
    if not cog: return
    channel = bot.get_channel(ACTIVITY_CHANNEL_ID)
    if not channel:
        try: channel = await bot.fetch_channel(ACTIVITY_CHANNEL_ID)
        except Exception: return
    embed = discord.Embed(
        title="📈 Активность отряда G4S",
        description="Здесь отслеживается ваша активность на сервере.\nУчитывается время в голосовых каналах и количество сообщений.\n\nНажмите на кнопку ниже, чтобы посмотреть статистику.",
        color=discord.Color.brand_green()
    )
    embed.set_footer(text="Code by PAVUK")
    view = ActivityView(cog)
    async for msg in channel.history(limit=20):
        if msg.author == bot.user and msg.embeds and msg.components:
            for row in msg.components:
                for comp in row.children:
                    if hasattr(comp, 'custom_id') and comp.custom_id == "act_my":
                        await msg.edit(embed=embed, view=view)
                        return
    await channel.send(embed=embed, view=view)
