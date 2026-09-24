"""
Provider profiles — capability, cost, and privacy metadata.

These are plain, dependency-free dataclasses so that importing them (and the
provider ABCs that expose them) never pulls a cloud SDK. The PolicyEngine and
the router read `ProviderPrivacyProfile.is_local` to decide, fail-closed,
whether an outbound call is allowed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ProviderCapabilities:
    """What a provider can do (used by the router / UI, not security-critical)."""

    supports_streaming: bool = False
    supports_system_prompt: bool = True
    supports_embeddings: bool = False
    supports_tools: bool = False
    max_context_tokens: int = 8192


@dataclass(frozen=True)
class ProviderCostProfile:
    """Rough cost signal in USD per 1M tokens. 0.0 everywhere => local/free."""

    input_per_million_usd: float = 0.0
    output_per_million_usd: float = 0.0
    embed_per_million_usd: float = 0.0

    @property
    def is_free(self) -> bool:
        return (
            self.input_per_million_usd == 0.0
            and self.output_per_million_usd == 0.0
            and self.embed_per_million_usd == 0.0
        )


@dataclass(frozen=True)
class ProviderPrivacyProfile:
    """
    The security-critical profile. `is_local` is the single fact the policy
    gate keys on: True means the call stays on this host / self-hosted runtime
    with no third-party egress. Defaults are conservative (cloud) so an
    unclassified provider is treated as external — fail-closed.
    """

    provider_label: str
    is_local: bool = False
    sends_data_offhost: bool = True
    data_region: str = "unknown"


@dataclass
class ProviderHealth:
    """Result of a real reachability probe (used by /providers/health)."""

    provider_label: str
    available: bool
    latency_ms: Optional[float] = None
    detail: str = ""
