"""Cache-then-guard-then-call, shared by every step that makes structured model calls."""
from __future__ import annotations

from pydantic import BaseModel

from engine.narration.cache import ArtifactCache, cache_key
from engine.narration.runtime.client import ModelClient, guard_prompt


async def cached_call(client: ModelClient, cache: ArtifactCache, role: str, step: str, sha: str,
                      text: str, schema: type[BaseModel]):
    key = cache_key(step, {"prompt": text}, sha, client.model_for(role), client.params_for(role))
    hit = cache.get(step, key, schema)
    if hit is not None:
        return hit
    guard_prompt(client, role, text)
    out = await client.structured(role, text, schema)
    cache.put(step, key, out)
    return out