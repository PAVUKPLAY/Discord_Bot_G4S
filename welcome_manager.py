import discord
from discord import ui
import logging
from datetime import datetime
from config import WELCOME_CHANNEL_ID, ORGANIZATION_CHANNEL_ID, GUEST_ROLE_ID, FIGHTER_ROLE_ID
from utils import has_moderator_role

logger = logging.getLogger(__name__)
applications = {}

class ApplyModal(ui.Modal, title='Заявка в отряд G4S'):
    nickname = ui.TextInput(label='Ваш игровой ник', required=True)
    age = ui.TextInput(label='Ваш возраст', required=True)
    experience = ui.TextInput(label='Опыт игры в Arma 3', required=False)

    async def on_submit(self, interaction: discord.Interaction):
        if str(interaction.user.id) in applications:
            await interaction.response.send_message("❌ Вы уже подали заявку.", ephemeral=True); return
        if FIGHTER_ROLE_ID and interaction.guild.get_role(FIGHTER_ROLE_ID) in interaction.user.roles:
            await interaction.response.send_message("✅ Вы уже боец.", ephemeral=True); return

        app_id = f"{int(datetime.now().timestamp())}"
        applications[str(interaction.user.id)] = {
            "id": app_id, "user_id": interaction.user.id, "user_name": interaction.user.display_name,
            "nickname": self.nickname.value, "age": self.age.value,
            "experience": self.experience.value or "Не указан", "status": "pending"
        }

        channel = interaction.guild.get_channel(ORGANIZATION_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message("❌ Канал не настроен.", ephemeral=True); return

        embed = discord.Embed(title="📋 Новая заявка!", description=f"Пользователь **{interaction.user.display_name}** хочет вступить.", color=discord.Color.blue())
        embed.add_field(name="🎮 Ник", value=self.nickname.value, inline=True)
        embed.add_field(name="📅 Возраст", value=self.age.value, inline=True)
        embed.add_field(name="📝 Опыт", value=self.experience.value or "Не указан", inline=False)
        embed.set_footer(text=f"G4S Командование • ID: {app_id} | Code by PAVUK")

        view = ApplicationActions(app_id, interaction.user.id)
        await channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ Заявка отправлена!", ephemeral=True)

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

        await member.add_roles(role)
        current_nick = member.display_name
        if not current_nick.startswith("[G4S]"):
            new_nick = f"[G4S] {current_nick}"
            if len(new_nick) > 32: new_nick = new_nick[:32]
            try: await member.edit(nick=new_nick)
            except Exception: pass

        app["status"] = "accepted"
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
    channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if not channel: return
    if GUEST_ROLE_ID:
        role = member.guild.get_role(GUEST_ROLE_ID)
        if role and role not in member.roles: await member.add_roles(role)

    embed = discord.Embed(
        title=f"👋 Добро пожаловать, {member.display_name}!",
        description="Рады приветствовать тебя на сервере **Group 4 Securicor**!\n\n📌 **Чтобы стать бойцом:**\n1. Ознакомься с правилами.\n2. Нажми **«Подать заявку»** ниже.\n3. Заполни форму.\n\n🛡️ **Ты получил роль `Гость`.**\nУдачи на полях сражений! 💥",
        color=discord.Color.gold()
    )
    embed.set_footer(text="G4S Командование | Code by PAVUK")
    await channel.send(f"{member.mention}", embed=embed, view=ApplyButton())
