-- Run this in MySQL Workbench as root
CREATE DATABASE air_quality_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'aq_user'@'localhost' IDENTIFIED BY 'Toni_$k8!';
GRANT ALL PRIVILEGES ON air_quality_db.* TO 'aq_user'@'localhost';
FLUSH PRIVILEGES;