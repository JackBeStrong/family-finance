"""
ANZ Bank CSV Parser

Handles ANZ CSV exports which have a simpler format:
- No header row
- Signed amounts (positive = credit, negative = debit)
- Variable number of columns depending on transaction type

CSV Format (no headers):
- Column 0: Date (DD/MM/YYYY)
- Column 1: Amount (signed, quoted)
- Column 2: Description
- Column 3: Reference/Code (optional)
- Column 4: Payee/Reference (optional)
- Columns 5-7: Usually empty
"""

import re
from dataclasses import dataclass
from datetime import date
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
class ANZConfig:
    """Configuration for ANZ parser."""
    # Column indices (ANZ has no headers)
    col_date: int = 0
    col_amount: int = 1
    col_description: int = 2
    col_reference: int = 3
    col_payee: int = 4
    
    # Date format
    date_format: str = "%d/%m/%Y"
    
    # Default account type (ANZ exports are typically per-account)
    default_account_type: AccountType = AccountType.TRANSACTION


class ANZParser(BaseParser):
    """
    Parser for ANZ Bank CSV exports.
    
    ANZ exports are simpler than Westpac:
    - No header row
    - One account per file (typically)
    - Signed amounts in a single column
    """
    
    def __init__(self, config: Optional[ANZConfig] = None, account_id: Optional[str] = None):
        """
        Initialize the ANZ parser.
        
        Args:
            config: Optional configuration override
            account_id: Optional account identifier (since ANZ doesn't include it in CSV)
        """
        self.config = config or ANZConfig()
        self._account_id = account_id
    
    @property
    def bank_name(self) -> str:
        return "anz"
    
    def can_parse(self, file_path: Path) -> bool:
        """
        Check if this file is an ANZ CSV export.
        
        Detection is based on:
        1. CSV file extension
        2. Directory name OR filename contains 'anz'
        """
        if not file_path.suffix.lower() == '.csv':
            return False
        
        # Check if directory name or filename contains 'anz'
        dir_name = file_path.parent.name.lower()
        filename = file_path.stem.lower()  # filename without extension
        
        if 'anz' in dir_name or 'anz' in filename:
            return True
        
        return False
    
    def _parse_csv_line(self, line: str) -> List[str]:
        """Parse a CSV line handling quoted fields."""
        import csv
        from io import StringIO
        reader = csv.reader(StringIO(line))
        return next(reader, [])
    
    def parse(self, file_path: Path) -> List[Transaction]:
        """
        Parse ANZ CSV and return normalized transactions.
        
        Args:
            file_path: Path to the ANZ CSV file
            
        Returns:
            List of normalized Transaction objects
        """
        # Derive account ID from filename if not provided
        account_id = self._account_id or self._derive_account_id(file_path)
        
        # First pass: parse all rows into intermediate data
        parsed_data = []
        rows = self._read_csv(file_path, has_header=False)
        
        for row_num, row in enumerate(rows, start=1):
            try:
                data = self._parse_row_data(row, row_num, file_path, account_id)
                if data:
                    parsed_data.append(data)
            except Exception as e:
                # Log error but continue parsing
                print(f"Warning: Failed to parse row {row_num}: {e}")
                continue
        
        # Second pass: assign occurrence numbers for identical transactions
        parsed_data = self._assign_occurrence_numbers(parsed_data)
        
        # Third pass: create Transaction objects with proper IDs
        transactions = []
        for data in parsed_data:
            trans_id = self._generate_transaction_id(
                data['date'], data['account_id'], data['amount'],
                data['description'], data['occurrence']
            )
            
            transaction = Transaction(
                id=trans_id,
                date=data['date'],
                amount=data['amount'],
                description=data['description'],
                account_id=data['account_id'],
                account_type=data['account_type'],
                bank_source=self.bank_name,
                source_file=str(file_path),
                balance=data['balance'],
                original_category=data['original_category'],
                transaction_type=data['transaction_type'],
                merchant_name=data['merchant_name'],
                location=data['location'],
                raw_transaction=data['raw_transaction'],
            )
            transactions.append(transaction)
        
        return transactions
    
    def _derive_account_id(self, file_path: Path) -> str:
        """
        Derive account ID from file path.
        
        ANZ doesn't include account ID in the CSV, so we derive it from:
        1. Parent folder name
        2. File name
        """
        # Try to extract from parent folder (e.g., 'anz-transactional-account')
        parent_name = file_path.parent.name
        if parent_name and parent_name != '.':
            return parent_name
        
        # Fall back to filename without extension
        return file_path.stem
    
    def _parse_row_data(self, row: dict, row_num: int, file_path: Path,
                        account_id: str) -> Optional[dict]:
        """Parse a single CSV row into intermediate data dict for occurrence tracking."""
        
        # ANZ rows are indexed by column number (no headers)
        date_str = row.get(str(self.config.col_date), '').strip()
        amount_str = row.get(str(self.config.col_amount), '').strip()
        description = row.get(str(self.config.col_description), '').strip()
        reference = row.get(str(self.config.col_reference), '').strip()
        payee = row.get(str(self.config.col_payee), '').strip()
        
        # Skip empty rows
        if not date_str or not description:
            return None
        
        # Create raw transaction for audit trail
        raw_transaction = RawTransaction(
            source_file=str(file_path),
            source_bank=self.bank_name,
            row_number=row_num,
            raw_fields=dict(row),
        )
        
        # Parse date
        trans_date = self._parse_date(date_str, self.config.date_format)
        
        # Parse amount - ANZ uses signed amounts
        amount = self._parse_amount(amount_str)
        
        # Determine transaction type from sign
        if amount > 0:
            trans_type = TransactionType.CREDIT
        elif amount < 0:
            trans_type = TransactionType.DEBIT
        else:
            trans_type = TransactionType.DEBIT
        
        # Check if it's a transfer
        if self._is_transfer(description):
            trans_type = TransactionType.TRANSFER
        
        # Build enhanced description with payee if available
        full_description = description
        if payee:
            full_description = f"{description} - {payee}"
        
        # Extract merchant and location
        merchant_name, location = self._parse_description(description, payee)
        
        # Return data dict (ID will be generated after occurrence assignment)
        return {
            'date': trans_date,
            'amount': amount,
            'description': full_description,
            'account_id': account_id,
            'account_type': self.config.default_account_type,
            'balance': None,  # ANZ doesn't include balance in exports
            'original_category': None,  # ANZ doesn't categorize
            'transaction_type': trans_type,
            'merchant_name': merchant_name,
            'location': location,
            'raw_transaction': raw_transaction,
        }
    
    def _is_transfer(self, description: str) -> bool:
        """Check if transaction is an internal transfer."""
        transfer_keywords = [
            'TRANSFER FROM',
            'TRANSFER TO',
            'ANZ INTERNET BANKING PAYMENT',
            'ANZ INTERNET BANKING TRANSFER',
            'INTERNAL TRANSFER',
        ]
        description_upper = description.upper()
        return any(kw in description_upper for kw in transfer_keywords)
    
    def _parse_description(self, description: str, payee: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract merchant name and location from description.
        
        ANZ descriptions are typically simpler than Westpac.
        """
        if not description:
            return None, None
        
        # If payee is provided, use it as merchant name
        if payee:
            return payee, None
        
        # Try to extract from description patterns
        # ANZ often has format: "DESCRIPTION TO/FROM NAME"
        to_from_pattern = r'(?:TO|FROM)\s+(.+)$'
        match = re.search(to_from_pattern, description, re.IGNORECASE)
        if match:
            return match.group(1).strip(), None
        
        return description, None
