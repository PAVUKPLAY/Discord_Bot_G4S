import discord
import aiohttp
import logging
from discord import FFmpegPCMAudio

logger = logging.getLogger(__name__)

RADIO_API_BASE = "https://de1.api.radio-browser.info/json"

# Опции FFmpeg для стабильного воспроизведения потока
# -reconnect: переподключаться при обрыве
# -reconnect_streamed: переподключаться для потоковых источников
# -timeout: таймаут в микросекундах (30 секунд)
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -timeout 30000000",
    "options": "-vn"  # отключаем видео, только аудио
}

class RadioManager:
    def __init__(self):
        self.voice_clients: dict[int, discord.VoiceClient] = {}
        self.current_stations: dict[int, str] = {}  # guild_id -> название станции

    async def search_station(self, query: str) -> dict | None:
        """Ищет станцию по названию через Radio Browser API."""
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
                    if not stations:
                        return None
                    # Берём первую станцию с рабочим URL
                    for st in stations:
                        stream_url = st.get("url_resolved") or st.get("url")
                        if stream_url and stream_url.startswith(("http://", "https://")):
                            return {
                                "name": st.get("name", "Неизвестная станция"),
                                "url": stream_url,
                                "country": st.get("country", ""),
                                "tags": st.get("tags", "")
                            }
                    return None
        except Exception as e:
            logger.error(f"Ошибка поиска станции '{query}': {e}")
            return None

    async def join_and_play(self, interaction: discord.Interaction, query: str) -> str:
        """Подключается к голосовому каналу и запускает поток. Возвращает сообщение об успехе/ошибке."""
        if not interaction.user.voice or not interaction.user.voice.channel:
            return "❌ Вы должны находиться в голосовом канале."

        channel = interaction.user.voice.channel
        guild_id = interaction.guild_id

        # Подключаемся или перемещаемся
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_connected():
            if vc.channel != channel:
                await vc.move_to(channel)
        else:
            try:
                vc = await channel.connect(timeout=25, reconnect=True)
                self.voice_clients[guild_id] = vc
            except Exception as e:
                logger.error(f"Ошибка подключения к голосовому каналу: {e}")
                return f"❌ Не удалось подключиться к каналу: {e}"

        # Ищем станцию или используем прямую ссылку
        stream_url = None
        station_name = query
        if query.startswith(("http://", "https://")):
            stream_url = query
        else:
            station = await self.search_station(query)
            if station:
                stream_url = station["url"]
                station_name = station["name"]
            else:
                return f"❌ Станция «{query}» не найдена в каталоге Radio Browser."

        # Останавливаем текущий поток, если играет
        if vc.is_playing() or vc.is_paused():
            vc.stop()

        try:
            source = FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
            vc.play(source)
            self.current_stations[guild_id] = station_name
            logger.info(f"Запущено радио «{station_name}» в гильдии {guild_id}")
            return f"📻 Воспроизводится: **{station_name}**"
        except Exception as e:
            logger.error(f"Ошибка FFmpeg при запуске потока: {e}")
            return f"❌ Не удалось запустить поток: {e}"

    async def stop(self, guild_id: int) -> bool:
        vc = self.voice_clients.get(guild_id)
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            self.current_stations.pop(guild_id, None)
            return True
        return False

    async def leave(self, guild_id: int) -> bool:
        vc = self.voice_clients.get(guild_id)
        if vc and vc.is_connected():
            await vc.disconnect()
            self.voice_clients.pop(guild_id, None)
            self.current_stations.pop(guild_id, None)
            return True
        return False
