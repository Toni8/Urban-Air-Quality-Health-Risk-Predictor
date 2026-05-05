USE air_quality_db;

CREATE TABLE IF NOT EXISTS dim_location (
    location_id   INT AUTO_INCREMENT PRIMARY KEY,
    state_code    CHAR(2)      NOT NULL,
    state_name    VARCHAR(50)  NOT NULL,
    county_code   CHAR(3)      NOT NULL,
    county_name   VARCHAR(100) NOT NULL,
    city_name     VARCHAR(100),
    site_num      VARCHAR(10),
    latitude      DECIMAL(9,6),
    longitude     DECIMAL(9,6),
    cbsa_name     VARCHAR(200),            -- Core Based Statistical Area (metro)
    UNIQUE KEY uq_site (state_code, county_code, site_num)
) ENGINE=InnoDB;

-- DIMENSION: dim_date
-- Pre-populated calendar dimension

CREATE TABLE IF NOT EXISTS dim_date (
    date_id       INT PRIMARY KEY,         -- YYYYMMDD integer
    full_date     DATE        NOT NULL,
    year          SMALLINT    NOT NULL,
    quarter       TINYINT     NOT NULL,
    month         TINYINT     NOT NULL,
    month_name    VARCHAR(10) NOT NULL,
    day_of_month  TINYINT     NOT NULL,
    day_of_week   TINYINT     NOT NULL,    -- 1=Monday
    week_of_year  TINYINT     NOT NULL,
    is_weekend    BOOLEAN     NOT NULL,
    season        VARCHAR(10) NOT NULL,    -- Spring/Summer/Fall/Winter
    UNIQUE KEY uq_date (full_date)
) ENGINE=InnoDB;


-- DIMENSION: dim_pollutant

CREATE TABLE IF NOT EXISTS dim_pollutant (
    pollutant_id     INT AUTO_INCREMENT PRIMARY KEY,
    parameter_code   VARCHAR(10)  NOT NULL,
    parameter_name   VARCHAR(100) NOT NULL,
    units            VARCHAR(20)  NOT NULL,
    description      TEXT,
    UNIQUE KEY uq_param (parameter_code)
) ENGINE=InnoDB;


-- FACT TABLE: fact_daily_aqi
-- One row per day per monitoring site per pollutant

CREATE TABLE IF NOT EXISTS fact_daily_aqi (
    id               BIGINT AUTO_INCREMENT PRIMARY KEY,
    date_id          INT          NOT NULL,
    location_id      INT          NOT NULL,
    pollutant_id     INT          NOT NULL,
    aqi_value        SMALLINT,
    aqi_category     VARCHAR(50),          -- Good/Moderate/USG/Unhealthy/VeryUnhealthy/Hazardous
    aqi_category_num TINYINT,              -- 0-5 numeric label for ML
    max_value        DECIMAL(10,4),
    mean_value       DECIMAL(10,4),
    defining_param   VARCHAR(50),
    data_source      VARCHAR(20) DEFAULT 'EPA_AQS',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (date_id)      REFERENCES dim_date(date_id),
    FOREIGN KEY (location_id)  REFERENCES dim_location(location_id),
    FOREIGN KEY (pollutant_id) REFERENCES dim_pollutant(pollutant_id),
    INDEX idx_date     (date_id),
    INDEX idx_location (location_id),
    INDEX idx_category (aqi_category_num)
) ENGINE=InnoDB;


-- STAGING TABLE: raw AQI county data (loaded first)

CREATE TABLE IF NOT EXISTS stg_aqi_county (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    state_name    VARCHAR(50),
    county_name   VARCHAR(100),
    state_code    CHAR(2),
    county_code   CHAR(3),
    date_local    DATE,
    aqi           SMALLINT,
    category      VARCHAR(50),
    defining_param VARCHAR(100),
    defining_site VARCHAR(50),
    num_sites     TINYINT
) ENGINE=InnoDB;


-- Seed dim_pollutant

INSERT IGNORE INTO dim_pollutant (parameter_code, parameter_name, units, description) VALUES
('88101', 'PM2.5',   'µg/m³', 'Fine particulate matter < 2.5 micrometers'),
('44201', 'Ozone',   'ppm',   'Ground-level ozone (O3)'),
('42602', 'NO2',     'ppb',   'Nitrogen dioxide'),
('42101', 'CO',      'ppm',   'Carbon monoxide'),
('42401', 'SO2',     'ppb',   'Sulfur dioxide'),
('AQI',   'AQI',    'index', 'Composite Air Quality Index');