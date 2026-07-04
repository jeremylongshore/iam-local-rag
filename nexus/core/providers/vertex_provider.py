"""
Google Vertex AI provider implementation using official SDK.
"""
import time
from typing import Dict, List, Optional

from ..config import Config
from .base import EmbeddingProvider, LLMProvider
from .profiles import ProviderCapabilities, ProviderCostProfile, ProviderPrivacyProfile


class VertexLLMProvider(LLMProvider):
    """
    Vertex AI Gemini LLM provider using official Google Cloud SDK.
    Supports Gemini 1.5 Pro and other Vertex AI models.
    """

    def __init__(self, project: Optional[str] = None, region: Optional[str] = None, model: Optional[str] = None):
        self.project = project or Config.GOOGLE_CLOUD_PROJECT
        self.region = region or Config.GOOGLE_CLOUD_REGION
        self.model = model or Config.VERTEX_MODEL

        if not self.project:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT required. Set it in .env file:\n"
                "GOOGLE_CLOUD_PROJECT=your-project-id"
            )

        self._client = None
        self._model_instance = None

    def _get_client(self):
        """Lazy initialization of Vertex AI client"""
        if self._client is None:
            try:
                from google.cloud import aiplatform
                aiplatform.init(project=self.project, location=self.region)
                self._client = aiplatform
            except ImportError:
                raise ImportError(
                    "Google Cloud AI Platform SDK not installed. Install with:\n"
                    "pip install google-cloud-aiplatform"
                )
        return self._client

    def _get_model(self):
        """Lazy initialization of Gemini model"""
        if self._model_instance is None:
            try:
                from vertexai.generative_models import GenerativeModel
                self._model_instance = GenerativeModel(self.model)
            except ImportError:
                raise ImportError(
                    "Vertex AI SDK not installed. Install with:\n"
                    "pip install google-cloud-aiplatform"
                )
        return self._model_instance

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """
        Generate text from prompt using Gemini.

        Args:
            prompt: The input prompt
            max_tokens: Maximum tokens to generate (default: 1024)
            temperature: Sampling temperature (0.0 to 2.0)
            **kwargs: Additional parameters

        Returns:
            Generated text response
        """
        max_tokens = max_tokens or 1024

        # Convert single prompt to messages format
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
        Generate text from messages using Gemini.

        Args:
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum tokens to generate (default: 1024)
            temperature: Sampling temperature
            **kwargs: Additional parameters (system, top_p, top_k, etc.)

        Returns:
            Generated text response
        """
        max_tokens = max_tokens or 1024

        # Initialize client and model
        self._get_client()
        model = self._get_model()

        # Convert messages to Gemini format
        # Extract system instruction if present
        system_instruction = None
        content_parts = []

        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            elif msg["role"] == "user":
                content_parts.append(msg["content"])
            elif msg["role"] == "assistant":
                # Gemini doesn't support assistant messages in the same way
                # Append as context
                content_parts.append(f"Assistant: {msg['content']}")

        # Combine all content
        combined_content = "\n\n".join(content_parts)

        # Configure generation
        from vertexai.generative_models import GenerationConfig
        generation_config = GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
            top_p=kwargs.get("top_p", 0.95),
            top_k=kwargs.get("top_k", 40)
        )

        # Retry logic for rate limits and transient errors
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries):
            try:
                # Generate content
                if system_instruction:
                    # Recreate model with system instruction
                    from vertexai.generative_models import GenerativeModel
                    model_with_system = GenerativeModel(
                        self.model,
                        system_instruction=system_instruction
                    )
                    response = model_with_system.generate_content(
                        combined_content,
                        generation_config=generation_config
                    )
                else:
                    response = model.generate_content(
                        combined_content,
                        generation_config=generation_config
                    )

                # Extract text from response
                return response.text

            except Exception as e:
                error_str = str(e).lower()

                # Check for rate limit or server errors
                if '429' in error_str or 'rate' in error_str or 'quota' in error_str:
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
        if not self.project:
            return False

        try:
            # Try to initialize client
            self._get_client()
            return True
        except Exception:
            return False

    def get_privacy_profile(self) -> ProviderPrivacyProfile:
        return ProviderPrivacyProfile(
            provider_label="vertex",
            is_local=False,
            sends_data_offhost=True,
            data_region=f"gcp:{self.region}",
        )

    def get_cost_profile(self) -> ProviderCostProfile:
        # Approximate Gemini 1.5 Pro pricing (USD / 1M tokens).
        return ProviderCostProfile(input_per_million_usd=3.5, output_per_million_usd=10.5)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_system_prompt=True,
            supports_tools=True,
            max_context_tokens=1000000,
        )


class VertexEmbeddingProvider(EmbeddingProvider):
    """
    Vertex AI embeddings provider using official SDK.
    Uses textembedding-gecko model.
    """

    def __init__(self, project: Optional[str] = None, region: Optional[str] = None, model: str = "textembedding-gecko@003"):
        self.project = project or Config.GOOGLE_CLOUD_PROJECT
        self.region = region or Config.GOOGLE_CLOUD_REGION
        self.model = model

        if not self.project:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT required. Set it in .env file:\n"
                "GOOGLE_CLOUD_PROJECT=your-project-id"
            )

        self._client = None

    def _get_client(self):
        """Lazy initialization of Vertex AI client"""
        if self._client is None:
            try:
                from google.cloud import aiplatform
                aiplatform.init(project=self.project, location=self.region)
                self._client = aiplatform
            except ImportError:
                raise ImportError(
                    "Google Cloud AI Platform SDK not installed. Install with:\n"
                    "pip install google-cloud-aiplatform"
                )
        return self._client

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for documents using Vertex AI.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors (768-dimensional)
        """
        self._get_client()

        from vertexai.language_models import TextEmbeddingModel

        # Initialize embedding model
        model = TextEmbeddingModel.from_pretrained(self.model)

        # Vertex AI has a batch size limit, process in chunks
        batch_size = 250  # Vertex AI limit is typically 250
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            # Retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Get embeddings for batch
                    embeddings = model.get_embeddings(batch)

                    # Extract values
                    batch_embeddings = [emb.values for emb in embeddings]
                    all_embeddings.extend(batch_embeddings)
                    break

                except Exception as e:
                    error_str = str(e).lower()
                    if '429' in error_str or 'rate' in error_str or 'quota' in error_str:
                        if attempt < max_retries - 1:
                            time.sleep(1.0 * (2 ** attempt))
                            continue
                        else:
                            raise ValueError(f"Rate limit exceeded after {max_retries} retries")
                    else:
                        raise

        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        """
        Generate embedding for a single query.

        Args:
            text: Query text to embed

        Returns:
            Embedding vector (768-dimensional)
        """
        return self.embed_documents([text])[0]

    def get_embedding_dimension(self) -> int:
        """Return embedding dimension for textembedding-gecko"""
        return 768  # textembedding-gecko

    def is_available(self) -> bool:
        """Check if the provider is configured and accessible"""
        if not self.project:
            return False

        try:
            # Try to initialize client
            self._get_client()
            return True
        except Exception:
            return False

    def get_privacy_profile(self) -> ProviderPrivacyProfile:
        return ProviderPrivacyProfile(
            provider_label="vertex",
            is_local=False,
            sends_data_offhost=True,
            data_region=f"gcp:{self.region}",
        )

    def get_cost_profile(self) -> ProviderCostProfile:
        return ProviderCostProfile(embed_per_million_usd=0.10)

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_embeddings=True, supports_system_prompt=False, max_context_tokens=3072
        )
