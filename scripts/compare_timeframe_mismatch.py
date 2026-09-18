"""Công cụ đo lệch khung nến giữa backtest (bars_daily) và production (bars 5m) — Brief đợt 45.

Đo trên 3 mã production (HPG, IJC, AAA) trong khoảng 2026-06-01 -> 2026-09-12:
1. Số nến ngày và tín hiệu trên bars_daily
2. Số nến 5 phút và tín hiệu trên bars (5m)
3. Số lệnh giấy thật trong bảng orders
4. Bảng chẩn đoán từng vế điều kiện trên nến 5 phút
"""

import argparse
import sys
from datetime import datetime
from typing import Any

import psycopg

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

from trading.calendar_vn import TZ
from trading.models import Bar
from trading.strategies.octopus_pullback import OctopusPullbackStrategy

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def get_direct_db_counts(
    conn: psycopg.Connection,
    symbols: list[str],
    start_dt: datetime,
    end_dt: datetime,
) -> dict[str, dict[str, int]]:
    """Truy vấn count(*) trực tiếp trên các bảng DB để làm mốc đối chứng (Tiêu chí kiểm chứng 1 & 2)."""
    db_counts: dict[str, dict[str, int]] = {}
    with conn.cursor() as cur:
        cur.execute("SET TimeZone='Asia/Ho_Chi_Minh';")
        for sym in symbols:
            # 1. bars_daily
            cur.execute(
                """
                SELECT count(*)
                FROM bars_daily
                WHERE symbol = %s AND ts >= %s AND ts <= %s;
                """,
                (sym, start_dt, end_dt),
            )
            c_daily = int(cur.fetchone()[0])

            # 2. bars (5m)
            cur.execute(
                """
                SELECT count(*)
                FROM bars
                WHERE symbol = %s AND ts >= %s AND ts <= %s;
                """,
                (sym, start_dt, end_dt),
            )
            c_5m = int(cur.fetchone()[0])

            # 3. orders
            cur.execute(
                """
                SELECT count(*)
                FROM orders
                WHERE symbol = %s AND ts >= %s AND ts <= %s;
                """,
                (sym, start_dt, end_dt),
            )
            c_orders = int(cur.fetchone()[0])

            db_counts[sym] = {
                "bars_daily": c_daily,
                "bars_5m": c_5m,
                "orders": c_orders,
            }
    return db_counts


def run_timeframe_comparison(
    conn: psycopg.Connection,
    symbols: list[str] | None = None,
    start_dt: datetime | None = None,
    end_dt: datetime | None = None,
) -> dict[str, Any]:
    """Chạy so sánh tín hiệu giữa bars_daily và bars 5m theo đúng cấu hình _default_strategy()."""
    if symbols is None:
        symbols = ["HPG", "IJC", "AAA"]
    if start_dt is None:
        start_dt = datetime(2026, 6, 1, 0, 0, 0, tzinfo=TZ)
    if end_dt is None:
        end_dt = datetime(2026, 9, 12, 23, 59, 59, tzinfo=TZ)

    db_counts = get_direct_db_counts(conn, symbols, start_dt, end_dt)

    counts_daily: dict[str, int] = {}
    signals_daily: dict[str, dict[str, int]] = {}
    counts_5m: dict[str, int] = {}
    signals_5m: dict[str, dict[str, int]] = {}
    real_orders: dict[str, int] = {}
    diagnosis_5m: dict[str, dict[str, int]] = {}

    with conn.cursor() as cur:
        cur.execute("SET TimeZone='Asia/Ho_Chi_Minh';")

        # ---------------- 1. Đo trên bars_daily ----------------
        for sym in symbols:
            # Nạp toàn bộ lịch sử đến end_dt để warm-up đầy đủ
            cur.execute(
                """
                SELECT symbol, ts, open, high, low, close, volume, source
                FROM bars_daily
                WHERE symbol = %s AND ts <= %s
                ORDER BY ts ASC;
                """,
                (sym, end_dt),
            )
            rows = cur.fetchall()
            daily_bars = [Bar(*r) for r in rows]

            # Khởi tạo chiến lược đúng y hệt _default_strategy()
            strat_daily = OctopusPullbackStrategy()
            eval_daily_cnt = 0
            daily_bull = 0
            daily_bear = 0

            for b in daily_bars:
                sig = strat_daily.compute_crossover(b)
                if start_dt <= b.ts <= end_dt:
                    eval_daily_cnt += 1
                    if sig == "bull":
                        daily_bull += 1
                    elif sig == "bear":
                        daily_bear += 1

            counts_daily[sym] = eval_daily_cnt
            signals_daily[sym] = {"bull": daily_bull, "bear": daily_bear, "total": daily_bull + daily_bear}

        # ---------------- 2. Đo trên bars (5m) & Bảng chẩn đoán ----------------
        for sym in symbols:
            # Nạp toàn bộ lịch sử đến end_dt để warm-up đầy đủ
            cur.execute(
                """
                SELECT symbol, ts, open, high, low, close, volume, source
                FROM bars
                WHERE symbol = %s AND ts <= %s
                ORDER BY ts ASC;
                """,
                (sym, end_dt),
            )
            rows = cur.fetchall()
            bars_5m = [Bar(*r) for r in rows]

            strat_5m = OctopusPullbackStrategy()
            eval_5m_cnt = 0
            m5_bull = 0
            m5_bear = 0

            diag = {
                "eval_bars": 0,
                "warmup_ready": 0,
                "trend": 0,
                "pullback": 0,
                "crossover": 0,
                "macd_pos": 0,
                "reversal": 0,
                "liquidity": 0,
                "all_combined": 0,
            }

            for b in bars_5m:
                # Giá trị trước update
                p_fast = strat_5m._ema_fast.last(b.symbol)
                p_slow = strat_5m._ema_slow.last(b.symbol)

                sig = strat_5m.compute_crossover(b)

                if start_dt <= b.ts <= end_dt:
                    eval_5m_cnt += 1
                    diag["eval_bars"] += 1

                    # Giá trị sau update
                    e_fast = strat_5m._ema_fast.last(b.symbol)
                    e_slow = strat_5m._ema_slow.last(b.symbol)
                    e_trend = strat_5m._ema_trend.last(b.symbol)
                    hist = strat_5m._macd.last(b.symbol)
                    reds_b = strat_5m._reds_before(b.symbol)
                    liq_ok = strat_5m._liquidity_ok(b.symbol)

                    # 1. Warmup
                    warmup_ok = (
                        e_fast is not None
                        and e_slow is not None
                        and e_trend is not None
                        and hist is not None
                        and p_fast is not None
                        and p_slow is not None
                    )
                    if warmup_ok:
                        diag["warmup_ready"] += 1

                        # 2. Xu hướng: close > EMA(200)
                        if b.close > e_trend:
                            diag["trend"] += 1

                        # 3. Pullback: >= 2 nến đỏ trong 5 nến trước
                        if reds_b is not None and reds_b >= strat_5m.pullback_red:
                            diag["pullback"] += 1

                        # 4. Giao cắt: EMA(9) cắt lên EMA(21)
                        cross_up = p_fast <= p_slow and e_fast > e_slow
                        if cross_up:
                            diag["crossover"] += 1

                        # 5. MACD histogram > 0
                        if hist > 0:
                            diag["macd_pos"] += 1

                        # 6. Đảo chiều = Giao cắt VÀ MACD > 0
                        if cross_up and hist > 0:
                            diag["reversal"] += 1

                        # 7. Thanh khoản: bình quân 20 ngày >= 2 tỷ
                        if liq_ok:
                            diag["liquidity"] += 1

                    if sig == "bull":
                        m5_bull += 1
                        diag["all_combined"] += 1
                    elif sig == "bear":
                        m5_bear += 1

            counts_5m[sym] = eval_5m_cnt
            signals_5m[sym] = {"bull": m5_bull, "bear": m5_bear, "total": m5_bull + m5_bear}
            diagnosis_5m[sym] = diag
            real_orders[sym] = db_counts[sym]["orders"]

    return {
        "symbols": symbols,
        "start_dt": start_dt,
        "end_dt": end_dt,
        "db_counts": db_counts,
        "counts_daily": counts_daily,
        "signals_daily": signals_daily,
        "counts_5m": counts_5m,
        "signals_5m": signals_5m,
        "real_orders": real_orders,
        "diagnosis_5m": diagnosis_5m,
    }


def print_report(res: dict[str, Any]) -> None:
    symbols = res["symbols"]
    start_dt = res["start_dt"]
    end_dt = res["end_dt"]

    print("=" * 88)
    print("BÁO CÁO ĐO LỆCH KHUNG NẾN GIỮA BACKTEST (DAILY) VÀ PRODUCTION (5M)")
    print(f"Khoảng đo: {start_dt.strftime('%Y-%m-%d')} -> {end_dt.strftime('%Y-%m-%d')} (Giờ VN)")
    print("Chiến lược: OctopusPullbackStrategy (tham số mặc định theo _default_strategy())")
    print("=" * 88)

    print("\n--- BẢNG 1: TÍN HIỆU NẾN NGÀY SO VỚI NẾN 5 PHÚT & LỆNH GIẤY THẬT (§2.2) ---")
    print(
        f"{'Mã':<6} | {'Số nến ngày':<12} | {'Tín hiệu ngày (bull/bear)':<25} | "
        f"{'Số nến 5m':<12} | {'Tín hiệu 5m (bull/bear)':<23} | {'Lệnh giấy thật'}"
    )
    print("-" * 105)

    tot_daily = 0
    tot_sig_daily_bull = 0
    tot_sig_daily_bear = 0
    tot_5m = 0
    tot_sig_5m_bull = 0
    tot_sig_5m_bear = 0
    tot_orders = 0

    for sym in symbols:
        c_d = res["counts_daily"][sym]
        s_d = res["signals_daily"][sym]
        c_5 = res["counts_5m"][sym]
        s_5 = res["signals_5m"][sym]
        ord_cnt = res["real_orders"][sym]

        tot_daily += c_d
        tot_sig_daily_bull += s_d["bull"]
        tot_sig_daily_bear += s_d["bear"]
        tot_5m += c_5
        tot_sig_5m_bull += s_5["bull"]
        tot_sig_5m_bear += s_5["bear"]
        tot_orders += ord_cnt

        sig_d_str = f"{s_d['bull']} bull / {s_d['bear']} bear"
        sig_5_str = f"{s_5['bull']} bull / {s_5['bear']} bear"

        print(
            f"{sym:<6} | {c_d:<12} | {sig_d_str:<25} | {c_5:<12} | {sig_5_str:<23} | {ord_cnt:<14}"
        )

    print("-" * 105)
    tot_d_str = f"{tot_sig_daily_bull} bull / {tot_sig_daily_bear} bear"
    tot_5_str = f"{tot_sig_5m_bull} bull / {tot_sig_5m_bear} bear"
    print(
        f"{'TỔNG':<6} | {tot_daily:<12} | {tot_d_str:<25} | {tot_5m:<12} | {tot_5_str:<23} | {tot_orders:<14}"
    )

    print("\n--- BẢNG 2: CHẨN ĐOÁN TỪNG VẾ ĐIỀU KIỆN TRÊN NẾN 5 PHÚT (§2.3) ---")
    headers = [
        "Mã",
        "Số bar 5m",
        "Warmup đủ",
        "Xu hướng (close>EMA200)",
        "Pullback (>=2 đỏ)",
        "Crossover (EMA9^21)",
        "MACD hist>0",
        "Đảo chiều (Cross&MACD)",
        "Thanh khoản (>=2 tỷ)",
        "HỢP CẢ VẾ (Signal)",
    ]
    print(
        f"{headers[0]:<5} | {headers[1]:<10} | {headers[2]:<10} | {headers[3]:<23} | "
        f"{headers[4]:<18} | {headers[5]:<19} | {headers[6]:<12} | {headers[7]:<22} | "
        f"{headers[8]:<20} | {headers[9]}"
    )
    print("-" * 175)

    tot_diag = {
        "eval_bars": 0,
        "warmup_ready": 0,
        "trend": 0,
        "pullback": 0,
        "crossover": 0,
        "macd_pos": 0,
        "reversal": 0,
        "liquidity": 0,
        "all_combined": 0,
    }

    for sym in symbols:
        d = res["diagnosis_5m"][sym]
        for k in tot_diag:
            tot_diag[k] += d[k]

        n = d["eval_bars"]
        p_trend = f"{d['trend']} ({d['trend']/n*100:.1f}%)"
        p_pb = f"{d['pullback']} ({d['pullback']/n*100:.1f}%)"
        p_cross = f"{d['crossover']} ({d['crossover']/n*100:.1f}%)"
        p_macd = f"{d['macd_pos']} ({d['macd_pos']/n*100:.1f}%)"
        p_rev = f"{d['reversal']} ({d['reversal']/n*100:.1f}%)"
        p_liq = f"{d['liquidity']} ({d['liquidity']/n*100:.1f}%)"
        p_all = f"{d['all_combined']} ({d['all_combined']/n*100:.2f}%)"

        print(
            f"{sym:<5} | {n:<10} | {d['warmup_ready']:<10} | {p_trend:<23} | "
            f"{p_pb:<18} | {p_cross:<19} | {p_macd:<12} | {p_rev:<22} | "
            f"{p_liq:<20} | {p_all}"
        )

    print("-" * 175)
    tn = tot_diag["eval_bars"]
    t_trend = f"{tot_diag['trend']} ({tot_diag['trend']/tn*100:.1f}%)"
    t_pb = f"{tot_diag['pullback']} ({tot_diag['pullback']/tn*100:.1f}%)"
    t_cross = f"{tot_diag['crossover']} ({tot_diag['crossover']/tn*100:.1f}%)"
    t_macd = f"{tot_diag['macd_pos']} ({tot_diag['macd_pos']/tn*100:.1f}%)"
    t_rev = f"{tot_diag['reversal']} ({tot_diag['reversal']/tn*100:.1f}%)"
    t_liq = f"{tot_diag['liquidity']} ({tot_diag['liquidity']/tn*100:.1f}%)"
    t_all = f"{tot_diag['all_combined']} ({tot_diag['all_combined']/tn*100:.2f}%)"

    print(
        f"{'TỔNG':<5} | {tn:<10} | {tot_diag['warmup_ready']:<10} | {t_trend:<23} | "
        f"{t_pb:<18} | {t_cross:<19} | {t_macd:<12} | {t_rev:<22} | "
        f"{t_liq:<20} | {t_all}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="So sánh lệch khung nến giữa backtest và production.")
    parser.add_argument("--symbols", default="HPG,IJC,AAA", help="Danh sách mã cách nhau bởi dấu phẩy")
    parser.add_argument("--start", default="2026-06-01", help="Ngày bắt đầu (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-09-12", help="Ngày kết thúc (YYYY-MM-DD)")
    parser.add_argument("--dsn", default=None, help="Database DSN override")

    args = parser.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    start_dt = datetime.fromisoformat(args.start).replace(tzinfo=TZ)
    end_dt = datetime.fromisoformat(args.end).replace(hour=23, minute=59, second=59, tzinfo=TZ)

    conn = psycopg.connect(resolve_dsn(args.dsn))
    try:
        res = run_timeframe_comparison(conn, symbols=symbols, start_dt=start_dt, end_dt=end_dt)
        print_report(res)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
