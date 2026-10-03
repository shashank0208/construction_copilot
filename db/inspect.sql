-- Full database inspection query for Phase 0
-- Run against construction_risk database

-- 1. All tables with row counts
SELECT 'ROW COUNTS' as section;
SELECT
    schemaname,
    relname as table_name,
    n_live_tup as row_count
FROM pg_stat_user_tables
ORDER BY relname;

-- 2. Columns with types for each table
SELECT 'COLUMNS' as section;
SELECT
    c.table_name,
    c.column_name,
    c.data_type,
    c.character_maximum_length,
    c.numeric_precision,
    c.is_nullable,
    c.column_default
FROM information_schema.columns c
JOIN information_schema.tables t ON c.table_name = t.table_name AND c.table_schema = t.table_schema
WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
ORDER BY c.table_name, c.ordinal_position;

-- 3. Primary keys
SELECT 'PRIMARY KEYS' as section;
SELECT
    tc.table_name,
    kcu.column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'
ORDER BY tc.table_name;

-- 4. Foreign keys
SELECT 'FOREIGN KEYS' as section;
SELECT
    tc.table_name as from_table,
    kcu.column_name as from_column,
    ccu.table_name as to_table,
    ccu.column_name as to_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
ORDER BY tc.table_name;

-- 5. Sample rows (3 per table)
SELECT 'SAMPLE: projects' as section;
SELECT * FROM projects LIMIT 3;
SELECT 'SAMPLE: resources' as section;
SELECT * FROM resources LIMIT 3;
SELECT 'SAMPLE: milestones' as section;
SELECT * FROM milestones LIMIT 3;
SELECT 'SAMPLE: cost_items' as section;
SELECT * FROM cost_items LIMIT 3;
SELECT 'SAMPLE: risk_assessments' as section;
SELECT * FROM risk_assessments LIMIT 3;
SELECT 'SAMPLE: change_orders' as section;
SELECT * FROM change_orders LIMIT 3;
SELECT 'SAMPLE: project_resources' as section;
SELECT * FROM project_resources LIMIT 3;
SELECT 'SAMPLE: daily_logs' as section;
SELECT * FROM daily_logs LIMIT 3;
