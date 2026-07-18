CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS bars (
  symbol text NOT NULL,
  ts timestamptz NOT NULL,
  open double precision NOT NULL,
  high double precision NOT NULL,
  low double precision NOT NULL,
  close double precision NOT NULL,
  volume bigint NOT NULL,
  source text NOT NULL DEFAULT 'ssi',
  PRIMARY KEY (symbol, ts)
);
SELECT create_hypertable('bars', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS bars_daily (
  symbol text NOT NULL,
  ts timestamptz NOT NULL,
  open double precision NOT NULL,
  high double precision NOT NULL,
  low double precision NOT NULL,
  close double precision NOT NULL,
  volume bigint NOT NULL,
  source text NOT NULL DEFAULT 'ssi',
  PRIMARY KEY (symbol, ts)
);

CREATE TABLE IF NOT EXISTS index_values (
  index_id text NOT NULL,
  ts timestamptz NOT NULL,
  value double precision NOT NULL,
  PRIMARY KEY (index_id, ts)
);
SELECT create_hypertable('index_values', 'ts', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS heartbeat (
  service text PRIMARY KEY,
  last_seen timestamptz NOT NULL
);