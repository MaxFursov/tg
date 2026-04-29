import sys
import requests

chat = sys.argv[1]
text = sys.argv[2]

r = requests.post(
    "http://localhost:8080/send",
    headers={"X-Secret": "secret", "Content-Type": "application/json"},
    json={"chat": chat, "text": text},
)
print(r.json())
