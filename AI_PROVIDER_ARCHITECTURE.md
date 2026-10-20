# AI Provider Architecture

**Document version:** 1.0  
**Date:** 2026-10-20  
**Scope:** Universal AI Gateway architecture for PanelFlow Studio

## 1. Architecture Overview

### 1.1 Design Principles

The Universal AI Gateway follows Clean Architecture and Hexagonal Architecture principles:

1. **Separation of Concerns** - Business workflows depend on interfaces, not implementations
2. **Dependency Inversion** - High-level modules depend on abstractions, low-level details depend on abstractions
3. **Single Responsibility** - Each component has one clear purpose
4. **Open/Closed Principle** - Extensible without modifying existing code
5. **Secure by Default** - Credentials never in plaintext, SSRF protection, input sanitization

### 1.2 High-Level Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Business Workflows                        │
│  (Story, Script, OCR, Motion, Audio - existing)             │
└──────────────────────────┬──────────────────────────────────┘
                           │ Capability Requests
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Universal AI Gateway (Core)                     │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  UniversalAIGateway                                   │  │
│  │  - Request normalization                              │  │
│  │  - Routing decision                                   │  │
│  │  - Result validation                                  │  │
│  └───────────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Provider    │  │  Routing     │  │  Policy      │
│  Registry    │  │  Engine      │  │  Engine      │
└──────────────┘  └──────────────┘  └──────────────┘
         │                 │                 │
         ▼                 ▼                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Adapters    │  │  Health      │  │  Cost        │
│  (9 providers)│  │  Monitor     │  │  Tracker     │
└──────────────┘  └──────────────┘  └──────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                   External Providers                         │
│  Ollama, OpenAI, Anthropic, Gemini, Groq, ...             │
└─────────────────────────────────────────────────────────────┘
```

## 2. Core Components

### 2.1 UniversalAIGateway

**Location:** `engine/ai_gateway/gateway.py`

**Responsibilities:**
- Normalize requests from business workflows
- Route to appropriate provider based on policy
- Validate responses
- Handle retries and fallback
- Audit logging

**Interface:**
```python
class UniversalAIGateway:
    async def execute(
        request: AIRequest,
        project_id: str,
        user_id: str | None = None
    ) -> AIResponse
```

### 2.2 Provider Registry

**Location:** `engine/ai_gateway/registry/provider_registry.py`

**Responsibilities:**
- Manage provider configurations
- Load/unload providers dynamically
- Manage credential references
- Provider discovery

**Key Classes:**
- `ProviderRegistry` - Central registry
- `ProviderConfig` - Configuration model
- `CredentialReference` - Secure credential handle

### 2.3 Provider Adapter Interface

**Location:** `engine/ai_gateway/adapters/base.py`

**Base Interface:**
```python
class ProviderAdapter(ABC):
    @abstractmethod
    async def health_check(self) -> HealthStatus
    @abstractmethod
    async def execute(self, request: NormalizedRequest) -> NormalizedResponse
    @abstractmethod
    async def discover_models(self) -> List[ModelInfo]
    @abstractmethod
    def supports_capability(self, capability: str) -> bool
    @abstractmethod
    def get_capabilities(self) -> CapabilitySet
```

### 2.4 Model Registry

**Location:** `engine/ai_gateway/registry/model_registry.py`

**Responsibilities:**
- Catalog discovered models
- Store capability metadata
- Track model performance
- Handle model deprecation

**Model Metadata:**
- Provider ID, Model ID
- Capabilities, Modalities
- Context window, Output limits
- Pricing, Free tier eligibility
- Privacy characteristics
- Health status
- Last verification

### 2.5 Capability Registry

**Location:** `engine/ai_gateway/registry/capability_registry.py`

**Normalized Capabilities:**
- `text.generate`
- `text.reason`
- `text.structured`
- `text.translate`
- `text.summarize`
- `vision.understand`
- `vision.ocr_assist`
- `vision.panel_analysis`
- `vision.continuity_check`
- `audio.transcribe`
- `audio.synthesize`
- `audio.analyze`
- `music.generate`
- `image.generate`
- `image.edit`
- `video.generate`
- `embeddings.generate`

**Capability Dimensions:**
- Streaming support
- Tool calling
- Long context
- Batch processing
- Structured output

### 2.6 Routing Policy Engine

**Location:** `engine/ai_gateway/routing/routing_engine.py`

**Routing Strategies:**
1. **LOCAL_FIRST** - Prefer local providers
2. **FREE_FIRST** - Free models only
3. **LOWEST_COST** - Minimize cost
4. **QUALITY_FIRST** - Best quality evidence
5. **LOWEST_LATENCY** - Fastest response
6. **BALANCED** - Weighted scoring
7. **MANUAL** - User-specified

**Routing Process:**
1. Receive capability request
2. Filter by project/policy
3. Check provider health
4. Validate compatibility
5. Enforce budget/privacy
6. Rank candidates
7. Execute preferred
8. Validate result
9. Fallback if needed

### 2.7 Health Monitor

**Location:** `engine/ai_gateway/monitoring/health_monitor.py`

**Features:**
- Periodic health checks
- Circuit breaker pattern
- Cooldown management
- Rate limit tracking
- Success/failure metrics

**Circuit Breaker States:**
- CLOSED - Normal operation
- OPEN - Failing, rejecting requests
- HALF_OPEN - Testing recovery

### 2.8 Cost Tracker

**Location:** `engine/ai_gateway/billing/cost_tracker.py`

**Features:**
- Cost estimation before requests
- Actual usage capture
- Budget enforcement
- Spending alerts
- Cost attribution

### 2.9 Credential Vault

**Location:** `engine/ai_gateway/security/credential_vault.py`

**Security:**
- OS-native storage (Windows Credential Manager, macOS Keychain)
- SQLite stores references only
- No plaintext secrets in logs
- Write-only secret updates
- No exposed keys in API responses

## 3. Data Models

### 3.1 Database Schema

**New Tables:**

```sql
-- Provider configurations
CREATE TABLE ai_provider_configs (
    id TEXT PRIMARY KEY,
    provider_type TEXT NOT NULL,
    display_name TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    auth_type TEXT,
    credential_ref TEXT,
    endpoint_url TEXT,
    settings JSON,
    privacy_options JSON,
    routing_priority INTEGER DEFAULT 100,
    created_at DATETIME,
    updated_at DATETIME
);

-- Model catalog
CREATE TABLE ai_model_catalog (
    id TEXT PRIMARY KEY,
    provider_config_id TEXT,
    provider_model_id TEXT NOT NULL,
    display_name TEXT,
    capabilities JSON,
    modalities JSON,
    context_window INTEGER,
    supports_streaming BOOLEAN,
    supports_structured BOOLEAN,
    supports_tools BOOLEAN,
    pricing JSON,
    free_tier BOOLEAN,
    commercial_use BOOLEAN,
    privacy_retention TEXT,
    health_status TEXT,
    last_verified DATETIME,
    FOREIGN KEY(provider_config_id) REFERENCES ai_provider_configs(id)
);

-- Routing profiles
CREATE TABLE ai_routing_profiles (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    profile_name TEXT,
    strategy TEXT,
    preferences JSON,
    restrictions JSON,
    budget_limits JSON,
    created_at DATETIME
);

-- Inference requests
CREATE TABLE ai_inference_requests (
    id TEXT PRIMARY KEY,
    workflow_job_id TEXT,
    project_id TEXT,
    capability TEXT,
    routing_profile_id TEXT,
    status TEXT,
    created_at DATETIME,
    completed_at DATETIME
);

-- Inference attempts
CREATE TABLE ai_inference_attempts (
    id TEXT PRIMARY KEY,
    request_id TEXT,
    provider_config_id TEXT,
    model_id TEXT,
    status TEXT,
    cost_estimate DECIMAL,
    cost_actual DECIMAL,
    latency_ms INTEGER,
    error_code TEXT,
    error_message TEXT,
    attempt_number INTEGER,
    created_at DATETIME,
    FOREIGN KEY(request_id) REFERENCES ai_inference_requests(id)
);

-- Provider health
CREATE TABLE ai_provider_health (
    provider_config_id TEXT PRIMARY KEY,
    health_status TEXT,
    last_check DATETIME,
    success_rate DECIMAL,
    avg_latency_ms INTEGER,
    cooldown_until DATETIME,
    failure_count INTEGER,
    circuit_state TEXT
);

-- Usage records
CREATE TABLE ai_usage_records (
    id TEXT PRIMARY KEY,
    provider_config_id TEXT,
    model_id TEXT,
    project_id TEXT,
    request_count INTEGER,
    token_count INTEGER,
    cost_total DECIMAL,
    period_start DATETIME,
    period_end DATETIME
);

-- Budget policies
CREATE TABLE ai_budget_policies (
    id TEXT PRIMARY KEY,
    scope TEXT, -- 'global', 'project', 'user'
    scope_id TEXT,
    monthly_budget DECIMAL,
    daily_budget DECIMAL,
    free_only BOOLEAN DEFAULT FALSE,
    paid_authorized BOOLEAN DEFAULT FALSE,
    alert_threshold DECIMAL
);
```

## 4. Request/Response Contracts

### 4.1 AIRequest Model

```python
class AIRequest(BaseModel):
    request_id: str
    workflow_job_id: str
    project_id: str
    capability: str  # e.g., 'vision.panel_analysis'
    prompt: str
    input_refs: List[str] = []  # File references
    input_modalities: List[str] = []
    output_schema: Dict | None = None
    quality_requirements: Dict = {}
    timeout_seconds: int = 180
    cancellation_token: str | None = None
    routing_policy: str = "BALANCED"
    data_sharing_restrictions: List[str] = []
    free_only: bool = False
    spending_budget: Decimal | None = None
    preferred_providers: List[str] = []
    prohibited_providers: List[str] = []
    max_attempts: int = 3
    model_overrides: Dict = {}
    idempotency_key: str | None = None
```

### 4.2 AIResponse Model

```python
class AIResponse(BaseModel):
    request_id: str
    status: str  # SUCCESS, FAILED, CANCELLED
    result: Any
    artifact_refs: List[str] = []
    provider_used: str
    model_used: str
    attempt_history: List[AttemptResult] = []
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_estimate: Decimal | None = None
    cost_actual: Decimal | None = None
    cost_confidence: str  # HIGH, MEDIUM, LOW
    latency_ms: int
    finish_reason: str | None = None
    validation_status: str
    error_info: Dict | None = None
    provider_request_id: str | None = None
    trace_id: str
    created_at: datetime
```

## 5. Adapter Implementations

### 5.1 Provider Adapters

**Location:** `engine/ai_gateway/adapters/`

**Implemented Adapters:**
1. `ollama_adapter.py` - Existing Ollama with gateway integration
2. `openai_compatible_adapter.py` - Base for OpenAI-compatible
3. `openai_adapter.py` - OpenAI-specific optimizations
4. `anthropic_adapter.py` - Claude API
5. `gemini_adapter.py` - Google Gemini
6. `groq_adapter.py` - GroqCloud
7. `openrouter_adapter.py` - OpenRouter routing
8. `cloudflare_adapter.py` - Workers AI
9. `mistral_adapter.py` - Mistral API
10. `custom_endpoint_adapter.py` - User-configured

### 5.2 Adapter Pattern

Each adapter implements:
```python
class ProviderAdapter:
    provider_id: str
    display_name: str
    
    async def health_check(self) -> HealthStatus
    async def execute(self, request: NormalizedRequest) -> NormalizedResponse
    async def discover_models(self) -> List[ModelInfo]
    def normalize_request(self, request: AIRequest) -> ProviderRequest
    def normalize_response(self, response: ProviderResponse) -> AIResponse
```

## 6. Routing Algorithm

### 6.1 Candidate Selection

```python
def select_candidates(request: AIRequest) -> List[ModelCandidate]:
    candidates = []
    
    for provider in provider_registry.list_enabled():
        # Check basic eligibility
        if not provider.enabled: continue
        if provider.id in request.prohibited_providers: continue
        if request.preferred_providers and provider.id not in request.preferred_providers: continue
        
        # Check capability
        if not provider.supports_capability(request.capability): continue
        
        # Check health
        if not health_monitor.is_healthy(provider): continue
        
        # Check rate limits
        if rate_limiter.is_exceeded(provider): continue
        
        # Check budget
        if not budget_checker.can_afford(provider, request): continue
        
        # Check privacy
        if not privacy_checker.allowed(provider, request): continue
        
        # Find suitable models
        for model in model_registry.get_models(provider.id, request.capability):
            if not model.meets_constraints(request): continue
            
            # Calculate score
            score = scoring_engine.score(model, request)
            candidates.append(ModelCandidate(model, score))
    
    return sorted(candidates, key=lambda c: c.score, reverse=True)
```

### 6.2 BALANCED Scoring

```python
def calculate_balanced_score(candidate, request):
    weights = {
        'quality': 0.35,
        'cost': 0.25,
        'latency': 0.20,
        'reliability': 0.15,
        'quota': 0.05
    }
    
    score = 0
    score += weights['quality'] * normalize_quality(candidate.quality_score)
    score += weights['cost'] * (1 - normalize_cost(candidate.estimated_cost))
    score += weights['latency'] * (1 - normalize_latency(candidate.avg_latency))
    score += weights['reliability'] * candidate.success_rate
    score += weights['quota'] * candidate.quota_remaining
    
    return score
```

## 7. Security Architecture

### 7.1 Credential Management

1. **Storage**: OS-native credential stores
   - Windows: Credential Manager
   - macOS: Keychain
   - Linux: Secret Service

2. **Access Control**:
   - Read-only access for gateway
   - Write-only for updates
   - Never in logs or responses

3. **Rotation**:
   - Support credential updates
   - Graceful failover during rotation
   - Audit log changes

### 7.2 Input Validation

1. **SSRF Protection**:
   - Validate all external URLs
   - Block private IP ranges
   - DNS rebinding protection

2. **Prompt Injection Prevention**:
   - Sanitize user content
   - Isolate system prompts
   - Validate structured outputs

3. **Content Filtering**:
   - Project-level restrictions
   - Provider-specific policies
   - Opt-in for sensitive data

## 8. Integration Strategy

### 8.1 Phase 1: Foundation

**Files to create:**
- `engine/ai_gateway/__init__.py`
- `engine/ai_gateway/gateway.py`
- `engine/ai_gateway/contracts.py`
- Database migrations

**Existing to extend:**
- `engine/llm/providers/base.py` - Add gateway interface
- `engine/database/models.py` - Add AI tables

### 8.2 Phase 2: Adapters

**New adapters:**
- Keep existing Ollama as primary
- Add OpenAI-compatible base
- Create provider-specific adapters

### 8.3 Phase 3: Routing

**Implement:**
- Provider registry
- Model catalog
- Routing engine
- Health monitor

### 8.4 Phase 4: Integration

**Migrate workflows:**
1. Story analysis
2. Script generation
3. Panel analysis
4. OCR correction

## 9. Performance Considerations

### 9.1 Caching

- Model catalog cache (5 min TTL)
- Health check results (30 sec TTL)
- Routing decisions (session cache)
- Cost estimates (per model)

### 9.2 Connection Pooling

- HTTP clients per provider
- Connection reuse
- Timeout management
- Retry with backoff

### 9.3 Async Design

- All operations async
- Non-blocking I/O
- Concurrent execution where safe
- Cancellation support

## 10. Monitoring & Observability

### 10.1 Metrics

- Request rate by provider/model
- Success/failure rates
- Latency percentiles
- Cost per request
- Fallback frequency
- Circuit breaker events

### 10.2 Logging

- Structured logs
- Correlation IDs
- No secrets in logs
- Audit trails

### 10.3 Diagnostics

- Routing explanations
- Provider health dashboard
- Cost analysis
- Performance profiling

## 11. Testing Strategy

### 11.1 Unit Tests

- Provider adapters (mocked HTTP)
- Routing algorithms
- Cost calculations
- Validation logic

### 11.2 Integration Tests

- End-to-end workflows
- Provider switching
- Fallback scenarios
- Circuit breaker behavior

### 11.3 Security Tests

- Credential leakage
- SSRF attempts
- Injection attacks
- Authorization bypass

## 12. Deployment Considerations

### 12.1 Configuration

- Environment-based config
- Feature flags
- Gradual rollout
- Kill switches

### 12.2 Migration

- Backward compatibility
- Dual-write period
- Data migration scripts
- Rollback plan

### 12.3 Monitoring

- Health checks
- Alert thresholds
- Performance baselines
- Error budgets

## Architecture Conclusion

The Universal AI Gateway architecture provides a production-ready, extensible platform for multi-provider AI integration while preserving existing functionality. The clean architecture ensures business workflows remain decoupled from provider specifics, enabling seamless provider switching and future expansion.
