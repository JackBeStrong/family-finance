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

from .email_sender import send_report_email

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# System prompt for the financial analyst agent
SYSTEM_PROMPT = """You are a financial analyst assistant for a family finance tracking system.
You have access to tools that can query a database containing bank transactions from multiple accounts.

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

## Step 2: Enrich Transaction Categories

When you encounter transactions with generic categories (like "INT" for interest):
1. Use `get_account_context` with the account_id to understand what type of account it is
2. If it's a mortgage account, the context will include the linked property address
3. Report these transactions with meaningful labels (e.g., "Mortgage Interest - [Property Address]")

Similarly, use `get_property_context` to understand all accounts linked to a property.

## Step 3: Gather Report Data

Use these tools to gather data:
1. get_available_months - to find the most recent month with data
2. get_monthly_summary - for income/expense totals
3. get_spending_by_category - for spending patterns
4. get_top_merchants - for major expenses
5. get_month_comparison - for month-over-month comparison
6. get_transactions_by_bank - for per-bank breakdown
7. query_transactions - for detailed transaction data when needed

## Report Format

Format your report in clean markdown with:
- A clear title with the month/year
- Executive summary with key numbers
- Property-related expenses (mortgage interest, etc.) broken down by property if applicable
- Spending breakdown by category (table format)
- Top merchants/expenses (table format)
- Activity by bank/account (use account labels from context, not raw IDs)
- Month-over-month comparison
- Key observations and recommendations

Be concise but insightful. Focus on actionable insights. Use tables for data presentation."""

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
            server_names=["family-finance"],
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
