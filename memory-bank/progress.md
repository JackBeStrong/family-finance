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
| MCP Server | LXC 128 (192.168.1.237:8080) | ✓ Running |
| PostgreSQL | LXC 110 (192.168.1.228) | ✓ Running |
| NFS Mount | Unraid NAS | ✓ Mounted |

### Data
- **Total Transactions**: 768
- **Banks Supported**: 5 (ANZ, Bankwest, CBA, Macquarie, Westpac)
- **Date Range**: Oct 2021 - Dec 2025

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

## Phase 2: Reporting & Analysis ✓ COMPLETE

### MCP Server for Database Access ✓ COMPLETE
* [2025-12-30 10:45:00 AEDT] - Created MCP server (`src/mcp_server/server.py`)
* [2025-12-30 10:45:00 AEDT] - Implemented 9 tools for querying transaction data
* [2025-12-30 10:45:00 AEDT] - Tested all tools successfully with Roo
* [2025-12-30 16:45:00 AEDT] - Deployed MCP server to LXC 128 as Docker container
* [2025-12-30 16:45:00 AEDT] - Fixed SSE transport (use Mount for /messages/ endpoint)
* [2025-12-30 16:45:00 AEDT] - Fixed IP conflict (iPhone had same IP as LXC)
* [2025-12-30 16:45:00 AEDT] - Fixed router DHCP range (was 2-254, now 2-199)
* [2025-12-30 16:50:00 AEDT] - All 9 MCP tools verified working in production

### MCP Server Configuration
- **URL**: http://192.168.1.237:8080
- **SSE Endpoint**: http://192.168.1.237:8080/sse
- **Messages Endpoint**: http://192.168.1.237:8080/messages/
- **Roo Config**: `.roo/mcp.json`

### Available MCP Tools (12 total)

**Data Query Tools:**
| Tool | Description |
|------|-------------|
| `get_database_stats` | Overall stats (total transactions, date range, banks) |
| `get_available_months` | List months with transaction data |
| `get_monthly_summary` | Income/expenses totals for a month |
| `get_spending_by_category` | Category breakdown with percentages |
| `get_transactions_by_bank` | Per-bank/account totals |
| `get_top_merchants` | Top spending merchants |
| `get_month_comparison` | Month-over-month comparison |
| `query_transactions` | Flexible filtered queries |
| `execute_sql` | Raw SELECT queries (read-only) |

**Financial Context Tools (NEW):**
| Tool | Description |
|------|-------------|
| `get_financial_context` | Full context (people, accounts, properties, entities, category rules) |
| `get_account_context` | Account details with linked property resolved |
| `get_property_context` | Property details with linked accounts resolved |

### AI Report Generator ✓ COMPLETE
* [2025-12-30 17:59:00 AEDT] - Built agentic AI report generator using `mcp-agent` library
* [2025-12-30 17:59:00 AEDT] - Uses Claude Sonnet 4.5 with 64K max tokens
* [2025-12-30 17:59:00 AEDT] - Agent autonomously calls MCP tools for data gathering
* [2025-12-30 17:59:00 AEDT] - Generates markdown reports with HTML email formatting
* [2025-12-30 17:59:00 AEDT] - Sends via Gmail SMTP to junzhouan@gmail.com
* [2025-12-30 17:59:00 AEDT] - Deployed to LXC 128 with monthly cron job
* [2025-12-30 17:59:00 AEDT] - Verified working: 6168 char report generated and emailed
* [2025-12-30 18:15:00 AEDT] - Fixed: Added clean_report() to strip [Calling tool...] artifacts from email output

### Report Generator Files
- `src/report_generator/__main__.py` - Entry point using mcp-agent
- `src/report_generator/email_sender.py` - Gmail SMTP sender
- `Dockerfile.report` - Docker container
- `requirements-report.txt` - Dependencies (mcp-agent[anthropic], markdown)
- `mcp_agent.config.yaml` - MCP agent configuration

### Report Generator Deployment
- **On-demand script**: `/usr/local/bin/generate-finance-report.sh`
- **Monthly cron**: `0 8 1 * *` (1st of month at 8am AEDT)
- **Logs**: `/var/log/finance-report/cron.log`

### Future Enhancements
* [x] Refine report prompt for more detailed analysis → Done via Financial Context Store
* [x] Report on last month (not current) for complete data → Done 2025-12-30
* [x] Support multiple email recipients → Done 2025-12-30 (ready for future use)
* [ ] Add trend visualization charts
* [ ] Add budget tracking and alerts

## Phase 3: Financial Context Store ✓ COMPLETE

### Completed Tasks
* [2025-12-30 20:20:00 AEDT] - Created `config/financial-context.yaml` with user's financial structure
* [2025-12-30 20:20:00 AEDT] - Created `src/mcp_server/context_store.py` to load and query YAML config
* [2025-12-30 20:20:00 AEDT] - Added 3 new MCP tools: get_financial_context, get_account_context, get_property_context
* [2025-12-30 20:20:00 AEDT] - Updated Dockerfile.mcp to include config/ directory
* [2025-12-30 20:20:00 AEDT] - Updated Ansible playbook to copy config/ directory
* [2025-12-30 20:20:00 AEDT] - Updated report generator system prompt to use context tools
* [2025-12-30 20:20:00 AEDT] - Deployed and verified all 12 MCP tools working

### Financial Context Store Features
- **People**: Household members with aliases for transaction matching
- **Accounts**: All bank accounts with types, purposes, and property links
- **Properties**: Investment properties with addresses
- **Entities**: Known merchants, employers, property managers
- **Category Rules**: Pattern-based rules for auto-categorization
- **Reporting Preferences**: Group by property, exclude transfers, etc.

### Key Files
- `config/financial-context.yaml` - User's financial structure (YAML)
- `src/mcp_server/context_store.py` - Context store module

## Phase 4: Transaction Categorization (Future)

* [ ] Add more category rules to financial-context.yaml
* [ ] Implement rule-based auto-categorization at import time
* [ ] Add manual category assignment UI

## Phase 4: Home Loan Management (Future)

* [ ] Mortgage tracking
* [ ] Extra payment calculations
* [ ] Interest savings projections

## Phase 5: Investment & Planning (Future)

* [ ] Investment portfolio tracking
* [ ] Goal-based savings plans
* [ ] Long-term financial projections
