CREATE DATABASE IF NOT EXISTS aihawk_control CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE aihawk_control;

CREATE TABLE IF NOT EXISTS application_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id INT NOT NULL,
    job_title VARCHAR(255),
    company VARCHAR(255),
    link TEXT,
    location VARCHAR(255),
    status ENUM('applied','success','failed','skipped') NOT NULL,
    reason TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_run (run_id),
    INDEX idx_status (status),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS run (
    id INT AUTO_INCREMENT PRIMARY KEY,
    start_time DATETIME NOT NULL,
    end_time DATETIME,
    status ENUM('running','stopped','finished','error') NOT NULL,
    notes TEXT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS configuration (
    id INT PRIMARY KEY DEFAULT 1,
    manual_position TEXT,
    countries TEXT,
    contract_types JSON,
    experience_level JSON,
    remote BOOLEAN DEFAULT TRUE,
    hybrid BOOLEAN DEFAULT TRUE,
    onsite BOOLEAN DEFAULT TRUE,
    distance INT DEFAULT 100,
    date_filter ENUM('all_time','month','week','24_hours') DEFAULT '24_hours',
    apply_once_at_company BOOLEAN DEFAULT TRUE,
    company_blacklist TEXT,
    title_blacklist TEXT,
    location_blacklist TEXT,
    CHECK (id = 1)
) ENGINE=InnoDB;

INSERT INTO configuration (id) VALUES (1) ON DUPLICATE KEY UPDATE id=1;

CREATE TABLE IF NOT EXISTS resume_content (
    id INT PRIMARY KEY DEFAULT 1,
    plain_text_yaml MEDIUMTEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (id = 1)
) ENGINE=InnoDB;

INSERT INTO resume_content (id, plain_text_yaml) VALUES (1, '') ON DUPLICATE KEY UPDATE id=1;