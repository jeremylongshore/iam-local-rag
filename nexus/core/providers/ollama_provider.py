"""
Ollama provider implementation for local LLM and embeddings.
"""
from typing import Dict, List, Optional

from langchain_ollama import OllamaEmbeddings, OllamaLLM

from ..config import Config
from .base import EmbeddingProvider, LLMProvider
from .profiles import ProviderCapabilities, ProviderCostProfile, ProviderPrivacyProfile


def _ollama_reachable(base_url: str) -> bool:
    """Light reachability probe — list local models, no generation."""
    try:
        from ollama import Client

        Client(host=base_url).list()
        return True
    except Exception:
        return False


class OllamaLLMProvider(LLMProvider):
    """Ollama LLM provider using LangChain"""

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None):
        self.model = model or Config.OLLAMA_MODEL
        self.base_url = base_url or Config.OLLAMA_BASE_URL
        self._llm = None

    def _get_llm(self, temperature: float = 0.7, num_predict: Optional[int] = None):
        """
        Build an OllamaLLM. In langchain-ollama, sampling params (temperature,
        num_predict) are MODEL fields, not invoke() kwargs, so we bind them here.
        """
        params = {"model": self.model, "base_url": self.base_url, "temperature": temperature}
        if num_predict:
            params["num_predict"] = num_predict
        return OllamaLLM(**params)

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """Generate text from prompt"""
        llm = self._get_llm(temperature=temperature, num_predict=max_tokens)
        return llm.invoke(prompt)

    def generate_with_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """Generate from messages (convert to single prompt for Ollama)"""
        # Convert messages to single prompt
        prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
        return self.generate(prompt, max_tokens, temperature, **kwargs)

    def get_model_name(self) -> str:
        """Return model identifier"""
        return self.model

    def is_available(self) -> bool:
        """Check if the Ollama server is reachable (no generation)."""
        return _ollama_reachable(self.base_url)

    def get_privacy_profile(self) -> ProviderPrivacyProfile:
        return ProviderPrivacyProfile(
            provider_label="ollama",
            is_local=True,
            sends_data_offhost=False,
            data_region="on-host",
        )

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_system_prompt=True,
            supports_embeddings=False,
            max_context_tokens=8192,
        )

    def get_cost_profile(self) -> ProviderCostProfile:
        return ProviderCostProfile()  # local => free


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Ollama embedding provider using LangChain"""

    def __init__(self, model: Optional[str] = None, base_url: Optional[str] = None):
        # Dedicated embedding model (NOT the generation model).
        self.model = model or Config.OLLAMA_EMBED_MODEL
        self.base_url = base_url or Config.OLLAMA_BASE_URL
        self._embeddings = None

    def _get_embeddings(self):
        """Lazy initialization of Ollama embeddings"""
        if self._embeddings is None:
            self._embeddings = OllamaEmbeddings(
                model=self.model,
                base_url=self.base_url
            )
        return self._embeddings

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for documents"""
        embeddings = self._get_embeddings()
        return embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        """Generate embedding for query"""
        embeddings = self._get_embeddings()
        return embeddings.embed_query(text)

    def get_embedding_dimension(self) -> int:
        """Best-effort embedding dimension (varies by model)."""
        # Substring match so prefixed/tagged names (e.g. library/nomic-embed-text:latest)
        # still resolve. nomic-embed-text=768, all-minilm=384, mxbai-embed-large=1024.
        model = self.model.lower()
        for name, dim in (("nomic-embed-text", 768), ("all-minilm", 384), ("mxbai-embed-large", 1024)):
            if name in model:
                return dim
        return 768

    def is_available(self) -> bool:
        """Check if the Ollama server is reachable (no embedding call)."""
        return _ollama_reachable(self.base_url)

    def get_privacy_profile(self) -> ProviderPrivacyProfile:
        return ProviderPrivacyProfile(
            provider_label="ollama",
            is_local=True,
            sends_data_offhost=False,
            data_region="on-host",
        )

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(supports_embeddings=True, supports_system_prompt=False)

    def get_cost_profile(self) -> ProviderCostProfile:
        return ProviderCostProfile()  # local => free
