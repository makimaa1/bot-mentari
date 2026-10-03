import json
import urllib.request
import re

# Ambil token dari auth.json
with open("data/auth.json", "r") as f:
    auth_data = json.load(f)

token = None
for origin in auth_data.get("origins", []):
    for item in origin.get("localStorage", []):
        if item.get("name") == "access":
            raw_val = json.loads(item.get("value"))
            if isinstance(raw_val, list) and len(raw_val) > 0:
                token = raw_val[0].get("token")
                user_info = raw_val[0]
                print(f"[V] User: {user_info.get('fullname')} ({user_info.get('username')})")
                print(f"[V] Prodi: {user_info.get('prodi')}")

print(f"[V] Token ditemukan: {token[:20]}...{token[-10:]}")
