"""
Base provider interfaces for LLM and Embedding providers.
All providers must implement these abstract base classes.

The concrete `get_*_profile` / `is_local` / `health_check` methods carry
conservative defaults (treat an unclassified provider as external — fail-closed)
so the PolicyEngine can always ask "is this call local?" and get a safe answer.
Cloud SDKs are still imported lazily inside each provider's `_get_client`.
"""
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from .profiles import (
    ProviderCapabilities,
    ProviderCostProfile,
    ProviderHealth,
    ProviderPrivacyProfile,
)


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        """
        Generate text from a prompt.

        Args:
            prompt: The input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)
            **kwargs: Provider-specific parameters

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    def generate_with_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs,
    ) -> str:
        """
        Generate text from a list of messages (chat format).

        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Provider-specific parameters

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model identifier"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and configured"""
        pass

    # --- Profiles (concrete defaults; override per provider) ---

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    def get_cost_profile(self) -> ProviderCostProfile:
        return ProviderCostProfile()

    def get_privacy_profile(self) -> ProviderPrivacyProfile:
        # Conservative default: unclassified provider is treated as external.
        return ProviderPrivacyProfile(provider_label=type(self).__name__, is_local=False)

    @property
    def is_local(self) -> bool:
        """True only when the call stays on-host with no third-party egress."""
        return self.get_privacy_profile().is_local

    def health_check(self) -> ProviderHealth:
        """Real reachability probe, timed. Never raises."""
        label = self.get_privacy_profile().provider_label
        start = time.time()
        try:
            ok = self.is_available()
            return ProviderHealth(
                provider_label=label,
                available=ok,
                latency_ms=(time.time() - start) * 1000,
                detail="ok" if ok else "unavailable",
            )
        except Exception as e:  # pragma: no cover - defensive
            return ProviderHealth(
                provider_label=label,
                available=False,
                latency_ms=(time.time() - start) * 1000,
                detail=f"error: {type(e).__name__}: {e}",
            )


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers"""

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of documents.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        pass

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """
        Generate embedding for a query.

        Args:
            text: Query text to embed

        Returns:
            Embedding vector
        """
        pass

    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """Return the dimension of embeddings produced"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and configured"""
        pass

    # --- Profiles (concrete defaults; override per provider) ---

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_embeddings=True, supports_system_prompt=False)

    def get_cost_profile(self) -> ProviderCostProfile:
        return ProviderCostProfile()

    def get_privacy_profile(self) -> ProviderPrivacyProfile:
        return ProviderPrivacyProfile(provider_label=type(self).__name__, is_local=False)

    @property
    def is_local(self) -> bool:
        return self.get_privacy_profile().is_local

    def health_check(self) -> ProviderHealth:
        label = self.get_privacy_profile().provider_label
        start = time.time()
        try:
            ok = self.is_available()
            return ProviderHealth(
                provider_label=label,
                available=ok,
                latency_ms=(time.time() - start) * 1000,
                detail="ok" if ok else "unavailable",
            )
        except Exception as e:  # pragma: no cover - defensive
            return ProviderHealth(
                provider_label=label,
                available=False,
                latency_ms=(time.time() - start) * 1000,
                detail=f"error: {type(e).__name__}: {e}",
            )
