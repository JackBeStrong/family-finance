"""
PostgreSQL implementation of the TransactionRepository using SQLAlchemy.

This module provides a PostgreSQL database for storing transactions,
enabling independent access for reporting and other services.

Uses SQLAlchemy for:
- Automatic connection pooling
- Proper transaction management with rollback on errors
- Session lifecycle management
- Protection against SQL injection
"""

import logging
import os
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple
import sys
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.parsers.base import Transaction, TransactionType, AccountType
from src.database.repository import TransactionRepository

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker, Session
    from sqlalchemy.exc import IntegrityError
    from src.database.models import TransactionModel, get_engine, get_session_factory
    SQLALCHEMY_AVAILABLE = True
except ImportError:
    SQLALCHEMY_AVAILABLE = False


class PostgresRepository(TransactionRepository):
    """
    PostgreSQL implementation of TransactionRepository using SQLAlchemy.
    
    Stores transactions in a PostgreSQL database for shared access
    by multiple services (watcher, reporting, etc.).
    
    Features:
    - Connection pooling (prevents stale connections)
    - Automatic transaction rollback on errors
    - Proper session lifecycle management
    - Protection against SQL injection
    """
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        database: str = None,
        user: str = None,
        password: str = None,
        url: str = None,
    ):
        """
        Initialize the PostgreSQL repository with SQLAlchemy.
        
        Args:
            host: PostgreSQL host (default: DB_HOST env var or localhost)
            port: PostgreSQL port (default: DB_PORT env var or 5432)
            database: Database name (default: DB_NAME env var or family_finance)
            user: Database user (default: DB_USER env var)
            password: Database password (default: DB_PASSWORD env var)
            url: Full database URL (overrides other params if provided)
        """
        if not SQLALCHEMY_AVAILABLE:
            raise ImportError("SQLAlchemy is required for PostgreSQL support. Install with: pip install sqlalchemy")
        
        # Build database URL
        if url is None:
            _host = host or os.environ.get('DB_HOST', 'localhost')
            _port = port or int(os.environ.get('DB_PORT', '5432'))
            _database = database or os.environ.get('DB_NAME', 'family_finance')
            _user = user or os.environ.get('DB_USER')
            _password = password or os.environ.get('DB_PASSWORD')
            
            if not _user or not _password:
                raise ValueError("Database user and password are required. Set DB_USER and DB_PASSWORD environment variables.")
            
            url = f"postgresql://{_user}:{_password}@{_host}:{_port}/{_database}"
        
        # Create engine and session factory
        self.engine = get_engine(url)
        self.SessionFactory = get_session_factory(self.engine)
    
    @contextmanager
    def get_session(self):
        """
        Context manager for database sessions.
        
        Automatically commits on success, rolls back on error, and closes the session.
        
        Usage:
            with repo.get_session() as session:
                session.add(transaction)
                # auto-commit on exit, auto-rollback on exception
        """
        session = self.SessionFactory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def initialize(self) -> None:
        """No-op: Tables are created via SQL scripts (sql/02_create_tables.sql)."""
        pass
    
    # ==================== Transaction CRUD ====================
    
    def save_transaction(self, transaction: Transaction, verbose: bool = False) -> bool:
        """
        Save a single transaction. Returns False if duplicate.
        
        Uses SQLAlchemy session with automatic rollback on error.
        """
        with self.get_session() as session:
            try:
                # Convert Transaction to TransactionModel
                txn_model = TransactionModel(
                    id=transaction.id,
                    date=transaction.date,
                    amount=transaction.amount,
                    description=transaction.description,
                    account_id=transaction.account_id,
                    account_type=transaction.account_type.value,
                    bank_source=transaction.bank_source,
                    source_file=transaction.source_file,
                    balance=transaction.balance,
                    original_category=transaction.original_category,
                    category=transaction.category,
                    transaction_type=transaction.transaction_type.value,
                    merchant_name=transaction.merchant_name,
                    location=transaction.location,
                    foreign_amount=transaction.foreign_amount,
                    foreign_currency=transaction.foreign_currency,
                    created_at=transaction.created_at,
                )
                
                session.add(txn_model)
                session.flush()  # Flush to catch IntegrityError
                
                if verbose:
                    print(f"    [SAVED] {transaction.id}")
                return True
                
            except IntegrityError:
                # Duplicate transaction (primary key conflict)
                if verbose:
                    print(f"    [SKIP] {transaction.id} - duplicate")
                return False
                
            except Exception as e:
                # Other errors - log and return False
                logger.error(f"Failed to save transaction {transaction.id}: {e}")
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
        with self.get_session() as session:
            txn_model = session.query(TransactionModel).filter_by(id=transaction_id).first()
            
            if txn_model is None:
                return None
            
            return self._model_to_transaction(txn_model)
    
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
        """Query transactions with optional filters using SQLAlchemy."""
        with self.get_session() as session:
            query = session.query(TransactionModel)
            
            if start_date:
                query = query.filter(TransactionModel.date >= start_date)
            
            if end_date:
                query = query.filter(TransactionModel.date <= end_date)
            
            if bank_source:
                query = query.filter(TransactionModel.bank_source == bank_source)
            
            if account_id:
                query = query.filter(TransactionModel.account_id == account_id)
            
            if category:
                query = query.filter(
                    (TransactionModel.category == category) |
                    (TransactionModel.original_category == category)
                )
            
            if transaction_type:
                query = query.filter(TransactionModel.transaction_type == transaction_type.value)
            
            if min_amount is not None:
                query = query.filter(TransactionModel.amount >= min_amount)
            
            if max_amount is not None:
                query = query.filter(TransactionModel.amount <= max_amount)
            
            query = query.order_by(TransactionModel.date.desc(), TransactionModel.id)
            
            if limit:
                query = query.limit(limit).offset(offset)
            
            results = query.all()
            return [self._model_to_transaction(txn_model) for txn_model in results]
    
    def count_transactions(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        bank_source: Optional[str] = None,
    ) -> int:
        """Count transactions matching the filters."""
        with self.get_session() as session:
            query = session.query(TransactionModel)
            
            if start_date:
                query = query.filter(TransactionModel.date >= start_date)
            
            if end_date:
                query = query.filter(TransactionModel.date <= end_date)
            
            if bank_source:
                query = query.filter(TransactionModel.bank_source == bank_source)
            
            return query.count()
    
    def delete_transaction(self, transaction_id: str) -> bool:
        """Delete a transaction by ID."""
        with self.get_session() as session:
            txn_model = session.query(TransactionModel).filter_by(id=transaction_id).first()
            if txn_model:
                session.delete(txn_model)
                return True
            return False
    
    def update_transaction_category(
        self,
        transaction_id: str,
        category: str
    ) -> bool:
        """Update the category of a transaction."""
        with self.get_session() as session:
            txn_model = session.query(TransactionModel).filter_by(id=transaction_id).first()
            if txn_model:
                txn_model.category = category
                return True
            return False
    
    def get_distinct_values(self, field: str) -> List[str]:
        """Get distinct values for a field."""
        allowed_fields = {'category', 'original_category', 'bank_source', 'account_id'}
        if field not in allowed_fields:
            raise ValueError(f"Field must be one of: {allowed_fields}")
        
        with self.get_session() as session:
            column = getattr(TransactionModel, field)
            results = session.query(column).filter(column.isnot(None)).distinct().order_by(column).all()
            return [row[0] for row in results]
    
    def close(self) -> None:
        """Close the database engine and connection pool."""
        if self.engine:
            self.engine.dispose()
    
    def _model_to_transaction(self, model: TransactionModel) -> Transaction:
        """Convert a TransactionModel (SQLAlchemy) to a Transaction (domain model)."""
        return Transaction(
            id=model.id,
            date=model.date,
            amount=Decimal(str(model.amount)),
            description=model.description,
            account_id=model.account_id,
            account_type=AccountType(model.account_type),
            bank_source=model.bank_source,
            source_file=model.source_file,
            balance=Decimal(str(model.balance)) if model.balance else None,
            original_category=model.original_category,
            category=model.category,
            transaction_type=TransactionType(model.transaction_type),
            merchant_name=model.merchant_name,
            location=model.location,
            foreign_amount=Decimal(str(model.foreign_amount)) if model.foreign_amount else None,
            foreign_currency=model.foreign_currency,
            created_at=model.created_at,
            raw_transaction=None,  # Raw data not stored in DB
        )
