"""
ReaderRecipe model for cached, self-healing site reader patterns.
Enforces strict secret-safe persistence: cookies, authorization tokens,
session IDs, and private secrets are never permitted in persisted recipes.
"""
from typing import List, Optional, Dict
from datetime import datetime, timezone
from pydantic import BaseModel, Field, field_validator

FORBIDDEN_HEADER_KEYS = {
    "cookie", "set-cookie", "authorization", "proxy-authorization",
    "x-csrf-token", "x-xsrf-token", "token", "session", "session-id",
    "bearer", "api-key", "apikey", "secret"
}

ALLOWED_HEADER_KEYS = {
    "user-agent", "accept", "accept-language", "referer"
}


def sanitize_recipe_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    """
    Sanitizes headers to ensure zero sensitive authentication tokens, cookies,
    or session credentials can ever be persisted into a ReaderRecipe.
    Only harmless configuration headers (User-Agent, Accept, Accept-Language, Referer)
    are permitted.
    """
    if not headers:
        return {}
    clean = {}
    for k, v in headers.items():
        k_lower = k.lower().strip()
        # Strictly reject any forbidden key or key containing secret tokens
        if any(bad in k_lower for bad in FORBIDDEN_HEADER_KEYS):
            continue
        if k_lower in ALLOWED_HEADER_KEYS:
            clean[k] = v
    return clean


class ReaderRecipe(BaseModel):
    domain: str
    chapter_path_pattern: str = "/*"
    preferred_strategy: str = "STATIC_DOM"
    container_signatures: List[str] = Field(default_factory=list)
    image_attributes: List[str] = Field(default_factory=lambda: ["src", "data-src", "data-original"])
    ordering: str = "DOM_ORDER"
    expected_cluster_minimum: int = 3
    known_cdn_patterns: List[str] = Field(default_factory=list)
    headers: Dict[str, str] = Field(default_factory=dict)
    requires_authenticated_session: bool = False
    version: int = 1
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_validated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, v: Dict[str, str]) -> Dict[str, str]:
        return sanitize_recipe_headers(v)

