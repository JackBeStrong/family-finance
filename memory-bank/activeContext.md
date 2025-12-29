# Active Context

This file tracks the project's current status, including recent changes, current goals, and open questions.

## Current Focus

* **Phase 1 Complete**: Bank statement import system is fully operational
* System is running in production on LXC container
* 366 transactions imported from 5 banks

## System Status

### Production Deployment ✓
| Component | Status | Details |
|-----------|--------|---------|
| File Watcher | Running | LXC 128 (192.168.1.237), Docker container |
| PostgreSQL | Running | LXC 110 (192.168.1.228), `family_finance` database |
| NFS Mount | Active | `/mnt/user/datastore/tools/bank-statements/` |

### How to Deploy/Redeploy

```bash
# 1. Make code changes locally
cd ~/workspace/family-finance
# ... edit files ...

# 2. Commit and push
git add -A && git commit -m "description" && git push

# 3. On ansible server, pull and deploy
ssh ansible@ansible-server
cd ~/family-finance && git pull
cd ~/home-server-related && git pull
ansible-playbook -i ~/home-server-related/ansible/hosts \
  ~/home-server-related/ansible/playbook/family-finance.yml \
  --ask-vault-pass
```

### How to Import Transactions

1. Export CSV from bank website
2. Copy to NAS: `/mnt/user/datastore/tools/bank-statements/{bank-name}/`
3. File watcher auto-detects and imports within 30 seconds
4. Check logs: `ssh root@192.168.1.237 docker logs -f family-finance`

### How to Query Data

```bash
# Connect as readonly user
psql -h 192.168.1.228 -U readonly -d family_finance

# Example queries
SELECT COUNT(*) FROM transactions;
SELECT bank_source, COUNT(*) FROM transactions GROUP BY bank_source;
SELECT * FROM transactions WHERE date >= '2025-11-01' ORDER BY date;
```

## Data Summary

| Bank | Transactions | Date Range |
|------|--------------|------------|
| ANZ | 4 | Nov 2025 |
| Bankwest | 8 | Aug-Dec 2025 |
| CBA | 40 | Oct-Dec 2025 |
| Macquarie | 100 | Various |
| Westpac | 214 | Nov 2025 |
| **Total** | **366** | Aug-Dec 2025 |

## Recent Changes

* [2025-12-29 14:03:28 AEDT] - Project initialized
* [2025-12-29 14:44:00 AEDT] - Implemented 5 bank parsers (Westpac, ANZ, CBA, Bankwest, Macquarie)
* [2025-12-29 16:30:00 AEDT] - Created SQLite database with repository pattern
* [2025-12-29 16:30:00 AEDT] - Built file watcher service for automated CSV processing
* [2025-12-29 16:30:00 AEDT] - Deployed to LXC container via Ansible
* [2025-12-29 18:15:00 AEDT] - Converted to PostgreSQL backend
* [2025-12-29 18:15:00 AEDT] - Fixed watcher to use DB_TYPE env var
* [2025-12-29 18:15:00 AEDT] - Verified 366 transactions imported to PostgreSQL

## Key Files

| File | Purpose |
|------|---------|
| `src/watcher.py` | File watcher service (main entry point) |
| `src/parsers/factory.py` | Auto-detects bank and parses CSV |
| `src/database/postgres_repository.py` | PostgreSQL data access |
| `Dockerfile` | Container build definition |
| `sql/02_create_tables.sql` | Database schema |
| `~/home-server-related/ansible/playbook/family-finance.yml` | Deployment playbook |

## Open Questions/Issues

* Transaction categorization - manual, rule-based, or ML-based?
* Reporting format - CLI, web dashboard, or export to spreadsheet?
* Should reports be generated on-demand or scheduled?

## Next Steps (Future Sessions)

1. Implement transaction categorization
2. Build reporting/analysis tools
3. Consider web dashboard for visualization
