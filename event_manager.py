import discord
from discord import ui
import re
from datetime import datetime
import json
import os
import asyncio
from config import EVENT_CHANNEL_ID, ANNOUNCE_CHANNEL_ID, PING_EVERYONE

DATA_FILE = "events_data.json"

def load_events():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                for eid, ev in data.items():
                    ev['participants'] = set(ev['participants'])
                    ev['non_participants'] = set(ev['non_participants'])
                return data
            except:
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

class CreateEventModal(ui.Modal, title='Создание смежки'):
    title_input = ui.TextInput(label='Название смежки', placeholder='Например: Отрядная операция', default='Отрядная смежка')
    date_input = ui.TextInput(label='Дата (ДД.ММ.ГГГГ)', placeholder='25.12.2025')
    time_input = ui.TextInput(label='Время (ЧЧ:ММ) по МСК', placeholder='19:00')

    async def on_submit(self, interaction: discord.Interaction):
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
            'reminded': False
        }
        save_events(events)

        embed = discord.Embed(
            title=f"📅 {self.title_input.value}",
            description=f"**Дата:** {self.date_input.value}\n**Время:** {self.time_input.value} (МСК)",
            color=discord.Color.gold()
        )
        embed.add_field(name="✅ Участники", value="Пока никого", inline=True)
        embed.add_field(name="❌ Не смогут", value="Пока никого", inline=True)
        embed.set_footer(text=f"ID события: {event_id}")

        channel = interaction.guild.get_channel(ANNOUNCE_CHANNEL_ID)
        if not channel:
            await interaction.response.send_message('❌ Канал объявлений не найден.', ephemeral=True)
            return

        view = EventActionButtons(event_id)
        content = "@everyone" if PING_EVERYONE else None
        msg = await channel.send(content=content, embed=embed, view=view)
        events[event_id]['message_id'] = msg.id
        save_events(events)

        await interaction.response.send_message(f'✅ Смежка создана! Объявление отправлено в канал {channel.mention}', ephemeral=True)

class EventActionButtons(ui.View):
    def __init__(self, event_id):
        super().__init__(timeout=None)
        self.event_id = event_id

    @ui.button(label='✅ Буду участвовать', style=discord.ButtonStyle.green, custom_id='event_join')
    async def join_button(self, interaction: discord.Interaction, button: ui.Button):
        print(f"[LOG] Нажата кнопка 'Буду участвовать' от {interaction.user.display_name}")
        await self._update_event(interaction, 'join')

    @ui.button(label='❌ Не могу', style=discord.ButtonStyle.red, custom_id='event_leave')
    async def leave_button(self, interaction: discord.Interaction, button: ui.Button):
        print(f"[LOG] Нажата кнопка 'Не могу' от {interaction.user.display_name}")
        await self._update_event(interaction, 'leave')

    async def _update_event(self, interaction: discord.Interaction, action: str):
        # Откладываем ответ, чтобы успеть обработать
        await interaction.response.defer(ephemeral=True)

        print(f"[LOG] Обновление события {self.event_id}, действие: {action}")

        event = events.get(self.event_id)
        if not event:
            print(f"[ERROR] Событие {self.event_id} не найдено")
            await interaction.followup.send('❌ Событие не найдено.', ephemeral=True)
            return

        user_id = interaction.user.id
        print(f"[LOG] Пользователь {interaction.user.display_name} (ID: {user_id})")

        if action == 'join':
            if user_id in event['non_participants']:
                event['non_participants'].remove(user_id)
                print(f"[LOG] Удалён из 'не смогут'")
            if user_id in event['participants']:
                event['participants'].remove(user_id)
                print(f"[LOG] Удалён из 'участники' (повторный отказ)")
            else:
                event['participants'].add(user_id)
                print(f"[LOG] Добавлен в 'участники'")
        else:  # leave
            if user_id in event['participants']:
                event['participants'].remove(user_id)
                print(f"[LOG] Удалён из 'участники'")
            if user_id in event['non_participants']:
                event['non_participants'].remove(user_id)
                print(f"[LOG] Удалён из 'не смогут' (повторный отказ)")
            else:
                event['non_participants'].add(user_id)
                print(f"[LOG] Добавлен в 'не смогут'")

        save_events(events)
        print(f"[LOG] Текущие участники: {event['participants']}")
        print(f"[LOG] Текущие не участники: {event['non_participants']}")

        # Формируем embed
        embed = discord.Embed(
            title=f"📅 {event['title']}",
            description=f"**Дата:** {event['date']}\n**Время:** {event['time']} (МСК)",
            color=discord.Color.gold()
        )
        participants = []
        for uid in event['participants']:
            user = interaction.guild.get_member(uid)
            if user:
                participants.append(user.display_name)
        non_participants = []
        for uid in event['non_participants']:
            user = interaction.guild.get_member(uid)
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
        embed.set_footer(text=f"ID события: {self.event_id}")

        # Создаём новый View для обновления
        new_view = EventActionButtons(self.event_id)

        channel = interaction.guild.get_channel(event['channel_id'])
        if not channel:
            print(f"[ERROR] Канал {event['channel_id']} не найден")
            await interaction.followup.send('❌ Канал не найден.', ephemeral=True)
            return

        try:
            msg = await channel.fetch_message(event['message_id'])
            print(f"[LOG] Найдено сообщение {msg.id}, редактируем...")
            await msg.edit(embed=embed, view=new_view)
            print(f"[LOG] Сообщение успешно обновлено")
            await interaction.followup.send('✅ Список обновлён!', ephemeral=True)
        except discord.NotFound:
            print(f"[ERROR] Сообщение {event['message_id']} не найдено")
            await interaction.followup.send('❌ Сообщение с событием не найдено. Возможно, оно было удалено.', ephemeral=True)
        except Exception as e:
            print(f"[ERROR] Ошибка редактирования: {e}")
            await interaction.followup.send(f'❌ Ошибка обновления: {e}', ephemeral=True)

class CreateEventButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label='➕ Создать смежку', style=discord.ButtonStyle.primary, custom_id='create_event_button')
    async def create_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(CreateEventModal())

async def setup_event_button(bot):
    if not EVENT_CHANNEL_ID:
        print("⚠️ EVENT_CHANNEL_ID не задан. Кнопка не создана.")
        return

    channel = bot.get_channel(EVENT_CHANNEL_ID)
    if not channel:
        try:
            channel = await bot.fetch_channel(EVENT_CHANNEL_ID)
        except Exception as e:
            print(f"❌ Не удалось найти канал с ID {EVENT_CHANNEL_ID}: {e}")
            return

    print(f"🔍 Проверяем канал {channel.name} (ID: {channel.id}) на наличие кнопки...")

    found = False
    async for msg in channel.history(limit=30):
        if msg.author == bot.user and msg.embeds:
            for row in msg.components:
                for comp in row.children:
                    if hasattr(comp, 'custom_id') and comp.custom_id == 'create_event_button':
                        found = True
                        print(f"✅ Найдено существующее сообщение с кнопкой (ID: {msg.id})")
                        break
                if found:
                    break
        if found:
            break

    if found:
        return

    print("📤 Отправляем новое сообщение с кнопкой...")
    embed = discord.Embed(
        title="📢 Создание смежки",
        description="Нажмите на кнопку ниже, чтобы создать новое событие для отряда.",
        color=discord.Color.blue()
    )
    view = CreateEventButton()
    await channel.send(embed=embed, view=view)
    print("✅ Постоянная кнопка 'Создать смежку' размещена.")

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
        await asyncio.sleep(60)
