import os
from dotenv import load_dotenv
from telethon.sync import TelegramClient

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PHONE = os.getenv("PHONE")

client = TelegramClient("session", API_ID, API_HASH)


def main():
    client.start(phone=PHONE)

    me = client.get_me()
    print(f"\nУвійшов як: {me.first_name} (@{me.username})\n")

    print("=== Останні 10 діалогів ===")
    for dialog in client.iter_dialogs(limit=10):
        print(f"  [{dialog.id}] {dialog.name}")

    print("\nГотово. Сесія збережена у файл session.session")


if __name__ == "__main__":
    with client:
        main()
