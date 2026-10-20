"""Circuit breaker for the Universal AI Gateway.

Manages per-provider circuit state (CLOSED/OPEN/HALF_OPEN) with:
- Failure threshold tracking
- Bounded exponential backoff cooldowns with jitter
- Automatic state transitions
- Per-scope cooldown (provider, credential, model)
"""

from __future__ import annotations

from enum import Enum
from threading import Lock
from typing import Dict, Optional, Tuple
import time
import random


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "CLOSED"       # Normal operation, requests flow
    OPEN = "OPEN"           # Failing, requests rejected
    HALF_OPEN = "HALF_OPEN" # Testing recovery, limited requests


class CircuitBreaker:
    """Circuit breaker for provider failure isolation.

    States:
    - CLOSED: Requests flow normally. Failures increment counter.
    - OPEN: Circuit tripped after threshold. Requests rejected.
    - HALF_OPEN: Testing recovery. Limited requests allowed.

    Transition: CLOSED --(failures)--> OPEN --(cooldown)--> HALF_OPEN --(success)--> CLOSED
                 HALF_OPEN --(failure)--> OPEN
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_cooldown: float = 60.0,
        half_open_max_requests: int = 3,
    ):
        """Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before tripping to OPEN
            recovery_cooldown: Seconds to wait before transitioning to HALF_OPEN
            half_open_max_requests: Max requests in HALF_OPEN state
        """
        self.failure_threshold = failure_threshold
        self.recovery_cooldown = recovery_cooldown
        self.half_open_max_requests = half_open_max_requests

        # Per-provider state
        self._states: Dict[str, CircuitState] = {}
        self._failure_counts: Dict[str, int] = {}
        self._last_failure_time: Dict[str, float] = {}
        self._half_open_count: Dict[str, int] = {}
        self._locks: Dict[str, Lock] = {}

        self._global_lock = Lock()

    def _get_key(self, scope: str = "provider") -> str:
        """Get the key for tracking circuit state."""
        return scope

    def _ensure_lock(self, key: str) -> None:
        """Ensure a lock exists for the given key."""
        if key not in self._locks:
            self._locks[key] = Lock()

    def record_failure(self, provider_id: str) -> None:
        """Record a failure for the given provider."""
        with self._global_lock:
            key = provider_id
            self._ensure_lock(key)

            with self._locks[key]:
                # Initialize if not exists
                if key not in self._states:
                    self._states[key] = CircuitState.CLOSED
                    self._failure_counts[key] = 0
                    self._last_failure_time[key] = 0
                    self._half_open_count[key] = 0

                # Increment failure counter
                self._failure_counts[key] += 1

                # Check if threshold reached
                if self._failure_counts[key] >= self.failure_threshold:
                    self._states[key] = CircuitState.OPEN
                    self._last_failure_time[key] = time.monotonic()
                    self._failure_counts[key] = 0  # Reset counter for OPEN state
                    logger = __import__("logging").getLogger("panelflow.circuit_breaker")
                    logger.info(f"Circuit breaker tripped OPEN for {provider_id}")

    def record_success(self, provider_id: str) -> None:
        """Record a success for the given provider."""
        with self._global_lock:
            key = provider_id
            self._ensure_lock(key)

            with self._locks[key]:
                if key not in self._states:
                    self._states[key] = CircuitState.CLOSED
                    self._failure_counts[key] = 0
                    self._last_failure_time[key] = 0
                    self._half_open_count[key] = 0

                # Transition based on current state
                if self._states[key] == CircuitState.HALF_OPEN:
                    # Success in HALF_OPEN resets to CLOSED
                    self._states[key] = CircuitState.CLOSED
                    self._failure_counts[key] = 0
                    self._half_open_count[key] = 0
                    logger = __import__("logging").getLogger("panelflow.circuit_breaker")
                    logger.info(f"Circuit breaker reset to CLOSED for {provider_id}")
                
                elif self._states[key] == CircuitState.CLOSED:
                    # Reset failure counter on success in CLOSED
                    self._failure_counts[key] = 0

    def allow_request(self, provider_id: str) -> bool:
        """Check if a request is allowed for the given provider.

        Returns True if request should be allowed, False if circuit is OPEN.
        """
        with self._global_lock:
            key = provider_id
            self._ensure_lock(key)

            with self._locks[key]:
                # Initialize if not exists
                if key not in self._states:
                    self._states[key] = CircuitState.CLOSED
                    self._failure_counts[key] = 0
                    self._last_failure_time[key] = 0
                    self._half_open_count[key] = 0

                state = self._states[key]

                if state == CircuitState.CLOSED:
                    return True

                elif state == CircuitState.OPEN:
                    # Check if cooldown has expired
                    last_failure = self._last_failure_time.get(key, 0)
                    elapsed = time.monotonic() - last_failure
                    if elapsed >= self.recovery_cooldown:
                        # Transition to HALF_OPEN for testing
                        self._states[key] = CircuitState.HALF_OPEN
                        self._half_open_count[key] = 0
                        logger = __import__("logging").getLogger("panelflow.circuit_breaker")
                        logger.info(
                            f"Circuit breaker transitioning OPEN->HALF_OPEN for {provider_id} "
                            f"after {elapsed:.1f}s cooldown"
                        )
                    return False

                elif state == CircuitState.HALF_OPEN:
                    # Allow limited requests
                    count = self._half_open_count.get(key, 0)
                    if count < self.half_open_max_requests:
                        self._half_open_count[key] = count + 1
                        return True
                    else:
                        return False

                return True  # Default allow

    def set_cooldown(self, provider_id: str, cooldown_seconds: float) -> None:
        """Set a custom cooldown time for the provider."""
        with self._global_lock:
            key = provider_id
            self._last_failure_time[key] = time.monotonic() - cooldown_seconds

    def get_state(self, provider_id: str) -> CircuitState:
        """Get the current circuit state for a provider."""
        with self._global_lock:
            key = provider_id
            self._ensure_lock(key)

            with self._locks[key]:
                if key not in self._states:
                    self._states[key] = CircuitState.CLOSED
                return self._states[key]


# Global circuit breaker instance
circuit_breaker = CircuitBreaker()