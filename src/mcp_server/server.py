#!/usr/bin/env python3
"""
Family Finance MCP Server

A Model Context Protocol (MCP) server that exposes PostgreSQL transaction data
to AI agents. Supports both SSE (HTTP) transport for remote access and stdio
transport for local development.

Usage:
    # SSE mode (for remote/production)
    python -m src.mcp_server.server --transport sse --port 8080
    
    # Stdio mode (for local development)
    python -m src.mcp_server.server --transport stdio
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import traceback
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

# MCP SDK imports
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

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

# Set MCP SDK logging to WARNING to reduce noise
logging.getLogger("mcp").setLevel(logging.WARNING)


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)


def json_dumps(obj: Any) -> str:
    """JSON serialize with Decimal support."""
    return json.dumps(obj, cls=DecimalEncoder, indent=2)


class FamilyFinanceMCP:
    """
    MCP Server for Family Finance database.
    
    Exposes tools for querying transaction data:
    - query_transactions: Flexible filtered queries
    - get_monthly_summary: Income/expenses totals
    - get_spending_by_category: Category breakdown
    - get_transactions_by_bank: Per-bank/account totals
    - get_top_merchants: Top spending merchants
    - get_month_comparison: Month-over-month comparison
    - execute_sql: Raw SELECT queries (read-only)
    
    Context Store tools:
    - get_financial_context: Get full financial context
    - get_account_context: Get context for a specific account
    - get_property_context: Get context for a specific property
    """
    
    def __init__(self):
        self.server = Server("family-finance-mcp")
        self.db: Optional[PostgresRepository] = None
        self.context_store = FinancialContextStore()
        self._setup_tools()
    
    def _get_db(self) -> PostgresRepository:
        """Get or create database connection."""
        if self.db is None:
            logger.info("Creating new database connection...")
            try:
                self.db = PostgresRepository()
                logger.info("Database connection established successfully")
            except Exception as e:
                error_trace = traceback.format_exc()
                logger.error(f"Failed to connect to database:\n{error_trace}")
                raise
        return self.db
    
    def _setup_tools(self):
        """Register all MCP tools."""
        
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="query_transactions",
                    description="Query transactions with optional filters. Returns transaction details.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "start_date": {
                                "type": "string",
                                "description": "Start date (YYYY-MM-DD)"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date (YYYY-MM-DD)"
                            },
                            "bank_source": {
                                "type": "string",
                                "description": "Filter by bank (westpac, anz, cba, bankwest, macquarie)"
                            },
                            "account_id": {
                                "type": "string",
                                "description": "Filter by account ID"
                            },
                            "min_amount": {
                                "type": "number",
                                "description": "Minimum amount (use negative for expenses)"
                            },
                            "max_amount": {
                                "type": "number",
                                "description": "Maximum amount"
                            },
                            "category": {
                                "type": "string",
                                "description": "Filter by category"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum results (default 100)"
                            }
                        }
                    }
                ),
                Tool(
                    name="get_monthly_summary",
                    description="Get total income, expenses, and net for a specific month.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "year": {
                                "type": "integer",
                                "description": "Year (e.g., 2025)"
                            },
                            "month": {
                                "type": "integer",
                                "description": "Month (1-12)"
                            }
                        },
                        "required": ["year", "month"]
                    }
                ),
                Tool(
                    name="get_spending_by_category",
                    description="Get spending breakdown by category for a specific month.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "year": {
                                "type": "integer",
                                "description": "Year (e.g., 2025)"
                            },
                            "month": {
                                "type": "integer",
                                "description": "Month (1-12)"
                            },
                            "top_n": {
                                "type": "integer",
                                "description": "Limit to top N categories (default: all)"
                            }
                        },
                        "required": ["year", "month"]
                    }
                ),
                Tool(
                    name="get_transactions_by_bank",
                    description="Get income/expense totals grouped by bank and account.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "year": {
                                "type": "integer",
                                "description": "Year (e.g., 2025)"
                            },
                            "month": {
                                "type": "integer",
                                "description": "Month (1-12)"
                            }
                        },
                        "required": ["year", "month"]
                    }
                ),
                Tool(
                    name="get_top_merchants",
                    description="Get top merchants/payees by total spending for a month. By default excludes internal transfers (mortgage payments, transfers between own accounts).",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "year": {
                                "type": "integer",
                                "description": "Year (e.g., 2025)"
                            },
                            "month": {
                                "type": "integer",
                                "description": "Month (1-12)"
                            },
                            "top_n": {
                                "type": "integer",
                                "description": "Number of top merchants (default: 10)"
                            },
                            "exclude_internal_transfers": {
                                "type": "boolean",
                                "description": "Exclude internal transfers like mortgage payments, transfers between own accounts (default: true)"
                            }
                        },
                        "required": ["year", "month"]
                    }
                ),
                Tool(
                    name="get_month_comparison",
                    description="Compare a month's totals with the previous month.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "year": {
                                "type": "integer",
                                "description": "Year (e.g., 2025)"
                            },
                            "month": {
                                "type": "integer",
                                "description": "Month (1-12)"
                            }
                        },
                        "required": ["year", "month"]
                    }
                ),
                Tool(
                    name="execute_sql",
                    description="Execute a read-only SQL query. Only SELECT statements allowed.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "SQL SELECT query"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="get_available_months",
                    description="Get list of months that have transaction data.",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                Tool(
                    name="get_database_stats",
                    description="Get overall database statistics (total transactions, date range, banks).",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                # ==========================================
                # CONTEXT STORE TOOLS
                # ==========================================
                Tool(
                    name="get_financial_context",
                    description="""Get the full financial context including:
- People (household members and their aliases)
- Accounts (all bank accounts with purposes, linked properties)
- Properties (investment properties with addresses)
- Entities (known merchants, employers, etc.)
- Category rules (for transaction categorization)
- Reporting preferences

Use this to understand the user's financial structure before generating reports.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "section": {
                                "type": "string",
                                "description": "Optional: Get only a specific section (people, accounts, properties, entities, category_rules, categories, reporting)"
                            }
                        }
                    }
                ),
                Tool(
                    name="get_account_context",
                    description="""Get detailed context for a specific bank account.

Returns:
- Account type (loan, offset, transaction, credit_card, etc.)
- Purpose (mortgage, daily_spending, salary, etc.)
- Linked property details (for mortgage/offset accounts)
- Linked loan details (for offset accounts)

Use this to understand what an account is used for when analyzing transactions.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "account_id": {
                                "type": "string",
                                "description": "The account ID to look up (e.g., '037194383538', '7802')"
                            }
                        },
                        "required": ["account_id"]
                    }
                ),
                Tool(
                    name="get_property_context",
                    description="""Get detailed context for a specific property.

Returns:
- Property address and type (investment, ppor)
- All linked accounts (mortgage loan, offset accounts)

Use this to understand property-related transactions like mortgage interest.""",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "property_id": {
                                "type": "string",
                                "description": "The property ID to look up (e.g., 'property_1', 'property_2')"
                            }
                        },
                        "required": ["property_id"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            logger.info(f"Tool called: {name} with args: {arguments}")
            try:
                result = await self._execute_tool(name, arguments)
                logger.info(f"Tool {name} completed successfully")
                logger.debug(f"Tool {name} result: {result}")
                return [TextContent(type="text", text=json_dumps(result))]
            except Exception as e:
                error_trace = traceback.format_exc()
                logger.error(f"Tool {name} failed with exception:\n{error_trace}")
                return [TextContent(type="text", text=json_dumps({"error": str(e), "traceback": error_trace}))]
    
    async def _execute_tool(self, name: str, args: dict) -> Any:
        """Execute a tool and return the result."""
        # Context store tools (don't need database)
        if name == "get_financial_context":
            return await self._get_financial_context(args)
        elif name == "get_account_context":
            return await self._get_account_context(args)
        elif name == "get_property_context":
            return await self._get_property_context(args)
        
        # Database tools
        db = self._get_db()
        
        if name == "query_transactions":
            return await self._query_transactions(db, args)
        elif name == "get_monthly_summary":
            return await self._get_monthly_summary(db, args)
        elif name == "get_spending_by_category":
            return await self._get_spending_by_category(db, args)
        elif name == "get_transactions_by_bank":
            return await self._get_transactions_by_bank(db, args)
        elif name == "get_top_merchants":
            return await self._get_top_merchants(db, args)
        elif name == "get_month_comparison":
            return await self._get_month_comparison(db, args)
        elif name == "execute_sql":
            return await self._execute_sql(db, args)
        elif name == "get_available_months":
            return await self._get_available_months(db)
        elif name == "get_database_stats":
            return await self._get_database_stats(db)
        else:
            raise ValueError(f"Unknown tool: {name}")
    
    # ==========================================
    # CONTEXT STORE TOOL IMPLEMENTATIONS
    # ==========================================
    
    async def _get_financial_context(self, args: dict) -> dict:
        """Get the full financial context or a specific section."""
        section = args.get("section")
        return self.context_store.get_full_context(section)
    
    async def _get_account_context(self, args: dict) -> dict:
        """Get context for a specific account."""
        account_id = args.get("account_id")
        if not account_id:
            return {"error": "account_id is required"}
        return self.context_store.get_account_context(account_id)
    
    async def _get_property_context(self, args: dict) -> dict:
        """Get context for a specific property."""
        property_id = args.get("property_id")
        if not property_id:
            return {"error": "property_id is required"}
        return self.context_store.get_property_context(property_id)
    
    # ==========================================
    # DATABASE TOOL IMPLEMENTATIONS
    # ==========================================
    
    async def _query_transactions(self, db: PostgresRepository, args: dict) -> dict:
        """Query transactions with filters."""
        start_date = date.fromisoformat(args["start_date"]) if args.get("start_date") else None
        end_date = date.fromisoformat(args["end_date"]) if args.get("end_date") else None
        
        transactions = db.get_transactions(
            start_date=start_date,
            end_date=end_date,
            bank_source=args.get("bank_source"),
            account_id=args.get("account_id"),
            category=args.get("category"),
            min_amount=args.get("min_amount"),
            max_amount=args.get("max_amount"),
            limit=args.get("limit", 100)
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
    
    async def _get_monthly_summary(self, db: PostgresRepository, args: dict) -> dict:
        """Get monthly income/expense summary."""
        year = args["year"]
        month = args["month"]
        
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
    
    async def _get_spending_by_category(self, db: PostgresRepository, args: dict) -> dict:
        """Get spending breakdown by category."""
        year = args["year"]
        month = args["month"]
        top_n = args.get("top_n")
        
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
    
    async def _get_transactions_by_bank(self, db: PostgresRepository, args: dict) -> dict:
        """Get totals grouped by bank and account."""
        year = args["year"]
        month = args["month"]
        
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
    
    async def _get_top_merchants(self, db: PostgresRepository, args: dict) -> dict:
        """Get top merchants by spending."""
        year = args["year"]
        month = args["month"]
        top_n = args.get("top_n", 10)
        exclude_internal = args.get("exclude_internal_transfers", True)
        
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)
        
        cursor = db.conn.cursor()
        
        if exclude_internal:
            # Internal transfer detection using two methods:
            #
            # METHOD 1: Double-Entry Matching (Primary)
            # Match a debit in account A with a credit of the same amount
            # on the same date (±1 day) in account B.
            #
            # METHOD 2: Pattern-Based Fallback
            # For transfers to external accounts not in our system, use
            # description patterns and bank categories.
            #
            # We also exclude:
            # - Loan accounts (mortgage interest/fees are not merchant spending)
            # - Interest charges (INT category)
            cursor.execute("""
                WITH matched_transfer_ids AS (
                    -- METHOD 1: Double-entry matching
                    -- Find debits that have a matching credit in another account
                    SELECT DISTINCT t1.id
                    FROM transactions t1
                    INNER JOIN transactions t2 ON
                        -- Same absolute amount (debit matches credit)
                        ABS(t1.amount) = ABS(t2.amount)
                        -- Opposite signs (one debit, one credit)
                        AND t1.amount < 0
                        AND t2.amount > 0
                        -- Same date or within 1 day (transfers may post on different days)
                        AND ABS(t1.date - t2.date) <= 1
                        -- Different accounts
                        AND t1.account_id != t2.account_id
                    WHERE t1.date >= %s AND t1.date < %s
                ),
                pattern_transfer_ids AS (
                    -- METHOD 2: Pattern-based fallback
                    -- Catch transfers to external accounts not in our system
                    SELECT id FROM transactions
                    WHERE date >= %s AND date < %s
                        AND amount < 0
                        AND (
                            -- Bank transfer categories
                            COALESCE(original_category, '') IN ('TFR', 'PAYMENT')
                            OR COALESCE(original_category, '') LIKE 'Financial > Transfer%%'
                            -- Description patterns: transfers to banks
                            OR LOWER(description) LIKE 'transfer to%%'
                            OR LOWER(description) LIKE 'to westpac%%'
                            OR LOWER(description) LIKE 'to anz%%'
                            OR LOWER(description) LIKE 'to cba%%'
                            OR LOWER(description) LIKE 'to macquarie%%'
                            OR LOWER(description) LIKE 'to bankwest%%'
                            OR LOWER(description) LIKE 'to bw%%'
                            -- Westpac mortgage auto-debits
                            OR LOWER(description) LIKE '%%payment by authority to westpac bankcorp%%'
                            -- Westpac internal transfers
                            OR LOWER(description) LIKE '%%withdrawal online%%tfr%%'
                            OR LOWER(description) LIKE '%%withdrawal mobile%%pymt%%'
                            -- ANZ internet banking transfers
                            OR LOWER(description) LIKE '%%anz internet banking%%payment%%to%%'
                            -- Investment platform transfers (IBKR)
                            OR LOWER(description) LIKE '%%pymt interactiv%%'
                            OR LOWER(description) LIKE '%%interactive brokers%%'
                            -- Large ATM withdrawals (CASH category, likely not merchant)
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
                    -- Exclude all detected internal transfers
                    AND id NOT IN (SELECT id FROM all_transfer_ids)
                    -- Exclude loan accounts (mortgage interest/fees)
                    AND account_type != 'loan'
                    -- Exclude interest charges
                    AND COALESCE(original_category, '') != 'INT'
                    AND description != 'INTEREST'
                GROUP BY description
                ORDER BY total DESC
                LIMIT %s
            """, (start_date, end_date, start_date, end_date, start_date, end_date, top_n))
        else:
            # Include all transactions
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
            "exclude_internal_transfers": exclude_internal,
            "top_merchants": [
                {
                    "description": row[0],
                    "total": float(row[1]),
                    "count": row[2]
                }
                for row in rows
            ]
        }
    
    async def _get_month_comparison(self, db: PostgresRepository, args: dict) -> dict:
        """Compare month with previous month."""
        year = args["year"]
        month = args["month"]
        
        # Current month
        current = await self._get_monthly_summary(db, {"year": year, "month": month})
        
        # Previous month
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1
        
        previous = await self._get_monthly_summary(db, {"year": prev_year, "month": prev_month})
        
        # Calculate changes
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
    
    async def _execute_sql(self, db: PostgresRepository, args: dict) -> dict:
        """Execute a read-only SQL query."""
        query = args["query"].strip()
        
        # Security: Only allow SELECT statements
        if not query.upper().startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed")
        
        # Block dangerous keywords
        dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "GRANT", "REVOKE"]
        query_upper = query.upper()
        for keyword in dangerous:
            if keyword in query_upper:
                raise ValueError(f"Query contains forbidden keyword: {keyword}")
        
        cursor = db.conn.cursor()
        cursor.execute(query)
        
        # Get column names
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
    
    async def _get_available_months(self, db: PostgresRepository) -> dict:
        """Get list of months with data."""
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
    
    async def _get_database_stats(self, db: PostgresRepository) -> dict:
        """Get overall database statistics."""
        cursor = db.conn.cursor()
        
        # Total count
        cursor.execute("SELECT COUNT(*) FROM transactions")
        total_count = cursor.fetchone()[0]
        
        # Date range
        cursor.execute("SELECT MIN(date), MAX(date) FROM transactions")
        date_range = cursor.fetchone()
        
        # Banks
        cursor.execute("""
            SELECT bank_source, COUNT(*) 
            FROM transactions 
            GROUP BY bank_source 
            ORDER BY COUNT(*) DESC
        """)
        banks = cursor.fetchall()
        
        # Account types
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
    
    async def run_sse(self, host: str = "0.0.0.0", port: int = 8080):
        """Run the server with SSE transport (for remote access)."""
        from starlette.applications import Starlette
        from starlette.routing import Route, Mount
        from starlette.responses import Response
        import uvicorn
        
        sse_transport = SseServerTransport("/messages/")
        
        async def handle_sse(request):
            """Handle SSE connections - this is where clients connect to receive events."""
            client_ip = request.client.host if request.client else "unknown"
            logger.info(f"SSE connection from {client_ip}")
            try:
                async with sse_transport.connect_sse(
                    request.scope, request.receive, request._send
                ) as streams:
                    logger.debug(f"SSE streams established for {client_ip}")
                    await self.server.run(
                        streams[0], streams[1], self.server.create_initialization_options()
                    )
                logger.info(f"SSE connection closed for {client_ip}")
            except Exception as e:
                error_trace = traceback.format_exc()
                logger.error(f"SSE handler error for {client_ip}:\n{error_trace}")
                raise
            return Response()
        
        # Standard MCP SSE setup following official examples:
        # - /sse endpoint: Route handler for SSE connections
        # - /messages/ endpoint: Mount the handle_post_message directly as ASGI app
        app = Starlette(
            debug=True,
            routes=[
                Route("/sse", endpoint=handle_sse, methods=["GET"]),
                Mount("/messages/", app=sse_transport.handle_post_message),
            ],
        )
        
        logger.info(f"Starting MCP server on http://{host}:{port}")
        logger.info(f"SSE endpoint: http://{host}:{port}/sse")
        logger.info(f"Messages endpoint: http://{host}:{port}/messages/")
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
    
    async def run_stdio(self):
        """Run the server with stdio transport (for local development)."""
        logger.info("Starting MCP server on stdio")
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream, write_stream, self.server.create_initialization_options()
            )


def main():
    parser = argparse.ArgumentParser(description="Family Finance MCP Server")
    parser.add_argument(
        "--transport",
        choices=["sse", "stdio"],
        default="sse",
        help="Transport type (default: sse)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080)"
    )
    
    args = parser.parse_args()
    
    mcp = FamilyFinanceMCP()
    
    if args.transport == "sse":
        asyncio.run(mcp.run_sse(args.host, args.port))
    else:
        asyncio.run(mcp.run_stdio())


if __name__ == "__main__":
    main()
