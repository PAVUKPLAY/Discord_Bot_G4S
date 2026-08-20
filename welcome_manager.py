import discord
from discord import ui
import logging
from datetime import datetime
from config import WELCOME_CHANNEL_ID, ORGANIZATION_CHANNEL_ID, GUEST_ROLE_ID, FIGHTER_ROLE_ID
from utils import has_moderator_role

logger = logging.getLogger(__name__)

applications = {}

class ApplyModal(ui.Modal, title='Заявка в отряд G4S'):
    nickname = ui.TextInput(label='Ваш игровой ник', placeholder='Введите свой ник в Arma 3', required=True)
    age = ui.TextInput(label='Ваш возраст', placeholder='Например: 25', required=True)
    experience = ui.TextInput(label='Опыт игры в Arma 3', placeholder='Кратко опишите свой опыт', required=False)

    async def on_submit(self, interaction: discord.Interaction):
        if str(interaction.user.id) in applications:
            await interaction.response.send_message("❌ Вы уже подали заявку. Ожидайте ответа модерации.", ephemeral=True)
            return

        if FIGHTER_ROLE_ID and interaction.guild.get_role(FIGHTER_ROLE_ID) in interaction.user.roles:
            await interaction.response.send_message("✅ Вы уже являетесь бойцом отряда!", ephemeral=True)
            return

        app_id = f"{int(datetime.now().timestamp())}"
        applications[str(interaction.user.id)] = {
            "id": app_id,
            "user_id": interaction.user.id,
            "user_name": interaction.user.display_name,
            "nickname": self.nickname.value,
            "age": self.age.value,
            "experience": self.experience.value or "Не указан",
            "status": "pending"
        }

        channel = interaction.guild.get_channel(ORGANIZATION_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message("❌ Канал для заявок не настроен. Обратитесь к администратору.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📋 Новая заявка в отряд!",
            description=f"Пользователь **{interaction.user.display_name}** хочет вступить в отряд.",
            color=discord.Color.blue()
        )
        embed.add_field(name="🎮 Игровой ник", value=self.nickname.value, inline=True)
        embed.add_field(name="📅 Возраст", value=self.age.value, inline=True)
        embed.add_field(name="📝 Опыт", value=self.experience.value or "Не указан", inline=False)
        embed.set_footer(text=f"G4S Командование • ID: {app_id}")

        view = ApplicationActions(app_id, interaction.user.id)
        await channel.send(embed=embed, view=view)

        await interaction.response.send_message("✅ Ваша заявка отправлена! Ожидайте решения модерации.", ephemeral=True)
        logger.info(f"Пользователь {interaction.user} подал заявку в отряд (ID: {app_id})")

class ApplicationActions(ui.View):
    def __init__(self, app_id, user_id):
        super().__init__(timeout=None)
        self.app_id = app_id
        self.user_id = user_id

    @ui.button(label='✅ Принять', style=discord.ButtonStyle.green, custom_id='accept_app')
    async def accept_button(self, interaction: discord.Interaction, button: ui.Button):
        if not has_moderator_role(interaction.user):
            await interaction.response.send_message("❌ У вас недостаточно прав.", ephemeral=True)
            return

        app = applications.get(str(self.user_id))
        if not app or app["status"] != "pending":
            await interaction.response.send_message("❌ Заявка уже обработана.", ephemeral=True)
            return

        member = interaction.guild.get_member(self.user_id)
        if not member:
            await interaction.response.send_message("❌ Пользователь не найден на сервере.", ephemeral=True)
            return

        role = interaction.guild.get_role(FIGHTER_ROLE_ID)
        if not role:
            await interaction.response.send_message("❌ Роль бойца не настроена. Обратитесь к администратору.", ephemeral=True)
            return

        await member.add_roles(role)
        app["status"] = "accepted"
        logger.info(f"Заявка {self.app_id} принята модератором {interaction.user}")

        await interaction.message.delete()
        await interaction.response.send_message(f"✅ Заявка принята! Пользователь {member.display_name} получил роль бойца.", ephemeral=True)

        try:
            await member.send(f"🎉 Поздравляем! Ваша заявка в отряд **принята**! Добро пожаловать в ряды бойцов G4S!")
        except:
            pass

    @ui.button(label='❌ Отказать', style=discord.ButtonStyle.red, custom_id='reject_app')
    async def reject_button(self, interaction: discord.Interaction, button: ui.Button):
        if not has_moderator_role(interaction.user):
            await interaction.response.send_message("❌ У вас недостаточно прав.", ephemeral=True)
            return

        app = applications.get(str(self.user_id))
        if not app or app["status"] != "pending":
            await interaction.response.send_message("❌ Заявка уже обработана.", ephemeral=True)
            return

        app["status"] = "rejected"
        logger.info(f"Заявка {self.app_id} отклонена модератором {interaction.user}")

        await interaction.message.delete()
        await interaction.response.send_message("❌ Заявка отклонена.", ephemeral=True)

        member = interaction.guild.get_member(self.user_id)
        if member:
            try:
                await member.send("😔 Ваша заявка в отряд **отклонена** модерацией. Если у вас есть вопросы, обратитесь к администрации.")
            except:
                pass

class ApplyButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label='📝 Подать заявку', style=discord.ButtonStyle.primary, custom_id='apply_button')
    async def apply_button(self, interaction: discord.Interaction, button: ui.Button):
        if FIGHTER_ROLE_ID and interaction.guild.get_role(FIGHTER_ROLE_ID) in interaction.user.roles:
            await interaction.response.send_message("✅ Вы уже являетесь бойцом отряда!", ephemeral=True)
            return

        if str(interaction.user.id) in applications:
            await interaction.response.send_message("❌ Вы уже подали заявку. Ожидайте ответа модерации.", ephemeral=True)
            return

        modal = ApplyModal()
        await interaction.response.send_modal(modal)

async def send_welcome_message(member):
    logger.info(f"Обработка входа участника {member.display_name} (ID: {member.id})")

    channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if not channel:
        logger.warning(f"WELCOME_CHANNEL_ID={WELCOME_CHANNEL_ID} не найден")
        return

    if GUEST_ROLE_ID:
        role = member.guild.get_role(GUEST_ROLE_ID)
        if role:
            if role not in member.roles:
                await member.add_roles(role)
                logger.info(f"Пользователю {member} выдана роль гостя")
            else:
                logger.info(f"Роль гостя уже была у {member}")
        else:
            logger.warning(f"Роль гостя с ID {GUEST_ROLE_ID} не найдена")
    else:
        logger.warning("GUEST_ROLE_ID не задан")

    embed = discord.Embed(
        title=f"👋 Добро пожаловать, {member.display_name}!",
        description=(
            "Рады приветствовать тебя на сервере **Group 4 Securicor**!\n\n"
            "📌 **Чтобы стать полноценным бойцом отряда:**\n"
            "1. Ознакомься с правилами в канале `#📜-правила`.\n"
            "2. Нажми на кнопку **«Подать заявку»** ниже.\n"
            "3. Заполни форму – модерация рассмотрит твою заявку.\n\n"
            "🛡️ **Ты получил роль `Гость`.** После принятия заявки ты станешь бойцом отряда!\n"
            "Удачи на полях сражений! 💥"
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text="G4S Командование")
    view = ApplyButton()
    await channel.send(f"{member.mention}", embed=embed, view=view)
    logger.info(f"Приветствие отправлено для {member.display_name}")
