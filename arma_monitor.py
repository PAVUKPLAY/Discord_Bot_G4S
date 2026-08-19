import a2s
import re
import discord
from datetime import datetime, timezone
import logging
from config import SERVER_IP, SERVER_PORT, TARGET_CHANNEL_ID, ALLOWED_TAGS

logger = logging.getLogger(__name__)

def get_load_bar(current, max_val):
    if max_val <= 0:
        return "░" * 10
    percent = current / max_val
    squares = max(0, min(10, int(percent * 10)))
    return "█" * squares + "░" * (10 - squares)

def fetch_server_data():
    info = a2s.info((SERVER_IP, SERVER_PORT), timeout=4.0)
    try:
        players = a2s.players((SERVER_IP, SERVER_PORT), timeout=4.0)
    except Exception:
        players = []
    return info, players

def is_player_allowed(nickname):
    if not nickname:
        return False
    if nickname.strip() == "Leo Williams":
        return False
    nickname_lower = nickname.lower()

    if "[g4s]" in nickname_lower:
        return True

    if nickname.isupper():
        return False
    if re.search(r'\d', nickname):
        return False

    has_allowed_tag = any(f"[{tag}]" in nickname_lower for tag in ALLOWED_TAGS)
    if not has_allowed_tag and ("[" in nickname_lower or "]" in nickname_lower):
        return False

    clean_name = re.sub(r'\[.*?\]', '', nickname)
    words = [w for w in clean_name.split() if w.strip()]

    has_ru = any(re.search(r'[а-яА-ЯёЁ]', w) for w in words)
    has_en = any(re.search(r'[a-zA-Z]', w) for w in words)

    if has_ru and has_en:
        return False

    if has_ru:
        if len(words) != 2:
            return False
    else:
        if len(words) not in (2, 3):
            return False

    if not all(w[0].isupper() for w in words):
        return False

    return True

def chunk_player_list(players_list, style_type=None):
    chunks = []
    current_chunk = ""
    for player in players_list:
        if style_type == "red":
            line = f"\u001b[31m{player}\u001b[0m\n"
        elif style_type == "green":
            line = f"\u001b[32m{player}\u001b[0m\n"
        elif style_type == "blue":
            line = f"\u001b[34m{player}\u001b[0m\n"
        elif style_type == "yellow":
            line = f"\u001b[33m{player}\u001b[0m\n"
        else:
            line = f"{player}\n"
        if len(current_chunk) + len(line) > 950:
            chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += line
    if current_chunk:
        chunks.append(current_chunk)
    return chunks

async def update_status(bot, monitor_message):
    try:
        await bot.wait_until_ready()
        channel = bot.get_channel(TARGET_CHANNEL_ID)
        if not channel:
            try:
                channel = await bot.fetch_channel(TARGET_CHANNEL_ID)
            except Exception as e:
                logger.error(f"Не удалось найти канал с ID {TARGET_CHANNEL_ID}: {e}")
                return monitor_message

        current_unix_time = int(datetime.now(timezone.utc).timestamp())

        try:
            info, players_list = await bot.loop.run_in_executor(None, fetch_server_data)
            if info.player_count > 0:
                status_text = "🟢 АКТИВЕН"
            else:
                status_text = "🟡 НИЗКАЯ АКТИВНОСТЬ"
            online_text = f"{info.player_count}/{info.max_players}"
            load_bar = get_load_bar(info.player_count, info.max_players)

            all_names = [p.name for p in players_list]
            allowed_players = [p.name for p in players_list if is_player_allowed(p.name)]

            g4s_players = sorted([p for p in allowed_players if "[g4s]" in p.lower()])
            remaining_players = [p for p in allowed_players if p not in g4s_players]
            ru_players = sorted([p for p in remaining_players if re.search(r'[а-яА-ЯёЁ]', p)])
            en_players = sorted([p for p in remaining_players if p not in ru_players])

            non_allowed_players = [p for p in all_names if p not in allowed_players]

        except Exception as e:
            logger.error(f"Ошибка получения данных от Arma 3: {e}")
            status_text = "🔴 НЕДОСТУПЕН"
            online_text = "0/0"
            load_bar = "░" * 10
            g4s_players = []
            ru_players, en_players = [], []
            non_allowed_players = []

        content_block = (
            f"```\n"
            f"📡 СТАТУС       | {status_text}\n"
            f"👥 ОНЛАЙН       | {online_text}\n"
            f"🖥️ СЕРВЕР       | {SERVER_IP}:{SERVER_PORT}\n"
            f"📊 НАГРУЗКА     | {load_bar}\n"
            f"```"
        )

        embed = discord.Embed(
            title="🛡️ «Спектр Войны» • Мониторинг G4S",
            color=discord.Color.dark_theme() if "НЕДОСТУПЕН" not in status_text else discord.Color.red()
        )
        embed.description = content_block

        if allowed_players:
            ru_chunks = chunk_player_list(ru_players, "green")
            en_chunks = chunk_player_list(en_players, "blue")
            max_chunks = max(len(ru_chunks), len(en_chunks))
            if max_chunks > 0:
                for i in range(max_chunks):
                    ru_field_name = "🇿🇲 Повстанцы:" if i == 0 else "⠀"
                    en_field_name = "🧭 EAA:" if i == 0 else "⠀"
                    ru_value = f"```ansi\n{ru_chunks[i]}```" if i < len(ru_chunks) else "```\n—\n```"
                    en_value = f"```ansi\n{en_chunks[i]}```" if i < len(en_chunks) else "```\n—\n```"
                    embed.add_field(name=ru_field_name, value=ru_value, inline=True)
                    embed.add_field(name=en_field_name, value=en_value, inline=True)

            if g4s_players:
                g4s_chunks = chunk_player_list(g4s_players, "red")
                for i, chunk in enumerate(g4s_chunks):
                    g4s_field_name = "🛡️ Подразделение [G4S]:" if i == 0 else "⠀"
                    embed.add_field(name=g4s_field_name, value=f"```ansi\n{chunk}```", inline=False)
        else:
            embed.add_field(name="👥 Активные бойцы:", value="```\nПодходящие игроки на сервере отсутствуют.\n```", inline=False)

        if non_allowed_players:
            other_chunks = chunk_player_list(non_allowed_players, "yellow")
            for i, chunk in enumerate(other_chunks):
                field_name = "🌍 Все игроки:" if i == 0 else "⠀"
                embed.add_field(name=field_name, value=f"```ansi\n{chunk}```", inline=False)
        else:
            embed.add_field(name="🌍 Все игроки:", value="```\nНет дополнительных игроков.\n```", inline=False)

        embed.add_field(
            name="⠀",
            value=f"🛡️ G4S • Live Monitor • Обновлено <t:{current_unix_time}:R>",
            inline=False
        )

        if monitor_message is None:
            async for msg in channel.history(limit=15):
                if msg.author == bot.user and msg.embeds:
                    monitor_message = msg
                    break

        if monitor_message:
            try:
                await monitor_message.edit(embed=embed)
            except discord.NotFound:
                monitor_message = await channel.send(embed=embed)
        else:
            monitor_message = await channel.send(embed=embed)

        await bot.change_presence(activity=discord.Game(name=f"Онлайн: {online_text}"))
        logger.debug(f"Мониторинг обновлён: {online_text}, карта {map_name if 'map_name' in locals() else 'unknown'}")
        return monitor_message

    except Exception as e:
        logger.error(f"Критическая ошибка в цикле автообновления: {e}")
        return monitor_message

async def cleanup_monitor(bot):
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not channel:
        logger.warning("Канал мониторинга не найден для очистки")
        return
    async for msg in channel.history(limit=100):
        if msg.author == bot.user and msg.embeds:
            for embed in msg.embeds:
                if embed.title and "Мониторинг G4S" in embed.title:
                    await msg.delete()
                    logger.info(f"Удалено старое сообщение мониторинга {msg.id}")
                    break
