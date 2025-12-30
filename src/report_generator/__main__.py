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
import asyncio
import logging
from datetime import datetime

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

When generating a monthly financial report:
1. First, use get_available_months to see what data is available
2. Use get_monthly_summary to get income/expense totals for the most recent month
3. Use get_spending_by_category to understand spending patterns
4. Use get_top_merchants to identify major expenses
5. Use get_month_comparison to compare with the previous month

Format your report in clean markdown with:
- A clear title with the month/year
- Executive summary with key numbers
- Spending breakdown by category
- Top merchants/expenses
- Month-over-month comparison
- Any notable observations or recommendations

Be concise but insightful. Focus on actionable insights."""

# User prompt for generating the report
USER_PROMPT = """Generate a comprehensive monthly financial report for the most recent month with data.
Include spending analysis, category breakdown, top merchants, and comparison with the previous month."""

app = MCPApp(name="finance_report_generator")


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
            logger.info("Generating financial report...")
            report = await llm.generate_str(message=USER_PROMPT)
            
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
        report_content = asyncio.run(generate_report())
        logger.info(f"Report generated ({len(report_content)} chars)")
        
        # Step 2: Send email
        logger.info("Step 2: Sending email...")
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
