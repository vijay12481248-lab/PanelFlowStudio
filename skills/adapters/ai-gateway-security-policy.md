# AI Gateway Security and Failure Policy

## Command
Use when enforcing security policies and failure handling for the Universal AI Gateway. <one-line behavior>

## Behavior
Enforce the security and failure policies defined in `AI_PROVIDER_SECURITY_AND_FAILURE_POLICY.md`. The gateway must adhere to:

### Credential Management
- Store API keys and sensitive tokens in OS-native secure facilities (Windows Credential Manager, macOS Keychain, Linux Secret Service)
- SQLite stores only non-sensitive configuration, provider IDs, and credential references (UUIDs pointing to the secure store)
- Never store plaintext API keys in the project database
- API GET endpoints must return boolean flags (e.g., `has_api_key: true`) rather than masked or plaintext keys
- Secret updates must use write-only operations (`PUT`/`PATCH` with secret payload)
- Never write API keys, authorization headers, sensitive request contents, or hidden authentication data to log files, telemetry records, or error diagnostics
- All logging handlers must sanitize headers and payload secrets before output

### SSRF Prevention
- Reject private IP ranges, loopback addresses (except trusted local runtimes like Ollama on `127.0.0.1`), link-local addresses, and cloud metadata endpoints (`169.254.169.254`, `metadata.google.internal`)
- Require HTTPS for all external endpoints by default. Loopback HTTP is permitted exclusively for local runtimes (Ollama, LM Studio).
- Prevent DNS rebinding attacks by validating resolved IP literals against allowed ranges

### Prompt Injection Prevention
- Treat ingested manga/manhua text, OCR outputs, scraped web content, and user-uploaded files as untrusted data
- Wrap untrusted content in strict XML/Markdown delimiters or structured data blocks to prevent prompt injection from altering routing rules, leaking secrets, or invoking privileged tools
- Validate structured outputs strictly against Pydantic schemas
- Reject responses containing unexpected control characters, script injections, or malformed JSON structures

### Error Classification and Handling
#### Rate Limited (HTTP 429 / Resource Exhausted)
- Parse `Retry-After` header or `X-RateLimit-Reset` metadata
- Apply bounded exponential backoff with jitter
- Do not trip main circuit breaker for transient rate limits unless persistent
- Immediately select another eligible provider in the fallback chain

#### Temporary Provider Failure (HTTP 5xx / Network Errors / Timeouts)
- Apply bounded exponential backoff (base 1s, max 10s, factor 2.0) with random jitter
- Trip circuit breaker after 5 consecutive failures
- Circuit breaker cooldown: 60 seconds with automatic transition to HALF_OPEN
- Immediately select another eligible provider in the fallback chain

#### Authentication Failure (HTTP 401 / HTTP 403)
- Never retry the same invalid credential repeatedly
- Log actionable configuration error: "API key invalid or expired for provider X"
- Permit fallback to a different authorized provider only if policy allows

#### Insufficient Balance
- Mark affected credential/account as budget or credit exhausted
- Do not treat as a transient network outage
- Do not automatically purchase credits or authorize paid overrides

#### Unsupported Capability
- Exclude unsuitable model/provider from candidate pool
- Never substitute a text-only model for required vision understanding or structured output
- Preserve original task constraints

#### Validation Failure
- Distinguish schema failure, incomplete response, policy refusal, and semantic quality failure
- Use a single structured repair attempt passing the validation error back to the model
- If repair fails, trigger fallback or raise descriptive error

#### Cancellation
- Propagate cancellation tokens through pending requests and running tasks
- Never continue paid fallback after user cancellation or disconnect

### Non-Idempotent and Streaming Safety
- Never blindly retry a request after a timeout when the upstream provider may already have accepted the job
- Persist external task IDs and poll/reconcile their status
- Use idempotency keys where supported
- Never concatenate outputs from different models into one answer
- Resume or regenerate only through an explicit safe policy
- Maintain durable job states across desktop engine restarts

### Budget and Free-Tier Policy
- Free-first default: paid inference disabled by default
- Per-request cost ceiling, per-project spending limit, global monthly budget
- Compute cost estimates *before* executing expensive tasks
- Block execution if estimated cost exceeds budget
- Display estimated values clearly as estimates ("Estimated cost: $0.02 USD")
- Do not misuse multiple keys or accounts to evade provider quotas or rate limits