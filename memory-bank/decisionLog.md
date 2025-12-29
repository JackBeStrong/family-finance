# Decision Log

This file records architectural and implementation decisions.

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
