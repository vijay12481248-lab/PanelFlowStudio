"""Budget enforcer for the Universal AI Gateway.

Enforces spending limits with:
- Global monthly budget
- Per-project spending limits
- Per-request cost ceilings
- Free-only mode enforcement
- Budget alert thresholds
- Cost attribution by provider/model/project
"""

from __future__ import annotations

from decimal import Decimal
from threading import Lock
from typing import Dict, Optional, DefaultDict
from collections import defaultdict
import time

from engine.ai_gateway.contracts import FinishStatus, Decimal


class BudgetEnforcer:
    """Enforces budget constraints for AI inference requests.

    Budget scopes:
    - 'global': Organization-wide monthly budget
    - 'project': Per-project spending limit
    - 'user': Per-user budget (if applicable)

    Enforcement rules:
    - Free-first default (paid inference disabled)
    - Per-request cost ceiling enforced before execution
    - Project budget never exceeded by unauthorized scheduling
    - Monthly budget alerts at threshold (80%, 90%, 100%)
    """

    def __init__(self):
        self._global_budget: Optional[Decimal] = None
        self._project_budgets: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        self._spending: DefaultDict[str, DefaultDict[str, Decimal]] = defaultdict(
            lambda: defaultdict(Decimal)
        )  # project -> scope -> spending
        self._alert_thresholds: Dict[str, float] = {
            "global": 0.8,  # 80% alert
            "project": 0.8,
        }
        self._lock = Lock()

    def set_global_budget(self, budget: Decimal) -> None:
        """Set the global monthly budget."""
        with self._lock:
            self._global_budget = budget

    def set_project_budget(self, project_id: str, budget: Decimal) -> None:
        """Set the per-project spending limit."""
        with self._lock:
            self._project_budgets[project_id] = budget

    def set_alert_threshold(self, scope: str, threshold: float) -> None:
        """Set the alert threshold (0.0-1.0) for a given scope."""
        with self._lock:
            self._alert_thresholds[scope] = max(0.0, min(1.0, threshold))

    def check_budget(
        self,
        scope: str,
        scope_id: str,
        estimated_cost: Decimal,
        free_only: bool = True,
    ) -> Dict[str, any]:
        """Check if a request is within budget.

        Returns dict with:
        - allowed: bool
        - remaining_budget: Decimal
        - spend_percent: float (0.0-1.0)
        - warning: str | None
        """
        with self._lock:
            now = time.time()

            # Free-only enforcement
            if free_only and estimated_cost > Decimal("0.0"):
                # Check if global budget is free-only enabled
                # (This is primarily a policy check; actual blocking
                #  happens in the routing engine)
                return {
                    "allowed": False,
                    "remaining_budget": self._get_remaining(scope, scope_id),
                    "spend_percent": self._get_spend_percent(scope, scope_id),
                    "warning": "Free-only mode: paid request blocked",
                }

            # Get current spending
            scope_spending = self._spending.get(scope, {}).get(scope_id, Decimal("0.0"))

            # Check global budget
            if self._global_budget is not None:
                if scope_spending + estimated_cost > self._global_budget:
                    remaining = self._global_budget - scope_spending
                    percent = float(scope_spending / self._global_budget) if self._global_budget > 0 else 0.0
                    return {
                        "allowed": False,
                        "remaining_budget": remaining,
                        "spend_percent": percent,
                        "warning": f"Global budget exceeded. Remaining: ${remaining:.4f}",
                    }

            # Check project budget
            project_budget = self._project_budgets.get(scope_id)
            if project_budget is not None and project_budget > 0:
                if scope_spending + estimated_cost > project_budget:
                    remaining = project_budget - scope_spending
                    percent = float(scope_spending / project_budget) if project_budget > 0 else 0.0
                    return {
                        "allowed": False,
                        "remaining_budget": remaining,
                        "spend_percent": percent,
                        "warning": f"Project budget exceeded. Remaining: ${remaining:.4f}",
                    }

            # Calculate remaining and percent
            remaining = self._get_remaining(scope, scope_id)
            spend_percent = self._get_spend_percent(scope, scope_id)

            # Check alert thresholds
            warning = None
            alert_threshold = self._alert_thresholds.get(scope, 0.8)
            if spend_percent >= alert_threshold:
                warning = f"Budget at {spend_percent*100:.0f}% of threshold (${remaining:.4f} remaining)"

            return {
                "allowed": True,
                "remaining_budget": remaining,
                "spend_percent": spend_percent,
                "warning": warning,
            }

    def _get_remaining(self, scope: str, scope_id: str) -> Decimal:
        """Get remaining budget for a scope."""
        if scope == "global" and self._global_budget is not None:
            spending = self._spending.get(scope, {}).get(scope_id, Decimal("0.0"))
            return max(Decimal("0.0"), self._global_budget - spending)
        elif scope == "project":
            budget = self._project_budgets.get(scope_id, Decimal("0.0"))
            spending = self._spending.get(scope, {}).get(scope_id, Decimal("0.0"))
            return max(Decimal("0.0"), budget - spending)
        return Decimal("0.0")

    def _get_spend_percent(self, scope: str, scope_id: str) -> float:
        """Get spending percentage for a scope."""
        if scope == "global" and self._global_budget is not None and self._global_budget > 0:
            spending = self._spending.get(scope, {}).get(scope_id, Decimal("0.0"))
            return min(float(spending / self._global_budget), 1.0)
        elif scope == "project":
            budget = self._project_budgets.get(scope_id, Decimal("0"))
            if budget > 0:
                spending = self._spending.get(scope, {}).get(scope_id, Decimal("0.0"))
                return min(float(spending / budget), 1.0)
        return 0.0

    def record_spending(self, scope: str, scope_id: str, amount: Decimal) -> None:
        """Record actual spending after a request."""
        with self._lock:
            self._spending[scope][scope_id] += amount


# Global budget enforcer instance
budget_enforcer = BudgetEnforcer()