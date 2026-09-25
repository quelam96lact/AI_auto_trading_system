"""Công cụ nghiệm thu file sổ lệnh VN30F (Brief 92 Task 2).

Chức năng:
1. Đọc và phân tích file dữ liệu sổ lệnh .jsonl.gz (chế độ chỉ đọc, không ghi DB, không sửa file).
2. Kiểm tra 3 tiêu chí đạt/không đạt:
   - Tiêu chí 1: Không có dòng lỗi parse JSON.
   - Tiêu chí 2: Độ phủ phiên khớp lệnh liên tục >= 90% (chia thành các ô 5 phút, bỏ qua nghỉ trưa).
   - Tiêu chí 3: Mã ghi được là front-month thực tế của ngày đó (theo SSI).
     Nếu không gọi được SSI thì thông báo rõ là không kiểm được tiêu chí này và không coi là đạt.
3. In báo cáo chi tiết và trả exit code 0 nếu ĐẠT, exit code khác 0 nếu KHÔNG ĐẠT.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import io
import json
import os
import pathlib
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

# Force UTF-8 stdout/stderr on Windows to avoid UnicodeEncodeError
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

# Ensure repo root is in sys.path
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.record_vn30f_orderbook import (
    AFTERNOON_END,
    AFTERNOON_START,
    MORNING_END,
    MORNING_START,
    classify_message,
    resolve_front_month_symbol,
)
from trading.calendar_vn import TZ


@dataclass(frozen=True)
class OrderbookMetrics:
    symbol: str | None
    target_date: date | None
    counts: dict[str, int]
    unparseable_lines: int
    first_recv_ts: datetime | None
    last_recv_ts: datetime | None
    total_slots: int
    covered_slots: int
    coverage_ratio: float
    empty_slots: list[str]


@dataclass(frozen=True)
class VerificationResult:
    is_valid: bool
    reasons: list[str]
    criteria_status: dict[str, bool | None]
    expected_front_month: str | None
    front_month_error: str | None


def generate_continuous_session_slots(
    d: date,
    slot_minutes: int = 5,
) -> list[tuple[datetime, datetime, str]]:
    """Tạo danh sách các ô 5 phút trong giờ khớp lệnh liên tục của ngày d.

    - Phiên sáng: 09:00 -> 11:30 (150 phút = 30 ô)
    - Nghỉ trưa: 11:30 -> 13:00 (không tính vào mẫu số)
    - Phiên chiều: 13:00 -> 14:45 (105 phút = 21 ô)
    Tổng cộng: 51 ô.
    """
    slots: list[tuple[datetime, datetime, str]] = []
    step = timedelta(minutes=slot_minutes)

    # 1. Phiên sáng
    cur = datetime.combine(d, MORNING_START, tzinfo=TZ)
    m_end = datetime.combine(d, MORNING_END, tzinfo=TZ)
    while cur < m_end:
        nxt = min(cur + step, m_end)
        label = f"{cur.strftime('%H:%M')}-{nxt.strftime('%H:%M')}"
        slots.append((cur, nxt, label))
        cur = nxt

    # 2. Phiên chiều
    cur = datetime.combine(d, AFTERNOON_START, tzinfo=TZ)
    a_end = datetime.combine(d, AFTERNOON_END, tzinfo=TZ)
    while cur < a_end:
        nxt = min(cur + step, a_end)
        label = f"{cur.strftime('%H:%M')}-{nxt.strftime('%H:%M')}"
        slots.append((cur, nxt, label))
        cur = nxt

    return slots


def compute_slot_coverage(
    timestamps: list[datetime],
    target_date: date,
    slot_minutes: int = 5,
) -> tuple[int, int, float, list[str]]:
    """Tính độ phủ các ô thời gian 5 phút trong giờ giao dịch khớp lệnh liên tục.

    Trả về: (total_slots, covered_slots, coverage_ratio, empty_slots)
    - total_slots: Luôn là 51 ô (mẫu số không bao gồm nghỉ trưa).
    - covered_slots: Số ô có ít nhất 1 tin.
    - coverage_ratio: covered_slots / total_slots (từ 0.0 đến 1.0).
    - empty_slots: Danh sách nhãn các ô không có tin nào.
    """
    slots = generate_continuous_session_slots(target_date, slot_minutes=slot_minutes)
    total_slots = len(slots)
    if total_slots == 0:
        return 0, 0, 0.0, []

    # Đếm số tin trong từng ô
    slot_counts = [0] * total_slots

    for ts in timestamps:
        ts_vn = ts.astimezone(TZ)
        if ts_vn.date() != target_date:
            continue

        # Tìm ô tương ứng
        t_val = ts_vn.time()
        # Phiên sáng: 09:00:00 -> 11:30:00
        if MORNING_START <= t_val <= MORNING_END:
            min_offset = (ts_vn.hour - 9) * 60 + ts_vn.minute + ts_vn.second / 60.0
            idx = int(min_offset // slot_minutes)
            if idx >= 30:
                idx = 29  # Tin lúc 11:30:00 tính vào ô cuối phiên sáng
            slot_counts[idx] += 1
        # Phiên chiều: 13:00:00 -> 14:45:00
        elif AFTERNOON_START <= t_val <= AFTERNOON_END:
            min_offset = (ts_vn.hour - 13) * 60 + ts_vn.minute + ts_vn.second / 60.0
            idx = 30 + int(min_offset // slot_minutes)
            if idx >= total_slots:
                idx = total_slots - 1  # Tin lúc 14:45:00 tính vào ô cuối phiên chiều
            slot_counts[idx] += 1

    covered_slots = sum(1 for c in slot_counts if c > 0)
    empty_slots = [slots[i][2] for i, c in enumerate(slot_counts) if c == 0]
    coverage_ratio = covered_slots / total_slots

    return total_slots, covered_slots, coverage_ratio, empty_slots


def scan_orderbook_stream(lines: Iterable[str]) -> OrderbookMetrics:
    """Hàm thuần đọc và trích xuất các chỉ số từ luồng dòng JSON text."""
    counts = {"QUOTE": 0, "TRADE": 0, "OTHER": 0}
    unparseable_lines = 0
    symbols: dict[str, int] = {}
    timestamps: list[datetime] = []

    for line in lines:
        line_s = line.strip()
        if not line_s:
            continue

        try:
            msg = json.loads(line_s)
        except Exception:
            unparseable_lines += 1
            continue

        if not isinstance(msg, dict):
            unparseable_lines += 1
            continue

        cat = classify_message(msg)
        counts[cat] = counts.get(cat, 0) + 1

        sym = msg.get("symbol")
        if sym:
            symbols[sym] = symbols.get(sym, 0) + 1

        r_ts = msg.get("recv_ts")
        if r_ts:
            try:
                dt = datetime.fromisoformat(r_ts)
                timestamps.append(dt)
            except Exception:
                pass

    # Xác định mã hợp đồng chủ đạo
    main_symbol = max(symbols.keys(), key=lambda k: symbols[k]) if symbols else None

    # Mốc thời gian
    first_recv_ts = min(timestamps) if timestamps else None
    last_recv_ts = max(timestamps) if timestamps else None
    target_date = first_recv_ts.astimezone(TZ).date() if first_recv_ts else None

    # Tính độ phủ phiên
    if target_date:
        total_slots, covered_slots, coverage_ratio, empty_slots = compute_slot_coverage(
            timestamps, target_date
        )
    else:
        # File rỗng hoặc không có timestamp hợp lệ
        total_slots = 51
        covered_slots = 0
        coverage_ratio = 0.0
        slots_def = generate_continuous_session_slots(date(2026, 1, 1))
        empty_slots = [s[2] for s in slots_def]

    return OrderbookMetrics(
        symbol=main_symbol,
        target_date=target_date,
        counts=counts,
        unparseable_lines=unparseable_lines,
        first_recv_ts=first_recv_ts,
        last_recv_ts=last_recv_ts,
        total_slots=total_slots,
        covered_slots=covered_slots,
        coverage_ratio=coverage_ratio,
        empty_slots=empty_slots,
    )


def evaluate_orderbook_verification(
    metrics: OrderbookMetrics,
    expected_symbol: str | None,
    front_month_error: str | None = None,
    min_coverage: float = 0.90,
) -> VerificationResult:
    """Hàm thuần đánh giá 3 tiêu chí nghiệm thu file sổ lệnh.

    Trả về exit code khác 0 (is_valid = False) nếu vi phạm bất kỳ:
    1. Có dòng không parse được (unparseable_lines > 0).
    2. Độ phủ phiên dưới min_coverage (mặc định 90%).
    3. Mã ghi được không phải front-month của ngày đó (hoặc không gọi được SSI).
    """
    reasons: list[str] = []
    criteria_status: dict[str, bool | None] = {}

    # Tiêu chí 1: Không có dòng lỗi parse
    if metrics.unparseable_lines == 0:
        criteria_status["parseable"] = True
    else:
        criteria_status["parseable"] = False
        reasons.append(f"Có {metrics.unparseable_lines} dòng dữ liệu không parse được JSON.")

    # Tiêu chí 2: Độ phủ phiên >= min_coverage
    if metrics.coverage_ratio >= min_coverage:
        criteria_status["coverage"] = True
    else:
        criteria_status["coverage"] = False
        cov_pct = metrics.coverage_ratio * 100.0
        reasons.append(
            f"Độ phủ phiên chỉ đạt {cov_pct:.1f}% ({metrics.covered_slots}/{metrics.total_slots} ô), "
            f"thấp hơn ngưỡng tối thiểu {min_coverage * 100.0:.0f}%."
        )

    # Tiêu chí 3: Mã là front-month thực tế
    if front_month_error:
        criteria_status["front_month"] = False
        reasons.append(
            f"Không gọi được SSI: không thể kiểm chứng mã front-month ({front_month_error})."
        )
    elif not expected_symbol:
        criteria_status["front_month"] = False
        reasons.append("Không xác định được mã hợp đồng front-month kỳ vọng.")
    elif metrics.symbol != expected_symbol:
        criteria_status["front_month"] = False
        reasons.append(
            f"Mã ghi được ({metrics.symbol}) không phải front-month ({expected_symbol}) của ngày {metrics.target_date}."
        )
    else:
        criteria_status["front_month"] = True

    is_valid = all(v is True for v in criteria_status.values())
    return VerificationResult(
        is_valid=is_valid,
        reasons=reasons,
        criteria_status=criteria_status,
        expected_front_month=expected_symbol,
        front_month_error=front_month_error,
    )


def format_verification_report(
    filepath: Path | str,
    metrics: OrderbookMetrics,
    result: VerificationResult,
    min_coverage: float = 0.90,
) -> str:
    """Tạo báo cáo nghiệm thu dạng văn bản chuẩn."""
    lines: list[str] = []
    lines.append("=" * 68)
    lines.append("=== BÁO CÁO NGHIỆM THU FILE SỔ LỆNH VN30F (BRIEF 92) ===")
    lines.append("=" * 68)
    lines.append(f"File kiểm tra: {filepath}")
    lines.append(f"- Mã hợp đồng đọc được: {metrics.symbol or '(không tìm thấy)'}")
    lines.append(f"- Ngày giao dịch: {metrics.target_date or '(không xác định)'}")

    total_msgs = sum(metrics.counts.values())
    lines.append(
        f"- Tổng số tin: {total_msgs:,} "
        f"(QUOTE: {metrics.counts['QUOTE']:,}, TRADE: {metrics.counts['TRADE']:,}, KHÁC: {metrics.counts['OTHER']:,})"
    )
    lines.append(f"- Số dòng không parse được: {metrics.unparseable_lines}")

    first_s = metrics.first_recv_ts.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S%z") if metrics.first_recv_ts else "N/A"
    last_s = metrics.last_recv_ts.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S%z") if metrics.last_recv_ts else "N/A"
    lines.append(f"- Mốc tin đầu tiên (recv_ts): {first_s}")
    lines.append(f"- Mốc tin cuối cùng (recv_ts): {last_s}")

    cov_pct = metrics.coverage_ratio * 100.0
    lines.append(
        f"- Độ phủ phiên khớp lệnh liên tục: {metrics.covered_slots}/{metrics.total_slots} ô ({cov_pct:.1f}%)"
    )

    if metrics.empty_slots:
        lines.append(f"- Danh sách {len(metrics.empty_slots)} ô trống không có tin:")
        for s in metrics.empty_slots:
            lines.append(f"  * Ô {s}")
    else:
        lines.append("- Toàn bộ các ô 5 phút trong phiên đều có dữ liệu.")

    lines.append("-" * 68)
    lines.append("ĐÁNH GIÁ 3 TIÊU CHÍ NGHIỆM THU:")

    # Tiêu chí 1
    c1_ok = result.criteria_status.get("parseable")
    c1_mark = "[x]" if c1_ok else "[ ]"
    lines.append(
        f"  {c1_mark} Tiêu chí 1: Không có dòng lỗi parse "
        f"({metrics.unparseable_lines} dòng lỗi) -> {'ĐẠT' if c1_ok else 'KHÔNG ĐẠT'}"
    )

    # Tiêu chí 2
    c2_ok = result.criteria_status.get("coverage")
    c2_mark = "[x]" if c2_ok else "[ ]"
    lines.append(
        f"  {c2_mark} Tiêu chí 2: Độ phủ phiên >= {min_coverage * 100.0:.0f}% "
        f"(Thực tế: {cov_pct:.1f}%, thiếu {len(metrics.empty_slots)} ô) -> {'ĐẠT' if c2_ok else 'KHÔNG ĐẠT'}"
    )

    # Tiêu chí 3
    c3_ok = result.criteria_status.get("front_month")
    c3_mark = "[x]" if c3_ok else "[ ]"
    if result.front_month_error:
        c3_desc = f"KHÔNG ĐẠT (Không gọi được SSI: {result.front_month_error})"
    elif c3_ok:
        c3_desc = f"ĐẠT (Kỳ vọng: {result.expected_front_month}, Thực tế: {metrics.symbol})"
    else:
        c3_desc = f"KHÔNG ĐẠT (Kỳ vọng: {result.expected_front_month}, Thực tế: {metrics.symbol})"
    lines.append(f"  {c3_mark} Tiêu chí 3: Mã hợp đồng là front-month -> {c3_desc}")

    lines.append("-" * 68)
    verdict = "ĐẠT (File đạt chuẩn chất lượng)" if result.is_valid else "KHÔNG ĐẠT (File không đủ tiêu chuẩn)"
    lines.append(f"KẾT LUẬN CHUNG: {verdict}")
    if result.reasons:
        lines.append("Lý do không đạt:")
        for r in result.reasons:
            lines.append(f"  - {r}")
    lines.append("=" * 68)
    return "\n".join(lines)


def _load_dotenv(env_path: str = ".env") -> None:
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


async def verify_orderbook_file(
    filepath: Path | str,
    ssi_fetcher: Any = None,
    expected_symbol: str | None = None,
    min_coverage: float = 0.90,
) -> tuple[OrderbookMetrics, VerificationResult]:
    """Hàm chính thực hiện nghiệm thu file dữ liệu sổ lệnh."""
    p = Path(filepath)
    if not p.exists():
        raise FileNotFoundError(f"File không tồn tại: {filepath}")

    # Đọc luồng gzip chế độ chỉ đọc
    with gzip.open(p, mode="rt", encoding="utf-8") as f:
        metrics = scan_orderbook_stream(f)

    # Xác định mã front-month kỳ vọng
    front_month_error: str | None = None
    expected_front_month = expected_symbol

    if expected_front_month is None and metrics.target_date is not None:
        try:
            # Nếu không có ssi_fetcher được truyền, thử kết nối SSI nếu có môi trường
            fetcher = ssi_fetcher
            if fetcher is None:
                async def _default_ssi_fetcher():
                    _load_dotenv()
                    from ssi_sdk import AsyncData

                    from scripts.measure_derivative_contract_volume import (
                        discover_derivative_contracts,
                    )
                    from trading.collector.ssi_auth import ensure_authenticated
                    from trading.config import load_config
                    from trading.storage.db import Storage

                    app_cfg = load_config("config/config.yaml")
                    db_dsn = app_cfg.db_dsn.replace("@localhost:", "@127.0.0.1:")
                    storage = Storage(db_dsn)
                    auth_ssi = await ensure_authenticated(app_cfg, storage)
                    try:
                        data_ssi = AsyncData(auth_ssi)
                        return await discover_derivative_contracts(data_ssi)
                    finally:
                        try:
                            await auth_ssi.close()
                        except Exception:
                            pass

                fetcher = _default_ssi_fetcher

            # Tiêu chí 3 yêu cầu: Không gọi được SSI thì nói rõ là không kiểm được tiêu chí này, đừng coi là đạt
            expected_front_month = await resolve_front_month_symbol(
                metrics.target_date, ssi_fetcher=fetcher, fallback_generator=lambda d: []
            )
        except Exception as e:
            front_month_error = str(e)
            expected_front_month = None

    result = evaluate_orderbook_verification(
        metrics,
        expected_symbol=expected_front_month,
        front_month_error=front_month_error,
        min_coverage=min_coverage,
    )

    report_text = format_verification_report(filepath, metrics, result, min_coverage=min_coverage)
    print(report_text)

    return metrics, result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Công cụ nghiệm thu file sổ lệnh VN30F (Brief 92 Task 2)"
    )
    parser.add_argument("file", help="Đường dẫn file .jsonl.gz cần nghiệm thu")
    parser.add_argument(
        "--expected-symbol",
        default=None,
        help="Ghi đè mã front-month kỳ vọng (mặc định: tự truy vấn SSI)",
    )
    parser.add_argument(
        "--min-coverage",
        type=float,
        default=0.90,
        help="Ngưỡng độ phủ tối thiểu (mặc định: 0.90)",
    )
    args = parser.parse_args()

    try:
        _metrics, result = asyncio.run(
            verify_orderbook_file(
                args.file,
                expected_symbol=args.expected_symbol,
                min_coverage=args.min_coverage,
            )
        )
        if not result.is_valid:
            sys.exit(1)
        sys.exit(0)
    except Exception as e:
        print(f"\n[LỖI] Nghiệm thu thất bại: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
