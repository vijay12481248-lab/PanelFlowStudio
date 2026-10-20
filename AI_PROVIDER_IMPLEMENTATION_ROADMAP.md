# AI Provider Implementation Roadmap

**Document version:** 1.0  
**Date:** 2026-10-20  
**Scope:** Phased implementation plan for Universal AI Gateway

## Overview

This roadmap breaks the Universal AI Gateway implementation into 8 manageable phases, each delivering verifiable functionality. Each phase builds on the previous, preserving existing Ollama workflows throughout.

## Phase 1: Repository Audit, Contracts & Migration Design (Week 1)

### Deliverables
- [x] AI_PROVIDER_EXISTING_SYSTEM_AUDIT.md (COMPLETED)
- [x] AI_PROVIDER_ARCHITECTURE.md (COMPLETED)
- [x] AI_PROVIDER_CAPABILITY_MATRIX.md (COMPLETED)
- [ ] AI_PROVIDER_IMPLEMENTATION_ROADMAP.md (this document)
- [ ] AI_PROVIDER_SECURITY_AND_FAILURE_POLICY.md
- [ ] Normalized request/response contracts (Pydantic models)
- [ ] Database migration design (SQL)

### Tasks
1. **Complete remaining documentation** - Security policy and final roadmap
2. **Define Pydantic contracts** in `engine/ai_gateway/contracts.py`:
   - `AIRequest`, `AIResponse`, `NormalizedRequest`, `NormalizedResponse`
   - `ModelInfo`, `CapabilitySet`, `ProviderConfig`
   - `HealthStatus`, `CostEstimate`, `RoutingDecision`
3. **Design database migrations** in `engine/database/migrations/`:
   - `001_ai_provider_configs.sql`
   - `002_ai_model_catalog.sql`
   - `003_ai_routing_profiles.sql`
   - `004_ai_inference_requests.sql`
   - `005_ai_inference_attempts.sql`
   - `006_ai_provider_health.sql`
   - `007_ai_usage_records.sql`
   - `008_ai_budget_policies.sql`
4. **Create migration runner** integrated with existing SQLite migration logic

### Verification
- Contracts pass Pydantic validation
- Migration scripts run against test database
- Existing schema unaffected

---

## Phase 2: Provider Registry, Credentials & Model Discovery (Week 2)

### Deliverables
- `engine/ai_gateway/registry/provider_registry.py`
- `engine/ai_gateway/registry/model_registry.py`
- `engine/ai_gateway/registry/capability_registry.py`
- `engine/ai_gateway/security/credential_vault.py`
- Database migrations applied
- API endpoints for provider CRUD

### Tasks
1. **Provider Registry** - Central management of provider configurations
   - Load from database on startup
   - Dynamic add/remove/update
   - Health check integration
2. **Model Registry** - Catalog of discovered models
   - Per-provider model discovery
   - Capability indexing
   - Performance tracking
3. **Capability Registry** - Normalized capability definitions
   - Capability → model mapping
   - Compatibility checking
3. **Credential Vault** - Secure secret storage
   - Windows Credential Manager integration
   - macOS Keychain integration
   - Fallback to encrypted file (last resort)
   - Write-only API
4. **Database Migrations** - Apply all 8 migration scripts
5. **API Endpoints** in `engine/api/routers/ai_providers.py`:
   - `GET /api/ai/providers` - List providers
   - `POST /api/ai/providers` - Create provider
   - `PATCH /api/ai/providers/{id}` - Update provider
   - `DELETE /api/ai/providers/{id}` - Remove provider
   - `POST /api/ai/providers/{id}/test` - Test connection
   - `GET /api/ai/providers/{id}/models` - Discover models

### Verification
- [ ] Registry loads providers from DB
- [ ] Credentials stored securely (not in DB)
- [ ] Ollama models discovered and cataloged
- [ ] API endpoints return expected JSON
- [ ] Existing Ollama workflows unchanged

---

## Phase 3: Core Adapters (Ollama, OpenAI, Anthropic, Gemini, Groq, OpenRouter) (Week 3)

### Deliverables
- `engine/ai_gateway/adapters/base.py` - Abstract base
- `engine/ai_gateway/adapters/ollama_adapter.py` - Wrap existing
- `engine/ai_gateway/adapters/openai_adapter.py`
- `engine/ai_gateway/adapters/anthropic_adapter.py`
- `engine/ai_gateway/adapters/gemini_adapter.py`
- `engine/ai_gateway/adapters/groq_adapter.py`
- `engine/ai_gateway/adapters/openrouter_adapter.py`
- `engine/ai_gateway/adapters/custom_endpoint_adapter.py`
- Unit tests for each adapter

### Tasks
1. **Base Adapter** - Common interface with:
   - Request normalization
   - Response normalization
   - Error mapping to common hierarchy
   - Timeout handling
   - Streaming support
2. **Ollama Adapter** - Refactor existing `OllamaProvider` to implement `ProviderAdapter`
3. **OpenAI Adapter** - Full API support including:
   - Chat completions
   - Structured outputs (response_format)
   - Vision (gpt-4o)
   - Embeddings
   - Audio (whisper, tts)
   - Images (dall-e-3)
4. **Anthropic Adapter** - Messages API support
5. **Gemini Adapter** - Generative AI API including 1.5 Pro/Flash
6. **Groq Adapter** - OpenAI-compatible with provider-specific optimizations
7. **OpenRouter Adapter** - Aggregator with native routing options
8. **Custom Endpoint Adapter** - Generic OpenAI-compatible
9. **Tests** - Mock HTTP, verify request/response shapes

### Verification
- [ ] Each adapter passes health check
- [ ] Text generation works for all
- [ ] Structured output works for all supporting it
- [ ] Vision works for providers supporting it
- [ ] Error handling maps to common hierarchy
- [ ] Existing Ollama workflows still function

---

## Phase 4: Routing, Rate Limits, Circuit Breakers, Fallback & Budget (Week 4)

### Deliverables
- `engine/ai_gateway/routing/routing_engine.py`
- `engine/ai_gateway/monitoring/health_monitor.py`
- `engine/ai_gateway/monitoring/circuit_breaker.py`
- `engine/ai_gateway/monitoring/rate_limiter.py`
- `engine/ai_gateway/fallback/fallback_coordinator.py`
- `engine/ai_gateway/billing/cost_tracker.py`
- `engine/ai_gateway/billing/budget_enforcer.py`
- Integration tests for routing scenarios

### Tasks
1. **Routing Engine** - 7 strategies:
   - `LOCAL_FIRST` - Prefer local providers
   - `FREE_FIRST` - Only free models
   - `LOWEST_COST` - Minimize estimated cost
   - `QUALITY_FIRST` - Best quality evidence
   - `LOWEST_LATENCY` - Fastest observed
   - `BALANCED` - Weighted scoring
   - `MANUAL` - User-specified model
2. **Health Monitor** - Periodic checks:
   - Provider health state
   - Latency tracking
   - Success rate calculation
3. **Circuit Breaker** - Per-provider:
   - CLOSED/OPEN/HALF_OPEN states
   - Configurable failure threshold
   - Cooldown with jitter
4. **Rate Limiter** - Per-provider:
   - RPM, TPM, daily limits
   - Retry-After parsing
   - Backoff with jitter
5. **Fallback Coordinator** - Chain of responsibility:
   - Ordered fallback candidates
   - Failure classification
   - Repair strategies
6. **Cost Tracker** - Estimation + actuals:
   - Pre-request estimation
   - Post-request capture
   - Usage aggregation
7. **Budget Enforcer** - Hard limits:
   - Global, project, user budgets
   - Free-only mode
   - Alert thresholds

### Verification
- [ ] Routing selects correct provider for each strategy
- [ ] 429 triggers cooldown and fallback
- [ ] 401 disables retries, reports config error
- [ ] 5xx triggers circuit breaker
- [ ] Free-only never routes to paid
- [ ] Budget exceeded blocks requests
- [ ] Fallback chain executes correctly

---

## Phase 5: Provider Management UI (Week 5)

### Deliverables
- React components in `apps/desktop/src/components/ai-gateway/`
- Provider management screen
- Model explorer
- Routing configuration
- Usage dashboard
- Diagnostics panel

### Tasks
1. **Provider Overview** - Cards with status, capabilities, cost tier
2. **Add Provider Wizard** - Step-by-step:
   - Provider selection
   - Credential entry (secure)
   - Endpoint configuration
   - Test connection
3. **Model Explorer** - Filterable table:
   - By provider
   - By capability
   - By price (free/paid)
   - By context window
4. **Routing Configuration** - Strategy selection:
   - Default strategy
   - Per-task overrides
   - Fallback ordering
   - Privacy rules
   - Budget settings
5. **Usage Dashboard** - Charts:
   - Requests by provider
   - Success/failure rates
   - Latency percentiles
   - Cost trends
   - Token usage
6. **Diagnostics Panel** - Routing explanation:
   - Why model selected
   - Why others excluded
   - Cooldown states
   - Error categories

### Verification
- [ ] UI matches PanelFlow dark theme
- [ ] All CRUD operations work
- [ ] Credentials never exposed in UI
- [ ] Real-time health updates
- [ ] Routing preview works
- [ ] Keyboard accessible

---

## Phase 6: Workflow Integration - Story, Script, OCR, Panels (Week 6)

### Deliverables
- Updated workflow services using gateway
- Migration of 4 core workflows
- Backward compatibility layer

### Tasks
1. **UniversalAIGateway** - Core orchestration:
   - Request validation
   - Routing execution
   - Result validation
   - Audit logging
2. **Story Analysis** (`engine/story/`) - Route via gateway:
   - Scene interpretation
   - Character identification
   - Continuity checking
3. **Script Generation** (`engine/story/script/`) - Route via gateway:
   - Narration generation
   - Dialogue attribution
   - Emotion direction
4. **OCR Correction** (`engine/ocr/`) - Route via gateway:
   - Text enhancement
   - Language detection
5. **Panel Analysis** (`engine/imaging/panels/`) - Route via gateway:
   - Panel detection validation
   - Reading order
   - Content classification

### Verification
- [ ] All 4 workflows produce identical results with Ollama
- [ ] Gateway routing works with multiple providers
- [ ] Fallback activates correctly
- [ ] Structured output validation preserved
- [ ] Checkpoint/provenance unchanged

---

## Phase 7: Audio, Multimodal, Motion & Media Adapters (Week 7)

### Deliverables
- Audio adapters (transcribe, synthesize, analyze)
- Image/video generation adapters
- Motion planning integration
- ComfyUI bridge via gateway

### Tasks
1. **Audio Adapters**:
   - Whisper (OpenAI, local)
   - TTS (OpenAI, ElevenLabs, local Chatterbox)
2. **Image/Video Adapters**:
   - DALL-E 3 (OpenAI)
   - Stable Diffusion (Cloudflare, local ComfyUI)
   - Imagen (Gemini)
3. **Motion Planning** - Multimodal reasoning for camera
4. **ComfyUI Integration** - Submit workflows via gateway
5. **Existing Audio Preservation** - Reuse Chatterbox, F5-TTS, ACE-Step

### Verification
- [ ] Audio workflows use gateway
- [ ] Image generation works
- [ ] ComfyUI jobs submitted via gateway
- [ ] Existing audio integrations preserved

---

## Phase 8: Remaining Providers, Hardened Tests, Documentation, Release (Week 8)

### Deliverables
- Cloudflare Workers AI adapter
- Mistral adapter
- Complete test suite
- Architecture documentation
- Operations guide
- Release validation

### Tasks
1. **Cloudflare Adapter** - Workers AI API
2. **Mistral Adapter** - Mistral API
3. **Security Tests** - Credential leakage, SSRF, injection
4. **Load Tests** - Concurrent requests, rate limits
5. **Regression Tests** - All existing workflows
6. **Documentation**:
   - `AI_PROVIDER_API.md` - API reference
   - `AI_PROVIDER_OPERATIONS.md` - Ops guide
   - `AI_PROVIDER_DEVELOPER.md` - Extending providers
7. **Release Validation** - End-to-end test

### Verification
- [ ] All 25 required test scenarios pass
- [ ] Security review clean
- [ ] Performance within SLA
- [ ] Documentation complete

---

## Dependency Graph

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5
                                  │             │
                                  ▼             ▼
                             Phase 6 ◄────── Phase 7
                                  │
                                  ▼
                             Phase 8
```

## Success Criteria per Phase

| Phase | Must Pass | Can Defer |
|-------|-----------|-----------|
| 1 | Contracts valid, migrations ready | Full migration execution |
| 2 | Registry loads, credentials secure, API works | Full model catalog |
| 3 | All 6 adapters functional, tests pass | Streaming optimization |
| 4 | All 7 strategies work, fallback tested | Advanced scoring |
| 5 | Full CRUD, routing config, diagnostics | Advanced charts |
| 6 | 4 workflows migrated, Ollama parity | Motion integration |
| 7 | Audio/image via gateway, ComfyUI works | Video generation |
| 8 | 25 scenarios pass, docs complete | Edge cases |

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking Ollama | Dual-run period, feature flag |
| Secret leakage | Vault abstraction, no plaintext in code |
| Cost overruns | Hard budgets, free-only default |
| Performance | Async, caching, connection pooling |
| Provider changes | Adapter isolation, version detection |

## Timeline Summary

| Week | Phase | Focus |
|------|-------|-------|
| 1 | 1 | Audit, Contracts, Migrations |
| 2 | 2 | Registry, Credentials, Models |
| 3 | 3 | Core Adapters |
| 4 | 4 | Routing, Resilience, Budget |
| 5 | 5 | Provider Management UI |
| 6 | 6 | Core Workflow Integration |
| 7 | 7 | Media Adapters, Motion |
| 8 | 8 | Polish, Tests, Docs, Release |

**Total: 8 weeks for MVP with all core providers and workflows integrated.**

---

## Next Immediate Action

Begin **Phase 1** completion:
1. Create `AI_PROVIDER_SECURITY_AND_FAILURE_POLICY.md`
2. Create `engine/ai_gateway/contracts.py` with Pydantic models
3. Create database migration SQL files
4. Create migration runner

Then proceed to Phase 2 implementation.