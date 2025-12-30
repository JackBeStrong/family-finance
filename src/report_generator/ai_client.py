"""
AI Client abstraction for multiple providers.

Supports:
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)

Usage:
    client = get_ai_client()  # Uses AI_PROVIDER env var
    response = client.generate("Your prompt here")
"""

import os
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class AIClient(ABC):
    """Abstract base class for AI providers."""
    
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generate a response from the AI model."""
        pass


class OpenAIClient(AIClient):
    """OpenAI API client (GPT-4, GPT-3.5)."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        self.model = model
        
        # Import here to avoid requiring openai if not used
        import openai
        self.client = openai.OpenAI(api_key=self.api_key)
    
    def generate(self, prompt: str) -> str:
        """Generate a response using OpenAI API."""
        logger.info(f"Calling OpenAI API with model {self.model}")
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=4096,
            temperature=0.7
        )
        
        result = response.choices[0].message.content
        logger.info(f"OpenAI response received ({len(result)} chars)")
        return result


class AnthropicClient(AIClient):
    """Anthropic API client (Claude)."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        self.model = model
        
        # Import here to avoid requiring anthropic if not used
        import anthropic
        self.client = anthropic.Anthropic(api_key=self.api_key)
    
    def generate(self, prompt: str) -> str:
        """Generate a response using Anthropic API."""
        logger.info(f"Calling Anthropic API with model {self.model}")
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        result = response.content[0].text
        logger.info(f"Anthropic response received ({len(result)} chars)")
        return result


def get_ai_client(provider: Optional[str] = None) -> AIClient:
    """
    Factory function to get the appropriate AI client.
    
    Args:
        provider: AI provider name ("openai" or "anthropic").
                  If not provided, uses AI_PROVIDER env var.
                  Defaults to "openai" if not set.
    
    Returns:
        AIClient instance for the specified provider.
    
    Raises:
        ValueError: If provider is not supported.
    """
    provider = provider or os.environ.get("AI_PROVIDER", "openai")
    provider = provider.lower()
    
    logger.info(f"Creating AI client for provider: {provider}")
    
    if provider == "openai":
        return OpenAIClient()
    elif provider == "anthropic":
        return AnthropicClient()
    else:
        raise ValueError(f"Unsupported AI provider: {provider}. Use 'openai' or 'anthropic'.")
