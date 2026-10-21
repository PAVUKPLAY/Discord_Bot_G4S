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

# Берем путь из переменной окружения DATA_DIR или используем /app/data (постоянный том Bothost)
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
DATA_FILE = os.path.join(DATA_DIR, "events_data.json")

os.makedirs(DATA_DIR, exist_ok=True)

def load_events():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                for eid, ev in data.items():
                    ev['participants'] = set(ev['participants'])
                    ev['non_participants'] = set(ev['non_participants'])
                logger.info(f"Загружено {len(data)} событий из {DATA_FILE}")
                return data
            except Exception as e:
                logger.error(f"Ошибка загрузки событий: {e}")
                return {}
    logger.warning(f"Файл {DATA_FILE} не найден — история событий пуста")
    return {}

def save_events(events):
    data = {}
    for eid, ev in events.items():
        data[eid] = ev.copy()
        data[eid]['participants'] = list(ev['participants'])
        data[eid]['non_participants'] = list(ev['non_participants'])
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        logger.info(f"События сохранены в {DATA_FILE}")
    except Exception as e:
        logger.error(f"Ошибка сохранения событий: {e}")

events = load_events()

async def update_event_embed(message, event_id):
    event = events.get(event_id)
    if not event:
        logger.warning(f"Попытка обновить несуществующее событие {event_id}")
        return

    is_cancelled = event.get('is_cancelled', False)
    
    if is_cancelled:
        title = f"❌ ОТМЕНЕНО: {event['title']}"
        color = discord.Color.red()
        description = f"**Дата:** {event['date']}\n**Время:** {event['time']} (МСК)\n\n**Мероприятие отменено.**"
    else:
        title = f"📅 {event['title']}"
        color = discord.Color.gold()
        description = f"**Дата:** {event['date']}\n**Время:** {event['time']} (МСК)\n\n**Ставьте реакции:**\n✅ – буду участвовать\n❌ – не смогу"

    embed = discord.Embed(
        title=title,
        description=description,
        color=color
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
    embed.set_footer(text=f"G4S Командование • ID: {event_id} | Code by PAVUK")
    await message.edit(embed=embed)
    logger.debug(f"Обновлён embed события {event_id}")

# ==================== ОТМЕНА И ПЕРЕНОС ====================

async def cancel_event(bot, event_id):
    event = events.get(event_id)
    if not event: return
    event['is_cancelled'] = True
    save_events(events)

    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="❌ Мероприятие отменено",
            description=f"Мероприятие **{event['title']}** на {event['date']} в {event['time']} было отменено.",
            color=discord.Color.red()
        )
        embed.set_footer(text="Code by PAVUK")
        await channel.send(embed=embed)

    try:
        ev_channel = bot.get_channel(event['channel_id'])
        msg = await ev_channel.fetch_message(event['message_id'])
        await update_event_embed(msg, event_id)
        await msg.clear_reactions()
    except Exception as e:
        logger.error(f"Не удалось обновить сообщение отмененного события: {e}")

async def reschedule_event(bot, event_id, new_date, new_time):
    event = events.get(event_id)
    if not event: return
    
    event['date'] = new_date
    event['time'] = new_time
    dt_str = f"{new_date} {new_time}"
    event_dt = datetime.strptime(dt_str, "%d.%m.%Y %H:%M")
    event['datetime'] = event_dt.isoformat()
    
    # Сбрасываем флаги напоминаний, чтобы они сработали заново
    event['reminded_24h'] = False
    event['reminded_1h'] = False
    event['reminded_start'] = False
    
    save_events(events)

    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if channel:
        embed = discord.Embed(
            title="🔄 Мероприятие перенесено",
            description=f"Мероприятие **{event['title']}** перенесено на **{new_date}** в **{new_time}** (МСК).",
            color=discord.Color.orange()
        )
        embed.set_footer(text="Code by PAVUK")
        await channel.send(embed=embed)

    try:
        ev_channel = bot.get_channel(event['channel_id'])
        msg = await ev_channel.fetch_message(event['message_id'])
        await update_event_embed(msg, event_id)
    except Exception as e:
        logger.error(f"Не удалось обновить сообщение перенесенного события: {e}")

# ==================== МОДАЛЬНЫЕ ОКНА И СЕЛЕКТЫ ====================

class CreateEventModal(ui.Modal, title='Создание смежки'):
    title_input = ui.TextInput(label='Название смежки', placeholder='Например: Отрядная операция', default='Отрядная смежка')
    date_input = ui.TextInput(label='Дата (ДД.ММ.ГГГГ)', placeholder='25.12.2025')
    time_input = ui.TextInput(label='Время (ЧЧ:ММ) по МСК', placeholder='19:00')

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if not ANNOUNCE_CHANNEL_ID:
                await interaction.response.send_message('❌ Канал для объявлений не настроен.', ephemeral=True)
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
                'reminded_24h': False,
                'reminded_1h': False,
                'reminded_start': False,
                'is_cancelled': False
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
            embed.set_footer(text=f"G4S Командование • ID: {event_id} | Code by PAVUK")

            channel = interaction.guild.get_channel(ANNOUNCE_CHANNEL_ID)
            if not channel:
                await interaction.response.send_message('❌ Канал объявлений не найден.', ephemeral=True)
                return

            content = "@everyone" if PING_EVERYONE else None
            msg = await channel.send(content=content, embed=embed)
            events[event_id]['message_id'] = msg.id
            save_events(events)

            await msg.add_reaction('✅')
            await msg.add_reaction('❌')

            await interaction.response.send_message(f'✅ Смежка создана! Объявление отправлено в канал {channel.mention}', ephemeral=True)
            logger.info(f"Создано событие {event_id} пользователем {interaction.user}")
        except Exception as e:
            logger.error(f"Ошибка в on_submit: {e}")
            await interaction.response.send_message(f'❌ Произошла ошибка: {e}', ephemeral=True)

class RescheduleEventModal(ui.Modal, title='Перенос мероприятия'):
    date_input = ui.TextInput(label='Новая дата (ДД.ММ.ГГГГ)', placeholder='25.12.2025')
    time_input = ui.TextInput(label='Новое время (ЧЧ:ММ) по МСК', placeholder='19:00')

    def __init__(self, event_id):
        super().__init__()
        self.event_id = event_id

    async def on_submit(self, interaction: discord.Interaction):
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', self.date_input.value):
            await interaction.response.send_message('❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ', ephemeral=True)
            return
        if not re.match(r'^\d{2}:\d{2}$', self.time_input.value):
            await interaction.response.send_message('❌ Неверный формат времени. Используйте ЧЧ:ММ', ephemeral=True)
            return
        try:
            datetime.strptime(f"{self.date_input.value} {self.time_input.value}", "%d.%m.%Y %H:%M")
        except ValueError:
            await interaction.response.send_message('❌ Некорректная дата или время.', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await reschedule_event(interaction.client, self.event_id, self.date_input.value, self.time_input.value)
        await interaction.followup.send(f"✅ Мероприятие успешно перенесено.", ephemeral=True)

class EventCancelSelect(ui.Select):
    def __init__(self, active_events):
        options = []
        for eid, ev in active_events.items():
            options.append(discord.SelectOption(label=ev['title'], description=f"{ev['date']} {ev['time']}", value=eid))
        super().__init__(placeholder="Выберите мероприятие для отмены...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        event_id = self.values[0]
        await interaction.response.defer(ephemeral=True)
        await cancel_event(interaction.client, event_id)
        await interaction.followup.send(f"✅ Мероприятие отменено.", ephemeral=True)

class EventRescheduleSelect(ui.Select):
    def __init__(self, active_events):
        options = []
        for eid, ev in active_events.items():
            options.append(discord.SelectOption(label=ev['title'], description=f"{ev['date']} {ev['time']}", value=eid))
        super().__init__(placeholder="Выберите мероприятие для переноса...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        event_id = self.values[0]
        await interaction.response.send_modal(RescheduleEventModal(event_id))

# ==================== ГЛАВНАЯ ПАНЕЛЬ СМЕЖЕК ====================

class CreateEventView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label='➕ Создать смежку', style=discord.ButtonStyle.primary, custom_id='create_event_button')
    async def create_button(self, interaction: discord.Interaction, button: ui.Button):
        if not has_moderator_role(interaction.user):
            await interaction.response.send_message("❌ У вас недостаточно прав.", ephemeral=True)
            return
        await interaction.response.send_modal(CreateEventModal())

    @ui.button(label='❌ Отменить', style=discord.ButtonStyle.danger, custom_id='cancel_event_button')
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        if not has_moderator_role(interaction.user):
            await interaction.response.send_message("❌ У вас недостаточно прав.", ephemeral=True)
            return
        active_events = {k: v for k, v in events.items() if not v.get('is_cancelled', False)}
        if not active_events:
            await interaction.response.send_message("Нет активных мероприятий для отмены.", ephemeral=True)
            return
        
        view = ui.View()
        view.add_item(EventCancelSelect(active_events))
        await interaction.response.send_message("Выберите мероприятие, которое нужно отменить:", view=view, ephemeral=True)

    @ui.button(label='🔄 Перенести', style=discord.ButtonStyle.secondary, custom_id='reschedule_event_button')
    async def reschedule_button(self, interaction: discord.Interaction, button: ui.Button):
        if not has_moderator_role(interaction.user):
            await interaction.response.send_message("❌ У вас недостаточно прав.", ephemeral=True)
            return
        active_events = {k: v for k, v in events.items() if not v.get('is_cancelled', False)}
        if not active_events:
            await interaction.response.send_message("Нет активных мероприятий для переноса.", ephemeral=True)
            return
        
        view = ui.View()
        view.add_item(EventRescheduleSelect(active_events))
        await interaction.response.send_message("Выберите мероприятие, которое нужно перенести:", view=view, ephemeral=True)

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

    logger.info(f"Проверяем канал {channel.name} (ID: {channel.id}) на наличие панели смежек...")

    found = False
    async for msg in channel.history(limit=30):
        if msg.author == bot.user and msg.embeds:
            for row in msg.components:
                for comp in row.children:
                    if hasattr(comp, 'custom_id') and comp.custom_id == 'create_event_button':
                        found = True
                        if len(msg.components[0].children) < 3:
                            embed = discord.Embed(
                                title="📢 Управление смежками",
                                description="Нажмите на кнопку ниже, чтобы создать, отменить или перенести событие для отряда.",
                                color=discord.Color.blue()
                            )
                            embed.set_footer(text="Code by PAVUK")
                            await msg.edit(embed=embed, view=CreateEventView())
                            logger.info("Старая панель смежек обновлена (добавлены кнопки).")
                        break
                if found: break
        if found: break

    if found:
        return

    logger.info("Отправляем новое сообщение с кнопками смежек...")
    embed = discord.Embed(
        title="📢 Управление смежками",
        description="Нажмите на кнопку ниже, чтобы создать, отменить или перенести событие для отряда.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Code by PAVUK")
    await channel.send(embed=embed, view=CreateEventView())
    logger.info("Постоянная панель смежек размещена.")

async def cleanup_event_button(bot):
    if not EVENT_CHANNEL_ID:
        return
    channel = bot.get_channel(EVENT_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(EVENT_CHANNEL_ID)
        except Exception:
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

# ==================== ФОНОВАЯ ЗАДАЧА НАПОМИНАНИЙ ====================

async def send_reminder(bot, event, title, description, color):
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if not channel: return
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text="Code by PAVUK")
    content = "@everyone" if PING_EVERYONE else None
    await channel.send(content=content, embed=embed)

async def reminder_task(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        now = datetime.now()
        for eid, event in list(events.items()):
            if event.get('is_cancelled', False):
                continue

            try:
                event_dt = datetime.fromisoformat(event['datetime'])
            except Exception:
                continue

            delta = (event_dt - now).total_seconds()

            # Если мероприятие прошло более 2 часов назад, пропускаем
            if delta < -2 * 3600:
                continue

            # 1. Напоминание за 24 часа (если осталось меньше 24 часов, но больше 1 часа)
            if not event.get('reminded_24h', False) and 1 * 3600 < delta <= 24 * 3600:
                await send_reminder(
                    bot, event,
                    title="📅 Напоминание о смежке!",
                    description=f"**{event['title']}** состоится **завтра** в **{event['time']}** (МСК).\nНе забудьте подтвердить участие!",
                    color=discord.Color.orange()
                )
                event['reminded_24h'] = True
                save_events(events)

            # 2. Напоминание за 1 час (если осталось меньше 1 часа, но больше 5 минут)
            elif not event.get('reminded_1h', False) and 5 * 60 < delta <= 1 * 3600:
                await send_reminder(
                    bot, event,
                    title="⏳ Скоро начало!",
                    description=f"Мероприятие **{event['title']}** начнется **через 1 час** (в **{event['time']}** МСК).\nГотовьтесь!",
                    color=discord.Color.blue()
                )
                event['reminded_1h'] = True
                save_events(events)

            # 3. Напоминание о начале (если осталось меньше 5 минут или уже началось, но не прошло 2 часа)
            elif not event.get('reminded_start', False) and -2 * 3600 <= delta <= 5 * 60:
                await send_reminder(
                    bot, event,
                    title="🚀 Мероприятие началось!",
                    description=f"Мероприятие **{event['title']}** **уже началось**!\nПрисоединяйтесь к каналу!",
                    color=discord.Color.green()
                )
                event['reminded_start'] = True
                save_events(events)

        await asyncio.sleep(30) # Проверяем каждые 30 секунд

async def on_reaction_add(reaction, user):
    if user.bot: return
    event_id = None
    for eid, ev in events.items():
        if ev['message_id'] == reaction.message.id:
            event_id = eid
            break
    if not event_id: return
    if str(reaction.emoji) not in ('✅', '❌'): return

    event = events[event_id]
    if event.get('is_cancelled', False):
        try: await reaction.remove(user)
        except: pass
        return

    if str(reaction.emoji) == '✅':
        if user.id in event['non_participants']:
            event['non_participants'].remove(user.id)
        event['participants'].add(user.id)
    else:
        if user.id in event['participants']:
            event['participants'].remove(user.id)
        event['non_participants'].add(user.id)

    save_events(events)
    await update_event_embed(reaction.message, event_id)

async def on_reaction_remove(reaction, user):
    if user.bot: return
    event_id = None
    for eid, ev in events.items():
        if ev['message_id'] == reaction.message.id:
            event_id = eid
            break
    if not event_id: return

    event = events[event_id]
    if event.get('is_cancelled', False): return

    if str(reaction.emoji) == '✅':
        if user.id in event['participants']:
            event['participants'].remove(user.id)
    elif str(reaction.emoji) == '❌':
        if user.id in event['non_participants']:
            event['non_participants'].remove(user.id)

    save_events(events)
    await update_event_embed(reaction.message, event_id)

async def sync_events(bot):
    for eid, event in events.items():
        channel = bot.get_channel(event['channel_id'])
        if not channel: continue
        try:
            msg = await channel.fetch_message(event['message_id'])
            await update_event_embed(msg, eid)
        except Exception: pass

# ==================== ПАНЕЛЬ УПРАВЛЕНИЯ БОТОМ ====================

class RestartConfirmModal(ui.Modal, title='Подтверждение перезапуска'):
    confirm = ui.TextInput(label='Введите "ДА" для подтверждения', min_length=2, max_length=2)
    async def on_submit(self, interaction: discord.Interaction):
        if self.confirm.value.upper() == 'ДА':
            await interaction.response.send_message("🔄 Перезапуск бота...", ephemeral=True)
            save_events(events)
            import sys
            await interaction.client.close()
            sys.exit(0)
        else:
            await interaction.response.send_message("❌ Отменено.", ephemeral=True)

class DashboardView(ui.View):
    def __init__(self, radio_manager=None):
        super().__init__(timeout=None)
        self.radio_manager = radio_manager
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        features = {
            "ai_enabled": ("🤖 AI-чат", discord.ButtonStyle.green, discord.ButtonStyle.red),
            "monitor_enabled": ("🛡️ Мониторинг", discord.ButtonStyle.green, discord.ButtonStyle.red),
            "radio_enabled": ("📻 Радио", discord.ButtonStyle.green, discord.ButtonStyle.red)
        }
        for feature, (label, on_style, off_style) in features.items():
            status = get_status(feature, True)
            style = on_style if status else off_style
            button = ui.Button(label=f"{label}: {'ВКЛ' if status else 'ВЫКЛ'}", style=style, custom_id=f"toggle_{feature}")
            button.callback = self.make_callback(feature)
            self.add_item(button)

        restart_button = ui.Button(label="🔄 Перезапустить бота", style=discord.ButtonStyle.danger, custom_id="restart_bot")
        restart_button.callback = self.restart_callback
        self.add_item(restart_button)

    def make_callback(self, feature):
        async def callback(interaction: discord.Interaction):
            if not has_moderator_role(interaction.user):
                await interaction.response.send_message("❌ У вас недостаточно прав.", ephemeral=True)
                return
            new_status = not get_status(feature, True)
            set_status(feature, new_status)
            
            if feature == "radio_enabled":
                if not new_status and self.radio_manager:
                    await self.radio_manager.disconnect_voice(interaction.guild_id)
                elif new_status and self.radio_manager:
                    asyncio.create_task(self.radio_manager.auto_start(interaction.client))

            self.update_buttons()
            embed = discord.Embed(title="📋 Панель управления ботом", description="Управляйте функциями бота.", color=discord.Color.blue())
            embed.set_footer(text="G4S Командование | Code by PAVUK")
            await interaction.response.edit_message(embed=embed, view=self)
        return callback

    async def restart_callback(self, interaction: discord.Interaction):
        if not has_moderator_role(interaction.user):
            await interaction.response.send_message("❌ У вас недостаточно прав.", ephemeral=True)
            return
        await interaction.response.send_modal(RestartConfirmModal())

async def setup_dashboard(bot, radio_manager=None):
    if not EVENT_CHANNEL_ID: return
    channel = bot.get_channel(EVENT_CHANNEL_ID)
    if not channel:
        try: channel = await bot.fetch_channel(EVENT_CHANNEL_ID)
        except Exception: return

    async for msg in channel.history(limit=50):
        if msg.author == bot.user and msg.embeds:
            for row in msg.components:
                for comp in row.children:
                    if hasattr(comp, 'custom_id') and comp.custom_id.startswith('toggle_'):
                        view = DashboardView(radio_manager)
                        embed = discord.Embed(title="📋 Панель управления ботом", description="Управляйте функциями бота.", color=discord.Color.blue())
                        embed.set_footer(text="G4S Командование | Code by PAVUK")
                        await msg.edit(embed=embed, view=view)
                        return
    view = DashboardView(radio_manager)
    embed = discord.Embed(title="📋 Панель управления ботом", description="Управляйте функциями бота.", color=discord.Color.blue())
    embed.set_footer(text="G4S Командование | Code by PAVUK")
    await channel.send(embed=embed, view=view)
