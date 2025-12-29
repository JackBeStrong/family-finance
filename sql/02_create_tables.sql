-- =============================================================================
-- Step 2: Create Tables and Grant Permissions
-- =============================================================================
-- Run this while connected to the 'family_finance' database
-- Uses existing readwrite and readonly users from the PostgreSQL server
-- =============================================================================

-- Create transactions table
CREATE TABLE IF NOT EXISTS transactions (
    id VARCHAR(64) PRIMARY KEY,
    date DATE NOT NULL,
    description TEXT NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    balance DECIMAL(12, 2),
    bank VARCHAR(50) NOT NULL,
    account_type VARCHAR(50) NOT NULL,
    source_file VARCHAR(255) NOT NULL,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_bank ON transactions(bank);
CREATE INDEX IF NOT EXISTS idx_transactions_account_type ON transactions(account_type);
CREATE INDEX IF NOT EXISTS idx_transactions_amount ON transactions(amount);

-- Grant permissions to existing users
-- readwrite user: full access for the import service
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO readwrite;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO readwrite;

-- readonly user: read-only access for reporting services
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO readwrite;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO readwrite;
