# Configure AI Gateway Routing Engine

## Command
Use when configuring the routing engine for the Universal AI Gateway. <one-line behavior>

## Behavior
Configure the `RoutingEngine` (`engine/ai_gateway/routing/routing_engine.py`) which implements 7 routing strategies with full policy enforcement:

### Routing Strategies
1. **LOCAL_FIRST** - Prefer local Ollama; cloud only if local unavailable
2. **FREE_FIRST** - Only use free-tier models (free_tier=True)
3. **LOWEST_COST** - Minimize estimated cost across eligible models
4. **QUALITY_FIRST** - Select model with best quality evidence (benchmarks, evaluations)
5. **LOWEST_LATENCY** - Choose model with lowest observed average latency
6. **BALANCED** - Weighted scoring: quality(35%) + cost(25%) + latency(20%) + reliability(15%) + quota(5%)
7. **MANUAL** - User-specified model override; no automatic routing

### Routing Engine Process
1. Receive capability request from business workflow
2. Filter eligible providers/models based on policies
3. Exclude disabled/unconfigured providers
4. Exclude unavailable or incompatible models
5. Enforce context-window and modality constraints
6. Enforce privacy and data-transfer policies
7. Enforce free-only or paid authorization
8. Enforce project and global spending budgets
9. Check provider health and cooldown state (circuit breaker)
10. Account for rate limits and expected token usage
11. Rank eligible models using selected strategy
12. Execute preferred candidate
13. Validate the result
14. Trigger permitted fallback only when necessary
15. Persist attempt history, selected model, cost, and validation results

### Key Components
- **RoutingEngine** (`engine/ai_gateway/routing/routing_engine.py`) - Core routing logic
- **CircuitBreaker** (`engine/ai_gateway/monitoring/circuit_breaker.py`) - CLOSED/OPEN/HALF_OPEN states with cooldowns
- **RateLimiter** (`engine/ai_gateway/monitoring/rate_limiter.py`) - RPM, TPM, daily quotas, Retry-After
- **FallbackCoordinator** (`engine/ai_gateway/fallback/fallback_coordinator.py`) - Failure classification and fallback chain
- **BudgetEnforcer** (`engine/ai_gateway/billing/budget_enforcer.py`) - Global/project budgets, free-first policy, spending limits

### Routing Decision Output
`RoutingDecision` contains:
- `selected_provider`: The chosen provider ID
- `selected_model`: The chosen model ID or display name
- `strategy`: The routing strategy used
- `rejected_providers`: List of providers that were considered but rejected
- `reasoning`: Human-readable explanation of the routing decision
- `cost_estimate`: Estimated cost in USD for the request
- `latency_estimate`: Estimated latency in milliseconds
- `free_only_violation`: Whether the free-only policy was enforced
- `budget_violation`: Whether a budget constraint was hit
- `health_issues`: List of health-related warnings or concerns

## Configuration
No configuration file needed - routing engine reads from `provider_registry` and `model_registry` which are populated from the database.

## Pitfalls
- Forgetting to check circuit breaker state before executing requests
- Not checking rate limits before executing requests
- Forgetting to enforce free-only policy when `free_only=True`
- Not checking budget before executing expensive requests
- Using `MANUAL` strategy without a specific model specified
- Not having fallback strategies configured for critical workflows

## Integration
The routing engine is invoked via `adapter_factory.execute_request(provider_id, request)` which handles:
- Strategy selection
- Circuit breaker state checks
- Rate limit checks
- Fallback coordination
- Budget enforcement
- Attempt history recording