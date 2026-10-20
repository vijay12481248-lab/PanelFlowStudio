-- PanelFlow AI Gateway - Database Migration 004
-- Inference Requests Table
-- Created: 2026-10-20

CREATE TABLE IF NOT EXISTS ai_inference_requests (
    id TEXT PRIMARY KEY,
    workflow_job_id TEXT,
    project_id TEXT,
    capability TEXT NOT NULL,
    routing_profile_id TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    request_data JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(routing_profile_id) REFERENCES ai_routing_profiles(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_inference_requests_project ON ai_inference_requests(project_id);
CREATE INDEX IF NOT EXISTS idx_ai_inference_requests_job ON ai_inference_requests(workflow_job_id);
CREATE INDEX IF NOT EXISTS idx_ai_inference_requests_capability ON ai_inference_requests(capability);
CREATE INDEX IF NOT EXISTS idx_ai_inference_requests_status ON ai_inference_requests(status);
