"""
Westpac Bank CSV Parser

Handles Westpac CSV exports which can contain multiple account types:
- Credit cards (4-digit account numbers like 7802)
- Savings/Transaction accounts (longer account numbers)
- Foreign currency transactions

CSV Format:
- Headers: Bank Account,Date,Narrative,Debit Amount,Credit Amount,Balance,Categories,Serial
- Date format: DD/MM/YYYY
- Amounts: Separate debit/credit columns
- Categories: Bank's own categorization (PAYMENT, OTHER, DEP, CREDIT, CASH, FEE)
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
class WestpacConfig:
    """Configuration for Westpac parser."""
    # Column names (can be customized if Westpac changes format)
    col_account: str = "Bank Account"
    col_date: str = "Date"
    col_narrative: str = "Narrative"
    col_debit: str = "Debit Amount"
    col_credit: str = "Credit Amount"
    col_balance: str = "Balance"
    col_category: str = "Categories"
    col_serial: str = "Serial"
    
    # Date format
    date_format: str = "%d/%m/%Y"
    
    # Account type detection patterns
    credit_card_pattern: str = r"^\d{4}$"  # 4-digit = credit card
    

class WestpacParser(BaseParser):
    """
    Parser for Westpac Bank CSV exports.
    
    Westpac exports can contain transactions from multiple accounts
    in a single file, including credit cards and savings accounts.
    """
    
    def __init__(self, config: Optional[WestpacConfig] = None):
        """
        Initialize the Westpac parser.
        
        Args:
            config: Optional configuration override
        """
        self.config = config or WestpacConfig()
    
    @property
    def bank_name(self) -> str:
        return "westpac"
    
    def can_parse(self, file_path: Path) -> bool:
        """
        Check if this file is a Westpac CSV export.
        
        Detection is based on:
        1. CSV file extension
        2. Header row containing Westpac-specific columns
        """
        if not file_path.suffix.lower() == '.csv':
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                first_line = f.readline().strip()
                
            # Check for Westpac-specific header columns
            required_columns = [
                self.config.col_account,
                self.config.col_narrative,
                self.config.col_debit,
                self.config.col_credit,
            ]
            
            return all(col in first_line for col in required_columns)
            
        except Exception:
            return False
    
    def parse(self, file_path: Path) -> List[Transaction]:
        """
        Parse Westpac CSV and return normalized transactions.
        
        Args:
            file_path: Path to the Westpac CSV file
            
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
                # Log error but continue parsing
                print(f"Warning: Failed to parse row {row_num}: {e}")
                continue
        
        return transactions
    
    def _parse_row(self, row: dict, row_num: int, file_path: Path) -> Optional[Transaction]:
        """Parse a single CSV row into a Transaction."""
        
        # Extract raw values
        account_id = row.get(self.config.col_account, '').strip()
        date_str = row.get(self.config.col_date, '').strip()
        narrative = row.get(self.config.col_narrative, '').strip()
        debit_str = row.get(self.config.col_debit, '').strip()
        credit_str = row.get(self.config.col_credit, '').strip()
        balance_str = row.get(self.config.col_balance, '').strip()
        category = row.get(self.config.col_category, '').strip()
        
        # Skip empty rows
        if not date_str or not narrative:
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
        
        # Parse amounts - Westpac uses separate debit/credit columns
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
        
        # Detect if it's a transfer
        if self._is_transfer(narrative, category):
            trans_type = TransactionType.TRANSFER
        
        # Parse balance
        balance = self._parse_amount(balance_str) if balance_str else None
        
        # Determine account type
        account_type = self._detect_account_type(account_id)
        
        # Extract merchant and location from narrative
        merchant_name, location = self._parse_narrative(narrative)
        
        # Extract foreign currency info if present
        foreign_amount, foreign_currency = self._parse_foreign_currency(narrative)
        
        # Generate unique ID
        trans_id = self._generate_transaction_id(
            trans_date, account_id, amount, narrative, row_num
        )
        
        return Transaction(
            id=trans_id,
            date=trans_date,
            amount=amount,
            description=narrative,
            account_id=account_id,
            account_type=account_type,
            bank_source=self.bank_name,
            source_file=str(file_path),
            balance=balance,
            original_category=category if category else None,
            transaction_type=trans_type,
            merchant_name=merchant_name,
            location=location,
            foreign_amount=foreign_amount,
            foreign_currency=foreign_currency,
            raw_transaction=raw_transaction,
        )
    
    def _detect_account_type(self, account_id: str) -> AccountType:
        """Detect account type from account ID pattern."""
        if re.match(self.config.credit_card_pattern, account_id):
            return AccountType.CREDIT_CARD
        elif len(account_id) > 8:
            # Longer account numbers are typically savings/transaction
            return AccountType.SAVINGS
        else:
            return AccountType.UNKNOWN
    
    def _is_transfer(self, narrative: str, category: str) -> bool:
        """Check if transaction is an internal transfer."""
        transfer_keywords = ['TFR FROM', 'TFR TO', 'TRANSFER', 'TFR Westpac', 'TFR Altitude']
        narrative_upper = narrative.upper()
        
        if category == 'PAYMENT' and any(kw.upper() in narrative_upper for kw in transfer_keywords):
            return True
        
        return False
    
    def _parse_narrative(self, narrative: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract merchant name and location from narrative.
        
        Westpac narratives often follow patterns like:
        - "MERCHANT NAME LOCATION AUS"
        - "MERCHANT NAME CITY STATE AUS"
        """
        if not narrative:
            return None, None
        
        # Common location suffixes
        location_patterns = [
            r'\s+(AUS|USA|GBR|NZL|SGP|HKG|JPN|CHN)$',
            r'\s+([A-Z]{2,})\s+(AUS|USA|GBR|NZL)$',
        ]
        
        merchant = narrative
        location = None
        
        # Try to extract location
        for pattern in location_patterns:
            match = re.search(pattern, narrative)
            if match:
                location = match.group(0).strip()
                merchant = narrative[:match.start()].strip()
                break
        
        return merchant if merchant else None, location
    
    def _parse_foreign_currency(self, narrative: str) -> Tuple[Optional[Decimal], Optional[str]]:
        """
        Extract foreign currency amount and code from narrative.
        
        Westpac includes foreign currency info like:
        "FRGN AMT: 10.00  U. S. DOLLAR"
        """
        # Pattern for foreign amount
        frgn_pattern = r'FRGN AMT:\s*([\d.]+)\s+([A-Z.\s]+(?:DOLLAR|POUND|EURO|YEN))'
        
        match = re.search(frgn_pattern, narrative, re.IGNORECASE)
        if match:
            try:
                amount = Decimal(match.group(1))
                currency_text = match.group(2).strip()
                
                # Map currency text to code
                currency_map = {
                    'U. S. DOLLAR': 'USD',
                    'U.S. DOLLAR': 'USD',
                    'POUND': 'GBP',
                    'EURO': 'EUR',
                    'YEN': 'JPY',
                }
                
                currency = currency_map.get(currency_text.upper(), currency_text)
                return amount, currency
            except (ValueError, InvalidOperation):
                pass
        
        return None, None


# For backwards compatibility and easy importing
from decimal import InvalidOperation
