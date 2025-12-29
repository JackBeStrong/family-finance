"""
Macquarie Bank CSV Parser

Handles Macquarie Bank CSV exports with the following format:
- Headers: Transaction Date,Details,Account,Category,Subcategory,Tags,Notes,Debit,Credit,Balance,Original Description
- Date format: DD MMM YYYY (e.g., "19 Dec 2025")
- Amounts: Separate debit/credit columns (no sign prefix)
- Rich categorization: Category, Subcategory, Tags
- Account name included in each row
"""

import re
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

from .base import (
    BaseParser, 
    Transaction, 
    RawTransaction,
    TransactionType,
    AccountType,
)


@dataclass
class MacquarieConfig:
    """Configuration for Macquarie parser."""
    # Column names
    col_date: str = "Transaction Date"
    col_details: str = "Details"
    col_account: str = "Account"
    col_category: str = "Category"
    col_subcategory: str = "Subcategory"
    col_tags: str = "Tags"
    col_notes: str = "Notes"
    col_debit: str = "Debit"
    col_credit: str = "Credit"
    col_balance: str = "Balance"
    col_original_desc: str = "Original Description"
    
    # Date format - Macquarie uses "DD MMM YYYY" format
    date_format: str = "%d %b %Y"


class MacquarieParser(BaseParser):
    """
    Parser for Macquarie Bank CSV exports.
    
    Macquarie exports are the richest in terms of metadata:
    - Pre-categorized with Category and Subcategory
    - Tags for additional classification
    - Notes field
    - Original description preserved separately
    """
    
    def __init__(self, config: Optional[MacquarieConfig] = None):
        """
        Initialize the Macquarie parser.
        
        Args:
            config: Optional configuration override
        """
        self.config = config or MacquarieConfig()
    
    @property
    def bank_name(self) -> str:
        return "macquarie"
    
    def can_parse(self, file_path: Path) -> bool:
        """
        Check if this file is a Macquarie CSV export.
        
        Detection is based on:
        1. CSV file extension
        2. Header row containing Macquarie-specific columns (Subcategory, Tags, Original Description)
        """
        if not file_path.suffix.lower() == '.csv':
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                first_line = f.readline().strip()
            
            # Check for Macquarie-specific header columns
            required_columns = [
                self.config.col_subcategory,
                self.config.col_tags,
                self.config.col_original_desc,
            ]
            
            return all(col in first_line for col in required_columns)
            
        except Exception:
            return False
    
    def parse(self, file_path: Path) -> List[Transaction]:
        """
        Parse Macquarie CSV and return normalized transactions.
        
        Args:
            file_path: Path to the Macquarie CSV file
            
        Returns:
            List of normalized Transaction objects
        """
        transactions = []
        rows = self._read_csv(file_path, has_header=True)
        
        for row_num, row in enumerate(rows, start=2):  # Start at 2 (1 = header)
            try:
                transaction = self._parse_row(row, row_num, file_path)
                if transaction:
                    transactions.append(transaction)
            except Exception as e:
                print(f"Warning: Failed to parse row {row_num}: {e}")
                continue
        
        return transactions
    
    def _parse_row(self, row: dict, row_num: int, file_path: Path) -> Optional[Transaction]:
        """Parse a single CSV row into a Transaction."""
        
        # Extract raw values
        date_str = row.get(self.config.col_date, '').strip()
        details = row.get(self.config.col_details, '').strip()
        account_name = row.get(self.config.col_account, '').strip()
        category = row.get(self.config.col_category, '').strip()
        subcategory = row.get(self.config.col_subcategory, '').strip()
        tags = row.get(self.config.col_tags, '').strip()
        notes = row.get(self.config.col_notes, '').strip()
        debit_str = row.get(self.config.col_debit, '').strip()
        credit_str = row.get(self.config.col_credit, '').strip()
        balance_str = row.get(self.config.col_balance, '').strip()
        original_desc = row.get(self.config.col_original_desc, '').strip()
        
        # Skip empty rows
        if not date_str or not details:
            return None
        
        # Create raw transaction for audit trail
        raw_transaction = RawTransaction(
            source_file=str(file_path),
            source_bank=self.bank_name,
            row_number=row_num,
            raw_fields=dict(row),
        )
        
        # Parse date - Macquarie uses "DD MMM YYYY" format
        trans_date = self._parse_macquarie_date(date_str)
        
        # Parse amounts - Macquarie uses separate debit/credit columns
        # Note: In Macquarie exports, Debit column shows money OUT, Credit shows money IN
        debit_amount = self._parse_amount(debit_str) if debit_str else Decimal('0')
        credit_amount = self._parse_amount(credit_str) if credit_str else Decimal('0')
        
        # Calculate signed amount
        # Macquarie's Debit column = money going OUT (should be negative)
        # Macquarie's Credit column = money coming IN (should be positive)
        if credit_amount > 0:
            amount = credit_amount
            trans_type = TransactionType.CREDIT
        elif debit_amount > 0:
            amount = -debit_amount
            trans_type = TransactionType.DEBIT
        else:
            amount = Decimal('0')
            trans_type = TransactionType.DEBIT
        
        # Check if it's a transfer based on category or description
        if self._is_transfer(category, subcategory, details):
            trans_type = TransactionType.TRANSFER
        
        # Parse balance
        balance = self._parse_amount(balance_str) if balance_str else None
        
        # Build combined category string
        original_category = self._build_category_string(category, subcategory, tags)
        
        # Derive account ID from account name
        account_id = self._derive_account_id(account_name)
        
        # Determine account type
        account_type = self._detect_account_type(account_name)
        
        # Extract merchant info
        merchant_name, location = self._parse_details(details, original_desc)
        
        # Generate unique ID
        trans_id = self._generate_transaction_id(
            trans_date, account_id, amount, details, row_num
        )
        
        return Transaction(
            id=trans_id,
            date=trans_date,
            amount=amount,
            description=details,
            account_id=account_id,
            account_type=account_type,
            bank_source=self.bank_name,
            source_file=str(file_path),
            balance=balance,
            original_category=original_category,
            transaction_type=trans_type,
            merchant_name=merchant_name,
            location=location,
            raw_transaction=raw_transaction,
        )
    
    def _parse_macquarie_date(self, date_str: str) -> date:
        """Parse Macquarie date format (DD MMM YYYY)."""
        # Remove quotes if present
        date_str = date_str.strip('"').strip()
        return datetime.strptime(date_str, self.config.date_format).date()
    
    def _is_transfer(self, category: str, subcategory: str, details: str) -> bool:
        """Check if transaction is a transfer."""
        # Macquarie categorizes transfers under "Financial" > "Transfers"
        if category.lower() == 'financial' and subcategory.lower() == 'transfers':
            return True
        
        transfer_keywords = ['Transfer', 'From ', 'To ']
        return any(kw.lower() in details.lower() for kw in transfer_keywords)
    
    def _build_category_string(self, category: str, subcategory: str, tags: str) -> Optional[str]:
        """Build a combined category string from Macquarie's rich categorization."""
        parts = []
        if category:
            parts.append(category)
        if subcategory:
            parts.append(subcategory)
        if tags:
            parts.append(f"[{tags}]")
        
        return " > ".join(parts) if parts else None
    
    def _derive_account_id(self, account_name: str) -> str:
        """Derive a short account ID from the full account name."""
        if not account_name:
            return "macquarie-unknown"
        
        # Simplify common account names
        name_lower = account_name.lower()
        if 'platinum' in name_lower and 'transaction' in name_lower:
            return "macquarie-platinum"
        elif 'savings' in name_lower:
            return "macquarie-savings"
        elif 'transaction' in name_lower:
            return "macquarie-transaction"
        
        # Fall back to slugified name
        return "macquarie-" + re.sub(r'[^a-z0-9]+', '-', name_lower).strip('-')
    
    def _detect_account_type(self, account_name: str) -> AccountType:
        """Detect account type from account name."""
        name_lower = account_name.lower()
        
        if 'savings' in name_lower:
            return AccountType.SAVINGS
        elif 'transaction' in name_lower:
            return AccountType.TRANSACTION
        elif 'credit' in name_lower:
            return AccountType.CREDIT_CARD
        elif 'loan' in name_lower:
            return AccountType.LOAN
        
        return AccountType.TRANSACTION
    
    def _parse_details(self, details: str, original_desc: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract merchant name and location from details."""
        if not details:
            return None, None
        
        # Macquarie details often have format:
        # "From Name - Reference"
        # "To Name - Description"
        # "Salary from Company"
        
        patterns = [
            r'^From\s+(.+?)\s+-\s+',
            r'^To\s+(.+?)\s+-\s+',
            r'^Salary from\s+(.+)',
            r'^Payment$',  # Generic payment
        ]
        
        for pattern in patterns:
            match = re.match(pattern, details, re.IGNORECASE)
            if match:
                return match.group(1).strip() if match.lastindex else details, None
        
        return details, None
