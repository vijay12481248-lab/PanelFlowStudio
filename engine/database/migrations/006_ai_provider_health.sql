-- PanelFlow AI Gateway - Database Migration 006
-- Provider Health Table
-- Created: 2026-10-20

CREATE TABLE IF NOT EXISTS ai_provider_health (
    provider_config_id TEXT PRIMARY KEY,
    health_status TEXT DEFAULT 'HEALTHY',
    last_check DATETIME,
    success_rate DECIMAL(5, 4) DEFAULT 1.0,
    avg_latency_ms INTEGER DEFAULT 0,
    cooldown_until DATETIME,
    failure_count INTEGER DEFAULT 0,
    circuit_state TEXT DEFAULT 'CLOSED',
    last_success DATETIME,
    last_failure DATETIME,
    FOREIGN KEY(provider_config_id) REFERENCES ai_provider_configs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_provider_health_status ON ai_provider_health(health_status);
CREATE INDEX IF NOT EXISTS idx_ai_provider_health_circuit ON ai_provider_health(circuit_state);
