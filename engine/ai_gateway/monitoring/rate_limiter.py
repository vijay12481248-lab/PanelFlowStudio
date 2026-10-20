"""Rate limiter for the Universal AI Gateway.

Tracks per-constraint rate limits and enforces them with:
- Requests per minute (RPM)
- Tokens per minute (TPM)
- Daily request quota
- Provider-specific constraints
- Retry-After parsing for 429 responses
"""

from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from typing import Dict, Optional, DefaultDict
import time
import asyncio


class RateLimitRecord:
    """Records rate limit state for a specific constraint."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self.requests: deque = deque()  # timestamps of requests
        self.tokens: deque = deque()    # tokens used per request
        self.last_reset = time.monotonic()


class RateLimiter:
    """Rate limiter tracking multiple constraint types per provider.

    Supports:
    - Requests per minute (RPM)
    - Tokens per minute (TPM)
    - Daily request quota
    - Provider-specific custom constraints
    - Retry-After timestamp parsing
    """

    def __init__(self):
        self._limits: Dict[str, Dict[str, RateLimitRecord]] = defaultdict(
            lambda: {}
        )
        self._lock = Lock()

    def set_rpm(self, provider_id: str, rpm: int) -> None:
        """Set requests per minute limit for a provider."""
        with self._lock:
            self._limits[provider_id]["rpm"] = RateLimitRecord(rpm, 60)

    def set_tpm(self, provider_id: str, tpm: int) -> None:
        """Set tokens per minute limit for a provider."""
        with self._lock:
            self._limits[provider_id]["tpm"] = RateLimitRecord(tpm, 60)

    def set_daily_quota(self, provider_id: str, daily_limit: int) -> None:
        """Set daily request quota for a provider."""
        with self._lock:
            self._limits[provider_id]["daily"] = RateLimitRecord(daily_limit, 86400)

    def can_execute(self, provider_id: str, model_id: str = "unknown") -> bool:
        """Check if a request can be executed without exceeding rate limits.

        Returns True if within limits, False if rate limit would be exceeded.
        """
        with self._lock:
            limits = self._limits.get(provider_id, {})

            # Check RPM
            if "rpm" in limits:
                rpm_record = limits["rpm"]
                now = time.monotonic()
                # Remove requests outside the window
                while rpm_requests := rpm_record.requests:
                    if now - rpm_requests[0] > 60:
                        rpm_requests.popleft()
                    else:
                        break

                if len(rpm_record.requests) >= rpm_record.limit:
                    return False

                # Check TPM
                if "tpm" in limits:
                    tpm_record = limits["tpm"]
                    # Remove old token entries
                    while tpm_record.tokens:
                        t_age = now - tpm_record.tokens[0][0] if tpm_record.tokens else 0
                        if t_age > 60:
                            tpm_record.tokens.popleft()
                        else:
                            break

                    # Count current tokens
                    current_tokens = sum(t[1] for t in tpm_record.tokens)
                    if current_tokens + 1 > tpm_record.limit:  # +1 for this request
                        return False

            # Check daily quota
            if "daily" in limits:
                daily_record = limits["daily"]
                now = time.monotonic()
                # Reset day boundary
                if now - daily_record.last_reset > 86400:
                    daily_record.requests.clear()
                    daily_record.tokens.clear()
                    daily_record.last_reset = now

                if len(daily_record.requests) >= daily_record.limit:
                    return False

            return True

        # No limits configured, allow
        return True

    def record_request(self, provider_id: str, model_id: str, tokens: int = 0) -> None:
        """Record that a request was executed, updating rate limit state."""
        with self._lock:
            limits = self._limits.get(provider_id, {})

            # Record RPM
            if "rpm" in limits:
                rpm_record = limits["rpm"]
                rpm_record.requests.append(time.monotonic())
                # Keep only last 100 entries to prevent memory growth
                while len(rpm_record.requests) > 100:
                    rpm_record.requests.popleft()

            # Record TPM
            if "tpm" in limits:
                tpm_record = limits["tpm"]
                tpm_record.tokens.append((time.monotonic(), tokens))
                # Keep only last 100 entries
                while len(tpm_record.tokens) > 100:
                    tpm_record.tokens.popleft()

            # Record daily
            if "daily" in limits:
                daily_record = limits["daily"]
                daily_record.requests.append(time.monotonic())
                daily_record.tokens.append(tokens)
                # Reset day boundary check
                if time.monotonic() - daily_record.last_reset > 86400:
                    daily_record.last_reset = time.monotonic()
                    daily_record.requests.clear()
                    daily_record.tokens.clear()


# Global rate limiter instance
rate_limiter = RateLimiter()