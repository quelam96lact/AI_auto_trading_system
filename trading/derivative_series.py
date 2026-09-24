"""Phân hệ xử lý chuỗi liên tục (continuous series) cho phái sinh VN (Brief 83).

Cung cấp các hàm thuần:
1. build_roll_schedule: Xây dựng lịch roll từ metadata hợp đồng theo quy tắc
   chuyển giao tại cuối phiên ngày giao dịch cuối cùng (lastTradingDate).
2. compute_roll_gaps: Tính hiệu số (gap) tại điểm giao thoa giữa 2 hợp đồng và
   tính tích luỹ cộng dồn cho phương pháp back-adjust hiệu số (Panama method).
3. stitch_continuous: Ghép và chuẩn hoá dữ liệu nến thành chuỗi liên tục
   (VN30F1M_CONT) bảo toàn nguyên vẹn biến động điểm giá giữa các nến liền kề.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from trading.calendar_vn import TZ
from trading.models import Bar

DEFAULT_CONTINUOUS_SYMBOL = "VN30F1M_CONT"


@dataclass(frozen=True)
class ContractMetadata:
    """Metadata tối thiểu cần thiết để xác định lịch roll hợp đồng."""

    symbol: str
    last_trading_date: date
    first_trading_date: date | None = None
    name: str = ""


@dataclass(frozen=True)
class RollGap:
    """Thông tin chi tiết về chênh lệch giá tại mốc roll giữa 2 hợp đồng."""

    roll_date: date
    from_symbol: str
    to_symbol: str
    overlap_ts: datetime
    from_close: float
    to_close: float
    gap: float  # to_close - from_close
    cumulative_adjustment: float


def _parse_date(d: Any) -> date:
    """Hỗ trợ parse date từ date object, datetime object hoặc string 'YYYY/MM/DD'/'YYYY-MM-DD'."""
    if isinstance(d, datetime):
        return d.astimezone(TZ).date() if d.tzinfo else d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        clean = d.replace("-", "/").strip().split()[0]
        parts = [int(p) for p in clean.split("/")]
        return date(parts[0], parts[1], parts[2])
    raise ValueError(f"Không thể chuyển đổi kiểu dữ liệu ngày: {d!r}")


def _extract_contract_fields(c: Any) -> tuple[str, date, date | None]:
    """Trích xuất symbol, last_trading_date, first_trading_date từ nhiều dạng object/dict."""
    if isinstance(c, dict):
        sym = c.get("symbol") or c.get("Symbol") or ""
        last_d = c.get("last_trading_date") or c.get("lastTradingDate")
        first_d = c.get("first_trading_date") or c.get("firstTradingDate")
    else:
        sym = getattr(c, "symbol", "")
        last_d = getattr(c, "last_trading_date", None)
        if last_d is None:
            last_d = getattr(c, "lastTradingDate", None)
        first_d = getattr(c, "first_trading_date", None)
        if first_d is None:
            first_d = getattr(c, "firstTradingDate", None)

    if not sym or last_d is None:
        raise ValueError(f"Dữ liệu hợp đồng thiếu symbol hoặc last_trading_date: {c!r}")

    last_date = _parse_date(last_d)
    first_date = _parse_date(first_d) if first_d else None
    return sym, last_date, first_date


def build_roll_schedule(contracts: list[Any]) -> list[tuple[str, date, date]]:
    """Xây dựng lịch roll từ metadata hợp đồng.

    Quy tắc roll:
    - Chuyển sang hợp đồng tháng kế tiếp vào cuối phiên của ngày giao dịch
      cuối cùng của hợp đồng đang giữ (lastTradingDate).
    - Hợp đồng mới bắt đầu hiệu lực từ ngày hôm sau (lastTradingDate + 1 ngày).

    Args:
        contracts: Danh sách hợp đồng (ContractMetadata, ContractInfo, hoặc dict).

    Returns:
        Danh sách các tuple: (symbol, start_date, end_date) theo thứ tự thời gian.
    """
    if not contracts:
        return []

    parsed = [_extract_contract_fields(c) for c in contracts]
    # Sắp xếp tăng dần theo last_trading_date
    parsed.sort(key=lambda x: x[1])

    schedule: list[tuple[str, date, date]] = []
    for i, (sym, last_d, first_d) in enumerate(parsed):
        if i == 0:
            start_d = first_d if first_d else last_d - timedelta(days=30)
        else:
            # Bắt đầu từ ngày sau khi hợp đồng trước hết hạn
            start_d = parsed[i - 1][1] + timedelta(days=1)
        schedule.append((sym, start_d, last_d))

    return schedule


def compute_roll_gaps(
    bars_by_symbol: dict[str, list[Bar]],
    roll_schedule: list[tuple[str, date, date]],
) -> list[RollGap]:
    """Tính toán hiệu số (gap) tại từng mốc roll và lượng cộng dồn luỹ kế.

    Phương pháp Panama (Back-adjustment bằng hiệu số):
    - Tại mỗi mốc roll từ C_k sang C_{k+1}:
      gap_k = C_{k+1}.close - C_k.close tại nến cuối cùng cả hai đều có trên
      hoặc trước mốc roll (end_date của C_k).
    - Lượng cộng dồn:
      Hợp đồng mới nhất (cuối cùng): adjustment = 0.
      Hợp đồng C_k: adjustment_k = tổng(gap_j từ j=k đến N-2).

    Raises:
        ValueError: Nếu không tìm thấy nến trùng khớp giữa hai hợp đồng tại mốc roll.
    """
    if len(roll_schedule) <= 1:
        return []

    raw_gaps: list[dict[str, Any]] = []

    for k in range(len(roll_schedule) - 1):
        from_sym = roll_schedule[k][0]
        to_sym = roll_schedule[k + 1][0]
        roll_date = roll_schedule[k][2]  # lastTradingDate của hợp đồng cũ

        bars_from = bars_by_symbol.get(from_sym, [])
        bars_to = bars_by_symbol.get(to_sym, [])

        # Lập dict tra cứu nến theo timestamp
        from_by_ts = {
            b.ts: b
            for b in bars_from
            if (b.ts.astimezone(TZ).date() if b.ts.tzinfo else b.ts.date()) <= roll_date
            and not (b.open == 0 and b.volume == 0 and b.close == 0)
        }
        to_by_ts = {
            b.ts: b
            for b in bars_to
            if (b.ts.astimezone(TZ).date() if b.ts.tzinfo else b.ts.date()) <= roll_date
            and not (b.open == 0 and b.volume == 0 and b.close == 0)
        }

        # Tìm các timestamp trùng khớp
        common_ts = set(from_by_ts.keys()) & set(to_by_ts.keys())
        if not common_ts:
            raise ValueError(
                f"Không tìm thấy nến chồng lấn (overlapping bars) giữa {from_sym} và {to_sym} "
                f"tại hoặc trước mốc roll {roll_date}"
            )

        # Lấy nến trùng khớp muộn nhất (gần mốc roll nhất)
        latest_overlap_ts = max(common_ts)
        bar_from = from_by_ts[latest_overlap_ts]
        bar_to = to_by_ts[latest_overlap_ts]

        gap = round(bar_to.close - bar_from.close, 4)
        raw_gaps.append(
            {
                "roll_date": roll_date,
                "from_symbol": from_sym,
                "to_symbol": to_sym,
                "overlap_ts": latest_overlap_ts,
                "from_close": bar_from.close,
                "to_close": bar_to.close,
                "gap": gap,
            }
        )

    # Tính lượng cộng dồn luỹ kế (cumulative adjustment)
    # cum_adjustments[k] là tổng gap từ transition k đến hết
    num_gaps = len(raw_gaps)
    result: list[RollGap] = []
    running_cum = 0.0
    cum_list: list[float] = [0.0] * num_gaps
    for i in reversed(range(num_gaps)):
        running_cum = round(running_cum + raw_gaps[i]["gap"], 4)
        cum_list[i] = running_cum

    for i in range(num_gaps):
        rg = raw_gaps[i]
        result.append(
            RollGap(
                roll_date=rg["roll_date"],
                from_symbol=rg["from_symbol"],
                to_symbol=rg["to_symbol"],
                overlap_ts=rg["overlap_ts"],
                from_close=rg["from_close"],
                to_close=rg["to_close"],
                gap=rg["gap"],
                cumulative_adjustment=cum_list[i],
            )
        )

    return result


def stitch_continuous(
    bars_by_symbol: dict[str, list[Bar]],
    roll_schedule: list[tuple[str, date, date]],
    continuous_symbol: str = DEFAULT_CONTINUOUS_SYMBOL,
) -> list[Bar]:
    """Tạo chuỗi nến liên tục bằng phương pháp back-adjust hiệu số (Panama).

    Args:
        bars_by_symbol: Dict nến của từng hợp đồng {symbol: list[Bar]}.
        roll_schedule: Lịch roll [(symbol, start_date, end_date), ...].
        continuous_symbol: Mã symbol gán cho chuỗi kết quả (mặc định: VN30F1M_CONT).

    Returns:
        Danh sách Bar liên tục đã được điều chỉnh giá, sắp xếp theo thời gian tăng dần.
    """
    if not roll_schedule:
        return []

    # 1. Tính toán gaps và lượng cộng dồn luỹ kế
    roll_gaps = compute_roll_gaps(bars_by_symbol, roll_schedule)

    # cumulative_adj[sym] là lượng cộng dồn vào giá của hợp đồng sym
    cumulative_adj: dict[str, float] = {}
    for i, item in enumerate(roll_schedule):
        sym = item[0]
        if i == len(roll_schedule) - 1:
            # Hợp đồng mới nhất: không điều chỉnh (adjustment = 0)
            cumulative_adj[sym] = 0.0
        else:
            # Hợp đồng cũ thứ i: nhận lượng cộng dồn từ transition thứ i
            cumulative_adj[sym] = roll_gaps[i].cumulative_adjustment

    # 2. Trích xuất nến và áp dụng hiệu số back-adjust
    stitched: list[Bar] = []
    for sym, start_d, end_d in roll_schedule:
        adj = cumulative_adj[sym]
        bars = bars_by_symbol.get(sym, [])

        for b in bars:
            # Dọn nến hỏng (open=0, low=0) theo quy tắc cấu trúc thị trường
            cleaned_b = clean_bar(b)
            if cleaned_b is None:
                continue

            bar_date = cleaned_b.ts.astimezone(TZ).date() if cleaned_b.ts.tzinfo else cleaned_b.ts.date()
            if start_d <= bar_date <= end_d:
                stitched.append(
                    Bar(
                        symbol=continuous_symbol,
                        ts=cleaned_b.ts,
                        open=round(cleaned_b.open + adj, 4),
                        high=round(cleaned_b.high + adj, 4),
                        low=round(cleaned_b.low + adj, 4),
                        close=round(cleaned_b.close + adj, 4),
                        volume=cleaned_b.volume,
                        source=cleaned_b.source,
                    )
                )

    stitched.sort(key=lambda b: b.ts)
    return stitched


class BarCleanAction:
    """Các hành động xử lý nến có giá trị 0."""

    KEEP = "keep"
    FIX_ATC = "fix_atc"
    REPORT = "report"
    DELETE = "delete"


def classify_bar_for_cleaning(bar: Bar) -> str:
    """Phân loại nến có giá trị lỗi (open=0, low=0, high=0, hoặc close=0).

    Quy tắc cấu trúc thị trường (Brief 84 Task 2):
    - Nếu nến bình thường (toàn bộ OHLC > 0): KEEP.
    - Nếu nến có giá trị <= 0:
      - Nến 14:45 (phiên ATC - khớp tại một mức giá duy nhất):
        - Nếu high == close: FIX_ATC (sửa open = low = close).
        - Nếu high != close: REPORT (báo cáo riêng, không sửa).
      - Mọi nến khác (bao gồm 09:00 gộp nhiều mức giá): DELETE (xoá bỏ, không đoán giá).
    """
    if bar.open > 0 and bar.high > 0 and bar.low > 0 and bar.close > 0:
        return BarCleanAction.KEEP

    ts_vn = bar.ts.astimezone(TZ) if bar.ts.tzinfo else bar.ts
    is_atc = (ts_vn.hour == 14 and ts_vn.minute == 45)

    if is_atc:
        if bar.high == bar.close:
            return BarCleanAction.FIX_ATC
        return BarCleanAction.REPORT
    return BarCleanAction.DELETE


def clean_bar(bar: Bar) -> Bar | None:
    """Áp dụng quy tắc dọn nến: trả về Bar đã sửa, None (nếu xoá), hoặc Bar gốc."""
    action = classify_bar_for_cleaning(bar)
    if action == BarCleanAction.KEEP:
        return bar
    if action == BarCleanAction.FIX_ATC:
        return Bar(
            symbol=bar.symbol,
            ts=bar.ts,
            open=bar.close,
            high=bar.high,
            low=bar.close,
            close=bar.close,
            volume=bar.volume,
            source=bar.source,
        )
    if action == BarCleanAction.DELETE:
        return None
    # BarCleanAction.REPORT: giữ nguyên nến gốc để kiểm tra/báo cáo
    return bar
