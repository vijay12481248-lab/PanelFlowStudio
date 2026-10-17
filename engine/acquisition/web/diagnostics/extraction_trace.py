"""
Structured extraction trace and sanitization for observable, debuggable acquisition runs.
"""
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

SECRET_QUERY_REGEX = re.compile(r"([?&](?:token|key|auth|api_key|password|sig)=)[^&]+", re.IGNORECASE)


def sanitize_url(url: str) -> str:
    """Strip authentication tokens, secret keys, or passwords from logged URLs."""
    if not url:
        return ""
    return SECRET_QUERY_REGEX.sub(r"\1[REDACTED]", url)


class TraceStep(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    strategy: str
    status: str
    candidate_count: int = 0
    confidence: float = 0.0
    elapsed_ms: float = 0.0
    message: str = ""
    diagnostics: Dict[str, Any] = Field(default_factory=dict)


class ExtractionTrace:
    """
    Maintains a sanitized chronological audit trail of all extraction attempts.
    """

    def __init__(self, target_url: str):
        self.target_url = sanitize_url(target_url)
        self.start_time = datetime.now(timezone.utc)
        self.steps: List[TraceStep] = []
        self.warnings: List[str] = []
        self.final_status: Optional[str] = None

    def record_step(
        self,
        strategy: str,
        status: str,
        candidate_count: int = 0,
        confidence: float = 0.0,
        elapsed_ms: float = 0.0,
        message: str = "",
        diagnostics: Optional[Dict[str, Any]] = None,
    ):
        step = TraceStep(
            strategy=strategy,
            status=status,
            candidate_count=candidate_count,
            confidence=confidence,
            elapsed_ms=elapsed_ms,
            message=message,
            diagnostics=diagnostics or {},
        )
        self.steps.append(step)

    def add_warning(self, warning: str):
        self.warnings.append(warning)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_url": self.target_url,
            "steps": [s.model_dump() for s in self.steps],
            "warnings": self.warnings,
            "final_status": self.final_status,
            "total_elapsed_ms": round(
                (datetime.now(timezone.utc) - self.start_time).total_seconds() * 1000, 2
            ),
        }
