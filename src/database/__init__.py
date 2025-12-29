"""
Database module providing abstracted data storage for transactions.

This module provides:
- TransactionRepository: Abstract interface for transaction storage
- SQLiteRepository: SQLite implementation (default)
- PostgresRepository: PostgreSQL implementation (for shared access)

The repository pattern allows swapping database backends (SQLite, PostgreSQL, etc.)
without changing the rest of the application.

Usage:
    from src.database import get_repository
    
    # SQLite (default)
    repo = get_repository()
    
    # PostgreSQL
    repo = get_repository(db_type="postgres")
    
    saved, skipped = repo.save_transactions(transactions)
    
    # Query transactions
    transactions = repo.get_transactions(start_date=date(2025, 11, 1))
"""

import os
from .repository import TransactionRepository
from .sqlite_repository import SQLiteRepository

# Conditionally import PostgresRepository (requires psycopg2)
try:
    from .postgres_repository import PostgresRepository
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    PostgresRepository = None


def get_repository(db_type: str = None, **kwargs) -> TransactionRepository:
    """
    Get a new repository instance.
    
    Args:
        db_type: Type of database ("sqlite" or "postgres")
                 Default: Uses DB_TYPE env var, or "sqlite" if not set
        **kwargs: Database-specific configuration
            SQLite:
                - db_path: Path to SQLite database file (default: "data/transactions.db")
            PostgreSQL:
                - host: Database host (default: DB_HOST env var)
                - port: Database port (default: DB_PORT env var or 5432)
                - database: Database name (default: DB_NAME env var or "family_finance")
                - user: Database user (default: DB_USER env var)
                - password: Database password (default: DB_PASSWORD env var)
        
    Returns:
        TransactionRepository instance
    """
    # Default to environment variable or sqlite
    if db_type is None:
        db_type = os.environ.get('DB_TYPE', 'sqlite')
    
    if db_type == "sqlite":
        db_path = kwargs.get('db_path', os.environ.get('DB_PATH', 'data/transactions.db'))
        return SQLiteRepository(db_path)
    elif db_type == "postgres":
        if not POSTGRES_AVAILABLE:
            raise ImportError("psycopg2 is required for PostgreSQL support. Install with: pip install psycopg2-binary")
        return PostgresRepository(
            host=kwargs.get('host'),
            port=kwargs.get('port'),
            database=kwargs.get('database'),
            user=kwargs.get('user'),
            password=kwargs.get('password'),
        )
    else:
        raise ValueError(f"Unsupported database type: {db_type}. Use 'sqlite' or 'postgres'.")


__all__ = [
    'TransactionRepository',
    'SQLiteRepository',
    'PostgresRepository',
    'get_repository',
    'POSTGRES_AVAILABLE',
]
