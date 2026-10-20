"""Fallback coordinator for the Universal AI Gateway.

Manages fallback chains on provider failures with:
- Failure classification (rate limit, transient, auth, unsupported, validation)
- Per-request attempt tracking
- Controlled fallback execution
- Cancellation support
- No infinite retry loops
"""

from __future__ import annotations

from collections import defaultdict
from enum import Enum
from threading import Lock
from typing import Dict, List, Optional, Tuple
import time
import asyncio


class FallbackStatus(Enum):
    """Status of fallback attempts."""
    CONTINUE = "CONTINUE"     # Try next in chain
    STOP = "STOP"             # Stop fallback, use last result
    CANCELLED = "CANCELLED"   # User cancelled, no more fallbacks


class FallbackCoordinator:
    """Coordinates fallback chains on provider failures.

    Responsibilities:
    - Classify failures into categories
    - Manage fallback candidate ordering
    - Track attempt history for audit
    - Support cancellation propagation
    - Prevent fallback loops
    """

    def __init__(self):
        self._fallback_chains: Dict[str, List[str]] = defaultdict(list)  # provider -> [fallback_providers]
        self._attempt_history: List[dict] = []
        self._lock = Lock()
        self._cancelled: bool = False

    def add_fallback(self, provider_id: str, fallback_providers: List[str]) -> None:
        """Add fallback providers for a given primary provider."""
        with self._lock:
            self._fallback_chains[provider_id] = fallback_providers

    def set_cancel(self) -> None:
        """Signal that fallback should be cancelled."""
        with self._lock:
            self._cancelled = True

    def is_cancelled(self) -> bool:
        """Check if fallback has been cancelled."""
        with self._lock:
            return self._cancelled

    def classify_failure(self, error: Exception) -> str:
        """Classify an error into a fallback category.

        Returns one of:
        - 'rate_limit'
        - 'transient'
        - 'authentication'
        - 'unsupported_capability'
        - 'validation_failure'
        - 'budget_exhausted'
        """
        error_str = str(error).lower()

        if "rate limit" in error_str or "429" in error_str:
            return "rate_limit"
        elif ("timeout" in error_str or "connection" in error_str
              or "network" in error_str):
            return "transient"
        elif ("authentication" in error_str or "invalid" in error_str
              or "401" in error_str or "403" in error_str):
            return "authentication"
        elif ("unsupported" in error_str or "not supported" in error_str):
            return "unsupported_capability"
        elif ("validation" in error_str or "schema" in error_str
              or "malformed" in error_str):
            return "validation_failure"
        elif ("budget" in error_str or "exhausted" in error_str
              or "insufficient" in error_str):
            return "budget_exhausted"

        return "unknown"

    def should_fallback(self, error: Exception, current_attempt: int,
                        max_attempts: int, fallback_chain: List[str]) -> Tuple[bool, Optional[str]]:
        """Determine if fallback should be attempted.

        Returns (should_fallback, next_provider_or_None).
        """
        with self._lock:
            # Check cancellation
            if self._cancelled:
                return False, None

            # Check max attempts
            if current_attempt >= max_attempts:
                return False, None

            # Check failure class
            failure_class = self.classify_failure(error)

            # Rate limits: immediate fallback
            if failure_class == "rate_limit":
                # Get next provider in chain
                if fallback_chain:
                    next_provider = fallback_chain[0]
                    # Return the fallback and remove it from the chain
                    remaining = fallback_chain[1:]
                    # Store updated chain
                    self._fallback_chains[fallback_chain[0] if fallback_chain else ""] = remaining
                    return True, next_provider
                return False, None

            # Transient errors: fallback after brief consideration
            if failure_class == "transient":
                if fallback_chain:
                    next_provider = fallback_chain[0]
                    remaining = fallback_chain[1:]
                    self._fallback_chains[fallback_chain[0] if fallback_chain else ""] = remaining
                    return True, next_provider
                return False, None

            # Authentication: do NOT fallback; report config error
            if failure_class == "authentication":
                return False, None

            # Unsupported capability: try next model, not provider switch
            if failure_class == "unsupported_capability":
                return False, None

            # Budget exhausted: stop
            if failure_class == "budget_exhausted":
                return False, None

            # Unknown: stop
            return False, None

    def record_attempt(self, request_id: str, provider: str, model: str,
                       status: str, latency: int, error: Optional[str] = None) -> None:
        """Record an attempt in the history."""
        with self._lock:
            self._attempt_history.append({
                "request_id": request_id,
                "provider": provider,
                "model": model,
                "status": status,
                "latency_ms": latency,
                "error": error,
                "timestamp": time.monotonic(),
            })

    def get_attempt_history(self, request_id: str) -> List[dict]:
        """Get attempt history for a specific request."""
        with self._lock:
            return [a for a in self._attempt_history if a["request_id"] == request_id]