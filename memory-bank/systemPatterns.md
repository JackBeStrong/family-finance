# System Patterns

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FAMILY FINANCE SYSTEM                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────────┐     ┌───────────────────┐       │
│  │   NAS Share  │────▶│  File Watcher    │────▶│   PostgreSQL DB   │       │
│  │ (CSV files)  │     │  (LXC Container) │     │  (LXC Container)  │       │
│  └──────────────┘     └──────────────────┘     └───────────────────┘       │
│                                                         │                   │
│  bank-statements/      192.168.1.237           192.168.1.228               │
│  └── *.csv             VMID: 128               VMID: 110                   │
│                        Docker: family-finance   DB: family_finance         │
│                                                         │                   │
│                       ┌──────────────────┐              │                   │
│                       │   MCP Server     │◀─────────────┘                   │
│                       │  (12 tools)      │                                  │
│                       └────────┬─────────┘                                  │
│                                │                                            │
│                       ┌────────▼─────────┐     ┌───────────────────┐       │
│                       │ Financial Context│     │  Report Generator │       │
│                       │ Store (YAML)     │◀────│  (AI Agent)       │       │
│                       └──────────────────┘     └───────────────────┘       │
│                                                                              │
│                       config/financial-context.yaml                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Deployment Architecture

### Infrastructure Components

| Component | Location | IP Address | Details |
|-----------|----------|------------|---------|
| NAS (Unraid) | Physical | 192.168.1.200 | Stores CSV files in `/mnt/user/datastore/tools/bank-statements/` |
| Proxmox Host | Physical | 192.168.1.200 | Hosts LXC containers |
| File Watcher | LXC 128 | 192.168.1.237 | Docker container running `family-finance` |
| MCP Server | LXC 128 | 192.168.1.237:8000 | Streamable HTTP transport at `/mcp` |
| PostgreSQL | LXC 110 | 192.168.1.228 | Database server, `family_finance` database |
| Ansible Server | LXC | 192.168.1.xxx | Deploys and manages infrastructure |

### Data Flow

1. **CSV Drop**: User exports bank statements and drops CSV files into NAS folder
2. **NFS Mount**: LXC 128 mounts NAS folder via NFS at `/mnt/bank-statements`
3. **File Watcher**: Docker container polls `/incoming` every 30 seconds
4. **Parser**: `ParserFactory` auto-detects bank format and parses transactions
5. **Database**: Transactions saved to PostgreSQL via `readwrite` user
6. **Processed**: CSV files moved to `data/processed/` directory

---

## Parser Architecture Pattern

### Plugin-Style Bank Parsers
The system uses a plugin architecture for bank CSV parsers, allowing easy addition of new banks.

```
src/parsers/
├── __init__.py      # Public exports
├── base.py          # BaseParser ABC, Transaction/RawTransaction models
├── factory.py       # ParserFactory with auto-registration
├── westpac.py       # Westpac parser (credit card, offset account)
├── anz.py           # ANZ parser (transactional)
├── cba.py           # CBA parser (transactional)
├── bankwest.py      # Bankwest parser (transactional)
├── macquarie.py     # Macquarie parser (with rich categorization)
└── [future_bank].py # Easy to add new banks
```

### Key Components

1. **BaseParser (Abstract Base Class)**
   - `bank_name` property - identifies the bank
   - `can_parse(file_path)` - auto-detection of file format
   - `parse(file_path)` - returns List[Transaction]

2. **ParserFactory (Registry Pattern)**
   - `register(parser_class)` - register new parsers
   - `detect_parser(file_path)` - auto-detect appropriate parser
   - `parse_file(file_path)` - parse with auto-detection
   - `parse_directory(path)` - batch processing

3. **Transaction Model (Normalized Schema)**
   - Unified format across all banks
   - Preserves raw data for audit trails
   - Uses Decimal for financial precision

### Adding a New Bank Parser

```python
from src.parsers.base import BaseParser, Transaction

class NewBankParser(BaseParser):
    @property
    def bank_name(self) -> str:
        return "newbank"
    
    def can_parse(self, file_path: Path) -> bool:
        # Detection logic - check headers, filename patterns
        pass
    
    def parse(self, file_path: Path) -> List[Transaction]:
        # Parsing logic
        pass

# Auto-register in factory.py
ParserFactory.register(NewBankParser)
```

---

## Database Architecture

### Repository Pattern

```
src/database/
├── __init__.py           # get_repository() factory function
├── repository.py         # TransactionRepository ABC
├── sqlite_repository.py  # SQLite implementation (local dev)
└── postgres_repository.py # PostgreSQL implementation (production)
```

### Database Selection

The system uses `DB_TYPE` environment variable to select backend:
- `DB_TYPE=sqlite` (default) - Uses local SQLite file
- `DB_TYPE=postgres` - Uses PostgreSQL with connection from env vars

### PostgreSQL Schema

```sql
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
```

### Database Users

| User | Purpose | Permissions |
|------|---------|-------------|
| `readwrite` | File watcher service | ALL on transactions table |
| `readonly` | Reporting services | SELECT only |

---

## Deployment Pattern

### Ansible-Based Deployment

The system is deployed via Ansible playbook at:
`~/home-server-related/ansible/playbook/family-finance.yml`

### Deployment Steps

1. **Prepare Code**: Commit changes to git, push to origin
2. **Sync to Ansible Server**: `git pull` on ansible server
3. **Run Playbook**: 
   ```bash
   ansible-playbook -i ~/home-server-related/ansible/hosts \
     ~/home-server-related/ansible/playbook/family-finance.yml \
     --ask-vault-pass
   ```

### What the Playbook Does

1. Creates/refreshes LXC container (VMID 128)
2. Mounts NFS share from NAS
3. Installs Docker
4. Copies project files to container
5. Builds Docker image
6. Runs container with PostgreSQL env vars from vault
7. Installs Filebeat for log shipping to Kafka
8. Configures SSH access

### Environment Variables (from Ansible Vault)

```yaml
DB_TYPE: postgres
DB_HOST: 192.168.1.228
DB_PORT: 5432
DB_NAME: family_finance
DB_USER: "{{ ALGO_TRADING_DB_USER_RW }}"      # readwrite
DB_PASSWORD: "{{ ALGO_TRADING_DB_PASSWORD_RW }}"
```

---

## Coding Patterns

### Naming Conventions
- **Files**: snake_case (e.g., `bank_parser.py`, `transaction_model.py`)
- **Classes**: PascalCase (e.g., `TransactionParser`, `WestpacParser`)
- **Functions/Methods**: snake_case (e.g., `parse_statement()`, `save_transaction()`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `DEFAULT_CURRENCY`, `MAX_TRANSACTIONS`)

### Type Hints
- Use type hints for all function signatures
- Use `Optional[]` for nullable parameters
- Use dataclasses for data models

### Error Handling
- Custom exceptions for domain-specific errors
- Graceful degradation when parsing fails
- Detailed logging for debugging
- Errors logged to stdout (captured by Filebeat → Kafka)

---

## Testing Patterns

### Local Testing

```bash
# Parse files locally
python -m src.parse_transactions bank-transactions-raw-csv/ --output json

# Run watcher locally (SQLite)
DB_TYPE=sqlite python -m src.watcher --watch-dir ./incoming --data-dir ./data

# Run watcher with PostgreSQL
DB_TYPE=postgres DB_HOST=192.168.1.228 DB_USER=readwrite DB_PASSWORD=xxx \
  python -m src.watcher --watch-dir ./incoming --data-dir ./data
```

### Production Testing

```bash
# Copy test files to NAS
cp -r bank-transactions-raw-csv/* /mnt/nas/datastore/tools/bank-statements/

# Check container logs
ssh root@192.168.1.237 docker logs -f family-finance

# Query database
psql -h 192.168.1.228 -U readonly -d family_finance -c "SELECT COUNT(*) FROM transactions"
```

---

## Financial Context Store Pattern

### Purpose
Provides household financial structure to AI for enriched transaction categorization.

### Architecture

```
config/
└── financial-context.yaml    # User's financial structure (YAML)

src/mcp_server/
├── context_store.py          # FinancialContextStore class
└── server.py                 # MCP tools that use context store
```

### YAML Structure

```yaml
version: "1.0"

people:
  - id: primary
    name: "Name"
    role: primary_account_holder
    aliases: ["NAME", "N NAME"]

accounts:
  - account_id: "123456789"
    bank: westpac
    type: loan
    purpose: mortgage
    property_id: property_1
    label: "Property Name Mortgage"

properties:
  - id: property_1
    address: "123 Main St"
    type: investment

entities:
  - id: employer
    name: "Company Name"
    type: employer
    category: income.salary
    aliases: ["COMPANY NAME PTY"]

category_rules:
  - name: "Mortgage Interest"
    pattern: "INTEREST"
    conditions:
      original_category: "INT"
      account_type: "loan"
    category: expense.mortgage_interest
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `get_financial_context` | Full context or specific section |
| `get_account_context` | Account with linked property resolved |
| `get_property_context` | Property with linked accounts resolved |

### Usage Pattern

1. AI calls `get_financial_context` at start of report generation
2. When encountering generic categories (e.g., "INT"), AI calls `get_account_context`
3. AI uses resolved property address for meaningful labels

---

## MCP Server Transport Pattern

### Streamable HTTP (Modern Protocol)

The MCP server uses Streamable HTTP transport, the modern replacement for deprecated SSE.

```
┌─────────────────┐     HTTP POST      ┌─────────────────┐
│   MCP Client    │ ─────────────────▶ │   MCP Server    │
│  (Roo, Report)  │ ◀───────────────── │  (FastMCP)      │
└─────────────────┘   JSON Response    └─────────────────┘
                                              │
                         Single endpoint: /mcp
```

### Configuration

**Server** (`src/mcp_server/server.py`):
```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("family-finance-mcp", stateless_http=True, host="0.0.0.0", port=8000)

@mcp.tool()
def get_monthly_summary(year: int, month: int) -> dict:
    """Tool implementation..."""
    pass

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

**Client - Roo** (`.roo/mcp.json`):
```json
{
  "family-finance": {
    "type": "streamable-http",
    "url": "http://192.168.1.237:8000/mcp"
  }
}
```

**Client - mcp-agent** (`mcp_agent.config.yaml`):
```yaml
mcp:
  servers:
    family-finance:
      transport: streamable_http  # Note: underscore, not hyphen!
      url: "http://192.168.1.237:8000/mcp"
```

### Key Differences from SSE

| Aspect | SSE (deprecated) | Streamable HTTP |
|--------|------------------|-----------------|
| Endpoints | `/sse` + `/messages/` | Single `/mcp` |
| Method | GET + POST | HTTP POST only |
| Port | 8080 | 8000 (FastMCP default) |
| Streaming | Server-Sent Events | HTTP response streaming |

### Important Notes
- FastMCP requires `host="0.0.0.0"` in constructor for Docker/external access
- mcp-agent uses `streamable_http` (underscore), Roo uses `streamable-http` (hyphen)
- `stateless_http=True` recommended for production scalability

---

[2025-12-29 14:44:00 AEDT] - Initial parser architecture documented
[2025-12-29 18:15:00 AEDT] - Added deployment architecture and PostgreSQL patterns
[2025-12-30 20:20:00 AEDT] - Added Financial Context Store pattern
[2026-01-03 10:44:00 AEDT] - Added MCP Server Transport Pattern (Streamable HTTP)
