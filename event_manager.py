import discord
from discord import ui
import re
from datetime import datetime
import json
import os
import asyncio
import logging
from config import EVENT_CHANNEL_ID, ANNOUNCE_CHANNEL_ID, PING_EVERYONE
from toggle_manager import get_status, set_status
from utils import has_moderator_role

logger = logging.getLogger(__name__)

DATA_FILE = "events_data.json"

def load_events():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                for eid, ev in data.items():
                    ev['participants'] = set(ev['participants'])
                    ev['non_participants'] = set(ev['non_participants'])
                logger.info(f"Загружено {len(data)} событий")
                return data
            except Exception as e:
                logger.error(f"Ошибка загрузки событий: {e}")
                return {}
    return {}

def save_events(events):
    data = {}
    for eid, ev in events.items():
        data[eid] = ev.copy()
        data[eid]['participants'] = list(ev['participants'])
        data[eid]['non_participants'] = list(ev['non_participants'])
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

events = load_events()

async def update_event_embed(message, event_id):
    event = events.get(event_id)
    if not event:
        logger.warning(f"Попытка обновить несуществующее событие {event_id}")
        return

    embed = discord.Embed(
        title=f"📅 {event['title']}",
        description=f"**Дата:** {event['date']}\n**Время:** {event['time']} (МСК)\n\n"
                    f"**Ставьте реакции:**\n✅ – буду участвовать\n❌ – не смогу",
        color=discord.Color.gold()
    )

    guild = message.guild
    participants = []
    for uid in event['participants']:
        user = guild.get_member(uid)
        if user:
            participants.append(user.display_name)
    non_participants = []
    for uid in event['non_participants']:
        user = guild.get_member(uid)
        if user:
            non_participants.append(user.display_name)

    embed.add_field(
        name=f"✅ Участники ({len(participants)})",
        value="\n".join(participants) if participants else "Пока никого",
        inline=True
    )
    embed.add_field(
        name=f"❌ Не смогут ({len(non_participants)})",
        value="\n".join(non_participants) if non_participants else "Пока никого",
        inline=True
    )
    embed.set_footer(text=f"ID события: {event_id}")

    await message.edit(embed=embed)
    logger.debug(f"Обновлён embed события {event_id}")

class CreateEventModal(ui.Modal, title='Создание смежки'):
    title_input = ui.TextInput(label='Название смежки', placeholder='Например: Отрядная операция', default='Отрядная смежка')
    date_input = ui.TextInput(label='Дата (ДД.ММ.ГГГГ)', placeholder='25.12.2025')
    time_input = ui.TextInput(label='Время (ЧЧ:ММ) по МСК', placeholder='19:00')

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if not ANNOUNCE_CHANNEL_ID:
                await interaction.response.send_message('❌ Канал для объявлений не настроен.', ephemeral=True)
                logger.error("Попытка создать смежку без ANNOUNCE_CHANNEL_ID")
                return
            if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', self.date_input.value):
                await interaction.response.send_message('❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ', ephemeral=True)
                return
            if not re.match(r'^\d{2}:\d{2}$', self.time_input.value):
                await interaction.response.send_message('❌ Неверный формат времени. Используйте ЧЧ:ММ', ephemeral=True)
                return
            try:
                event_datetime = datetime.strptime(f"{self.date_input.value} {self.time_input.value}", "%d.%m.%Y %H:%M")
            except ValueError:
                await interaction.response.send_message('❌ Некорректная дата или время.', ephemeral=True)
                return

            event_id = f"{int(datetime.now().timestamp())}"
            events[event_id] = {
                'title': self.title_input.value,
                'date': self.date_input.value,
                'time': self.time_input.value,
                'datetime': event_datetime.isoformat(),
                'participants': set(),
                'non_participants': set(),
                'message_id': None,
                'channel_id': ANNOUNCE_CHANNEL_ID,
                'reminded': False
            }
            save_events(events)

            embed = discord.Embed(
                title=f"📅 {self.title_input.value}",
                description=f"**Дата:** {self.date_input.value}\n**Время:** {self.time_input.value} (МСК)\n\n"
                            f"**Ставьте реакции:**\n✅ – буду участвовать\n❌ – не смогу",
                color=discord.Color.gold()
            )
            embed.add_field(name="✅ Участники", value="Пока никого", inline=True)
            embed.add_field(name="❌ Не смогут", value="Пока никого", inline=True)
            embed.set_footer(text=f"ID события: {event_id}")

            channel = interaction.guild.get_channel(ANNOUNCE_CHANNEL_ID)
            if not channel:
                await interaction.response.send_message('❌ Канал объявлений не найден.', ephemeral=True)
                logger.error(f"Канал {ANNOUNCE_CHANNEL_ID} не найден для события {event_id}")
                return

            content = "@everyone" if PING_EVERYONE else None
            msg = await channel.send(content=content, embed=embed)
            events[event_id]['message_id'] = msg.id
            save_events(events)

            await msg.add_reaction('✅')
            await msg.add_reaction('❌')

            await interaction.response.send_message(f'✅ Смежка создана! Объявление отправлено в канал {channel.mention}', ephemeral=True)
            logger.info(f"Создано событие {event_id} пользователем {interaction.user} (дата {self.date_input.value} {self.time_input.value})")
        except Exception as e:
            logger.error(f"Ошибка в on_submit: {e}")
            await interaction.response.send_message(f'❌ Произошла ошибка: {e}', ephemeral=True)

class CreateEventButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label='➕ Создать смежку', style=discord.ButtonStyle.primary, custom_id='create_event_button')
    async def create_button(self, interaction: discord.Interaction, button: ui.Button):
        if not has_moderator_role(interaction.user):
            await interaction.response.send_message("❌ У вас недостаточно прав для создания смежки.", ephemeral=True)
            logger.warning(f"Пользователь {interaction.user} пытался создать смежку без прав")
            return
        try:
            logger.info(f"Нажата кнопка создания смежки от {interaction.user.display_name}")
            modal = CreateEventModal()
            await interaction.response.send_modal(modal)
            logger.debug("Модальное окно отправлено успешно")
        except Exception as e:
            logger.error(f"Ошибка при создании модального окна: {e}")
            try:
                await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)
            except discord.errors.InteractionResponded:
                await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

async def setup_event_button(bot):
    if not EVENT_CHANNEL_ID:
        logger.warning("EVENT_CHANNEL_ID не задан. Кнопка не создана.")
        return

    channel = bot.get_channel(EVENT_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(EVENT_CHANNEL_ID)
        except Exception as e:
            logger.error(f"Не удалось найти канал с ID {EVENT_CHANNEL_ID}: {e}")
            return

    logger.info(f"Проверяем канал {channel.name} (ID: {channel.id}) на наличие кнопки...")

    found = False
    async for msg in channel.history(limit=30):
        if msg.author == bot.user and msg.embeds:
            for row in msg.components:
                for comp in row.children:
                    if hasattr(comp, 'custom_id') and comp.custom_id == 'create_event_button':
                        found = True
                        logger.info(f"Найдено существующее сообщение с кнопкой (ID: {msg.id})")
                        break
                if found:
                    break
        if found:
            break

    if found:
        return

    logger.info("Отправляем новое сообщение с кнопкой...")
    embed = discord.Embed(
        title="📢 Создание смежки",
        description="Нажмите на кнопку ниже, чтобы создать новое событие для отряда.",
        color=discord.Color.blue()
    )
    view = CreateEventButton()
    await channel.send(embed=embed, view=view)
    logger.info("Постоянная кнопка 'Создать смежку' размещена.")

async def cleanup_event_button(bot):
    if not EVENT_CHANNEL_ID:
        logger.warning("EVENT_CHANNEL_ID не задан. Пропускаем очистку.")
        return
    channel = bot.get_channel(EVENT_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(EVENT_CHANNEL_ID)
        except Exception as e:
            logger.error(f"Не удалось найти канал с ID {EVENT_CHANNEL_ID}: {e}")
            return

    logger.info("Удаляем старые сообщения с кнопкой...")
    async for msg in channel.history(limit=100):
        if msg.author == bot.user and msg.components:
            for row in msg.components:
                for comp in row.children:
                    if hasattr(comp, 'custom_id') and comp.custom_id == 'create_event_button':
                        await msg.delete()
                        logger.info(f"Удалено сообщение {msg.id}")
                        break

    await setup_event_button(bot)

async def reminder_task(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now()
        for eid, event in list(events.items()):
            if event.get('reminded', False):
                continue
            event_dt = datetime.fromisoformat(event['datetime'])
            delta = event_dt - now
            if 23*3600 <= delta.total_seconds() <= 25*3600:
                channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
                if channel:
                    embed = discord.Embed(
                        title="🔔 Напоминание о смежке!",
                        description=f"**{event['title']}** состоится **завтра** в **{event['time']}** (МСК).\nНе забудьте подтвердить участие!",
                        color=discord.Color.orange()
                    )
                    content = "@everyone" if PING_EVERYONE else None
                    await channel.send(content=content, embed=embed)
                    event['reminded'] = True
                    save_events(events)
                    logger.info(f"Отправлено напоминание о событии {eid}")
        await asyncio.sleep(60)

async def on_reaction_add(reaction, user):
    if user.bot:
        return
    event_id = None
    for eid, ev in events.items():
        if ev['message_id'] == reaction.message.id:
            event_id = eid
            break
    if not event_id:
        return
    if str(reaction.emoji) not in ('✅', '❌'):
        return

    event = events[event_id]
    if str(reaction.emoji) == '✅':
        if user.id in event['non_participants']:
            event['non_participants'].remove(user.id)
        event['participants'].add(user.id)
    else:  # ❌
        if user.id in event['participants']:
            event['participants'].remove(user.id)
        event['non_participants'].add(user.id)

    save_events(events)
    await update_event_embed(reaction.message, event_id)
    logger.info(f"Пользователь {user.display_name} {reaction.emoji} на событие {event_id}")

async def on_reaction_remove(reaction, user):
    if user.bot:
        return
    event_id = None
    for eid, ev in events.items():
        if ev['message_id'] == reaction.message.id:
            event_id = eid
            break
    if not event_id:
        return

    event = events[event_id]
    if str(reaction.emoji) == '✅':
        if user.id in event['participants']:
            event['participants'].remove(user.id)
    elif str(reaction.emoji) == '❌':
        if user.id in event['non_participants']:
            event['non_participants'].remove(user.id)

    save_events(events)
    await update_event_embed(reaction.message, event_id)
    logger.info(f"Пользователь {user.display_name} убрал {reaction.emoji} с события {event_id}")

async def sync_events(bot):
    for eid, event in events.items():
        channel = bot.get_channel(event['channel_id'])
        if not channel:
            continue
        try:
            msg = await channel.fetch_message(event['message_id'])
            await update_event_embed(msg, eid)
            logger.debug(f"Синхронизировано событие {eid}")
        except Exception as e:
            logger.warning(f"Не удалось синхронизировать событие {eid}: {e}")

# ==================== МОДАЛЬНОЕ ОКНО ПОДТВЕРЖДЕНИЯ РЕСТАРТА ====================
class RestartConfirmModal(ui.Modal, title='Подтверждение перезапуска'):
    confirm = ui.TextInput(
        label='Введите "ДА" для подтверждения',
        placeholder='ДА',
        min_length=2,
        max_length=2,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        if self.confirm.value.upper() == 'ДА':
            await interaction.response.send_message("🔄 Перезапуск бота...", ephemeral=True)
            logger.info(f"Бот перезапущен пользователем {interaction.user}")
            # Сохраняем все данные перед выходом
            save_events(events)
            # Немедленное завершение процесса без генерации исключения
            os._exit(0)
        else:
            await interaction.response.send_message("❌ Перезапуск отменён.", ephemeral=True)

# ==================== ПАНЕЛЬ УПРАВЛЕНИЯ ====================
class DashboardView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        features = {
            "ai_enabled": ("🤖 AI-чат", discord.ButtonStyle.green, discord.ButtonStyle.red),
            "monitor_enabled": ("🛡️ Мониторинг", discord.ButtonStyle.green, discord.ButtonStyle.red),
            "quotes_enabled": ("📝 Цитатник", discord.ButtonStyle.green, discord.ButtonStyle.red)
        }
        for feature, (label, on_style, off_style) in features.items():
            status = get_status(feature, True)
            style = on_style if status else off_style
            button_label = f"{label}: {'ВКЛ' if status else 'ВЫКЛ'}"
            button = ui.Button(label=button_label, style=style, custom_id=f"toggle_{feature}")
            button.callback = self.make_callback(feature)
            self.add_item(button)

        # Кнопка перезапуска (всегда видна, но с проверкой прав внутри)
        restart_button = ui.Button(label="🔄 Перезапустить бота", style=discord.ButtonStyle.danger, custom_id="restart_bot")
        restart_button.callback = self.restart_callback
        self.add_item(restart_button)

    def make_callback(self, feature):
        async def callback(interaction: discord.Interaction):
            if not has_moderator_role(interaction.user):
                await interaction.response.send_message("❌ У вас недостаточно прав для управления панелью.", ephemeral=True)
                logger.warning(f"Пользователь {interaction.user} пытался управлять панелью без прав")
                return
            current = get_status(feature, True)
            new_status = not current
            set_status(feature, new_status)
            self.update_buttons()
            embed = discord.Embed(
                title="📋 Панель управления ботом",
                description="Управляйте функциями бота через кнопки ниже. Статус каждой функции отображается на кнопке.",
                color=discord.Color.blue()
            )
            embed.add_field(name="Статус", value="Зелёный – включено, Красный – выключено", inline=False)
            await interaction.response.edit_message(embed=embed, view=self)
            logger.info(f"Пользователь {interaction.user} переключил {feature} в {'ВКЛ' if new_status else 'ВЫКЛ'}")
        return callback

    async def restart_callback(self, interaction: discord.Interaction):
        if not has_moderator_role(interaction.user):
            await interaction.response.send_message("❌ У вас недостаточно прав для перезапуска бота.", ephemeral=True)
            logger.warning(f"Пользователь {interaction.user} пытался перезапустить бота без прав")
            return
        # Открываем модальное окно подтверждения
        await interaction.response.send_modal(RestartConfirmModal())

async def setup_dashboard(bot):
    if not EVENT_CHANNEL_ID:
        logger.warning("EVENT_CHANNEL_ID не задан, панель управления не создана.")
        return
    channel = bot.get_channel(EVENT_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(EVENT_CHANNEL_ID)
        except Exception as e:
            logger.error(f"Не удалось найти канал {EVENT_CHANNEL_ID}: {e}")
            return

    # Ищем существующее сообщение с панелью
    async for msg in channel.history(limit=50):
        if msg.author == bot.user and msg.embeds:
            for row in msg.components:
                for comp in row.children:
                    if hasattr(comp, 'custom_id') and comp.custom_id.startswith('toggle_'):
                        # Обновляем существующее сообщение
                        view = DashboardView()
                        embed = discord.Embed(
                            title="📋 Панель управления ботом",
                            description="Управляйте функциями бота через кнопки ниже. Статус каждой функции отображается на кнопке.",
                            color=discord.Color.blue()
                        )
                        embed.add_field(name="Статус", value="Зелёный – включено, Красный – выключено", inline=False)
                        await msg.edit(embed=embed, view=view)
                        logger.info("Обновлено существующее сообщение панели управления")
                        return
    # Если не нашли – создаём новое
    view = DashboardView()
    embed = discord.Embed(
        title="📋 Панель управления ботом",
        description="Управляйте функциями бота через кнопки ниже. Статус каждой функции отображается на кнопке.",
        color=discord.Color.blue()
    )
    embed.add_field(name="Статус", value="Зелёный – включено, Красный – выключено", inline=False)
    await channel.send(embed=embed, view=view)
    logger.info("Создано новое сообщение панели управления")
