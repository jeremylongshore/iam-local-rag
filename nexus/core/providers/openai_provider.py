"""
OpenAI provider implementation using the official SDK.

Includes three surfaces:
- OpenAILLMProvider          — Chat Completions (default) or the Responses API.
- OpenAIEmbeddingProvider    — embeddings.
- OpenAICompatibleLLMProvider — one adapter for any OpenAI-compatible endpoint
  (OpenRouter, Together, vLLM, LM Studio, llama.cpp servers) via a base_url.

The `openai` SDK is imported lazily inside `_get_client` so importing this
module never requires the SDK to be installed.
"""
import time
from typing import Dict, List, Optional

from ..config import Config
from .base import EmbeddingProvider, LLMProvider
from .profiles import ProviderCapabilities, ProviderCostProfile, ProviderPrivacyProfile


class OpenAILLMProvider(LLMProvider):
    """OpenAI GPT LLM provider (Chat Completions or Responses API)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        use_responses_api: bool = False,
    ):
        self.api_key = api_key or Config.OPENAI_API_KEY
        self.model = model or Config.OPENAI_MODEL
        self.use_responses_api = use_responses_api

        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY required. Set it in .env file:\n"
                "OPENAI_API_KEY=sk-..."
            )

        self._client = None

    def _get_client(self):
        """Lazy initialization of OpenAI client"""
        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "OpenAI SDK not installed. Install with:\n"
                    "pip install openai"
                )
        return self._client

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        """Generate text from prompt"""
        if self.use_responses_api:
            return self._generate_responses(prompt, max_tokens, temperature, **kwargs)
        messages = [{"role": "user", "content": prompt}]
        return self.generate_with_messages(messages, max_tokens, temperature, **kwargs)

    def _generate_responses(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        """Generate via the OpenAI Responses API (client.responses.create)."""
        client = self._get_client()
        max_tokens = max_tokens or 1024

        max_retries = 3
        base_delay = 1.0
        for attempt in range(max_retries):
            try:
                response = client.responses.create(
                    model=self.model,
                    input=prompt,
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs,
                )
                # SDK convenience accessor for concatenated text output.
                return response.output_text
            except Exception as e:
                error_str = str(e).lower()
                if "rate" in error_str or "429" in error_str or "5" in error_str[:3]:
                    if attempt < max_retries - 1:
                        time.sleep(base_delay * (2**attempt))
                        continue
                    raise ValueError(f"API error after {max_retries} retries: {e}")
                raise

        raise ValueError("Max retries exceeded")

    def generate_with_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        """Generate text from messages"""
        client = self._get_client()
        max_tokens = max_tokens or 1024

        # Retry logic for rate limits
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs,
                )

                return response.choices[0].message.content

            except Exception as e:
                error_str = str(e).lower()

                # Rate limit or server errors
                if "rate" in error_str or "429" in error_str or "5" in error_str[:3]:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
                        time.sleep(delay)
                        continue
                    else:
                        raise ValueError(f"API error after {max_retries} retries: {str(e)}")
                else:
                    raise

        raise ValueError("Max retries exceeded")

    def get_model_name(self) -> str:
        return self.model

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            self._get_client()
            return True
        except Exception:
            return False

    def get_privacy_profile(self) -> ProviderPrivacyProfile:
        return ProviderPrivacyProfile(
            provider_label="openai",
            is_local=False,
            sends_data_offhost=True,
            data_region="openai-cloud",
        )

    def get_cost_profile(self) -> ProviderCostProfile:
        # Approximate gpt-4-turbo-class pricing (USD / 1M tokens).
        return ProviderCostProfile(input_per_million_usd=10.0, output_per_million_usd=30.0)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_system_prompt=True,
            supports_tools=True,
            max_context_tokens=128000,
        )


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI embeddings provider using official SDK"""

    def __init__(self, api_key: Optional[str] = None, model: str = "text-embedding-ada-002"):
        self.api_key = api_key or Config.OPENAI_API_KEY
        self.model = model

        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY required. Set it in .env file:\n"
                "OPENAI_API_KEY=sk-..."
            )

        self._client = None

    def _get_client(self):
        """Lazy initialization of OpenAI client"""
        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "OpenAI SDK not installed. Install with:\n"
                    "pip install openai"
                )
        return self._client

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for documents"""
        client = self._get_client()

        # OpenAI has a max batch size, process in chunks
        batch_size = 100
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            # Retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = client.embeddings.create(
                        model=self.model,
                        input=batch,
                    )

                    embeddings = [item.embedding for item in response.data]
                    all_embeddings.extend(embeddings)
                    break

                except Exception:
                    if attempt < max_retries - 1:
                        time.sleep(1.0 * (2**attempt))
                        continue
                    else:
                        raise

        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for query"""
        return self.embed_documents([text])[0]

    def get_embedding_dimension(self) -> int:
        return 1536  # text-embedding-ada-002

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            self._get_client()
            return True
        except Exception:
            return False

    def get_privacy_profile(self) -> ProviderPrivacyProfile:
        return ProviderPrivacyProfile(
            provider_label="openai",
            is_local=False,
            sends_data_offhost=True,
            data_region="openai-cloud",
        )

    def get_cost_profile(self) -> ProviderCostProfile:
        return ProviderCostProfile(embed_per_million_usd=0.10)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_embeddings=True, supports_system_prompt=False, max_context_tokens=8191
        )


class OpenAICompatibleLLMProvider(LLMProvider):
    """
    Generic OpenAI-compatible chat provider — one adapter, base-url configurable.

    Covers OpenRouter, Together, Groq, DeepSeek, vLLM, LM Studio and local
    llama.cpp servers. Locality is DECLARED by the caller (`is_local`), default
    False (fail-closed): a self-hosted endpoint on localhost should pass
    is_local=True so the policy gate treats it as on-host.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        *,
        label: str = "openai_compatible",
        is_local: bool = False,
    ):
        self.base_url = base_url or Config.OPENAI_COMPATIBLE_BASE_URL
        # Many local servers ignore the key; use a placeholder so the SDK is happy.
        self.api_key = api_key or Config.OPENAI_COMPATIBLE_API_KEY or "not-needed"
        self.model = model or Config.OPENAI_COMPATIBLE_MODEL
        self.label = label
        self._declared_local = is_local

        if not self.base_url:
            raise ValueError(
                "base_url required for an OpenAI-compatible provider. Set "
                "OPENAI_COMPATIBLE_BASE_URL (e.g. https://openrouter.ai/api/v1)."
            )
        if not self.model:
            raise ValueError(
                "model required for an OpenAI-compatible provider. Set "
                "OPENAI_COMPATIBLE_MODEL."
            )

        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            except ImportError:
                raise ImportError(
                    "OpenAI SDK not installed. Install with:\n"
                    "pip install openai"
                )
        return self._client

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        messages = [{"role": "user", "content": prompt}]
        return self.generate_with_messages(messages, max_tokens, temperature, **kwargs)

    def generate_with_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        client = self._get_client()
        max_tokens = max_tokens or 1024

        max_retries = 3
        base_delay = 1.0
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    **kwargs,
                )
                return response.choices[0].message.content
            except Exception as e:
                error_str = str(e).lower()
                if "rate" in error_str or "429" in error_str or "5" in error_str[:3]:
                    if attempt < max_retries - 1:
                        time.sleep(base_delay * (2**attempt))
                        continue
                    raise ValueError(f"API error after {max_retries} retries: {e}")
                raise

        raise ValueError("Max retries exceeded")

    def get_model_name(self) -> str:
        return self.model

    def is_available(self) -> bool:
        try:
            self._get_client()
            return True
        except Exception:
            return False

    def get_privacy_profile(self) -> ProviderPrivacyProfile:
        return ProviderPrivacyProfile(
            provider_label=self.label,
            is_local=self._declared_local,
            sends_data_offhost=not self._declared_local,
            data_region="on-host" if self._declared_local else "external",
        )

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True, supports_system_prompt=True, supports_tools=False
        )
