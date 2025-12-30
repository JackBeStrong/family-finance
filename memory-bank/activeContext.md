# Active Context

This file tracks the project's current status, including recent changes, current goals, and open questions.

## Current Focus

* **Phase 1 Complete**: Bank statement import system is fully operational
* **Phase 2 In Progress**: MCP server deployed and working
* System is running in production on LXC container
* 768 transactions imported from 5 banks
* MCP server exposing 9 tools for AI-powered reporting

## System Status

### Production Deployment ✓
| Component | Status | Details |
|-----------|--------|---------|
| File Watcher | Running | LXC 128 (192.168.1.237), Docker container |
| MCP Server | Running | LXC 128 (192.168.1.237:8080), Docker container |
| PostgreSQL | Running | LXC 110 (192.168.1.228), `family_finance` database |
| NFS Mount | Active | `/mnt/user/datastore/tools/bank-statements/` |

### MCP Server Access

**Roo Configuration** (`.roo/mcp.json`):
```json
{
  "mcpServers": {
    "family-finance": {
      "url": "http://192.168.1.237:8080/sse",
      "transportType": "sse"
    }
  }
}
```

**Available Tools**:
- `get_database_stats` - Overall database statistics
- `get_available_months` - List months with data
- `get_monthly_summary` - Income/expenses for a month
- `get_spending_by_category` - Category breakdown
- `get_transactions_by_bank` - Per-bank totals
- `get_top_merchants` - Top spending merchants
- `get_month_comparison` - Month-over-month comparison
- `query_transactions` - Flexible filtered queries
- `execute_sql` - Raw SELECT queries (read-only)

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

**Via MCP Tools** (recommended):
- Use Roo with the family-finance MCP server
- Tools provide structured JSON responses

**Via SQL**:
```bash
# Connect as readonly user
psql -h 192.168.1.228 -U readonly -d family_finance

# Example queries
SELECT COUNT(*) FROM transactions;
SELECT bank_source, COUNT(*) FROM transactions GROUP BY bank_source;
SELECT * FROM transactions WHERE date >= '2025-11-01' ORDER BY date;
```

## Data Summary

| Bank | Transactions | Account Types |
|------|--------------|---------------|
| Westpac | 313 | Credit card, Savings |
| Macquarie | 217 | Transaction |
| ANZ | 98 | Transaction |
| CBA | 88 | Transaction |
| Bankwest | 52 | Transaction |
| **Total** | **768** | Oct 2021 - Dec 2025 |

## Recent Changes

* [2025-12-29 14:03:28 AEDT] - Project initialized
* [2025-12-29 14:44:00 AEDT] - Implemented 5 bank parsers (Westpac, ANZ, CBA, Bankwest, Macquarie)
* [2025-12-29 16:30:00 AEDT] - Created SQLite database with repository pattern
* [2025-12-29 16:30:00 AEDT] - Built file watcher service for automated CSV processing
* [2025-12-29 16:30:00 AEDT] - Deployed to LXC container via Ansible
* [2025-12-29 18:15:00 AEDT] - Converted to PostgreSQL backend
* [2025-12-30 10:45:00 AEDT] - Created MCP server with 9 tools
* [2025-12-30 16:45:00 AEDT] - Deployed MCP server to LXC 128
* [2025-12-30 16:45:00 AEDT] - Fixed SSE transport (Mount for /messages/)
* [2025-12-30 16:45:00 AEDT] - Fixed IP conflict (iPhone had same IP)
* [2025-12-30 16:45:00 AEDT] - Fixed router DHCP range (2-199)
* [2025-12-30 16:50:00 AEDT] - All 9 MCP tools verified working
* [2025-12-30 18:15:00 AEDT] - Fixed report email: added clean_report() to strip [Calling tool...] artifacts from AI output

## Key Files

| File | Purpose |
|------|---------|
| `src/watcher.py` | File watcher service (main entry point) |
| `src/mcp_server/server.py` | MCP server with 9 tools |
| `src/parsers/factory.py` | Auto-detects bank and parses CSV |
| `src/database/postgres_repository.py` | PostgreSQL data access |
| `Dockerfile` | File watcher container |
| `Dockerfile.mcp` | MCP server container |
| `.roo/mcp.json` | Roo MCP configuration |
| `sql/02_create_tables.sql` | Database schema |
| `~/home-server-related/ansible/playbook/family-finance.yml` | Deployment playbook |

## Open Questions/Issues

* ~~Transaction categorization - manual, rule-based, or ML-based?~~ (Future phase)
* ~~Reporting format - CLI, web dashboard, or export to spreadsheet?~~ → Using AI via MCP
* ~~Should reports be generated on-demand or scheduled?~~ → On-demand via AI

## Next Steps (Next Session)

1. **Create monthly report template** - Design the report format and system prompt
2. **Build report generation pipeline** - Automate report creation
3. **Implement trend visualization** - Charts and graphs
