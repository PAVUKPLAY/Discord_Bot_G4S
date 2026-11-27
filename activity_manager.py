from contextlib import closing

import discord
from discord import ui
from discord.ext import commands, tasks
import sqlite3
import os
import time
import logging
from datetime import datetime, timezone
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
        with closing(self._connect()) as con, con:
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
            # Миграция: добавляем дату вступления, если её нет (для красивого профиля)
            try:
                con.execute("ALTER TABLE activity ADD COLUMN join_date TEXT")
            except sqlite3.OperationalError:
                pass

    def add_activity(self, user_id: int, voice_sec: int = 0, messages: int = 0):
        today = datetime.now(timezone.utc).date().isoformat()
        with closing(self._connect()) as con, con:
            con.execute("""
                INSERT INTO activity (
                    user_id, voice_total, messages_total, voice_daily,
                    messages_daily, last_date, join_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    voice_total = activity.voice_total + excluded.voice_total,
                    messages_total = activity.messages_total + excluded.messages_total,
                    voice_daily = excluded.voice_daily + CASE
                        WHEN activity.last_date = excluded.last_date THEN activity.voice_daily
                        ELSE 0 END,
                    messages_daily = excluded.messages_daily + CASE
                        WHEN activity.last_date = excluded.last_date THEN activity.messages_daily
                        ELSE 0 END,
                    last_date = excluded.last_date,
                    join_date = COALESCE(NULLIF(activity.join_date, ''), excluded.join_date)
            """, (user_id, voice_sec, messages, voice_sec, messages, today, today))

    def get_user_stats(self, user_id: int):
        self.add_activity(user_id)
        with closing(self._connect()) as con:
            return con.execute("SELECT * FROM activity WHERE user_id=?", (user_id,)).fetchone()

    def get_leaderboard(self, daily: bool = False, limit: int = 10):
        col_v = "voice_daily" if daily else "voice_total"
        col_m = "messages_daily" if daily else "messages_total"
        date_filter = "AND last_date = ?" if daily else ""
        params = (datetime.now(timezone.utc).date().isoformat(), limit) if daily else (limit,)
        with closing(self._connect()) as con:
            return con.execute(f"""
                SELECT user_id, {col_v} as voice, {col_m} as msgs 
                FROM activity 
                WHERE ({col_v} > 0 OR {col_m} > 0) {date_filter}
                ORDER BY {col_v} DESC, {col_m} DESC, user_id LIMIT ?
            """, params).fetchall()


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
        now = time.monotonic()
        for user_id, join_time in list(self.voice_sessions.items()):
            if self.voice_sessions.get(user_id) != join_time:
                continue
            duration = int(now - join_time)
            if duration > 0:
                checkpoint = join_time + duration
                self.voice_sessions[user_id] = checkpoint
                try:
                    await self.bot.loop.run_in_executor(None, self.store.add_activity, user_id, duration, 0)
                except sqlite3.Error:
                    if self.voice_sessions.get(user_id) == checkpoint:
                        self.voice_sessions[user_id] = join_time
                    logger.exception("Не удалось сохранить голосовую активность пользователя %s.", user_id)

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if not member.bot:
                        # При gateway reconnect сохраняем время уже открытой сессии.
                        self.voice_sessions.setdefault(member.id, time.monotonic())

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return
        now = time.monotonic()
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


# ==================== UI (Кнопки) ====================

class ActivityView(ui.View):
    def __init__(self, cog: ActivityCog):
        super().__init__(timeout=None)
        self.cog = cog

    @ui.button(label="👤 Мой профиль", style=discord.ButtonStyle.primary, custom_id="act_profile")
    async def my_profile(self, interaction: discord.Interaction, button: ui.Button):
        # 1. Получаем активность
        stats = await interaction.client.loop.run_in_executor(None, self.cog.store.get_user_stats, interaction.user.id)
        
        # 2. Получаем баланс казино (если модуль загружен)
        casino_balance = 0
        casino_cog = interaction.client.get_cog("Casino")
        if casino_cog:
            try:
                casino_balance = await casino_cog.store.balance(interaction.user.id)
            except Exception:
                pass

        embed = discord.Embed(title="👤 Ваш профиль", color=discord.Color.blue())
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        if not stats:
            embed.description = "Вы пока не проявляли активности. Общайтесь и сидите в войсах!"
        else:
            join_date = stats['join_date'] if stats['join_date'] else "Неизвестно"
            
            embed.add_field(name="💰 Баланс казино", value=f"`{casino_balance} монет`", inline=True)
            embed.add_field(name="📅 Активность отслеживается с", value=f"`{join_date}`", inline=True)
            embed.add_field(name="⠀", value="⠀", inline=True) # пустышка для ровной сетки
            
            embed.add_field(name="🎙️ В голосовых (всего)", value=f"`{fmt_time(stats['voice_total'])}`", inline=True)
            embed.add_field(name="💬 Сообщений (всего)", value=f"`{stats['messages_total']} шт.`", inline=True)
            embed.add_field(name="⠀", value="⠀", inline=True)
            
            embed.add_field(name="🎙️ В голосовых (сегодня)", value=f"`{fmt_time(stats['voice_daily'])}`", inline=True)
            embed.add_field(name="💬 Сообщений (сегодня)", value=f"`{stats['messages_daily']} шт.`", inline=True)
            
        embed.set_footer(text="Code by PAVUK")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="🕒 Топ за сегодня", style=discord.ButtonStyle.secondary, custom_id="act_daily")
    async def daily_leaders(self, interaction: discord.Interaction, button: ui.Button):
        rows = await interaction.client.loop.run_in_executor(None, self.cog.store.get_leaderboard, True, 10)
        
        embed = discord.Embed(title="🔥 Самые активные сегодня (UTC)", color=discord.Color.orange())
        
        if not rows:
            embed.description = "Сегодня активности ещё не было."
        else:
            lines = []
            for i, row in enumerate(rows, 1):
                member = interaction.guild.get_member(row["user_id"])
                name = member.display_name if member else f"Игрок {row['user_id']}"
                lines.append(f"**{i}.** {discord.utils.escape_markdown(name)} | 🎙️ {fmt_time(row['voice'])} | 💬 {row['msgs']}")
            embed.description = "\n".join(lines)
            
        embed.set_footer(text="Code by PAVUK")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="🎖️ Топ за всё время", style=discord.ButtonStyle.success, custom_id="act_total")
    async def total_leaders(self, interaction: discord.Interaction, button: ui.Button):
        rows = await interaction.client.loop.run_in_executor(None, self.cog.store.get_leaderboard, False, 10)
        
        embed = discord.Embed(title="🎖️ Лучшие бойцы (За всё время)", color=discord.Color.brand_green())
        
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
        description=(
            "Здесь отслеживается жизнь отряда.\n"
            "Смотрите свой личный профиль и следите за топами бойцов.\n"
            "Учитывается время в голосовых каналах и количество сообщений."
        ),
        color=discord.Color.brand_green()
    )
    embed.set_footer(text="Code by PAVUK")
    
    view = ActivityView(cog)

    # Ищем старую панель, чтобы обновить её без дублей
    async for msg in channel.history(limit=20):
        if msg.author == bot.user and msg.embeds and msg.components:
            for row in msg.components:
                for comp in row.children:
                    if hasattr(comp, 'custom_id') and comp.custom_id == "act_profile":
                        await msg.edit(embed=embed, view=view)
                        return

    await channel.send(embed=embed, view=view)
