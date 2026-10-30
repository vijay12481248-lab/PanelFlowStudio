"""Model-grouped scheduler: one heavy model loaded at a time, bounded concurrency, OOM retry."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Sequence, TypeVar

import httpx

from engine.narration.runtime.roles import RoleConfig

log = logging.getLogger(__name__)
T = TypeVar("T")
R = TypeVar("R")
_OOM = object()


def _is_oom(exc: BaseException) -> bool:
    return "out of memory" in str(exc).lower()


class ModelScheduler:
    def __init__(self, roles: dict[str, RoleConfig], unload: Callable[[str], Awaitable[None]]):
        self.roles = roles
        self._unload = unload
        self._loaded: str | None = None

    def concurrency(self, role: str) -> int:
        return self.roles[role].concurrency

    async def release(self) -> None:
        if self._loaded is not None:
            await self._unload(self._loaded)
            self._loaded = None

    async def _pass(self, items, fn, limit: int) -> list:
        sem = asyncio.Semaphore(limit)

        async def one(item):
            async with sem:
                try:
                    return await fn(item)
                except Exception as exc:  # non-OOM errors propagate immediately
                    if _is_oom(exc):
                        return _OOM
                    raise

        return list(await asyncio.gather(*(one(i) for i in items)))

    async def map(self, role: str, items: Sequence[T], fn: Callable[[T], Awaitable[R]]) -> list[R]:
        cfg = self.roles[role]
        if self._loaded != cfg.model:
            await self.release()
            self._loaded = cfg.model
        results = await self._pass(items, fn, cfg.concurrency)
        failed = [i for i, r in enumerate(results) if r is _OOM]
        if failed:
            await self._unload(cfg.model)
            retried = await self._pass([items[i] for i in failed], fn, max(1, cfg.concurrency // 2))
            for i, r in zip(failed, retried):
                if r is _OOM:  # second OOM propagates
                    raise RuntimeError(f"out of memory on model {cfg.model} after retry")
                results[i] = r
        return results


def ollama_unloader(endpoint_url: str = "http://127.0.0.1:11434") -> Callable[[str], Awaitable[None]]:
    async def unload(model: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                await client.post(f"{endpoint_url}/api/generate", json={"model": model, "keep_alive": 0})
        except Exception as exc:
            log.warning("failed to unload %s: %s", model, exc)

    return unload