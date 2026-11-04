import asyncio
import random
import sqlite3
import os
import time
import logging
from pathlib import Path
import discord
from discord import ui, app_commands
from discord.ext import commands
from discord.errors import HTTPException
from utils import has_moderator_role

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

SHOP_ITEMS = {
    "radio_skip": ("🎫 Пропуск смены радио", 5000, "Позволяет сменить станцию в войсе без голосования (одноразовый)."),
    "daily_boost": ("💎 Бустер ежедневного бонуса", 10000, "Навсегда увеличивает ваш ежедневный бонус на 100 монет."),
    "custom_role": ("🎨 Кастомная роль", 20000, "Бот создаст вам личную роль с выбранным названием и цветом.")
}

def fmt(value: int) -> str: 
    return f"{value:,}".replace(",", " ")

def validate_bet(bet: int):
    if bet < MIN_BET or bet > MAX_BET: 
        raise ValueError(f"Ставка должна быть от {fmt(MIN_BET)} до {fmt(MAX_BET)}.")

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
            con.execute("""CREATE TABLE IF NOT EXISTS casino_users (user_id INTEGER PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 1000, daily_claimed INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0, wagered INTEGER NOT NULL DEFAULT 0, net_profit INTEGER NOT NULL DEFAULT 0)""")
            con.execute("""CREATE TABLE IF NOT EXISTS casino_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, game TEXT NOT NULL, bet INTEGER NOT NULL, delta INTEGER NOT NULL, balance_after INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            con.execute("""CREATE TABLE IF NOT EXISTS casino_inventory (user_id INTEGER NOT NULL, item_id TEXT NOT NULL, amount INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (user_id, item_id))""")
            
            # Таблицы для промокодов
            con.execute("""CREATE TABLE IF NOT EXISTS promo_codes (code TEXT PRIMARY KEY, amount INTEGER NOT NULL, max_uses INTEGER DEFAULT 0, current_uses INTEGER DEFAULT 0, expires_at INTEGER DEFAULT 0)""")
            con.execute("""CREATE TABLE IF NOT EXISTS promo_usages (code TEXT NOT NULL, user_id INTEGER NOT NULL, PRIMARY KEY (code, user_id))""")
            
            try:
                con.execute("ALTER TABLE casino_users ADD COLUMN daily_boost INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

    def _ensure_user(self, con, user_id: int):
        con.execute("INSERT OR IGNORE INTO casino_users(user_id, balance) VALUES (?, ?)", (user_id, STARTING_BALANCE))

    async def balance(self, user_id: int) -> int:
        async with self.lock:
            with self._connect() as con:
                self._ensure_user(con, user_id)
                return int(con.execute("SELECT balance FROM casino_users WHERE user_id=?", (user_id,)).fetchone()["balance"])

    async def daily(self, user_id: int):
        async with self.lock:
            with self._connect() as con:
                self._ensure_user(con, user_id)
                row = con.execute("SELECT balance, daily_claimed, daily_boost FROM casino_users WHERE user_id=?", (user_id,)).fetchone()
                now_day = int(time.time() // 86400)
                if int(row["daily_claimed"]) >= now_day: 
                    return False, int(row["balance"]), 0
                
                boost = row["daily_boost"] or 0
                reward = DAILY_REWARD + (boost * 100)
                
                new_balance = int(row["balance"]) + reward
                con.execute("UPDATE casino_users SET balance=?, daily_claimed=? WHERE user_id=?", (new_balance, now_day, user_id))
                con.execute("INSERT INTO casino_history(user_id, game, bet, delta, balance_after) VALUES (?, 'Ежедневный бонус', 0, ?, ?)", (user_id, reward, new_balance))
                return True, new_balance, reward

    async def play(self, user_id: int, game: str, bet: int, delta: int):
        async with self.lock:
            with self._connect() as con:
                self._ensure_user(con, user_id)
                balance = int(con.execute("SELECT balance FROM casino_users WHERE user_id=?", (user_id,)).fetchone()["balance"])
                if bet < MIN_BET or bet > MAX_BET: raise ValueError(f"Ставка должна быть от {fmt(MIN_BET)} до {fmt(MAX_BET)}.")
                if balance < bet: raise ValueError(f"Недостаточно монет. Баланс: {fmt(balance)}.")
                new_balance = balance + delta
                if new_balance < 0: raise ValueError("Недостаточно монет.")
                won = delta > 0
                con.execute("UPDATE casino_users SET balance=?, wins=wins+?, losses=losses+?, wagered=wagered+?, net_profit=net_profit+? WHERE user_id=?", (new_balance, int(won), int(delta < 0), bet, delta, user_id))
                con.execute("INSERT INTO casino_history(user_id, game, bet, delta, balance_after) VALUES (?, ?, ?, ?, ?)", (user_id, game, bet, delta, new_balance))
                return new_balance

    async def leaderboard(self, limit: int = 10):
        async with self.lock:
            with self._connect() as con:
                return con.execute("SELECT user_id, balance, wins, net_profit FROM casino_users ORDER BY balance DESC LIMIT ?", (limit,)).fetchall()

    async def history(self, user_id: int, limit: int = 5):
        async with self.lock:
            with self._connect() as con:
                return con.execute("SELECT game, bet, delta, balance_after, created_at FROM casino_history WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()

    async def buy_item(self, user_id: int, item_id: str) -> tuple[bool, str]:
        if item_id not in SHOP_ITEMS: return False, "Товар не найден."
        name, price, _ = SHOP_ITEMS[item_id]
        async with self.lock:
            with self._connect() as con:
                self._ensure_user(con, user_id)
                balance = int(con.execute("SELECT balance FROM casino_users WHERE user_id=?", (user_id,)).fetchone()["balance"])
                if balance < price:
                    return False, f"❌ Недостаточно монет. Нужно {fmt(price)}, у вас {fmt(balance)}."
                
                con.execute("UPDATE casino_users SET balance = balance - ? WHERE user_id=?", (price, user_id))
                
                if item_id == "daily_boost":
                    con.execute("UPDATE casino_users SET daily_boost = daily_boost + 1 WHERE user_id=?", (user_id,))
                else:
                    con.execute("INSERT INTO casino_inventory (user_id, item_id, amount) VALUES (?, ?, 1) ON CONFLICT(user_id, item_id) DO UPDATE SET amount = amount + 1", (user_id, item_id))
                
                con.execute("INSERT INTO casino_history(user_id, game, bet, delta, balance_after) VALUES (?, 'Покупка в магазине', 0, ?, ?)", (user_id, -price, balance - price))
                return True, f"✅ Вы успешно купили **{name}** за {fmt(price)} монет!"

    async def get_inventory(self, user_id: int) -> dict:
        async with self.lock:
            with self._connect() as con:
                rows = con.execute("SELECT item_id, amount FROM casino_inventory WHERE user_id=?", (user_id,)).fetchall()
                return {row["item_id"]: row["amount"] for row in rows}

    async def use_item(self, user_id: int, item_id: str) -> bool:
        async with self.lock:
            with self._connect() as con:
                row = con.execute("SELECT amount FROM casino_inventory WHERE user_id=? AND item_id=?", (user_id, item_id)).fetchone()
                if row and row["amount"] > 0:
                    con.execute("UPDATE casino_inventory SET amount = amount - 1 WHERE user_id=? AND item_id=?", (user_id, item_id))
                    return True
                return False

    # === ПРОМОКОДЫ ===
    async def create_promo(self, code: str, amount: int, max_uses: int, hours: float) -> tuple[bool, str]:
        code = code.strip().upper()
        expires_at = int(time.time() + (hours * 3600)) if hours > 0 else 0
        async with self.lock:
            with self._connect() as con:
                try:
                    con.execute(
                        "INSERT INTO promo_codes (code, amount, max_uses, expires_at) VALUES (?, ?, ?, ?)",
                        (code, amount, max_uses, expires_at)
                    )
                    return True, f"✅ Промокод **{code}** на {fmt(amount)} монет успешно создан!"
                except sqlite3.IntegrityError:
                    return False, f"❌ Промокод **{code}** уже существует."

    async def activate_promo(self, code: str, user_id: int) -> tuple[bool, str]:
        code = code.strip().upper()
        now = int(time.time())
        async with self.lock:
            with self._connect() as con:
                row = con.execute("SELECT amount, max_uses, current_uses, expires_at FROM promo_codes WHERE code=?", (code,)).fetchone()
                if not row:
                    return False, "❌ Промокод не найден."
                
                if row["expires_at"] > 0 and now > row["expires_at"]:
                    return False, "❌ Срок действия промокода истек."
                
                if row["max_uses"] > 0 and row["current_uses"] >= row["max_uses"]:
                    return False, "❌ Лимит активаций этого промокода исчерпан."
                
                usage = con.execute("SELECT 1 FROM promo_usages WHERE code=? AND user_id=?", (code, user_id)).fetchone()
                if usage:
                    return False, "❌ Вы уже активировали этот промокод."
                
                con.execute("UPDATE promo_codes SET current_uses = current_uses + 1 WHERE code=?", (code,))
                con.execute("INSERT INTO promo_usages (code, user_id) VALUES (?, ?)", (code, user_id))
                
                self._ensure_user(con, user_id)
                con.execute("UPDATE casino_users SET balance = balance + ? WHERE user_id=?", (row["amount"], user_id))
                
                new_balance = int(con.execute("SELECT balance FROM casino_users WHERE user_id=?", (user_id,)).fetchone()["balance"])
                con.execute("INSERT INTO casino_history(user_id, game, bet, delta, balance_after) VALUES (?, 'Промокод', 0, ?, ?)", (user_id, row["amount"], new_balance))
                
                return True, f"🎉 Промокод активирован! Вы получили **{fmt(row['amount'])}** монет."


# ==================== МОДАЛЬНЫЕ ОКНА ====================

class CreatePromoModal(ui.Modal, title="Создание промокода"):
    code_input = ui.TextInput(label="Промокод", placeholder="Например: G4S2026", required=True, max_length=50)
    amount_input = ui.TextInput(label="Сумма монет", placeholder="Например: 1000", required=True)
    uses_input = ui.TextInput(label="Кол-во активаций (0 - безлимит)", default="0", required=True)
    hours_input = ui.TextInput(label="Время в часах (0 - бессрочно)", default="0", required=True)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value)
            uses = int(self.uses_input.value)
            hours = float(self.hours_input.value)
            
            if amount <= 0: raise ValueError("Сумма должна быть больше 0.")
            if uses < 0 or hours < 0: raise ValueError("Лимиты не могут быть отрицательными.")
            
            await interaction.response.defer(ephemeral=True)
            success, msg = await self.cog.store.create_promo(self.code_input.value, amount, uses, hours)
            await interaction.followup.send(msg, ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Неверный формат ввода. Сумма и лимиты должны быть числами (больше или равны 0).", ephemeral=True)

class PromoModal(ui.Modal, title="Активация промокода"):
    code_input = ui.TextInput(label="Введите промокод", placeholder="Например: G4S2026", required=True, max_length=50)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        success, message = await self.cog.store.activate_promo(self.code_input.value, interaction.user.id)
        await interaction.followup.send(message, ephemeral=True)

class CustomRoleModal(ui.Modal, title="Создание кастомной роли"):
    role_name = ui.TextInput(label="Название роли", placeholder="Например: Кибер-Кот", max_length=32, required=True)
    color_hex = ui.TextInput(label="Цвет (HEX)", placeholder="#FF0000", max_length=7, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            color = discord.Color.from_str(self.color_hex.value)
        except ValueError:
            await interaction.response.send_message("❌ Неверный формат цвета. Используйте HEX (например, #FF0000).", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        
        try:
            role = await interaction.guild.create_role(name=self.role_name.value, color=color)
            await interaction.user.add_roles(role)
            await interaction.followup.send(f"✅ Роль **{role.name}** успешно создана и выдана вам!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ У бота нет прав на создание ролей.", ephemeral=True)
        except HTTPException as e:
            await interaction.followup.send(f"❌ Ошибка Discord: {e}", ephemeral=True)

class ShopSelect(ui.Select):
    def __init__(self, cog):
        self.cog = cog
        options = []
        for item_id, (name, price, desc) in SHOP_ITEMS.items():
            options.append(discord.SelectOption(label=name, value=item_id, description=f"Цена: {fmt(price)} | {desc[:50]}..."))
        super().__init__(placeholder="Выберите товар для покупки...", options=options)

    async def callback(self, interaction: discord.Interaction):
        item_id = self.values[0]
        name, price, _ = SHOP_ITEMS[item_id]
        
        success, msg = await self.cog.store.buy_item(interaction.user.id, item_id)
        
        if success:
            if item_id == "custom_role":
                await interaction.response.send_modal(CustomRoleModal())
                return
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

class ShopView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=180)
        self.add_item(ShopSelect(cog))

# ==================== ОСНОВНАЯ ПАНЕЛЬ ====================

class CasinoModal(ui.Modal):
    def __init__(self, title: str, bet_label: str = "Ставка (в монетах)"):
        super().__init__(title=title)
        self.bet_input = ui.TextInput(label=bet_label, placeholder=f"От {MIN_BET} до {MAX_BET}", required=True)
        self.add_item(self.bet_input)

class SlotsModal(CasinoModal):
    def __init__(self): super().__init__(title="🎰 Слоты")
    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet = int(self.bet_input.value)
            validate_bet(bet)
            symbols = random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=3)
            multiplier = 0
            if symbols[0] == symbols[1] == symbols[2]: multiplier = {"💎": 20, "⭐": 10, "🍉": 5, "🍇": 4, "🍋": 3, "🍒": 3}[symbols[0]]
            elif len(set(symbols)) == 2: multiplier = 0.5
            payout = int(bet * multiplier)
            delta = payout - bet
            cog = interaction.client.get_cog("Casino")
            balance = await cog.store.play(interaction.user.id, "Слоты", bet, delta)
            result = f"Выигрыш: **{fmt(payout)}**" if delta > 0 else ("Возврат части ставки." if delta == -bet // 2 else "Ставка проиграна.")
            embed = discord.Embed(title="🎰 Слоты", description=f"┏ {' │ '.join(symbols)} ┓\n\n{result}", color=discord.Color.green() if delta > 0 else discord.Color.red())
            embed.add_field(name="Ставка", value=fmt(bet)); embed.add_field(name="Изменение", value=f"{'+' if delta > 0 else ''}{fmt(delta)}"); embed.add_field(name="Баланс", value=fmt(balance))
            embed.set_footer(text="Code by PAVUK")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except ValueError: await interaction.response.send_message("❌ Введите корректную ставку.", ephemeral=True)

class CoinModal(ui.Modal):
    def __init__(self):
        super().__init__(title="🪙 Монетка")
        self.bet_input = ui.TextInput(label="Ставка (в монетах)", placeholder=f"От {MIN_BET} до {MAX_BET}", required=True)
        self.choice_input = ui.TextInput(label="Орёл или Решка?", placeholder="Напишите: орёл или решка", required=True)
        self.add_item(self.bet_input); self.add_item(self.choice_input)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet = int(self.bet_input.value); validate_bet(bet)
            choice = self.choice_input.value.strip().lower()
            if choice not in ("орёл", "орел", "решка"):
                await interaction.response.send_message("❌ Напишите «орёл» или «решка».", ephemeral=True); return
            if choice == "орел": choice = "орёл"
            result = random.choice(["орёл", "решка"])
            won = result == choice; delta = bet if won else -bet
            cog = interaction.client.get_cog("Casino")
            balance = await cog.store.play(interaction.user.id, "Монетка", bet, delta)
            embed = discord.Embed(title="🪙 Монетка", description=f"Выпало: **{result.capitalize()}**\n" + (f"🎉 Вы выиграли **{fmt(bet)}**!" if won else "Увы, ставка проиграна."), color=discord.Color.green() if won else discord.Color.red())
            embed.add_field(name="Баланс", value=fmt(balance)); embed.set_footer(text="Code by PAVUK")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except ValueError: await interaction.response.send_message("❌ Введите корректную ставку.", ephemeral=True)

class RouletteModal(ui.Modal):
    def __init__(self):
        super().__init__(title="🎡 Рулетка")
        self.bet_input = ui.TextInput(label="Ставка (в монетах)", placeholder=f"От {MIN_BET} до {MAX_BET}", required=True)
        self.type_input = ui.TextInput(label="На что ставим?", placeholder="Красное, Чёрное, Чётное, Нечётное или Число", required=True)
        self.number_input = ui.TextInput(label="Число (если ставите на число)", placeholder="От 0 до 36", required=False)
        self.add_item(self.bet_input); self.add_item(self.type_input); self.add_item(self.number_input)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            bet = int(self.bet_input.value); validate_bet(bet)
            t = self.type_input.value.strip().lower()
            red_numbers = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
            spin = random.randint(0, 36)
            if t in ("число", "числа"):
                if not self.number_input.value: await interaction.response.send_message("❌ Укажите число от 0 до 36.", ephemeral=True); return
                num = int(self.number_input.value)
                if not (0 <= num <= 36): raise ValueError()
                won = spin == num; multiplier = 36
            elif spin == 0: won, multiplier = False, 2
            elif t in ("красное", "красный"): won, multiplier = spin in red_numbers, 2
            elif t in ("чёрное", "черное", "черный", "чёрный"): won, multiplier = spin not in red_numbers, 2
            elif t in ("чётное", "четное", "чёт", "чет"): won, multiplier = spin % 2 == 0, 2
            elif t in ("нечётное", "нечетное", "нечёт", "нечет"): won, multiplier = spin % 2 == 1, 2
            else: await interaction.response.send_message("❌ Неверный тип ставки.", ephemeral=True); return
            payout = bet * multiplier if won else 0; delta = payout - bet
            cog = interaction.client.get_cog("Casino")
            balance = await cog.store.play(interaction.user.id, "Рулетка", bet, delta)
            color = discord.Color.dark_grey() if spin == 0 else (discord.Color.red() if spin in red_numbers else discord.Color.from_rgb(25, 25, 25))
            embed = discord.Embed(title="🎡 Рулетка G4S", description=f"Выпало: **{spin}** {'🟢' if spin == 0 else ('🔴' if spin in red_numbers else '⚫')}\n" + (f"🎉 Выигрыш: **{fmt(payout)}** монет" if won else "Ставка проиграна."), color=color)
            embed.add_field(name="Ставка", value=f"{fmt(bet)} на {t.capitalize()}"); embed.add_field(name="Баланс", value=fmt(balance)); embed.set_footer(text="Code by PAVUK")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except ValueError: await interaction.response.send_message("❌ Проверьте введенные данные.", ephemeral=True)

class CasinoView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        from config import CASINO_CHANNEL_ID
        if CASINO_CHANNEL_ID and interaction.channel_id != CASINO_CHANNEL_ID:
            await interaction.response.send_message(f"❌ Казино работает только в канале <#{CASINO_CHANNEL_ID}>.", ephemeral=True); return False
        return True
    @ui.button(label="🪙 Баланс", style=discord.ButtonStyle.secondary, custom_id="casino_balance")
    async def balance(self, interaction: discord.Interaction, button: ui.Button):
        balance = await self.cog.store.balance(interaction.user.id)
        embed = discord.Embed(title="🪙 Ваш баланс", description=f"**{fmt(balance)}** монет", color=discord.Color.gold())
        embed.set_footer(text="Code by PAVUK"); await interaction.response.send_message(embed=embed, ephemeral=True)
    @ui.button(label="🎁 Ежедневный", style=discord.ButtonStyle.success, custom_id="casino_daily")
    async def daily(self, interaction: discord.Interaction, button: ui.Button):
        ok, balance, reward = await self.cog.store.daily(interaction.user.id)
        if ok:
            msg = f"🎁 Вы получили **{fmt(reward)}** монет!\nБаланс: **{fmt(balance)}**."
        else:
            msg = f"⏳ Ежедневный бонус уже получен. Баланс: **{fmt(balance)}**."
        await interaction.response.send_message(msg, ephemeral=True)
    @ui.button(label="🎟️ Промокод", style=discord.ButtonStyle.success, custom_id="casino_promo")
    async def promo(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(PromoModal(self.cog))
    @ui.button(label="🛒 Магазин", style=discord.ButtonStyle.primary, custom_id="casino_shop")
    async def shop(self, interaction: discord.Interaction, button: ui.Button):
        balance = await self.cog.store.balance(interaction.user.id)
        embed = discord.Embed(title="🛒 Магазин казино", description=f"Ваш баланс: **{fmt(balance)}** монет.\nВыберите товар в меню ниже:", color=discord.Color.gold())
        embed.set_footer(text="Code by PAVUK")
        await interaction.response.send_message(embed=embed, view=ShopView(self.cog), ephemeral=True)
    @ui.button(label="🏆 Лидеры", style=discord.ButtonStyle.secondary, custom_id="casino_leaders")
    async def leaders(self, interaction: discord.Interaction, button: ui.Button):
        rows = await self.cog.store.leaderboard(10)
        if not rows: await interaction.response.send_message("Пока нет игроков.", ephemeral=True); return
        lines = []
        for i, r in enumerate(rows, 1):
            u = interaction.client.get_user(int(r['user_id']))
            name = u.display_name if u else f"Игрок {r['user_id']}"
            lines.append(f"**{i}.** {discord.utils.escape_markdown(name)} — **{fmt(int(r['balance']))}**")
        embed = discord.Embed(title="🏆 Лидеры казино", description="\n".join(lines), color=discord.Color.gold())
        embed.set_footer(text="Code by PAVUK"); await interaction.response.send_message(embed=embed, ephemeral=True)
    @ui.button(label="📜 История", style=discord.ButtonStyle.secondary, custom_id="casino_history")
    async def history(self, interaction: discord.Interaction, button: ui.Button):
        rows = await self.cog.store.history(interaction.user.id)
        if not rows: await interaction.response.send_message("История пуста.", ephemeral=True); return
        lines = [f"`{r['created_at']}` · **{r['game']}** · ставка {fmt(int(r['bet']))} · {'+' if int(r['delta'])>0 else ''}{fmt(int(r['delta']))} · баланс {fmt(int(r['balance_after']))}" for r in rows]
        embed = discord.Embed(title="📜 История казино", description="\n".join(lines), color=discord.Color.blurple())
        embed.set_footer(text="Code by PAVUK"); await interaction.response.send_message(embed=embed, ephemeral=True)
    @ui.button(label="🎰 Слоты", style=discord.ButtonStyle.primary, custom_id="casino_slots")
    async def slots(self, interaction: discord.Interaction, button: ui.Button): await interaction.response.send_modal(SlotsModal())
    @ui.button(label="🪙 Монетка", style=discord.ButtonStyle.primary, custom_id="casino_coin")
    async def coin(self, interaction: discord.Interaction, button: ui.Button): await interaction.response.send_modal(CoinModal())
    @ui.button(label="🎡 Рулетка", style=discord.ButtonStyle.primary, custom_id="casino_roulette")
    async def roulette(self, interaction: discord.Interaction, button: ui.Button): await interaction.response.send_modal(RouletteModal())


class Casino(commands.Cog):
    def __init__(self, bot: commands.Bot): 
        self.bot = bot
        self.store = CasinoStore()

    @app_commands.command(name="promo", description="Создать промокод в казино (только для модераторов)")
    async def promo_cmd(self, interaction: discord.Interaction):
        if not has_moderator_role(interaction.user):
            await interaction.response.send_message("❌ У вас недостаточно прав.", ephemeral=True)
            return
            
        await interaction.response.send_message("Нажмите на кнопку ниже, чтобы открыть форму создания промокода.", view=PromoCreateView(self), ephemeral=True)

class PromoCreateView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=120)
        self.cog = cog

    @ui.button(label="📝 Создать промокод", style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(CreatePromoModal(self.cog))

async def setup(bot: commands.Bot): 
    await bot.add_cog(Casino(bot))

async def setup_casino_panel(bot: commands.Bot):
    from config import CASINO_CHANNEL_ID
    if not CASINO_CHANNEL_ID: return
    cog = bot.get_cog("Casino")
    if not cog: return
    channel = bot.get_channel(CASINO_CHANNEL_ID)
    if not channel:
        try: channel = await bot.fetch_channel(CASINO_CHANNEL_ID)
        except: return
    embed = discord.Embed(title="🎰 Добро пожаловать в казино G4S!", description=f"Нажмите на кнопки ниже, чтобы играть.\n\n**Мин. ставка:** {MIN_BET}\n**Макс. ставка:** {fmt(MAX_BET)}\n\n💡 *При первом входе 1000 монет.*\n🔒 *Результаты видны только вам.*", color=discord.Color.gold())
    embed.set_footer(text="Code by PAVUK"); view = CasinoView(cog)
    async for msg in channel.history(limit=20):
        if msg.author == bot.user and msg.embeds and msg.components:
            for row in msg.components:
                for comp in row.children:
                    if hasattr(comp, 'custom_id') and comp.custom_id == "casino_balance":
                        await msg.edit(embed=embed, view=view); return
    await channel.send(embed=embed, view=view)
