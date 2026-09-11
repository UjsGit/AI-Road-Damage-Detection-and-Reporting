import requests

latitude = 12.972022
longitude = 79.159142

url = "https://nominatim.openstreetmap.org/reverse"

params = {
    "lat": latitude,
    "lon": longitude,
    "format": "jsonv2",
    "addressdetails": 1,
    "zoom": 18
}

headers = {
    "User-Agent": "PotholeDetectionProject/1.0"
}

response = requests.get(
    url,
    params=params,
    headers=headers,
    timeout=10
)

print("Status code:", response.status_code)

if response.ok:
    data = response.json()

    print("\nDisplay name:")
    print(data.get("display_name"))

    print("\nAddress:")
    print(data.get("address"))
else:
    print("\nRequest failed:")
    print(response.text)