# Product Context - Family Finance Manager

## Project Overview
A Python-based family finance management system designed to automatically import bank transactions from CSV files and store them in a centralized PostgreSQL database for analysis and reporting.

## Core Goals
1. **Automated Bank Statement Processing** - Automatically parse CSV exports from multiple Australian banks
2. **Centralized Data Storage** - Store all transactions in PostgreSQL for easy querying
3. **Multi-Bank Support** - Handle different CSV formats from various banks
4. **Duplicate Detection** - Prevent duplicate imports using occurrence-based transaction IDs

## Current Status: Phase 1 Complete ✓

### What's Working
- **5 Bank Parsers**: ANZ, Bankwest, CBA, Macquarie, Westpac
- **Automated Import**: File watcher service monitors NAS folder
- **PostgreSQL Storage**: 366 transactions imported and queryable
- **Docker Deployment**: Running on LXC container via Ansible

## Technical Stack

### Production Environment
| Component | Technology | Location |
|-----------|------------|----------|
| Application | Python 3.11 + Docker | LXC 128 (192.168.1.237) |
| Database | PostgreSQL 15 | LXC 110 (192.168.1.228) |
| File Storage | NFS (Unraid NAS) | 192.168.1.200 |
| Deployment | Ansible | Ansible server |
| Logging | Filebeat → Kafka | Kafka cluster |

### Key Dependencies
```
psycopg2-binary>=2.9.0  # PostgreSQL driver
```

### Source Code Structure
```
family-finance/
├── src/
│   ├── parsers/           # Bank CSV parsers (5 banks)
│   │   ├── base.py        # BaseParser ABC, Transaction model
│   │   ├── factory.py     # ParserFactory with auto-detection
│   │   ├── westpac.py     # Westpac (credit card, offset)
│   │   ├── anz.py         # ANZ (transactional)
│   │   ├── cba.py         # CBA (transactional)
│   │   ├── bankwest.py    # Bankwest (transactional)
│   │   └── macquarie.py   # Macquarie (with categories)
│   ├── database/          # Database layer
│   │   ├── repository.py  # Abstract interface
│   │   ├── sqlite_repository.py   # Local dev
│   │   └── postgres_repository.py # Production
│   ├── watcher.py         # File watcher service
│   └── parse_transactions.py  # CLI tool
├── sql/                   # Database setup scripts
│   ├── 01_create_database.sql
│   └── 02_create_tables.sql
├── Dockerfile             # Container build
└── requirements.txt       # Python dependencies
```

## Supported Banks

| Bank | Account Types | CSV Format | Notes |
|------|---------------|------------|-------|
| Westpac | Credit Card, Offset | Header-based, separate debit/credit | Multiple accounts per file |
| ANZ | Transactional | Headerless, signed amounts | Single account per file |
| CBA | Transactional | Header-based | Standard format |
| Bankwest | Transactional | Header-based | Standard format |
| Macquarie | Transactional | Header-based | Rich categorization included |

## Data Model

### Transaction Schema
```python
@dataclass
class Transaction:
    id: str                    # Unique ID (occurrence-based hash)
    date: date                 # Transaction date
    amount: Decimal            # Amount (negative = debit)
    description: str           # Transaction description
    account_id: str            # Account identifier
    account_type: AccountType  # TRANSACTION, CREDIT_CARD, SAVINGS, etc.
    bank_source: str           # Bank name (westpac, anz, etc.)
    source_file: str           # Original CSV filename
    balance: Optional[Decimal] # Running balance if available
    original_category: Optional[str]  # Bank's category
    category: Optional[str]    # User-assigned category
    transaction_type: TransactionType  # DEBIT, CREDIT, TRANSFER, etc.
    merchant_name: Optional[str]
    location: Optional[str]
    foreign_amount: Optional[Decimal]
    foreign_currency: Optional[str]
    created_at: datetime       # Import timestamp
```

## Future Phases (Planned)

### Phase 2 - Reporting & Analysis
- Monthly income/spending reports
- Category-based analysis
- Trend visualization

### Phase 3 - Transaction Categorization
- Rule-based auto-categorization
- Manual category assignment
- Category management

### Phase 4 - Home Loan Management
- Mortgage tracking
- Extra payment calculations
- Interest savings projections

### Phase 5 - Investment & Planning
- Investment portfolio tracking
- Goal-based savings plans
- Long-term financial projections

---
[2025-12-29 14:02:58 AEDT] - Initial project creation
[2025-12-29 18:15:00 AEDT] - Phase 1 complete: 5 banks, PostgreSQL, Docker deployment
