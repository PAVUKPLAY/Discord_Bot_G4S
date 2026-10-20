import discord
import aiohttp
import logging
from discord import FFmpegPCMAudio, ui
from config import RADIO_VOICE_CHANNEL_ID, RADIO_TEXT_CHANNEL_ID, RADIO_DEFAULT_STATION

logger = logging.getLogger(__name__)

RADIO_API_BASE = "https://de1.api.radio-browser.info/json"

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -timeout 30000000",
    "options": "-vn"
}


class RadioManager:
    def __init__(self):
        self.voice_clients: dict[int, discord.VoiceClient] = {}
        self.current_stations: dict[int, str] = {}
        self.control_messages: dict[int, discord.Message] = {}

    async def search_station(self, query: str):
        url = f"{RADIO_API_BASE}/stations/search"
        params = {
            "name": query,
            "limit": 5,
            "hidebroken": "true",
            "order": "clickcount",
            "reverse": "true"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status != 200:
                        logger.error(f"Radio Browser API вернул {resp.status}")
                        return None
                    stations = await resp.json()
                    for st in stations:
                        stream_url = st.get("url_resolved") or st.get("url")
                        if stream_url and stream_url.startswith(("http://", "https://")):
                            return {
                                "name": st.get("name", "Неизвестная станция"),
                                "url": stream_url,
                            }
                    return None
        except Exception as e:
            logger.error(f"Ошибка поиска станции '{query}': {e}")
            return None

    async def resolve_station(self, query: str):
        if query.startswith(("http://", "https://")):
            return (query, query)
        st = await self.search_station(query)
        if st:
            return (st["name"], st["url"])
        return None

    async def connect_voice(self, channel: discord.VoiceChannel):
        guild_id = channel.guild.id
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_connected():
            if vc.channel.id != channel.id:
                try:
                    await vc.move_to(channel)
                except Exception as e:
                    logger.error(f"Voice move error: {e}")
                    return None
            return vc
        try:
            vc = await channel.connect(timeout=25, reconnect=True)
            self.voice_clients[guild_id] = vc
            logger.info(f"Подключено к голосовому каналу {channel.name}")
            return vc
        except Exception as e:
            logger.error(f"Voice connect error: {e}")
            return None

    async def play_url(self, guild_id: int, url: str, name: str) -> bool:
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            return False
        if vc.is_playing() or vc.is_paused():
            vc.stop()
        try:
            source = FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
            vc.play(source)
            self.current_stations[guild_id] = name
            logger.info(f"Играет '{name}' в гильдии {guild_id}")
            return True
        except Exception as e:
            logger.error(f"FFmpeg error: {e}")
            return False

    async def change_station(self, guild_id: int, query: str) -> str:
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            return "❌ Бот не подключён к голосовому каналу."
        resolved = await self.resolve_station(query)
        if not resolved:
            return f"❌ Станция «{query}» не найдена."
        name, url = resolved
        ok = await self.play_url(guild_id, url, name)
        return f"📻 Воспроизводится: **{name}**" if ok else "❌ Не удалось запустить поток."

    async def toggle_pause(self, guild_id: int) -> str:
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            return "❌ Бот не подключён к голосовому каналу."
        if vc.is_playing():
            vc.pause()
            return "⏸️ Пауза."
        if vc.is_paused():
            vc.resume()
            return "▶️ Продолжаю."
        return "❌ Сейчас ничего не играет."

    async def stop_playback(self, guild_id: int) -> str:
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            return "❌ Бот не подключён к голосовому каналу."
        if vc.is_playing() or vc.is_paused():
            vc.stop()
            self.current_stations.pop(guild_id, None)
            return "⏹️ Радио остановлено."
        return "❌ Сейчас ничего не играет."

    async def auto_start(self, bot):
        if not RADIO_VOICE_CHANNEL_ID:
            logger.warning("RADIO_VOICE_CHANNEL_ID не задан — автозапуск радио отключён.")
            return
        await bot.wait_until_ready()
        channel = bot.get_channel(RADIO_VOICE_CHANNEL_ID)
        if not channel:
            try:
                channel = await bot.fetch_channel(RADIO_VOICE_CHANNEL_ID)
            except Exception as e:
                logger.error(f"Голосовой канал {RADIO_VOICE_CHANNEL_ID} не найден: {e}")
                return
        vc = await self.connect_voice(channel)
        if not vc:
            return
        guild_id = channel.guild.id

        if RADIO_DEFAULT_STATION:
            resolved = await self.resolve_station(RADIO_DEFAULT_STATION)
            if resolved:
                name, url = resolved
                await self.play_url(guild_id, url, name)
            else:
                logger.warning(f"Станция по умолчанию '{RADIO_DEFAULT_STATION}' не найдена.")

        if RADIO_TEXT_CHANNEL_ID:
            await self.ensure_control_panel(bot, RADIO_TEXT_CHANNEL_ID)

    def _build_embed(self, guild_id: int) -> discord.Embed:
        current = self.current_stations.get(guild_id, "Ничего не играет")
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_playing():
            status = "🟢 Играет"
        elif vc and vc.is_paused():
            status = "⏸️ Пауза"
        else:
            status = "⏹️ Остановлено"
        embed = discord.Embed(
            title="📻 Радио G4S",
            description=f"**Станция:** {current}\n**Статус:** {status}",
            color=discord.Color.purple()
        )
        embed.set_footer(text="Нажмите «Сменить станцию», чтобы выбрать другую.")
        return embed

    async def ensure_control_panel(self, bot, channel_id: int):
        channel = bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await bot.fetch_channel(channel_id)
            except Exception as e:
                logger.error(f"Текстовый канал {channel_id} не найден: {e}")
                return
        guild_id = channel.guild.id

        async for msg in channel.history(limit=50):
            if msg.author == bot.user and msg.components:
                for row in msg.components:
                    for comp in row.children:
                        if hasattr(comp, "custom_id") and comp.custom_id == "radio_change":
                            self.control_messages[guild_id] = msg
                            await self.update_control_panel(guild_id)
                            return

        embed = self._build_embed(guild_id)
        view = RadioControlView(self)
        msg = await channel.send(embed=embed, view=view)
        self.control_messages[guild_id] = msg
        logger.info(f"Панель радио отправлена в {channel.name}")

    async def update_control_panel(self, guild_id: int):
        msg = self.control_messages.get(guild_id)
        if not msg:
            return
        try:
            await msg.edit(embed=self._build_embed(guild_id))
        except Exception as e:
            logger.error(f"Ошибка обновления панели: {e}")


class ChangeStationModal(ui.Modal, title="Смена радиостанции"):
    station = ui.TextInput(
        label="Название станции или URL",
        placeholder="Например: Radio Record или https://stream.example.com/radio.mp3",
        required=True,
        max_length=200
    )

    def __init__(self, radio_manager: RadioManager):
        super().__init__()
        self.radio_manager = radio_manager

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await self.radio_manager.change_station(interaction.guild_id, self.station.value)
        await interaction.followup.send(result, ephemeral=True)
        await self.radio_manager.update_control_panel(interaction.guild_id)


class RadioControlView(ui.View):
    def __init__(self, radio_manager: RadioManager):
        super().__init__(timeout=None)
        self.radio_manager = radio_manager

    @ui.button(label="🔄 Сменить станцию", style=discord.ButtonStyle.primary, custom_id="radio_change")
    async def change_station(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(ChangeStationModal(self.radio_manager))

    @ui.button(label="⏯️ Пауза / Играть", style=discord.ButtonStyle.secondary, custom_id="radio_toggle")
    async def toggle(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        result = await self.radio_manager.toggle_pause(interaction.guild_id)
        await interaction.followup.send(result, ephemeral=True)
        await self.radio_manager.update_control_panel(interaction.guild_id)

    @ui.button(label="⏹️ Остановить", style=discord.ButtonStyle.danger, custom_id="radio_stop_btn")
    async def stop_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        result = await self.radio_manager.stop_playback(interaction.guild_id)
        await interaction.followup.send(result, ephemeral=True)
        await self.radio_manager.update_control_panel(interaction.guild_id)
