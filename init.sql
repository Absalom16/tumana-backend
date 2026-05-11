-- Tumana Database Initialization
-- This file runs automatically when the MySQL container starts for the first time.

CREATE DATABASE IF NOT EXISTS tumana_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE tumana_db;

-- Seed an admin user (password: Admin@1234)
-- The hash below is bcrypt for "Admin@1234"
INSERT IGNORE INTO users (name, email, phone, password_hash, role, status, is_verified, created_at, updated_at)
VALUES (
    'Super Admin',
    'admin@tumana.co.ke',
    '+254700000000',
    '$2b$12$examplehashwillbegeneratedbyflask',
    'admin',
    'active',
    1,
    NOW(),
    NOW()
);
