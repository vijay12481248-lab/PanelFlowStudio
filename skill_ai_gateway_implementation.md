# AI Provider Gateway Implementation Skill

**Skill name:** ai_gateway_implementation  
**Category:** ai-infrastructure  
**Trigger:** Use when implementing or extending the Universal AI Gateway in PanelFlow Studio — provider registry, model catalog, database migrations, Pydantic contracts, or adapter integration.

## 1. Overview

This skill captures the class-level implementation patterns for the Universal AI Gateway in PanelFlow Studio. It covers the foundation phases (Phase 1-2) including provider registries, model registries, database migrations, normalized contracts (Pydantic models), and security policies.

The implementation extends the existing LLM provider abstraction to support multiple AI providers (Ollama, OpenAI, Anthropic, Gemini, Groq, OpenRouter) while preserving existing Ollama workflows and adding secure, extensible infrastructure.

## 2. Prerequisites — Always verify before starting

| Check | How |
|-------|-----|
| Repository state | Run `git status` from `C:\Users\Vijaya sekhar\Tools\PanelFlow Studio`. Ensure no uncommitted changes to files you will modify. |
| Python venv activated | `cd "C:\Users\Vijaya sekhar\Tools\PanelFlow Studio" && .venv\Scripts\activate.ps1` (PowerShell) or `source .venv/bin/activate` (bash). |
| Required packages installed | `pip list | grep -iE "fastapi|sqlalchemy|pydantic|httpx"` should list the core packages. |
| Database schema current | Verify `panelflow.db` exists at `C:\Users\Vijaya sekhar\AppData\Local\PanelFlow Studio\database\panelflow.db`. |

## 3. Step-by-Step Implementation Workflow

### Step 1 — Audit existing LLM infrastructure

**Goal:** Understand current provider abstractions before extending.

**Actions:**
1. Read existing provider files to understand the abstraction layer:
   - `engine/llm/providers/base.py` — Base LLMProvider class
   - `engine/llm/providers/ollama.py` — Existing Ollama adapter (591 lines)
   - `engine/llm/providers/openai_compatible.py` — OpenAI-compatible adapter
   - `engine/llm/registry.py` — Provider registry and `get_default_llm_registry()`
   - `engine/llm/activity.py` — Activity publishing for streaming
   - `engine/llm/errors.py` — LLM-specific error types

2. Identify existing integration points:
   - How `llm_registry.get_active_provider()` is called across workflows
   - Existing `MockLLMProvider` usage in tests
   - Current API endpoints in `engine/api/routers/system.py` related to Ollama

**Pitfall:** Do not assume the existing `LLMProvider` base class supports all needed capabilities (vision, structured output, routing). The base class may need extension, not replacement.

### Step 2 — Create architectural design documents

**Goal:** Document the design before writing code.

**Actions:** Create the following markdown documents in the repository root:
- `AI_PROVIDER_EXISTING_SYSTEM_AUDIT.md` — Executive assessment, architecture table, verified local AI environment, implementation changes, limitations, release recommendations.
- `AI_PROVIDER_ARCHITECTURE.md` — Architecture overview, design principles, high-level components diagram, core components (UniversalAIGateway, Provider Registry, Model Registry, Capability Registry, Routing Policy Engine, Health Monitor, Cost Tracker, Credential Vault).
- `AI_PROVIDER_CAPABILITY_MATRIX.md` — 17 capability definitions, provider capability matrix (Ollama, OpenAI, Anthropic, Gemini, Groq, OpenRouter, Cloudflare, Mistral), model-specific capabilities, PanelFlow workflow mappings, free tier analysis, privacy/compliance table.
- `AI_PROVIDER_IMPLEMENTATION_ROADMAP.md` — 8-phase roadmap with deliverables per phase, dependency graph, success criteria per phase, timeline summary.
- `AI_PROVIDER_SECURITY_AND_FAILURE_POLICY.md` — Credential management (OS-native storage, never in logs/DB, write-only operations), error classification (rate limit, transient, auth, budget, unsupported, validation, cancellation), non-idempotent/streaming safety, billing/free-tier policy, audit/diagnostics.

**Verification:** All documents should follow the established dark-theme technical writing convention, use consistent terminology ("LOCAL_FIRST", "FREE_FIRST", "BALANCED", etc.), and be self-contained without referencing internal incident numbers.

### Step 3 — Design normalized Pydantic contracts

**Goal:** Define versioned request/response contracts using the project's established typing mechanisms.

**Actions:** Create `engine/ai_gateway/contracts.py` with these core models:

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from enum import Enum
from decimal import Decimal
from datetime import datetime, timezone

class CapabilityType(str, Enum):
    TEXT_GENERATE = "text.generate"
    TEXT_REASON = "text.reason"
    TEXT_STRUCTURED = "text.structured"
    # ... 14 more capabilities

class RoutingStrategy(str, Enum):
    LOCAL_FIRST = "LOCAL_FIRST"
    FREE_FIRST = "FREE_FIRST"
    LOWEST_COST = "LOWEST_COST"
    QUALITY_FIRST = "QUALITY_FIRST"
    LOWEST_LATENCY = "LOWEST_LATENCY"
    BALANCED = "BALANCED"
    MANUAL = "MANUAL"

class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    OFFLINE = "OFFLINE"

class FinishStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    VALIDATION_FAILED = "VALIDATION_FAILED"

class ModelInfo(BaseModel):
    model_id: str
    provider_id: str
    upstream_model_id: str
    display_name: str
    capabilities: List[CapabilityType] = Field(default_factory=list)
    modalities_in: List[str] = Field(default_factory=lambda: ["text"])
    modalities_out: List[str] = Field(default_factory=lambda: ["text"])
    context_window: int = 8192
    output_limit: int = 4096
    supports_streaming: bool = True
    supports_structured: bool = True
    supports_tools: bool = False
    pricing_input_per_million: Decimal = Decimal("0.0")
    pricing_output_per_million: Decimal = Decimal("0.0")
    free_tier: bool = False
    commercial_use: bool = True
    privacy_retention: str = "standard"
    health_status: HealthStatus = HealthStatus.HEALTHY
    last_verified: Optional[datetime] = None
    extra: Dict[str, Any] = Field(default_factory=dict)

class ProviderConfig(BaseModel):
    config_id: str
    provider_type: str  # ollama, openai, anthropic, gemini, groq, openrouter, cloudflare, mistral, custom
    display_name: str
    enabled: bool = True
    auth_type: str = "api_key"
    credential_ref: Optional[str] = None  # Reference to secure vault
    endpoint_url: Optional[str] = None
    settings: Dict[str, Any] = Field(default_factory=dict)
    privacy_options: Dict[str, Any] = Field(default_factory=dict)
    routing_priority: int = 100
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AIRequest(BaseModel):
    request_id: str
    workflow_job_id: str
    project_id: str
    capability: CapabilityType
    prompt: str
    system_prompt: Optional[str] = None
    input_refs: List[str] = Field(default_factory=list)
    input_modalities: List[str] = Field(default_factory=lambda: ["text"])
    output_schema: Optional[Dict[str, Any]] = None
    quality_requirements: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 180
    cancellation_token: Optional[str] = None
    routing_policy: RoutingStrategy = RoutingStrategy.BALANCED
    data_sharing_restrictions: List[str] = Field(default_factory=list)
    free_only: bool = True  # Free-first / free-only by default per policy
    spending_budget: Optional[Decimal] = None
    preferred_providers: List[str] = Field(default_factory=list)
    prohibited_providers: List[str] = Field(default_factory=list)
    max_attempts: int = 3
    model_overrides: Dict[str, str] = Field(default_factory=dict)
    idempotency_key: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 2048

class AttemptResult(BaseModel):
    attempt_number: int
    provider_id: str
    model_id: str
    status: FinishStatus
    latency_ms: int
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_estimate: Optional[Decimal] = None
    cost_actual: Optional[Decimal] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    provider_request_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AIResponse(BaseModel):
    request_id: str
    status: FinishStatus
    result: Any
    artifact_refs: List[str] = Field(default_factory=list)
    provider_used: str
    model_used: str
    attempt_history: List[AttemptResult] = Field(default_factory=list)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_estimate: Optional[Decimal] = None
    cost_actual: Optional[Decimal] = None
    cost_confidence: str = "HIGH"
    latency_ms: int = 0
    finish_reason: Optional[str] = None
    validation_status: str = "SUCCESS"
    error_info: Optional[Dict[str, Any]] = None
    provider_request_id: Optional[str] = None
    trace_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

**Verification:** All Pydantic models should pass `pydantic.BaseModel.model_validate()` tests with sample data. Models should be importable from `engine.ai_gateway.contracts`.

### Step 4 — Create database migration scripts

**Goal:** Version the AI gateway database schema extensions.

**Actions:** Create 8 migration SQL files in `engine/database/migrations/`:

1. **001_ai_provider_configs.sql** — Provider configurations table with id, provider_type, display_name, enabled, auth_type, credential_ref, endpoint_url, settings JSON, privacy_options JSON, routing_priority, created_at/updated_at. Indexes on enabled and provider_type.

2. **002_ai_model_catalog.sql** — Model catalog table with provider_config_id FK, provider_model_id, display_name, capabilities JSON, modalities_in/out JSON, context_window, output_limit, streaming/structured/tools/vision booleans, pricing, free_tier, commercial_use, privacy_retention, health_status, last_verified. FK to ai_provider_configs ON DELETE CASCADE. Indexes on provider, provider+model, capabilities.

3. **003_ai_routing_profiles.sql** — Routing profiles table with project_id FK, profile_name, strategy (LOCAL_FIRST/FREE_FIRST/etc.), preferences JSON, restrictions JSON, budget_limits JSON. FK to projects ON DELETE CASCADE. Indexes on project and strategy.

4. **004_ai_inference_requests.sql** — Inference requests table with workflow_job_id, project_id, capability, routing_profile_id, status, request_data JSON, created_at/completed_at. FK to projects and routing_profiles. Indexes on project, job, capability, status.

5. **005_ai_inference_attempts.sql** — Inference attempts table with request_id FK, provider_config_id FK, model_id, status, cost_estimate/cost_actual DECIMAL, latency_ms, input/output_tokens, error_code/message, attempt_number, provider_request_id. FK cascades to requests and provider_configs. Indexes on request, provider, model.

6. **006_ai_provider_health.sql** — Provider health table with provider_config_id PK (FK to configs), health_status, last_check, success_rate DECIMAL(5,4), avg_latency_ms, cooldown_until DATETIME, failure_count, circuit_state (CLOSED/OPEN/HALF_OPEN), last_success/last_failure. Indexes on status and circuit_state.

7. **007_ai_usage_records.sql** — Usage records table with provider_config_id FK, model_id, project_id, request_count, token_count, cost_total DECIMAL, period_start/end DATETIME. FK cascades. Indexes on provider, project, period.

8. **008_ai_budget_policies.sql** — Budget policies table with id PK, scope ('global'/'project'/'user'), scope_id, monthly_budget/daily_budget DECIMAL(10,2), free_only BOOLEAN DEFAULT TRUE, paid_authorized BOOLEAN DEFAULT FALSE, alert_threshold DECIMAL(5,4) DEFAULT 0.8. Index on scope+scope_id.

**Migration runner:** Create `engine/database/migrations/run_ai_migrations.py` that:
- Creates the `ai_gateway_migrations` tracking table if missing
- Scans `engine/database/migrations/*.sql` files sorted by name
- For each file, checks if its stem (e.g., "001_ai_provider_configs") is already in the tracking table
- If not applied, reads the SQL, splits by `;` and executes each statement via SQLAlchemy
- Records the migration as applied in the tracking table
- Commits transaction per migration
- Reports success/failure per migration

**Verification:** Run `PYTHONPATH=. .venv/Scripts/python.exe engine/database/migrations/run_ai_migrations.py` — should output "✓ Applied 8 migrations" on fresh run, or "already applied" for each on re-run.

### Step 5 — Implement provider registry

**Goal:** Central management of provider configurations loaded from database.

**Actions:** Create `engine/ai_gateway/registry/provider_registry.py` with:

- **ProviderRegistry class:**
  - `_get_db_session()` → returns `SessionLocal()` from `engine.database.session`
  - `load_from_db()` — loads all providers from `ai_provider_configs` table; sets `_loaded = True` to avoid reloading
  - `register(provider: ProviderConfig) → str` — inserts new provider into DB and cache; generates UUID config_id if missing; returns the ID
  - `update(provider_id: str, updates: Dict) → bool` — dynamic UPDATE query building only specified fields (display_name, enabled, endpoint_url, routing_priority); updates cache entry
  - `delete(provider_id: str) → bool` — deletes from DB and removes from cache
  - `get_provider(provider_id: str) → Optional[ProviderConfig]` — returns cached provider if `_loaded`, else loads from DB first
  - `list_providers(enabled_only: bool = True) → List[ProviderConfig]` — returns all or enabled-only, sorted by routing_priority
  - `get_provider_by_type(provider_type: str) → Optional[ProviderConfig]` — returns first enabled provider matching type

**Key pattern:** All DB operations use explicit `try/finally: db.close()` to ensure session cleanup. Migration-style SQL uses `conn.begin()` for explicit transaction handling.

### Step 6 — Implement model registry

**Goal:** Catalog discovered models with capability metadata.

**Actions:** Create `engine/ai_gateway/registry/model_registry.py` with:

- **ModelRegistry class:**
  - `_get_db_session()` → `SessionLocal()`
  - `load_from_db()` — loads models from `ai_model_catalog`; parses JSON capabilities/modalities; sets `_loaded = True`
  - `register_model(model: ModelInfo) → str` — INSERT OR REPLACE into DB with JSON-serialized capabilities, modalities, pricing; updates cache; returns model_id
  - `get_model(model_id: str) → Optional[ModelInfo]` — returns from cache or loads
  - `get_models_by_provider(provider_id: str) → List[ModelInfo]` — filters cache by provider_id
  - `get_models_by_capability(capability: CapabilityType, free_only: bool = False) → List[ModelInfo]` — filters by capability in capabilities list; optional free_tier filter
  - `discover_models_for_provider(provider_id: str) → List[ModelInfo]` — hook for adapter-specific discovery; adapters populate catalog via this method
  - `update_model_health(model_id: str, health: HealthStatus) → bool` — UPDATE health_status, last_verified, updated_at in DB; updates cache entry

**Key pattern:** JSON fields stored via `json.dumps()` on write, `json.loads()` on read. Health status uses the HealthStatus enum values.

### Step 7 — Implement security and credential handling

**Goal:** Secure provider credential management per the failure policy.

**Actions:** Design credential vault pattern (not full OS integration in Phase 1-2):
- `credential_ref` in `ProviderConfig` stores a UUID/reference, not plaintext
- SQLite stores only non-sensitive metadata
- Real OS credential manager (Windows Credential Manager, macOS Keychain) integration deferred to later phase
- All API responses exclude `credential_ref` or show only `has_credential: boolean`
- Logging sanitization: never write API keys, authorization headers, or bearer tokens
- Endpoint validation: SSRF prevention, HTTPS requirement for external, loopback HTTP only for trusted local runtimes (Ollama)

### Step 8 — Wire into existing workflows

**Goal:** Integrate gateway without breaking existing Ollama-dependent workflows.

**Actions:**
1. Preserve existing `llm_registry` and `OllamaProvider` — do not modify
2. Add new `UniversalAIGateway` class that can coexist with existing registry
3. Migrate 4 core workflows to use gateway (Phase 6):
   - Story analysis → route via gateway
   - Script generation → route via gateway
   - OCR correction → route via gateway
   - Panel analysis → route via gateway
4. Add API endpoints in `engine/api/routers/ai_providers.py`:
   - `GET /api/ai/providers` — list providers
   - `POST /api/ai/providers` — create provider config
   - `PATCH /api/ai/providers/{id}` — update provider
   - `DELETE /api/ai/providers/{id}` — remove provider
   - `POST /api/ai/providers/{id}/test` — test connection
   - `GET /api/ai/providers/{id}/models` — discover models

**Critical:** All existing Ollama `/api/system/ollama/*` endpoints remain fully functional. New AI gateway endpoints are additive, not replacement.

## 4. Pitfalls & Lessons Learned

| Pitfall | Rule |
|---------|------|
| **Assuming all providers support vision** | `supports_vision` is a per-model attribute, not per-provider. Always check `model.capabilities` before routing vision tasks. |
| **Storing plaintext API keys in DB** | `credential_ref` must reference OS vault, not store secrets. SQLite columns for credentials must be NULLable and never populated with raw keys. |
| **Free-only routing silently becoming paid** | Contract sets `free_only: bool = True` default; routing engine must enforce and never override without explicit user authorization. |
| **Circuit breaker cooldown scope confusion** | Cooldown state associates with `(provider_config_id, model_id)` tuple, not just provider. Different models from same provider can have independent cooldowns. |
| **Rate-limit windows not distinguished** | RPM (requests per minute), TPM (tokens per minute), and daily request caps are separate counters. Do not conflate them. |
| **Ignoring model context window constraints** | Always validate `prompt_tokens + system_tokens ≤ model.context_window` before dispatching. Truncation should be last resort with user notification. |
| **Structured output repair loop exhaustion** | Max repair retries = 2 (3 total attempts including initial). After exhaustion, raise descriptive `ValueError` with last error — do not silently return partial data. |
| **Streaming concatenation across models** | Never concatenate output from different models into one answer. Each streaming response belongs to its model. Use explicit regeneration policy for re-trials. |
| **Missing migration tracking table** | Always create `ai_gateway_migrations` table first in runner. Without it, re-running migrations creates duplicate tables or silent failures. |
| **JSON field type mismatches** | Pydantic `Decimal` fields from DB rows must be `Decimal(str(value))`, not `float(value)`. SQLite affinity may return floats for DECIMAL columns. |
| **Provider type strings must be consistent** | Use the exact `provider_type` values: `ollama`, `openai`, `anthropic`, `gemini`, `groq`, `openrouter`, `cloudflare`, `mistral`, `custom`. Mismatches cause registry lookup failures. |

## 5. Reference Files (references/ directory)

Support files extend the skill's capabilities. Create these under `engine/ai_gateway/skill_references/` (or referenced via skill metadata):

### references/provider_capabilities.md
Decision table mapping each provider to its supported capabilities, context windows, and pricing tiers. Used by routing engine and model discovery.

### references/routing_scoring_policies.md
Configurable scoring policy for BALANCED mode: quality evidence (0.35 weight), expected cost (0.25), observed latency (0.20), recent success rate (0.15), remaining quota (0.05). Includes how to adjust weights per project.

### references/budget_enforcement.md
Budget policy enforcement logic: per-request cost ceiling check, per-project spending limit, global monthly budget, free-only mode gate, alert threshold (80% of budget triggers warning). Shows how to compute estimated cost before request execution.

### references/error_classification_table.md
Map of HTTP status codes to error classifications: 429→RateLimitError, 5xx→TransientProviderError, 401→AuthenticationError, 403→AuthenticationError, budget exhausted→BudgetExhaustedError, capability unsupported→UnsupportedCapabilityError, validation failure→ValidationError.

### references/ssrf_prevention_guidelines.md
SSRF protection rules: reject private IP ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, 127.0.0.0/8), loopback, link-local; require HTTPS for external endpoints; allow loopback HTTP only for trusted local runtimes (Ollama 127.0.0.1:11434); block cloud metadata endpoints (169.254.169.254, metadata.google.internal).

### templates/gateway_config_template.yaml
Starter YAML config for provider registration with placeholder values and comments explaining each field. Used by `provider_registry.register()` when no DB entry exists.

### scripts/discover_models.py
Verification script that: loads provider registry, queries each enabled provider's health, discovers models via adapter, validates capability claims against actual model metadata, outputs JSON summary of discovered models and any mismatches. Run with `PYTHONPATH=. .venv/Scripts/python.exe engine/ai_gateway/scripts/discover_models.py`.

## 6. Testing Checklist

All new implementations must pass these verification steps:

- [ ] Ollama-only operation succeeds (existing workflows unchanged)
- [ ] Gemini text request succeeds (via OpenAI-compatible adapter or direct)
- [ ] Groq structured request succeeds
- [ ] OpenRouter integration succeeds (aggregator routing)
- [ ] Vision task selects a vision-capable model (rejects text-only)
- [ ] Text-only model is rejected for vision capability
- [ ] HTTP 429 causes correct cooldown and fallback
- [ ] Retry-After header is respected
- [ ] HTTP 401 disables retries against invalid credentials
- [ ] Insufficient balance is handled correctly (blocks, not auto-purchase)
- [ ] All providers unavailable returns actionable failure
- [ ] Free-only policy excludes paid routes
- [ ] Project budget is never exceeded by unauthorized scheduling
- [ ] Provider secrets never included in API responses or logs
- [ ] Cancellation prevents additional fallback requests
- [ ] Provider timeout does not create duplicate media-generation jobs
- [ ] Streaming interruption is safely handled
- [ ] Structured-output validation rejects malformed responses
- [ ] Model deprecation/removal updates registry safely
- [ ] Existing Ollama workflows continue to work
- [ ] Durable job recovery works after engine restart

Run the full test suite: `PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/ -v --tb=short` and verify all 25 scenarios pass before marking Phase 3 complete.

## 7. Known Limitations (as of this skill version)

- OS-native credential vault integration not yet implemented (Phase 3+)
- Full adapter implementations (OpenAI, Anthropic, Gemini, etc.) not yet written
- Routing engine with all 7 strategies not yet implemented
- Usage dashboards and diagnostics UI not yet built
- Credential rotation and rotation-aware cooldown not yet supported
- Multi-tenant project budget isolation not yet enforced

These are documented as known and will be addressed in subsequent phases per the implementation roadmap.

## 8. Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-10-20 | Initial release covering Phases 1-2 foundation: registry implementation, model catalog, migrations, contracts, security policy. |