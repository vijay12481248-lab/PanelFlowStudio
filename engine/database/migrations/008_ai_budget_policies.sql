-- PanelFlow AI Gateway - Database Migration 008
-- Budget Policies Table
-- Created: 2026-10-20

CREATE TABLE IF NOT EXISTS ai_budget_policies (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL, -- 'global', 'project', 'user'
    scope_id TEXT,
    monthly_budget DECIMAL(10, 2),
    daily_budget DECIMAL(10, 2),
    free_only BOOLEAN DEFAULT TRUE,
    paid_authorized BOOLEAN DEFAULT FALSE,
    alert_threshold DECIMAL(5, 4) DEFAULT 0.8,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_budget_policies_scope ON ai_budget_policies(scope, scope_id);
