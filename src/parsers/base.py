"""
Base parser module defining the transaction data models and abstract parser interface.

This module provides:
- RawTransaction: Captures all original fields from bank CSV files
- Transaction: Normalized transaction format for analysis
- BaseParser: Abstract base class for bank-specific parsers
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any
import csv
import json


class TransactionType(Enum):
    """Type of transaction based on money flow."""
    DEBIT = "debit"      # Money going out
    CREDIT = "credit"    # Money coming in
    TRANSFER = "transfer"  # Internal transfer


class AccountType(Enum):
    """Type of bank account."""
    CREDIT_CARD = "credit_card"
    SAVINGS = "savings"
    TRANSACTION = "transaction"
    LOAN = "loan"
    UNKNOWN = "unknown"


@dataclass
class RawTransaction:
    """
    Captures all original fields from the bank CSV file.
    This preserves the raw data for audit trails and debugging.
    """
    # Source information
    source_file: str
    source_bank: str
    row_number: int
    
    # Raw field values (as strings, exactly as they appear in CSV)
    raw_fields: Dict[str, str] = field(default_factory=dict)
    
    # Parsing metadata
    parsed_at: datetime = field(default_factory=datetime.now)
    parse_errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['parsed_at'] = self.parsed_at.isoformat()
        return result


@dataclass
class Transaction:
    """
    Normalized transaction format for analysis and reporting.
    
    This is the standardized format that all bank parsers output to,
    enabling consistent analysis across different bank sources.
    """
    # Unique identifier (generated)
    id: str
    
    # Core transaction data
    date: date
    amount: Decimal  # Positive for credits, negative for debits
    description: str
    
    # Account information
    account_id: str
    account_type: AccountType
    
    # Source tracking
    bank_source: str  # e.g., "westpac", "anz", "commbank"
    source_file: str
    
    # Optional fields (may not be available from all banks)
    balance: Optional[Decimal] = None
    original_category: Optional[str] = None  # Bank's own categorization
    category: Optional[str] = None  # Our unified category (set later)
    
    # Transaction type
    transaction_type: TransactionType = TransactionType.DEBIT
    
    # Additional metadata
    merchant_name: Optional[str] = None
    location: Optional[str] = None
    foreign_amount: Optional[Decimal] = None
    foreign_currency: Optional[str] = None
    
    # Reference to raw data
    raw_transaction: Optional[RawTransaction] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            'id': self.id,
            'date': self.date.isoformat(),
            'amount': str(self.amount),
            'description': self.description,
            'account_id': self.account_id,
            'account_type': self.account_type.value,
            'bank_source': self.bank_source,
            'source_file': self.source_file,
            'balance': str(self.balance) if self.balance is not None else None,
            'original_category': self.original_category,
            'category': self.category,
            'transaction_type': self.transaction_type.value,
            'merchant_name': self.merchant_name,
            'location': self.location,
            'foreign_amount': str(self.foreign_amount) if self.foreign_amount is not None else None,
            'foreign_currency': self.foreign_currency,
            'created_at': self.created_at.isoformat(),
        }
        
        # Include raw transaction if present
        if self.raw_transaction:
            result['raw_transaction'] = self.raw_transaction.to_dict()
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Transaction':
        """Create Transaction from dictionary."""
        # Handle raw_transaction separately
        raw_data = data.pop('raw_transaction', None)
        raw_transaction = None
        if raw_data:
            raw_data['parsed_at'] = datetime.fromisoformat(raw_data['parsed_at'])
            raw_transaction = RawTransaction(**raw_data)
        
        return cls(
            id=data['id'],
            date=date.fromisoformat(data['date']),
            amount=Decimal(data['amount']),
            description=data['description'],
            account_id=data['account_id'],
            account_type=AccountType(data['account_type']),
            bank_source=data['bank_source'],
            source_file=data['source_file'],
            balance=Decimal(data['balance']) if data.get('balance') else None,
            original_category=data.get('original_category'),
            category=data.get('category'),
            transaction_type=TransactionType(data['transaction_type']),
            merchant_name=data.get('merchant_name'),
            location=data.get('location'),
            foreign_amount=Decimal(data['foreign_amount']) if data.get('foreign_amount') else None,
            foreign_currency=data.get('foreign_currency'),
            raw_transaction=raw_transaction,
            created_at=datetime.fromisoformat(data['created_at']),
        )


class BaseParser(ABC):
    """
    Abstract base class for bank-specific CSV parsers.
    
    Each bank parser must implement:
    - bank_name: Property returning the bank identifier
    - can_parse(): Method to detect if a file matches this bank's format
    - parse(): Method to parse the CSV and return normalized transactions
    """
    
    @property
    @abstractmethod
    def bank_name(self) -> str:
        """Return the bank identifier (e.g., 'westpac', 'anz')."""
        pass
    
    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        """
        Check if this parser can handle the given CSV file.
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            True if this parser can handle the file format
        """
        pass
    
    @abstractmethod
    def parse(self, file_path: Path) -> List[Transaction]:
        """
        Parse the CSV file and return normalized transactions.
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            List of normalized Transaction objects
        """
        pass
    
    def _generate_transaction_id(self, date: date, account_id: str, 
                                  amount: Decimal, description: str,
                                  row_number: int) -> str:
        """
        Generate a unique transaction ID.
        
        Format: {bank}_{date}_{account}_{row}_{hash}
        """
        import hashlib
        
        # Create a hash from the transaction details
        hash_input = f"{date.isoformat()}|{account_id}|{amount}|{description}"
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        
        return f"{self.bank_name}_{date.strftime('%Y%m%d')}_{account_id}_{row_number}_{hash_value}"
    
    def _parse_date(self, date_str: str, format: str = "%d/%m/%Y") -> date:
        """Parse a date string to a date object."""
        return datetime.strptime(date_str, format).date()
    
    def _parse_amount(self, amount_str: str) -> Decimal:
        """Parse an amount string to Decimal, handling various formats."""
        if not amount_str or amount_str.strip() == '':
            return Decimal('0')
        
        # Remove currency symbols, spaces, and commas
        cleaned = amount_str.strip().replace('$', '').replace(',', '').replace(' ', '')
        
        # Handle parentheses for negative numbers
        if cleaned.startswith('(') and cleaned.endswith(')'):
            cleaned = '-' + cleaned[1:-1]
        
        return Decimal(cleaned)
    
    def _read_csv(self, file_path: Path, has_header: bool = True) -> List[Dict[str, str]]:
        """
        Read CSV file and return list of row dictionaries.
        
        Args:
            file_path: Path to CSV file
            has_header: Whether the CSV has a header row
            
        Returns:
            List of dictionaries, one per row
        """
        rows = []
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            if has_header:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(row)
            else:
                reader = csv.reader(f)
                for row in reader:
                    # Create dict with numeric keys for headerless CSV
                    rows.append({str(i): val for i, val in enumerate(row)})
        return rows


def save_transactions_json(transactions: List[Transaction], output_path: Path) -> None:
    """Save transactions to a JSON file."""
    data = {
        'exported_at': datetime.now().isoformat(),
        'count': len(transactions),
        'transactions': [t.to_dict() for t in transactions]
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_transactions_csv(transactions: List[Transaction], output_path: Path) -> None:
    """Save transactions to a CSV file (without raw data)."""
    if not transactions:
        return
    
    fieldnames = [
        'id', 'date', 'amount', 'description', 'account_id', 'account_type',
        'bank_source', 'source_file', 'balance', 'original_category', 'category',
        'transaction_type', 'merchant_name', 'location', 'foreign_amount',
        'foreign_currency', 'created_at'
    ]
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for t in transactions:
            row = {
                'id': t.id,
                'date': t.date.isoformat(),
                'amount': str(t.amount),
                'description': t.description,
                'account_id': t.account_id,
                'account_type': t.account_type.value,
                'bank_source': t.bank_source,
                'source_file': t.source_file,
                'balance': str(t.balance) if t.balance is not None else '',
                'original_category': t.original_category or '',
                'category': t.category or '',
                'transaction_type': t.transaction_type.value,
                'merchant_name': t.merchant_name or '',
                'location': t.location or '',
                'foreign_amount': str(t.foreign_amount) if t.foreign_amount is not None else '',
                'foreign_currency': t.foreign_currency or '',
                'created_at': t.created_at.isoformat(),
            }
            writer.writerow(row)
