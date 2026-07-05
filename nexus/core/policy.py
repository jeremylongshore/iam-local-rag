"""
Policy enforcement for NEXUS outbound calls.

``PolicyEngine`` is the single, mode-aware gate. Every outbound call (LLM *and*
embeddings) passes through ``guard_llm`` / ``guard_embedding``. It is the one
policy gate the acceptance invariants require: LOCAL blocks all external calls
(fail-closed), HYBRID forces local embeddings and refuses payloads carrying
secrets, CLOUD is explicit but still refuses to ship secrets. PII is redacted
from snippets by ``prepare_context`` before they ever reach the gate.

This replaces the old ``PolicyRedactor`` truncate-and-hash helper, which never
redacted PII/secrets, was not mode-aware, and was bypassable.
"""
import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .config import Config, NexusMode
from .models import Citation


@dataclass
class Redaction:
    """A class of PII redacted from outbound context, with a count."""

    kind: str
    count: int


@dataclass
class PolicyDecision:
    """
    The result of inspecting one outbound call. Doubles as the raw material for
    a privacy receipt. Note ``secret_hits`` carries pattern NAMES, never the
    secret values themselves.
    """

    allowed: bool
    mode: str
    kind: str  # "llm" | "embedding"
    provider: str
    is_local: bool
    char_count: int
    token_estimate: int
    reason: str
    model: Optional[str] = None
    chunk_ids: List[str] = field(default_factory=list)
    content_hashes: List[str] = field(default_factory=list)
    redactions: List[Redaction] = field(default_factory=list)
    secret_hits: List[str] = field(default_factory=list)

    def as_receipt(self) -> dict:
        return {
            "policy_pass": self.allowed,
            "mode": self.mode,
            "kind": self.kind,
            "provider": self.provider,
            "model": self.model,
            "destination": "local" if self.is_local else "cloud",
            "chars_out": self.char_count,
            "tokens_out_estimate": self.token_estimate,
            "chunk_ids": self.chunk_ids,
            "content_hashes": self.content_hashes,
            "redactions": [{"kind": r.kind, "count": r.count} for r in self.redactions],
            "secret_patterns_detected": self.secret_hits,
            "reason": self.reason,
        }


@dataclass
class ContextBundle:
    """Redacted, capped, source-attributed context ready for an outbound prompt."""

    safe_context: str
    excerpt_hashes: List[str]
    chunk_ids: List[str]
    redactions: List[Redaction]


class PolicyViolation(Exception):
    """Raised when the PolicyEngine blocks an outbound call. Carries the decision."""

    def __init__(self, decision: PolicyDecision):
        self.decision = decision
        super().__init__(decision.reason)


class PolicyEngine:
    """Mode-aware gate on every outbound LLM and embedding call."""

    # High-confidence secret patterns. A match on any external call is a hard
    # block in every mode — we never intend to ship a live credential.
    _SECRET_PATTERNS = {
        "openai_key": r"sk-[A-Za-z0-9]{20,}",
        "openai_project_key": r"sk-proj-[A-Za-z0-9_\-]{20,}",
        "anthropic_key": r"sk-ant-[A-Za-z0-9_\-]{20,}",
        "aws_access_key": r"\bAKIA[0-9A-Z]{16}\b",
        "google_api_key": r"\bAIza[0-9A-Za-z_\-]{35}\b",
        "github_token": r"\bghp_[A-Za-z0-9]{36}\b",
        "slack_token": r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b",
        "private_key_block": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----",
    }

    # Best-effort PII patterns (v1 heuristics; refined by the eval corpus in P5).
    # These are REDACTED from snippets, not blocked.
    _PII_PATTERNS = {
        "email": r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
        "phone": r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "credit_card": r"\b\d{13,19}\b",
    }

    # High-signal prompt-injection phrases in UNTRUSTED context — neutralized
    # (not blocked) before the context reaches the model, so a weak model is far
    # less likely to obey injected instructions. Defense-in-depth atop the
    # untrusted-data prompt boundary.
    # TIGHT patterns: each matches ONLY the imperative override phrase (no
    # end-of-line consumption), and the role/word variants are gated on a
    # specific cue, so normal prose ("reply with your name", "you are now a
    # member") is NOT scrubbed and adjacent content (incl. secrets) is preserved.
    _INJECTION_PATTERNS = [
        r"(?i)\bignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier|preceding)\s+(?:instructions?|prompts?|directions?|messages?)",
        r"(?i)\bdisregard\s+(?:all\s+|the\s+|any\s+)?(?:previous|prior|above|earlier|foregoing|preceding)\s+(?:instructions?|prompts?|directions?|messages?|context)",
        r"(?i)\bforget\s+(?:everything\s+above|all\s+(?:previous|prior)\s+instructions?|your\s+(?:previous\s+)?instructions?)",
        r"(?i)\byou\s+are\s+now\s+(?:a|an|the)\s+\w+\s+(?:assistant|ai|model|bot|persona|chatbot|system)\b",
        r"(?i)\bnew\s+(?:system\s+)?instructions?\s*:",
        r"(?i)\boverride\s+(?:the\s+)?(?:system|previous|above|earlier)\s+(?:instructions?|prompt|settings?)",
        r"(?i)\b(?:reply|respond|answer|say|output|print)\s+with\s+the\s+(?:word|phrase|string|text)\s+\S+",
    ]

    def __init__(
        self,
        mode=None,
        hybrid_safe_mode: bool = None,
        max_snippet_length: int = None,
    ):
        self.mode: NexusMode = NexusMode(mode) if mode is not None else Config.NEXUS_MODE
        self.hybrid_safe_mode = (
            hybrid_safe_mode if hybrid_safe_mode is not None else Config.HYBRID_SAFE_MODE
        )
        self.max_snippet_length = (
            max_snippet_length if max_snippet_length is not None else Config.MAX_SNIPPET_LENGTH
        )
        self._secret_res = {k: re.compile(v) for k, v in self._SECRET_PATTERNS.items()}
        self._pii_res = {k: re.compile(v) for k, v in self._PII_PATTERNS.items()}
        self._injection_res = [re.compile(p) for p in self._INJECTION_PATTERNS]

    # --- helpers ---

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def scan_secrets(self, text: str) -> List[str]:
        """Return the NAMES (not values) of secret patterns found in text."""
        return [name for name, rx in self._secret_res.items() if rx.search(text)]

    def redact_pii(self, text: str) -> Tuple[str, List[Redaction]]:
        redactions: List[Redaction] = []
        for name, rx in self._pii_res.items():
            text, n = rx.subn(f"[REDACTED:{name}]", text)
            if n:
                redactions.append(Redaction(kind=name, count=n))
        return text, redactions

    def scrub_injection(self, text: str) -> Tuple[str, int]:
        """Neutralize imperative prompt-injection phrases in untrusted context."""
        count = 0
        for rx in self._injection_res:
            text, n = rx.subn("[flagged: possible prompt injection removed]", text)
            count += n
        return text, count

    def prepare_context(self, citations: List[Citation]) -> ContextBundle:
        """
        Build cloud-safe context: hash each full excerpt (pre-redaction, for
        audit), redact PII, cap per-snippet length, add source attribution.
        Secrets are intentionally NOT scrubbed here so the outbound guard can
        detect and hard-block them.
        """
        snippets: List[str] = []
        excerpt_hashes: List[str] = []
        chunk_ids: List[str] = []
        totals: dict = {}

        for i, c in enumerate(citations):
            excerpt = c.excerpt
            excerpt_hashes.append(self._hash(excerpt))
            chunk_ids.append((c.content_hash or "")[:12] or f"chunk-{i}")

            red_excerpt, reds = self.redact_pii(excerpt)
            for r in reds:
                totals[r.kind] = totals.get(r.kind, 0) + r.count

            red_excerpt, inj_n = self.scrub_injection(red_excerpt)
            if inj_n:
                totals["injection"] = totals.get("injection", 0) + inj_n

            if self.hybrid_safe_mode and len(red_excerpt) > self.max_snippet_length:
                red_excerpt = red_excerpt[: self.max_snippet_length] + "..."

            source_info = f"[Source: {c.source}"
            if c.page:
                source_info += f", Page {c.page}"
            source_info += "]"
            snippets.append(f"{source_info}\n{red_excerpt}")

        safe_context = "\n\n---\n\n".join(snippets)
        redactions = [Redaction(kind=k, count=v) for k, v in totals.items()]
        return ContextBundle(safe_context, excerpt_hashes, chunk_ids, redactions)

    def guard(
        self,
        *,
        payload: str,
        provider,
        kind: str,
        model: Optional[str] = None,
        chunk_ids: Optional[List[str]] = None,
        content_hashes: Optional[List[str]] = None,
        redactions: Optional[List[Redaction]] = None,
    ) -> PolicyDecision:
        """Inspect one outbound call and decide allow/block. Never sends anything."""
        prof = provider.get_privacy_profile()
        is_local = prof.is_local
        label = prof.provider_label
        secret_hits = self.scan_secrets(payload)
        char_count = len(payload)
        token_estimate = max(1, char_count // 4)

        allowed = True
        reason = "ok"

        if is_local:
            allowed = True
            reason = "local provider — no third-party egress"
        elif self.mode == NexusMode.LOCAL:
            allowed = False
            reason = f"LOCAL mode forbids the external {kind} call to '{label}'"
        elif self.mode == NexusMode.HYBRID:
            if kind == "embedding":
                allowed = False
                reason = (
                    f"HYBRID mode requires local embeddings; refusing external "
                    f"embedding call to '{label}'"
                )
            elif secret_hits:
                allowed = False
                reason = (
                    f"secret pattern(s) {secret_hits} in outbound payload; refusing "
                    f"external {kind} call to '{label}'"
                )
        elif self.mode == NexusMode.CLOUD:
            if secret_hits:
                allowed = False
                reason = (
                    f"secret pattern(s) {secret_hits} detected; refusing to send "
                    f"secrets even in CLOUD mode"
                )

        return PolicyDecision(
            allowed=allowed,
            mode=self.mode.value,
            kind=kind,
            provider=label,
            is_local=is_local,
            char_count=char_count,
            token_estimate=token_estimate,
            reason=reason,
            model=model,
            chunk_ids=chunk_ids or [],
            content_hashes=content_hashes or [],
            redactions=redactions or [],
            secret_hits=secret_hits,
        )

    def guard_llm(self, payload: str, provider, model: Optional[str] = None, **meta) -> PolicyDecision:
        return self.guard(payload=payload, provider=provider, kind="llm", model=model, **meta)

    def guard_embedding(self, texts, provider, **meta) -> PolicyDecision:
        payload = "\n".join(texts) if isinstance(texts, (list, tuple)) else str(texts)
        return self.guard(payload=payload, provider=provider, kind="embedding", **meta)

    @staticmethod
    def enforce(decision: PolicyDecision) -> PolicyDecision:
        """Raise PolicyViolation if the decision blocked the call; else pass through."""
        if not decision.allowed:
            raise PolicyViolation(decision)
        return decision

    # --- backward-compat surface (pipeline.policy / app_nexus) ---

    def get_policy_summary(self) -> dict:
        return {
            "mode": self.mode.value,
            "hybrid_safe_mode": self.hybrid_safe_mode,
            "max_snippet_length": self.max_snippet_length,
            "policy_enforced": True,
        }
