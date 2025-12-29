"""
Abstract repository interface for transaction storage.

This module defines the contract that all database implementations must follow,
enabling easy swapping between SQLite, PostgreSQL, or other backends.

Transaction uniqueness is handled by the transaction ID, which is generated
by the parser to include an occurrence number for identical transactions
within the same file.
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import List, Optional
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.parsers.base import Transaction, TransactionType


class TransactionRepository(ABC):
    """
    Abstract interface for transaction storage.
    
    All database implementations must implement these methods.
    This allows the application to work with any database backend.
    
    Transaction uniqueness is handled by the ID field - the database
    simply rejects duplicates based on the primary key.
    """
    
    @abstractmethod
    def initialize(self) -> None:
        """
        Initialize the database schema.
        Creates tables if they don't exist.
        """
        pass
    
    # ==================== Transaction CRUD ====================
    
    @abstractmethod
    def save_transaction(self, transaction: Transaction) -> bool:
        """
        Save a single transaction to the database.
        
        Args:
            transaction: The transaction to save
            
        Returns:
            True if saved successfully, False if duplicate (ID already exists)
        """
        pass
    
    @abstractmethod
    def save_transactions(self, transactions: List[Transaction]) -> tuple[int, int]:
        """
        Save multiple transactions to the database.
        
        Args:
            transactions: List of transactions to save
            
        Returns:
            Tuple of (saved_count, skipped_count)
        """
        pass
    
    @abstractmethod
    def get_transaction_by_id(self, transaction_id: str) -> Optional[Transaction]:
        """
        Get a transaction by its ID.
        
        Args:
            transaction_id: The unique transaction ID
            
        Returns:
            Transaction if found, None otherwise
        """
        pass
    
    @abstractmethod
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
        """
        Query transactions with optional filters.
        
        Args:
            start_date: Filter transactions on or after this date
            end_date: Filter transactions on or before this date
            bank_source: Filter by bank source
            account_id: Filter by account ID
            category: Filter by category
            transaction_type: Filter by transaction type (debit/credit)
            min_amount: Filter by minimum amount
            max_amount: Filter by maximum amount
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of matching transactions, ordered by date descending
        """
        pass
    
    @abstractmethod
    def count_transactions(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        bank_source: Optional[str] = None,
    ) -> int:
        """
        Count transactions matching the filters.
        
        Args:
            start_date: Filter transactions on or after this date
            end_date: Filter transactions on or before this date
            bank_source: Filter by bank source
            
        Returns:
            Count of matching transactions
        """
        pass
    
    @abstractmethod
    def delete_transaction(self, transaction_id: str) -> bool:
        """
        Delete a transaction by ID.
        
        Args:
            transaction_id: The transaction ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        pass
    
    @abstractmethod
    def update_transaction_category(
        self,
        transaction_id: str,
        category: str
    ) -> bool:
        """
        Update the category of a transaction.
        
        Args:
            transaction_id: The transaction ID
            category: The new category
            
        Returns:
            True if updated, False if not found
        """
        pass
    
    @abstractmethod
    def get_distinct_values(self, field: str) -> List[str]:
        """
        Get distinct values for a field (e.g., categories, banks).
        
        Args:
            field: Field name ('category', 'bank_source', 'account_id')
            
        Returns:
            List of distinct values
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close the database connection."""
        pass
