"""Schema-constrained model client: role params, bounded retries, no fallback text."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from engine.llm.providers.base import LLMProvider
from engine.narration.runtime.roles import RoleConfig

T = TypeVar("T", bound=BaseModel)
_TRANSIENT = (TimeoutError, httpx.HTTPError, ConnectionError)


class StepModelError(RuntimeError):
    def __init__(self, role: str, cause: BaseException | str):
        super().__init__(f"model call failed for role '{role}': {cause}")
        self.role = role
        self.cause = cause


class ModelClient(Protocol):
    def model_for(self, role: str) -> str: ...

    def params_for(self, role: str) -> dict: ...

    async def structured(
        self, role: str, prompt: str, schema: type[T],
        image: Path | None = None, system: str | None = None,
    ) -> T: ...


class ProviderModelClient:
    def __init__(self, provider: LLMProvider, roles: dict[str, RoleConfig],
                 backoff_s: tuple[float, ...] = (2.0, 4.0)):
        self._provider = provider
        self._roles = roles
        self._backoff_s = backoff_s

    def model_for(self, role: str) -> str:
        return self._roles[role].model

    def params_for(self, role: str) -> dict:
        r = self._roles[role]
        return {"temperature": r.temperature, "top_p": r.top_p,
                "max_tokens": r.max_tokens, "num_ctx": r.num_ctx}

    async def _with_backoff(self, role: str, call: Callable[[], Awaitable]):
        timeout = self._roles[role].timeout_s
        for delay in (*self._backoff_s, None):
            try:
                return await asyncio.wait_for(call(), timeout)
            except _TRANSIENT as e:
                if delay is None:
                    raise StepModelError(role, e) from e
                await asyncio.sleep(delay)

    async def structured(self, role, prompt, schema, image=None, system=None):
        cfg = self._roles[role]
        if image is None:
            try:
                return await self._with_backoff(role, lambda: self._provider.generate_structured(
                    prompt, schema, system_prompt=system, temperature=cfg.temperature,
                    max_repair_retries=1, model=cfg.model, max_tokens=cfg.max_tokens,
                    num_ctx=cfg.num_ctx))
            except ValueError as e:  # provider exhausted its own repair retry
                raise StepModelError(role, e) from e

        current = prompt
        for attempt in range(2):
            text = await self._with_backoff(role, lambda: self._provider.analyze_vision(
                image, current, system_prompt=system, model=cfg.model,
                max_tokens=cfg.max_tokens, format_schema=schema.model_json_schema()))
            try:
                return schema.model_validate_json(text)
            except ValidationError as e:
                if attempt == 1:
                    raise StepModelError(role, e) from e
                current = (f"{prompt}\n\nYour previous reply failed validation: "
                           f"{str(e)[:600]}. Reply with corrected JSON only.")
