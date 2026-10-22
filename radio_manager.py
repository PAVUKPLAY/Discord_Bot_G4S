import discord
import aiohttp
import asyncio
import logging
from discord import FFmpegPCMAudio, PCMVolumeTransformer, ui
from urllib.parse import urlparse
from config import RADIO_VOICE_CHANNEL_ID, RADIO_TEXT_CHANNEL_ID, RADIO_DEFAULT_STATION, RADIO_DEFAULT_VOLUME
from utils import has_moderator_role
from toggle_manager import get_status

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
    try: parsed = urlparse(url)
    except Exception: return False
    if not parsed.scheme or not parsed.netloc: return False
    path = (parsed.path or "").lower()
    if any(path.endswith(ext) for ext in AUDIO_EXTENSIONS): return True
    if parsed.port and parsed.port in (8000, 8001, 8080, 8443, 9000): return True
    if any(kw in path for kw in STREAM_KEYWORDS): return True
    if path in ("", "/", "/index.html", "/index.htm", "/index.php"): return False
    return None

async def _ensure_user_in_bot_voice(interaction: discord.Interaction, radio_manager: 'RadioManager') -> bool:
    vc = radio_manager.voice_clients.get(interaction.guild_id)
    if not vc or not vc.is_connected():
        await interaction.response.send_message("❌ Бот не подключён к голосовому каналу.", ephemeral=True)
        return False
    user_voice = getattr(interaction.user, "voice", None)
    if not user_voice or not user_voice.channel:
        await interaction.response.send_message(f"❌ Вы должны находиться в голосовом канале {vc.channel.mention}.", ephemeral=True)
        return False
    if user_voice.channel.id != vc.channel.id:
        await interaction.response.send_message(f"❌ Вы должны находиться в голосовом канале {vc.channel.mention}.", ephemeral=True)
        return False
    return True

class RadioManager:
    def __init__(self):
        self.voice_clients = {}
        self.current_stations = {}
        self.current_urls = {}
        self.control_messages = {}
        self.control_views = {}
        self.bot = None
        self.stopping = set()
        self.retry_count = {}
        self.retry_tasks = {}
        self.volumes = {}

    def _get_volume(self, guild_id: int) -> float:
        return self.volumes.get(guild_id, RADIO_DEFAULT_VOLUME)

    def _create_source(self, url: str, guild_id: int) -> PCMVolumeTransformer:
        raw = FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
        return PCMVolumeTransformer(raw, volume=self._get_volume(guild_id))

    async def search_stations(self, query: str) -> list:
        url = f"{RADIO_API_BASE}/stations/search"
        params = {"name": query, "limit": 20, "hidebroken": "true", "order": "clickcount", "reverse": "true"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status != 200: return []
                    stations = await resp.json()
                    results = []
                    seen_names = set()
                    for st in stations:
                        if st.get("lastcheckok", 1) == 0: continue
                        stream_url = st.get("url_resolved") or st.get("url")
                        if not stream_url or not stream_url.startswith(("http://", "https://")): continue
                        if _classify_url(stream_url) is not True: continue
                        name = st.get("name", "Неизвестная станция")
                        if name.lower() in seen_names: continue
                        seen_names.add(name.lower())
                        results.append({"name": name, "url": stream_url})
                        if len(results) >= 5: break
                    return results
        except Exception:
            return []

    async def connect_voice(self, channel: discord.VoiceChannel):
        guild_id = channel.guild.id
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_connected():
            if vc.channel.id != channel.id:
                try: await vc.move_to(channel)
                except: return None
            return vc
        try:
            vc = await channel.connect(timeout=25, reconnect=True)
            self.voice_clients[guild_id] = vc
            return vc
        except: return None

    async def disconnect_voice(self, guild_id: int) -> str:
        vc = self.voice_clients.get(guild_id)
        self.stopping.add(guild_id) 
        if vc and vc.is_connected():
            if vc.is_playing() or vc.is_paused(): vc.stop()
            await vc.disconnect()
        self.voice_clients.pop(guild_id, None)
        self.current_stations.pop(guild_id, None)
        self.current_urls.pop(guild_id, None)
        task = self.retry_tasks.get(guild_id)
        if task and not task.done(): task.cancel()
        await self.update_control_panel(guild_id)
        return "🔌 Бот отключён."

    async def _notify(self, text: str):
        if not (self.bot and RADIO_TEXT_CHANNEL_ID): return
        try:
            channel = self.bot.get_channel(RADIO_TEXT_CHANNEL_ID)
            if channel: await channel.send(text)
        except: pass

    def _after_play(self, error, guild_id: int, name: str, url: str):
        if error is None: return
        if guild_id in self.stopping:
            self.stopping.discard(guild_id)
            return
        self.current_stations.pop(guild_id, None)
        if self.bot:
            asyncio.run_coroutine_threadsafe(self._retry_stream(guild_id, name, url), self.bot.loop)

    async def _retry_stream(self, guild_id: int, name: str, url: str):
        if guild_id in self.retry_tasks and not self.retry_tasks[guild_id].done(): return
        task = asyncio.create_task(self._retry_loop(guild_id, name, url))
        self.retry_tasks[guild_id] = task

    async def _retry_loop(self, guild_id: int, name: str, url: str):
        attempt = self.retry_count.get(guild_id, 0)
        while attempt < MAX_RETRIES:
            attempt += 1
            self.retry_count[guild_id] = attempt
            await asyncio.sleep(RETRY_DELAY)
            vc = self.voice_clients.get(guild_id)
            if not vc or not vc.is_connected():
                await self._reconnect_voice(guild_id)
                vc = self.voice_clients.get(guild_id)
                if not vc or not vc.is_connected(): continue
            try:
                source = self._create_source(url, guild_id)
                vc.play(source, after=lambda e: self._after_play(e, guild_id, name, url))
                self.current_stations[guild_id] = name
                self.retry_count[guild_id] = 0
                await self.update_control_panel(guild_id)
                await self._notify(f"🔄 Радио «{name}» перезапущено.")
                return
            except: pass
        await self._notify(f"⚠️ Не удалось восстановить поток «{name}».")
        self.retry_count[guild_id] = 0

    async def _reconnect_voice(self, guild_id: int):
        if not RADIO_VOICE_CHANNEL_ID: return
        channel = self.bot.get_channel(RADIO_VOICE_CHANNEL_ID) if self.bot else None
        if not channel: return
        try:
            self.voice_clients.pop(guild_id, None)
            await self.connect_voice(channel)
        except: pass

    async def play_url(self, guild_id: int, url: str, name: str, notify_channel_id: int = None) -> bool:
        vc = self.voice_clients.get(guild_id)
        if not vc or not vc.is_connected(): return False
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
            return True
        except: return False

    async def set_volume(self, guild_id: int, percent: int) -> str:
        if percent < 0 or percent > 200: return "❌ Громкость должна быть 0–200%."
        volume = percent / 100.0
        self.volumes[guild_id] = volume
        vc = self.voice_clients.get(guild_id)
        if vc and vc.source and isinstance(vc.source, PCMVolumeTransformer):
            vc.source.volume = volume
        return f"🔊 Громкость: **{percent}%**"

    async def auto_start(self, bot):
        self.bot = bot
        if not get_status("radio_enabled", True) or not RADIO_VOICE_CHANNEL_ID: return
        await bot.wait_until_ready()
        channel = bot.get_channel(RADIO_VOICE_CHANNEL_ID)
        if not channel:
            try: channel = await bot.fetch_channel(RADIO_VOICE_CHANNEL_ID)
            except: return
        vc = await self.connect_voice(channel)
        if not vc: return
        guild_id = channel.guild.id
        if RADIO_DEFAULT_STATION:
            stations = await self.search_stations(RADIO_DEFAULT_STATION)
            if stations: await self.play_url(guild_id, stations[0]["url"], stations[0]["name"], notify_channel_id=RADIO_TEXT_CHANNEL_ID)
        if RADIO_TEXT_CHANNEL_ID: await self.ensure_control_panel(bot, RADIO_TEXT_CHANNEL_ID)

    def _build_embed(self, guild_id: int) -> discord.Embed:
        current = self.current_stations.get(guild_id, "Ничего не играет")
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_playing(): status = "🟢 Играет"
        elif vc and vc.is_paused(): status = "⏸️ Пауза"
        else: status = "⏹️ Остановлено"
        volume_pct = int(self._get_volume(guild_id) * 100)
        embed = discord.Embed(
            title="📻 Радио G4S",
            description=f"**Станция:** {current}\n**Статус:** {status}\n**Громкость:** 🔊 {volume_pct}%",
            color=discord.Color.purple()
        )
        embed.set_footer(text="Смена станции — голосование | Code by PAVUK")
        return embed

    async def ensure_control_panel(self, bot, channel_id: int):
        channel = bot.get_channel(channel_id)
        if not channel:
            try: channel = await bot.fetch_channel(channel_id)
            except: return
        guild_id = channel.guild.id
        async for msg in channel.history(limit=50):
            if msg.author == bot.user and msg.components:
                for row in msg.components:
                    for comp in row.children:
                        if hasattr(comp, "custom_id") and comp.custom_id == "radio_change":
                            try: await msg.delete()
                            except: pass
                            break
        embed = self._build_embed(guild_id)
        view = RadioControlView(self)
        msg = await channel.send(embed=embed, view=view)
        self.control_messages[guild_id] = msg
        self.control_views[guild_id] = view

    async def update_control_panel(self, guild_id: int):
        msg = self.control_messages.get(guild_id)
        if not msg: return
        try: await msg.edit(embed=self._build_embed(guild_id), view=self.control_views.get(guild_id))
        except: pass

class OpenChangeModalView(ui.View):
    def __init__(self, radio_manager: RadioManager):
        super().__init__(timeout=120)
        self.radio_manager = radio_manager

    @ui.button(label="Выбрать станцию", style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, button: ui.Button):
        if not await _ensure_user_in_bot_voice(interaction, self.radio_manager): return
        await interaction.response.send_modal(ChangeStationModal(self.radio_manager))
        self.stop()

class RadioChangeVoteView(ui.View):
    def __init__(self, radio_manager: RadioManager, original_interaction: discord.Interaction, voice_channel: discord.VoiceChannel):
        super().__init__(timeout=120)
        self.radio_manager = radio_manager
        self.original_interaction = original_interaction
        self.voice_channel = voice_channel
        self.votes_yes = set()
        self.votes_no = set()
        self.message = None
        vc_members = [m for m in voice_channel.members if not m.bot]
        self.total_members = len(vc_members)
        self.required_votes = (self.total_members // 2) + 1

    async def update_vote_embed(self):
        if not self.message: return
        embed = self.message.embeds[0]
        remaining = self.total_members - len(self.votes_yes) - len(self.votes_no)
        embed.clear_fields()
        embed.add_field(name="✅ За", value=f"**{len(self.votes_yes)}**", inline=True)
        embed.add_field(name="❌ Против", value=f"**{len(self.votes_no)}**", inline=True)
        embed.add_field(name="🤷 Не голосовали", value=f"**{remaining}**", inline=True)
        try: await self.message.edit(embed=embed, view=self)
        except: pass

    async def check_result(self, interaction: discord.Interaction) -> bool:
        if len(self.votes_yes) >= self.required_votes:
            self.stop()
            if self.message:
                try: await self.message.delete()
                except: pass
            try:
                await self.original_interaction.followup.send("✅ Большинство проголосовало **ЗА**. Вы можете выбрать станцию.", view=OpenChangeModalView(self.radio_manager), ephemeral=True)
            except: pass
            return True
        remaining = self.total_members - len(self.votes_yes) - len(self.votes_no)
        if len(self.votes_yes) + remaining < self.required_votes:
            self.stop()
            if self.message:
                try: await self.message.delete()
                except: pass
            try:
                await self.original_interaction.followup.send("❌ Участники проголосовали **ПРОТИВ**. Смена отменена.", ephemeral=True)
            except: pass
            return True
        return False

    @ui.button(label="✋ Я за", style=discord.ButtonStyle.success, custom_id="radio_vote_yes")
    async def vote_yes(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.voice or interaction.user.voice.channel.id != self.voice_channel.id:
            await interaction.response.send_message("❌ Вы должны быть в канале.", ephemeral=True)
            return
        if interaction.user.id in self.votes_yes:
            await interaction.response.send_message("❌ Вы уже проголосовали ЗА.", ephemeral=True)
            return
        if interaction.user.id in self.votes_no: self.votes_no.remove(interaction.user.id)
        self.votes_yes.add(interaction.user.id)
        await interaction.response.send_message(f"✅ Ваш голос учтен!", ephemeral=True)
        await self.update_vote_embed()
        await self.check_result(interaction)

    @ui.button(label="❌ Я против", style=discord.ButtonStyle.danger, custom_id="radio_vote_no")
    async def vote_no(self, interaction: discord.Interaction, button: ui.Button):
        if not interaction.user.voice or interaction.user.voice.channel.id != self.voice_channel.id:
            await interaction.response.send_message("❌ Вы должны быть в канале.", ephemeral=True)
            return
        if interaction.user.id in self.votes_no:
            await interaction.response.send_message("❌ Вы уже проголосовали ПРОТИВ.", ephemeral=True)
            return
        if interaction.user.id in self.votes_yes: self.votes_yes.remove(interaction.user.id)
        self.votes_no.add(interaction.user.id)
        await interaction.response.send_message(f"❌ Ваш голос против учтен!", ephemeral=True)
        await self.update_vote_embed()
        await self.check_result(interaction)

    async def on_timeout(self):
        if self.message:
            try: await self.message.delete()
            except: pass
        try: await self.original_interaction.followup.send("⏳ Время голосования истекло. Смена отменена.", ephemeral=True)
        except: pass

class ChangeStationModal(ui.Modal, title="Смена радиостанции"):
    station = ui.TextInput(label="Название станции или URL", placeholder="Radio Record, Europa Plus или https://...", required=True, max_length=200)

    def __init__(self, radio_manager: RadioManager):
        super().__init__()
        self.radio_manager = radio_manager

    async def on_submit(self, interaction: discord.Interaction):
        if not await _ensure_user_in_bot_voice(interaction, self.radio_manager): return
        await interaction.response.defer(ephemeral=True)
        query = self.station.value.strip()
        
        if query.startswith(("http://", "https://")):
            if _classify_url(query) is False:
                await interaction.followup.send(f"❌ URL не похож на поток.", ephemeral=True)
                return
            ok = await self.radio_manager.play_url(interaction.guild_id, query, query, notify_channel_id=RADIO_TEXT_CHANNEL_ID)
            if ok: await interaction.followup.send(f"📻 Воспроизводится прямой поток.", ephemeral=True)
            else: await interaction.followup.send("❌ Не удалось запустить поток.", ephemeral=True)
            await self.radio_manager.update_control_panel(interaction.guild_id)
            return

        stations = await self.radio_manager.search_stations(query)
        if not stations:
            await interaction.followup.send(f"❌ Станция не найдена.", ephemeral=True)
            return

        if len(stations) == 1:
            ok = await self.radio_manager.play_url(interaction.guild_id, stations[0]["url"], stations[0]["name"], notify_channel_id=RADIO_TEXT_CHANNEL_ID)
            if ok: await interaction.followup.send(f"📻 Воспроизводится: **{stations[0]['name']}**", ephemeral=True)
            else: await interaction.followup.send("❌ Не удалось запустить поток.", ephemeral=True)
            await self.radio_manager.update_control_panel(interaction.guild_id)
        else:
            view = StationSelectView(self.radio_manager, stations)
            await interaction.followup.send(f"Найдено несколько станций. Выберите нужную:", view=view, ephemeral=True)

class StationSelect(ui.Select):
    def __init__(self, radio_manager: RadioManager, stations: list):
        self.radio_manager = radio_manager
        self.stations = stations
        options = [discord.SelectOption(label=st["name"][:100], value=str(i)) for i, st in enumerate(stations)]
        super().__init__(placeholder="Выберите радиостанцию...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if not await _ensure_user_in_bot_voice(interaction, self.radio_manager): return
        await interaction.response.defer(ephemeral=True)
        idx = int(self.values[0])
        station = self.stations[idx]
        ok = await self.radio_manager.play_url(interaction.guild_id, station["url"], station["name"], notify_channel_id=RADIO_TEXT_CHANNEL_ID)
        if ok:
            await interaction.followup.send(f"📻 Воспроизводится: **{station['name']}**", ephemeral=True)
            await self.radio_manager.update_control_panel(interaction.guild_id)
            self.disabled = True
            await interaction.message.edit(view=None)
        else:
            await interaction.followup.send("❌ Не удалось запустить поток.", ephemeral=True)

class StationSelectView(ui.View):
    def __init__(self, radio_manager: RadioManager, stations: list):
        super().__init__(timeout=60)
        self.add_item(StationSelect(radio_manager, stations))

class VolumeModal(ui.Modal, title="Громкость радио"):
    level = ui.TextInput(label="Громкость (0–200%)", placeholder="Например: 50", required=True, min_length=1, max_length=3)

    def __init__(self, radio_manager: RadioManager):
        super().__init__()
        self.radio_manager = radio_manager

    async def on_submit(self, interaction: discord.Interaction):
        if not await _ensure_user_in_bot_voice(interaction, self.radio_manager): return
        try: percent = int(self.level.value.strip().rstrip("%"))
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
        if not await _ensure_user_in_bot_voice(interaction, self.radio_manager): return
        vc = self.radio_manager.voice_clients.get(interaction.guild_id)
        if not vc or not vc.is_connected(): return
        vc_members = [m for m in vc.channel.members if not m.bot]
        
        if len(vc_members) <= 1:
            await interaction.response.send_modal(ChangeStationModal(self.radio_manager))
            return
            
        view = RadioChangeVoteView(self.radio_manager, interaction, vc.channel)
        mentions = " ".join([m.mention for m in vc_members])
        embed = discord.Embed(
            title="🗳️ Голосование за смену радио",
            description=f"Пользователь {interaction.user.mention} хочет сменить радиостанцию.\nДля смены нужно **больше 50%** голосов.\n\nГолосуйте кнопками ниже:",
            color=discord.Color.blue()
        )
        embed.add_field(name="✅ За", value="**0**", inline=True)
        embed.add_field(name="❌ Против", value="**0**", inline=True)
        embed.add_field(name="🤷 Не голосовали", value=f"**{view.total_members}**", inline=True)
        embed.set_footer(text="Code by PAVUK")
        msg = await interaction.channel.send(content=mentions, embed=embed, view=view)
        view.message = msg
        await interaction.response.send_message("Запущено голосование в канале.", ephemeral=True)

    @ui.button(label="🔊 Громкость", style=discord.ButtonStyle.secondary, custom_id="radio_volume")
    async def volume(self, interaction: discord.Interaction, button: ui.Button):
        if not await _ensure_user_in_bot_voice(interaction, self.radio_manager): return
        await interaction.response.send_modal(VolumeModal(self.radio_manager))
