-- Construction Cost & Schedule Risk Analytics — Schema
-- Database: construction_risk

-- ============================================================
-- 1. PROJECTS — core project tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS projects (
    project_id      SERIAL PRIMARY KEY,
    project_name    VARCHAR(200)   NOT NULL,
    project_code    VARCHAR(20)    NOT NULL UNIQUE,
    status          VARCHAR(30)    NOT NULL DEFAULT 'Planning'
                    CHECK (status IN ('Planning','Active','On Hold','Completed','Cancelled')),
    project_type    VARCHAR(50)    NOT NULL,
    region          VARCHAR(100)   NOT NULL,
    client_name     VARCHAR(200),                       -- sensitive: hidden from agent
    project_manager VARCHAR(150),                       -- sensitive: hidden from agent
    description     TEXT,                               -- free text
    planned_budget  NUMERIC(15,2)  NOT NULL CHECK (planned_budget >= 0),
    actual_cost     NUMERIC(15,2)  NOT NULL DEFAULT 0   CHECK (actual_cost >= 0),
    start_date      DATE           NOT NULL,
    planned_end_date DATE          NOT NULL,
    actual_end_date  DATE,
    percent_complete NUMERIC(5,2)  NOT NULL DEFAULT 0   CHECK (percent_complete BETWEEN 0 AND 100),
    created_at      TIMESTAMP      NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP      NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 2. RESOURCES — people, equipment, materials
-- ============================================================
CREATE TABLE IF NOT EXISTS resources (
    resource_id     SERIAL PRIMARY KEY,
    resource_name   VARCHAR(200)   NOT NULL,
    resource_type   VARCHAR(30)    NOT NULL
                    CHECK (resource_type IN ('Labor','Equipment','Material','Subcontractor')),
    category        VARCHAR(100)   NOT NULL,
    hourly_rate     NUMERIC(10,2)  CHECK (hourly_rate >= 0),
    daily_rate      NUMERIC(10,2)  CHECK (daily_rate >= 0),
    email           VARCHAR(254),                       -- sensitive: PII
    phone           VARCHAR(30),                        -- sensitive: PII
    certifications  TEXT,
    is_active       BOOLEAN        NOT NULL DEFAULT TRUE
);

-- ============================================================
-- 3. MILESTONES — schedule milestones per project
-- ============================================================
CREATE TABLE IF NOT EXISTS milestones (
    milestone_id    SERIAL PRIMARY KEY,
    project_id      INTEGER        NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    milestone_name  VARCHAR(200)   NOT NULL,
    planned_date    DATE           NOT NULL,
    actual_date     DATE,
    status          VARCHAR(30)    NOT NULL DEFAULT 'Pending'
                    CHECK (status IN ('Pending','In Progress','Completed','Delayed','Cancelled')),
    weight_pct      INTEGER        NOT NULL DEFAULT 10 CHECK (weight_pct BETWEEN 0 AND 100),
    notes           TEXT                                -- free text
);
CREATE INDEX idx_milestones_project ON milestones(project_id);

-- ============================================================
-- 4. COST_ITEMS — itemized costs per project
-- ============================================================
CREATE TABLE IF NOT EXISTS cost_items (
    cost_item_id    SERIAL PRIMARY KEY,
    project_id      INTEGER        NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    resource_id     INTEGER        REFERENCES resources(resource_id),
    cost_category   VARCHAR(50)    NOT NULL
                    CHECK (cost_category IN ('Labor','Materials','Equipment','Subcontractor',
                                             'Permits','Overhead','Contingency','Other')),
    description     VARCHAR(300)   NOT NULL,            -- free text
    planned_amount  NUMERIC(12,2)  NOT NULL CHECK (planned_amount >= 0),
    actual_amount   NUMERIC(12,2)  NOT NULL DEFAULT 0   CHECK (actual_amount >= 0),
    incurred_date   DATE           NOT NULL,
    approval_status VARCHAR(20)    NOT NULL DEFAULT 'Pending'
                    CHECK (approval_status IN ('Pending','Approved','Rejected')),
    notes           TEXT                                -- free text
);
CREATE INDEX idx_cost_items_project ON cost_items(project_id);
CREATE INDEX idx_cost_items_resource ON cost_items(resource_id);

-- ============================================================
-- 5. RISK_ASSESSMENTS — identified risks with scoring
-- ============================================================
CREATE TABLE IF NOT EXISTS risk_assessments (
    risk_id             SERIAL PRIMARY KEY,
    project_id          INTEGER        NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    risk_category       VARCHAR(50)    NOT NULL
                        CHECK (risk_category IN ('Schedule','Budget','Safety','Quality',
                                                  'Environmental','Legal','Supply Chain','Weather')),
    risk_description    TEXT           NOT NULL,         -- free text
    probability         INTEGER        NOT NULL CHECK (probability BETWEEN 1 AND 5),
    impact              INTEGER        NOT NULL CHECK (impact BETWEEN 1 AND 5),
    risk_score          INTEGER        GENERATED ALWAYS AS (probability * impact) STORED,
    mitigation_strategy TEXT,                           -- free text
    status              VARCHAR(30)    NOT NULL DEFAULT 'Open'
                        CHECK (status IN ('Open','Mitigating','Closed','Accepted')),
    identified_by       VARCHAR(150),                   -- sensitive: person name
    identified_date     DATE           NOT NULL,
    review_date         DATE,
    notes               TEXT                            -- free text
);
CREATE INDEX idx_risks_project ON risk_assessments(project_id);

-- ============================================================
-- 6. CHANGE_ORDERS — scope changes with cost/schedule impact
-- ============================================================
CREATE TABLE IF NOT EXISTS change_orders (
    change_order_id     SERIAL PRIMARY KEY,
    project_id          INTEGER        NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    change_order_number VARCHAR(30)    NOT NULL,
    title               VARCHAR(300)   NOT NULL,        -- free text
    description         TEXT,                           -- free text
    cost_impact         NUMERIC(12,2)  NOT NULL DEFAULT 0,
    schedule_impact_days INTEGER       NOT NULL DEFAULT 0,
    status              VARCHAR(30)    NOT NULL DEFAULT 'Submitted'
                        CHECK (status IN ('Submitted','Under Review','Approved','Rejected','Implemented')),
    submitted_date      DATE           NOT NULL,
    approved_date       DATE,
    requested_by        VARCHAR(150),                   -- sensitive: person name
    approved_by         VARCHAR(150)                    -- sensitive: person name
);
CREATE INDEX idx_change_orders_project ON change_orders(project_id);

-- ============================================================
-- 7. PROJECT_RESOURCES — resource assignments and utilization
-- ============================================================
CREATE TABLE IF NOT EXISTS project_resources (
    assignment_id   SERIAL PRIMARY KEY,
    project_id      INTEGER        NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    resource_id     INTEGER        NOT NULL REFERENCES resources(resource_id),
    role            VARCHAR(100)   NOT NULL,
    start_date      DATE           NOT NULL,
    end_date        DATE,
    allocated_hours NUMERIC(8,2)   NOT NULL CHECK (allocated_hours >= 0),
    actual_hours    NUMERIC(8,2)   NOT NULL DEFAULT 0   CHECK (actual_hours >= 0),
    utilization_pct NUMERIC(5,2)   GENERATED ALWAYS AS (
                        CASE WHEN allocated_hours > 0
                             THEN LEAST((actual_hours / allocated_hours) * 100, 999.99)
                             ELSE 0 END
                    ) STORED
);
CREATE INDEX idx_proj_res_project ON project_resources(project_id);
CREATE INDEX idx_proj_res_resource ON project_resources(resource_id);

-- ============================================================
-- 8. DAILY_LOGS — daily site reports
-- ============================================================
CREATE TABLE IF NOT EXISTS daily_logs (
    log_id          SERIAL PRIMARY KEY,
    project_id      INTEGER        NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    log_date        DATE           NOT NULL,
    weather         VARCHAR(30)    CHECK (weather IN ('Clear','Cloudy','Rain','Storm','Snow','Extreme Heat')),
    workers_on_site INTEGER        NOT NULL DEFAULT 0   CHECK (workers_on_site >= 0),
    hours_worked    NUMERIC(5,2)   NOT NULL DEFAULT 0   CHECK (hours_worked >= 0),
    work_performed  TEXT,                               -- free text
    safety_incidents TEXT,                              -- free text
    delays          TEXT,                               -- free text
    reported_by     VARCHAR(150)                        -- sensitive: person name
);
CREATE INDEX idx_daily_logs_project ON daily_logs(project_id);
CREATE INDEX idx_daily_logs_date ON daily_logs(log_date);
