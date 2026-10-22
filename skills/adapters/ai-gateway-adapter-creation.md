# Create Provider Adapters for Universal AI Gateway

## Command
Use when creating a new provider adapter for the Universal AI Gateway. <one-line behavior>

## Behavior
Wrap existing or new LLM provider implementations to implement the `ProviderAdapter` interface defined in `engine/ai_gateway/adapters/base.py`. Adapters must:
- Implement `provider_id`, `display_name`, `health_check()`, `execute()`, `supports_capability()`, `get_capabilities()`, `normalize_request()`, and `normalize_response()`
- Handle request timeout enforcement
- Map errors to the standard hierarchy: `RateLimitError`, `AuthenticationError`, `TransientError`, `UnsupportedCapabilityError`
- Provide bounded exponential backoff + jitter on transient failures
- Never retry authentication failures
- Never substitute a text-only model for required vision understanding or structured output
- Persist external task IDs and poll/reconcile their status for non-idempotent operations
- Use idempotency keys where supported by the upstream provider
- Maintain durable job states across desktop engine restarts
- Never automatically regenerate costly artifacts merely because a connection was interrupted

## Adapter Files
Create adapter files in `engine/ai_gateway/adapters/` following the pattern of `ollama_adapter.py`, `openai_adapter.py`, `gemini_adapter.py`, `anthropic_adapter.py`, `groq_adapter.py`, `openrouter_adapter.py`, `freellm_adapter.py`.

Each adapter must:
- Extend `ProviderAdapter` base class
- Implement all abstract methods
- Register with `provider_registry` on initialization
- Provide `get_capabilities()` with proper `ModelInfo` metadata
- Handle `normalize_request()` and `normalize_response()` for the gateway contract

## Supported Providers
1. **Ollama** (`ollama`): Local, free, no API key. Supports text, structured, vision.
2. **OpenAI** (`openai`): Chat completions, vision, structured outputs, embeddings, TTS/whisper. Requires API key.
3. **Gemini** (`gemini`): Gemini 1.5 Pro/Flash, vision OCR, embeddings. Requires API key.
4. **Anthropic** (`anthropic`): Claude 3 Opus/Sonnet, messages API, vision. Requires API key.
5. **Groq** (`groq`): Llama 3.1 fast inference. Text-only. Requires API key.
6. **OpenRouter** (`openrouter`): Aggregator of 100+ models. Requires API key.
7. **FreeLLM** (`freellm`): Free-tier enforcement for OpenAI-compatible endpoints. Default free-only mode.

## Adapter Factory
The `AdapterFactory` (`engine/ai_gateway/adapters/factory.py`) manages provider adapter instantiation, health checks, capability checking, and execution through `safe_execute` with retry and circuit breaker behavior.

## Known Pitfalls
- Forgetting to register the adapter with `provider_registry` after construction
- Missing the `supports_capability` check before executing a request
- Not enforcing `free_only` policy when `free_only=True` is set in the request
- Forgetting to add the provider to the registry after construction
- Incorrectly handling the `output_schema` in `normalize_request` / `normalize_response`
- Forgetting to add `model_overrides` or `model_id` to the request
- Not respecting the `free_only` policy which blocks paid models by default
- Forgetting to handle `UnsupportedCapabilityError` for vision on text-only models

## Adapter Factory Registration
Register new adapters via `adapter_factory.register(provider_id, AdapterClass)`.
The factory auto-instantiates adapters on demand via `get_instance(provider_id, **kwargs)`.
Adapter instances are cached in `adapter_factory._instances[provider_id]`.