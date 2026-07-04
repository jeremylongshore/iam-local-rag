"""
Anthropic Claude provider implementation using official SDK.
"""
import time
from typing import Dict, List, Optional

from ..config import Config
from .base import LLMProvider
from .profiles import ProviderCapabilities, ProviderCostProfile, ProviderPrivacyProfile


class AnthropicLLMProvider(LLMProvider):
    """
    Anthropic Claude LLM provider using official Python SDK.
    Supports Claude 3.5 Sonnet and other models.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or Config.ANTHROPIC_API_KEY
        self.model = model or Config.ANTHROPIC_MODEL

        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY required. Set it in .env file:\n"
                "ANTHROPIC_API_KEY=sk-ant-..."
            )

        self._client = None

    def _get_client(self):
        """Lazy initialization of Anthropic client"""
        if self._client is None:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "Anthropic SDK not installed. Install with:\n"
                    "pip install anthropic"
                )
        return self._client

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """
        Generate text from prompt using Claude.

        Args:
            prompt: The input prompt
            max_tokens: Maximum tokens to generate (default: 1024)
            temperature: Sampling temperature (0.0 to 1.0)
            **kwargs: Additional parameters

        Returns:
            Generated text response
        """
        max_tokens = max_tokens or 1024

        # Convert single prompt to messages format for Claude
        messages = [{"role": "user", "content": prompt}]

        return self.generate_with_messages(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

    def generate_with_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """
        Generate text from messages using Claude.

        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate (default: 1024)
            temperature: Sampling temperature
            **kwargs: Additional parameters (system, top_p, top_k, etc.)

        Returns:
            Generated text response
        """
        max_tokens = max_tokens or 1024
        client = self._get_client()

        # Extract system message if present
        system = kwargs.pop('system', None)
        if not system and messages and messages[0]['role'] == 'system':
            system = messages[0]['content']
            messages = messages[1:]  # Remove system message from messages list

        # Retry logic for rate limits and transient errors
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                # Call Claude API
                response = client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system if system else None,
                    messages=messages,
                    **kwargs
                )

                # Extract text from response
                return response.content[0].text

            except Exception as e:
                error_str = str(e).lower()

                # Check for rate limit or server errors
                if '429' in error_str or 'rate' in error_str:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)  # Exponential backoff
                        time.sleep(delay)
                        continue
                    else:
                        raise ValueError(f"Rate limit exceeded after {max_retries} retries")

                elif '5' in error_str[:3]:  # 5xx server errors
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        time.sleep(delay)
                        continue
                    else:
                        raise ValueError(f"Server error after {max_retries} retries: {str(e)}")

                # Other errors, raise immediately
                else:
                    raise

        # Should not reach here, but just in case
        raise ValueError("Max retries exceeded")

    def get_model_name(self) -> str:
        """Return the model identifier"""
        return self.model

    def is_available(self) -> bool:
        """Check if the provider is configured and accessible"""
        if not self.api_key:
            return False

        try:
            # Constructing the client (lazy import + key check) is enough here;
            # health_check() does the real network probe.
            self._get_client()
            return True
        except Exception:
            return False

    def get_privacy_profile(self) -> ProviderPrivacyProfile:
        return ProviderPrivacyProfile(
            provider_label="anthropic",
            is_local=False,
            sends_data_offhost=True,
            data_region="anthropic-cloud",
        )

    def get_cost_profile(self) -> ProviderCostProfile:
        # Approximate Claude 3.5 Sonnet pricing (USD / 1M tokens).
        return ProviderCostProfile(input_per_million_usd=3.0, output_per_million_usd=15.0)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_system_prompt=True,
            supports_tools=True,
            max_context_tokens=200000,
        )
