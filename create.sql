-- Create database
DROP DATABASE IF EXISTS Mirrulations;
CREATE DATABASE IF NOT EXISTS Mirrulations;
USE Mirrulations;

-- Create tables
CREATE TABLE IF NOT EXISTS document (
    docket_id VARCHAR(255),
    title VARCHAR(255),
    cfr_part VARCHAR(255),
    agency_id VARCHAR(255),
    document_type VARCHAR(255),
    authors VARCHAR(255),
    comment_start_date VARCHAR(255),
    comment_end_date VARCHAR(255),
    posted_date DATETIME,
    modified_date DATETIME
);
