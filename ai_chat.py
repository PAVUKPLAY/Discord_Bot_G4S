import re
import asyncio
import aiohttp
import base64
import logging
from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL
from toggle_manager import get_status

logger = logging.getLogger(__name__)

conversations = {}
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
        "- Никаких научных и околонаучных терминов. Никаких 'кризис идентичности', 'отчуждение труда', 'постмодерн', 'дискурс'. Если мысль можно сказать простыми словами — говори простыми.\n"
        "- Объясняй как живому мужику за столом, а не как студенту на лекции. Примеры из жизни, а не из учебника.\n"
        "- Не бойся разговорных оборотов: 'нахуя я тогда нужен', 'тебя надувают', 'пустоту шмотками не закроешь'.\n"
        "- Если тема сложная — разбивай на простые куски. Один тезис — одна мысль — один пример.\n"
        "- Не строй длинных конструкций. Чем короче фраза, тем лучше доходит.\n\n"
        "ПОЗИЦИЯ:\n"
        "- Говоришь как есть, даже если неприятно. Не смягчаешь, не льстишь.\n"
        "- Требуешь фактов и конкретики. Спорный тезис — разбираешь, а не соглашаешься автоматически.\n"
        "- Прямо говоришь 'нет', если просят тупое, опасное или противоречивое. Мат — стиль, а не разрешение на хуйню.\n"
        "- Прямота — инструмент, а не поза. Не играешь в 'крутого' ради эффекта.\n\n"
        "ЗАПРЕТЫ:\n"
        "- Никаких 'к сожалению', 'я понимаю ваши чувства', 'как ИИ я не могу'.\n"
        "- Никакой вежливой воды и уклончивых формулировок.\n"
        "- Никаких умных слов ради умности. Если слово можно заменить простым — заменяй.\n"
        "- Не соглашаешься автоматически — споришь, если собеседник несёт чушь.\n\n"
        "ВАЖНОЕ ПРАВИЛО ДЛЯ ДИАЛОГА:\n"
        "В беседе могут участвовать несколько человек. Формат входящих сообщений: '[Имя_игрока]: текст'. Учитывай это при ответе."
    )
}

def split_text(text: str, limit: int = 1990) -> list:
    if len(text) <= limit: 
        return [text]
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
    if current_chunk: 
        chunks.append(current_chunk)
    return chunks

async def send_long_answer(destination, text):
    # Защита от пустых чанков
    chunks = [c for c in split_text(text) if c.strip()]
    if not chunks: 
        return []
        
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

async def ask_deepseek(history: list, image_url: str = None, user_name: str = "", question: str = "") -> str:
    if not DEEPSEEK_API_KEY: return "⚠️ API-ключ DeepSeek не настроен."

    content_str = f"[{user_name}]: {question}"
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
                
                # Безопасное извлечение контента
                try:
                    content = data["choices"][0]["message"]["content"]
                    if not content or not content.strip():
                        return "⚠️ Нейросеть вернула пустой ответ (возможно, сработал фильтр). Попробуйте переформулировать вопрос."
                    return content.strip()
                except (KeyError, IndexError):
                    return "⚠️ Нейросеть вернула некорректный ответ."
                    
        except asyncio.TimeoutError:
            return "⏰ DeepSeek не ответил вовремя."
        except Exception as e:
            return f"⚠️ Ошибка: {str(e)}"

async def on_ai_message(message, bot):
    if message.author == bot.user: return
    if not get_status("ai_enabled", True): return
    if message.mention_everyone or "@everyone" in message.content or "@here" in message.content: return

    content = message.content
    is_mentioned = bot.user.mentioned_in(message)
    ucheniy_match = re.match(r'^уч[её]ный\s+', content, re.IGNORECASE)

    image_attachments = [att for att in message.attachments if att.content_type and att.content_type.startswith("image/")]
    if image_attachments and not (ucheniy_match or is_mentioned): return

    if ucheniy_match or is_mentioned:
        question = ""
        if ucheniy_match: question = content[ucheniy_match.end():].strip()
        elif is_mentioned:
            mention_pattern = re.compile(r'<@!?%s>' % bot.user.id)
            question = mention_pattern.sub('', content).strip()
            if not question and not image_attachments: return

        if not question and image_attachments:
            question = "Опиши, что изображено на этой картинке."

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
                                mime = att.content_type or "image/jpeg"
                                image_url = f"data:{mime};base64,{b64}"
                except Exception:
                    await message.reply("⚠️ Не удалось загрузить изображение.")
                    return

            async with message.channel.typing():
                user_name = message.author.display_name
                answer = await ask_deepseek(history, image_url=image_url, user_name=user_name, question=question)
                
                # Проверка на пустой ответ перед отправкой
                if not answer or not answer.strip():
                    await message.reply("⚠️ Нейросеть не смогла ответить (пустой ответ).")
                    return
                
                history.append({"role": "user", "content": f"[{user_name}]: {question}"})
                history.append({"role": "assistant", "content": answer})
                if len(history) > MAX_HISTORY_LENGTH: history = history[-MAX_HISTORY_LENGTH:]
                
                conversations[conv_id] = history
                
                sent_messages = await send_long_answer(message, answer)
                for msg in sent_messages: msg_to_conv[msg.id] = conv_id
                msg_to_conv[message.id] = conv_id
                
                # Защита от утечки памяти
                if len(msg_to_conv) > 5000:
                    msg_to_conv.clear()
                    logger.info("Очищен кэш msg_to_conv во избежание утечки памяти.")

async def clear_history(user_id):
    conversations.clear()
    msg_to_conv.clear()
    return True
