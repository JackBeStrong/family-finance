"""
Report Generator - Main Entry Point

Generates an AI-powered financial report using MCP tools and sends it via email.

Uses mcp-agent library for agentic AI with MCP tool support.

Usage:
    python -m src.report_generator                    # Default: last month
    python -m src.report_generator --month 11 --year 2025  # Specific month
    python -m src.report_generator --start 2025-11-01 --end 2025-11-30  # Date range

Environment Variables:
    ANTHROPIC_API_KEY: Anthropic API key
    SMTP_SERVER: SMTP server (default: smtp.gmail.com)
    SMTP_PORT: SMTP port (default: 587)
    SMTP_PASSWORD: SMTP password
    SENDER_EMAIL: Sender email address
    RECEIVER_EMAIL: Recipient email address
    MCP_SERVER_URL: MCP server URL (default: http://192.168.1.237:8080/sse)
"""

import os
import sys
import re
import asyncio
import logging
import argparse
from datetime import datetime
from dateutil.relativedelta import relativedelta
from calendar import monthrange

from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM
from mcp_agent.config import Settings, get_settings

from .email_sender import send_report_email

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get IBKR Flex Query ID from environment (default to the configured query)
IBKR_FLEX_QUERY_ID = os.environ.get("IBKR_FLEX_QUERY_ID", "1359561")

# Base system prompt for the financial analyst agent
BASE_SYSTEM_PROMPT = """You are a financial analyst assistant for a family finance tracking system.
You have access to tools that can query a database containing bank transactions from multiple accounts,
as well as tools to query investment portfolio data from Interactive Brokers.

IMPORTANT: Your response will be sent directly as an email report. Do NOT include:
- Any preamble like "I'll generate a report..." or "Let me check..."
- Any mention of tool calls like "[Calling tool...]" or "Using get_monthly_summary..."
- Any thinking or reasoning about what you're doing
- Any closing remarks like "Let me know if you need anything else"

ONLY output the final formatted report sections. Nothing else."""

# System prompt for PART 1: Summary, Credit Card, Investment Portfolio
SYSTEM_PROMPT_PART1 = f"""{BASE_SYSTEM_PROMPT}

## Your Task: Generate PART 1 of the Monthly Financial Report

You are generating the FIRST HALF of a comprehensive financial report. Focus on:
- Executive Summary
- Credit Card Spending (DETAILED - this is the most important section)
- Investment Portfolio

## Step 1: Understand the Financial Context

BEFORE generating the report, ALWAYS call `get_financial_context` first. This provides:
- Household members and their roles
- All accounts with their types and purposes (mortgage, offset, credit card, etc.)
- Properties with addresses (if any)
- Known entities (employers, property managers, etc.)
- Category rules for proper transaction classification

Use this context to provide meaningful labels instead of raw account IDs.

## Step 2: Get Investment Portfolio Data (REQUIRED)

**THIS IS MANDATORY** - You MUST call `get_flex_query` with queryId="{IBKR_FLEX_QUERY_ID}" to get investment portfolio data.

This provides:
- Account information and total NAV in the `ChangeInNAV` section (look for `endingValue`)
- Current positions in `OpenPositions` with cost basis and unrealized P&L (look for `levelOfDetail: "SUMMARY"` entries)
- Recent trades in `Trades` section
- Dividends and interest in `CashTransactions` section
- Cash balances in `CashReport` section

## Step 3: Get Credit Card Transactions

Use `query_transactions` with the credit card account_id (from financial context) to get ALL credit card transactions for the month.
This is the most important data - we want to see every transaction.

## Step 4: Get Summary Data

Use these tools:
1. get_monthly_summary - for income/expense totals
2. get_month_comparison - for month-over-month changes

## Report Format for PART 1 (FOLLOW EXACTLY)

**CRITICAL: Each section MUST include the section number (1, 2, 3, 4) in the heading. Do NOT omit the numbers.**

Output this EXACTLY (with section numbers):

## 1. Executive Summary

# Monthly Financial Report: [Month Year]

**Period:** [Month] 1-[last day], [Year] | **Transactions:** [count]

| Metric | Amount | Change vs [Previous Month] |
|--------|--------|---------------------------|
| Total Income | $X | ⬆️/⬇️ X% (+/-$X) |
| Total Expenses | $X | ⬆️/⬇️ X% (+/-$X) |
| Net Position | $X | ⬆️/⬇️ $X |

## 2. 🚨 Key Highlights
- Investment portfolio value and performance
- Credit card spending summary
- Notable income/expense changes
- Any unusual transactions or patterns

## 3. 💳 Credit Card Spending Detail
Use `query_transactions` with the credit card account_id to get credit card transactions.

**Credit Card Summary:**

| Metric | Value |
|--------|-------|
| Total Spend | $X |
| Transactions | X |
| Average | $X |

**Top 5 Largest Purchases:**

| Date | Description | Amount |
|------|-------------|--------|
| Nov XX | XXX | $X |
| Nov XX | XXX | $X |
| Nov XX | XXX | $X |
| Nov XX | XXX | $X |
| Nov XX | XXX | $X |

**Spending by Category:**

| Category | Amount | Count |
|----------|--------|-------|
| 🍽️ Dining | $X | X |
| 🛒 Groceries | $X | X |
| 🛍️ Shopping | $X | X |
| 🔄 Subscriptions | $X | X |
| ⛽ Transport | $X | X |
| 🎬 Entertainment | $X | X |
| 💡 Utilities | $X | X |
| 🏥 Healthcare | $X | X |
| Other | $X | X |

## 4. 📈 Investment Portfolio (REQUIRED)
**Total Portfolio Value:** $X USD (~$X AUD at 1.51 rate)

| Symbol | Shares | Market Value (USD) | Cost Basis (USD) | Unrealized P&L (USD) |
|--------|--------|-------------------|------------------|---------------------|
| XXX | X | $X | $X | +/-$X (+/-X%) |

**Cash Position:** $X USD

**Portfolio Composition:**
- Breakdown by holding with percentages

**Trading Activity (if any):**
- Realized gains/losses from trades

**Dividend Income:** $X USD
- Breakdown by symbol

**Interest Income:** $X USD (if any)

---
END OF PART 1 - Part 2 will continue with spending categories, merchants, and recommendations.
"""

# System prompt for PART 2: Categories, Merchants, Recommendations
SYSTEM_PROMPT_PART2 = f"""{BASE_SYSTEM_PROMPT}

## Your Task: Generate PART 2 of the Monthly Financial Report

You are generating the SECOND HALF of a comprehensive financial report. Focus on:
- Spending by Category (all accounts)
- Top Merchants
- Analysis and Recommendations

## Step 1: Understand the Financial Context

Call `get_financial_context` first to understand account labels and purposes.

## Step 2: Gather Data

Use these tools:
1. get_spending_by_category - for spending patterns
2. get_top_merchants - for top 5 merchants only

## Report Format for PART 2 (FOLLOW EXACTLY)

**CRITICAL: Each section MUST include the section number (5, 6, 7, 8) in the heading. Do NOT omit the numbers.**

## 5. 💰 Spending Breakdown by Category (All Accounts)
| Category | Amount | % of Total |
|----------|--------|------------|
| XXX | $X | X% |

## 6. 🏪 Top 5 Merchants
| Merchant/Description | Amount |
|---------------------|--------|
| XXX | $X |

## 7. 💭 Key Observations & Recommendations

**⚠️ Concerns**
- 2-3 bullet points about potential issues

**✅ Strengths**
- 2-3 bullet points about positive aspects

**📋 Recommendations**
- 3-5 actionable recommendations based on the data

## 8. Footer
```
---
**Report Generated:** [Month Year] Data | [X] Transactions Analyzed
```

## Important Guidelines
- Use emojis for section headers as shown above
- Be concise - avoid verbose explanations
- Use meaningful account labels from financial context (not raw IDs)
- Provide specific, actionable insights
- **CRITICAL: Use proper markdown tables** - every table must have:
  - Header row with | separators
  - Separator row with |---|---|
  - Data rows with | separators
  - NO nested bullet lists inside tables
"""

def setup_ibkr_environment():
    """
    Ensure IB_FLEX_TOKEN is available for the interactive-brokers MCP server.
    
    The mcp-agent library's YAML config doesn't expand ${VAR} syntax in the env block.
    We need to ensure the environment variable is set in the current process so that
    when the stdio MCP server is spawned, it inherits the token.
    
    This function also patches the mcp-agent's get_default_environment to include
    our custom environment variables.
    """
    ib_token = os.environ.get("IB_FLEX_TOKEN")
    if ib_token:
        logger.info("IB_FLEX_TOKEN found in environment")
    else:
        logger.warning("IB_FLEX_TOKEN not found in environment - IBKR MCP will fail")
        return
    
    # Patch the subprocess environment to include IB_FLEX_TOKEN
    # The mcp library uses get_default_environment() which only returns minimal vars
    # We need to ensure our token is passed through
    try:
        from mcp.client.stdio import get_default_environment
        import mcp.client.stdio as stdio_module
        
        original_get_default_environment = get_default_environment
        
        def patched_get_default_environment():
            """Return default environment plus IB_FLEX_TOKEN."""
            env = original_get_default_environment()
            # Add IB_FLEX_TOKEN from current environment
            if "IB_FLEX_TOKEN" in os.environ:
                env["IB_FLEX_TOKEN"] = os.environ["IB_FLEX_TOKEN"]
            return env
        
        # Monkey-patch the function
        stdio_module.get_default_environment = patched_get_default_environment
        logger.info("Patched get_default_environment to include IB_FLEX_TOKEN")
    except ImportError as e:
        logger.warning(f"Could not patch mcp.client.stdio: {e}")


# Setup IBKR environment before creating the app
setup_ibkr_environment()

app = MCPApp(name="finance_report_generator")


def clean_report(report: str) -> str:
    """
    Remove tool-calling artifacts from the report.
    
    The mcp-agent library sometimes includes [Calling tool...] lines
    in the output. This function strips them out.
    """
    # Remove lines that start with [Calling tool
    lines = report.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Skip lines that are tool call artifacts
        if line.strip().startswith('[Calling tool'):
            continue
        # Skip lines that look like "Perfect!" or "Let me" preambles
        if re.match(r'^(Perfect!|Great!|Let me|I\'ll|I will|Now let me)', line.strip()):
            continue
        cleaned_lines.append(line)
    
    # Join and strip leading/trailing whitespace
    result = '\n'.join(cleaned_lines).strip()
    
    return result


async def generate_report_part(system_prompt: str, user_prompt: str, part_name: str) -> str:
    """
    Generate a part of the financial report using the MCP agent.
    
    Args:
        system_prompt: The system prompt for this part
        user_prompt: The user prompt for this part
        part_name: Name of the part for logging
    
    Returns:
        The generated report part as markdown string.
    """
    async with app.run() as running_app:
        logger.info(f"MCPApp started for {part_name}, creating agent...")
        
        # Create the financial analyst agent
        agent = Agent(
            name=f"finance_analyst_{part_name}",
            instruction=system_prompt,
            server_names=["family-finance", "interactive-brokers"],
        )
        
        async with agent:
            # List available tools for logging
            tools = await agent.list_tools()
            tool_names = [t[0] if isinstance(t, tuple) else getattr(t, 'name', str(t)) for t in tools]
            logger.info(f"Agent ({part_name}) has access to {len(tool_names)} tools")
            
            # Attach the Anthropic LLM (uses model from mcp_agent.config.yaml)
            llm = await agent.attach_llm(AnthropicAugmentedLLM)
            
            # Generate the report part
            logger.info(f"Generating {part_name}...")
            report_part = await llm.generate_str(message=user_prompt)
            
            return report_part


async def generate_report(start_date: datetime = None, end_date: datetime = None) -> str:
    """
    Generate a comprehensive financial report in two parts to avoid token limits.
    
    Part 1: Executive Summary, Credit Card Details, Investment Portfolio
    Part 2: Spending Categories, Merchants, Bank Activity, Recommendations
    
    Args:
        start_date: Start date for the report period (default: first day of last month)
        end_date: End date for the report period (default: last day of last month)
    
    Returns:
        The combined report as markdown string.
    """
    # Calculate target period
    today = datetime.now()
    
    if start_date is None or end_date is None:
        # Default: last month
        last_month = today - relativedelta(months=1)
        start_date = last_month.replace(day=1)
        _, last_day = monthrange(last_month.year, last_month.month)
        end_date = last_month.replace(day=last_day)
    
    # Format dates for display and queries
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    # Determine if this is a single month or a date range
    is_single_month = (start_date.year == end_date.year and
                       start_date.month == end_date.month and
                       start_date.day == 1 and
                       end_date.day == monthrange(end_date.year, end_date.month)[1])
    
    if is_single_month:
        # Single month - use month-based queries
        month_name = start_date.strftime("%B")
        year = start_date.year
        month_num = start_date.month
        period_label = f"{month_name} {year}"
        period_detail = f"{month_name} 1-{end_date.day}, {year}"
        prev_month_name = (start_date - relativedelta(months=1)).strftime('%B %Y')
        
        # User prompt for Part 1 (single month)
        user_prompt_part1 = f"""Generate PART 1 of the monthly financial report for {month_name} {year} (month {month_num}).

This part should include:
1. Title and Executive Summary (with summary table)
2. Key Highlights (3-5 bullet points)
3. Credit Card Spending (summary + top 5 transactions + spending by category)
4. Investment Portfolio (holdings, dividends, trades)

Use get_monthly_summary with year={year} and month={month_num}.
Use query_transactions with the credit card account_id and start_date="{start_str}" and end_date="{end_str}".
Use get_flex_query for investment portfolio data.

Keep it concise - only top 5 credit card transactions, not all."""

        # User prompt for Part 2 (single month)
        user_prompt_part2 = f"""Generate PART 2 of the monthly financial report for {month_name} {year} (month {month_num}).

This part should include:
5. Spending Breakdown by Category (all accounts)
6. Top 5 Merchants
7. Key Observations & Recommendations
8. Footer

Use get_spending_by_category and get_top_merchants (top_n=5) with year={year} and month={month_num}.

Keep it concise - no month-over-month comparison needed."""
    else:
        # Date range - use date-based queries
        period_label = f"{start_str} to {end_str}"
        period_detail = f"{start_date.strftime('%B %d, %Y')} - {end_date.strftime('%B %d, %Y')}"
        
        # User prompt for Part 1 (date range)
        user_prompt_part1 = f"""Generate PART 1 of the financial report for the period {period_label}.

This part should include:
1. Title and Executive Summary (with summary table)
2. Key Highlights (3-5 bullet points)
3. Credit Card Spending (summary + top 5 transactions + spending by category)
4. Investment Portfolio (holdings, dividends, trades)

Use query_transactions with start_date="{start_str}" and end_date="{end_str}" to get all transactions.
Use query_transactions with the credit card account_id and start_date="{start_str}" and end_date="{end_str}" for credit card transactions.
Use get_flex_query for investment portfolio data.

For the summary, calculate totals from the transaction data.
Keep it concise - only top 5 credit card transactions, not all."""

        # User prompt for Part 2 (date range)
        user_prompt_part2 = f"""Generate PART 2 of the financial report for the period {period_label}.

This part should include:
5. Spending Breakdown by Category (all accounts)
6. Top 5 Merchants
7. Key Observations & Recommendations
8. Footer

Use query_transactions with start_date="{start_str}" and end_date="{end_str}" to get all transactions.
Then calculate category breakdown and top merchants from the transaction data.

Keep it concise - no month-over-month comparison needed."""

    # Generate Part 1
    logger.info("=" * 40)
    logger.info("Generating Part 1: Summary, Credit Card, Investments")
    logger.info("=" * 40)
    part1 = await generate_report_part(SYSTEM_PROMPT_PART1, user_prompt_part1, "part1")
    logger.info(f"Part 1 generated ({len(part1)} chars)")
    
    # Generate Part 2
    logger.info("=" * 40)
    logger.info("Generating Part 2: Categories, Merchants, Recommendations")
    logger.info("=" * 40)
    part2 = await generate_report_part(SYSTEM_PROMPT_PART2, user_prompt_part2, "part2")
    logger.info(f"Part 2 generated ({len(part2)} chars)")
    
    # Combine the parts
    # Remove the "END OF PART 1" marker if present
    part1_cleaned = re.sub(r'---\s*END OF PART 1.*$', '', part1, flags=re.DOTALL).strip()
    
    # Combine
    combined_report = f"{part1_cleaned}\n\n{part2}"
    logger.info(f"Combined report: {len(combined_report)} chars")
    
    return combined_report


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate AI-powered financial reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.report_generator                           # Default: last month
  python -m src.report_generator --month 11 --year 2025    # Specific month
  python -m src.report_generator --start 2025-11-01 --end 2025-11-30  # Date range
  python -m src.report_generator --start 2025-10-01 --end 2025-11-30  # Multi-month range
        """
    )
    
    # Month/year options (for single month reports)
    parser.add_argument(
        "--month", "-m",
        type=int,
        choices=range(1, 13),
        metavar="MONTH",
        help="Month number (1-12) for single month report"
    )
    parser.add_argument(
        "--year", "-y",
        type=int,
        metavar="YEAR",
        help="Year (e.g., 2025) for single month report"
    )
    
    # Date range options (for custom date ranges)
    parser.add_argument(
        "--start", "-s",
        type=str,
        metavar="DATE",
        help="Start date in YYYY-MM-DD format"
    )
    parser.add_argument(
        "--end", "-e",
        type=str,
        metavar="DATE",
        help="End date in YYYY-MM-DD format"
    )
    
    # Optional: skip email (for testing)
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Generate report but don't send email (print to stdout instead)"
    )
    
    return parser.parse_args()


def get_date_range(args) -> tuple[datetime, datetime]:
    """
    Determine the date range from command-line arguments.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        Tuple of (start_date, end_date) as datetime objects
        
    Raises:
        ValueError: If arguments are invalid or conflicting
    """
    # Check for conflicting options
    has_month_year = args.month is not None or args.year is not None
    has_date_range = args.start is not None or args.end is not None
    
    if has_month_year and has_date_range:
        raise ValueError("Cannot use --month/--year with --start/--end. Choose one method.")
    
    if has_month_year:
        # Month/year mode
        if args.month is None or args.year is None:
            raise ValueError("Both --month and --year are required when using month mode")
        
        start_date = datetime(args.year, args.month, 1)
        _, last_day = monthrange(args.year, args.month)
        end_date = datetime(args.year, args.month, last_day)
        
        logger.info(f"Using month mode: {start_date.strftime('%B %Y')}")
        return start_date, end_date
    
    elif has_date_range:
        # Date range mode
        if args.start is None or args.end is None:
            raise ValueError("Both --start and --end are required when using date range mode")
        
        try:
            start_date = datetime.strptime(args.start, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid start date format: {args.start}. Use YYYY-MM-DD")
        
        try:
            end_date = datetime.strptime(args.end, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid end date format: {args.end}. Use YYYY-MM-DD")
        
        if start_date > end_date:
            raise ValueError(f"Start date ({args.start}) must be before end date ({args.end})")
        
        logger.info(f"Using date range mode: {args.start} to {args.end}")
        return start_date, end_date
    
    else:
        # Default: last month
        logger.info("Using default mode: last month")
        return None, None  # generate_report() will handle the default


def main():
    """Main entry point for the report generator."""
    # Parse command-line arguments
    args = parse_args()
    
    logger.info("=" * 50)
    logger.info("Family Finance Report Generator")
    logger.info(f"Started at: {datetime.now().isoformat()}")
    logger.info("=" * 50)
    
    try:
        # Determine date range from arguments
        start_date, end_date = get_date_range(args)
        
        if start_date and end_date:
            logger.info(f"Report period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        else:
            logger.info("Report period: Last month (default)")
        
        # Step 1: Generate report using AI agent with MCP tools
        logger.info("Step 1: Generating report with AI agent...")
        raw_report = asyncio.run(generate_report(start_date, end_date))
        logger.info(f"Raw report generated ({len(raw_report)} chars)")
        
        # Step 2: Clean up the report (remove tool-calling artifacts)
        logger.info("Step 2: Cleaning report...")
        report_content = clean_report(raw_report)
        logger.info(f"Cleaned report ({len(report_content)} chars)")
        
        # Step 3: Send email (or print to stdout if --no-email)
        if args.no_email:
            logger.info("Step 3: Printing report to stdout (--no-email specified)")
            print("\n" + "=" * 60)
            print(report_content)
            print("=" * 60 + "\n")
            sys.exit(0)
        
        logger.info("Step 3: Sending email...")
        
        # Build subject line with date range info
        if start_date and end_date:
            if start_date.year == end_date.year and start_date.month == end_date.month:
                period_str = start_date.strftime('%B %Y')
            else:
                period_str = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
        else:
            # Default: last month
            last_month = datetime.now() - relativedelta(months=1)
            period_str = last_month.strftime('%B %Y')
        
        subject = f"Family Finance Report - {period_str}"
        
        success = send_report_email(
            subject=subject,
            body=report_content,
            content_type="markdown"
        )
        
        if success:
            logger.info("Report sent successfully!")
            sys.exit(0)
        else:
            logger.error("Failed to send report email")
            sys.exit(1)
            
    except ValueError as e:
        logger.error(f"Invalid arguments: {e}")
        sys.exit(2)
    except Exception as e:
        logger.exception(f"Report generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
