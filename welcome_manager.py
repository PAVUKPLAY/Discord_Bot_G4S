import discord
from discord import ui
import logging
import json
import os
import tempfile
from datetime import datetime
from config import WELCOME_CHANNEL_ID, ORGANIZATION_CHANNEL_ID, GUEST_ROLE_ID, FIGHTER_ROLE_ID
from utils import has_moderator_role

logger = logging.getLogger(__name__)
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
APPLICATIONS_FILE = os.path.join(DATA_DIR, "applications.json")
try:
    with open(APPLICATIONS_FILE, "r", encoding="utf-8") as _file:
        _loaded = json.load(_file)
    applications = _loaded if isinstance(_loaded, dict) else {}
except FileNotFoundError:
    applications = {}
except (OSError, json.JSONDecodeError) as exc:
    logger.error(f"Не удалось загрузить заявки: {exc}")
    applications = {}

pending_submissions = set()


def save_applications():
    os.makedirs(DATA_DIR, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="applications_", suffix=".tmp", dir=DATA_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(applications, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, APPLICATIONS_FILE)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def register_pending_application_views(bot):
    for app in applications.values():
        if app.get("status") != "pending" or not app.get("message_id"):
            continue
        try:
            bot.add_view(
                ApplicationActions(str(app["id"]), int(app["user_id"])),
                message_id=int(app["message_id"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(f"Не удалось восстановить кнопку заявки: {exc}")

class ApplyModal(ui.Modal, title='Заявка в отряд G4S'):
    nickname = ui.TextInput(label='Ваш игровой ник', required=True)
    age = ui.TextInput(label='Ваш возраст', required=True)
    experience = ui.TextInput(label='Опыт игры в Arma 3', required=False)

    async def on_submit(self, interaction: discord.Interaction):
        user_key = str(interaction.user.id)
        if user_key in applications or user_key in pending_submissions:
            await interaction.response.send_message("❌ Вы уже подали заявку.", ephemeral=True); return
        if FIGHTER_ROLE_ID and interaction.guild.get_role(FIGHTER_ROLE_ID) in interaction.user.roles:
            await interaction.response.send_message("✅ Вы уже боец.", ephemeral=True); return

        pending_submissions.add(user_key)
        message = None
        try:
            channel = interaction.guild.get_channel(ORGANIZATION_CHANNEL_ID) if ORGANIZATION_CHANNEL_ID else None
            if not channel and ORGANIZATION_CHANNEL_ID:
                try:
                    channel = await interaction.guild.fetch_channel(ORGANIZATION_CHANNEL_ID)
                except discord.HTTPException:
                    channel = None
            if not channel:
                await interaction.response.send_message("❌ Канал заявок не настроен или недоступен.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            app_id = f"{int(datetime.now().timestamp())}-{interaction.user.id}"
            app = {
                "id": app_id, "user_id": interaction.user.id, "user_name": interaction.user.display_name,
                "nickname": self.nickname.value, "age": self.age.value,
                "experience": self.experience.value or "Не указан", "status": "pending"
            }
            embed = discord.Embed(title="📋 Новая заявка!", description=f"Пользователь **{interaction.user.display_name}** хочет вступить.", color=discord.Color.blue())
            embed.add_field(name="🎮 Ник", value=self.nickname.value, inline=True)
            embed.add_field(name="📅 Возраст", value=self.age.value, inline=True)
            embed.add_field(name="📝 Опыт", value=self.experience.value or "Не указан", inline=False)
            embed.set_footer(text=f"G4S Командование • ID: {app_id} | Code by PAVUK")

            message = await channel.send(embed=embed, view=ApplicationActions(app_id, interaction.user.id))
            app["message_id"] = message.id
            applications[user_key] = app
            save_applications()
            try:
                await interaction.followup.send("✅ Заявка отправлена!", ephemeral=True)
            except discord.HTTPException:
                logger.warning("Заявка сохранена, но подтверждение пользователю отправить не удалось.")
        except discord.HTTPException:
            logger.exception("Не удалось отправить заявку в Discord.")
            if message:
                try: await message.delete()
                except discord.HTTPException: logger.warning("Не удалось удалить несохранённую заявку.")
            if interaction.response.is_done():
                await interaction.followup.send("❌ Не удалось отправить заявку. Попробуйте позже.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Не удалось отправить заявку. Попробуйте позже.", ephemeral=True)
        except OSError:
            logger.exception("Не удалось сохранить заявку на диск.")
            applications.pop(user_key, None)
            if message:
                try: await message.delete()
                except discord.HTTPException: logger.warning("Не удалось удалить заявку, которую не удалось сохранить.")
            if interaction.response.is_done():
                await interaction.followup.send("❌ Не удалось сохранить заявку. Попробуйте позже.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Не удалось сохранить заявку. Попробуйте позже.", ephemeral=True)
        finally:
            pending_submissions.discard(user_key)

class ApplicationActions(ui.View):
    def __init__(self, app_id, user_id):
        super().__init__(timeout=None)
        self.app_id = app_id
        self.user_id = user_id

    @ui.button(label='✅ Принять', style=discord.ButtonStyle.green, custom_id='accept_app')
    async def accept_button(self, interaction: discord.Interaction, button: ui.Button):
        if not has_moderator_role(interaction.user):
            await interaction.response.send_message("❌ Нет прав.", ephemeral=True); return
        app = applications.get(str(self.user_id))
        if not app or app["status"] != "pending":
            await interaction.response.send_message("❌ Заявка обработана.", ephemeral=True); return

        member = interaction.guild.get_member(self.user_id)
        role = interaction.guild.get_role(FIGHTER_ROLE_ID)
        if not member or not role:
            await interaction.response.send_message("❌ Ошибка.", ephemeral=True); return

        try:
            await member.add_roles(role)
        except discord.HTTPException:
            logger.exception("Не удалось выдать роль участнику по заявке.")
            await interaction.response.send_message("❌ Не удалось выдать роль. Проверьте права бота и попробуйте снова.", ephemeral=True)
            return
        current_nick = member.display_name
        if not current_nick.startswith("[G4S]"):
            new_nick = f"[G4S] {current_nick}"
            if len(new_nick) > 32: new_nick = new_nick[:32]
            try: await member.edit(nick=new_nick)
            except discord.HTTPException: logger.warning("Роль выдана, но ник участника изменить не удалось.")

        app["status"] = "accepted"
        save_applications()
        await interaction.message.delete()
        await interaction.response.send_message(f"✅ Заявка принята!", ephemeral=True)
        try: await member.send(f"🎉 Поздравляем! Ваша заявка в отряд **принята**!")
        except: pass

    @ui.button(label='❌ Отказать', style=discord.ButtonStyle.red, custom_id='reject_app')
    async def reject_button(self, interaction: discord.Interaction, button: ui.Button):
        if not has_moderator_role(interaction.user):
            await interaction.response.send_message("❌ Нет прав.", ephemeral=True); return
        app = applications.get(str(self.user_id))
        if not app or app["status"] != "pending":
            await interaction.response.send_message("❌ Заявка обработана.", ephemeral=True); return

        app["status"] = "rejected"
        save_applications()
        await interaction.message.delete()
        await interaction.response.send_message("❌ Заявка отклонена.", ephemeral=True)
        member = interaction.guild.get_member(self.user_id)
        if member:
            try: await member.send("😔 Ваша заявка отклонена.")
            except: pass

class ApplyButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label='📝 Подать заявку', style=discord.ButtonStyle.primary, custom_id='apply_button')
    async def apply_button(self, interaction: discord.Interaction, button: ui.Button):
        if FIGHTER_ROLE_ID and interaction.guild.get_role(FIGHTER_ROLE_ID) in interaction.user.roles:
            await interaction.response.send_message("✅ Вы уже боец.", ephemeral=True); return
        if str(interaction.user.id) in applications:
            await interaction.response.send_message("❌ Вы уже подали заявку.", ephemeral=True); return
        await interaction.response.send_modal(ApplyModal())

async def send_welcome_message(member):
    if not WELCOME_CHANNEL_ID:
        return
    channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if not channel:
        try:
            channel = await member.guild.fetch_channel(WELCOME_CHANNEL_ID)
        except discord.HTTPException:
            logger.exception("Не удалось получить канал приветствий.")
            return
    if not channel: return
    if GUEST_ROLE_ID:
        role = member.guild.get_role(GUEST_ROLE_ID)
        if role and role not in member.roles:
            try:
                await member.add_roles(role)
            except discord.HTTPException:
                logger.exception("Не удалось выдать гостевую роль; приветствие всё равно будет отправлено.")

    embed = discord.Embed(
        title=f"👋 Добро пожаловать, {member.display_name}!",
        description="Рады приветствовать тебя на сервере **Group 4 Securicor**!\n\n📌 **Чтобы стать бойцом:**\n1. Ознакомься с правилами.\n2. Нажми **«Подать заявку»** ниже.\n3. Заполни форму.\n\n🛡️ **Ты получил роль `Гость`.**\nУдачи на полях сражений! 💥",
        color=discord.Color.gold()
    )
    embed.set_footer(text="G4S Командование | Code by PAVUK")
    await channel.send(f"{member.mention}", embed=embed, view=ApplyButton())
