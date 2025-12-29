# System Patterns

## Parser Architecture Pattern

### Plugin-Style Bank Parsers
The system uses a plugin architecture for bank CSV parsers, allowing easy addition of new banks.

```
src/parsers/
├── __init__.py      # Public exports
├── base.py          # BaseParser ABC, Transaction/RawTransaction models
├── factory.py       # ParserFactory with auto-registration
├── westpac.py       # Westpac-specific parser
├── anz.py           # ANZ-specific parser
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
        # Detection logic
        pass
    
    def parse(self, file_path: Path) -> List[Transaction]:
        # Parsing logic
        pass

# Auto-register
ParserFactory.register(NewBankParser)
```

---
[2025-12-29 14:44:00 AEDT] - Initial parser architecture documented

This file documents recurring patterns and standards used in the project.

---

## Coding Patterns

### Naming Conventions
- **Files**: snake_case (e.g., `bank_parser.py`, `transaction_model.py`)
- **Classes**: PascalCase (e.g., `TransactionParser`, `SummaryReport`)
- **Functions/Methods**: snake_case (e.g., `parse_statement()`, `generate_report()`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `DEFAULT_CURRENCY`, `MAX_TRANSACTIONS`)

### Type Hints
- Use type hints for all function signatures
- Use `Optional[]` for nullable parameters
- Use dataclasses or Pydantic for data models

### Error Handling
- Custom exceptions for domain-specific errors
- Graceful degradation when parsing fails
- Detailed logging for debugging

---

## Architectural Patterns

### Parser Plugin Pattern
```
parsers/
  base_parser.py      # Abstract base class
  commbank_parser.py  # Bank-specific implementation
  westpac_parser.py   # Bank-specific implementation
```
- Each bank parser inherits from BaseParser
- Auto-detection of bank format where possible
- Fallback to manual selection

### Data Flow
```
Bank Statement (CSV/PDF) 
    → Parser 
    → Transaction Model 
    → Categorizer 
    → Report Generator 
    → Output (PDF/HTML/CSV)
```

### Repository Pattern for Data Access
- Abstract data access from business logic
- Support multiple storage backends
- Easy to mock for testing

---

## Testing Patterns

### Test Structure
- Unit tests for individual components
- Integration tests for data flow
- Sample data fixtures for each bank format

### Test Naming
- `test_<function_name>_<scenario>_<expected_result>`
- Example: `test_parse_transaction_valid_csv_returns_transaction_list`

---

[2025-12-29 14:04:59 AEDT] - Initial patterns documented
