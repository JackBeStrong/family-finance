"""
PostgreSQL implementation of the TransactionRepository.

This module provides a PostgreSQL database for storing transactions,
enabling independent access for reporting and other services.
"""

import os
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.parsers.base import Transaction, TransactionType, AccountType
from src.database.repository import TransactionRepository

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False


class PostgresRepository(TransactionRepository):
    """
    PostgreSQL implementation of TransactionRepository.
    
    Stores transactions in a PostgreSQL database for shared access
    by multiple services (watcher, reporting, etc.).
    """
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        database: str = None,
        user: str = None,
        password: str = None,
    ):
        """
        Initialize the PostgreSQL repository.
        
        Args:
            host: PostgreSQL host (default: DB_HOST env var or localhost)
            port: PostgreSQL port (default: DB_PORT env var or 5432)
            database: Database name (default: DB_NAME env var or family_finance)
            user: Database user (default: DB_USER env var)
            password: Database password (default: DB_PASSWORD env var)
        """
        if not PSYCOPG2_AVAILABLE:
            raise ImportError("psycopg2 is required for PostgreSQL support. Install with: pip install psycopg2-binary")
        
        self.host = host or os.environ.get('DB_HOST', 'localhost')
        self.port = port or int(os.environ.get('DB_PORT', '5432'))
        self.database = database or os.environ.get('DB_NAME', 'family_finance')
        self.user = user or os.environ.get('DB_USER')
        self.password = password or os.environ.get('DB_PASSWORD')
        
        if not self.user or not self.password:
            raise ValueError("Database user and password are required. Set DB_USER and DB_PASSWORD environment variables.")
        
        self._conn = None
        self.initialize()
    
    @property
    def conn(self):
        """Get or create database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
            )
        return self._conn
    
    def initialize(self) -> None:
        """Create database tables if they don't exist."""
        cursor = self.conn.cursor()
        
        # Transactions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                date DATE NOT NULL,
                amount DECIMAL(15, 2) NOT NULL,
                description TEXT NOT NULL,
                account_id TEXT NOT NULL,
                account_type TEXT NOT NULL,
                bank_source TEXT NOT NULL,
                source_file TEXT NOT NULL,
                balance DECIMAL(15, 2),
                original_category TEXT,
                category TEXT,
                transaction_type TEXT NOT NULL,
                merchant_name TEXT,
                location TEXT,
                foreign_amount DECIMAL(15, 2),
                foreign_currency TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_amount 
            ON transactions(amount)
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (
                transaction.id,
                transaction.date,
                transaction.amount,
                transaction.description,
                transaction.account_id,
                transaction.account_type.value,
                transaction.bank_source,
                transaction.source_file,
                transaction.balance,
                transaction.original_category,
                transaction.category,
                transaction.transaction_type.value,
                transaction.merchant_name,
                transaction.location,
                transaction.foreign_amount,
                transaction.foreign_currency,
                transaction.created_at,
            ))
            self.conn.commit()
            
            # Check if row was inserted (rowcount = 1) or skipped (rowcount = 0)
            if cursor.rowcount > 0:
                if verbose:
                    print(f"    [SAVED] {transaction.id}")
                return True
            else:
                if verbose:
                    print(f"    [SKIP] {transaction.id} - duplicate")
                return False
                
        except Exception as e:
            self.conn.rollback()
            if verbose:
                print(f"    [ERROR] {transaction.id} - {e}")
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
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM transactions WHERE id = %s", (transaction_id,))
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
            query += " AND date >= %s"
            params.append(start_date)
        
        if end_date:
            query += " AND date <= %s"
            params.append(end_date)
        
        if bank_source:
            query += " AND bank_source = %s"
            params.append(bank_source)
        
        if account_id:
            query += " AND account_id = %s"
            params.append(account_id)
        
        if category:
            query += " AND (category = %s OR original_category = %s)"
            params.extend([category, category])
        
        if transaction_type:
            query += " AND transaction_type = %s"
            params.append(transaction_type.value)
        
        if min_amount is not None:
            query += " AND amount >= %s"
            params.append(min_amount)
        
        if max_amount is not None:
            query += " AND amount <= %s"
            params.append(max_amount)
        
        query += " ORDER BY date DESC, id"
        
        if limit:
            query += " LIMIT %s OFFSET %s"
            params.extend([limit, offset])
        
        cursor = self.conn.cursor(cursor_factory=RealDictCursor)
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
            query += " AND date >= %s"
            params.append(start_date)
        
        if end_date:
            query += " AND date <= %s"
            params.append(end_date)
        
        if bank_source:
            query += " AND bank_source = %s"
            params.append(bank_source)
        
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()[0]
    
    def delete_transaction(self, transaction_id: str) -> bool:
        """Delete a transaction by ID."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM transactions WHERE id = %s", (transaction_id,))
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
            "UPDATE transactions SET category = %s WHERE id = %s",
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
    
    def _row_to_transaction(self, row: dict) -> Transaction:
        """Convert a database row to a Transaction object."""
        return Transaction(
            id=row['id'],
            date=row['date'],
            amount=Decimal(str(row['amount'])),
            description=row['description'],
            account_id=row['account_id'],
            account_type=AccountType(row['account_type']),
            bank_source=row['bank_source'],
            source_file=row['source_file'],
            balance=Decimal(str(row['balance'])) if row['balance'] else None,
            original_category=row['original_category'],
            category=row['category'],
            transaction_type=TransactionType(row['transaction_type']),
            merchant_name=row['merchant_name'],
            location=row['location'],
            foreign_amount=Decimal(str(row['foreign_amount'])) if row['foreign_amount'] else None,
            foreign_currency=row['foreign_currency'],
            created_at=row['created_at'],
            raw_transaction=None,  # Raw data not stored in DB
        )
