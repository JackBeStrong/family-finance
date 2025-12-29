"""
Database module providing abstracted data storage for transactions.

This module provides:
- TransactionRepository: Abstract interface for transaction storage
- SQLiteRepository: SQLite implementation (default)

The repository pattern allows swapping database backends (SQLite, PostgreSQL, etc.)
without changing the rest of the application.

Usage:
    from src.database import get_repository
    
    repo = get_repository()  # Gets default SQLite repository
    saved, skipped = repo.save_transactions(transactions)
    
    # Query transactions
    transactions = repo.get_transactions(start_date=date(2025, 11, 1))
"""

from .repository import TransactionRepository
from .sqlite_repository import SQLiteRepository


def get_repository(db_type: str = "sqlite", **kwargs) -> TransactionRepository:
    """
    Get a new repository instance.
    
    Args:
        db_type: Type of database ("sqlite" or future "postgres")
        **kwargs: Database-specific configuration
            - db_path: Path to SQLite database file (default: "data/transactions.db")
        
    Returns:
        TransactionRepository instance
    """
    if db_type == "sqlite":
        db_path = kwargs.get('db_path', 'data/transactions.db')
        return SQLiteRepository(db_path)
    else:
        raise ValueError(f"Unsupported database type: {db_type}")


__all__ = [
    'TransactionRepository',
    'SQLiteRepository',
    'get_repository',
]
