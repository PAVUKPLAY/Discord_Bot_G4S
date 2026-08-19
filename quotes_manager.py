import json
import os
import random
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

QUOTES_FILE = "quotes.json"

def load_quotes():
    if os.path.exists(QUOTES_FILE):
        with open(QUOTES_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                logger.info(f"Загружено {len(data)} цитат")
                return data
            except Exception as e:
                logger.error(f"Ошибка загрузки цитат: {e}")
                return []
    return []

def save_quotes(quotes):
    with open(QUOTES_FILE, "w", encoding="utf-8") as f:
        json.dump(quotes, f, ensure_ascii=False, indent=2)

quotes = load_quotes()

async def add_quote(author_id, author_name, text):
    quote_id = len(quotes) + 1
    quotes.append({
        "id": quote_id,
        "author_id": author_id,
        "author_name": author_name,
        "text": text,
        "timestamp": datetime.now().isoformat()
    })
    save_quotes(quotes)
    logger.info(f"Добавлена цитата ID {quote_id} от {author_name}")
    return quote_id

async def remove_quote(quote_id):
    global quotes
    for i, q in enumerate(quotes):
        if q["id"] == quote_id:
            del quotes[i]
            save_quotes(quotes)
            logger.info(f"Удалена цитата ID {quote_id}")
            return True
    logger.warning(f"Попытка удалить несуществующую цитату ID {quote_id}")
    return False

async def get_random_quote():
    if not quotes:
        return None
    return random.choice(quotes)

async def get_user_quotes(user_id):
    return [q for q in quotes if q["author_id"] == user_id]
