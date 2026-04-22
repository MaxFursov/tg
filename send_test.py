import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

client = TelegramClient("session", API_ID, API_HASH)

with client:
    client.send_message("@frsvmx", "Тест підключення Telegram API ✓")
    print("Повідомлення надіслано на @frsvmx")
