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

SELECT create_hypertable('bars_daily', 'ts', if_not_exists => TRUE, migrate_data => TRUE);

CREATE TABLE IF NOT EXISTS symbol_universe (
  symbol text PRIMARY KEY,
  exchange text NOT NULL,
  avg_value_20d double precision,
  avg_volume_20d double precision,
  is_active boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS backfill_progress (
  symbol text NOT NULL,
  timeframe text NOT NULL,
  last_done_date date,
  status text NOT NULL,
  error text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, timeframe)
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

CREATE TABLE IF NOT EXISTS derivative_balance_snapshot (
  account_no text NOT NULL,
  ts timestamptz NOT NULL,
  account_balance double precision NOT NULL,
  floating_pl double precision NOT NULL,
  trading_pl double precision NOT NULL,
  total_pl double precision NOT NULL,
  withdrawable double precision NOT NULL,
  PRIMARY KEY (account_no, ts)
);

CREATE TABLE IF NOT EXISTS derivative_margin_snapshot (
  account_no text NOT NULL,
  ts timestamptz NOT NULL,
  rc_call boolean NOT NULL,
  account_ratio_ssi double precision NOT NULL,
  account_ratio_vsdc double precision NOT NULL,
  used_limit_warning_level1_ssi double precision NOT NULL,
  used_limit_warning_level2_ssi double precision NOT NULL,
  used_limit_warning_level3_ssi double precision NOT NULL,
  total_equity double precision NOT NULL,
  PRIMARY KEY (account_no, ts)
);

CREATE TABLE IF NOT EXISTS derivative_position_snapshot (
  account_no text NOT NULL,
  ts timestamptz NOT NULL,
  symbol text NOT NULL,
  long integer NOT NULL,
  short integer NOT NULL,
  net integer NOT NULL,
  floating_pl double precision NOT NULL,
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

CREATE TABLE IF NOT EXISTS real_risk_state (
  id integer PRIMARY KEY DEFAULT 1,
  halted_date date,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (id = 1)
);
