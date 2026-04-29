import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")

client = TelegramClient("session", API_ID, API_HASH)

with client:
    client.send_message(-4993792827, "Привіт всім! Я — Ділова Ковбаса, ваш новий цифровий асистент. Готовий до роботи 🤝")
    print("Повідомлення надіслано в групу")
