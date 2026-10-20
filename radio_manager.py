import discord
import aiohttp
import asyncio
import logging
from discord import FFmpegPCMAudio, PCMVolumeTransformer, ui
from urllib.parse import urlparse
from config import RADIO_VOICE_CHANNEL_ID, RADIO_TEXT_CHANNEL_ID, RADIO_DEFAULT_STATION, RADIO_DEFAULT_VOLUME
from utils import has_moderator_role

logger = logging.getLogger(__name__)

RADIO_API_BASE = "https://de1.api.radio-browser.info/json"

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -timeout 30000000",
    "options": "-vn"
}

AUDIO_EXTENSIONS = (".mp3", ".aac", ".ogg", ".m3u8", ".m3u", ".pls", ".opus", ".flac", ".wav", ".mp4", ".webm")
STREAM_KEYWORDS = ("stream", "live", "radio", "listen", "air", "broadcast", "play", "icecast", "shoutcast", "audio")

MAX_RETRIES = 5
RETRY_DELAY = 10


def _classify_url(url: str):
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if not parsed.scheme or not parsed.netloc:
        return False
    path = (parsed.path or "").lower()
    if any(path.endswith(ext) for ext in AUDIO_EXTENSIONS):
        return True
    if parsed.port and parsed.port in (8000, 8001, 8080, 8443, 9000):
        return True
    if any(kw in path for kw in STREAM_KEYWORDS):
        return True
    if path in ("", "/", "/index.html", "/index.htm", "/index.php"):
        return False
    return None


async def _ensure_user_in_bot_voice(interaction: discord.Interaction, radio_manager: 'RadioManager') -> bool:
    vc = radio_manager.voice_clients.get(interaction.guild_id)
    if not vc or not vc.is_connected():
        await interaction.response.send_message(
            "❌ Бот не подключён к голосовому каналу.",
            ephemeral=True
        )
        return False

    user_voice = getattr(interaction.user, "voice", None)
    if not user_voice or not user_voice.channel:
        await interaction.response.send_message(
            f"❌ Чтобы управлять радио, вы должны находиться в голосовом канале {vc.channel.mention}.",
            ephemeral=True
        )
        return False

    if user_voice.channel.id != vc.channel.id:
        await interaction.response.send_message(
            f"❌ Вы должны находиться в голосовом канале {vc.channel.mention}, чтобы управлять радио.",
            ephemeral=True
        )
        return False

    return True


async def _ensure_moderator(interaction: discord.Interaction) -> bool:
    if not has_moderator_role(interaction.user):
        await interaction.response.send_message(
            "❌ Эта кнопка доступна только модераторам.",
            ephemeral=True
        )
        return False
    return True


class RadioManager:
    def __init__(self):
        self.voice_clients: dict[int, discord.VoiceClient] = {}
        self.current_stations: dict[int, str] = {}
        self.current_urls: dict[int, str] = {}
        self.control_messages: dict[int, discord.Message] = {}
        self.bot = None
        self.stopping: set[int] = set()
        self.retry_count: dict[int, int] = {}
        self.retry_tasks: dict[int, asyncio.Task] = {}
        self.volumes: dict[int, float] = {}  # guild_id -> volume (0.0–2.0)

    def _get_volume(self, guild_id: int) -> float:
        return self.volumes.get(guild_id, RADIO_DEFAULT_VOLUME)

    def _create_source(self, url: str, guild_id: int) -> PCMVolumeTransformer:
        """Создаёт FFmpegPCMAudio и оборачивает в VolumeTransformer с текущей громкостью."""
        raw = FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
        return PCMVolumeTransformer(raw, volume=self._get_volume(guild_id))

    async def search_station(self, query: str):
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
            logger.info(f"Подключено к голосовому каналу {channel.name} (громкость: {int(self._get_volume(guild_id) * 100)}%)")
            return vc
        except Exception as e:
            logger.error(f"Voice connect error: {e}")
            return None

    async def _notify(self, text: str):
        if not (self.bot and RADIO_TEXT_CHANNEL_ID):
            return
        try:
            channel = self.bot.get_channel(RADIO_TEXT_CHANNEL_ID)
            if channel:
                await channel.send(text)
        except Exception as e:
            logger.error(f"Ошибка уведомления: {e}")

    def _after_play(self, error, guild_id: int, name: str, url: str):
        if error is None:
            logger.info(f"Поток '{name}' завершён штатно")
            return
        if guild_id in self.stopping:
            logger.info(f"Поток '{name}' остановлен вручную")
            self.stopping.discard(guild_id)
            return
        logger.warning(f"Поток '{name}' прервался: {error}. Пробую перезапустить...")
        self.current_stations.pop(guild_id, None)
        if self.bot:
            asyncio.run_coroutine_threadsafe(
                self._retry_stream(guild_id, name, url),
                self.bot.loop
            )

    async def _retry_stream(self, guild_id: int, name: str, url: str):
        if guild_id in self.retry_tasks and not self.retry_tasks[guild_id].done():
            return
        task = asyncio.create_task(self._retry_loop(guild_id, name, url))
        self.retry_tasks[guild_id] = task

    async def _retry_loop(self, guild_id: int, name: str, url: str):
        attempt = self.retry_count.get(guild_id, 0)
        while attempt < MAX_RETRIES:
            attempt += 1
            self.retry_count[guild_id] = attempt
            logger.info(f"Перезапуск '{name}' (попытка {attempt}/{MAX_RETRIES}) через {RETRY_DELAY}с...")
            await asyncio.sleep(RETRY_DELAY)

            vc = self.voice_clients.get(guild_id)
            if not vc or not vc.is_connected():
                logger.warning("Голосовое соединение потеряно — попытка переподключения...")
                await self._reconnect_voice(guild_id)
                vc = self.voice_clients.get(guild_id)
                if not vc or not vc.is_connected():
                    continue

            try:
                source = self._create_source(url, guild_id)
                vc.play(source, after=lambda e: self._after_play(e, guild_id, name, url))
                self.current_stations[guild_id] = name
                self.retry_count[guild_id] = 0
                logger.info(f"Перезапущено '{name}' в гильдии {guild_id}")
                await self.update_control_panel(guild_id)
                await self._notify(f"🔄 Радио «{name}» перезапущено после обрыва.")
                return
            except Exception as e:
                logger.error(f"Ошибка перезапуска '{name}': {e}")

        logger.error(f"Не удалось восстановить '{name}' после {MAX_RETRIES} попыток.")
        await self._notify(
            f"⚠️ Не удалось восстановить поток «{name}» после {MAX_RETRIES} попыток. "
            f"Смените станцию вручную."
        )
        self.retry_count[guild_id] = 0

    async def _reconnect_voice(self, guild_id: int):
        if not RADIO_VOICE_CHANNEL_ID:
            return
        channel = self.bot.get_channel(RADIO_VOICE_CHANNEL_ID) if self.bot else None
        if not channel:
            return
        try:
            self.voice_clients.pop(guild_id, None)
            await self.connect_voice(channel)
        except Exception as e:
            logger.error(f"Ошибка переподключения к голосу: {e}")

    async def play_url(self, guild_id: int, url: str, name: str, notify_channel_id: int = None) -> bool:
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            return False
        if vc.is_playing() or vc.is_paused():
            self.stopping.add(guild_id)
            vc.stop()
            await asyncio.sleep(0.2)
        try:
            source = self._create_source(url, guild_id)
            vc.play(source, after=lambda e: self._after_play(e, guild_id, name, url))
            self.current_stations[guild_id] = name
            self.current_urls[guild_id] = url
            self.retry_count[guild_id] = 0
            logger.info(f"Играет '{name}' в гильдии {guild_id} (громкость: {int(self._get_volume(guild_id) * 100)}%)")
            return True
        except Exception as e:
            logger.error(f"FFmpeg error: {e}")
            return False

    async def change_station(self, guild_id: int, query: str) -> str:
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected():
            return "❌ Бот не подключён к голосовому каналу."
        query = query.strip()
        if query.startswith(("http://", "https://")):
            if _classify_url(query) is False:
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
        if vc.is_playing() or vc.is_paused():
            self.stopping.add(guild_id)
            vc.stop()
            await asyncio.sleep(0.2)
        task = self.retry_tasks.get(guild_id)
        if task and not task.done():
            task.cancel()
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
            self.stopping.add(guild_id)
            vc.stop()
            self.current_stations.pop(guild_id, None)
            self.current_urls.pop(guild_id, None)
            self.retry_count[guild_id] = 0
            task = self.retry_tasks.get(guild_id)
            if task and not task.done():
                task.cancel()
            return "⏹️ Радио остановлено."
        return "❌ Сейчас ничего не играет."

    async def set_volume(self, guild_id: int, percent: int) -> str:
        """Устанавливает громкость в процентах (0–200). Применяется сразу."""
        if percent < 0 or percent > 200:
            return "❌ Громкость должна быть в диапазоне 0–200%."
        volume = percent / 100.0
        self.volumes[guild_id] = volume
        vc = self.voice_clients.get(guild_id)
        if vc and vc.source and isinstance(vc.source, PCMVolumeTransformer):
            vc.source.volume = volume
        logger.info(f"Громкость в гильдии {guild_id} установлена на {percent}%")
        return f"🔊 Громкость: **{percent}%**"

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
        volume_pct = int(self._get_volume(guild_id) * 100)
        embed = discord.Embed(
            title="📻 Радио G4S",
            description=(
                f"**Станция:** {current}\n"
                f"**Статус:** {status}\n"
                f"**Громкость:** 🔊 {volume_pct}%"
            ),
            color=discord.Color.purple()
        )
        embed.set_footer(text="Смена станции — участники голосового канала • Пауза/Стоп — модераторы в голосовом канале")
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
        if not await _ensure_user_in_bot_voice(interaction, self.radio_manager):
            return
        await interaction.response.defer(ephemeral=True)
        result = await self.radio_manager.change_station(interaction.guild_id, self.station.value)
        await interaction.followup.send(result, ephemeral=True)
        await self.radio_manager.update_control_panel(interaction.guild_id)


class VolumeModal(ui.Modal, title="Громкость радио"):
    level = ui.TextInput(
        label="Громкость (0–200%)",
        placeholder="Например: 50",
        required=True,
        min_length=1,
        max_length=3
    )

    def __init__(self, radio_manager: RadioManager):
        super().__init__()
        self.radio_manager = radio_manager

    async def on_submit(self, interaction: discord.Interaction):
        if not await _ensure_user_in_bot_voice(interaction, self.radio_manager):
            return
        try:
            percent = int(self.level.value.strip().rstrip("%"))
        except ValueError:
            await interaction.response.send_message("❌ Введите целое число от 0 до 200.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        result = await self.radio_manager.set_volume(interaction.guild_id, percent)
        await interaction.followup.send(result, ephemeral=True)
        await self.radio_manager.update_control_panel(interaction.guild_id)


class RadioControlView(ui.View):
    def __init__(self, radio_manager: RadioManager):
        super().__init__(timeout=None)
        self.radio_manager = radio_manager

    @ui.button(label="🔄 Сменить станцию", style=discord.ButtonStyle.primary, custom_id="radio_change")
    async def change_station(self, interaction: discord.Interaction, button: ui.Button):
        if not await _ensure_user_in_bot_voice(interaction, self.radio_manager):
            return
        await interaction.response.send_modal(ChangeStationModal(self.radio_manager))

    @ui.button(label="🔊 Громкость", style=discord.ButtonStyle.secondary, custom_id="radio_volume")
    async def volume(self, interaction: discord.Interaction, button: ui.Button):
        if not await _ensure_user_in_bot_voice(interaction, self.radio_manager):
            return
        await interaction.response.send_modal(VolumeModal(self.radio_manager))

    @ui.button(label="⏯️ Пауза / Играть", style=discord.ButtonStyle.secondary, custom_id="radio_toggle")
    async def toggle(self, interaction: discord.Interaction, button: ui.Button):
        if not await _ensure_moderator(interaction):
            return
        if not await _ensure_user_in_bot_voice(interaction, self.radio_manager):
            return
        await interaction.response.defer(ephemeral=True)
        result = await self.radio_manager.toggle_pause(interaction.guild_id)
        await interaction.followup.send(result, ephemeral=True)
        await self.radio_manager.update_control_panel(interaction.guild_id)

    @ui.button(label="⏹️ Остановить", style=discord.ButtonStyle.danger, custom_id="radio_stop_btn")
    async def stop_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not await _ensure_moderator(interaction):
            return
        if not await _ensure_user_in_bot_voice(interaction, self.radio_manager):
            return
        await interaction.response.defer(ephemeral=True)
        result = await self.radio_manager.stop_playback(interaction.guild_id)
        await interaction.followup.send(result, ephemeral=True)
        await self.radio_manager.update_control_panel(interaction.guild_id)
