# Active Context

This file tracks the project's current status, including recent changes, current goals, and open questions.

## Current Focus

* **Phase 2 Development**: Monthly reporting - income vs spending analysis
* PostgreSQL backend is now live with 366 transactions
* Ready to build reporting module

## Recent Changes

* [2025-12-29 14:03:28 AEDT] - Project initialized
* [2025-12-29 14:03:28 AEDT] - Memory Bank created
* [2025-12-29 14:03:28 AEDT] - Initial project scope defined
* [2025-12-29 14:44:00 AEDT] - Implemented parser architecture with plugin pattern
* [2025-12-29 14:44:00 AEDT] - Created Westpac CSV parser (148 transactions parsed)
* [2025-12-29 14:44:00 AEDT] - Created ANZ CSV parser (4 transactions parsed)
* [2025-12-29 14:44:00 AEDT] - Normalized output to JSON and CSV formats
* [2025-12-29 15:05:00 AEDT] - Added Bankwest, CBA, Macquarie parsers (366 total transactions)
* [2025-12-29 16:30:00 AEDT] - Created SQLite database with repository pattern
* [2025-12-29 16:30:00 AEDT] - Built file watcher service for automated CSV processing
* [2025-12-29 16:30:00 AEDT] - Deployed to LXC container via Ansible
* [2025-12-29 18:15:00 AEDT] - Converted to PostgreSQL backend (192.168.1.228/family_finance)
* [2025-12-29 18:15:00 AEDT] - Fixed watcher to use DB_TYPE env var for database selection
* [2025-12-29 18:15:00 AEDT] - Verified 366 transactions imported to PostgreSQL

## System Status

### Production Deployment
- **File Watcher**: Running on LXC 128 (192.168.1.237)
- **Database**: PostgreSQL on LXC 110 (192.168.1.228)
- **NFS Mount**: `/mnt/user/datastore/tools/bank-statements/` → `/incoming`

### Data Summary
- **Total Transactions**: 366
- **Banks**: ANZ (4), Bankwest (8), CBA (40), Macquarie (100), Westpac (214)
- **Date Range**: Aug 2025 - Dec 2025

## Open Questions/Issues

* ~~Which Australian banks should be prioritized for statement format support?~~ → All 5 major banks supported
* ~~Data storage - SQLite or PostgreSQL?~~ → PostgreSQL for shared access
* Preferred report output format (PDF, HTML, CSV, or all)?
* Transaction categorization rules - manual, rule-based, or ML-based?
* Should reports be generated on-demand or scheduled?

## Next Steps

1. Create monthly income/spending report
2. Implement transaction categorization
3. Build reporting CLI or dashboard
