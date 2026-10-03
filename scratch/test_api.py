import requests
import json

# Baca token dari auth.json
with open("data/auth.json") as f:
    auth_data = json.load(f)

cookies = {c["name"]: c["value"] for c in auth_data.get("cookies", [])}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

# Coba beberapa kemungkinan endpoint API
endpoints = [
    "https://mentari.unpam.ac.id/api/v1/user/profile",
    "https://mentari.unpam.ac.id/api/mahasiswa/dashboard",
    "https://mentari.unpam.ac.id/api/kelas",
    "https://api-mentari.unpam.ac.id/v1/dashboard",
]

# Cari token
token = None
for origin in auth_data.get("origins", []):
    for item in origin.get("localStorage", []):
        if item.get("name") == "access":
            raw_val = json.loads(item.get("value"))
            user_obj = raw_val[0] if isinstance(raw_val, list) else raw_val
            token = user_obj.get("token")

if token:
    headers["Authorization"] = f"Bearer {token}"
    print("[*] Authorization header siap dengan Bearer JWT")

for ep in endpoints:
    try:
        r = requests.get(ep, headers=headers, cookies=cookies, timeout=5)
        print(f"Endpoint {ep} -> Status: {r.status_code}")
        if r.status_code == 200:
            print(f"Data: {r.text[:200]}")
    except Exception as e:
        print(f"Endpoint {ep} -> Error: {e}")
