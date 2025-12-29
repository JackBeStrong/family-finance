"""
Commonwealth Bank (CBA) CSV Parser

Handles CBA CSV exports with the following format:
- No header row
- Columns: Date, Amount (signed with +/-), Description, Balance
- Date format: DD/MM/YYYY
- Amounts: Single signed column with explicit +/- prefix
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
class CBAConfig:
    """Configuration for CBA parser."""
    # Column indices (CBA has no headers)
    col_date: int = 0
    col_amount: int = 1
    col_description: int = 2
    col_balance: int = 3
    
    # Date format
    date_format: str = "%d/%m/%Y"
    
    # Default account type
    default_account_type: AccountType = AccountType.TRANSACTION


class CBAParser(BaseParser):
    """
    Parser for Commonwealth Bank (CBA) CSV exports.
    
    CBA exports are headerless with signed amounts that include
    explicit +/- prefixes (e.g., "+2716.10", "-2716.10").
    """
    
    def __init__(self, config: Optional[CBAConfig] = None, account_id: Optional[str] = None):
        """
        Initialize the CBA parser.
        
        Args:
            config: Optional configuration override
            account_id: Optional account identifier (since CBA doesn't include it in CSV)
        """
        self.config = config or CBAConfig()
        self._account_id = account_id
    
    @property
    def bank_name(self) -> str:
        return "cba"
    
    def can_parse(self, file_path: Path) -> bool:
        """
        Check if this file is a CBA CSV export.
        
        Detection is based on:
        1. CSV file extension
        2. Directory name contains 'cba'
        """
        if not file_path.suffix.lower() == '.csv':
            return False
        
        # Check if directory name indicates CBA
        dir_name = file_path.parent.name.lower()
        if 'cba' in dir_name or 'commbank' in dir_name or 'commonwealth' in dir_name:
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
        Parse CBA CSV and return normalized transactions.
        
        Args:
            file_path: Path to the CBA CSV file
            
        Returns:
            List of normalized Transaction objects
        """
        transactions = []
        
        # Derive account ID from filename if not provided
        account_id = self._account_id or self._derive_account_id(file_path)
        
        rows = self._read_csv(file_path, has_header=False)
        
        for row_num, row in enumerate(rows, start=1):
            try:
                transaction = self._parse_row(row, row_num, file_path, account_id)
                if transaction:
                    transactions.append(transaction)
            except Exception as e:
                print(f"Warning: Failed to parse row {row_num}: {e}")
                continue
        
        return transactions
    
    def _derive_account_id(self, file_path: Path) -> str:
        """
        Derive account ID from file path.
        
        CBA doesn't include account ID in the CSV, so we derive it from:
        1. Parent folder name
        2. File name
        """
        parent_name = file_path.parent.name
        if parent_name and parent_name != '.':
            return parent_name
        return file_path.stem
    
    def _parse_row(self, row: dict, row_num: int, file_path: Path, 
                   account_id: str) -> Optional[Transaction]:
        """Parse a single CSV row into a Transaction."""
        
        # CBA rows are indexed by column number (no headers)
        date_str = row.get(str(self.config.col_date), '').strip()
        amount_str = row.get(str(self.config.col_amount), '').strip()
        description = row.get(str(self.config.col_description), '').strip()
        balance_str = row.get(str(self.config.col_balance), '').strip()
        
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
        
        # Parse amount - CBA uses explicit +/- prefix
        amount = self._parse_cba_amount(amount_str)
        
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
        
        # Parse balance
        balance = self._parse_cba_amount(balance_str) if balance_str else None
        
        # Extract merchant info from description
        merchant_name, location = self._parse_description(description)
        
        # Generate unique ID
        trans_id = self._generate_transaction_id(
            trans_date, account_id, amount, description, row_num
        )
        
        return Transaction(
            id=trans_id,
            date=trans_date,
            amount=amount,
            description=description,
            account_id=account_id,
            account_type=self.config.default_account_type,
            bank_source=self.bank_name,
            source_file=str(file_path),
            balance=balance,
            original_category=None,  # CBA doesn't categorize
            transaction_type=trans_type,
            merchant_name=merchant_name,
            location=location,
            raw_transaction=raw_transaction,
        )
    
    def _parse_cba_amount(self, amount_str: str) -> Decimal:
        """Parse CBA amount format with explicit +/- prefix."""
        if not amount_str or amount_str.strip() == '':
            return Decimal('0')
        
        # Remove quotes and clean up
        cleaned = amount_str.strip().replace('"', '').replace(',', '').replace(' ', '')
        
        # CBA format: "+2716.10" or "-2716.10"
        return Decimal(cleaned)
    
    def _is_transfer(self, description: str) -> bool:
        """Check if transaction is an internal transfer."""
        transfer_keywords = [
            'Transfer To',
            'Transfer From',
            'Fast Transfer',
            'Direct Credit',
            'NetBank',
            'CommBank App',
        ]
        description_upper = description.upper()
        return any(kw.upper() in description_upper for kw in transfer_keywords)
    
    def _parse_description(self, description: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract merchant name and location from description."""
        if not description:
            return None, None
        
        # CBA descriptions often have format:
        # "Transfer To/From Name Method"
        # "Direct Credit NNNNNN Name DESCRIPTION"
        # "Fast Transfer From Name Reference"
        
        patterns = [
            r'Transfer (?:To|From)\s+(.+?)\s+(?:NetBank|CommBank)',
            r'Fast Transfer From\s+(.+?)\s+CT\.',
            r'Direct Credit \d+\s+(.+?)\s+RENT',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                return match.group(1).strip(), None
        
        return description, None
