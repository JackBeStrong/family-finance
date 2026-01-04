"""
SQLAlchemy models for family-finance database.

This module defines the database schema using SQLAlchemy ORM.
"""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Column, String, Date, Numeric, DateTime, Index,
    create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

Base = declarative_base()


class TransactionModel(Base):
    """SQLAlchemy model for transactions table."""
    
    __tablename__ = 'transactions'
    
    # Primary key
    id = Column(String, primary_key=True)
    
    # Core transaction fields
    date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(15, 2), nullable=False)
    description = Column(String, nullable=False)
    
    # Account information
    account_id = Column(String, nullable=False, index=True)
    account_type = Column(String, nullable=False)
    bank_source = Column(String, nullable=False, index=True)
    
    # Source tracking
    source_file = Column(String, nullable=False)
    
    # Optional fields
    balance = Column(Numeric(15, 2))
    original_category = Column(String, index=True)
    category = Column(String, index=True)
    transaction_type = Column(String, nullable=False)
    merchant_name = Column(String)
    location = Column(String)
    foreign_amount = Column(Numeric(15, 2))
    foreign_currency = Column(String)
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_date_bank', 'date', 'bank_source'),
        Index('idx_date_account', 'date', 'account_id'),
    )


def get_engine(url: str = None):
    """
    Create SQLAlchemy engine with connection pooling.
    
    Args:
        url: Database URL (postgresql://user:pass@host:port/dbname)
             If None, constructs from environment variables
    
    Returns:
        SQLAlchemy engine with connection pooling configured
    """
    if url is None:
        # Construct URL from environment variables
        user = os.environ.get('DB_USER')
        password = os.environ.get('DB_PASSWORD')
        host = os.environ.get('DB_HOST', 'localhost')
        port = os.environ.get('DB_PORT', '5432')
        dbname = os.environ.get('DB_NAME', 'family_finance')
        
        if not user or not password:
            raise ValueError("DB_USER and DB_PASSWORD environment variables are required")
        
        url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    
    # Create engine with connection pooling
    # pool_pre_ping: test connections before using them (prevents stale connections)
    # pool_recycle: recycle connections after 1 hour (prevents "server closed connection" errors)
    # pool_size: number of connections to maintain
    # max_overflow: number of connections to create beyond pool_size when needed
    engine = create_engine(
        url,
        pool_pre_ping=True,      # Test connection before use
        pool_recycle=3600,       # Recycle connections after 1 hour
        pool_size=5,             # Maintain 5 connections
        max_overflow=10,         # Allow up to 15 total connections
        echo=False,              # Set to True for SQL debugging
    )
    
    return engine


def get_session_factory(engine):
    """
    Create a session factory for creating database sessions.
    
    Args:
        engine: SQLAlchemy engine
    
    Returns:
        sessionmaker instance
    """
    return sessionmaker(bind=engine)
