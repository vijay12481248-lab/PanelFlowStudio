import asyncio
import base64
import hashlib
import ipaddress
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar, Type, Any, Optional, Iterable
from urllib.parse import urlparse
import httpx
from pydantic import BaseModel, ValidationError

from engine.llm.providers.base import LLMProvider, ModelMetadata
from engine.llm.errors import GenerationLimitError

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger("panelflow.llm.ollama")


@dataclass(frozen=True)
class OllamaEndpointAuthorization:
    """Immutable identity for the user-approved remote Ollama IP set."""

    approved_remote_ips: frozenset[str]
    identity: str

    @classmethod
    def create(cls, approved_remote_ips: Iterable[str]) -> "OllamaEndpointAuthorization":
        normalized: set[str] = set()
        for value in approved_remote_ips:
            try:
                ip = ipaddress.ip_address(str(value).strip())
            except ValueError as exc:
                raise ValueError(f"Invalid approved Ollama IP address: {value}") from exc
            if _is_forbidden_remote_ip(ip):
                raise ValueError(f"Approved Ollama IP must be public: {ip}")
            normalized.add(str(ip))
        frozen = frozenset(normalized)
        identity = hashlib.sha256(json.dumps(sorted(frozen), separators=(",", ":")).encode("utf-8")).hexdigest()
        return cls(frozen, identity)


def _authorization_path() -> Path:
    from engine.config.settings import settings

    return settings.app_data_dir / "config" / "ollama_remote_allowlist.json"


def load_ollama_endpoint_authorization() -> OllamaEndpointAuthorization:
    configured: list[str] = []
    path = _authorization_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("approved_remote_ips"), list):
            configured.extend(str(value) for value in data["approved_remote_ips"])
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Persisted Ollama remote allowlist is invalid") from exc
    configured.extend(
        value.strip()
        for value in os.environ.get("PANELFLOW_OLLAMA_REMOTE_ALLOWLIST", "").split(",")
        if value.strip()
    )
    return OllamaEndpointAuthorization.create(configured)


def persist_ollama_endpoint_authorization(authorization: OllamaEndpointAuthorization) -> None:
    path = _authorization_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "approved_remote_ips": sorted(authorization.approved_remote_ips),
                "authorization_identity": authorization.identity,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def _is_forbidden_remote_ip(ip: ipaddress._BaseAddress) -> bool:
    return any(
        (
            ip.is_private,
            ip.is_loopback,
            ip.is_link_local,
            ip.is_multicast,
            ip.is_reserved,
            ip.is_unspecified,
        )
    )


def validate_ollama_endpoint(
    url: str,
    is_remote: bool = False,
    approved_remote_ips: Iterable[str] | None = None,
    authorization: OllamaEndpointAuthorization | None = None,
) -> tuple[bool, str]:
    """Validate an Ollama endpoint without allowing SSRF to internal networks."""
    if not url or not url.strip():
        return False, "Endpoint URL cannot be empty"
    try:
        parsed = urlparse(url.strip())
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except (TypeError, ValueError) as exc:
        return False, f"Invalid URL format: {exc}"

    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported scheme '{parsed.scheme}'. Only http and https are allowed."
    if parsed.username is not None or parsed.password is not None:
        return False, "Endpoint URL must not contain embedded credentials"
    if parsed.params or parsed.query or parsed.fragment:
        return False, "Endpoint URL must be an origin without parameters, query, or fragment"
    hostname = parsed.hostname
    if not hostname:
        return False, "URL hostname is missing"
    hostname_lower = hostname.lower()

    if not is_remote:
        if hostname_lower in ("localhost", "127.0.0.1", "::1"):
            if parsed.path not in ("", "/"):
                return False, "Endpoint URL must not contain a path"
            return True, ""
        try:
            ip = ipaddress.ip_address(hostname_lower)
            if ip.is_loopback:
                if parsed.path not in ("", "/"):
                    return False, "Endpoint URL must not contain a path"
                return True, ""
        except ValueError:
            pass
        return False, f"Local endpoint must be localhost or 127.0.0.1 (got {hostname})"

    if "metadata.google.internal" in hostname_lower or hostname_lower in {"localhost", "0.0.0.0"}:
        return False, f"Remote endpoint cannot target local or cloud metadata hosts ({hostname})"

    try:
        ip = ipaddress.ip_address(hostname_lower)
    except ValueError as exc:
        return False, "Remote Ollama endpoints must use a public IP literal to prevent DNS rebinding"
    if _is_forbidden_remote_ip(ip):
        return False, f"Rejected non-public remote address {ip}"
    try:
        approved = authorization or (
            OllamaEndpointAuthorization.create(approved_remote_ips)
            if approved_remote_ips is not None
            else load_ollama_endpoint_authorization()
        )
    except ValueError as exc:
        return False, str(exc)
    if str(ip) not in approved.approved_remote_ips:
        return False, f"Remote Ollama address {ip} is not explicitly user-approved"
    if parsed.path not in ("", "/"):
        return False, "Endpoint URL must not contain a path"
    return True, ""


class OllamaProvider(LLMProvider):
    """
    Adapter for local or private remote Ollama instance.
    Supports official REST APIs:
      - /api/tags (model discovery)
      - /api/show (deep architectural capability inspection)
      - /api/ps (live VRAM telemetry)
      - /api/generate (text, structured JSON, and vision inference)
    Supports multi-role configuration:
      - Vision Model (e.g. qwen3.5:9b, gemma4)
      - Story Reasoning Model (e.g. qwen3.5:9b, qwen3-coder:30b)
      - Narration Model (e.g. qwen3.5:9b, qwen3.6:latest)
    """

    def __init__(
        self,
        endpoint_url: str = "http://127.0.0.1:11434",
        is_remote: bool = False,
        auth_token: str = "",
        text_model: str = "qwen3.5:9b",
        vision_model: str = "qwen3.5:9b",
        reasoning_model: str = "qwen3.5:9b",
        narration_model: str = "qwen3.5:9b",
        timeout: float = 180.0,
        num_ctx: int = 32768,
        concurrency_mode: str = "MANUAL",
        max_gpu_concurrency: int = 1,
        approved_remote_ips: Iterable[str] | None = None,
        endpoint_authorization: OllamaEndpointAuthorization | None = None,
    ):
        self.remote_authorization = endpoint_authorization or (
            OllamaEndpointAuthorization.create(approved_remote_ips)
            if approved_remote_ips is not None
            else load_ollama_endpoint_authorization()
        )
        valid, error = validate_ollama_endpoint(
            endpoint_url,
            is_remote=is_remote,
            authorization=self.remote_authorization,
        )
        if not valid:
            raise ValueError(f"Invalid Ollama endpoint: {error}")
        self.endpoint_url = endpoint_url.rstrip("/")
        self.is_remote = is_remote
        self.auth_token = auth_token
        self.vision_model = vision_model or "qwen3.5:9b"
        self.reasoning_model = reasoning_model or text_model or "qwen3.5:9b"
        self.narration_model = narration_model or text_model or "qwen3.5:9b"
        self.text_model = text_model or self.narration_model
        self.timeout = timeout
        self.num_ctx = num_ctx
        self.concurrency_mode = concurrency_mode
        self.max_gpu_concurrency = max_gpu_concurrency

    def _get_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token and self.auth_token.strip():
            headers["Authorization"] = f"Bearer {self.auth_token.strip()}"
        return headers

    @property
    def provider_id(self) -> str:
        return "ollama"

    @property
    def display_name(self) -> str:
        return f"Ollama Local ({self.narration_model})"

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0, headers=self._get_headers(), follow_redirects=False) as client:
                res = await client.get(f"{self.endpoint_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    async def list_available_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=4.0, headers=self._get_headers(), follow_redirects=False) as client:
                res = await client.get(f"{self.endpoint_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            pass
        return []

    async def inspect_model_capabilities(self, model_name: str) -> dict:
        """
        Queries official Ollama POST /api/show to inspect real capabilities,
        quantization, family, and parameter size.
        """
        try:
            async with httpx.AsyncClient(timeout=8.0, headers=self._get_headers(), follow_redirects=False) as client:
                res = await client.post(f"{self.endpoint_url}/api/show", json={"name": model_name})
                if res.status_code != 200:
                    return {
                        "name": model_name,
                        "supports_vision": False,
                        "supports_tools": False,
                        "supports_thinking": False,
                        "family": "unknown",
                        "parameter_size": "unknown",
                        "quantization_level": "unknown",
                    }
                data = res.json()
                caps = [c.lower() for c in data.get("capabilities", [])]
                details = data.get("details", {})
                model_info = data.get("model_info", {})
                family = str(details.get("family", "")).lower()

                has_vision_cap = "vision" in caps
                has_vision_info = any("vision" in k.lower() or "clip" in k.lower() for k in model_info.keys())
                has_vision_family = family in ("mllama", "qwen2vl", "qwen35", "llava")

                supports_vision = has_vision_cap or has_vision_info or has_vision_family
                supports_tools = "tools" in caps
                supports_thinking = "thinking" in caps

                return {
                    "name": model_name,
                    "supports_vision": supports_vision,
                    "supports_tools": supports_tools,
                    "supports_thinking": supports_thinking,
                    "family": details.get("family", "unknown"),
                    "parameter_size": details.get("parameter_size", "unknown"),
                    "quantization_level": details.get("quantization_level", "unknown"),
                    "format": details.get("format", "gguf"),
                    "capabilities": caps,
                }
        except Exception as e:
            logger.warning(f"Failed to inspect capabilities for {model_name}: {e}")
            return {
                "name": model_name,
                "supports_vision": False,
                "supports_tools": False,
                "supports_thinking": False,
                "family": "unknown",
                "parameter_size": "unknown",
                "quantization_level": "unknown",
            }

    async def discover_models_with_capabilities(self) -> list[dict]:
        """
        Discovers all installed models and their actual capabilities via /api/tags and /api/show.
        """
        model_names = await self.list_available_models()
        if not model_names:
            return []

        tasks = [self.inspect_model_capabilities(name) for name in model_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        models = []
        for r in results:
            if isinstance(r, dict):
                models.append(r)
        return models

    def recommend_models(self, models: list[dict]) -> dict[str, str]:
        """
        Recommends best models for Vision, Story Reasoning, and Narration based on installed inventory.
        """
        names = [m["name"] for m in models]
        vision_capable = [m["name"] for m in models if m.get("supports_vision")]

        # 1. Vision Role Recommendation
        vision_rec = self.vision_model if self.vision_model in vision_capable else ""
        if not vision_rec:
            for pref in ("qwen3.5:9b", "gemma4:latest", "qwen3.6:latest", "qwen-extended:latest"):
                if pref in vision_capable:
                    vision_rec = pref
                    break
        if not vision_rec and vision_capable:
            vision_rec = vision_capable[0]
        if not vision_rec and names:
            vision_rec = names[0]

        # 2. Story Reasoning Role Recommendation
        reasoning_rec = self.reasoning_model if self.reasoning_model in names else ""
        if not reasoning_rec:
            for pref in ("qwen3-coder:30b", "qwen3.6:latest", "qwen3.5:9b", "gemma4:latest"):
                if pref in names:
                    reasoning_rec = pref
                    break
        if not reasoning_rec and names:
            reasoning_rec = names[0]

        # 3. Narration Role Recommendation
        narration_rec = self.narration_model if self.narration_model in names else ""
        if not narration_rec:
            for pref in ("qwen3.6:latest", "qwen3.5:9b", "gemma4:latest"):
                if pref in names:
                    narration_rec = pref
                    break
        if not narration_rec and names:
            narration_rec = names[0]

        return {
            "vision_model": vision_rec or "qwen3.5:9b",
            "reasoning_model": reasoning_rec or "qwen3.5:9b",
            "narration_model": narration_rec or "qwen3.5:9b",
        }

    async def get_active_telemetry(self) -> list[dict]:
        """Queries GET /api/ps for running models and allocated VRAM."""
        try:
            async with httpx.AsyncClient(timeout=3.0, headers=self._get_headers(), follow_redirects=False) as client:
                res = await client.get(f"{self.endpoint_url}/api/ps")
                if res.status_code == 200:
                    data = res.json()
                    return data.get("models", [])
        except Exception:
            pass
        return []

    async def _generate_response(self, payload, *, attempt=1, max_attempts=1):
        """Stream for tracked jobs; keep the existing buffered API elsewhere."""
        import time
        from engine.llm.activity import activity_sink, publish_activity, generation_cancelled
        cancelled = generation_cancelled.get()
        if cancelled and cancelled():
            raise asyncio.CancelledError("Model request cancelled")
        if activity_sink.get() is None:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self._get_headers(), follow_redirects=False) as client:
                response = await client.post(f"{self.endpoint_url}/api/generate", json=payload)
                if response.status_code != 200 and isinstance(payload.get("format"), dict):
                    payload = {**payload, "format": "json"}
                    response = await client.post(f"{self.endpoint_url}/api/generate", json=payload)
                if response.status_code != 200:
                    raise RuntimeError(f"Ollama generation failed: HTTP {response.status_code}: {response.text}")
                result = response.json()
                if result.get("done_reason") == "length":
                    raise GenerationLimitError("length", result.get("eval_count"), payload.get("options", {}).get("num_predict"))
                return result.get("response", "").strip()

        started = time.monotonic()
        last_update = started
        parts = []
        characters = 0
        activity = {"model": payload["model"], "phase": "preparing", "attempt": attempt,
                    "max_attempts": max_attempts, "output_characters": 0,
                    "output_token_limit": payload.get("options", {}).get("num_predict"),
                    "context_limit": payload.get("options", {}).get("num_ctx"), "elapsed_seconds": 0}
        publish_activity(dict(activity))
        async with httpx.AsyncClient(timeout=self.timeout, headers=self._get_headers(), follow_redirects=False) as client:
            for format_attempt in range(2):
                async with client.stream("POST", f"{self.endpoint_url}/api/generate", json={**payload, "stream": True}) as response:
                    if response.status_code != 200:
                        await response.aread()
                        if format_attempt == 0 and isinstance(payload.get("format"), dict):
                            payload = {**payload, "format": "json"}
                            continue
                        raise RuntimeError(f"Ollama generation failed: HTTP {response.status_code}: {response.text}")
                    done = False
                    async for line in response.aiter_lines():
                        if cancelled and cancelled():
                            raise asyncio.CancelledError("Model request cancelled")
                        if not line.strip():
                            continue
                        event = json.loads(line)
                        if event.get("error"):
                            raise RuntimeError(f"Ollama generation failed: {event['error']}")
                        fragment = event.get("response", "")
                        parts.append(fragment)
                        characters += len(fragment)
                        now = time.monotonic()
                        activity.update(phase="generating", output_characters=characters,
                                        elapsed_seconds=round(now - started, 1))
                        if event.get("done"):
                            done = True
                            duration = event.get("eval_duration", 0) / 1e9
                            activity.update(phase="validating", input_tokens=event.get("prompt_eval_count"),
                                            output_tokens=event.get("eval_count"),
                                            tokens_per_second=round(event.get("eval_count", 0) / duration, 1) if duration else None,
                                            finish_reason=event.get("done_reason"))
                        if done or len(parts) == 1 or now - last_update >= 1.0:
                            publish_activity(dict(activity))
                            last_update = now
                        if done and event.get("done_reason") == "length":
                            raise GenerationLimitError("length", event.get("eval_count"), payload.get("options", {}).get("num_predict"))
                    if not done:
                        raise RuntimeError("Ollama response stream ended before completion")
                    return "".join(parts).strip()

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        **kwargs
    ) -> str:
        model_to_use = kwargs.get("model", self.narration_model or self.text_model)
        payload = {
            "model": model_to_use,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "thinking": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": kwargs.get("num_ctx", min(self.num_ctx, 8192)),
                "think": False,
                "thinking": False,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        return await self._generate_response(payload)

    async def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_repair_retries: int = 2,
        **kwargs
    ) -> T:
        schema_dict = response_model.model_json_schema()
        system_instruction = (
            (system_prompt or "You are a precise narrative structure analysis engine.") +
            "\nRespond ONLY with valid JSON conforming to the supplied structured-output schema. "
            "Do NOT include markdown fences, comments, or preamble. Return raw JSON only."
        )

        current_prompt = prompt
        last_error = ""
        model_to_use = kwargs.get("model", self.reasoning_model or self.text_model)

        for attempt in range(max_repair_retries + 1):
            payload = {
                "model": model_to_use,
                "prompt": current_prompt,
                "system": system_instruction,
                "format": schema_dict,
                "think": False,
                "thinking": False,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_ctx": kwargs.get("num_ctx", self.num_ctx),
                    "think": False,
                    "thinking": False,
                    "num_predict": kwargs.get("max_tokens", 1536),
                },
            }

            raw_json = await self._generate_response(payload, attempt=attempt + 1, max_attempts=max_repair_retries + 1)

            try:
                # Parse JSON
                parsed = json.loads(raw_json)
                # Validate Pydantic schema
                return response_model.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError) as e:
                last_error = str(e)
                logger.warning(f"Ollama JSON validation failed on attempt {attempt + 1}: {e}")
                if attempt < max_repair_retries:
                    # Construct repair prompt
                    current_prompt = (
                        f"{prompt}\n\nThe previous attempt failed validation: {last_error[:800]}. "
                        "Generate a fresh, concise complete JSON response; do not repeat verbose descriptions."
                    )
                else:
                    break

        raise ValueError(
            f"Failed to generate structured data for {response_model.__name__} after "
            f"{max_repair_retries + 1} attempts. Last error: {last_error}"
        )

    async def analyze_vision(
        self,
        image: Path | bytes,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs
    ) -> str:
        if isinstance(image, Path):
            with open(image, "rb") as f:
                img_bytes = f.read()
        else:
            img_bytes = image

        b64_img = base64.b64encode(img_bytes).decode("utf-8")
        model_to_use = kwargs.get("model", self.vision_model)

        payload = {
            "model": model_to_use,
            "prompt": prompt,
            "images": [b64_img],
            "stream": False,
            "think": False,
            "options": {"num_ctx": self.num_ctx, "num_predict": kwargs.get("max_tokens", 2048), "temperature": 0.1},
        }
        if kwargs.get("format_schema"):
            payload["format"] = kwargs["format_schema"]
        if system_prompt:
            payload["system"] = system_prompt

        return await self._generate_response(payload)

    def context_window(self) -> int:
        return self.num_ctx

    def model_metadata(self) -> ModelMetadata:
        return ModelMetadata(
            provider_id=self.provider_id,
            model_name=self.narration_model,
            supports_vision=True,
            supports_structured=True,
            context_window=self.context_window(),
            endpoint=self.endpoint_url,
            extra={
                "vision_model": self.vision_model,
                "reasoning_model": self.reasoning_model,
                "narration_model": self.narration_model,
                "is_remote": self.is_remote,
                "remote_authorization_identity": self.remote_authorization.identity,
                "concurrency_mode": self.concurrency_mode,
                "max_gpu_concurrency": self.max_gpu_concurrency,
            },
        )

