# System Patterns

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
