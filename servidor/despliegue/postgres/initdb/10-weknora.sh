#!/bin/sh
# Crea la base y el rol de WeKnora en el primer arranque (solo si el volumen está vacío).
set -eu
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
CREATE EXTENSION IF NOT EXISTS vector;
CREATE ROLE weknora LOGIN PASSWORD '${WEKNORA_DB_PASSWORD}';
CREATE DATABASE weknora OWNER weknora;
SQL
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d weknora <<SQL
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;
SQL
