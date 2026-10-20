-- PanelFlow AI Gateway - Database Migration 007
-- Usage Records Table
-- Created: 2026-10-20

CREATE TABLE IF NOT EXISTS ai_usage_records (
    id TEXT PRIMARY KEY,
    provider_config_id TEXT NOT NULL,
    model_id TEXT,
    project_id TEXT,
    request_count INTEGER DEFAULT 0,
    token_count INTEGER DEFAULT 0,
    cost_total DECIMAL(10, 6) DEFAULT 0.0,
    period_start DATETIME NOT NULL,
    period_end DATETIME NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(provider_config_id) REFERENCES ai_provider_configs(id) ON DELETE CASCADE,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_usage_records_provider ON ai_usage_records(provider_config_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_records_project ON ai_usage_records(project_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_records_period ON ai_usage_records(period_start, period_end);
