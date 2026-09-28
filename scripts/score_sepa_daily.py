"""Bảng điểm SEPA (Minervini Trend Template) dạng hiển thị hàng ngày.

Đợt 119: Triển khai bảng điểm mô tả trạng thái kỹ thuật 7 tiêu chí SEPA
kết hợp tiêu chí thứ tám: Sức mạnh giá tương đối (RS/SM).

CẢNH BÁO QUAN TRỌNG:
Dữ liệu đọc sau mốc niêm phong 2023-01-01 (giờ VN). Bảng điểm này CHỈ MÔ TẢ
trạng thái kỹ thuật hiện tại, TUYỆT ĐỐI KHÔNG dùng để đo lường hiệu năng,
tính toán lợi suất tương lai, hay dự báo mua/bán.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from datetime import date
from pathlib import Path
from typing import Any

import psycopg

# Đảm bảo import được khi chạy trực tiếp từ thư mục gốc hoặc từ scripts/
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from _db_common import resolve_dsn
except ImportError:
    from scripts._db_common import resolve_dsn

try:
    from screen_vcp_daily import (
        RANGE_WINDOW,
        TREND_KEYS,
        TREND_MIN_BARS,
        bar_date,
        clean_bars,
        rolling_max,
        rolling_mean,
        rolling_min,
        trend_conditions,
    )
except ImportError:
    from scripts.screen_vcp_daily import (
        RANGE_WINDOW,
        TREND_KEYS,
        TREND_MIN_BARS,
        bar_date,
        clean_bars,
        rolling_max,
        rolling_mean,
        rolling_min,
        trend_conditions,
    )
from trading.metrics import empirical_percentile_rank
from trading.models import Bar

WARNING_BANNER = """========================================================================================
CẢNH BÁO NIÊM PHONG (SEALED HOLDOUT NOTICE):
Dữ liệu đang được đọc sau mốc niêm phong 2023-01-01 (giờ VN).
Bảng điểm này CHỈ PHỤC VỤ MÔ TẢ TRẠNG THÁI KỸ THUẬT HIỆN TẠI (Descriptive Scorecard).
TUYỆT ĐỐI KHÔNG dùng cho bất kỳ phép đo hiệu năng, kiểm định lợi thế hay dự báo lợi suất nào.
========================================================================================"""

CRITERIA_LABELS = {
    "c1_close_tren_sma150_200": "Giá trên MA150 và MA200",
    "c2_sma150_tren_sma200": "MA150 trên MA200",
    "c3_sma200_di_len": "MA200 hướng lên ≥ 1 tháng",
    "c4_sma50_tren_sma150_200": "MA50 trên cả MA150 và MA200",
    "c5_close_tren_sma50": "Giá trên MA50",
    "c6_cach_day_252_nen": "Giá ≥ 30% trên đáy 52 tuần",
    "c7_gan_dinh_252_nen": "Giá trong 25% của đỉnh 52 tuần",
}


def calculate_boundary_percentages(close: float, low252: float, high252: float) -> tuple[float, float]:
    """Tính % trên đáy 52 tuần (252 nến) và % cách đỉnh 52 tuần (252 nến).

    Args:
        close: Giá đóng cửa hiện tại (P).
        low252: Giá thấp nhất trong 252 nến (đáy 52 tuần).
        high252: Giá cao nhất trong 252 nến (đỉnh 52 tuần).

    Returns:
        tuple[float, float]: (% trên đáy, % cách đỉnh) tính theo đơn vị phần trăm (%).
            % trên đáy = (P / low252 - 1.0) * 100
            % cách đỉnh = (1.0 - P / high252) * 100
    """
    if low252 <= 0 or high252 <= 0:
        raise ValueError("low252 và high252 phải lớn hơn 0")
    pct_above_low = (close / low252 - 1.0) * 100.0
    pct_below_high = (1.0 - close / high252) * 100.0
    return pct_above_low, pct_below_high


def calculate_rs_raw(closes: list[float]) -> float | None:
    """Tính RS_raw theo công thức trọng số chuẩn:

    RS_raw = 0.4 * (P / P_63 - 1)
           + 0.2 * (P / P_126 - 1)
           + 0.2 * (P / P_189 - 1)
           + 0.2 * (P / P_252 - 1)

    Yêu cầu chuỗi đóng cửa phải có ít nhất 253 nến sạch (P là nến hiện tại closes[-1],
    P_k là closes[-1 - k]). Nếu không đủ, trả về None (không gán 0 hay 50).
    """
    if len(closes) < 253:
        return None

    p = closes[-1]
    p63 = closes[-1 - 63]
    p126 = closes[-1 - 126]
    p189 = closes[-1 - 189]
    p252 = closes[-1 - 252]

    if p63 <= 0 or p126 <= 0 or p189 <= 0 or p252 <= 0:
        return None

    return (
        0.4 * (p / p63 - 1.0)
        + 0.2 * (p / p126 - 1.0)
        + 0.2 * (p / p189 - 1.0)
        + 0.2 * (p / p252 - 1.0)
    )


def calculate_rs_ranks(rs_raw_by_symbol: dict[str, float]) -> dict[str, int]:
    """Quy đổi RS_raw thành RS_rank thang 1–99 dựa trên phân vị thực nghiệm.

    Sử dụng empirical_percentile_rank từ trading.metrics trên vũ trụ đủ điều kiện.
    RS_rank = max(1, min(99, round(percentile)))
    """
    if not rs_raw_by_symbol:
        return {}

    raw_values = list(rs_raw_by_symbol.values())
    ranks: dict[str, int] = {}
    for sym, raw_val in rs_raw_by_symbol.items():
        pct = empirical_percentile_rank(raw_values, raw_val)
        rank_val = max(1, min(99, round(pct)))
        ranks[sym] = rank_val
    return ranks


def evaluate_sepa_single(
    bars: list[Bar],
    as_of: date | None = None,
) -> dict[str, Any]:
    """Đánh giá 7 tiêu chí SEPA và chuẩn bị dữ liệu RS cho một mã tại ngày as_of."""
    # 1. Lọc nến đến hết ngày as_of (theo giờ VN qua bar_date)
    if as_of is not None and bars and bar_date(bars[-1]) > as_of:
        bars_to_date = [b for b in bars if bar_date(b) <= as_of]
    else:
        bars_to_date = bars

    cleaned, dropped = clean_bars(bars_to_date)
    symbol = bars[0].symbol if bars else "UNKNOWN"

    if len(cleaned) < TREND_MIN_BARS:
        return {
            "symbol": symbol,
            "as_of": bar_date(cleaned[-1]) if cleaned else as_of,
            "eligible_trend": False,
            "eligible_rs": False,
            "cleaned_bars": len(cleaned),
            "dropped_bars": dropped,
            "reason": f"Không đủ {TREND_MIN_BARS} nến sạch ({len(cleaned)} nến)",
            "score": 0,
            "conditions": dict.fromkeys(TREND_KEYS, False),
            "close": cleaned[-1].close if cleaned else None,
            "ma50": None,
            "ma150": None,
            "ma200": None,
            "ma200_prev21": None,
            "low252": None,
            "high252": None,
            "pct_above_low": None,
            "pct_below_high": None,
            "rs_raw": None,
        }

    # Tính toán các chỉ báo kỹ thuật tại nến cuối cùng (index = len(cleaned) - 1)
    closes = [b.close for b in cleaned]
    highs = [b.high for b in cleaned]
    lows = [b.low for b in cleaned]

    sma50 = rolling_mean(closes, 50)
    sma150 = rolling_mean(closes, 150)
    sma200 = rolling_mean(closes, 200)
    win_low = rolling_min(lows, RANGE_WINDOW)
    win_high = rolling_max(highs, RANGE_WINDOW)

    last_bar = cleaned[-1]
    last_date = bar_date(last_bar)
    p = last_bar.close

    m50 = sma50[-1]
    m150 = sma150[-1]
    m200 = sma200[-1]
    m200_prev21 = sma200[-22] if len(sma200) >= 22 else None
    lo252 = win_low[-1]
    hi252 = win_high[-1]

    # Đánh giá 7 điều kiện bằng trend_conditions (t = len(cleaned) để i = t - 1)
    conds = trend_conditions(
        cleaned,
        len(cleaned),
        sma50=sma50,
        sma150=sma150,
        sma200=sma200,
        win_low=win_low,
        win_high=win_high,
    )
    score = sum(1 for v in conds.values() if v)

    pct_above_low, pct_below_high = calculate_boundary_percentages(p, lo252, hi252)
    rs_raw = calculate_rs_raw(closes)

    return {
        "symbol": symbol,
        "as_of": last_date,
        "eligible_trend": True,
        "eligible_rs": rs_raw is not None,
        "cleaned_bars": len(cleaned),
        "dropped_bars": dropped,
        "score": score,
        "conditions": conds,
        "close": p,
        "ma50": m50,
        "ma150": m150,
        "ma200": m200,
        "ma200_prev21": m200_prev21,
        "low252": lo252,
        "high252": hi252,
        "pct_above_low": pct_above_low,
        "pct_below_high": pct_below_high,
        "rs_raw": rs_raw,
    }


def format_single_symbol_report(
    item: dict[str, Any],
    rs_rank: int | None,
    rs_universe_size: int,
) -> str:
    """Định dạng bảng điểm 8 dòng chi tiết cho một mã cổ phiếu."""
    lines: list[str] = [WARNING_BANNER, ""]

    sym = item["symbol"]
    d_str = item["as_of"].isoformat() if item["as_of"] else "N/A"
    lines.append(f"BẢNG ĐIỂM KỸ THUẬT SEPA (MINERVINI TREND TEMPLATE) — MÃ: {sym}")

    if sym.upper() in load_untrusted_symbols():
        lines.append(
            "[CHU Y] Ma nay nam trong danh sach du lieu dieu chinh gia KHONG tin cay "
            "(exclusions.txt). MA150/MA200 va bien do 52 tuan deu co the SAI. "
            "KHONG dung bang diem duoi day."
        )
    lines.append(f"Ngày đánh giá: {d_str} (Giờ VN) | Tổng số nến sạch: {item['cleaned_bars']}")

    if not item["eligible_trend"]:
        lines.append(f"\n[KHÔNG ĐỦ ĐIỀU KIỆN ĐÁNH GIÁ]: {item.get('reason')}")
        return "\n".join(lines)

    p = item["close"]
    m50 = item["ma50"]
    m150 = item["ma150"]
    m200 = item["ma200"]
    m200_p = item["ma200_prev21"]
    lo252 = item["low252"]
    hi252 = item["high252"]
    pct_lo = item["pct_above_low"]
    pct_hi = item["pct_below_high"]
    conds = item["conditions"]
    score = item["score"]

    lines.append(f"Giá đóng cửa: {p:,.1f} VND | Điểm xu hướng SEPA: {score}/7\n")
    lines.append(f"{'#':<3} | {'Tiêu chí':<35} | {'Giá trị kỹ thuật':<42} | {'Trạng thái'}")
    lines.append("-" * 95)

    def op(a: float, b: float) -> str:
        """Toan tu so sanh THAT giua a va b.

        Truoc day cac dong 2, 4, 5 ghim cung ">" nen khi dieu kien KHONG dat,
        bang van in ra mot bat dang thuc sai, vi du "MA50=48,071.2 > MA150=53,686.7".
        Cong cu nay chi co mot viec la phat bieu su that, nen operator phai dung.
        """
        if a > b:
            return ">"
        if a < b:
            return "<"
        return "="

    # 1
    st1 = "ĐẠT" if conds["c1_close_tren_sma150_200"] else "Không đạt"
    val1 = f"P={p:,.1f} {op(p, m150)} MA150={m150:,.1f}, {op(p, m200)} MA200={m200:,.1f}"
    lines.append(f"1   | {CRITERIA_LABELS['c1_close_tren_sma150_200']:<35} | {val1:<42} | {st1}")

    # 2
    st2 = "ĐẠT" if conds["c2_sma150_tren_sma200"] else "Không đạt"
    val2 = f"MA150={m150:,.1f} {op(m150, m200)} MA200={m200:,.1f}"
    lines.append(f"2   | {CRITERIA_LABELS['c2_sma150_tren_sma200']:<35} | {val2:<42} | {st2}")

    # 3
    st3 = "ĐẠT" if conds["c3_sma200_di_len"] else "Không đạt"
    val3 = f"MA200={m200:,.1f} {op(m200, m200_p)} MA200_21d={m200_p:,.1f}"
    lines.append(f"3   | {CRITERIA_LABELS['c3_sma200_di_len']:<35} | {val3:<42} | {st3}")

    # 4
    st4 = "ĐẠT" if conds["c4_sma50_tren_sma150_200"] else "Không đạt"
    val4 = f"MA50={m50:,.1f} {op(m50, m150)} MA150={m150:,.1f}, {op(m50, m200)} MA200={m200:,.1f}"
    lines.append(f"4   | {CRITERIA_LABELS['c4_sma50_tren_sma150_200']:<35} | {val4:<42} | {st4}")

    # 5
    st5 = "ĐẠT" if conds["c5_close_tren_sma50"] else "Không đạt"
    val5 = f"P={p:,.1f} {op(p, m50)} MA50={m50:,.1f}"
    lines.append(f"5   | {CRITERIA_LABELS['c5_close_tren_sma50']:<35} | {val5:<42} | {st5}")

    # 6
    st6 = "ĐẠT" if conds["c6_cach_day_252_nen"] else "Không đạt"
    val6 = f"{pct_lo:+.1f}% trên đáy (Đáy 252={lo252:,.1f})"
    lines.append(f"6   | {CRITERIA_LABELS['c6_cach_day_252_nen']:<35} | {val6:<42} | {st6}")

    # 7
    st7 = "ĐẠT" if conds["c7_gan_dinh_252_nen"] else "Không đạt"
    val7 = f"{pct_hi:.1f}% cách đỉnh (Đỉnh 252={hi252:,.1f})"
    lines.append(f"7   | {CRITERIA_LABELS['c7_gan_dinh_252_nen']:<35} | {val7:<42} | {st7}")

    # 8 RS
    if rs_rank is not None:
        st8 = "ĐẠT" if rs_rank >= 70 else "Không đạt"
        val8 = f"RS_rank = {rs_rank}/99 (Vũ trụ {rs_universe_size} mã)"
    else:
        st8 = "–"
        val8 = f"Thiếu nến sạch (< 253 nến, Vũ trụ {rs_universe_size} mã)"
    lines.append(f"8   | Sức mạnh giá RS ≥ 70 (Thang 1-99)       | {val8:<42} | {st8}")
    lines.append("-" * 95)
    lines.append(f"KẾT QUẢ TỔNG HỢP: Điểm SEPA = {score}/7 | Tiêu chí RS ≥ 70: {st8}")
    lines.append(
        "\n* Lưu ý: RS_rank được tính xấp xỉ theo trọng số 0.4/0.2/0.2/0.2 trên vũ trụ cổ phiếu đủ điều kiện,\n"
        "  KHÔNG PHẢI là chỉ số bản quyền IBD RS Rating. Bảng điểm mang tính chất mô tả thuần túy kỹ thuật."
    )
    return "\n".join(lines)


EXCLUSIONS_DEFAULT = "exclusions.txt"


def load_untrusted_symbols(path: str = EXCLUSIONS_DEFAULT) -> set[str]:
    """Doc danh sach ma co du lieu dieu chinh gia KHONG tin cay.

    Nguon: `scripts/check_price_adjustment.py --emit-exclusions`. Gom cac ma con
    split chua dieu chinh va cac ma co >= 5% nen OHLC <= 0. Voi nhung ma do,
    MA150/MA200 va bien do 52 tuan deu sai, nen bang diem cua chung khong dung
    duoc — phai danh dau, khong duoc in nhu mot dong binh thuong.

    Khong co file thi tra ve tap rong va NOI RA, khong im lang coi nhu sach.
    """
    f = pathlib.Path(path)
    if not f.exists():
        return set()
    out: set[str] = set()
    for line in f.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if t and not t.startswith("#"):
            out.add(t.upper())
    return out


def format_multi_symbol_report(
    eval_results: list[dict[str, Any]],
    rs_ranks: dict[str, int],
    rs_universe_size: int,
    ineligible_info: list[tuple[str, str]],
    as_of: date,
) -> str:
    """Định dạng bảng tổng hợp SEPA cho toàn bộ vũ trụ cổ phiếu."""
    lines: list[str] = [WARNING_BANNER, ""]

    lines.append("BẢNG TỔNG HỢP ĐIỂM SEPA VÀ RS CHO TOÀN BỘ VŨ TRỤ CỔ PHIẾU HOẠT ĐỘNG")
    lines.append(f"Phiên giao dịch: {as_of.isoformat()} (Giờ VN)")
    lines.append(f"Tổng số mã đủ điều kiện xu hướng SEPA (≥ 252 nến): {len(eval_results)}")
    lines.append(f"Tổng số mã đủ điều kiện xếp hạng RS (≥ 253 nến): {rs_universe_size}")
    lines.append(f"Số mã bị loại khỏi vũ trụ: {len(ineligible_info)}")

    untrusted = load_untrusted_symbols()
    flagged = sorted(r["symbol"] for r in eval_results if r["symbol"] in untrusted)
    if not untrusted:
        lines.append(
            "[CHU Y] Khong doc duoc exclusions.txt, nen KHONG danh dau duoc ma co "
            "du lieu dieu chinh gia khong tin cay. Chay "
            "`scripts/check_price_adjustment.py --emit-exclusions exclusions.txt` truoc."
        )
    elif flagged:
        lines.append(
            f"[CHU Y] {len(flagged)}/{len(eval_results)} ma co du lieu dieu chinh gia "
            f"KHONG tin cay, danh dau (!) o cot Ma. Voi cac ma nay MA150/MA200 va bien do "
            f"52 tuan deu co the sai, nen KHONG dung bang diem cua chung: "
            f"{', '.join(flagged)}"
        )
    lines.append("")

    # Bảng phân loại mã bị loại
    lines.append("DANH SÁCH MÃ BỊ LOẠI KHỎI VŨ TRỤ ĐÁNH GIÁ:")
    for sym, reason in sorted(ineligible_info):
        lines.append(f"  - {sym:<6}: {reason}")
    lines.append("")

    # Sắp xếp kết quả: Điểm SEPA giảm dần, sau đó RS rank giảm dần, sau đó mã
    def sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        sym = item["symbol"]
        score = item["score"]
        r = rs_ranks.get(sym, -1)
        return (score, r, sym)

    sorted_results = sorted(eval_results, key=sort_key, reverse=True)

    header = (
        f"{'Mã':<6} | {'Điểm':<5} | {'c1':<2} | {'c2':<2} | {'c3':<2} | {'c4':<2} | "
        f"{'c5':<2} | {'c6':<2} | {'c7':<2} | {'% trên đáy':<11} | {'% cách đỉnh':<12} | "
        f"{'RS_rank':<8} | {'Đạt RS?':<7} | {'Giá đóng':<9}"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for item in sorted_results:
        sym = item["symbol"]
        # Danh dau (!) neu du lieu dieu chinh gia cua ma nay khong tin cay
        sym_disp = f"{sym}(!)" if sym in untrusted else sym
        score = f"{item['score']}/7"
        conds = item["conditions"]
        c1 = "1" if conds["c1_close_tren_sma150_200"] else "0"
        c2 = "1" if conds["c2_sma150_tren_sma200"] else "0"
        c3 = "1" if conds["c3_sma200_di_len"] else "0"
        c4 = "1" if conds["c4_sma50_tren_sma150_200"] else "0"
        c5 = "1" if conds["c5_close_tren_sma50"] else "0"
        c6 = "1" if conds["c6_cach_day_252_nen"] else "0"
        c7 = "1" if conds["c7_gan_dinh_252_nen"] else "0"

        pct_lo_str = f"{item['pct_above_low']:+.1f}%" if item["pct_above_low"] is not None else "–"
        pct_hi_str = f"{item['pct_below_high']:.1f}%" if item["pct_below_high"] is not None else "–"

        r_val = rs_ranks.get(sym)
        if r_val is not None:
            r_str = f"{r_val}/99"
            rs_pass = "ĐẠT" if r_val >= 70 else "K.Đạt"
        else:
            r_str = "–"
            rs_pass = "–"

        p_str = f"{item['close']:,.0f}" if item["close"] is not None else "–"

        row = (
            f"{sym_disp:<6} | {score:<5} | {c1:<2} | {c2:<2} | {c3:<2} | {c4:<2} | "
            f"{c5:<2} | {c6:<2} | {c7:<2} | {pct_lo_str:>11} | {pct_hi_str:>12} | "
            f"{r_str:>8} | {rs_pass:<7} | {p_str:>9}"
        )
        lines.append(row)

    lines.append("-" * len(header))
    lines.append(
        "\n* Chú thích các cột tiêu chí SEPA:\n"
        "  c1: Close > MA150 & MA200 | c2: MA150 > MA200 | c3: MA200 dốc lên (21 phiên)\n"
        "  c4: MA50 > MA150 & MA200  | c5: Close > MA50  | c6: Cách đáy 252 nến ≥ +30% | c7: Cách đỉnh 252 nến ≤ 25%\n"
        "  RS_rank: Phân vị thực nghiệm (1-99) tính trên vũ trụ các mã có ít nhất 253 nến sạch.\n"
        "  Điểm SEPA tổng là n/7 theo đúng bảng điểm kỹ thuật."
    )
    return "\n".join(lines)


def load_universe_and_bars(
    dsn: str,
    as_of: date | None = None,
    specific_symbol: str | None = None,
) -> tuple[dict[str, list[Bar]], list[tuple[str, str]], date]:
    """Tải dữ liệu từ bars_daily kết hợp symbol_universe."""
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        # Xác định ngày phiên mới nhất nếu as_of là None
        if as_of is None:
            cur.execute("SELECT max(ts) FROM bars_daily")
            max_ts = cur.fetchone()[0]
            if max_ts is None:
                raise RuntimeError("Không có dữ liệu trong bars_daily")
            # Quy đổi sang giờ VN
            dummy_bar = Bar("DUMMY", max_ts, 1, 1, 1, 1, 1)
            as_of = bar_date(dummy_bar)

        # Lấy danh sách mã hoạt động từ symbol_universe
        cur.execute("SELECT symbol, is_active FROM symbol_universe")
        universe_status = {r[0]: bool(r[1]) for r in cur.fetchall()}
        active_symbols = [s for s, act in universe_status.items() if act]

        # Truy vấn thanh nến
        if specific_symbol:
            cur.execute(
                """
                SELECT symbol, ts, open, high, low, close, volume
                FROM bars_daily
                WHERE symbol = %s
                ORDER BY ts ASC
                """,
                (specific_symbol,),
            )
        else:
            cur.execute(
                """
                SELECT symbol, ts, open, high, low, close, volume
                FROM bars_daily
                WHERE symbol = ANY(%s)
                ORDER BY symbol, ts ASC
                """,
                (active_symbols,),
            )
        rows = cur.fetchall()

    bars_by_symbol: dict[str, list[Bar]] = {}
    for r in rows:
        sym = r[0]
        if sym not in bars_by_symbol:
            bars_by_symbol[sym] = []
        bars_by_symbol[sym].append(
            Bar(
                symbol=sym,
                ts=r[1],
                open=float(r[2]),
                high=float(r[3]),
                low=float(r[4]),
                close=float(r[5]),
                volume=int(r[6]),
            )
        )

    # Phân loại mã đủ điều kiện / bị loại
    ineligible_info: list[tuple[str, str]] = []
    filtered_bars: dict[str, list[Bar]] = {}

    for sym, raw_bars in bars_by_symbol.items():
        is_act = universe_status.get(sym, False)
        if not is_act:
            ineligible_info.append((sym, "is_active = false trong symbol_universe"))
            continue

        # Lọc đến ngày as_of
        b_up_to = [b for b in raw_bars if bar_date(b) <= as_of]
        cleaned, _ = clean_bars(b_up_to)

        if not cleaned:
            ineligible_info.append((sym, "Không có nến nào hợp lệ (toàn bộ nến bẩn)"))
            continue

        if len(cleaned) < TREND_MIN_BARS:
            ineligible_info.append(
                (sym, f"Thiếu lịch sử ({len(cleaned)} < {TREND_MIN_BARS} nến sạch)")
            )
            continue

        filtered_bars[sym] = cleaned

    return filtered_bars, ineligible_info, as_of


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bảng điểm SEPA và RS Rating dạng hiển thị mô tả trạng thái kỹ thuật."
    )
    parser.add_argument("--symbol", type=str, default=None, help="Mã cổ phiếu cần xem chi tiết (VD: BFC)")
    parser.add_argument("--as-of", type=str, default=None, help="Ngày đánh giá YYYY-MM-DD (mặc định: phiên mới nhất)")
    parser.add_argument("--output", type=str, default=None, help="Đường dẫn file ghi kết quả")
    args = parser.parse_args()

    as_of_date = date.fromisoformat(args.as_of) if args.as_of else None
    dsn = resolve_dsn()

    print("Đang tải dữ liệu từ database...")
    bars_by_symbol, ineligible_info, as_of_date = load_universe_and_bars(
        dsn, as_of=as_of_date, specific_symbol=args.symbol
    )

    if args.symbol:
        sym = args.symbol.upper()
        if sym not in bars_by_symbol:
            # Kiểm tra xem mã bị loại vì lý do gì
            reason = "Không tìm thấy dữ liệu"
            for s, r in ineligible_info:
                if s == sym:
                    reason = r
                    break
            print(f"LỖI: Mã {sym} không đủ điều kiện: {reason}")
            return 1

        # Cần tải toàn bộ vũ trụ để tính RS_rank chuẩn xác cho mã này
        all_bars, _, _ = load_universe_and_bars(dsn, as_of=as_of_date, specific_symbol=None)
        rs_raws: dict[str, float] = {}
        for s, b_list in all_bars.items():
            closes = [b.close for b in b_list]
            r_raw = calculate_rs_raw(closes)
            if r_raw is not None:
                rs_raws[s] = r_raw

        rs_ranks = calculate_rs_ranks(rs_raws)
        eval_res = evaluate_sepa_single(bars_by_symbol[sym], as_of=as_of_date)
        report = format_single_symbol_report(
            eval_res,
            rs_rank=rs_ranks.get(sym),
            rs_universe_size=len(rs_raws),
        )
        print(report)

        if args.output:
            out_p = Path(args.output)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(report, encoding="utf-8")
            print(f"\nĐã ghi kết quả ra file: {out_p}")
        return 0

    # Chạy cho toàn bộ vũ trụ
    eval_results: list[dict[str, Any]] = []
    rs_raws_all: dict[str, float] = {}

    for sym, b_list in bars_by_symbol.items():
        res = evaluate_sepa_single(b_list, as_of=as_of_date)
        eval_results.append(res)
        if res["rs_raw"] is not None:
            rs_raws_all[sym] = res["rs_raw"]

    rs_ranks_all = calculate_rs_ranks(rs_raws_all)
    report_all = format_multi_symbol_report(
        eval_results,
        rs_ranks=rs_ranks_all,
        rs_universe_size=len(rs_raws_all),
        ineligible_info=ineligible_info,
        as_of=as_of_date,
    )
    print(report_all)

    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(report_all, encoding="utf-8")
        print(f"\nĐã ghi kết quả ra file: {out_p}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
