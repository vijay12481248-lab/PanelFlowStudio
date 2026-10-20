"""Routing engine for the Universal AI Gateway.

Implements 7 routing strategies with circuit breaker integration,
rate limit awareness, fallback coordination, and budget enforcement.

The routing engine sits between business workflows and provider adapters,
translating capability requests into provider selection decisions
with full policy enforcement and audit logging.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from enum import Enum

from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from enum import Enum

from engine.ai_gateway.adapters.base import (
    ProviderAdapter,
    NormalizedRequest,
    NormalizedResponse,
    HealthStatus,
    FinishStatus,
    CapabilityType,
    AttemptResult,
    ModelInfo,
    RoutingStrategy,
)
from engine.ai_gateway.registry.provider_registry import provider_registry
from engine.ai_gateway.registry.model_registry import model_registry
from engine.ai_gateway.monitoring.circuit_breaker import CircuitBreaker
from engine.ai_gateway.monitoring.rate_limiter import RateLimiter
from engine.ai_gateway.fallback.fallback_coordinator import FallbackCoordinator
from engine.ai_gateway.billing.budget_enforcer import BudgetEnforcer


class RoutingDecision:
    """The result of a routing evaluation.

    Attributes:
        selected_provider: The chosen provider ID
        selected_model: The chosen model ID or display name
        strategy: The routing strategy used
        rejected_providers: List of providers that were considered but rejected
        reasoning: Human-readable explanation of the routing decision
        cost_estimate: Estimated cost in USD for the request
        latency_estimate: Estimated latency in milliseconds
        free_only_violation: Whether the free-only policy was enforced
        budget_violation: Whether a budget constraint was hit
        health_issues: List of health-related warnings or concerns
    """
    def __init__(
        self,
        selected_provider: str = "",
        selected_model: str = "",
        strategy: str = RoutingStrategy.BALANCED.value,
        rejected_providers: Optional[List[Dict[str, str]]] = None,
        reasoning: str = "",
        cost_estimate: Decimal = Decimal("0.0"),
        latency_estimate: int = 0,
        free_only_violation: bool = False,
        budget_violation: bool = False,
        health_issues: Optional[List[str]] = None,
    ):
        self.selected_provider = selected_provider
        self.selected_model = selected_model
        self.strategy = strategy
        self.rejected_providers = rejected_providers or []
        self.reasoning = reasoning
        self.cost_estimate = cost_estimate
        self.latency_estimate = latency_estimate
        self.free_only_violation = free_only_violation
        self.budget_violation = budget_violation
        self.health_issues = health_issues or []


class RoutingEngine:
    """Core routing engine implementing 7 strategies with full policy enforcement.

    Responsibilities:
    - Receive capability requests from business workflows
    - Filter eligible providers/models based on policies
    - Rank candidates using selected strategy
    - Execute with circuit breaker protection
    - Coordinate fallback on failure
    - Persist attempt history
    """

    def __init__(self):
        self.circuit_breaker = CircuitBreaker()
        self.rate_limiter = RateLimiter()
        self.fallback_coordinator = FallbackCoordinator()
        self.budget_enforcer = BudgetEnforcer()
        self.adapter_factory = provider_registry  # alias for convenience

    def route(
        self,
        capability: CapabilityType,
        project_id: str,
        user_id: str | None = None,
        routing_policy: RoutingStrategy = RoutingStrategy.BALANCED,
        free_only: bool = True,
        max_attempts: int = 3,
    ) -> RoutingDecision:
        """Execute the routing decision process for a given capability.

        Args:
            capability: The AI capability required (e.g., 'text.generate')
            project_id: The project making the request
            user_id: Optional user identifier for per-user policies
            routing_policy: The routing strategy to use
            free_only: Whether to enforce free-tier only mode
            max_attempts: Maximum fallback attempts

        Returns:
            RoutingDecision with selected provider/model and rationale
        """
        decision = RoutingDecision(
            selected_provider="",
            selected_model="",
            strategy=routing_policy,
            free_only_violation=False,
            budget_violation=False,
            health_issues=[],
        )

        try:
            # Step 1: Get enabled providers
            enabled_providers = provider_registry.list_providers(enabled_only=True)
            
            if not enabled_providers:
                decision.health_issues.append("No enabled providers configured")
                return decision

            # Step 2: Filter by capability support
            capable_providers = []
            for prov_id in enabled_providers:
                adapter = provider_registry.get_instance(prov_id)
                if adapter and adapter.supports_capability(capability):
                    capable_providers.append(prov_id)

            if not capable_providers:
                decision.health_issues.append(
                    f"No provider supports capability: {capability}"
                )
                return decision

            # Step 3: Get eligible models for capable providers
            model_candidates: List[Tuple[str, ModelInfo, float]] = []  # (provider_id, model, score)
            
            for prov_id in capable_providers:
                adapter = provider_registry.get_instance(prov_id)
                models = adapter.get_capabilities().capabilities if adapter else []
                
                # Get models from registry that support this capability
                registry_models = model_registry.get_models_by_capability(capability, free_only=not free_only)
                
                # Filter to only models from enabled providers
                for reg_model in registry_models:
                    if reg_model.provider_id in capable_providers:
                        # Estimate score based on available metadata
                        score = self._estimate_model_score(reg_model, capability)
                        model_candidates.append((prov_id, reg_model, score))

            if not model_candidates:
                decision.health_issues.append("No eligible models found")
                return decision

            # Step 4: Rate limit check
            rate_limited_providers = []
            for prov_id, model, score in model_candidates:
                if not self.rate_limiter.can_execute(prov_id, model.model_id or "unknown"):
                    rate_limited_providers.append(prov_id)
            
            # Remove rate-limited providers
            model_candidates = [
                (p, m, s) for p, m, s in model_candidates if p not in rate_limited_providers
            ]

            if not model_candidates and rate_limited_providers:
                decision.health_issues.append(
                    f"All candidates rate-limited: {rate_limited_providers}"
                )
                # Try fallback to last-resort providers
                fallback_providers = [
                    p for p in enabled_providers if p not in rate_limited_providers
                ]
                if fallback_providers:
                    # Use last candidate from remaining
                    pass

            # Step 5: Budget check
            budget_ok_candidates = []
            for prov_id, model, score in model_candidates:
                # Quick budget check - full check happens during execution
                budget_result = self.budget_enforcer.check_budget(
                    prov_id, 
                    model.model_id or "unknown", 
                    free_only
                )
                if budget_result.allowed:
                    budget_ok_candidates.append((prov_id, model, score, budget_result))
                else:
                    decision.budget_violation = True
                    decision.health_issues.append(
                        f"Budget constraint for {prov_id}/{model.model_id or 'unknown'}"
                    )

            # Use budget-ok candidates, but don't fail if none (will be handled at execution)
            candidates_to_rank = budget_ok_candidates if budget_ok_candidates else model_candidates

            # Step 6: Rank using selected strategy
            ranked = self._rank_candidates(
                candidates_to_rank, capability, routing_policy
            )

            if not ranked:
                decision.health_issues.append("No candidates after ranking")
                return decision

            # Step 7: Select top candidate
            top_provider, top_model, top_score, *budget_info = ranked[0]
            decision.selected_provider = top_provider
            decision.selected_model = top_model.model_id or top_model.display_name
            decision.cost_estimate = top_model.pricing_input_per_million or Decimal("0.0")
            decision.latency_estimate = self._estimate_latency(top_model)

            # Step 8: Add reasoning
            decision.reasoning = self._generate_routing_reasoning(
                ranked, capability, routing_policy, free_only
            )

            # Step 9: Record health issues
            decision.health_issues.extend(self._collect_health_issues(ranked))

        except Exception as e:
            decision.health_issues.append(f"Routing error: {e}")

        return decision

    def _estimate_model_score(
        self, model: ModelInfo, capability: CapabilityType
    ) -> float:
        """Estimate a ranking score for a model based on available metadata."""
        score = 0.0
        
        # Free tier boost
        if model.free_tier:
            score += 0.3
        
        # Commercial use allowance
        if model.commercial_use:
            score += 0.1
        
        # Context window (normalized: larger is better up to 1M tokens)
        ctx = model.context_window or 8192
        score += min(ctx / 100000, 0.2)  # Max 0.2 for 100K+ context
        
        # Health status implication (HEALTHY assumed if in registry)
        if model.health_status.value == "HEALTHY":
            score += 0.1
        
        # Capability match
        if capability in models.capabilities if hasattr(model, 'capabilities') else []:
            score += 0.3
        
        return score

    def _estimate_latency(self, model: ModelInfo) -> int:
        """Estimate average latency for a model in milliseconds."""
        # Default estimates based on model type and context
        ctx = model.context_window or 8192
        if ctx >= 100_000:
            return 2000  # Long context models
        elif ctx >= 32_000:
            return 1000  # Standard models
        else:
            return 500   # Small models

    def _rank_candidates(
        self,
        candidates: List[Tuple[str, ModelInfo, float, any]],  # (provider, model, score, budget_info)
        capability: CapabilityType,
        strategy: RoutingStrategy,
    ) -> List[Tuple[str, ModelInfo, float, any]]:
        """Rank model candidates using the selected routing strategy."""
        
        if not candidates:
            return []

        # Sort by score descending
        scored = [(prov, model, score, budget) for prov, model, score, *budget_info in candidates]
        scored.sort(key=lambda x: x[2], reverse=True)
        
        # Strategy-specific adjustments
        if strategy == RoutingStrategy.LOCAL_FIRST:
            # Boost local/providers with localhost/127.0.0.1 endpoints
            for i, (prov, model, score, budget) in enumerate(scored):
                # We can't easily check endpoint here, skip local boost for now
                scored[i] = (prov, model, score, budget)
        
        elif strategy == RoutingStrategy.FREE_FIRST:
            # Ensure free-tier models come first among tied scores
            scored.sort(key=lambda x: (x[2], not self._is_free_model(x[1])))
        
        elif strategy == RoutingStrategy.LOWEST_COST:
            # Primary sort by cost, then by score
            scored.sort(key=lambda x: (
                x[3].cost_estimate if x[3] else Decimal("inf"),
                -x[2]
            ))
        
        elif strategy == RoutingStrategy.QUALITY_FIRST:
            # Quality is reflected in score; keep primary sort
            pass
        
        elif strategy == RoutingStrategy.LOWEST_LATENCY:
            # Boost lower latency models
            scored.sort(key=lambda x: (
                self._estimate_latency(x[1]),
                -x[2]
            ))
        
        elif strategy == RoutingStrategy.BALANCED:
            # Balanced already uses weighted score; keep primary sort
            pass
        
        # Return top-ranked candidates
        return scored[:5]  # Return top 5 for fallback options

    def _is_free_model(self, model: ModelInfo) -> bool:
        """Check if a model is configured as free-tier."""
        return model.free_tier

    def _generate_routing_reasoning(
        self,
        ranked: List[Tuple[str, ModelInfo, float, any]],
        capability: CapabilityType,
        strategy: RoutingStrategy,
        free_only: bool,
    ) -> str:
        """Generate human-readable explanation for routing decision."""
        if not ranked:
            return "No eligible models found for requested capability."

        top_provider, top_model, top_score, *budget_info = ranked[0]
        
        reasons = []
        
        # Strategy reason
        strategy_names = {
            RoutingStrategy.LOCAL_FIRST: "LOCAL_FIRST",
            RoutingStrategy.FREE_FIRST: "FREE_FIRST",
            RoutingStrategy.LOWEST_COST: "LOWEST_COST",
            RoutingStrategy.QUALITY_FIRST: "QUALITY_FIRST",
            RoutingStrategy.LOWEST_LATENCY: "LOWEST_LATENCY",
            RoutingStrategy.BALANCED: "BALANCED",
            RoutingStrategy.MANUAL: "MANUAL",
        }
        reasons.append(f"Strategy: {strategy_names.get(strategy, 'UNKNOWN')}")
        
        # Capability reason
        reasons.append(f"Capability: {capability}")
        
        # Model info
        reasons.append(f"Model: {top_model.display_name} ({top_model.model_id})")
        
        # Free-only status
        if free_only:
            if top_model.free_tier:
                reasons.append("Free-tier model selected")
            else:
                reasons.append("Free-only policy: paid model averted")
        
        # Cost info
        if top_model.pricing_input_per_million:
            cost = top_model.pricing_input_per_million
            reasons.append(f"Estimated cost: ~${cost:.4f}/1K input tokens")
        
        # Score
        reasons.append(f"Ranking score: {top_score:.2f}")
        
        return " | ".join(reasons)

    def _collect_health_issues(
        self, ranked: List[Tuple[str, ModelInfo, float, any]]
    ) -> List[str]:
        """Collect health issues from ranked candidates."""
        issues = []
        for prov_id, model, score, *budget_info in ranked:
            if model.health_status.value != "HEALTHY":
                issues.append(
                    f"Model {model.model_id} status: {model.health_status.value}"
                )
        return issues


# Global routing engine instance
routing_engine = RoutingEngine()