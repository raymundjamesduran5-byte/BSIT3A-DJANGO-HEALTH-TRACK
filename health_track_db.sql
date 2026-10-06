-- Database creation
CREATE DATABASE IF NOT EXISTS Health_track_db;
USE Health_track_db;

-- 2. Users Table
-- Stores the account information of the person using the system.
CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    date_of_birth DATE,
    gender ENUM('Male', 'Female', 'Other'),
    contact_number VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Health Profile Table
-- Stores basic health information.
CREATE TABLE IF NOT EXISTS health_profiles (
    health_profile_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    height_cm DECIMAL(5,2),
    weight_kg DECIMAL(5,2),
    blood_type VARCHAR(5),
    allergies TEXT,
    existing_conditions TEXT,
    emergency_contact_name VARCHAR(100),
    emergency_contact_number VARCHAR(20),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

-- 4. Daily Health Activity Table
-- Records general daily health activities.
CREATE TABLE IF NOT EXISTS health_activities (
    activity_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    activity_date DATE NOT NULL,
    steps INT DEFAULT 0,
    calories_burned DECIMAL(7,2) DEFAULT 0,
    mood ENUM('Excellent', 'Good', 'Neutral', 'Poor', 'Very Poor'),
    stress_level ENUM('Low', 'Moderate', 'High', 'Very High'),
    notes TEXT,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

-- 5. Exercise Table
-- Records exercise activities.
CREATE TABLE IF NOT EXISTS exercises (
    exercise_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    exercise_date DATE NOT NULL,
    exercise_type VARCHAR(100) NOT NULL,
    duration_minutes INT NOT NULL,
    calories_burned DECIMAL(7,2) DEFAULT 0,
    intensity ENUM('Low', 'Moderate', 'High'),
    notes TEXT,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

-- 6. Sleep Records Table
-- Tracks sleeping and waking times.
CREATE TABLE IF NOT EXISTS sleep_records (
    sleep_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    sleep_date DATE NOT NULL,
    bedtime TIME NOT NULL,
    wake_time TIME NOT NULL,
    total_hours DECIMAL(4,2),
    sleep_quality ENUM('Poor', 'Fair', 'Good', 'Excellent'),
    notes TEXT,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

-- 7. Water Intake Table
-- Records daily water consumption.
CREATE TABLE IF NOT EXISTS water_intake (
    water_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    intake_date DATE NOT NULL,
    amount_ml INT NOT NULL,
    intake_time TIME,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

-- 8. Meal Records Table
-- Records meals during the day.
CREATE TABLE IF NOT EXISTS meals (
    meal_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    meal_date DATE NOT NULL,
    meal_type ENUM('Breakfast', 'Lunch', 'Dinner', 'Snack') NOT NULL,
    meal_description VARCHAR(255),
    calories DECIMAL(7,2),
    notes TEXT,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

-- 9. Health Goals Table
-- Allows users to create personal health goals.
CREATE TABLE IF NOT EXISTS health_goals (
    goal_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    goal_name VARCHAR(150) NOT NULL,
    description TEXT,
    target_value DECIMAL(10,2),
    current_value DECIMAL(10,2) DEFAULT 0,
    unit VARCHAR(30),
    start_date DATE,
    target_date DATE,
    status ENUM('Not Started', 'In Progress', 'Completed', 'Cancelled')
        DEFAULT 'Not Started',

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

-- 10. Health Measurements Table
-- For measurements such as blood pressure, heart rate, temperature, etc.
CREATE TABLE IF NOT EXISTS health_measurements (
    measurement_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    measurement_date DATETIME NOT NULL,
    systolic_bp INT,
    diastolic_bp INT,
    heart_rate INT,
    temperature DECIMAL(4,1),
    blood_sugar DECIMAL(6,2),
    weight_kg DECIMAL(5,2),
    notes TEXT,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

-- 11. Health Reminders Table
-- For reminders such as exercise, water intake, sleep, or health checkups.
CREATE TABLE IF NOT EXISTS health_reminders (
    reminder_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    reminder_title VARCHAR(150) NOT NULL,
    description TEXT,
    reminder_date DATE NOT NULL,
    reminder_time TIME NOT NULL,
    reminder_type ENUM(
        'Exercise',
        'Water',
        'Meal',
        'Sleep',
        'Medication',
        'Checkup',
        'Other'
    ) DEFAULT 'Other',
    status ENUM('Pending', 'Completed', 'Cancelled')
        DEFAULT 'Pending',

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);

-- 12. Health Reports Table
-- If you want to save generated health summaries.
CREATE TABLE IF NOT EXISTS health_reports (
    report_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    report_date DATE NOT NULL,
    report_period ENUM('Daily', 'Weekly', 'Monthly') NOT NULL,
    summary TEXT,
    recommendations TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id)
        REFERENCES users(user_id)
        ON DELETE CASCADE
);
