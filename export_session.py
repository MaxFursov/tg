import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PHONE = os.getenv("PHONE")

# Створюємо нову сесію з нуля
with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    client.start(phone=PHONE)
    print("\nСесія (SESSION_STRING):")
    print(client.session.save())
