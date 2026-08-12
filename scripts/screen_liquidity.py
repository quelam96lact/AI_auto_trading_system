"""Task 6: Lọc thanh khoản từ bars_daily -> symbol_universe.is_active.

CLI:
  uv run python -m scripts.screen_liquidity [--window-days 20] [--min-value 1e9] [--dry-run]

Tính từ bars_daily (KHÔNG gọi API): avg_value_20d = avg(close*volume) trên N
phiên gần nhất mỗi mã; avg_volume_20d = avg(volume).

Điều kiện gần đây (bài học audit 2026-08-10): chỉ xét mã có max(ts) >=
(ngày giao dịch mới nhất trong bars_daily) - max_stale_days. Mã ngừng giao
dịch lâu (vd PSH/HSA/ITA/BCG bar cuối 2024-2025) dù avg 20 phiên cũ vẫn cao
cũng KHÔNG được is_active. Dùng mốc từ bars_daily chứ không phải date.today()
để chạy lại cuối tuần/lễ vẫn cho kết quả ổn định.

--dry-run: in bảng phân bố theo ngưỡng + theo sàn, KHÔNG ghi is_active.
Không --dry-run: ghi is_active = (không stale AND avg_value_20d >= min_value).
"""

import argparse
from datetime import timedelta

import psycopg

DSN_DEFAULT = "postgresql://trading:trading@127.0.0.1:5432/trading"

THRESHOLDS = [0.5e9, 1e9, 5e9, 10e9, 20e9]


def compute(window_days: int, max_stale_days: int, dsn: str):
    """Trả về (stats, cutoff) với stats[symbol] = (exchange, avg_value, avg_volume, max_ts).

    stats chứa MỌI mã trong universe (kể cả stale, để main set is_active=false);
    cutoff = ngày giao dịch mới nhất toàn bars_daily - max_stale_days."""
    with psycopg.connect(dsn) as c:
        total_max = c.execute(
            "SELECT max((ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date) FROM bars_daily"
        ).fetchone()[0]
        if total_max is None:
            raise SystemExit("bars_daily rong - chay Task 5 truoc")
        rows = c.execute(
            """
            WITH ranked AS (
              SELECT symbol, close, volume, ts,
                     ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ts DESC) AS rn
              FROM bars_daily
            ),
            recent AS (
              SELECT symbol, close, volume, ts
              FROM ranked WHERE rn <= %s
            )
            SELECT u.symbol, u.exchange,
                   COALESCE(AVG(r.close * r.volume), 0) AS avg_value,
                   COALESCE(AVG(r.volume), 0) AS avg_volume,
                   MAX((r.ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date) AS max_ts
            FROM symbol_universe u
            LEFT JOIN recent r USING (symbol)
            GROUP BY u.symbol, u.exchange
            """,
            (window_days,),
        ).fetchall()
    cutoff = total_max - timedelta(days=max_stale_days)
    stats = {r[0]: (r[1], float(r[2]), float(r[3]), r[4]) for r in rows}
    return stats, cutoff


def is_stale(entry, cutoff) -> bool:
    return entry[3] is None or entry[3] < cutoff


def print_distribution(data: dict, cutoff) -> None:
    fresh = {s: v for s, v in data.items() if not is_stale(v, cutoff)}
    n_stale = len(data) - len(fresh)
    by_exchange: dict[str, int] = {}
    for ex, _, _, _ in fresh.values():
        by_exchange[ex] = by_exchange.get(ex, 0) + 1

    print(f"Tong ma trong universe: {len(data)} (loai vi stale/chet: {n_stale})")
    print(f"Ngay cat stale: max(ts) >= {cutoff}")
    print(f"Phan bo theo san (ma con giao dich): {by_exchange}")
    print()
    print("nguong >= X ty VND/phien:  so ma")
    for t in THRESHOLDS:
        n = sum(1 for v in fresh.values() if v[1] >= t)
        print(f"nguong >= {t / 1e9:>5} ty VND/phien:  {n:>5} ma")

    print()
    print("Phan bo theo san tai tung nguong:")
    for t in THRESHOLDS:
        per_san = {}
        for ex, v, _, _ in fresh.values():
            if v >= t:
                per_san[ex] = per_san.get(ex, 0) + 1
        print(f"  >= {t / 1e9:>5} ty: {per_san}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, default=20)
    ap.add_argument("--min-value", type=float, default=1e9)
    ap.add_argument("--max-stale-days", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--dsn", default=DSN_DEFAULT)
    args = ap.parse_args()

    data, cutoff = compute(args.window_days, args.max_stale_days, args.dsn)

    if args.dry_run:
        print_distribution(data, cutoff)
        print("\n(dry-run: chua ghi is_active - cho user chot nguong)")
        return

    n_active = 0
    with psycopg.connect(args.dsn) as c:
        for sym, (ex, avg_value, avg_volume, max_ts) in data.items():
            active = not is_stale((ex, avg_value, avg_volume, max_ts), cutoff) and avg_value >= args.min_value
            c.execute(
                "UPDATE symbol_universe SET avg_value_20d = %s, avg_volume_20d = %s, "
                "is_active = %s, updated_at = now() WHERE symbol = %s",
                (avg_value, avg_volume, active, sym),
            )
            if active:
                n_active += 1
    print(f"Da ghi is_active: {n_active}/{len(data)} ma (nguong >= {args.min_value / 1e9} ty, stale <= {args.max_stale_days} ngay)")


if __name__ == "__main__":
    main()
