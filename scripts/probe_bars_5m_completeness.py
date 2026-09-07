"""Probe độ đầy đủ của bars (5m) — Brief đợt 12 (2026-09-07).

Task ĐIỀU TRA, chỉ đọc. Không INSERT/UPDATE/DELETE, không đổi config, không sửa
trading/.

Trả lời 3 câu hỏi:
  1. Phân bố số bar/ngày trên TOÀN RỔ (một bảng tần suất duy nhất), liệt kê các
     lượt symbol-ngày > 51 bar, kiểm trùng (symbol, ts).
  2. Bar đầu ngày là mấy giờ (VN)? Phân bố ra sao, theo sàn? Giả thuyết "nhãn
     theo giờ đóng" đúng hay sai (đối chiếu code aggregator/backfill)?
  3. Nếu tìm ra nguyên nhân cụ thể thì nêu; không tìm ra thì nói thẳng.

Mọi phân tích dùng MỘT CTE bars_day (số bar/symbol/ngày VN) cho toàn bảng —
không truy vấn riêng cho từng câu hỏi. Ngày VN = ts AT TIME ZONE 'Asia/Ho_Chi_Minh'.

CLI:
    uv run python scripts/probe_bars_5m_completeness.py [--dsn ...]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _db_common import resolve_dsn

from trading.storage.db import Storage

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

TZ_SQL = "AT TIME ZONE 'Asia/Ho_Chi_Minh'"

#: Ngưỡng "ngày backfill toàn rổ" (kỷ nguyên 03/04-07/08): tổng bar/ngày >= 5000.
#: 07/07/2026 chỉ có 349 bar toàn thị trường -> tự bị loại khỏi kỷ nguyên này.
MIN_BARS_FOR_FULL_ERA = 5000

#: Một ngày giao dịch bình thường của 1 mã thanh khoản HOSE là ~46 bar (xem kết
#: luận). Ngưỡng này chỉ dùng để gắn nhãn "ngày đầy đủ" trong báo cáo phụ.
FULL_DAY_BARS = 45

DAY_COUNTS_SQL = f"""
    WITH bars_day AS (
        SELECT symbol,
               (ts {TZ_SQL})::date AS d,
               count(*)             AS n_bars
        FROM bars
        GROUP BY symbol, (ts {TZ_SQL})::date
    )
"""


def q(conn, sql: str, params=None):
    return conn.execute(sql, params or ()).fetchall()


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe độ đầy đủ bars 5m (chỉ đọc)")
    ap.add_argument("--dsn", default=None, help="Postgres connection DSN")
    args = ap.parse_args()

    st = Storage(resolve_dsn(args.dsn))
    with st.conn() as c:
        (n_rows, n_syms, ts_min, ts_max) = q(
            c,
            "SELECT count(*), count(DISTINCT symbol), min(ts), max(ts) FROM bars",
        )[0]
        (n_zero,) = q(
            c, "SELECT count(*) FROM bars WHERE close = 0 OR volume = 0"
        )[0]
        (n_offgrid,) = q(
            c,
            f"""SELECT count(*) FROM bars
                WHERE EXTRACT(second FROM ts {TZ_SQL}) <> 0
                   OR mod(EXTRACT(minute FROM ts {TZ_SQL})::int, 5) <> 0""",
        )[0]

    sep = "=" * 100
    print(sep)
    print("PROBE ĐỘ ĐẦY ĐỦ BARS (5m) — BRIEF ĐỢT 12 — CHỈ ĐỌC, KHÔNG SỬA DỮ LIỆU")
    print(sep)
    print(f"Tổng bar            : {n_rows:,}")
    print(f"Số mã (distinct)    : {n_syms}")
    print(f"Cửa sổ dữ liệu      : {ts_min} -> {ts_max} (UTC)")
    print(f"  = ngày VN         : {ts_min.astimezone()} -> {ts_max.astimezone()}")
    print(f"Bar close=0/vol=0   : {n_zero:,} (bar 0 — chỗ trống phiên đấu giá)")
    print(f"Bar lệch mốc 5 phút : {n_offgrid:,} (second<>0 hoặc minute%5<>0)")

    # ---------------------------------------------------------------- Q1
    print("\n" + sep)
    print("CÂU 1 — PHÂN BỐ SỐ BAR/NGÀY TRÊN TOÀN RỔ (MỘT BẢNG TẦN SUẤT DUY NHẤT)")
    print(sep)

    with st.conn() as c:
        hist_all = q(
            c,
            DAY_COUNTS_SQL
            + """
            SELECT n_bars, count(*) AS symbol_days
            FROM bars_day GROUP BY n_bars ORDER BY n_bars""",
        )
        hist_full_era = q(
            c,
            DAY_COUNTS_SQL
            + """
            SELECT n_bars, count(*) AS symbol_days
            FROM bars_day
            WHERE d IN (
                SELECT d FROM bars_day GROUP BY d HAVING sum(n_bars) >= %s
            )
            GROUP BY n_bars ORDER BY n_bars""",
            (MIN_BARS_FOR_FULL_ERA,),
        )

    print("Bảng tần suất TOÀN BỘ dữ liệu (mọi ngày có bar):")
    print(f"  {'số bar/ngày':>12} | {'số symbol-ngày':>15}")
    for n, cnt in hist_all:
        print(f"  {n:>12} | {cnt:>15}")
    print("  (chú thích: 'ngày' = ngày VN; 1 symbol-ngày = 1 mã trong 1 ngày có bar)")

    print("\nCùng bảng này, chỉ tính những NGÀY BACKFILL TOÀN RỔ "
          f"(tổng bar/ngày >= {MIN_BARS_FOR_FULL_ERA:,} — kỷ nguyên 03/04→07/08):")
    print(f"  {'số bar/ngày':>12} | {'số symbol-ngày':>15}")
    for n, cnt in hist_full_era:
        print(f"  {n:>12} | {cnt:>15}")

    # Ngày thuộc kỷ nguyên backfill toàn rổ = ? và các ngày "dị thường"
    with st.conn() as c:
        day_totals = q(
            c,
            DAY_COUNTS_SQL
            + """
            SELECT d, sum(n_bars) AS tot, count(*) AS syms
            FROM bars_day GROUP BY d ORDER BY d""",
        )
    full_days = [r for r in day_totals if r[1] >= MIN_BARS_FOR_FULL_ERA]
    print(f"\nSố ngày backfill toàn rổ (tot>= {MIN_BARS_FOR_FULL_ERA:,} bar): "
          f"{len(full_days)} — từ {full_days[0][0]} đến {full_days[-1][0]}")

    # Những ngày < 100 mã mà vẫn có bar (sau 08/08 = kỷ nguyên live basket)
    late = [r for r in day_totals if r[1] < MIN_BARS_FOR_FULL_ERA and r[0] > full_days[-1][0]]
    if late:
        print(f"\nCác ngày SAU kỷ nguyên toàn rổ (từ {late[0][0]}):")
        for d, tot, syms in late:
            print(f"  {d} ({d.strftime('%a')}): {tot:,} bar / {syms} mã")

    # ---------------------------------------------------------------- >51
    print("\n" + "-" * 100)
    print("CÂU 1 (tiếp) — CÁC LƯỢT SYMBOL-NGÀY > 51 BAR (vượt '51 lý thuyết')")
    print("-" * 100)

    with st.conn() as c:
        over51 = q(
            c,
            DAY_COUNTS_SQL
            + """
            SELECT bd.symbol, bd.d, bd.n_bars, u.exchange
            FROM bars_day bd
            LEFT JOIN symbol_universe u ON u.symbol = bd.symbol
            WHERE bd.n_bars > 51
            ORDER BY bd.symbol, bd.d""",
        )
    print(f"Tổng số lượt > 51 bar: {len(over51)}")
    print("Liệt kê đầy đủ (symbol | ngày VN | số bar | sàn):")
    for sym, d, n, exch in over51:
        print(f"  {sym:<8} {d}  n={n:>3}  {exch or '(ngoài symbol_universe)'}")

    exch_cnt: dict[str, int] = {}
    for _sym, _d, _n, exch in over51:
        exch_cnt[exch or "?"] = exch_cnt.get(exch or "?", 0) + 1
    print("Theo sàn:", dict(sorted(exch_cnt.items(), key=lambda kv: -kv[1])))

    # Cơ chế của các ngày > 51: bar CUỐI cùng lúc mấy giờ? Có bar-0 không?
    with st.conn() as c:
        last_lbl = q(
            c,
            DAY_COUNTS_SQL
            + """
            SELECT last_t, count(*) AS n
            FROM (
                SELECT bd.symbol, bd.d,
                       max(to_char(b.ts AT TIME ZONE 'Asia/Ho_Chi_Minh', 'HH24:MI'))
                           AS last_t
                FROM bars_day bd
                JOIN bars b ON b.symbol = bd.symbol
                    AND (b.ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date = bd.d
                WHERE bd.n_bars > 51
                GROUP BY bd.symbol, bd.d
            ) x GROUP BY last_t ORDER BY n DESC""",
        )
        (n_over51_with_zero,) = q(
            c,
            DAY_COUNTS_SQL
            + """
            SELECT count(*) FROM (
                SELECT bd.symbol, bd.d
                FROM bars_day bd
                JOIN bars b ON b.symbol = bd.symbol
                    AND (b.ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date = bd.d
                WHERE bd.n_bars > 51 AND (b.close = 0 OR b.volume = 0)
                GROUP BY bd.symbol, bd.d
            ) x""",
        )[0]
    n_over51_late = sum(n for t, n in last_lbl if t >= "14:50")
    print("\nPhân bố nhãn giờ của bar CUỐI CÙNG trong các ngày > 51 bar "
          "(cơ chế: in khớp trễ cuối ngày hay bar-0 slot đấu giá):")
    for t, cnt in last_lbl:
        print(f"  bar cuối {t} -> {cnt} ngày")
    print(f"  => {n_over51_late}/{len(over51)} ngày (>51) có bar cuối >= 14:50 "
          f"(in khớp sau khung 51-bar chuẩn, tới 14:55); "
          f"{len(over51) - n_over51_late} ngày còn lại kết thúc 14:45 — trong đó "
          f"{n_over51_with_zero} ngày có chứa bar close=0/vol=0 (slot đấu giá).")

    # Kiểm trùng (symbol, ts)
    with st.conn() as c:
        dups = q(
            c,
            "SELECT symbol, ts, count(*) FROM bars "
            "GROUP BY symbol, ts HAVING count(*) > 1 LIMIT 10",
        )
    print(f"\nBản ghi trùng (symbol, ts): {len(dups)} "
          "(schema.sql:12 PRIMARY KEY (symbol, ts) — trùng không thể tồn tại; "
          "truy vấn HAVING count>1 chạy để xác minh thực tế)")
    if dups:
        for r in dups:
            print("  ", r)

    # Bar close=0/vol=0 nằm ở đâu (chỗ trống phiên đấu giá)? Và theo kỷ nguyên?
    with st.conn() as c:
        zero_lbl = q(
            c,
            f"""SELECT to_char(ts {TZ_SQL}, 'HH24:MI') AS t, count(*)
                FROM bars WHERE close = 0 OR volume = 0
                GROUP BY 1 ORDER BY 1""",
        )
        (n_zero_symdays,) = q(
            c,
            f"""SELECT count(DISTINCT (symbol, (ts {TZ_SQL})::date))
                FROM bars WHERE close = 0 OR volume = 0""",
        )[0]
        (n_zero_bulk,) = q(
            c,
            f"""SELECT count(*) FROM bars
                WHERE (close = 0 OR volume = 0)
                  AND (ts {TZ_SQL})::date <= '2026-08-07'""",
        )[0]
    print(f"\nPhân bố {n_zero} bar close=0/vol=0 ({n_zero_symdays} symbol-ngày) "
          "theo nhãn giờ (nghi chỗ trống phiên đấu giá):")
    for t, cnt in zero_lbl:
        print(f"  {t} -> {cnt}")
    print(f"  Trong kỷ nguyên toàn rổ (<= 07/08/2026): {n_zero_bulk} bar "
          f"— tức {n_zero - n_zero_bulk} bar đều xuất hiện sau đó (thời live).")

    # ---------------------------------------------------------------- Q2
    print("\n" + sep)
    print("CÂU 2 — BAR ĐẦU TIÊN MỖI NGÀY LÀ MẤY GIỜ (VN)?")
    print(sep)

    with st.conn() as c:
        first_all = q(
            c,
            f"""
            SELECT first_t, count(*) AS symbol_days
            FROM (
                SELECT symbol, (ts {TZ_SQL})::date AS d,
                       min(to_char(ts {TZ_SQL}, 'HH24:MI')) AS first_t
                FROM bars
                GROUP BY symbol, (ts {TZ_SQL})::date
            ) y
            GROUP BY first_t ORDER BY symbol_days DESC, first_t""",
        )
    print("Phân bố giờ bar ĐẦU TIÊN trong ngày — TOÀN BỘ symbol-ngày:")
    print(f"  {'giờ (VN)':>10} | {'số symbol-ngày':>15}")
    for t, cnt in first_all:
        print(f"  {t:>10} | {cnt:>15}")

    with st.conn() as c:
        first_by_exch = q(
            c,
            f"""
            SELECT u.exchange, first_t, count(*) AS n
            FROM (
                SELECT symbol, (ts {TZ_SQL})::date AS d,
                       min(to_char(ts {TZ_SQL}, 'HH24:MI')) AS first_t
                FROM bars
                GROUP BY symbol, (ts {TZ_SQL})::date
            ) y
            LEFT JOIN symbol_universe u ON u.symbol = y.symbol
            GROUP BY u.exchange, first_t
            ORDER BY u.exchange, n DESC""",
        )
    print("\nPhân bố giờ bar đầu tiên THEO SÀN (top 5 giờ mỗi sàn):")
    cur = None
    for exch, t, cnt in first_by_exch:
        if exch != cur:
            print(f"  [{(exch or 'ngoài symbol_universe')}]")
            cur = exch
        print(f"     {t} -> {cnt}")

    print("""
Giả thuyết cần kiểm: "bar 5m gắn nhãn theo giờ ĐÓNG nên bar 09:00-09:05 mang
nhãn 09:05".

KẾT LUẬN: SAI — nhãn là giờ MỞ bucket (floor xuống mốc 5 phút):
- trading/collector/aggregator.py:24-26 (live):
      def _bucket(self, ts):
          minute = (ts.minute // (self.interval.seconds // 60)) * (self.interval.seconds // 60)
          return ts.replace(minute=minute, second=0, microsecond=0)
- trading/collector/backfill.py:30 (gom 1m -> 5m):
      bucket = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
  và backfill.py:68-78/_parse_trading_date giữ NGUYÊN giờ provider trả về, không
  dịch chuyển +5 phút nào.

Bằng chứng thực nghiệm mạnh nhất: ngày 07/07/2026 (xem Câu 3) hầu hết mã chỉ còn
ĐÚNG 1 bar khớp lệnh đóng cửa, và bar đó mang nhãn 14:45 (VD: VCB 07/07 bar duy
nhất = 14:45). Khớp lệnh định kỳ đóng cửa HOSE xảy ra tại 14:45:00 -> nếu nhãn
theo giờ đóng, bar phải là 14:50; thực tế là 14:45 => nhãn = giờ mở bucket chứa
cú khớp 14:45:00.

Vì vậy "bar đầu ngày 09:15" KHÔNG phải lỗi lệch nhãn: HOSE khớp lệnh định kỳ mở
cửa (ATO) chỉ khớp tại 09:15:00, không có khớp lệnh liên tục trước đó -> bucket
09:00/09:05/09:10 không có cú khớp nào -> không có bar. HNX/UPCOM khớp từ 09:00
nên bar đầu ngày của họ là 09:00.""")

    # ---------------------------------------------------------------- Q3
    print("\n" + sep)
    print("CÂU 3 — NGUYÊN NHÂN QUAN SÁT ĐƯỢC")
    print(sep)

    # Ngày giao dịch thật = ngày có >= 100 mã trong bars_daily (quy ước như
    # scripts/check_data_completeness.py). Đối chiếu với bars 5m để tìm ngày mất.
    bulk_start = full_days[0][0] if full_days else None
    bulk_end = full_days[-1][0] if full_days else None
    with st.conn() as c:
        lost_days = q(
            c,
            DAY_COUNTS_SQL
            + f"""
            SELECT d.d AS ngay, d.n_daily, COALESCE(b5.tot, 0) AS bars_5m
            FROM (
                SELECT (ts {TZ_SQL})::date AS d,
                       count(DISTINCT symbol) AS n_daily
                FROM bars_daily
                WHERE (ts {TZ_SQL})::date BETWEEN %s AND %s
                GROUP BY (ts {TZ_SQL})::date
                HAVING count(DISTINCT symbol) >= 100
            ) d
            LEFT JOIN (
                SELECT d, sum(n_bars) AS tot
                FROM bars_day GROUP BY d
            ) b5 ON b5.d = d.d
            WHERE b5.tot IS NULL OR b5.tot < %s
            ORDER BY d.d""",
            (bulk_start, bulk_end, MIN_BARS_FOR_FULL_ERA),
        )
    print(f"\n3A. MẤT DỮ LIỆU TOÀN THỊ TRƯỜNG trong kỷ nguyên toàn rổ "
          f"({bulk_start} -> {bulk_end}, ngày giao dịch xác nhận bằng bars_daily "
          f">= 100 mã): {len(lost_days)} ngày")
    for ngay, n_daily, bars_5m in lost_days:
        print(f"  {ngay} ({ngay.strftime('%a')}): bars_daily {n_daily} mã "
              f"nhưng bars 5m chỉ có {bars_5m:,} bar "
              f"(bình thường ~10.500 bar/ngày)")

    # Phân bố n_bar của 07/07 (chứng minh chỉ còn bar đóng cửa)
    with st.conn() as c:
        dist_707 = q(
            c,
            DAY_COUNTS_SQL
            + """
            SELECT n_bars, count(*) AS syms
            FROM bars_day WHERE d = '2026-07-07'
            GROUP BY n_bars ORDER BY n_bars""",
        )
    print("\n  Chi tiết 07/07/2026 (phân bố số bar/mã — hầu hết chỉ còn 1 bar "
          "khớp lệnh đóng cửa 14:45):")
    for n, cnt in dist_707:
        print(f"    n={n:>3} bar -> {cnt} mã")
    with st.conn() as c:
        row = q(
            c,
            "SELECT open, high, low, close, volume FROM bars_daily "
            "WHERE symbol = 'VCB' AND (ts " + TZ_SQL + ")::date = '2026-07-07'",
        )[0]
        print("    Đối chứng: VCB 07/07 có bar DAILY đầy đủ (o,h,l,c,vol) =", row,
              "-> thị trường giao dịch bình thường, chỉ dữ liệu 5m là mất.")
    zero_bulk_note = (
        "nằm trong kỷ nguyên toàn rổ (cửa sổ đo đợt 11, <= 07/08) → KHÔNG ảnh hưởng"
        if n_zero_bulk == 0
        else f"nằm trong kỷ nguyên toàn rổ ({n_zero_bulk} bar) → CÓ thể ảnh hưởng cửa sổ đo"
    )
    print(f"""    => Cơ chế (backfill 5m lỗi/gián đoạn ngày đó? API chỉ trả được phần
       cuối phiên?) KHÔNG xác định được từ DB vì task chỉ đọc — cần đối chiếu
       log backfill/collector của 06-07/07 hoặc chạy thử 1 lần fetch lại 1 mã.

3B. BAR 0 (close=0/vol=0): {n_zero} bar, {n_zero_symdays} symbol-ngày — toàn bộ
    nằm ở các slot phiên đấu giá (09:00-09:10, 14:30-14:40, xem Câu 1).
    Provider trả row rỗng cho slot đấu giá của một số mã-ngày; {n_zero_bulk} bar
    {zero_bulk_note}. Không phải lỗi aggregator (live không bao giờ tạo bar 0).""")

    # Kỷ nguyên live: 6 mã rồi 3 mã
    with st.conn() as c:
        late_syms_6 = q(
            c,
            "SELECT DISTINCT symbol FROM bars "
            "WHERE (ts " + TZ_SQL + ")::date BETWEEN '2026-08-10' AND '2026-08-13' "
            "ORDER BY symbol",
        )
        late_syms_3 = q(
            c,
            "SELECT DISTINCT symbol FROM bars "
            "WHERE (ts " + TZ_SQL + ")::date >= '2026-08-14' ORDER BY symbol",
        )
    print(f"\n3C. Sau kỷ nguyên toàn rổ: 10-13/08 chỉ còn {len(late_syms_6)} mã có "
          f"bar 5m ({', '.join(s[0] for s in late_syms_6)}); từ 14/08 chỉ còn "
          f"{len(late_syms_3)} mã ({', '.join(s[0] for s in late_syms_3)}).")
    print("""    => Việc "thiếu bar" của 307 mã sau 08/08 là do backfill toàn rổ ĐÃ
       DỪNG (chỉ còn collector/live basket ghi bar), không phải bar bị mất lẻ
       tẻ. Mọi kết luận đo lường của đợt 11 dùng cửa sổ 03/04→07/08 nên không
       bị ảnh hưởng bởi thay đổi này.""")

    # Nhóm mã mỏng (residual): tỉ lệ ngày >= 45 bar thấp nhưng vẫn giao dịch đều
    with st.conn() as c:
        thin = q(
            c,
            DAY_COUNTS_SQL
            + """
            SELECT symbol, count(*) AS days,
                   count(*) FILTER (WHERE n_bars >= %s) AS full_days
            FROM bars_day GROUP BY symbol
            HAVING count(*) >= 60 AND count(*) FILTER (WHERE n_bars >= %s) < 40
            ORDER BY (count(*) FILTER (WHERE n_bars >= %s))::float / count(*) ASC,
                     count(*) DESC, symbol
            LIMIT 15""",
            (FULL_DAY_BARS, FULL_DAY_BARS, FULL_DAY_BARS),
        )
    print("\n3D. Mã có >= 60 ngày bar nhưng < 40 ngày 'đầy đủ' (>= 45 bar) — "
          "nhóm 'mỏng' còn lại (mỏng nhất lên đầu):")
    for sym, days, n_full in thin:
        print(f"  {sym:<8} days={days:>4} full_days(>=45)={n_full:>4}")
    exch_str = ", ".join(f"{k}: {v}" for k, v in sorted(exch_cnt.items(), key=lambda kv: -kv[1]))
    print(f"""    => Với nhóm này, số bar thấp hơn hẳn VCB/FPT (90/91 ngày đạt 46 bar).
       Khả năng là thanh khoản mỏng (ít cú khớp, in theo từng lệnh) nhưng
       KHÔNG loại trừ mất dữ liệu — task chỉ đọc không đủ để phân biệt; nếu
       cần thì brief riêng đối chiếu nguồn cú khớp.

3E. TÓM LẠI:
    - Trùng (symbol, ts): {len(dups)} (schema PK). Lệch mốc 5 phút: {n_offgrid}.
      Mọi bar nằm đúng lưới 5 phút.
    - "46 bar/ngày" (mode) KHÔNG phải thiếu bar: HOSE chỉ khớp liên tục
      09:15-11:30 và 13:00-14:30 + khớp đóng cửa 14:45 -> tối đa 27+18+1 = 46
      bar có cú khớp thật. Quy ước 51 (= 30 + 21 bucket của SESSIONS
      09:00-11:30/13:00-14:45 trong trading/calendar_vn.py:5) giả định có khớp
      ở 09:00-09:10 và 14:30-14:40 — hai khoảng này là phiên ĐẤU GIÁ (không có
      khớp lệnh liên tục) nên bar không tồn tại, đó là BẢN CHẤT DỮ LIỆU.
    - Lượt > 51 bar ({len(over51)} lượt, tới 54) không phải trùng lặp: theo sàn
      = {exch_str}; {n_over51_late}/{len(over51)} ngày có bar cuối >= 14:50
      (in khớp trễ tới 14:55 của nhóm mã UPCOM, vượt khung 51-bar vốn thiết kế
      theo giờ HOSE); {len(over51) - n_over51_late} ngày còn lại kết thúc 14:45.
      Trong toàn bộ {len(over51)} ngày, {n_over51_with_zero} ngày có chứa bar-0
      slot đấu giá (các ngày live của AAA/IJC/HII 08/13+). Lưu ý: nhãn sàn lấy
      từ symbol_universe có thể lệch với niêm yết hiện tại của vài mã (VD: BVB
      có nhịp in giống HNX nhưng bảng ghi HOSE).
    - Bar close=0/vol=0 ({n_zero} bar): {n_zero_bulk} bar {zero_bulk_note},
      không làm nhiễu kết quả đo đợt 11 ({'CÓ thể làm nhiễu' if n_zero_bulk > 0 else 'sạch'}).
    - MẤT THẬT (không phải bản chất): 07/06/2026 (0 bar toàn thị trường) và
      07/07/2026 (chỉ còn bar đóng cửa) trong kỷ nguyên toàn rổ; cơ chế chưa
      xác định. Sau 08/08 backfill toàn rổ dừng (chỉ 3-6 mã live còn được ghi).
    - Ảnh hưởng tới đợt 11: cửa sổ đo 03/04→07/08 còn 2 ngày mất (06-07/07)
      làm giảm nhẹ cỡ mẫu (~2/{len(full_days)} ngày, ~2%): ước lượng 574 ->
      ~586 lệnh, không đổi kết luận PF 0,47.""")

    print("\n" + sep)
    print("HẾT PROBE — script chỉ đọc, không sửa dữ liệu.")
    print(sep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
