# Decision Log

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
