-- PostgreSQL Health Check Script for Steacher
-- Run this monthly or when investigating performance issues
-- Usage: docker exec -i steacher_app-db-1 psql -U steacher_admin -d steacher_prod < specs/fail/251003_pg_newrelic_monitoring/manual_stats.sql

\echo '=== DATABASE SIZE ==='
SELECT 
    pg_database.datname AS database_name,
    pg_size_pretty(pg_database_size(pg_database.datname)) AS size
FROM pg_database
WHERE datname = 'steacher_prod';

\echo ''
\echo '=== TOP 10 LARGEST TABLES ==='
SELECT 
    schemaname,
    relname AS tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||relname)) AS size,
    pg_size_pretty(pg_relation_size(schemaname||'.'||relname)) AS table_size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||relname) - pg_relation_size(schemaname||'.'||relname)) AS indexes_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(schemaname||'.'||relname) DESC
LIMIT 10;

\echo ''
\echo '=== DEAD TUPLES (Run VACUUM if >20%) ==='
SELECT 
    schemaname,
    relname AS table_name,
    n_dead_tup AS dead_tuples,
    n_live_tup AS live_tuples,
    ROUND(n_dead_tup * 100.0 / NULLIF(n_live_tup + n_dead_tup, 0), 2) AS dead_tuple_percent
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY n_dead_tup DESC
LIMIT 10;

\echo ''
\echo '=== UNUSED INDEXES (Consider dropping) ==='
SELECT 
    schemaname,
    relname AS tablename,
    indexrelname AS indexname,
    idx_scan AS index_scans,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
    AND indexrelname NOT LIKE '%pkey%'
ORDER BY pg_relation_size(indexrelid) DESC;

\echo ''
\echo '=== CONNECTION COUNT ==='
SELECT 
    COUNT(*) as total_connections,
    COUNT(*) FILTER (WHERE state = 'active') as active,
    COUNT(*) FILTER (WHERE state = 'idle') as idle
FROM pg_stat_activity
WHERE datname = 'steacher_prod';

\echo ''
\echo '=== CACHE HIT RATIO (Should be >90%) ==='
SELECT 
    ROUND(100.0 * sum(blks_hit) / NULLIF(sum(blks_hit) + sum(blks_read), 0), 2) AS cache_hit_ratio_percent
FROM pg_stat_database
WHERE datname = 'steacher_prod';
