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
-- Dot 128 (2026-09-29): chunk 30 ngay cho bars 5m (tranh bung no chunk tren VPS).
SELECT create_hypertable('bars', 'ts', chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS bars_derivative (
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
-- Dot 128 (2026-09-29): chunk 30 ngay cho bars_derivative (tranh bung no chunk tren VPS).
SELECT create_hypertable('bars_derivative', 'ts', chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);

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

-- Dot 128 (2026-09-29): chunk 1 nam (~60 MB/chunk) de tranh bung no chunk (560 -> ~11).
-- if_not_exists => TRUE khong doi DB da co; DB cu can scripts/merge_bars_daily_chunks.py (xem §2 brief dot 128).
SELECT create_hypertable('bars_daily', 'ts', chunk_time_interval => INTERVAL '1 year', if_not_exists => TRUE, migrate_data => TRUE);

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

-- SYNC-LOG-1: su kien dong bo vi the (CHI luu lan gan nhat, khong lich su —
-- lich su nhip dong bo da co o account_balance_snapshot cung chu ky 5 phut).
-- Ghi LUON khi fetch thanh cong (ca khi danh muc RONG) de phan biet
-- "chua dong bo bao gio" voi "da dong bo va rong" — khong ghi thi max(ts)
-- dung o lan cu, vi the da ban ve VINH VIEN.
CREATE TABLE IF NOT EXISTS account_sync_log (
  account_no text PRIMARY KEY,
  ts         timestamptz NOT NULL
);

-- MARGIN-1 (phan 1): suc mua theo TUNG MA do san quyet (trần cứng khi dat lenh —
-- phan 2). KHONG luu purchase_power (da do: chuoi RONG o ca 2 tai khoan — luu
-- cot luon rong chi lam nguoi sau tuong no co nghia). margin_ratio_pct cho phep
-- NULL: chuoi '50%' -> 50.0; SSI tra dang la thi NULL (dung doan).
CREATE TABLE IF NOT EXISTS account_buying_power (
  account_no text NOT NULL,
  symbol text NOT NULL,
  ts timestamptz NOT NULL,
  max_buy_qty integer NOT NULL,
  max_sell_qty integer NOT NULL,
  margin_ratio_pct double precision,
  PRIMARY KEY (account_no, symbol, ts)
);

-- MARGIN-1 (phan 1): tai san RONG (NAV) = tien mat + Σ(qty × gia) − no.
-- Bang RIENG (khong them cot vao account_balance_snapshot) vi NAV TINH TU
-- positions + gia (nguon khac field SSI) — them cot se lam nguoi sau tuong NAV
-- la field SSI tra ve. unpriced_symbols = cac ma khong dinh gia duoc (khong co
-- gia / gia qua cu) — de canh bao ro ma nao, khong im lang.
CREATE TABLE IF NOT EXISTS account_nav_snapshot (
  account_no text NOT NULL,
  ts timestamptz NOT NULL,
  nav double precision NOT NULL,
  unpriced_symbols text[] NOT NULL DEFAULT '{}',
  PRIMARY KEY (account_no, ts)
);

-- backtest-grafana: ket qua mo phong chien luoc tung ma, Grafana doc bang nay.
CREATE TABLE IF NOT EXISTS backtest_runs (
  run_id bigserial PRIMARY KEY,
  ts timestamptz NOT NULL DEFAULT now(),
  symbol text NOT NULL,
  strategy text NOT NULL,
  timeframe text NOT NULL,
  frm date NOT NULL,
  to_date date NOT NULL,
  capital double precision NOT NULL,
  realized_pnl double precision,
  unrealized_pnl double precision,
  buy_and_hold_pnl double precision,
  max_drawdown double precision,
  win_rate double precision,
  trades int,
  filtered_bars int
);

CREATE TABLE IF NOT EXISTS backtest_equity (
  run_id bigint NOT NULL REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
  ts timestamptz NOT NULL,
  equity double precision NOT NULL,
  -- Duong mua-va-giu THAT tai cung moc ts (khong phai noi suy). Grafana chi
  -- DOC cot nay; tinh benchmark trong SQL la ban thu hai cua cong thuc.
  equity_bh double precision
);
ALTER TABLE backtest_equity ADD COLUMN IF NOT EXISTS equity_bh double precision;

CREATE TABLE IF NOT EXISTS backtest_fills (
  run_id bigint NOT NULL REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
  ts timestamptz NOT NULL,
  side text NOT NULL,
  qty int NOT NULL,
  price double precision NOT NULL,
  fee double precision NOT NULL
);
