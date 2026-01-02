"""
Agentic Report Generator using MCP tools.

This module provides an AI-agnostic agentic loop that:
1. Connects to an MCP server to discover available tools
2. Sends a prompt to an AI provider with the tools
3. Executes tool calls via MCP when the AI requests them
4. Returns the final report when the AI is done

Supports: Anthropic (Claude), OpenAI (GPT-4)
"""

import os
import json
import asyncio
import logging
from typing import Optional, Any
from dataclasses import dataclass

from mcp.client.streamable_http import streamable_http_client
from mcp import ClientSession

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for the agentic report generator."""
    mcp_server_url: str
    ai_provider: str  # "anthropic" or "openai"
    model: str
    max_iterations: int = 10  # Prevent infinite loops


def mcp_tools_to_anthropic(mcp_tools: list) -> list:
    """Convert MCP tool format to Anthropic tool format."""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.inputSchema
        }
        for tool in mcp_tools
    ]


def mcp_tools_to_openai(mcp_tools: list) -> list:
    """Convert MCP tool format to OpenAI tool format."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.inputSchema
            }
        }
        for tool in mcp_tools
    ]


async def run_anthropic_agent(
    session: ClientSession,
    tools: list,
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_iterations: int
) -> str:
    """Run agentic loop with Anthropic Claude."""
    import anthropic
    
    client = anthropic.Anthropic()
    anthropic_tools = mcp_tools_to_anthropic(tools)
    
    messages = [{"role": "user", "content": user_prompt}]
    
    for iteration in range(max_iterations):
        logger.info(f"Iteration {iteration + 1}/{max_iterations}")
        
        # Call Claude
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=system_prompt,
            tools=anthropic_tools,
            messages=messages
        )
        
        logger.info(f"Stop reason: {response.stop_reason}")
        
        # Check if we're done
        if response.stop_reason == "end_turn":
            # Extract final text response
            for block in response.content:
                if hasattr(block, 'text'):
                    return block.text
            return "No text response generated."
        
        # Process tool uses
        if response.stop_reason == "tool_use":
            # Add assistant's response to messages
            messages.append({"role": "assistant", "content": response.content})
            
            # Process each tool use
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_use_id = block.id
                    
                    logger.info(f"Executing tool: {tool_name} with input: {json.dumps(tool_input)}")
                    
                    # Execute tool via MCP
                    try:
                        result = await session.call_tool(tool_name, tool_input)
                        # Extract text content from result
                        result_text = ""
                        for content in result.content:
                            if hasattr(content, 'text'):
                                result_text += content.text
                        
                        logger.info(f"Tool result: {result_text[:200]}...")
                        
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": result_text
                        })
                    except Exception as e:
                        logger.error(f"Tool execution failed: {e}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": f"Error: {str(e)}",
                            "is_error": True
                        })
            
            # Add tool results to messages
            messages.append({"role": "user", "content": tool_results})
        else:
            # Unexpected stop reason
            logger.warning(f"Unexpected stop reason: {response.stop_reason}")
            break
    
    return "Max iterations reached without completing the report."


async def run_openai_agent(
    session: ClientSession,
    tools: list,
    system_prompt: str,
    user_prompt: str,
    model: str,
    max_iterations: int
) -> str:
    """Run agentic loop with OpenAI GPT."""
    import openai
    
    client = openai.OpenAI()
    openai_tools = mcp_tools_to_openai(tools)
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    for iteration in range(max_iterations):
        logger.info(f"Iteration {iteration + 1}/{max_iterations}")
        
        # Call OpenAI
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=openai_tools,
            tool_choice="auto"
        )
        
        message = response.choices[0].message
        finish_reason = response.choices[0].finish_reason
        
        logger.info(f"Finish reason: {finish_reason}")
        
        # Check if we're done
        if finish_reason == "stop":
            return message.content or "No text response generated."
        
        # Process tool calls
        if finish_reason == "tool_calls" and message.tool_calls:
            # Add assistant's response to messages
            messages.append(message)
            
            # Process each tool call
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_input = json.loads(tool_call.function.arguments)
                
                logger.info(f"Executing tool: {tool_name} with input: {json.dumps(tool_input)}")
                
                # Execute tool via MCP
                try:
                    result = await session.call_tool(tool_name, tool_input)
                    result_text = ""
                    for content in result.content:
                        if hasattr(content, 'text'):
                            result_text += content.text
                    
                    logger.info(f"Tool result: {result_text[:200]}...")
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_text
                    })
                except Exception as e:
                    logger.error(f"Tool execution failed: {e}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Error: {str(e)}"
                    })
        else:
            # Unexpected finish reason
            logger.warning(f"Unexpected finish reason: {finish_reason}")
            break
    
    return "Max iterations reached without completing the report."


async def generate_report(
    config: AgentConfig,
    system_prompt: str,
    user_prompt: str
) -> str:
    """
    Generate a report using an agentic AI with MCP tools.
    
    Args:
        config: Agent configuration (MCP server URL, AI provider, model)
        system_prompt: System prompt for the AI
        user_prompt: User prompt (what report to generate)
    
    Returns:
        The generated report as a string (markdown).
    """
    logger.info(f"Connecting to MCP server at {config.mcp_server_url}")
    
    # Use Streamable HTTP transport (modern MCP protocol)
    async with streamable_http_client(config.mcp_server_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            # Initialize MCP session
            await session.initialize()
            logger.info("MCP session initialized")
            
            # Get available tools
            tools_response = await session.list_tools()
            tools = tools_response.tools
            logger.info(f"Discovered {len(tools)} tools")
            
            # Run the appropriate agent
            if config.ai_provider == "anthropic":
                return await run_anthropic_agent(
                    session, tools, system_prompt, user_prompt,
                    config.model, config.max_iterations
                )
            elif config.ai_provider == "openai":
                return await run_openai_agent(
                    session, tools, system_prompt, user_prompt,
                    config.model, config.max_iterations
                )
            else:
                raise ValueError(f"Unsupported AI provider: {config.ai_provider}")


def generate_report_sync(
    config: AgentConfig,
    system_prompt: str,
    user_prompt: str
) -> str:
    """Synchronous wrapper for generate_report."""
    return asyncio.run(generate_report(config, system_prompt, user_prompt))
