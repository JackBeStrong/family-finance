# Decision Log

## [2025-12-29 14:42:00 AEDT] - Bank Parser Architecture Design

### Decision
Implemented a flexible, plugin-style parser architecture for handling multiple bank CSV formats.

### Context
- User has accounts with many banks (Westpac, ANZ, and potentially more)
- Each bank has different CSV export formats
- Need to normalize all transactions into a single format for analysis

### Architecture Choices

1. **Abstract Base Parser (`BaseParser`)**
   - Defines common interface: `bank_name`, `can_parse()`, `parse()`
   - Provides utility methods for date/amount parsing
   - Ensures all parsers output consistent `Transaction` objects

2. **Normalized Transaction Schema**
   - Captures maximum fields for flexibility: id, date, amount, description, account_id, account_type, bank_source, balance, original_category, category, transaction_type, merchant_name, location, foreign_amount, foreign_currency
   - Preserves raw data in `RawTransaction` for audit trails
   - Uses `Decimal` for amounts to avoid floating-point issues

3. **Parser Factory with Auto-Registration**
   - `ParserFactory.register()` decorator for easy parser addition
   - Auto-detection via `can_parse()` method
   - Supports batch processing of directories

4. **Bank-Specific Configurations**
   - Each parser has its own `Config` dataclass (e.g., `WestpacConfig`, `ANZConfig`)
   - Allows customization without code changes
   - Handles format variations within same bank

### Supported Banks (Initial)
- **Westpac**: Header-based CSV, separate debit/credit columns, multiple accounts per file
- **ANZ**: Headerless CSV, signed amounts, single account per file

### Implications
- Adding new banks requires only creating a new parser class
- No changes needed to core infrastructure
- Raw data preservation enables future re-processing if schema changes

This file records architectural and implementation decisions using a list format.

---

## Decision: Python as Primary Language

**Date**: 2025-12-29 14:04:33 AEDT

**Rationale**: 
- Excellent ecosystem for data processing (pandas, numpy)
- Strong CSV/PDF parsing libraries available
- Easy to extend and maintain
- Good for rapid prototyping and iteration

**Implementation Details**:
- Target Python 3.10+ for modern features
- Use type hints for better code quality
- Follow PEP 8 style guidelines

---

## Decision: Modular Architecture

**Date**: 2025-12-29 14:04:33 AEDT

**Rationale**:
- Allows independent development of features
- Easy to add new bank format parsers
- Supports future expansion (loans, investments)
- Facilitates testing of individual components

**Implementation Details**:
- Separate modules for: parsers, models, reports, utils
- Plugin-style architecture for bank parsers
- Clear interfaces between components

---

## Decision: Local-First Data Storage

**Date**: 2025-12-29 14:04:33 AEDT

**Rationale**:
- Privacy-focused for sensitive financial data
- No dependency on external services
- Works offline
- User maintains full control of data

**Implementation Details**:
- SQLite for structured data storage
- CSV import/export for portability
- Consider encryption for sensitive data
