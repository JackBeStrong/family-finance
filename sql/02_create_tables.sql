-- =============================================================================
-- Step 2: Create Tables and Grant Permissions
-- =============================================================================
-- Run this while connected to the 'family_finance' database
-- Uses existing readwrite and readonly users from the PostgreSQL server
-- =============================================================================

-- Drop existing table if schema changed
DROP TABLE IF EXISTS transactions;

-- Create transactions table (matches Python postgres_repository.py schema)
CREATE TABLE transactions (
    id TEXT PRIMARY KEY,
    date DATE NOT NULL,
    amount DECIMAL(15, 2) NOT NULL,
    description TEXT NOT NULL,
    account_id TEXT NOT NULL,
    account_type TEXT NOT NULL,
    bank_source TEXT NOT NULL,
    source_file TEXT NOT NULL,
    balance DECIMAL(15, 2),
    original_category TEXT,
    category TEXT,
    transaction_type TEXT NOT NULL,
    merchant_name TEXT,
    location TEXT,
    foreign_amount DECIMAL(15, 2),
    foreign_currency TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for common queries
CREATE INDEX idx_transactions_date ON transactions(date);
CREATE INDEX idx_transactions_bank_account ON transactions(bank_source, account_id);
CREATE INDEX idx_transactions_category ON transactions(category);
CREATE INDEX idx_transactions_amount ON transactions(amount);

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
