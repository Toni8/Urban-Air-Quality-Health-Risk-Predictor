USE air_quality_db;

-- Q1: Monthly average AQI by state (2024)

SELECT
    dl.state_name,
    dd.year,
    dd.month_name,
    ROUND(AVG(f.aqi_value), 1) AS avg_aqi,
    COUNT(*)                    AS readings
FROM fact_daily_aqi f
JOIN dim_date     dd ON f.date_id     = dd.date_id
JOIN dim_location dl ON f.location_id = dl.location_id
WHERE dd.year = 2024
GROUP BY dl.state_name, dd.year, dd.month, dd.month_name
ORDER BY dl.state_name, dd.month;


-- Q2: Top 20 most-polluted counties (by % of Unhealthy+ days)

SELECT
    dl.state_name,
    dl.county_name,
    COUNT(*)                                                AS total_days,
    SUM(IF(f.aqi_category_num >= 3, 1, 0))                AS unhealthy_days,
    ROUND(100.0 * SUM(IF(f.aqi_category_num >= 3, 1, 0))
               / COUNT(*), 1)                             AS pct_unhealthy
FROM fact_daily_aqi f
JOIN dim_location dl ON f.location_id = dl.location_id
JOIN dim_date     dd ON f.date_id     = dd.date_id
WHERE dd.year BETWEEN 2023 AND 2025
  AND f.aqi_value IS NOT NULL
GROUP BY dl.state_name, dl.county_name
HAVING total_days > 100
ORDER BY pct_unhealthy DESC
LIMIT 20;


-- Q3: Seasonal AQI patterns across all years

SELECT
    dd.season,
    ROUND(AVG(f.aqi_value), 1)          AS avg_aqi,
    ROUND(AVG(f.aqi_category_num), 2)   AS avg_risk_level,
    COUNT(*)                             AS samples
FROM fact_daily_aqi f
JOIN dim_date dd ON f.date_id = dd.date_id
GROUP BY dd.season
ORDER BY avg_aqi DESC;


-- Q4: Year-over-year AQI trend (national)

SELECT
    dd.year,
    ROUND(AVG(f.aqi_value), 1)  AS avg_aqi,
    MIN(f.aqi_value)             AS min_aqi,
    MAX(f.aqi_value)             AS max_aqi,
    SUM(IF(f.aqi_category_num >= 3, 1, 0)) AS unhealthy_days
FROM fact_daily_aqi f
JOIN dim_date dd ON f.date_id = dd.date_id
GROUP BY dd.year
ORDER BY dd.year;


-- Q5: Weekly pattern (is air worse on weekdays?)

SELECT
    dd.day_of_week,
    CASE dd.day_of_week
        WHEN 1 THEN 'Monday'  WHEN 2 THEN 'Tuesday' WHEN 3 THEN 'Wednesday'
        WHEN 4 THEN 'Thursday' WHEN 5 THEN 'Friday'
        WHEN 6 THEN 'Saturday' WHEN 7 THEN 'Sunday'
    END AS day_name,
    ROUND(AVG(f.aqi_value), 1) AS avg_aqi,
    COUNT(*) AS samples
FROM fact_daily_aqi f
JOIN dim_date dd ON f.date_id = dd.date_id
GROUP BY dd.day_of_week
ORDER BY dd.day_of_week;


-- Q6: Pull ML training set from MySQL

SELECT
    dd.full_date,
    dd.month,
    dd.day_of_week,
    dd.season,
    dd.is_weekend,
    dl.state_name,
    dl.county_name,
    f.aqi_value,
    f.aqi_category_num          AS target_class,
    f.defining_param
FROM fact_daily_aqi f
JOIN dim_date     dd ON f.date_id     = dd.date_id
JOIN dim_location dl ON f.location_id = dl.location_id
WHERE f.aqi_value   IS NOT NULL
  AND f.aqi_category_num IS NOT NULL
  AND dd.year BETWEEN 2022 AND 2025
ORDER BY dd.full_date, dl.state_name;