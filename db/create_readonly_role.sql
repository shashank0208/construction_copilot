-- create_readonly_role.sql
-- Creates a read-only PostgreSQL role for the agent and views that hide PII columns.
-- Run as superuser: psql -U postgres -d construction_risk -f db/create_readonly_role.sql

-- ============================================================
-- 1. Read-only role
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'copilot_reader') THEN
        CREATE ROLE copilot_reader WITH LOGIN PASSWORD 'copilot_readonly';
    END IF;
END
$$;

-- Revoke everything first, then grant only what's needed
REVOKE ALL ON SCHEMA public FROM copilot_reader;
GRANT USAGE ON SCHEMA public TO copilot_reader;

-- Revoke direct table access (agent uses views instead)
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM copilot_reader;

-- Set default statement timeout to 5 seconds for this role
ALTER ROLE copilot_reader SET statement_timeout = '5s';

-- ============================================================
-- 2. Views that hide PII columns
-- ============================================================

-- projects: hide client_name, project_manager
CREATE OR REPLACE VIEW v_projects AS
SELECT
    project_id,
    project_name,
    project_code,
    status,
    project_type,
    region,
    -- client_name HIDDEN (PII)
    -- project_manager HIDDEN (PII)
    description,
    planned_budget,
    actual_cost,
    start_date,
    planned_end_date,
    actual_end_date,
    percent_complete,
    created_at,
    updated_at
FROM projects;

-- resources: hide email, phone
CREATE OR REPLACE VIEW v_resources AS
SELECT
    resource_id,
    resource_name,
    resource_type,
    category,
    hourly_rate,
    daily_rate,
    -- email HIDDEN (PII)
    -- phone HIDDEN (PII)
    certifications,
    is_active
FROM resources;

-- milestones: no PII, full access
CREATE OR REPLACE VIEW v_milestones AS
SELECT * FROM milestones;

-- cost_items: no PII, full access
CREATE OR REPLACE VIEW v_cost_items AS
SELECT * FROM cost_items;

-- risk_assessments: hide identified_by
CREATE OR REPLACE VIEW v_risk_assessments AS
SELECT
    risk_id,
    project_id,
    risk_category,
    risk_description,
    probability,
    impact,
    risk_score,
    mitigation_strategy,
    status,
    -- identified_by HIDDEN (PII)
    identified_date,
    review_date,
    notes
FROM risk_assessments;

-- change_orders: hide requested_by, approved_by
CREATE OR REPLACE VIEW v_change_orders AS
SELECT
    change_order_id,
    project_id,
    change_order_number,
    title,
    description,
    cost_impact,
    schedule_impact_days,
    status,
    submitted_date,
    approved_date
    -- requested_by HIDDEN (PII)
    -- approved_by HIDDEN (PII)
FROM change_orders;

-- project_resources: no PII, full access
CREATE OR REPLACE VIEW v_project_resources AS
SELECT * FROM project_resources;

-- daily_logs: hide reported_by
CREATE OR REPLACE VIEW v_daily_logs AS
SELECT
    log_id,
    project_id,
    log_date,
    weather,
    workers_on_site,
    hours_worked,
    work_performed,
    safety_incidents,
    delays
    -- reported_by HIDDEN (PII)
FROM daily_logs;

-- ============================================================
-- 3. Grant SELECT on views only
-- ============================================================
GRANT SELECT ON v_projects TO copilot_reader;
GRANT SELECT ON v_resources TO copilot_reader;
GRANT SELECT ON v_milestones TO copilot_reader;
GRANT SELECT ON v_cost_items TO copilot_reader;
GRANT SELECT ON v_risk_assessments TO copilot_reader;
GRANT SELECT ON v_change_orders TO copilot_reader;
GRANT SELECT ON v_project_resources TO copilot_reader;
GRANT SELECT ON v_daily_logs TO copilot_reader;

-- Verify
SELECT 'Views created:' AS info;
SELECT table_name FROM information_schema.views WHERE table_schema = 'public' ORDER BY table_name;
SELECT 'Role grants:' AS info;
SELECT grantee, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'copilot_reader'
ORDER BY table_name;
