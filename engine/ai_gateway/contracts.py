from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CapabilityType(str, Enum):
    TEXT_GENERATE = "text.generate"
    TEXT_REASON = "text.reason"
    TEXT_STRUCTURED = "text.structured"
    TEXT_TRANSLATE = "text.translate"
    TEXT_SUMMARIZE = "text.summarize"
    VISION_UNDERSTAND = "vision.understand"
    VISION_OCR_ASSIST = "vision.ocr_assist"
    VISION_PANEL_ANALYSIS = "vision.panel_analysis"
    VISION_CONTINUITY_CHECK = "vision.continuity_check"
    AUDIO_TRANSCRIBE = "audio.transcribe"
    AUDIO_SYNTHESIZE = "audio.synthesize"
    AUDIO_ANALYZE = "audio.analyze"
    MUSIC_GENERATE = "music.generate"
    IMAGE_GENERATE = "image.generate"
    IMAGE_EDIT = "image.edit"
    VIDEO_GENERATE = "video.generate"
    EMBEDDINGS_GENERATE = "embeddings.generate"


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


class CapabilitySet(BaseModel):
    supports_streaming: bool = True
    supports_tools: bool = False
    supports_structured: bool = True
    supports_vision: bool = False
    supports_audio: bool = False
    supports_images: bool = False
    supports_video: bool = False
    supports_embeddings: bool = False
    max_context_window: int = 8192
    max_output_tokens: int = 4096


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
    auth_type: str = "api_key"  # api_key, token, none
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
    free_only: bool = True  # Free-first / free-only by default per rules
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
    cost_confidence: str = "HIGH"  # HIGH, MEDIUM, LOW
    latency_ms: int = 0
    finish_reason: Optional[str] = None
    validation_status: str = "SUCCESS"
    error_info: Optional[Dict[str, Any]] = None
    provider_request_id: Optional[str] = None
    trace_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
