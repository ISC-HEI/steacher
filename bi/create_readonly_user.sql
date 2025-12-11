-- Create read-only PostgreSQL user for Metabase
-- Run this once before starting Metabase for the first time

-- Create the read-only user
CREATE USER metabase_readonly WITH PASSWORD 'CHANGE_THIS_PASSWORD';

-- Grant connection to the database
GRANT CONNECT ON DATABASE steacher_prod TO metabase_readonly;

-- Grant usage on the public schema
GRANT USAGE ON SCHEMA public TO metabase_readonly;

-- Grant SELECT on all existing tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO metabase_readonly;

-- Grant SELECT on all future tables (so new tables are automatically accessible)
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO metabase_readonly;

-- Grant SELECT on all sequences (needed for some queries)
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO metabase_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO metabase_readonly;

-- Verify permissions
\du metabase_readonly
