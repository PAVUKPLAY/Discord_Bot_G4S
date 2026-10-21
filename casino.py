import asyncio
import random
import sqlite3
import os
import logging
from pathlib import Path
from typing import Optional

import discord
from discord import ui
from discord.ext import commands

logger = logging.getLogger(__name__)

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = Path(DATA_DIR) / "casino_data.sqlite3"

STARTING_BALANCE = 1000
DAILY_REWARD = 250
MIN_BET = 10
MAX_BET = 100_000

SLOT_SYMBOLS = ["🍒", "🍋", "🍇", "🍉", "⭐", "💎"]
SLOT_WEIGHTS = [30, 25, 20, 15, 8, 2]


def fmt(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def validate_bet(bet: int):
    if bet < MIN_BET or bet > MAX_BET:
        raise ValueError(f"Ставка должна быть от {fmt(MIN_BET)} до {fmt(MAX_BET)} монет.")


class CasinoStore:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.lock = asyncio.Lock()
        self._init_db()

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self):
        with self._connect() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS casino_users (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 1000,
                    daily_claimed INTEGER NOT NULL DEFAULT 0,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    wagered INTEGER NOT NULL DEFAULT 0,
                    net_profit INTEGER NOT NULL DEFAULT 0
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS casino_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    game TEXT NOT NULL,
                    bet INTEGER NOT NULL,
                    delta INTEGER NOT NULL,
                    balance_after INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def _ensure_user(self, con, user_id: int):
        con.execute(
            "INSERT OR IGNORE INTO casino_users(user_id, balance) VALUES (?, ?)",
            (user_id, STARTING_BALANCE),
        )

    async def balance(self, user_id: int) -> int:
        async with self.lock:
            with self._connect() as con:
                self._ensure_user(con, user_id)
                row = con.execute(
                    "SELECT balance FROM casino_users WHERE user_id=?", (user_id,)
                ).fetchone()
                return int(row["balance"])

    async def daily(self, user_id: int):
        async with self.lock:
            with self._connect() as con:
                self._ensure_user(con, user_id)
                row = con.execute(
                    "SELECT balance, daily_claimed FROM casino_users WHERE user_id=?",
                    (user_id,),
                ).fetchone()
                now_day = int(__import__("time").time() // 86400)
                if int(row["daily_claimed"]) >= now_day:
                    return False, int(row["balance"])
                new_balance = int(row["balance"]) + DAILY_REWARD
                con.execute(
                    "UPDATE casino_users SET balance=?, daily_claimed=? WHERE user_id=?",
                    (new_balance, now_day, user_id),
                )
                con.execute(
                    "INSERT INTO casino_history(user_id, game, bet, delta, balance_after) "
                    "VALUES (?, 'Ежедневный бонус', 0, ?, ?)",
                    (user_id, DAILY_REWARD, new_balance),
                )
                return True, new_balance

    async def play(self, user_id: int, game: str, bet: int, delta: int):
        async with self.lock:
            with self._connect() as con:
                self._ensure_user(con, user_id)
                row = con.execute(
                    "SELECT balance FROM casino_users WHERE user_id=?", (user_id,)
                ).fetchone()
                balance = int(row["balance"])
                if bet < MIN_BET or bet > MAX_BET:
                    raise ValueError(f"Ставка должна быть от {fmt(MIN_BET)} до {fmt(MAX_BET)}.")
                if balance < bet:
                    raise ValueError(f"Недостаточно монет. Баланс: {fmt(balance)}.")
                new_balance = balance + delta
                if new_balance < 0:
                    raise ValueError("Недостаточно монет для завершения ставки.")
                won = delta > 0
                con.execute(
                    """UPDATE casino_users
                       SET balance=?, wins=wins+?, losses=losses+?,
                           wagered=wagered+?, net_profit=net_profit+?
                       WHERE user_id=?""",
                    (new_balance, int(won), int(delta < 0), bet, delta, user_id),
                )
                con.execute(
                    """INSERT INTO casino_history(user_id, game, bet, delta, balance_after)
                       VALUES (?, ?, ?, ?, ?)""",
                    (user_id, game, bet, delta, new_balance),
                )
                return new_balance

    async def leaderboard(self, limit: int = 10):
        async with self.lock:
            with self._connect() as con:
                return con.execute(
                    "SELECT user_id, balance, wins, net_profit FROM casino_users "
                    "ORDER BY balance DESC LIMIT ?", (limit,)
                ).fetchall()

    async def history(self, user_id: int, limit: int = 5):
        async with self.lock:
            with self._connect() as con:
                return con.execute(
                    "SELECT game, bet, delta, balance_after, created_at FROM casino_history "
                    "WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)
                ).fetchall()


class CasinoModal(ui.Modal):
    def __init__(self, title: str, bet_label: str = "Ставка (в монетах)"):
        super().__init__(title=title)
        self.bet_input = ui.TextInput(label=bet_label, placeholder=f"От {MIN_BET} до {MAX_BET}", required=True)
        self.add_item(self.bet_input)


class SlotsModal(CasinoModal):
    def __init__(self):
        super().__init__(title="🎰 Слоты")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet = int(self.bet_input.value)
            validate_bet(bet)
            symbols = random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=3)
            multiplier = 0
            if symbols[0] == symbols[1] == symbols[2]:
                multiplier = {"💎": 20, "⭐": 10, "🍉": 5, "🍇": 4, "🍋": 3, "🍒": 3}[symbols[0]]
            elif len(set(symbols)) == 2:
                multiplier = 0.5
            payout = int(bet * multiplier)
            delta = payout - bet
            
            cog = interaction.client.get_cog("Casino")
            balance = await cog.store.play(interaction.user.id, "Слоты", bet, delta)
            
            result = f"Выигрыш: **{fmt(payout)}**" if delta > 0 else ("Возврат части ставки." if delta == -bet // 2 else "Ставка проиграна.")
            embed = discord.Embed(title="🎰 Слоты", description=f"┏ {' │ '.join(symbols)} ┓\n\n{result}", color=discord.Color.green() if delta > 0 else discord.Color.red())
            embed.add_field(name="Ставка", value=fmt(bet))
            embed.add_field(name="Изменение", value=f"{'+' if delta > 0 else ''}{fmt(delta)}")
            embed.add_field(name="Баланс", value=fmt(balance))
            embed.set_footer(text="Code by PAVUK")
            await interaction.response.send_message(embed=embed)
        except ValueError:
            await interaction.response.send_message("❌ Введите корректную ставку числом.", ephemeral=True)


class CoinModal(ui.Modal):
    def __init__(self):
        super().__init__(title="🪙 Монетка")
        self.bet_input = ui.TextInput(label="Ставка (в монетах)", placeholder=f"От {MIN_BET} до {MAX_BET}", required=True)
        self.choice_input = ui.TextInput(label="Орёл или Решка?", placeholder="Напишите: орёл или решка", required=True)
        self.add_item(self.bet_input)
        self.add_item(self.choice_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet = int(self.bet_input.value)
            validate_bet(bet)
            choice = self.choice_input.value.strip().lower()
            if choice not in ("орёл", "орел", "решка"):
                await interaction.response.send_message("❌ Напишите «орёл» или «решка».", ephemeral=True)
                return
            if choice == "орел": choice = "орёл"
            
            result = random.choice(["орёл", "решка"])
            won = result == choice
            delta = bet if won else -bet
            
            cog = interaction.client.get_cog("Casino")
            balance = await cog.store.play(interaction.user.id, "Монетка", bet, delta)
            
            embed = discord.Embed(
                title="🪙 Монетка",
                description=f"Выпало: **{result.capitalize()}**\n" + (f"🎉 Вы выиграли **{fmt(bet)}**!" if won else "Увы, ставка проиграна."),
                color=discord.Color.green() if won else discord.Color.red(),
            )
            embed.add_field(name="Баланс", value=fmt(balance))
            embed.set_footer(text="Code by PAVUK")
            await interaction.response.send_message(embed=embed)
        except ValueError:
            await interaction.response.send_message("❌ Введите корректную ставку числом.", ephemeral=True)


class RouletteModal(ui.Modal):
    def __init__(self):
        super().__init__(title="🎡 Рулетка")
        self.bet_input = ui.TextInput(label="Ставка (в монетах)", placeholder=f"От {MIN_BET} до {MAX_BET}", required=True)
        self.type_input = ui.TextInput(label="На что ставим?", placeholder="Красное, Чёрное, Чётное, Нечётное или Число", required=True)
        self.number_input = ui.TextInput(label="Число (если ставите на число)", placeholder="От 0 до 36", required=False)
        self.add_item(self.bet_input)
        self.add_item(self.type_input)
        self.add_item(self.number_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet = int(self.bet_input.value)
            validate_bet(bet)
            t = self.type_input.value.strip().lower()
            
            red_numbers = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
            spin = random.randint(0, 36)
            
            if t in ("число", "числа"):
                if not self.number_input.value:
                    await interaction.response.send_message("❌ Укажите число от 0 до 36.", ephemeral=True)
                    return
                num = int(self.number_input.value)
                if not (0 <= num <= 36): raise ValueError()
                won = spin == num
                multiplier = 36
            elif spin == 0:
                won, multiplier = False, 2
            elif t in ("красное", "красный"):
                won, multiplier = spin in red_numbers, 2
            elif t in ("чёрное", "черное", "черный", "чёрный"):
                won, multiplier = spin not in red_numbers, 2
            elif t in ("чётное", "четное", "чёт", "чет"):
                won, multiplier = spin % 2 == 0, 2
            elif t in ("нечётное", "нечетное", "нечёт", "нечет"):
                won, multiplier = spin % 2 == 1, 2
            else:
                await interaction.response.send_message("❌ Неверный тип ставки. Напишите: Красное, Чёрное, Чётное, Нечётное или Число.", ephemeral=True)
                return

            payout = bet * multiplier if won else 0
            delta = payout - bet
            
            cog = interaction.client.get_cog("Casino")
            balance = await cog.store.play(interaction.user.id, "Рулетка", bet, delta)
            
            color = discord.Color.dark_grey() if spin == 0 else (discord.Color.red() if spin in red_numbers else discord.Color.from_rgb(25, 25, 25))
            embed = discord.Embed(title="🎡 Рулетка G4S", description=f"Выпало: **{spin}** {'🟢' if spin == 0 else ('🔴' if spin in red_numbers else '⚫')}\n" + (f"🎉 Выигрыш: **{fmt(payout)}** монет" if won else "Ставка проиграна."), color=color)
            embed.add_field(name="Ставка", value=f"{fmt(bet)} на {t.capitalize()}")
            embed.add_field(name="Баланс", value=fmt(balance))
            embed.set_footer(text="Code by PAVUK")
            await interaction.response.send_message(embed=embed)
        except ValueError:
            await interaction.response.send_message("❌ Проверьте правильность введенных данных (ставка и число должны быть цифрами).", ephemeral=True)


class CasinoView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        from config import CASINO_CHANNEL_ID
        if CASINO_CHANNEL_ID and interaction.channel_id != CASINO_CHANNEL_ID:
            await interaction.response.send_message(f"❌ Казино работает только в канале <#{CASINO_CHANNEL_ID}>.", ephemeral=True)
            return False
        return True

    @ui.button(label="🪙 Баланс", style=discord.ButtonStyle.secondary, custom_id="casino_balance")
    async def balance(self, interaction: discord.Interaction, button: ui.Button):
        balance = await self.cog.store.balance(interaction.user.id)
        embed = discord.Embed(title="🪙 Ваш баланс", description=f"**{fmt(balance)}** монет", color=discord.Color.gold())
        embed.set_footer(text="Code by PAVUK")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="🎁 Ежедневный", style=discord.ButtonStyle.success, custom_id="casino_daily")
    async def daily(self, interaction: discord.Interaction, button: ui.Button):
        ok, balance = await self.cog.store.daily(interaction.user.id)
        if ok:
            msg = f"🎁 Вы получили **{fmt(DAILY_REWARD)}** монет!\nБаланс: **{fmt(balance)}**."
        else:
            msg = f"⏳ Ежедневный бонус уже получен. Баланс: **{fmt(balance)}** монет."
        await interaction.response.send_message(msg, ephemeral=True)

    @ui.button(label="🏆 Лидеры", style=discord.ButtonStyle.secondary, custom_id="casino_leaders")
    async def leaders(self, interaction: discord.Interaction, button: ui.Button):
        rows = await self.cog.store.leaderboard(10)
        if not rows:
            await interaction.response.send_message("Пока нет игроков в таблице.", ephemeral=True)
            return
        lines = []
        for index, row in enumerate(rows, 1):
            member = interaction.client.get_user(int(row["user_id"]))
            name = member.display_name if member else f"Игрок {row['user_id']}"
            lines.append(f"**{index}.** {discord.utils.escape_markdown(name)} — **{fmt(int(row['balance']))}** монет")
        embed = discord.Embed(title="🏆 Лидеры казино", description="\n".join(lines), color=discord.Color.gold())
        embed.set_footer(text="Code by PAVUK")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="📜 История", style=discord.ButtonStyle.secondary, custom_id="casino_history")
    async def history(self, interaction: discord.Interaction, button: ui.Button):
        rows = await self.cog.store.history(interaction.user.id)
        if not rows:
            await interaction.response.send_message("История пока пуста.", ephemeral=True)
            return
        lines = []
        for row in rows:
            delta = int(row["delta"])
            sign = "+" if delta > 0 else ""
            lines.append(f"`{row['created_at']}` · **{row['game']}** · ставка {fmt(int(row['bet']))} · {sign}{fmt(delta)} · баланс {fmt(int(row['balance_after']))}")
        embed = discord.Embed(title="📜 История казино", description="\n".join(lines), color=discord.Color.blurple())
        embed.set_footer(text="Code by PAVUK")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="🎰 Слоты", style=discord.ButtonStyle.primary, custom_id="casino_slots")
    async def slots(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SlotsModal())

    @ui.button(label="🪙 Монетка", style=discord.ButtonStyle.primary, custom_id="casino_coin")
    async def coin(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(CoinModal())

    @ui.button(label="🎡 Рулетка", style=discord.ButtonStyle.primary, custom_id="casino_roulette")
    async def roulette(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(RouletteModal())


class Casino(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = CasinoStore()

async def setup(bot: commands.Bot):
    await bot.add_cog(Casino(bot))

async def setup_casino_panel(bot: commands.Bot):
    """Функция для создания или обновления панели казино в канале."""
    from config import CASINO_CHANNEL_ID
    if not CASINO_CHANNEL_ID:
        logger.warning("CASINO_CHANNEL_ID не задан, панель казино не создана.")
        return

    cog = bot.get_cog("Casino")
    if not cog:
        logger.error("Cog Casino не загружен.")
        return

    channel = bot.get_channel(CASINO_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(CASINO_CHANNEL_ID)
        except Exception as e:
            logger.error(f"Не удалось найти канал казино: {e}")
            return

    embed = discord.Embed(
        title="🎰 Добро пожаловать в казино G4S!",
        description=(
            "Нажмите на кнопки ниже, чтобы играть.\n\n"
            f"**Минимальная ставка:** {MIN_BET} монет\n"
            f"**Максимальная ставка:** {fmt(MAX_BET)} монет\n\n"
            "💡 *При первом входе вам начисляется 1000 монет.*"
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text="Code by PAVUK")
    
    view = CasinoView(cog)

    # Ищем старое сообщение, чтобы не спамить
    async for msg in channel.history(limit=20):
        if msg.author == bot.user and msg.embeds and msg.components:
            for row in msg.components:
                for comp in row.children:
                    if hasattr(comp, 'custom_id') and comp.custom_id == "casino_balance":
                        await msg.edit(embed=embed, view=view)
                        logger.info("Панель казино обновлена.")
                        return

    await channel.send(embed=embed, view=view)
    logger.info("Панель казино создана и отправлена.")
