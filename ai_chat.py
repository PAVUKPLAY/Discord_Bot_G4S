import re
import asyncio
import aiohttp
from config import DEEPSEEK_API_KEY, DEEPSEEK_API_URL

contexts = {}
MAX_HISTORY_LENGTH = 10

def split_text(text: str, limit: int = 1990) -> list:
    if len(text) <= limit:
        return [text]
    chunks = []
    current_chunk = ""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= limit:
            if current_chunk:
                current_chunk += " " + sentence
            else:
                current_chunk = sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            if len(sentence) > limit:
                words = sentence.split()
                temp = ""
                for word in words:
                    if len(temp) + len(word) + 1 <= limit:
                        if temp:
                            temp += " " + word
                        else:
                            temp = word
                    else:
                        chunks.append(temp)
                        temp = word
                if temp:
                    current_chunk = temp
                else:
                    current_chunk = ""
            else:
                current_chunk = sentence
    if current_chunk:
        chunks.append(current_chunk)
    return chunks

async def send_long_answer(destination, text):
    chunks = split_text(text)
    total = len(chunks)
    for i, chunk in enumerate(chunks):
        if i == 0:
            if hasattr(destination, 'reply'):
                await destination.reply(chunk)
            else:
                await destination.send(chunk)
        else:
            if hasattr(destination, 'channel'):
                await destination.channel.send(chunk)
            else:
                await destination.send(chunk)
        if i < total - 1:
            await asyncio.sleep(0.5)

async def ask_deepseek(prompt: str, history: list = None) -> str:
    if not DEEPSEEK_API_KEY:
        return "⚠️ API-ключ DeepSeek не настроен. Обратитесь к администратору."
    if history is None:
        history = []
    messages = history + [{"role": "user", "content": prompt}]
    if len(messages) > MAX_HISTORY_LENGTH * 2 + 1:
        messages = messages[- (MAX_HISTORY_LENGTH * 2 + 1):]

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "stream": False,
        "temperature": 0.7,
        "max_tokens": 1500
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30) as resp:
                if resp.status != 200:
                    error_data = await resp.json()
                    error_msg = error_data.get("error", {}).get("message", "Неизвестная ошибка")
                    if resp.status == 402:
                        return "💳 **Недостаточно средств на аккаунте DeepSeek.**\nПополните баланс: https://platform.deepseek.com/balance"
                    return f"❌ Ошибка API DeepSeek {resp.status}: {error_msg}"
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except asyncio.TimeoutError:
            return "⏰ DeepSeek не ответил вовремя."
        except Exception as e:
            return f"⚠️ Ошибка: {str(e)}"

async def on_ai_message(message, bot):
    if message.author == bot.user:
        return

    content = message.content
    is_mentioned = bot.user.mentioned_in(message)
    ucheniy_match = re.match(r'^уч[её]ный\s+', content, re.IGNORECASE)

    if ucheniy_match or is_mentioned:
        question = None
        if ucheniy_match:
            question = content[ucheniy_match.end():].strip()
        elif is_mentioned:
            mention_pattern = re.compile(r'<@!?%s>' % bot.user.id)
            question = mention_pattern.sub('', content).strip()
            if not question:
                return

        if question:
            async with message.channel.typing():
                user_id = message.author.id
                history = contexts.get(user_id, [])
                answer = await ask_deepseek(question, history)
                history.append({"role": "user", "content": question})
                history.append({"role": "assistant", "content": answer})
                if len(history) > MAX_HISTORY_LENGTH * 2:
                    history = history[- (MAX_HISTORY_LENGTH * 2):]
                contexts[user_id] = history
                await send_long_answer(message, answer)
