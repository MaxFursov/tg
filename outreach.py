"""
Запуск розсилки:
  python3 outreach.py +380991234567 "Назва магазину"
  python3 outreach.py @username "Назва"

Або список з файлу contacts.txt (один рядок = "телефон/username назва"):
  python3 outreach.py --file contacts.txt
"""
import sys
import requests

API_URL = "https://tg-1-production.up.railway.app/outreach"
SECRET = "dlk_secret_2024"


def send(contacts: list[dict]):
    r = requests.post(
        API_URL,
        headers={"X-Secret": SECRET, "Content-Type": "application/json"},
        json={"contacts": contacts},
    )
    data = r.json()
    if data.get("ok"):
        print(f"Запущено для {data['count']} контактів")
    else:
        print(f"Помилка: {data}")


if __name__ == "__main__":
    args = sys.argv[1:]

    if args and args[0] == "--file":
        contacts = []
        with open(args[1]) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(None, 1)
                contacts.append({"chat": parts[0], "name": parts[1] if len(parts) > 1 else parts[0]})
    elif len(args) >= 1:
        contacts = [{"chat": args[0], "name": args[1] if len(args) > 1 else args[0]}]
    else:
        print(__doc__)
        sys.exit(1)

    send(contacts)
