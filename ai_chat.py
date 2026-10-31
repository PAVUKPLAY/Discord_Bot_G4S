import re
import asyncio
import aiohttp
import base64
import logging
import json
import os
import tempfile
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
import edge_tts
import discord
from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL
from toggle_manager import get_status

# Безопасный импорт библиотек для аудио
try:
    from faster_whisper import WhisperModel
    from pydub import AudioSegment
    AUDIO_SUPPORT = True
except ImportError as e:
    logging.error(f"Не удалось загрузить библиотеки для голоса: {e}")
    AUDIO_SUPPORT = False

logger = logging.getLogger(__name__)

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
AI_MEMORY_FILE = os.path.join(DATA_DIR, "ai_memory.json")

whisper_model = None

def get_whisper_model():
    global whisper_model
    if not AUDIO_SUPPORT:
        return None
    if whisper_model is None:
        logger.info("Загрузка модели faster-whisper...")
        whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    return whisper_model

def load_ai_memory():
    if os.path.exists(AI_MEMORY_FILE):
        try:
            with open(AI_MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки памяти ИИ: {e}")
    return {}

def save_ai_memory(memory):
    try:
        if len(memory) > 100:
            memory = dict(list(memory.items())[-100:])
        with open(AI_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения памяти ИИ: {e}")

conversations = load_ai_memory()
msg_to_conv = {}
MAX_HISTORY_LENGTH = 15

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "Ты отвечаешь пользователю, который ценит жёсткую честность, прямоту и конкретику. Никакой воды, вежливых реверансов и этического морализаторства.\n\n"
        "СТИЛЬ:\n"
        "- Сразу к сути. Без вступлений 'отличный вопрос' и прочей шелухи.\n"
        "- Короткие рубленые фразы. Тире и двоеточия вместо длинных.\n"
        "- Разговорная лексика, мат допустим как стилистический маркер (не для оскорбления, а для плотности).\n"
        "- Сленг: 'по сути', 'чё там', 'короче', 'смотри', 'лох', 'тупость'.\n"
        "- Обращение на 'ты'. Без 'братка' и уменьшительно-ласкательных.\n"
        "- Структура: списки, развилки, чёткие выводы. В конце — встречный вопрос или жёсткий итог одной строкой.\n\n"
        "ЧЕЛОВЕЧНОСТЬ (главное):\n"
        "- Никаких научных и околонаучных терминов. Если мысль можно сказать простыми словами — говори простыми.\n"
        "- Объясняй как живому мужику за столом, а не как студенту на лекции. Примеры из жизни.\n"
        "- Не бойся разговорных оборотов: 'нахуя я тогда нужен', 'тебя надувают', 'пустоту шмотками не закроешь'.\n"
        "- Если тема сложная — разбивай на простые куски. Один тезис — одна мысль — один пример.\n\n"
        "ПОЗИЦИЯ:\n"
        "- Говоришь как есть, даже если неприятно. Не смягчаешь, не льстишь.\n"
        "- Требуешь фактов и конкретики. Спорный тезис — разбираешь, а не соглашаешься автоматически.\n"
        "- Прямо говоришь 'нет', если просят тупое, опасное или противоречивое.\n\n"
        "ЗАПРЕТЫ:\n"
        "- Никаких 'к сожалению', 'я понимаю ваши чувства', 'как ИИ я не могу'.\n"
        "- Никаких умных слов ради умности. Если слово можно заменить простым — заменяй.\n"
        "- Не соглашаешься автоматически — споришь, если собеседник несёт чушь.\n\n"
        "ВАЖНОЕ ПРАВИЛО ДЛЯ ДИАЛОГА:\n"
        "В беседе могут участвовать несколько человек. Формат входящих сообщений: '[Имя_игрока]: текст'. Учитывай это при ответе."
    )
}

def split_text(text: str, limit: int = 1990) -> list:
    if len(text) <= limit: return [text]
    chunks = []
    current_chunk = ""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= limit:
            if current_chunk: current_chunk += " " + sentence
            else: current_chunk = sentence
        else:
            if current_chunk: chunks.append(current_chunk)
            if len(sentence) > limit:
                words = sentence.split()
                temp = ""
                for word in words:
                    if len(temp) + len(word) + 1 <= limit:
                        if temp: temp += " " + word
                        else: temp = word
                    else:
                        chunks.append(temp)
                        temp = word
                if temp: current_chunk = temp
                else: current_chunk = ""
            else:
                current_chunk = sentence
    if current_chunk: chunks.append(current_chunk)
    return chunks

async def send_long_answer(destination, text):
    chunks = [c for c in split_text(text) if c.strip()]
    if not chunks: return []
    total = len(chunks)
    sent_messages = []
    for i, chunk in enumerate(chunks):
        if i == 0:
            if hasattr(destination, 'reply'): msg = await destination.reply(chunk)
            else: msg = await destination.send(chunk)
        else:
            if hasattr(destination, 'channel'): msg = await destination.channel.send(chunk)
            else: msg = await destination.send(chunk)
        sent_messages.append(msg)
        if i < total - 1: await asyncio.sleep(0.5)
    return sent_messages

# ==================== ОЧИСТКА ТЕКСТА ДЛЯ TTS ====================
def clean_text_for_tts(text: str) -> str:
    """Убирает эмодзи, маркдаун и ссылки, чтобы edge-tts не падал с ошибкой."""
    # Удаляем Markdown-разметку
    text = re.sub(r'[*_`~#]', '', text)
    # Удаляем ссылки
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    text = re.sub(r'http\S+', '', text)
    # Удаляем эмодзи и спецсимволы (оставляем буквы, цифры, пробелы и базовую пунктуацию)
    text = re.sub(r'[^\w\s.,?!:;()\[\]{}\-]', '', text)
    return text.strip()

async def send_voice_answer(destination, text):
    """Генерирует TTS, конвертирует в OGG и отправляет голосовым сообщением."""
    clean_text = clean_text_for_tts(text)
    
    # Если после очистки ничего не осталось (только смайлики), отправляем текст
    if not clean_text:
        await send_long_answer(destination, text)
        return

    if len(clean_text) > 400:
        clean_text = clean_text[:400] + "... Короче, я устал говорить."

    temp_mp3 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
    temp_ogg = tempfile.NamedTemporaryFile(delete=False, suffix=".ogg").name

    try:
        # 1. Синтез речи (русский мужской голос)
        communicate = edge_tts.Communicate(clean_text, voice="ru-RU-DmitryNeural")
        await communicate.save(temp_mp3)

        # 2. Конвертация в OGG/Opus
        subprocess.run(
            ["ffmpeg", "-y", "-i", temp_mp3, "-c:a", "libopus", "-b:a", "48k", temp_ogg],
            check=True, capture_output=True
        )

        # 3. Отправка
        with open(temp_ogg, "rb") as f:
            file = discord.File(f, filename="voice-message.ogg")
            if hasattr(destination, 'reply'):
                await destination.reply(file=file)
            else:
                await destination.send(file=file)
                
    except Exception as e:
        logger.error(f"Ошибка генерации голосового ответа: {e}")
        # Если TTS упал, отправляем текстом, чтобы не терять ответ
        await destination.channel.send("*(Голосовой ответ не удался)*")
        await send_long_answer(destination, text)
    finally:
        if os.path.exists(temp_mp3): os.remove(temp_mp3)
        if os.path.exists(temp_ogg): os.remove(temp_ogg)
# =============================================================

async def transcribe_audio(attachment) -> str:
    if not AUDIO_SUPPORT:
        return "⚠️ Библиотеки для распознавания голоса не установлены."
    temp_path = None
    wav_path = None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as resp:
                if resp.status != 200:
                    return "⚠️ Не удалось скачать голосовое сообщение."
                audio_data = await resp.read()
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:
            f.write(audio_data)
            temp_path = f.name
            
        wav_path = temp_path.replace(".ogg", ".wav")
        
        audio = AudioSegment.from_file(temp_path)
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio.export(wav_path, format="wav")
        
        model = get_whisper_model()
        if not model:
            return "⚠️ Модель распознавания речи не загружена."
            
        segments, info = model.transcribe(wav_path, beam_size=5)
        text = " ".join(segment.text for segment in segments).strip()
        if not text:
            return "⚠️ Не удалось распознать речь в голосовом сообщении."
        return text
    except Exception as e:
        logger.error(f"Ошибка распознавания аудио: {e}")
        return "⚠️ Ошибка при распознавании голосового сообщения."
    finally:
        if temp_path and os.path.exists(temp_path): os.remove(temp_path)
        if wav_path and os.path.exists(wav_path): os.remove(wav_path)

async def web_search(query: str) -> str:
    if not DEEPSEEK_API_KEY: return ""
    url = "https://api.deepseek.com/v1/tools/search"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"query": query, "count": 3, "need_content": False}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                if resp.status != 200: return ""
                data = await resp.json()
                results = data.get("results", [])
                if not results: return ""
                snippets = [f"**{r.get('title', '')}**: {r.get('summary', '')}" for r in results if r.get('summary')]
                return "\n\n".join(snippets)
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        return ""

async def ask_deepseek(history: list, image_url: str = None, user_name: str = "", question: str = "", context_str: str = "") -> str:
    if not DEEPSEEK_API_KEY: return "⚠️ API-ключ DeepSeek не настроен."

    content_str = f"[Система]: {context_str}\n[{user_name}]: {question}" if context_str else f"[{user_name}]: {question}"

    if image_url:
        user_content = [
            {"type": "text", "text": content_str},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
    else:
        user_content = content_str

    messages = [SYSTEM_PROMPT] + history + [{"role": "user", "content": user_content}]
    if len(messages) > MAX_HISTORY_LENGTH + 2:
        messages = [SYSTEM_PROMPT] + messages[-(MAX_HISTORY_LENGTH + 1):]

    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-flash", "messages": messages, "stream": False, "temperature": 0.7, "max_tokens": 1500}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60) as resp:
                if resp.status != 200:
                    error_data = await resp.json()
                    error_msg = error_data.get("error", {}).get("message", "Неизвестная ошибка")
                    if resp.status == 402: return "💳 **Недостаточно средств на аккаунте DeepSeek.**"
                    return f"❌ Ошибка API DeepSeek {resp.status}: {error_msg}"
                data = await resp.json()
                try:
                    content = data["choices"][0]["message"]["content"]
                    if not content or not content.strip(): return "⚠️ Нейросеть вернула пустой ответ."
                    return content.strip()
                except (KeyError, IndexError): return "⚠️ Нейросеть вернула некорректный ответ."
        except asyncio.TimeoutError: return "⏰ DeepSeek не ответил вовремя."
        except Exception as e: return f"⚠️ Ошибка: {str(e)}"

async def on_ai_message(message, bot):
    if message.author == bot.user: return
    if not get_status("ai_enabled", True): return
    if message.mention_everyone or "@everyone" in message.content or "@here" in message.content: return

    content = message.content
    is_mentioned = bot.user.mentioned_in(message)
    ucheniy_match = re.match(r'^уч[её]ный\s+', content, re.IGNORECASE)

    image_attachments = [att for att in message.attachments if att.content_type and att.content_type.startswith("image/")]
    audio_attachments = [att for att in message.attachments if att.content_type and att.content_type.startswith("audio/") or (att.filename and att.filename.endswith(('.ogg', '.mp3', '.wav', '.m4a')))]

    if (image_attachments or audio_attachments) and not (ucheniy_match or is_mentioned): return

    if ucheniy_match or is_mentioned:
        question = ""
        is_voice_input = bool(audio_attachments)

        if ucheniy_match: question = content[ucheniy_match.end():].strip()
        elif is_mentioned:
            mention_pattern = re.compile(r'<@!?%s>' % bot.user.id)
            question = mention_pattern.sub('', content).strip()
            if not question and not image_attachments and not audio_attachments: return

        if audio_attachments:
            transcription = await transcribe_audio(audio_attachments[0])
            if transcription.startswith("⚠️"):
                await message.reply(transcription)
                return
            question = f"{question} (Голосовое сообщение: {transcription})".strip()
            if not question: question = transcription

        if not question and image_attachments: question = "Опиши, что изображено на этой картинке."

        if question:
            conv_id = str(message.id) 
            if message.reference and message.reference.message_id:
                ref_id = message.reference.message_id
                if ref_id in msg_to_conv: conv_id = msg_to_conv[ref_id]
            
            history = conversations.get(conv_id, [])
            image_url = None
            if image_attachments:
                att = image_attachments[0]
                if att.size > 20 * 1024 * 1024:
                    await message.reply("⚠️ Изображение слишком большое (макс. 20 МБ).")
                    return
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(att.url) as resp:
                            if resp.status == 200:
                                img_data = await resp.read()
                                b64 = base64.b64encode(img_data).decode('utf-8')
                                image_url = f"data:{att.content_type or 'image/jpeg'};base64,{b64}"
                except Exception:
                    await message.reply("⚠️ Не удалось загрузить изображение.")
                    return

            context_lines = []
            try: context_lines.append(f"Сейчас {datetime.now(ZoneInfo('Europe/Moscow')).strftime('%H:%M')} по МСК.")
            except: pass
            
            search_keywords = ["поищи", "найди в интернете", "что нового", "последние новости", "курс", "погода"]
            if any(kw in question.lower() for kw in search_keywords):
                search_results = await web_search(question)
                if search_results: context_lines.append(f"Результаты поиска в интернете:\n{search_results}")
            
            context_str = " ".join(context_lines)

            async with message.channel.typing():
                user_name = message.author.display_name
                answer = await ask_deepseek(history, image_url=image_url, user_name=user_name, question=question, context_str=context_str)
                
                if not answer or not answer.strip():
                    await message.reply("⚠️ Нейросеть не смогла ответить (пустой ответ).")
                    return
                
                history.append({"role": "user", "content": f"[{user_name}]: {question}"})
                history.append({"role": "assistant", "content": answer})
                if len(history) > MAX_HISTORY_LENGTH: history = history[-MAX_HISTORY_LENGTH:]
                
                conversations[conv_id] = history
                save_ai_memory(conversations)
                
                if is_voice_input:
                    await send_voice_answer(message, answer)
                else:
                    sent_messages = await send_long_answer(message, answer)
                    for msg in sent_messages: msg_to_conv[msg.id] = conv_id
                
                msg_to_conv[message.id] = conv_id
                if len(msg_to_conv) > 5000: msg_to_conv.clear()

async def clear_history(user_id):
    global conversations
    conversations.clear()
    msg_to_conv.clear()
    save_ai_memory(conversations)
    return True
