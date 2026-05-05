-- Populate dim_date for 2020-01-01 through 2027-12-31

USE air_quality_db;

DELIMITER $$
CREATE PROCEDURE populate_dim_date(start_date DATE, end_date DATE)
BEGIN
    DECLARE cur_date DATE DEFAULT start_date;
    WHILE cur_date <= end_date DO
        INSERT IGNORE INTO dim_date (
            date_id, full_date, year, quarter, month, month_name,
            day_of_month, day_of_week, week_of_year, is_weekend, season
        ) VALUES (
            YEAR(cur_date) * 10000 + MONTH(cur_date) * 100 + DAY(cur_date),
            cur_date,
            YEAR(cur_date),
            QUARTER(cur_date),
            MONTH(cur_date),
            DATE_FORMAT(cur_date, '%M'),
            DAY(cur_date),
            WEEKDAY(cur_date) + 1,
            WEEK(cur_date, 1),
            IF(WEEKDAY(cur_date) >= 5, TRUE, FALSE),
            CASE
                WHEN MONTH(cur_date) IN (3,4,5)  THEN 'Spring'
                WHEN MONTH(cur_date) IN (6,7,8)  THEN 'Summer'
                WHEN MONTH(cur_date) IN (9,10,11) THEN 'Fall'
                ELSE 'Winter'
            END
        );
        SET cur_date = DATE_ADD(cur_date, INTERVAL 1 DAY);
    END WHILE;
END$$
DELIMITER ;

CALL populate_dim_date('2020-01-01', '2027-12-31');
SELECT COUNT(*) as date_rows FROM dim_date;