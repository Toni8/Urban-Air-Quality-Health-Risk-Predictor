"""
download_epa.py
Downloads EPA AirData bulk CSV files for 2022–2025.
Files are public domain, no API key required.
"""

import os
import zipfile
import requests
from pathlib import Path
from tqdm import tqdm

RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

# EPA AirData direct download URLs – 2022 through 2025
EPA_FILES = {
    # AQI by county (main dataset)
    "daily_aqi_by_county_2022.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_aqi_by_county_2022.zip",
    "daily_aqi_by_county_2023.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_aqi_by_county_2023.zip",
    "daily_aqi_by_county_2024.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_aqi_by_county_2024.zip",
    "daily_aqi_by_county_2025.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_aqi_by_county_2025.zip",
    # PM2.5 (parameter 88101)
    "daily_88101_2022.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_88101_2022.zip",
    "daily_88101_2023.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_88101_2023.zip",
    "daily_88101_2024.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_88101_2024.zip",
    "daily_88101_2025.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_88101_2025.zip",
    # Ozone (parameter 44201)
    "daily_44201_2022.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_44201_2022.zip",
    "daily_44201_2023.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_44201_2023.zip",
    "daily_44201_2024.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_44201_2024.zip",
    "daily_44201_2025.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_44201_2025.zip",
    # NO2 (parameter 42602)
    "daily_42602_2022.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_42602_2022.zip",
    "daily_42602_2023.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_42602_2023.zip",
    "daily_42602_2024.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_42602_2024.zip",
    "daily_42602_2025.zip": "https://aqs.epa.gov/aqsweb/airdata/daily_42602_2025.zip",
}


def download_file(url: str, dest: Path) -> None:
    """Stream-download a file with a progress bar."""
    if dest.exists():
        print(f"  [SKIP] Already exists: {dest.name}")
        return
    print(f"  [DOWNLOAD] {dest.name} ...")
    resp = requests.get(url, stream=True, timeout=120)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    with open(dest, "wb") as f, tqdm(total=total, unit="B", unit_scale=True) as bar:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
            bar.update(len(chunk))


def unzip_file(zip_path: Path, dest_dir: Path) -> None:
    """Unzip a file into dest_dir."""
    print(f"  [UNZIP] {zip_path.name}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest_dir)


if __name__ == "__main__":
    for filename, url in EPA_FILES.items():
        zip_dest = RAW_DIR / filename
        download_file(url, zip_dest)
        unzip_file(zip_dest, RAW_DIR)

    print("\n✅ All EPA files downloaded and extracted to data/raw/")