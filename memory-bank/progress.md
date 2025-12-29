# Progress

This file tracks the project's progress using a task list format.

## Completed Tasks

* [2025-12-29 14:03:38 AEDT] - Project scope and vision defined
* [2025-12-29 14:03:38 AEDT] - Memory Bank initialized
* [2025-12-29 14:44:00 AEDT] - Designed project directory structure (src/parsers/)
* [2025-12-29 14:44:00 AEDT] - Created core Python package structure
* [2025-12-29 14:44:00 AEDT] - Defined transaction data models (Transaction, RawTransaction)
* [2025-12-29 14:44:00 AEDT] - Implemented Westpac CSV parser
* [2025-12-29 14:44:00 AEDT] - Implemented ANZ CSV parser
* [2025-12-29 14:44:00 AEDT] - Created ParserFactory with auto-detection
* [2025-12-29 14:44:00 AEDT] - Tested with real data: 152 transactions parsed (148 Westpac, 4 ANZ)
* [2025-12-29 15:05:00 AEDT] - Implemented Bankwest CSV parser
* [2025-12-29 15:05:00 AEDT] - Implemented CBA CSV parser
* [2025-12-29 15:05:00 AEDT] - Implemented Macquarie CSV parser (with rich categorization)
* [2025-12-29 15:05:00 AEDT] - Tested all 5 banks: 366 transactions parsed
* [2025-12-29 16:30:00 AEDT] - Created SQLite database module with repository pattern
* [2025-12-29 16:30:00 AEDT] - Implemented occurrence-based transaction ID generation
* [2025-12-29 16:30:00 AEDT] - Created file watcher service for automated CSV processing
* [2025-12-29 16:30:00 AEDT] - Created Dockerfile for containerization
* [2025-12-29 16:30:00 AEDT] - Created Ansible playbook for LXC deployment
* [2025-12-29 16:30:00 AEDT] - Deployed to LXC container (VMID 128, IP 192.168.1.237)
* [2025-12-29 16:30:00 AEDT] - Tested end-to-end: 340 transactions imported via file watcher
* [2025-12-29 18:15:00 AEDT] - Converted database backend from SQLite to PostgreSQL
* [2025-12-29 18:15:00 AEDT] - Created PostgreSQL repository implementation
* [2025-12-29 18:15:00 AEDT] - Updated Dockerfile with psycopg2 support
* [2025-12-29 18:15:00 AEDT] - Updated Ansible playbook with PostgreSQL connection (vault secrets)
* [2025-12-29 18:15:00 AEDT] - Created SQL scripts for database setup (sql/01_create_database.sql, sql/02_create_tables.sql)
* [2025-12-29 18:15:00 AEDT] - Tested PostgreSQL integration: 366 transactions imported successfully

## Current Architecture

### Data Flow
1. CSV files dropped into NAS folder (`/mnt/user/datastore/tools/bank-statements/`)
2. File watcher service (Docker container on LXC 128) polls folder every 30s
3. ParserFactory auto-detects bank format and parses transactions
4. Transactions saved to PostgreSQL database (192.168.1.228/family_finance)
5. Processed files moved to `data/processed/` directory

### Database
- **PostgreSQL Server**: 192.168.1.228 (LXC VMID 110)
- **Database**: family_finance
- **Users**: 
  - `readwrite` - for import service (full access)
  - `readonly` - for reporting services (SELECT only)

### Deployment
- **LXC Container**: VMID 128, IP 192.168.1.237
- **Docker Image**: family-finance
- **NFS Mount**: bank-statements folder from NAS

## Current Tasks

* [x] Design project directory structure
* [x] Create core Python package structure
* [x] Define transaction data models
* [x] Implement CSV bank statement parsers (5 banks)
* [x] Create SQLite database module
* [x] Create file watcher service
* [x] Containerize with Docker
* [x] Deploy to LXC via Ansible
* [x] Convert to PostgreSQL for reporting independence
* [ ] Create monthly income/spending report
* [ ] Implement transaction categorization

## Next Steps

* Create monthly report generator (income vs spending by category)
* Implement transaction categorization (rule-based)
* Build reporting dashboard or CLI
