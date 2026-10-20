-- PanelFlow AI Gateway - Database Migration 005
-- Inference Attempts Table
-- Created: 2026-10-20

CREATE TABLE IF NOT EXISTS ai_inference_attempts (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    provider_config_id TEXT,
    model_id TEXT,
    status TEXT NOT NULL,
    cost_estimate DECIMAL(10, 6),
    cost_actual DECIMAL(10, 6),
    latency_ms INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    error_code TEXT,
    error_message TEXT,
    attempt_number INTEGER DEFAULT 1,
    provider_request_id TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(request_id) REFERENCES ai_inference_requests(id) ON DELETE CASCADE,
    FOREIGN KEY(provider_config_id) REFERENCES ai_provider_configs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_inference_attempts_request ON ai_inference_attempts(request_id);
CREATE INDEX IF NOT EXISTS idx_ai_inference_attempts_provider ON ai_inference_attempts(provider_config_id);
CREATE INDEX IF NOT EXISTS idx_ai_inference_attempts_model ON ai_inference_attempts(model_id);
