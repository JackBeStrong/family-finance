#!/usr/bin/env python3
"""
Test script for mcp-agent with family-finance MCP server.

Run with:
    cd /home/jack/workspace/family-finance
    source venv/bin/activate
    source .env
    python test_mcp_agent.py
"""

import asyncio
from mcp_agent.app import MCPApp
from mcp_agent.agents.agent import Agent
from mcp_agent.workflows.llm.augmented_llm_anthropic import AnthropicAugmentedLLM

app = MCPApp(name="finance_report")

async def test():
    async with app.run() as running_app:
        logger = running_app.logger
        
        # Create agent with our family-finance MCP server
        agent = Agent(
            name="finance_analyst",
            instruction="""You are a financial analyst. Use the available tools to query 
            transaction data and provide insights. Always format your responses in markdown.""",
            server_names=["family-finance"],
        )
        
        async with agent:
            # List available tools (returns list of tuples or Tool objects)
            tools = await agent.list_tools()
            tool_names = [t[0] if isinstance(t, tuple) else t.name for t in tools]
            logger.info(f"Available tools: {tool_names}")
            
            # Attach Anthropic LLM (uses claude-sonnet-4-5-20250514 from config)
            llm = await agent.attach_llm(AnthropicAugmentedLLM)
            
            # Generate a simple report
            result = await llm.generate_str(
                message="What months have transaction data? Just list them briefly."
            )
            print("\n" + "="*50)
            print("RESULT:")
            print("="*50)
            print(result)

if __name__ == "__main__":
    asyncio.run(test())
