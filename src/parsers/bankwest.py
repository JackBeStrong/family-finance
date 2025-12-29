"""
Bankwest CSV Parser

Handles Bankwest CSV exports with the following format:
- Headers: BSB Number,Account Number,Transaction Date,Narration,Cheque,Debit,Credit,Balance,Transaction Type
- Date format: DD/MM/YYYY
- Amounts: Separate debit/credit columns
- Transaction types: WDL (withdrawal), DEP (deposit), etc.
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
class BankwestConfig:
    """Configuration for Bankwest parser."""
    # Column names
    col_bsb: str = "BSB Number"
    col_account: str = "Account Number"
    col_date: str = "Transaction Date"
    col_narration: str = "Narration"
    col_cheque: str = "Cheque"
    col_debit: str = "Debit"
    col_credit: str = "Credit"
    col_balance: str = "Balance"
    col_type: str = "Transaction Type"
    
    # Date format
    date_format: str = "%d/%m/%Y"


class BankwestParser(BaseParser):
    """
    Parser for Bankwest CSV exports.
    
    Bankwest exports include BSB and account number separately,
    with transaction type codes like WDL, DEP, etc.
    """
    
    def __init__(self, config: Optional[BankwestConfig] = None):
        """
        Initialize the Bankwest parser.
        
        Args:
            config: Optional configuration override
        """
        self.config = config or BankwestConfig()
    
    @property
    def bank_name(self) -> str:
        return "bankwest"
    
    def can_parse(self, file_path: Path) -> bool:
        """
        Check if this file is a Bankwest CSV export.
        
        Detection is based on:
        1. CSV file extension
        2. Header row containing Bankwest-specific columns (BSB Number, Narration)
        """
        if not file_path.suffix.lower() == '.csv':
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                first_line = f.readline().strip()
            
            # Check for Bankwest-specific header columns
            required_columns = [
                self.config.col_bsb,
                self.config.col_narration,
                self.config.col_type,
            ]
            
            return all(col in first_line for col in required_columns)
            
        except Exception:
            return False
    
    def parse(self, file_path: Path) -> List[Transaction]:
        """
        Parse Bankwest CSV and return normalized transactions.
        
        Args:
            file_path: Path to the Bankwest CSV file
            
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
        bsb = row.get(self.config.col_bsb, '').strip()
        account_num = row.get(self.config.col_account, '').strip()
        date_str = row.get(self.config.col_date, '').strip()
        narration = row.get(self.config.col_narration, '').strip()
        debit_str = row.get(self.config.col_debit, '').strip()
        credit_str = row.get(self.config.col_credit, '').strip()
        balance_str = row.get(self.config.col_balance, '').strip()
        trans_type_code = row.get(self.config.col_type, '').strip()
        
        # Skip empty rows
        if not date_str or not narration:
            return None
        
        # Build account ID from BSB and account number
        account_id = f"{bsb}-{account_num}" if bsb and account_num else account_num or bsb
        
        # Create raw transaction for audit trail
        raw_transaction = RawTransaction(
            source_file=str(file_path),
            source_bank=self.bank_name,
            row_number=row_num,
            raw_fields=dict(row),
        )
        
        # Parse date
        trans_date = self._parse_date(date_str, self.config.date_format)
        
        # Parse amounts - Bankwest uses separate debit/credit columns
        debit_amount = self._parse_amount(debit_str) if debit_str else Decimal('0')
        credit_amount = self._parse_amount(credit_str) if credit_str else Decimal('0')
        
        # Calculate signed amount (positive = credit, negative = debit)
        if credit_amount > 0:
            amount = credit_amount
            trans_type = TransactionType.CREDIT
        elif debit_amount > 0:
            amount = -debit_amount
            trans_type = TransactionType.DEBIT
        else:
            amount = Decimal('0')
            trans_type = TransactionType.DEBIT
        
        # Map transaction type code
        trans_type = self._map_transaction_type(trans_type_code, trans_type)
        
        # Parse balance
        balance = self._parse_amount(balance_str) if balance_str else None
        
        # Extract merchant and location from narration
        merchant_name, location = self._parse_narration(narration)
        
        # Generate unique ID
        trans_id = self._generate_transaction_id(
            trans_date, account_id, amount, narration, row_num
        )
        
        return Transaction(
            id=trans_id,
            date=trans_date,
            amount=amount,
            description=narration,
            account_id=account_id,
            account_type=AccountType.TRANSACTION,
            bank_source=self.bank_name,
            source_file=str(file_path),
            balance=balance,
            original_category=trans_type_code if trans_type_code else None,
            transaction_type=trans_type,
            merchant_name=merchant_name,
            location=location,
            raw_transaction=raw_transaction,
        )
    
    def _map_transaction_type(self, type_code: str, default: TransactionType) -> TransactionType:
        """Map Bankwest transaction type codes to our types."""
        type_map = {
            'WDL': TransactionType.DEBIT,      # Withdrawal
            'DEP': TransactionType.CREDIT,     # Deposit
            'TFR': TransactionType.TRANSFER,   # Transfer
            'INT': TransactionType.CREDIT,     # Interest
            'FEE': TransactionType.DEBIT,      # Fee
        }
        return type_map.get(type_code.upper(), default)
    
    def _parse_narration(self, narration: str) -> Tuple[Optional[str], Optional[str]]:
        """Extract merchant name and location from narration."""
        if not narration:
            return None, None
        
        # Bankwest narrations often have format: "To/From Name Time Date"
        # Try to extract the main part
        patterns = [
            r'^(?:To|From)\s+(.+?)\s+\d{2}:\d{2}[AP]M',  # "To Name 08:17PM"
            r'^(.+?)\s+\d{2}:\d{2}[AP]M',  # "Name 08:17PM"
        ]
        
        for pattern in patterns:
            match = re.match(pattern, narration, re.IGNORECASE)
            if match:
                return match.group(1).strip(), None
        
        return narration, None
