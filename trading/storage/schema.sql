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

CREATE TABLE IF NOT EXISTS orders (
  id bigserial PRIMARY KEY,
  ts timestamptz NOT NULL,
  symbol text NOT NULL,
  side text NOT NULL,
  qty integer NOT NULL,
  price double precision NOT NULL,
  fee double precision NOT NULL,
  pnl double precision,
  mode text NOT NULL DEFAULT 'paper'
);

CREATE TABLE IF NOT EXISTS positions (
  symbol text PRIMARY KEY,
  qty integer NOT NULL,
  avg_price double precision NOT NULL,
  updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS engine_state (
  id integer PRIMARY KEY DEFAULT 1,
  cash double precision NOT NULL,
  realized_pnl double precision NOT NULL,
  updated_at timestamptz NOT NULL,
  CHECK (id = 1)
);

CREATE TABLE IF NOT EXISTS pnl_daily (
  date date PRIMARY KEY,
  realized double precision NOT NULL DEFAULT 0,
  unrealized double precision NOT NULL DEFAULT 0,
  fees double precision NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ssi_auth_state (
  id integer PRIMARY KEY DEFAULT 1,
  access_token text NOT NULL,
  expires_at bigint NOT NULL,
  refresh_token text NOT NULL,
  refresh_token_expires_at bigint NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (id = 1)
);

CREATE TABLE IF NOT EXISTS account_balance_snapshot (
  account_no text NOT NULL,
  ts timestamptz NOT NULL,
  account_balance double precision NOT NULL,
  total_debt double precision NOT NULL,
  withdrawable double precision NOT NULL,
  buy_unmatched double precision NOT NULL,
  sell_unmatched double precision NOT NULL,
  PRIMARY KEY (account_no, ts)
);

CREATE TABLE IF NOT EXISTS account_position_snapshot (
  account_no text NOT NULL,
  ts timestamptz NOT NULL,
  symbol text NOT NULL,
  quantity integer NOT NULL,
  cost_price double precision NOT NULL,
  sellable_quantity integer NOT NULL,
  PRIMARY KEY (account_no, ts, symbol)
);

CREATE TABLE IF NOT EXISTS pending_real_orders (
  id bigserial PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  account_no text NOT NULL,
  symbol text NOT NULL,
  side text NOT NULL,
  quantity integer NOT NULL,
  price double precision NOT NULL,
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'confirmed', 'expired', 'rejected', 'placed', 'failed')),
  ssi_order_id text,
  confirmed_at timestamptz
);

CREATE TABLE IF NOT EXISTS real_order_fills (
  id bigserial PRIMARY KEY,
  ts timestamptz NOT NULL,
  account_no text NOT NULL,
  symbol text NOT NULL,
  side text NOT NULL,
  qty integer NOT NULL,
  price double precision NOT NULL,
  fee double precision NOT NULL DEFAULT 0,
  pnl double precision,
  ssi_order_id text,
  status text NOT NULL CHECK (status IN ('placed', 'cancelled', 'filled'))
);
