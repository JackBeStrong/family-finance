# Decision Log

This file records architectural and implementation decisions.

---

## [2026-01-04 18:10:00 AEDT] - SQLAlchemy Migration for Database Access

### Decision
Migrated from raw psycopg2 cursors to SQLAlchemy ORM with connection pooling for all database access in both the PostgreSQL repository and MCP server.

### Context
- MCP server was experiencing "current transaction is aborted, commands ignored until end of transaction block" errors
- Raw psycopg2 cursors were never being closed, causing resource leaks
- No automatic transaction rollback on errors - queries would fail and leave connection in aborted state
- No connection pooling - stale connections would accumulate
- Manual SQL string building was error-prone

### Problem Analysis
The root cause was **low-level database access without proper lifecycle management**:

1. **Cursor Leaks**: 21+ instances of `cursor = db.conn.cursor()` without `cursor.close()`
2. **No Auto-Rollback**: When any query failed, PostgreSQL marked the transaction as aborted, but the code had no automatic rollback
3. **Stale Connections**: Single connection reused indefinitely, no health checks or recycling
4. **Manual Error Handling**: Each query needed try/except with manual rollback - easy to forget

### Rationale
**Why SQLAlchemy over raw psycopg2?**
- **Connection Pooling**: Automatically maintains pool of healthy connections with pre-ping health checks
- **Session Management**: Context managers (`with session:`) provide automatic commit/rollback
- **Connection Recycling**: Connections recycled after 1 hour to prevent "server closed connection" errors
- **Industry Standard**: Used by Django ORM, Flask-SQLAlchemy, FastAPI SQLModel
- **Hybrid Approach**: Can use ORM for simple queries, raw SQL via `text()` for complex aggregations

**Why not other solutions?**
- **Just add autocommit**: Would prevent transactions entirely, losing ACID guarantees
- **Manual try/except everywhere**: Error-prone, doesn't solve connection pooling
- **Keep raw psycopg2**: Would require manually implementing connection pool, health checks, etc.

### Implementation

**1. Created SQLAlchemy Models** ([`src/database/models.py`](src/database/models.py)):
```python
from sqlalchemy import Column, String, Date, Numeric, DateTime
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class TransactionModel(Base):
    __tablename__ = 'transactions'
    id = Column(String, primary_key=True)
    date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(15, 2), nullable=False)
    # ... more fields
```

**2. Added Connection Pooling** ([`src/database/models.py`](src/database/models.py:82)):
```python
engine = create_engine(
    url,
    pool_pre_ping=True,      # Test connections before use (prevents stale connections)
    pool_recycle=3600,       # Recycle connections after 1 hour
    pool_size=5,             # Maintain 5 connections in pool
    max_overflow=10,         # Allow up to 15 total connections under load
)
```

**3. Migrated PostgreSQL Repository** ([`src/database/postgres_repository.py`](src/database/postgres_repository.py)):
- Added `get_session()` context manager for automatic commit/rollback
- Migrated CRUD operations to use SQLAlchemy sessions
- Kept repository interface unchanged (no breaking changes to callers)

**4. Migrated MCP Server** ([`src/mcp_server/server.py`](src/mcp_server/server.py)):
- **Hybrid approach**: Use `session.execute(text(query))` for complex SQL
- Keeps existing SQL queries (less risk of bugs from ORM translation)
- Gets benefits of connection pooling and auto-rollback
- All 13 MCP tools updated

### Key Changes

**Before (raw psycopg2)**:
```python
cursor = db.conn.cursor()
cursor.execute("SELECT COUNT(*) FROM transactions")
result = cursor.fetchone()  # Cursor never closed!
# If error occurs, transaction stays aborted
```

**After (SQLAlchemy)**:
```python
with db.get_session() as session:
    result = session.execute(text("SELECT COUNT(*) FROM transactions")).fetchone()
    # Auto-commit on exit, auto-rollback on exception
```

### Connection Pool Configuration

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `pool_size` | 5 | Baseline connections maintained |
| `max_overflow` | 10 | Additional connections under load (max 15 total) |
| `pool_pre_ping` | True | Test connection before use (prevents stale connections) |
| `pool_recycle` | 3600s | Recycle connections after 1 hour |

### Deployment & Testing
- **Deployed**: 2026-01-04 18:00 AEDT
- **Tested**: All 13 MCP tools verified working
  - `get_database_stats()` - 817 transactions ✓
  - `get_monthly_summary(2025, 12)` - $79,077 income, $77,380 expenses ✓
  - `execute_sql()` - No more "aborted transaction" errors ✓
  - `get_spending_by_category()` - Complex aggregation working ✓

### Implications
- **Immediate**: No more "aborted transaction" errors in MCP server
- **Performance**: Connection pooling reduces connection overhead
- **Reliability**: Automatic rollback prevents stuck transactions
- **Maintainability**: Context managers make error handling automatic
- **Future**: Easy to add read replicas, connection load balancing

### References
- SQLAlchemy connection pooling docs: https://docs.sqlalchemy.org/en/20/core/pooling.html
- Industry comparison: Django ORM, SQLModel, Peewee all use similar patterns

---

## [2026-01-03 10:43:00 AEDT] - MCP Transport Migration: SSE to Streamable HTTP

### Decision
Migrated the MCP server from SSE (Server-Sent Events) transport to Streamable HTTP, the modern MCP protocol.

### Context
- SSE transport is being deprecated in the MCP specification
- Streamable HTTP is the recommended transport for production deployments
- The existing SSE implementation used `/sse` + `/messages/` endpoints

### Rationale
- **Streamable HTTP is the future**: Single `/mcp` endpoint using HTTP POST with bidirectional streaming
- **Better scalability**: Supports stateless operation mode for multi-node deployments
- **FastMCP simplification**: High-level SDK with `@mcp.tool()` decorators reduces boilerplate
- **Industry direction**: MCP SDK documentation recommends Streamable HTTP for production

### Implementation

1. **Server Refactoring** (`src/mcp_server/server.py`):
   - Replaced custom Starlette app with FastMCP
   - Changed from ~1000 lines to ~500 lines using `@mcp.tool()` decorators
   - Added `host="0.0.0.0"` and `port=8000` in FastMCP constructor for external access

2. **Client Updates** (`src/report_generator/agentic_report.py`):
   - Changed import from `mcp.client.sse.sse_client` to `mcp.client.streamable_http.streamable_http_client`
   - Updated client usage (returns 3 values instead of 2)

3. **Configuration Updates**:
   - `.roo/mcp.json`: `type: streamable-http`, URL: `http://192.168.1.237:8000/mcp`
   - `mcp_agent.config.yaml`: `transport: streamable_http` (underscore, not hyphen!)
   - Ansible playbook: Changed port mapping from 8080 to 8000

### Key Gotchas
- **FastMCP host binding**: Must set `host="0.0.0.0"` in constructor, not in `run()` method
- **mcp-agent config**: Uses `streamable_http` (underscore), not `streamable-http` (hyphen)
- **Roo config**: Uses `streamable-http` (hyphen) - different from mcp-agent!

### Protocol Comparison
| Aspect | SSE (deprecated) | Streamable HTTP (modern) |
|--------|------------------|--------------------------|
| Endpoint | `/sse` + `/messages/` | Single `/mcp` |
| Method | GET (SSE) + POST | HTTP POST |
| Default Port | 8080 | 8000 |
| Config Type | `sse` | `streamable-http` or `streamable_http` |

### Implications
- All MCP clients need to update their transport configuration
- Report generator Docker image needs rebuild to pick up new config
- Existing SSE clients will fail until updated

---

## [2025-12-31 15:27:00 AEDT] - Internal Transfer Detection for Top Merchants

### Decision
Enhanced `get_top_merchants` MCP tool to automatically filter out internal transfers between accounts, providing more meaningful merchant spending analysis.

### Context
- Top merchants report was dominated by internal transfers (mortgage payments, account transfers)
- Example: "PAYMENT BY AUTHORITY TO WESTPAC BANKCORP" showing as top "merchant"
- These aren't actual merchant spending - they're money moving between user's own accounts
- User wanted to see actual spending patterns, not internal money movement

### Rationale
- **Double-entry matching (primary)**: Industry-standard accounting approach
  - If debit in Account A matches credit in Account B (same amount, same date ±1 day), it's a transfer
  - Most accurate method, used by QuickBooks, Xero, and other accounting software
- **Pattern-based fallback (secondary)**: Catches transfers to external accounts not in system
  - Bank categories: TFR, PAYMENT, Financial > Transfers
  - Description patterns: "Transfer to", "To Westpac", "PAYMENT BY AUTHORITY"
  - Investment transfers: Interactive Brokers
  - Large ATM withdrawals (>$5000 with CASH category)
- **Account type exclusion**: Loan accounts excluded entirely (mortgage interest isn't merchant spending)

### Implementation
```sql
WITH matched_transfer_ids AS (
    -- Double-entry matching: debit in A = credit in B
    SELECT DISTINCT t1.id
    FROM transactions t1
    INNER JOIN transactions t2 ON
        ABS(t1.amount) = ABS(t2.amount)
        AND t1.amount < 0 AND t2.amount > 0
        AND ABS(t1.date - t2.date) <= 1
        AND t1.account_id != t2.account_id
),
pattern_transfer_ids AS (
    -- Pattern-based fallback
    SELECT id FROM transactions
    WHERE original_category IN ('TFR', 'PAYMENT')
       OR description LIKE 'Transfer to%'
       -- ... more patterns
)
SELECT ... WHERE id NOT IN (matched_transfer_ids UNION pattern_transfer_ids)
```

### API Change
- Added `exclude_internal_transfers` parameter to `get_top_merchants` (default: `true`)
- Set to `false` to see all transactions including transfers

### Industry Comparison
| Method | Used By | Pros | Cons |
|--------|---------|------|------|
| Account Linking | Mint, YNAB | Accurate | Requires all accounts linked |
| Bank Categories | Banks | Easy | Bank-specific, inconsistent |
| ML Models | Plaid, Yodlee | Handles edge cases | Complex, needs training data |
| Double-Entry | QuickBooks, Xero | Accounting standard | Needs both sides of transfer |
| Pattern Rules | Tiller, Lunch Money | Customizable | Maintenance burden |

Our approach combines Double-Entry (primary) + Pattern Rules (fallback) for best coverage.

### Implications
- Top merchants now shows actual spending (groceries, utilities, subscriptions)
- Mortgage payments, inter-account transfers filtered out
- Users can still see all transactions with `exclude_internal_transfers: false`

---

## [2025-12-31 09:52:00 AEDT] - Date Range Support for Report Generator

### Decision
Added command-line argument support to the report generator for custom date ranges, while maintaining backward compatibility with the default "last month" behavior.

### Context
- Report generator previously only supported generating reports for the previous month
- User needed ability to generate reports for specific months or custom date ranges
- Cron job should continue to work without changes (default behavior)

### Rationale
- **argparse over environment variables**: CLI args are more intuitive for on-demand usage
- **Two modes**: Month/year mode (`--month 12 --year 2025`) for single months, date range mode (`--start`/`--end`) for custom periods
- **ENTRYPOINT over CMD**: Docker needs ENTRYPOINT to append arguments rather than replace the command
- **Backward compatible**: No arguments = last month (existing behavior preserved)

### Implementation

1. **Python Script Changes** (`src/report_generator/__main__.py`):
   - Added `parse_args()` function using `argparse`
   - Added `get_date_range()` function to validate and process arguments
   - Modified `generate_report()` to accept `start_date` and `end_date` parameters
   - Single-month reports use optimized month-based MCP queries
   - Date range reports use flexible `query_transactions` with date filters
   - Added `--no-email` flag for testing (prints to stdout)

2. **Dockerfile Changes** (`Dockerfile.report`):
   - Changed `CMD` to `ENTRYPOINT` so arguments are appended, not replaced
   - `ENTRYPOINT ["python", "-m", "src.report_generator"]`

3. **Ansible Playbook Changes** (`family-finance.yml`):
   - Updated shell script to pass `"$@"` to Docker container
   - Added usage documentation in script header

### Command-Line Options
```
--month, -m MONTH     Month number (1-12) for single month report
--year, -y YEAR       Year (e.g., 2025) for single month report
--start, -s DATE      Start date in YYYY-MM-DD format
--end, -e DATE        End date in YYYY-MM-DD format
--no-email            Generate report but don't send email (print to stdout)
```

### Usage Examples
```bash
generate-finance-report.sh                           # Default: last month
generate-finance-report.sh --month 12 --year 2025    # December 2025
generate-finance-report.sh --start 2025-11-01 --end 2025-11-30  # Date range
generate-finance-report.sh --no-email                # Print to stdout
```

### Implications
- Cron job continues to work unchanged (uses default behavior)
- Users can generate historical reports on-demand
- Multi-month reports possible with date range mode
- Testing easier with `--no-email` flag

---

## [2025-12-30 23:47:00 AEDT] - Interactive Brokers Integration via Flex Queries

### Decision
Integrated Interactive Brokers (IBKR) investment portfolio data into the monthly financial report using the `interactive-brokers-mcp` npm package with Flex Query API.

### Context
- User has share investments in IBKR
- Need to include portfolio value, holdings, dividends, and realized gains in monthly reports
- IBKR has multiple API options: Gateway API (requires 2FA), Flex Queries (token-based)

### Rationale
- **Flex Queries over Gateway API**: No 2FA required per request, uses token authentication
- **NPM package over custom MCP**: `interactive-brokers-mcp` already exists and works well
- **Stdio transport**: Spawned on-demand via `npx`, no persistent server needed

### Implementation
1. **Flex Query Setup** (IBKR Portal):
   - Created Flex Query "reporting1" (ID: 1359561)
   - Sections: AccountInformation, ChangeInNAV, OpenPositions, Trades, CashTransactions, CashReport
   - Removed ConversionRates (was 12,207 entries causing bloat)

2. **MCP Configuration**:
   - Added `interactive-brokers-mcp` to `.roo/mcp.json` and `mcp_agent.config.yaml`
   - Transport: stdio via `npx -y interactive-brokers-mcp`

3. **Environment Variable Handling**:
   - `IB_FLEX_TOKEN` passed via Docker environment
   - **Key Fix**: mcp-agent's YAML config doesn't expand `${VAR}` in env blocks
   - Solution: Monkey-patch `mcp.client.stdio.get_default_environment()` to include `IB_FLEX_TOKEN`

4. **Dockerfile Changes**:
   - Added Node.js 20 to `Dockerfile.report` for `npx` support

### Key Files Modified
- `src/report_generator/__main__.py` - Added `setup_ibkr_environment()` function
- `mcp_agent.config.yaml` - Added interactive-brokers server config
- `Dockerfile.report` - Added Node.js 20
- Ansible playbook - Added `IB_FLEX_TOKEN` to Docker environment

### Report Output
The report now includes:
- Total Portfolio Value (from ChangeInNAV.endingValue)
- Holdings table with cost basis and unrealized P&L
- Dividend income breakdown by symbol
- Realized gains from trades
- Interest income on cash balances

### Implications
- Monthly reports now provide complete financial picture (bank + investments)
- Flex Query token needs to be kept secure (24-char alphanumeric)
- Token stored in Ansible vault as `ibkr_flex_token`

---

## [2025-12-30 20:20:00 AEDT] - Financial Context Store for Better Categorization

### Decision
Created a YAML-based Financial Context Store to provide household financial structure to AI for enriched transaction categorization.

### Context
- Reports showed generic categories like "INT" for mortgage interest
- User has 3 investment properties with separate mortgages
- Need to distinguish "Mortgage Interest - 4 Mann Pl" from "Mortgage Interest - 16 Austin Ave"
- AI needs context about accounts, properties, and their relationships

### Rationale
- **YAML over JSON**: Human-readable, supports comments, easier manual editing
- **MCP Tools over Database**: Context is static configuration, not transactional data
- **AI-Driven Categorization**: Let AI use context at report time rather than categorizing at import time
- **Flexible Structure**: Supports people, accounts, properties, entities, category rules

### Implementation
- `config/financial-context.yaml` - User's financial structure
- `src/mcp_server/context_store.py` - Module to load and query YAML
- 3 new MCP tools:
  - `get_financial_context` - Full context or specific section
  - `get_account_context` - Account with linked property resolved
  - `get_property_context` - Property with linked accounts resolved
- Updated report generator system prompt to use context tools

### Key Features
- **Account-Property Linking**: Mortgage accounts linked to properties via `property_id`
- **Entity Recognition**: Known employers, landlord agents with aliases for matching
- **Category Rules**: Pattern-based rules for auto-categorization
- **Reporting Preferences**: Group by property, exclude transfers, etc.

### Implications
- AI can now report "Mortgage Interest - 4 Mann Pl: $2,862.30" instead of "INT: $2,862.30"
- Users can customize their financial structure by editing YAML
- New accounts/properties can be added without code changes

---

## [2025-12-29 18:15:00 AEDT] - PostgreSQL for Production Database

### Decision
Switched from SQLite to PostgreSQL for production deployment.

### Context
- File watcher runs in Docker container on LXC
- Need reporting services to access data independently
- SQLite file inside container not accessible externally

### Rationale
- PostgreSQL allows multiple clients to connect
- `readonly` user enables safe reporting access
- Existing PostgreSQL server available (192.168.1.228)
- Reuses existing `readwrite`/`readonly` users from marketdata database

### Implementation
- Created `postgres_repository.py` with same interface as SQLite
- Added `DB_TYPE` env var to select backend
- SQL scripts in `sql/` folder for schema setup
- Ansible playbook passes credentials from vault

---

## [2025-12-29 17:00:00 AEDT] - Ansible-Based Deployment

### Decision
Use Ansible playbook for automated LXC container deployment.

### Context
- Need reproducible deployments
- Multiple components: Docker, NFS mounts, Filebeat
- Credentials stored in Ansible vault

### Rationale
- Consistent with other home server deployments
- Secrets managed securely in vault
- Easy to redeploy after changes

### Implementation
- Playbook at `~/home-server-related/ansible/playbook/family-finance.yml`
- Uses shared tasks: `refresh-lxc.yml`, `mount_nfs.yml`, `copy_to_lxc.yml`
- LXC VMID 128, IP 192.168.1.237

---

## [2025-12-29 16:30:00 AEDT] - File Watcher Service Architecture

### Decision
Implemented polling-based file watcher instead of inotify.

### Context
- Need to monitor NFS-mounted folder for new CSV files
- inotify doesn't work reliably over NFS
- Simple polling is sufficient for this use case

### Rationale
- 30-second poll interval is acceptable latency
- More reliable than filesystem events over NFS
- Simpler implementation and debugging

### Implementation
- `src/watcher.py` polls `WATCH_DIR` every `POLL_INTERVAL` seconds
- Processes all `*.csv` files found (including subdirectories)
- Moves processed files to `data/processed/`
- Failed files moved to `data/failed/` with error log

---

## [2025-12-29 16:00:00 AEDT] - Occurrence-Based Transaction IDs

### Decision
Generate transaction IDs using hash of (date, amount, description, bank, occurrence_index).

### Context
- Need unique IDs for duplicate detection
- Same transaction can appear in multiple exports
- Some banks have identical transactions on same day

### Rationale
- Hash ensures consistent ID across imports
- Occurrence index handles duplicate transactions on same day
- `ON CONFLICT DO NOTHING` prevents re-importing

### Implementation
- `_generate_id()` method in each parser
- Uses SHA256 hash truncated to 16 chars
- Format: `{bank}_{date}_{hash}_{occurrence}`

---

## [2025-12-29 14:42:00 AEDT] - Bank Parser Architecture Design

### Decision
Implemented a flexible, plugin-style parser architecture for handling multiple bank CSV formats.

### Context
- User has accounts with many banks (Westpac, ANZ, CBA, Bankwest, Macquarie)
- Each bank has different CSV export formats
- Need to normalize all transactions into a single format for analysis

### Architecture Choices

1. **Abstract Base Parser (`BaseParser`)**
   - Defines common interface: `bank_name`, `can_parse()`, `parse()`
   - Provides utility methods for date/amount parsing
   - Ensures all parsers output consistent `Transaction` objects

2. **Normalized Transaction Schema**
   - Captures maximum fields for flexibility
   - Preserves raw data in `RawTransaction` for audit trails
   - Uses `Decimal` for amounts to avoid floating-point issues

3. **Parser Factory with Auto-Registration**
   - `ParserFactory.register()` for easy parser addition
   - Auto-detection via `can_parse()` method
   - Supports batch processing of directories

### Supported Banks
- **Westpac**: Header-based CSV, separate debit/credit columns
- **ANZ**: Headerless CSV, signed amounts
- **CBA**: Header-based CSV, standard format
- **Bankwest**: Header-based CSV, standard format
- **Macquarie**: Header-based CSV, includes categories

### Implications
- Adding new banks requires only creating a new parser class
- No changes needed to core infrastructure
- Raw data preservation enables future re-processing

---

## [2025-12-29 14:04:33 AEDT] - Python as Primary Language

### Decision
Use Python 3.11+ as the primary language.

### Rationale
- Excellent ecosystem for data processing
- Strong CSV parsing libraries
- Easy to extend and maintain
- Good for rapid prototyping

### Implementation
- Target Python 3.11 (matches Docker base image)
- Use type hints for better code quality
- Follow PEP 8 style guidelines

---

## [2025-12-29 14:04:33 AEDT] - Modular Architecture

### Decision
Organize code into separate modules for parsers, database, and services.

### Rationale
- Allows independent development of features
- Easy to add new bank format parsers
- Supports future expansion
- Facilitates testing of individual components

### Implementation
```
src/
├── parsers/    # Bank CSV parsers
├── database/   # Repository pattern for data access
├── watcher.py  # File watcher service
└── parse_transactions.py  # CLI tool
```

---

## [2025-12-29 14:04:33 AEDT] - Docker Containerization

### Decision
Package application as Docker container for deployment.

### Rationale
- Consistent environment across dev and prod
- Easy deployment to LXC containers
- Isolates dependencies
- Simple restart and update process

### Implementation
- `Dockerfile` based on `python:3.11-slim`
- Installs `libpq5` for psycopg2
- Entry point: `python -m src.watcher`
- Environment variables for configuration
