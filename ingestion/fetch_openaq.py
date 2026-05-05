"""
fetch_openaq.py
Fetches recent (2025-2026) daily PM2.5 measurements from the OpenAQ v3 API
for a set of major US cities, as a supplement to the EPA annual files.
Requires OPENAQ_API_KEY in .env
"""

import os
import time
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENAQ_API_KEY")
BASE_URL = "https://api.openaq.org/v3"
HEADERS = {"X-API-Key": API_KEY}
RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

# Major US cities with known OpenAQ location IDs for PM2.5
# NOTE: These IDs may have changed. Use test_api.py to verify.
CITY_LOCATION_IDS = {
    "Los Angeles": 2178,   # updated – see notes
    "New York":    60,
    "Chicago":     8184,
    "Houston":     8172,
    "Phoenix":     8196,
    "Denver":      1068,
    "Atlanta":     8168,
    "Seattle":     8201,
}

DATE_FROM = "2025-01-01T00:00:00Z"
DATE_TO   = "2026-04-30T23:59:59Z"


def fetch_daily_measurements(location_id: int, city: str) -> pd.DataFrame:
    """Fetch daily PM2.5 averages for a location from OpenAQ v3."""
    # Correct v3 endpoint: list sensors at a location
    url = f"{BASE_URL}/locations/{location_id}/sensors"
    resp = requests.get(url, headers=HEADERS, timeout=30)

    if resp.status_code == 404:
        print(f"  [WARNING] Location ID {location_id} ({city}) not found. Skipping.")
        return pd.DataFrame()
    resp.raise_for_status()
    sensors = resp.json().get("results", [])

    records = []
    for sensor in sensors:
        # Only PM2.5 sensors
        if sensor.get("parameter", {}).get("name") != "pm25":
            continue
        sensor_id = sensor["id"]
        meas_url = f"{BASE_URL}/sensors/{sensor_id}/measurements/daily"
        meas_params = {
            "date_from": DATE_FROM,
            "date_to": DATE_TO,
            "limit": 1000,
        }
        meas_resp = requests.get(meas_url, headers=HEADERS, params=meas_params, timeout=60)
        if meas_resp.status_code == 429:
            print("  Rate limited — sleeping 60s")
            time.sleep(60)
            meas_resp = requests.get(meas_url, headers=HEADERS, params=meas_params, timeout=60)
        meas_resp.raise_for_status()

        for m in meas_resp.json().get("results", []):
            records.append({
                "city":        city,
                "location_id": location_id,
                "sensor_id":   sensor_id,
                "date":        m.get("period", {}).get("datetimeFrom", {}).get("utc", "")[:10],
                "pm25_avg":    m.get("value"),
                "unit":        sensor.get("parameter", {}).get("units", "µg/m³"),
            })
        time.sleep(1)  # Respect rate limits

    return pd.DataFrame(records)


if __name__ == "__main__":
    if not API_KEY:
        raise EnvironmentError("OPENAQ_API_KEY not found in .env file")

    all_dfs = []
    for city, loc_id in CITY_LOCATION_IDS.items():
        print(f"Fetching {city} (location_id={loc_id})...")
        df = fetch_daily_measurements(loc_id, city)
        print(f"  → {len(df)} records")
        all_dfs.append(df)
        time.sleep(2)

    combined = pd.concat(all_dfs, ignore_index=True)
    out_path = RAW_DIR / "openaq_recent_pm25.csv"
    combined.to_csv(out_path, index=False)
    print(f"\n✅ Saved {len(combined)} rows to {out_path}")