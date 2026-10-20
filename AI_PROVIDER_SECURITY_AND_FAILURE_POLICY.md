# AI Provider Security and Failure Policy

**Document version:** 1.0  
**Date:** 2026-10-20  
**Scope:** Security hardening, failure modes, error handling, and recovery policies for Universal AI Gateway

## 1. Security Policy

### 1.1 Credential Management and Storage

1. **OS-Native Credential Storage**:
   - Provider API keys and sensitive tokens must be stored in OS-native secure facilities (Windows Credential Manager, macOS Keychain, Linux Secret Service).
   - SQLite stores only non-sensitive configuration, provider IDs, and credential references (UUIDs pointing to the secure store).
   - **Never store plaintext API keys in the project database.**

2. **Memory and Logging Hygiene**:
   - API keys, authorization headers, bearer tokens, and sensitive request payloads must **never** be written to log files, telemetry records, or error diagnostics.
   - All logging handlers must sanitize headers and payload secrets before output.
   - API GET endpoints (`/api/ai/providers`) must return boolean flags (e.g., `has_api_key: true`) rather than masked or plaintext keys.
   - Secret updates must use write-only operations (`PUT`/`PATCH` with secret payload).

3. **Credential Rotation and Removal**:
   - Support seamless rotation of API keys without restarting the desktop application.
   - Credential removal must securely purge secrets from the OS store and dissociate references in SQLite.

### 1.2 Network Security and SSRF Prevention

1. **Endpoint Validation**:
   - All external provider endpoints and custom URLs must be validated against SSRF (Server-Side Request Forgery) attacks.
   - Reject private IP ranges, loopback addresses (except trusted local runtimes like Ollama on `127.0.0.1`), link-local addresses, and cloud metadata endpoints (`169.254.169.254`, `metadata.google.internal`).
   - Require HTTPS for all external endpoints by default. Loopback HTTP is permitted exclusively for local runtimes (Ollama, LM Studio).
   - Prevent DNS rebinding attacks by validating resolved IP literals against allowed ranges.

2. **Data Exfiltration Prevention**:
   - Projects configured with strict privacy settings (`local_only: true`) must be blocked from transmitting content (text, images, audio) to cloud providers.
   - Gateway must verify project-level privacy constraints before routing requests.

### 1.3 Prompt Injection and Content Sanitization

1. **Untrusted Content Isolation**:
   - Ingested manga/manhua text, OCR outputs, scraped web content, and user-uploaded files must be treated as untrusted data.
   - Wrap untrusted content in strict XML/Markdown delimiters or structured data blocks to prevent prompt injection attacks from altering gateway routing rules, leaking secrets, or invoking privileged tools.

2. **Output Validation**:
   - Structured outputs must be strictly validated against Pydantic schemas.
   - Reject responses containing unexpected control characters, script injections, or malformed JSON structures.

---

## 2. Error Classification and Handling Policy

### 2.1 Error Hierarchy

The gateway defines a standardized error hierarchy to govern retry, fallback, and circuit-breaker behavior:

```
AIProviderError (Base)
├── RateLimitError (HTTP 429, ResourceExhausted)
├── TransientProviderError (HTTP 5xx, NetworkTimeout, DNSFailure)
├── AuthenticationError (HTTP 401, HTTP 403, InvalidKey)
├── BudgetExhaustedError (InsufficientBalance, CreditExhausted)
├── UnsupportedCapabilityError (CapabilityNotSupported)
├── ValidationError (SchemaFailure, MalformedResponse)
└── RequestCancelledError (UserCancelled, TimeoutCancelled)
```

### 2.2 Error Response Policies

#### A. Rate Limited (HTTP 429 / Resource Exhausted)
- **Action**: Parse `Retry-After` header or `X-RateLimit-Reset` metadata. Apply bounded exponential backoff with jitter.
- **Circuit Breaker**: Do not trip main circuit breaker for transient rate limits unless persistent.
- **Fallback**: Immediately select another eligible provider/model in the fallback chain.

#### B. Temporary Provider Failure (HTTP 5xx / Network Errors / Timeouts)
- **Action**: Apply bounded exponential backoff (e.g., base 1s, max 10s, factor 2.0) with random jitter.
- **Circuit Breaker**: Increment failure counter. If failure threshold (e.g., 5 consecutive failures) is reached, trip circuit breaker to `OPEN` state.
- **Cooldown**: Associate cooldown scope (provider account, credential, model) for a fixed window (e.g., 60 seconds).
- **Fallback**: Trigger fallback to secondary provider/model.

#### C. Authentication Failure (HTTP 401 / HTTP 403)
- **Action**: **Never retry** the same invalid credential repeatedly.
- **Notification**: Log actionable configuration error for the user ("API key invalid or expired for provider X").
- **Fallback**: Permit fallback to a different authorized provider *only* if policy allows (e.g., fallback from paid OpenAI to free Ollama).

#### D. Insufficient Balance / Credit Exhausted
- **Action**: Mark affected credential/account as budget or credit exhausted.
- **Restriction**: Do not treat as a transient network outage. Do not automatically purchase credits or authorize paid overrides.
- **Fallback**: Route remaining requests to free-tier or local providers.

#### E. Unsupported Capability
- **Action**: Exclude unsuitable model/provider from candidate pool.
- **Restriction**: Never substitute a text-only model for required vision understanding or structured output. Preserve original task constraints.

#### F. Validation Failure (Schema / Quality)
- **Action**: Distinguish schema failure, incomplete response, and policy refusal.
- **Repair Strategy**: Use a single structured repair attempt passing the validation error back to the model. If repair fails, trigger fallback or raise descriptive error.

#### G. Cancellation
- **Action**: Propagate cancellation tokens through pending requests and running tasks.
- **Restriction**: **Never continue paid fallback** after user cancellation or disconnect.

---

## 3. Non-Idempotent and Streaming Safety Policy

### 3.1 Costly Operations (Image, Video, Audio, Music)

1. **Idempotency Keys**:
   - Use idempotency keys for upstream provider requests where supported (e.g., OpenAI, Anthropic).
   - For providers without native idempotency support, generate deterministic request hashes and check the request audit log before re-submitting.

2. **Timeout and Interruption Recovery**:
   - Never blindly retry a request after a timeout when the upstream provider may already have accepted and executed an expensive job (image generation, video rendering).
   - Persist external task IDs in the database and poll/reconcile their status rather than issuing duplicate generation requests.
   - Do not automatically regenerate costly artifacts merely because a connection was interrupted.

3. **Streaming Safety**:
   - Handle partial output correctly with chunk buffering.
   - Detect streaming interruptions (premature EOS).
   - **Never concatenate outputs from different models** into a single answer.
   - Resume or regenerate only through an explicit safe policy.
   - Maintain durable job states across desktop engine restarts.

---

## 4. Billing, Budget, and Free-Tier Policy

### 4.1 Cost Control Rules

1. **Free-First Default**:
   - Paid inference is **disabled by default**. New installations operate in `FREE_ONLY` or `LOCAL_FIRST` mode unless explicit user authorization is granted.
   - Free-tier usage must respect actual provider rate limits and terms of service. Do not invent exact remaining quotas where the provider does not expose them.

2. **Budget Ceilings**:
   - Enforce per-request cost ceilings, per-project spending limits, and global monthly budgets.
   - Compute cost estimates *before* executing expensive tasks. If estimated cost exceeds budget, block execution and prompt the user.
   - Display estimated values clearly as estimates ("Estimated cost: $0.02 USD").

3. **Quota Protection**:
   - Do not misuse multiple keys or accounts to evade provider quotas or rate limits.
   - Respect provider-specific concurrency constraints.

---

## 5. Audit and Diagnostics Policy

### 5.1 Telemetry and Traceability

1. **Audit Logging**:
   - Record every inference request, attempt, provider used, latency, token count, estimated/actual cost, and validation result in `ai_inference_requests` and `ai_inference_attempts`.
   - **Redaction**: Strip raw prompts, personal user data, and private story contents from telemetry logs by default. Retain metadata, error codes, and sanitized summaries.

2. **Diagnostic Explanations**:
   - Provide clear routing explanations in diagnostics ("Model Qwen3.5:9b selected via LOCAL_FIRST strategy; OpenAI excluded due to free-only policy").
   - Expose cooldown states, circuit breaker statuses, and error categories in the developer diagnostics panel.

## Policy Enforcement

All gateway adapters, routing policies, and workflow integrations must strictly adhere to this security and failure policy. Automated tests in Phase 8 will verify compliance across all 25 required test scenarios.
