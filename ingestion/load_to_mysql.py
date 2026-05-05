"""
load_to_mysql.py
Reads EPA CSV files and loads data into the air_quality_db MySQL database.
Run AFTER: download_epa.py AND after creating the schema in MySQL.
"""

import os
import re
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# ---- DB Connection ----
DB_URL = (
    f"mysql+pymysql://{os.getenv('MYSQL_USER')}:{os.getenv('MYSQL_PASSWORD')}"
    f"@{os.getenv('MYSQL_HOST')}:{os.getenv('MYSQL_PORT', 3306)}/{os.getenv('MYSQL_DB')}"
)
engine = create_engine(DB_URL, echo=False)
RAW_DIR = Path("data/raw")


def load_aqi_county_files():
    """Load daily AQI by county CSV files into stg_aqi_county."""
    files = sorted(RAW_DIR.glob("daily_aqi_by_county_*.csv"))
    if not files:
        print("❌ No AQI county files found. Run download_epa.py first.")
        return

    all_dfs = []
    for f in files:
        print(f"  Reading {f.name}...")
        df = pd.read_csv(f, parse_dates=["Date"])
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
        # Standardize column names across EPA file versions
        df = df.rename(columns={
            "date":                   "date_local",
            "aqi":                    "aqi",
            "category":               "category",
            "defining_parameter":     "defining_param",
            "defining_site":          "defining_site",
            "number_of_sites_reporting": "num_sites",
            "state_name":             "state_name",
            "county_name":            "county_name",
            "state_code":             "state_code",
            "county_code":            "county_code",
        })
        # Keep only needed columns that exist
        keep = ["state_name","county_name","state_code","county_code",
                "date_local","aqi","category","defining_param","defining_site","num_sites"]
        df = df[[c for c in keep if c in df.columns]]

        # Ensure state_code and county_code are strings (some years might be int)
        if "state_code" in df.columns:
            df["state_code"] = df["state_code"].astype(str).str.zfill(2)
        if "county_code" in df.columns:
            df["county_code"] = df["county_code"].astype(str).str.zfill(3)

        all_dfs.append(df)

    combined = pd.concat(all_dfs, ignore_index=True)
    combined["date_local"] = pd.to_datetime(combined["date_local"]).dt.date
    combined.drop_duplicates(subset=["state_code","county_code","date_local"], inplace=True)

    print(f"  Loading {len(combined):,} rows into stg_aqi_county...")
    combined.to_sql("stg_aqi_county", engine, if_exists="replace",
                    index=False, chunksize=10_000, method="multi")
    print("  ✅ stg_aqi_county loaded")
    return combined


def populate_dim_location(df: pd.DataFrame):
    """Extract unique locations from staging and insert into dim_location."""
    locs = (
        df[["state_code","state_name","county_code","county_name"]]
        .drop_duplicates()
        .copy()
    )
    # Ensure string type
    locs["state_code"] = locs["state_code"].astype(str).str.zfill(2)
    locs["county_code"] = locs["county_code"].astype(str).str.zfill(3)

    locs["city_name"]  = None
    locs["site_num"]   = None
    locs["latitude"]   = None
    locs["longitude"]  = None
    locs["cbsa_name"]  = None

    # Read existing locations from MySQL and cast to string for safe merge
    existing = pd.read_sql("SELECT state_code, county_code FROM dim_location", engine)
    if not existing.empty:
        existing["state_code"] = existing["state_code"].astype(str).str.zfill(2)
        existing["county_code"] = existing["county_code"].astype(str).str.zfill(3)
        existing["_exists"] = 1
    else:
        existing = pd.DataFrame(columns=["state_code","county_code"])

    # Merge left to find new locations
    merged = locs.merge(existing, on=["state_code","county_code"], how="left")
    new_locs = merged[merged["_exists"].isna()].drop(columns=["_exists"])

    if len(new_locs) > 0:
        # Ensure the columns match the SQL table (drop extra merge key)
        new_locs.to_sql("dim_location", engine, if_exists="append",
                        index=False, chunksize=1000, method="multi")
        print(f"  ✅ Inserted {len(new_locs):,} new locations into dim_location")
    else:
        print("  dim_location already up to date")


def populate_fact_daily_aqi():
    """Join staging with dimensions and populate fact_daily_aqi."""
    print("  Populating fact_daily_aqi from staging...")
    sql = """
    INSERT INTO fact_daily_aqi
        (date_id, location_id, pollutant_id, aqi_value, aqi_category,
        aqi_category_num, defining_param, data_source)
    SELECT
        dd.date_id,
        dl.location_id,
        dp.pollutant_id,
        s.aqi,
        s.category,
        CASE s.category
            WHEN 'Good'                             THEN 0
            WHEN 'Moderate'                         THEN 1
            WHEN 'Unhealthy for Sensitive Groups'   THEN 2
            WHEN 'Unhealthy'                        THEN 3
            WHEN 'Very Unhealthy'                   THEN 4
            WHEN 'Hazardous'                        THEN 5
            ELSE NULL
        END AS aqi_category_num,
        s.defining_param,
        'EPA_AQS'
    FROM stg_aqi_county s
    JOIN dim_date dd     ON dd.full_date = s.date_local
    JOIN dim_location dl ON dl.state_code = s.state_code
                         AND dl.county_code = s.county_code
    JOIN dim_pollutant dp ON dp.parameter_code = 'AQI'
    ON DUPLICATE KEY UPDATE aqi_value = s.aqi
    """
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        conn.commit()
        print(f"  ✅ fact_daily_aqi: {result.rowcount:,} rows affected")


if __name__ == "__main__":
    print("=== Loading EPA data into MySQL ===\n")
    df = load_aqi_county_files()
    if df is not None:
        populate_dim_location(df)
        populate_fact_daily_aqi()
    print("\n🎉 Data loading complete!")