# Progress

This file tracks the project's progress using a task list format.

## Phase 1: Bank Statement Import System ✓ COMPLETE

### Completed Tasks

* [2025-12-29 14:03:38 AEDT] - Project scope and vision defined
* [2025-12-29 14:03:38 AEDT] - Memory Bank initialized
* [2025-12-29 14:44:00 AEDT] - Designed project directory structure (src/parsers/)
* [2025-12-29 14:44:00 AEDT] - Created core Python package structure
* [2025-12-29 14:44:00 AEDT] - Defined transaction data models (Transaction, RawTransaction)
* [2025-12-29 14:44:00 AEDT] - Implemented Westpac CSV parser (credit card, offset account)
* [2025-12-29 14:44:00 AEDT] - Implemented ANZ CSV parser (transactional)
* [2025-12-29 14:44:00 AEDT] - Created ParserFactory with auto-detection
* [2025-12-29 15:05:00 AEDT] - Implemented Bankwest CSV parser
* [2025-12-29 15:05:00 AEDT] - Implemented CBA CSV parser
* [2025-12-29 15:05:00 AEDT] - Implemented Macquarie CSV parser (with rich categorization)
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
* [2025-12-29 18:15:00 AEDT] - Created SQL scripts for database setup
* [2025-12-29 18:15:00 AEDT] - Tested PostgreSQL integration: 366 transactions imported successfully

## Current Production State

### Infrastructure
| Component | Location | Status |
|-----------|----------|--------|
| File Watcher | LXC 128 (192.168.1.237) | ✓ Running |
| PostgreSQL | LXC 110 (192.168.1.228) | ✓ Running |
| NFS Mount | Unraid NAS | ✓ Mounted |

### Data
- **Total Transactions**: 366
- **Banks Supported**: 5 (ANZ, Bankwest, CBA, Macquarie, Westpac)
- **Date Range**: Aug 2025 - Dec 2025

## Deployment Commands

### Redeploy After Code Changes
```bash
# On local machine
cd ~/workspace/family-finance
git add -A && git commit -m "description" && git push

# On ansible server
cd ~/family-finance && git pull
cd ~/home-server-related && git pull
ansible-playbook -i ~/home-server-related/ansible/hosts \
  ~/home-server-related/ansible/playbook/family-finance.yml \
  --ask-vault-pass
```

### Check Container Status
```bash
ssh root@192.168.1.237 docker logs -f family-finance
```

### Query Database
```bash
psql -h 192.168.1.228 -U readonly -d family_finance
```

## Phase 2: Reporting & Analysis (Future)

* [ ] Create monthly income/spending report
* [ ] Implement category-based analysis
* [ ] Build trend visualization

## Phase 3: Transaction Categorization (Future)

* [ ] Design categorization rules
* [ ] Implement rule-based auto-categorization
* [ ] Add manual category assignment UI

## Phase 4: Home Loan Management (Future)

* [ ] Mortgage tracking
* [ ] Extra payment calculations
* [ ] Interest savings projections

## Phase 5: Investment & Planning (Future)

* [ ] Investment portfolio tracking
* [ ] Goal-based savings plans
* [ ] Long-term financial projections
