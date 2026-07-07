#!/bin/bash
# PostgreSQL initialization — run once on fresh database.
# Creates extensions and base schema beyond what the app migrates.

set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Enable pg_stat_statements for query performance monitoring
    CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

    -- Enable uuid-ossp for UUID generation
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

    -- Enable pgcrypto for encryption functions
    CREATE EXTENSION IF NOT EXISTS "pgcrypto";
EOSQL
