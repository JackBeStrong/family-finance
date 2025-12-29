"""
SQLite implementation of the TransactionRepository.

This module provides a local SQLite database for storing transactions.
The database file is stored in the data/ directory by default.
"""

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.parsers.base import Transaction, TransactionType, AccountType
from src.database.repository import TransactionRepository


class SQLiteRepository(TransactionRepository):
    """
    SQLite implementation of TransactionRepository.
    
    Stores transactions in a local SQLite database file.
    Duplicate detection is handled by the transaction ID (primary key).
    """
    
    def __init__(self, db_path: str = "data/transactions.db"):
        """
        Initialize the SQLite repository.
        
        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self.initialize()
    
    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn
    
    def initialize(self) -> None:
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()
        
        # Transactions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                amount TEXT NOT NULL,
                description TEXT NOT NULL,
                account_id TEXT NOT NULL,
                account_type TEXT NOT NULL,
                bank_source TEXT NOT NULL,
                source_file TEXT NOT NULL,
                balance TEXT,
                original_category TEXT,
                category TEXT,
                transaction_type TEXT NOT NULL,
                merchant_name TEXT,
                location TEXT,
                foreign_amount TEXT,
                foreign_currency TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_date 
            ON transactions(date)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_bank_account 
            ON transactions(bank_source, account_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_category 
            ON transactions(category)
        """)
        
        self.conn.commit()
    
    # ==================== Transaction CRUD ====================
    
    def save_transaction(self, transaction: Transaction, verbose: bool = False) -> bool:
        """Save a single transaction. Returns False if duplicate."""
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO transactions
                (id, date, amount, description, account_id, account_type,
                 bank_source, source_file, balance, original_category, category,
                 transaction_type, merchant_name, location, foreign_amount,
                 foreign_currency, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                transaction.id,
                transaction.date.isoformat(),
                str(transaction.amount),
                transaction.description,
                transaction.account_id,
                transaction.account_type.value,
                transaction.bank_source,
                transaction.source_file,
                str(transaction.balance) if transaction.balance is not None else None,
                transaction.original_category,
                transaction.category,
                transaction.transaction_type.value,
                transaction.merchant_name,
                transaction.location,
                str(transaction.foreign_amount) if transaction.foreign_amount is not None else None,
                transaction.foreign_currency,
                transaction.created_at.isoformat(),
            ))
            self.conn.commit()
            if verbose:
                print(f"    [SAVED] {transaction.id}")
            return True
        except sqlite3.IntegrityError as e:
            # Duplicate ID - transaction already exists
            if verbose:
                print(f"    [SKIP] {transaction.id} - duplicate")
            return False
    
    def save_transactions(self, transactions: List[Transaction], verbose: bool = False) -> Tuple[int, int]:
        """Save multiple transactions. Returns (saved_count, skipped_count)."""
        saved_count = 0
        skipped_count = 0
        for txn in transactions:
            if self.save_transaction(txn, verbose):
                saved_count += 1
            else:
                skipped_count += 1
        return saved_count, skipped_count
    
    def get_transaction_by_id(self, transaction_id: str) -> Optional[Transaction]:
        """Get a transaction by its ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
        row = cursor.fetchone()
        
        if row is None:
            return None
        
        return self._row_to_transaction(row)
    
    def get_transactions(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        bank_source: Optional[str] = None,
        account_id: Optional[str] = None,
        category: Optional[str] = None,
        transaction_type: Optional[TransactionType] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Transaction]:
        """Query transactions with optional filters."""
        query = "SELECT * FROM transactions WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat())
        
        if bank_source:
            query += " AND bank_source = ?"
            params.append(bank_source)
        
        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)
        
        if category:
            query += " AND (category = ? OR original_category = ?)"
            params.extend([category, category])
        
        if transaction_type:
            query += " AND transaction_type = ?"
            params.append(transaction_type.value)
        
        if min_amount is not None:
            query += " AND CAST(amount AS REAL) >= ?"
            params.append(min_amount)
        
        if max_amount is not None:
            query += " AND CAST(amount AS REAL) <= ?"
            params.append(max_amount)
        
        query += " ORDER BY date DESC, id"
        
        if limit:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        
        return [self._row_to_transaction(row) for row in cursor.fetchall()]
    
    def count_transactions(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        bank_source: Optional[str] = None,
    ) -> int:
        """Count transactions matching the filters."""
        query = "SELECT COUNT(*) FROM transactions WHERE 1=1"
        params = []
        
        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat())
        
        if bank_source:
            query += " AND bank_source = ?"
            params.append(bank_source)
        
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()[0]
    
    def delete_transaction(self, transaction_id: str) -> bool:
        """Delete a transaction by ID."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def update_transaction_category(
        self, 
        transaction_id: str, 
        category: str
    ) -> bool:
        """Update the category of a transaction."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE transactions SET category = ? WHERE id = ?",
            (category, transaction_id)
        )
        self.conn.commit()
        return cursor.rowcount > 0
    
    def get_distinct_values(self, field: str) -> List[str]:
        """Get distinct values for a field."""
        allowed_fields = {'category', 'original_category', 'bank_source', 'account_id'}
        if field not in allowed_fields:
            raise ValueError(f"Field must be one of: {allowed_fields}")
        
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT DISTINCT {field} FROM transactions WHERE {field} IS NOT NULL ORDER BY {field}")
        return [row[0] for row in cursor.fetchall()]
    
    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def _row_to_transaction(self, row: sqlite3.Row) -> Transaction:
        """Convert a database row to a Transaction object."""
        return Transaction(
            id=row['id'],
            date=date.fromisoformat(row['date']),
            amount=Decimal(row['amount']),
            description=row['description'],
            account_id=row['account_id'],
            account_type=AccountType(row['account_type']),
            bank_source=row['bank_source'],
            source_file=row['source_file'],
            balance=Decimal(row['balance']) if row['balance'] else None,
            original_category=row['original_category'],
            category=row['category'],
            transaction_type=TransactionType(row['transaction_type']),
            merchant_name=row['merchant_name'],
            location=row['location'],
            foreign_amount=Decimal(row['foreign_amount']) if row['foreign_amount'] else None,
            foreign_currency=row['foreign_currency'],
            created_at=datetime.fromisoformat(row['created_at']),
            raw_transaction=None,  # Raw data not stored in DB
        )
