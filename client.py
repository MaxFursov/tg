import os
import re
import logging
import asyncio
import pdfplumber
import anthropic
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from rank_bm25 import BM25Okapi
from aiohttp import web

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PHONE = os.getenv("PHONE")
SESSION_STRING = os.getenv("SESSION_STRING")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

session = StringSession(SESSION_STRING) if SESSION_STRING else "session"
client = TelegramClient(session, API_ID, API_HASH)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Завантажуються один раз при старті
BASE_PROMPT: str = ""
KNOWLEDGE_CHUNKS: list[dict] = []   # [{name, text, tokens}]
BM25: BM25Okapi | None = None

# Історія розмов: {chat_id: [{"role": "user"|"assistant", "content": str}]}
CHAT_HISTORY: dict[int, list[dict]] = {}
MAX_HISTORY = 15  # повідомлень (туди і назад)


# --- RAG ---

def tokenize(text: str) -> list[str]:
    return re.findall(r'\w+', text.lower())


def load_knowledge_chunks() -> list[dict]:
    chunks = []
    knowledge_dir = Path("knowledge")
    if not knowledge_dir.exists():
        return chunks
    for file in sorted(knowledge_dir.iterdir()):
        if file.name == "README.txt":
            continue
        try:
            if file.suffix in (".txt", ".md"):
                text = file.read_text(encoding="utf-8")
            elif file.suffix == ".pdf":
                with pdfplumber.open(file) as pdf:
                    text = "\n".join(p.extract_text() or "" for p in pdf.pages)
            else:
                continue
            chunks.append({"name": file.name, "text": text})
        except Exception as e:
            log.warning(f"Не вдалось прочитати {file.name}: {e}")
    return chunks


def retrieve(query: str, top_k: int = 3) -> str:
    if not BM25 or not KNOWLEDGE_CHUNKS:
        return ""
    scores = BM25.get_scores(tokenize(query))
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    parts = []
    for i in top_indices:
        if scores[i] > 0:
            chunk = KNOWLEDGE_CHUNKS[i]
            parts.append(f"=== {chunk['name']} ===\n{chunk['text']}")
    return "\n\n".join(parts)


# --- AI ---

def ask_ai(chat_id: int, user_message: str) -> str:
    context = retrieve(user_message)
    user_content = user_message
    if context:
        user_content = f"[Контекст з бази знань]\n{context}\n\n[Повідомлення клієнта]\n{user_message}"

    history = CHAT_HISTORY.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_content})
    if len(history) > MAX_HISTORY:
        history[:] = history[-MAX_HISTORY:]

    response = claude.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=[
            {
                "type": "text",
                "text": BASE_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=history,
    )

    reply_text = response.content[0].text
    history.append({"role": "assistant", "content": reply_text})
    if len(history) > MAX_HISTORY:
        history[:] = history[-MAX_HISTORY:]

    usage = response.usage
    log.info(
        f"Токени: input={usage.input_tokens} "
        f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)} "
        f"cache_write={getattr(usage, 'cache_creation_input_tokens', 0)} "
        f"output={usage.output_tokens}"
    )
    return reply_text


# --- Telegram ---

async def should_respond(event, me) -> bool:
    if event.is_private:
        return True
    if event.mentioned:
        return True
    if event.message.reply_to:
        replied = await event.message.get_reply_message()
        if replied and replied.sender_id == me.id:
            return True
    return False


@client.on(events.NewMessage)
async def handler(event):
    log.info(f"[EVENT] incoming={event.message.out == False} private={event.is_private} text={event.message.text!r}")
    me = await client.get_me()
    if event.message.out:
        return  # ігнорувати вихідні повідомлення
    if not await should_respond(event, me):
        return

    sender = await event.get_sender()
    name = getattr(sender, "first_name", "Unknown")
    text = event.message.text

    if not text:
        return

    log.info(f"[{name}]: {text}")

    try:
        reply = await asyncio.to_thread(ask_ai, event.chat_id, text)
    except Exception as e:
        log.warning(f"Claude error: {e}")
        reply = "Наразі я перевантажений запитами. Спробуйте через кілька хвилин або зв'яжіться з менеджером."

    await event.reply(reply)
    log.info(f"[Відповідь → {name}]: {reply}")

    # Якщо бот згадав сайт — надіслати скріни
    if "dilovakovbasa.ua" in reply:
        for img in ["assets/site_1.png", "assets/site_2.png"]:
            if Path(img).exists():
                await client.send_file(event.chat_id, img)


API_SECRET = os.getenv("API_SECRET", "secret")


async def http_send(request: web.Request) -> web.Response:
    if request.headers.get("X-Secret") != API_SECRET:
        return web.json_response({"error": "unauthorized"}, status=401)
    data = await request.json()
    chat = data.get("chat")
    text = data.get("text")
    if not chat or not text:
        return web.json_response({"error": "missing chat or text"}, status=400)
    await client.send_message(chat, text)
    # Записуємо відправлене повідомлення в історію щоб бот знав що вже писав
    try:
        entity = await client.get_input_entity(chat)
        chat_id = entity.user_id if hasattr(entity, "user_id") else int(chat)
        history = CHAT_HISTORY.setdefault(chat_id, [])
        history.append({"role": "assistant", "content": text})
        if len(history) > MAX_HISTORY:
            history[:] = history[-MAX_HISTORY:]
    except Exception:
        pass
    log.info(f"[API] Надіслано у {chat}: {text}")
    return web.json_response({"ok": True})


MSG1 = """Доброго дня,

Це компанія «Ділова ковбаса»
Ми займаємося гуртовими продажами ковбасних виробів вже 13 років, знаходимося у Києві
Працюємо напряму з виробниками, тому навіть з доставкою ковбасні вироби виходять дешевше"""

MSG2 = """Підкажіть, будь ласка, чи продаєте Ви ковбасні вироби?
Хочу запропонувати Вам вигідну співпрацю з нами"""

OUTREACH_DELAY = int(os.getenv("OUTREACH_DELAY", 300))  # секунд між повідомленнями (5 хв за замовч.)


async def _send_and_record(chat_id: int, chat, text: str):
    await client.send_message(chat, text)
    history = CHAT_HISTORY.setdefault(chat_id, [])
    history.append({"role": "assistant", "content": text})
    if len(history) > MAX_HISTORY:
        history[:] = history[-MAX_HISTORY:]


async def run_outreach(chat, name: str):
    try:
        entity = await client.get_input_entity(chat)
        chat_id = entity.user_id if hasattr(entity, "user_id") else int(str(chat).lstrip("+"))
        log.info(f"[Outreach] Старт для {name} ({chat})")
        await _send_and_record(chat_id, chat, MSG1)
        log.info(f"[Outreach] Повідомлення 1 надіслано → {name}. Чекаю {OUTREACH_DELAY}с...")
        await asyncio.sleep(OUTREACH_DELAY)
        await _send_and_record(chat_id, chat, MSG2)
        log.info(f"[Outreach] Повідомлення 2 надіслано → {name}.")
    except Exception as e:
        log.error(f"[Outreach] Помилка для {chat}: {e}")


async def http_outreach(request: web.Request) -> web.Response:
    if request.headers.get("X-Secret") != API_SECRET:
        return web.json_response({"error": "unauthorized"}, status=401)
    data = await request.json()
    contacts = data.get("contacts", [])  # [{chat, name}]
    if not contacts:
        return web.json_response({"error": "no contacts"}, status=400)
    for c in contacts:
        asyncio.create_task(run_outreach(c["chat"], c.get("name", c["chat"])))
    log.info(f"[Outreach] Запущено для {len(contacts)} контактів")
    return web.json_response({"ok": True, "count": len(contacts)})


async def main():
    global BASE_PROMPT, KNOWLEDGE_CHUNKS, BM25

    await client.start(phone=PHONE)
    me = await client.get_me()
    log.info(f"Запущено як: {me.first_name} (@{me.username})")

    BASE_PROMPT = Path("prompt.txt").read_text(encoding="utf-8")
    log.info(f"Промпт завантажено ({len(BASE_PROMPT)} символів)")

    KNOWLEDGE_CHUNKS = load_knowledge_chunks()
    if KNOWLEDGE_CHUNKS:
        BM25 = BM25Okapi([tokenize(c["text"]) for c in KNOWLEDGE_CHUNKS])
        log.info(f"База знань: {len(KNOWLEDGE_CHUNKS)} файлів індексовано")
    else:
        log.info("База знань порожня")

    app = web.Application()
    app.router.add_post("/send", http_send)
    app.router.add_post("/outreach", http_outreach)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info(f"HTTP API запущено на порту {port}")

    log.info("Слухаю повідомлення (приватні + тег/reply у групах)...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    from telethon.errors import AuthKeyDuplicatedError

    RETRY_DELAY = 10
    MAX_RETRIES = 5

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            asyncio.run(main())
            break
        except AuthKeyDuplicatedError:
            log.critical("Сесія заблокована (AuthKeyDuplicated) — потрібна нова SESSION_STRING. Зупиняюсь.")
            break
        except Exception as e:
            log.error(f"Бот впав (спроба {attempt}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES:
                log.info(f"Перезапуск через {RETRY_DELAY} секунд...")
                import time; time.sleep(RETRY_DELAY)
            else:
                log.critical("Вичерпано всі спроби. Зупиняюсь.")
                raise
