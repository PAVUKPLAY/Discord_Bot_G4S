import discord
import aiohttp
import logging
from discord import FFmpegPCMAudio, ui
from urllib.parse import urlparse
from config import RADIO_VOICE_CHANNEL_ID, RADIO_TEXT_CHANNEL_ID, RADIO_DEFAULT_STATION

logger = logging.getLogger(__name__)

RADIO_API_BASE = "https://de1.api.radio-browser.info/json"

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -timeout 30000000",
    "options": "-vn"
}

AUDIO_EXTENSIONS = (".mp3", ".aac", ".ogg", ".m3u8", ".m3u", ".pls", ".opus", ".flac", ".wav", ".mp4", ".webm")
STREAM_KEYWORDS = ("stream", "live", "radio", "listen", "air", "broadcast", "play", "icecast", "shoutcast", "audio")


def _classify_url(url: str):
    """
    Пытается определить, является ли URL аудиопотоком.
    Возвращает True (поток), False (веб-страница) или None (неясно).
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if not parsed.scheme or not parsed.netloc:
        return False
    path = (parsed.path or "").lower()

    # Явные признаки потока
    if any(path.endswith(ext) for ext in AUDIO_EXTENSIONS):
        return True
    if parsed.port and parsed.port in (8000, 8001, 8080, 8443, 9000):
        return True
    if any(kw in path for kw in STREAM_KEYWORDS):
        return True

    # Явные признаки веб-страницы (главная страница сайта)
    if path in ("", "/", "/index.html", "/index.htm", "/index.php"):
        return False

    # Неясно — например /radio1 без расширения, может быть потоком
    return None


class RadioManager:
    def __init__(self):
        self.voice_clients: dict[int, discord.VoiceClient] = {}
        self.current_stations: dict[int, str] = {}
        self.control_messages: dict[int, discord.Message] = {}
        self.bot = None

    async def search_station(self, query: str):
        """Ищет станцию, пропуская те, у которых URL — веб-страница."""
        url = f"{RADIO_API_BASE}/stations/search"
        params = {
            "name": query,
            "limit": 20,
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
                        if st.get("lastcheckok", 1) == 0:
                            continue
                        stream_url = st.get("url_resolved") or st.get("url")
                        if not stream_url or not stream_url.startswith(("http://", "https://")):
                            continue
                        if _classify_url(stream_url) is not True:
                            logger.debug(
                                f"Пропускаем станцию '{st.get('name')}': URL не похож на поток ({stream_url})"
                            )
                            continue
                        return {
                            "name": st.get("name", "Неизвестная станция"),
                            "url": stream_url,
                        }
                    return None
        except Exception as e:
            logger.error(f"Ошибка поиска станции '{query}': {e}")
            return None

    async def resolve_station(self, query: str):
        query = query.strip()
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

    def _after_play(self, error, guild_id: int, name: str, channel_id: int = None):
        """Callback, который discord.py вызовет, когда FFmpeg завершится."""
        try:
            if error:
                if self.current_stations.get(guild_id) == name:
                    logger.error(f"Ошибка воспроизведения '{name}': {error}")
                    self.current_stations.pop(guild_id, None)
                    if self.bot and channel_id:
                        import asyncio
                        asyncio.run_coroutine_threadsafe(
                            self._notify_error(channel_id, name),
                            self.bot.loop
                        )
        except Exception as e:
            logger.error(f"Ошибка в after callback: {e}")

    async def _notify_error(self, channel_id: int, name: str):
        try:
            channel = self.bot.get_channel(channel_id)
            if channel:
                await channel.send(
                    f"⚠️ Не удалось воспроизвести «{name}». "
                    f"Поток недоступен или не является аудио. Попробуйте другую станцию."
                )
        except Exception as e:
            logger.error(f"Ошибка уведомления: {e}")

    async def play_url(self, guild_id: int, url: str, name: str, notify_channel_id: int = None) -> bool:
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            return False
        if vc.is_playing() or vc.is_paused():
            vc.stop()
        try:
            source = FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
            vc.play(source, after=lambda e: self._after_play(e, guild_id, name, notify_channel_id))
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

        query = query.strip()

        # Если пользователь ввёл URL напрямую — проверяем, что он не похож на веб-страницу
        if query.startswith(("http://", "https://")):
            classification = _classify_url(query)
            if classification is False:
                return (
                    f"❌ URL «{query}» похож на веб-страницу, а не на аудиопоток.\n"
                    f"Укажите прямую ссылку на поток — обычно она заканчивается на "
                    f"`.mp3`, `.m3u8` или содержит `:8000/`."
                )

        resolved = await self.resolve_station(query)
        if not resolved:
            return (
                f"❌ Станция «{query}» не найдена. Попробуйте другое название "
                f"(например, `Radio Record`, `Europa Plus`, `DFM`) или укажите прямой URL потока."
            )
        name, url = resolved
        ok = await self.play_url(guild_id, url, name, notify_channel_id=RADIO_TEXT_CHANNEL_ID)
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
        self.bot = bot
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
                await self.play_url(guild_id, url, name, notify_channel_id=RADIO_TEXT_CHANNEL_ID)
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
        placeholder="Например: Radio Record, Europa Plus или https://stream.example.com/radio.mp3",
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
