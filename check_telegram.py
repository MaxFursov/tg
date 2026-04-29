import os
import json
import asyncio
from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
from telethon.tl.types import InputPhoneContact

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_STRING = os.getenv("SESSION_STRING")

BATCH_SIZE = 50  # Telegram обмежує кількість за раз

async def check_contacts():
    with open("contacts_to_check.json", encoding="utf-8") as f:
        contacts = json.load(f)

    print(f"Перевіряємо {len(contacts)} контактів...")

    on_telegram = []

    async with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
        for i in range(0, len(contacts), BATCH_SIZE):
            batch = contacts[i:i + BATCH_SIZE]
            input_contacts = [
                InputPhoneContact(
                    client_id=idx,
                    phone=c["phone"],
                    first_name=c["name"][:50],
                    last_name=""
                )
                for idx, c in enumerate(batch)
            ]

            result = await client(ImportContactsRequest(input_contacts))

            # result.imported — список {client_id, user_id} для тих хто є в TG
            users_by_id = {u.id: u for u in result.users}

            for imported in result.imported:
                contact = batch[imported.client_id]
                user = users_by_id.get(imported.user_id)
                on_telegram.append({
                    "name": contact["name"],
                    "phone": contact["phone"],
                    "tg_username": f"@{user.username}" if user and user.username else "немає username",
                    "tg_id": imported.user_id
                })

            # Видалити імпортовані контакти щоб не смітити в адресній книзі
            if result.users:
                await client(DeleteContactsRequest(id=[u.id for u in result.users]))

            print(f"  Оброблено {min(i + BATCH_SIZE, len(contacts))}/{len(contacts)}...")
            await asyncio.sleep(2)

    print(f"\nЗнайдено в Telegram: {len(on_telegram)} з {len(contacts)}")

    with open("telegram_contacts_result.json", "w", encoding="utf-8") as f:
        json.dump(on_telegram, f, ensure_ascii=False, indent=2)

    print("\n=== Результат ===")
    for c in on_telegram:
        print(f"  {c['name']} | {c['phone']} | {c['tg_username']}")

if __name__ == "__main__":
    asyncio.run(check_contacts())
