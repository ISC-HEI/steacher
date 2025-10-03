-- Create New Relic monitoring user for PostgreSQL
-- Run this script as a superuser (postgres) in the steacher database

-- Create the monitoring user with a secure password
-- IMPORTANT: Replace 'CHANGE_THIS_PASSWORD' with a strong password
CREATE USER newrelic WITH PASSWORD 'CHANGE_THIS_PASSWORD';

-- Grant connection to the database
GRANT CONNECT ON DATABASE steacher_prod TO newrelic;

-- Grant usage on public schema
GRANT USAGE ON SCHEMA public TO newrelic;

-- Grant select on system tables for monitoring
GRANT SELECT ON ALL TABLES IN SCHEMA public TO newrelic;

-- Allow monitoring of pg_stat_* views
GRANT pg_monitor TO newrelic;

-- Optional: If you want to monitor table/index bloat (recommended)
-- Grant select on pg_catalog tables
GRANT SELECT ON pg_catalog.pg_class TO newrelic;
GRANT SELECT ON pg_catalog.pg_namespace TO newrelic;
GRANT SELECT ON pg_catalog.pg_database TO newrelic;

-- Verify the grants
\du+ newrelic

