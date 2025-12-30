"""
Report Generator - Main Entry Point

Generates an AI-powered financial report using MCP tools and sends it via email.

Uses mcp-agent library for agentic AI with MCP tool support.

Usage:
    python -m src.report_generator

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
from datetime import datetime
from dateutil.relativedelta import relativedelta

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

# System prompt for the financial analyst agent
SYSTEM_PROMPT = f"""You are a financial analyst assistant for a family finance tracking system.
You have access to tools that can query a database containing bank transactions from multiple accounts,
as well as tools to query investment portfolio data from Interactive Brokers.

IMPORTANT: Your response will be sent directly as an email report. Do NOT include:
- Any preamble like "I'll generate a report..." or "Let me check..."
- Any mention of tool calls like "[Calling tool...]" or "Using get_monthly_summary..."
- Any thinking or reasoning about what you're doing
- Any closing remarks like "Let me know if you need anything else"

ONLY output the final formatted report. Nothing else.

## Step 1: Understand the Financial Context

BEFORE generating the report, ALWAYS call `get_financial_context` first. This provides:
- Household members and their roles
- All accounts with their types and purposes (mortgage, offset, credit card, etc.)
- Properties with addresses (if any)
- Known entities (employers, property managers, etc.)
- Category rules for proper transaction classification
- Reporting preferences

Use this context to provide meaningful labels instead of raw account IDs or generic categories.

## Step 2: Get Investment Portfolio Data (REQUIRED)

**THIS IS MANDATORY** - You MUST call `get_flex_query` with queryId="{IBKR_FLEX_QUERY_ID}" to get investment portfolio data from Interactive Brokers.

This provides:
- Account information and total NAV (Net Asset Value) in the `ChangeInNAV` section (look for `endingValue`)
- Current positions in `OpenPositions` with cost basis and unrealized P&L (look for `levelOfDetail: "SUMMARY"` entries)
- Recent trades in `Trades` section
- Dividends and interest in `CashTransactions` section
- Cash balances in `CashReport` section

**The Investment Portfolio section MUST appear in the final report.** If the tool call fails, note that in the report.

## Step 3: Enrich Transaction Categories

When you encounter transactions with generic categories (like "INT" for interest):
1. Use `get_account_context` with the account_id to understand what type of account it is
2. If it's a mortgage account, the context will include the linked property address
3. Report these transactions with meaningful labels (e.g., "Mortgage Interest - [Property Address]")

Similarly, use `get_property_context` to understand all accounts linked to a property.

## Step 4: Gather Bank Transaction Data

Use these tools to gather data:
1. get_monthly_summary - for income/expense totals
2. get_spending_by_category - for spending patterns
3. get_top_merchants - for major expenses (limit to top 5)
4. get_transactions_by_bank - for per-bank breakdown

Keep the bank transaction analysis concise. Focus on key insights, not exhaustive details.

## Report Format (FOLLOW THIS ORDER)

Format your report in clean markdown with these sections IN THIS ORDER:

1. **Title** - "Monthly Financial Report - [Month Year]"

2. **Executive Summary** - 3-4 bullet points with:
   - Net cash flow (income - expenses)
   - Investment portfolio total value
   - Key highlight of the month

3. **Investment Portfolio** (REQUIRED SECTION)
   - Total Portfolio Value (from ChangeInNAV.endingValue)
   - Holdings table: Symbol | Shares | Value | Cost Basis | Unrealized P&L
   - Dividends received this period
   - Any realized gains from trades

4. **Bank Account Summary**
   - Total income and expenses
   - Net position

5. **Spending by Category** (top 5 categories only, table format)

6. **Key Observations** (2-3 bullet points)

Keep the report concise (under 4000 characters). Focus on insights, not raw data dumps."""

def get_user_prompt() -> str:
    """
    Generate the user prompt with the target month (last month).
    
    Since reports are typically generated at the start of a new month,
    we want to report on the previous month which has complete data.
    """
    # Calculate last month
    today = datetime.now()
    last_month = today - relativedelta(months=1)
    month_name = last_month.strftime("%B")  # e.g., "November"
    year = last_month.year
    month_num = last_month.month
    
    return f"""Generate a comprehensive monthly financial report for {month_name} {year} (month {month_num}).

Use get_monthly_summary with year={year} and month={month_num} to get the data.
Include spending analysis, category breakdown, top merchants, and comparison with the previous month ({(last_month - relativedelta(months=1)).strftime('%B %Y')})."""

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


async def generate_report() -> str:
    """
    Generate a financial report using the MCP agent.
    
    Returns:
        The generated report as markdown string.
    """
    async with app.run() as running_app:
        logger.info("MCPApp started, creating agent...")
        
        # Create the financial analyst agent
        agent = Agent(
            name="finance_analyst",
            instruction=SYSTEM_PROMPT,
            server_names=["family-finance", "interactive-brokers"],
        )
        
        async with agent:
            # List available tools for logging
            tools = await agent.list_tools()
            tool_names = [t[0] if isinstance(t, tuple) else getattr(t, 'name', str(t)) for t in tools]
            logger.info(f"Agent has access to tools: {tool_names}")
            
            # Attach the Anthropic LLM (uses model from mcp_agent.config.yaml)
            llm = await agent.attach_llm(AnthropicAugmentedLLM)
            
            # Generate the report
            user_prompt = get_user_prompt()
            logger.info(f"Generating financial report with prompt: {user_prompt[:100]}...")
            report = await llm.generate_str(message=user_prompt)
            
            return report


def main():
    """Main entry point for the report generator."""
    logger.info("=" * 50)
    logger.info("Family Finance Report Generator")
    logger.info(f"Started at: {datetime.now().isoformat()}")
    logger.info("=" * 50)
    
    try:
        # Step 1: Generate report using AI agent with MCP tools
        logger.info("Step 1: Generating report with AI agent...")
        raw_report = asyncio.run(generate_report())
        logger.info(f"Raw report generated ({len(raw_report)} chars)")
        
        # Step 2: Clean up the report (remove tool-calling artifacts)
        logger.info("Step 2: Cleaning report...")
        report_content = clean_report(raw_report)
        logger.info(f"Cleaned report ({len(report_content)} chars)")
        
        # Step 3: Send email
        logger.info("Step 3: Sending email...")
        subject = f"Family Finance Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
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
            
    except Exception as e:
        logger.exception(f"Report generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
