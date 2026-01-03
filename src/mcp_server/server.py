#!/usr/bin/env python3
"""
Family Finance MCP Server

A Model Context Protocol (MCP) server that exposes PostgreSQL transaction data
to AI agents using FastMCP.

Usage:
    # Run with streamable HTTP (default, recommended)
    python -m src.mcp_server.server
    
    # Or use the mcp CLI
    uv run mcp run src/mcp_server/server.py
"""

import logging
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from mcp.server.fastmcp import FastMCP

# Database imports - reuse existing repository
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.database.postgres_repository import PostgresRepository
from src.mcp_server.context_store import FinancialContextStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger("mcp").setLevel(logging.WARNING)


# Global instances
_db: Optional[PostgresRepository] = None
_context_store: Optional[FinancialContextStore] = None


def get_db() -> PostgresRepository:
    """Get or create database connection."""
    global _db
    if _db is None:
        logger.info("Creating new database connection...")
        _db = PostgresRepository()
        logger.info("Database connection established")
    return _db


def get_context_store() -> FinancialContextStore:
    """Get or create context store."""
    global _context_store
    if _context_store is None:
        _context_store = FinancialContextStore()
    return _context_store


# Create the FastMCP server
# Configure host to 0.0.0.0 for external access in Docker
mcp = FastMCP("family-finance-mcp", stateless_http=True, host="0.0.0.0", port=8000)


# ==========================================
# CONTEXT STORE TOOLS
# ==========================================

@mcp.tool()
def get_financial_context(section: str = None) -> dict:
    """Get the full financial context including people, accounts, properties, entities, category rules.
    
    Args:
        section: Optional section to get (people, accounts, properties, entities, category_rules, categories, reporting)
    """
    return get_context_store().get_full_context(section)


@mcp.tool()
def get_account_context(account_id: str) -> dict:
    """Get detailed context for a specific bank account.
    
    Args:
        account_id: The account ID to look up (e.g., '037194383538', '7802')
    """
    if not account_id:
        return {"error": "account_id is required"}
    return get_context_store().get_account_context(account_id)


@mcp.tool()
def get_property_context(property_id: str) -> dict:
    """Get detailed context for a specific property.
    
    Args:
        property_id: The property ID to look up (e.g., 'property_1', 'property_2')
    """
    if not property_id:
        return {"error": "property_id is required"}
    return get_context_store().get_property_context(property_id)


# ==========================================
# DATABASE TOOLS
# ==========================================

@mcp.tool()
def query_transactions(
    start_date: str = None,
    end_date: str = None,
    bank_source: str = None,
    account_id: str = None,
    min_amount: float = None,
    max_amount: float = None,
    category: str = None,
    limit: int = 100
) -> dict:
    """Query transactions with optional filters.
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        bank_source: Filter by bank (westpac, anz, cba, bankwest, macquarie)
        account_id: Filter by account ID
        min_amount: Minimum amount (use negative for expenses)
        max_amount: Maximum amount
        category: Filter by category
        limit: Maximum results (default 100)
    """
    db = get_db()
    
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None
    
    transactions = db.get_transactions(
        start_date=start,
        end_date=end,
        bank_source=bank_source,
        account_id=account_id,
        category=category,
        min_amount=min_amount,
        max_amount=max_amount,
        limit=limit
    )
    
    return {
        "count": len(transactions),
        "transactions": [
            {
                "date": t.date.isoformat(),
                "amount": float(t.amount),
                "description": t.description,
                "bank_source": t.bank_source,
                "account_id": t.account_id,
                "category": t.category or t.original_category,
                "transaction_type": t.transaction_type.value
            }
            for t in transactions
        ]
    }


@mcp.tool()
def get_monthly_summary(year: int, month: int) -> dict:
    """Get total income, expenses, and net for a specific month.
    
    Args:
        year: Year (e.g., 2025)
        month: Month (1-12)
    """
    db = get_db()
    
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)
    
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as total_income,
            COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as total_expenses,
            COALESCE(SUM(amount), 0) as net,
            COUNT(*) as transaction_count
        FROM transactions
        WHERE date >= %s AND date < %s
    """, (start_date, end_date))
    
    row = cursor.fetchone()
    return {
        "year": year,
        "month": month,
        "total_income": float(row[0]),
        "total_expenses": float(row[1]),
        "net": float(row[2]),
        "transaction_count": row[3]
    }


@mcp.tool()
def get_spending_by_category(year: int, month: int, top_n: int = None) -> dict:
    """Get spending breakdown by category for a specific month.
    
    Args:
        year: Year (e.g., 2025)
        month: Month (1-12)
        top_n: Limit to top N categories (default: all)
    """
    db = get_db()
    
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)
    
    query = """
        SELECT 
            COALESCE(category, original_category, 'Uncategorized') as category,
            SUM(ABS(amount)) as total,
            COUNT(*) as count
        FROM transactions
        WHERE date >= %s AND date < %s AND amount < 0
        GROUP BY COALESCE(category, original_category, 'Uncategorized')
        ORDER BY total DESC
    """
    
    if top_n:
        query += f" LIMIT {int(top_n)}"
    
    cursor = db.conn.cursor()
    cursor.execute(query, (start_date, end_date))
    
    rows = cursor.fetchall()
    total_spending = float(sum(row[1] for row in rows))
    
    return {
        "year": year,
        "month": month,
        "total_spending": total_spending,
        "categories": [
            {
                "category": row[0],
                "total": float(row[1]),
                "count": row[2],
                "percentage": round(float(row[1]) / total_spending * 100, 1) if total_spending > 0 else 0
            }
            for row in rows
        ]
    }


@mcp.tool()
def get_transactions_by_bank(year: int, month: int) -> dict:
    """Get income/expense totals grouped by bank and account.
    
    Args:
        year: Year (e.g., 2025)
        month: Month (1-12)
    """
    db = get_db()
    
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)
    
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT 
            bank_source,
            account_id,
            account_type,
            COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as income,
            COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as expenses,
            COALESCE(SUM(amount), 0) as net,
            COUNT(*) as count
        FROM transactions
        WHERE date >= %s AND date < %s
        GROUP BY bank_source, account_id, account_type
        ORDER BY bank_source, account_id
    """, (start_date, end_date))
    
    rows = cursor.fetchall()
    return {
        "year": year,
        "month": month,
        "accounts": [
            {
                "bank_source": row[0],
                "account_id": row[1],
                "account_type": row[2],
                "income": float(row[3]),
                "expenses": float(row[4]),
                "net": float(row[5]),
                "transaction_count": row[6]
            }
            for row in rows
        ]
    }


@mcp.tool()
def get_top_merchants(year: int, month: int, top_n: int = 10, exclude_internal_transfers: bool = True) -> dict:
    """Get top merchants/payees by total spending for a month.
    
    Args:
        year: Year (e.g., 2025)
        month: Month (1-12)
        top_n: Number of top merchants (default: 10)
        exclude_internal_transfers: Exclude internal transfers (default: true)
    """
    db = get_db()
    
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)
    
    cursor = db.conn.cursor()
    
    if exclude_internal_transfers:
        cursor.execute("""
            WITH matched_transfer_ids AS (
                SELECT DISTINCT t1.id
                FROM transactions t1
                INNER JOIN transactions t2 ON
                    ABS(t1.amount) = ABS(t2.amount)
                    AND t1.amount < 0
                    AND t2.amount > 0
                    AND ABS(t1.date - t2.date) <= 1
                    AND t1.account_id != t2.account_id
                WHERE t1.date >= %s AND t1.date < %s
            ),
            pattern_transfer_ids AS (
                SELECT id FROM transactions
                WHERE date >= %s AND date < %s
                    AND amount < 0
                    AND (
                        COALESCE(original_category, '') IN ('TFR', 'PAYMENT')
                        OR COALESCE(original_category, '') LIKE 'Financial > Transfer%%'
                        OR LOWER(description) LIKE 'transfer to%%'
                        OR LOWER(description) LIKE 'to westpac%%'
                        OR LOWER(description) LIKE 'to anz%%'
                        OR LOWER(description) LIKE 'to cba%%'
                        OR LOWER(description) LIKE 'to macquarie%%'
                        OR LOWER(description) LIKE 'to bankwest%%'
                        OR LOWER(description) LIKE 'to bw%%'
                        OR LOWER(description) LIKE '%%payment by authority to westpac bankcorp%%'
                        OR LOWER(description) LIKE '%%withdrawal online%%tfr%%'
                        OR LOWER(description) LIKE '%%withdrawal mobile%%pymt%%'
                        OR LOWER(description) LIKE '%%anz internet banking%%payment%%to%%'
                        OR LOWER(description) LIKE '%%pymt interactiv%%'
                        OR LOWER(description) LIKE '%%interactive brokers%%'
                        OR (LOWER(original_category) = 'cash' AND ABS(amount) > 5000)
                    )
            ),
            all_transfer_ids AS (
                SELECT id FROM matched_transfer_ids
                UNION
                SELECT id FROM pattern_transfer_ids
            )
            SELECT
                description,
                SUM(ABS(amount)) as total,
                COUNT(*) as count
            FROM transactions
            WHERE date >= %s AND date < %s
                AND amount < 0
                AND id NOT IN (SELECT id FROM all_transfer_ids)
                AND account_type != 'loan'
                AND COALESCE(original_category, '') != 'INT'
                AND description != 'INTEREST'
            GROUP BY description
            ORDER BY total DESC
            LIMIT %s
        """, (start_date, end_date, start_date, end_date, start_date, end_date, top_n))
    else:
        cursor.execute("""
            SELECT
                description,
                SUM(ABS(amount)) as total,
                COUNT(*) as count
            FROM transactions
            WHERE date >= %s AND date < %s AND amount < 0
            GROUP BY description
            ORDER BY total DESC
            LIMIT %s
        """, (start_date, end_date, top_n))
    
    rows = cursor.fetchall()
    return {
        "year": year,
        "month": month,
        "exclude_internal_transfers": exclude_internal_transfers,
        "top_merchants": [
            {
                "description": row[0],
                "total": float(row[1]),
                "count": row[2]
            }
            for row in rows
        ]
    }


@mcp.tool()
def get_month_comparison(year: int, month: int) -> dict:
    """Compare a month's totals with the previous month.
    
    Args:
        year: Year (e.g., 2025)
        month: Month (1-12)
    """
    current = get_monthly_summary(year, month)
    
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    
    previous = get_monthly_summary(prev_year, prev_month)
    
    income_change = current["total_income"] - previous["total_income"]
    expense_change = current["total_expenses"] - previous["total_expenses"]
    
    income_pct = (income_change / previous["total_income"] * 100) if previous["total_income"] > 0 else 0
    expense_pct = (expense_change / previous["total_expenses"] * 100) if previous["total_expenses"] > 0 else 0
    
    return {
        "current_month": current,
        "previous_month": previous,
        "changes": {
            "income_change": round(income_change, 2),
            "income_change_percent": round(income_pct, 1),
            "expense_change": round(expense_change, 2),
            "expense_change_percent": round(expense_pct, 1),
            "net_change": round(current["net"] - previous["net"], 2)
        }
    }


@mcp.tool()
def execute_sql(query: str) -> dict:
    """Execute a read-only SQL query. Only SELECT statements allowed.
    
    Args:
        query: SQL SELECT query
    """
    db = get_db()
    query = query.strip()
    
    if not query.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")
    
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "GRANT", "REVOKE"]
    query_upper = query.upper()
    for keyword in dangerous:
        if keyword in query_upper:
            raise ValueError(f"Query contains forbidden keyword: {keyword}")
    
    cursor = db.conn.cursor()
    cursor.execute(query)
    
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    
    return {
        "columns": columns,
        "row_count": len(rows),
        "rows": [
            {col: (float(val) if isinstance(val, Decimal) else val.isoformat() if isinstance(val, (date, datetime)) else val)
             for col, val in zip(columns, row)}
            for row in rows
        ]
    }


@mcp.tool()
def get_available_months() -> dict:
    """Get list of months that have transaction data."""
    db = get_db()
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT 
            EXTRACT(YEAR FROM date)::int as year,
            EXTRACT(MONTH FROM date)::int as month,
            COUNT(*) as count
        FROM transactions
        GROUP BY EXTRACT(YEAR FROM date), EXTRACT(MONTH FROM date)
        ORDER BY year DESC, month DESC
    """)
    
    rows = cursor.fetchall()
    return {
        "months": [
            {"year": row[0], "month": row[1], "transaction_count": row[2]}
            for row in rows
        ]
    }


@mcp.tool()
def get_database_stats() -> dict:
    """Get overall database statistics (total transactions, date range, banks)."""
    db = get_db()
    cursor = db.conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM transactions")
    total_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT MIN(date), MAX(date) FROM transactions")
    date_range = cursor.fetchone()
    
    cursor.execute("""
        SELECT bank_source, COUNT(*)
        FROM transactions
        GROUP BY bank_source
        ORDER BY COUNT(*) DESC
    """)
    banks = cursor.fetchall()
    
    cursor.execute("""
        SELECT account_type, COUNT(*)
        FROM transactions
        GROUP BY account_type
    """)
    account_types = cursor.fetchall()
    
    return {
        "total_transactions": total_count,
        "date_range": {
            "earliest": date_range[0].isoformat() if date_range[0] else None,
            "latest": date_range[1].isoformat() if date_range[1] else None
        },
        "banks": [{"bank": row[0], "count": row[1]} for row in banks],
        "account_types": [{"type": row[0], "count": row[1]} for row in account_types]
    }


@mcp.tool()
def get_table_schema(table_name: str = "transactions") -> dict:
    """Get the schema (columns, types, constraints) for a database table.
    
    Use this to understand the table structure before writing SQL queries with execute_sql.
    
    Args:
        table_name: Name of the table to describe (default: 'transactions')
    """
    db = get_db()
    cursor = db.conn.cursor()
    
    # Validate table name to prevent SQL injection
    allowed_tables = ["transactions"]
    if table_name not in allowed_tables:
        return {"error": f"Table '{table_name}' not found. Available tables: {allowed_tables}"}
    
    # Get column information from PostgreSQL information_schema
    cursor.execute("""
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length,
            numeric_precision,
            numeric_scale
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
    """, (table_name,))
    
    columns = cursor.fetchall()
    
    # Get primary key information
    cursor.execute("""
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = %s::regclass AND i.indisprimary
    """, (table_name,))
    
    primary_keys = [row[0] for row in cursor.fetchall()]
    
    # Get index information
    cursor.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = %s
    """, (table_name,))
    
    indexes = cursor.fetchall()
    
    # Get sample distinct values for key columns (useful for filtering)
    sample_values = {}
    for col in ["bank_source", "account_type", "transaction_type"]:
        cursor.execute(f"""
            SELECT DISTINCT {col} FROM {table_name}
            WHERE {col} IS NOT NULL
            ORDER BY {col}
            LIMIT 20
        """)
        sample_values[col] = [row[0] for row in cursor.fetchall()]
    
    return {
        "table_name": table_name,
        "columns": [
            {
                "name": col[0],
                "type": col[1],
                "nullable": col[2] == "YES",
                "default": col[3],
                "max_length": col[4],
                "precision": col[5],
                "scale": col[6],
                "is_primary_key": col[0] in primary_keys
            }
            for col in columns
        ],
        "primary_keys": primary_keys,
        "indexes": [
            {"name": idx[0], "definition": idx[1]}
            for idx in indexes
        ],
        "sample_values": sample_values,
        "notes": {
            "amount": "Negative values are expenses/debits, positive values are income/credits",
            "date": "Format: YYYY-MM-DD",
            "category": "User-assigned category (may be NULL)",
            "original_category": "Bank-provided category (may be NULL)",
            "transaction_type": "DEBIT, CREDIT, TRANSFER, etc."
        }
    }


# Run with streamable HTTP transport
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
