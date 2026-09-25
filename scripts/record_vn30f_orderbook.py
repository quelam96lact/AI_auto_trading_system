"""Máy ghi dữ liệu sổ lệnh và dòng lệnh VN30F1M thời gian thực (Brief 87).

Chức năng:
1. Xác thực bằng trading.collector.ssi_auth.ensure_authenticated(cfg, storage)
   (đọc và cập nhật token trong bảng ssi_auth_state của DB - đồng nhất với collector).
2. Kết nối WebSocket qua ssi_sdk.AsyncStream(auth) và subscribe hợp đồng phái sinh.
3. Ghi nguyên văn mọi tin QUOTE / TRADE kèm timestamp nhận recv_ts vào:
   data/orderbook/<symbol>/<YYYY-MM-DD>.jsonl.gz.
4. Tự dừng khi tới mốc --until HH:MM (giờ VN) hoặc khi nhận tín hiệu dừng (Ctrl+C).
5. In báo cáo thống kê: số tin mỗi loại, dung lượng file, khoảng lặng dài nhất
   và danh sách các khoảng lặng > 10s trong giờ giao dịch (bỏ qua nghỉ trưa).
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import gzip
import io
import json
import os
import pathlib
import signal
import sys
from collections.abc import Callable
from datetime import date, datetime, timedelta
from datetime import time as dt_time
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

from scripts.measure_derivative_contract_volume import (
    PREFIX_VN30,
    ContractInfo,
    discover_derivative_contracts,
    filter_living_contracts,
    identify_front_month,
)
from trading.alerts import alert
from trading.calendar_vn import TZ, is_trading_day
from trading.collector.ssi_auth import ensure_authenticated
from trading.config import load_config
from trading.storage.db import Storage

# Các mốc giờ phiên giao dịch phái sinh Việt Nam.
#
# CỐ Ý ĐỊNH NGHĨA RIÊNG, KHÔNG dùng trading.calendar_vn.SESSIONS, dù hiện tại hai bộ
# trùng giá trị. Lý do: SESSIONS là phiên CỔ PHIẾU; phiên PHÁI SINH khác thật sự —
# nó có ATO từ 08:45 (cổ phiếu 09:00) và ATC 14:30-14:45 nằm trong khung dưới đây.
# Hai bộ phải được phép rẽ nhau khi HNX đổi giờ một sàn. Đừng gộp lại.
#
# HẠN CHẾ ĐÃ BIẾT: khung dưới bắt đầu 09:00 nên KHÔNG phủ phiên ATO 08:45-09:00.
# Máy ghi vẫn NHẬN và GHI tin ATO (nó chạy từ 08:40), nhưng phép đo độ phủ ở
# scripts/verify_orderbook_file.py không tính khoảng đó vào mẫu số — tức thiếu tin
# ATO sẽ không bị phát hiện. Chấp nhận được vì ATO không phải khớp lệnh liên tục.
MORNING_START = dt_time(9, 0, 0)
MORNING_END = dt_time(11, 30, 0)
AFTERNOON_START = dt_time(13, 0, 0)
AFTERNOON_END = dt_time(14, 45, 0)


def should_reconnect(
    is_connected: bool,
    current_time: dt_time,
    until_time: dt_time | None = None,
    consecutive_failures: int = 0,
    max_retries: int = 10,
) -> bool:
    """Hàm thuần (C1): Quyết định có nên thử kết nối lại hay không.

    Quy tắc:
    1. Kết nối đang sống (is_connected=True) -> KHÔNG kết nối lại (False).
    2. Đã vượt quá số lần thử tối đa (consecutive_failures >= max_retries) -> KHÔNG kết nối lại (False).
    3. Đã quá mốc --until (current_time >= until_time) -> KHÔNG kết nối lại (False), dừng sạch.
    4. Ngược lại -> kết nối lại (True).
    """
    if is_connected:
        return False
    if consecutive_failures >= max_retries:
        return False
    return not (until_time is not None and current_time >= until_time)

class EarlyStopError(RuntimeError):
    """Tiến trình máy ghi dừng sớm trước mốc --until trên ngày giao dịch."""


def should_alert_early_stop(
    actual_stop_time: dt_time | datetime,
    until_time: dt_time | None,
    is_trading_day: bool,
    tolerance_seconds: float = 0.0,
) -> bool:
    """Hàm thuần (Brief 94 Task 1): Quyết định có nên cảnh báo khi tiến trình dừng sớm hay không.

    Quy tắc:
    1. Nếu không phải ngày giao dịch (is_trading_day=False) -> KHÔNG báo (False).
    2. Nếu không có mốc until_time (chạy không giới hạn) -> KHÔNG báo (False).
    3. Nếu giờ dừng thực tế >= until_time - tolerance_seconds -> KHÔNG báo (False) (đúng giờ hoặc trễ hơn).
    4. Nếu dừng trước mốc until_time (vượt ngưỡng dung sai tolerance_seconds) -> BÁO CRITICAL (True).
    """
    if not is_trading_day or until_time is None:
        return False

    t_actual = (
        actual_stop_time.time()
        if isinstance(actual_stop_time, datetime)
        else actual_stop_time
    )

    actual_sec = t_actual.hour * 3600 + t_actual.minute * 60 + t_actual.second
    until_sec = until_time.hour * 3600 + until_time.minute * 60 + until_time.second

    return actual_sec < (until_sec - tolerance_seconds)
def compute_reconnect_backoff(
    failure_count: int,
    base_delay: float = 1.0,
    factor: float = 2.0,
    max_delay: float = 60.0,
) -> float:
    """Hàm thuần (C1): Tính khoảng nghỉ tăng dần theo số lần thất bại (exponential backoff)."""
    if failure_count <= 0:
        return 0.0
    delay = base_delay * (factor ** (failure_count - 1))
    return min(delay, max_delay)


def get_third_thursday(year: int, month: int) -> date:
    """Trả về ngày thứ Năm thứ 3 của tháng (ngày đáo hạn chuẩn của HĐTL chỉ số VN30)."""
    first_day = date(year, month, 1)
    days_to_first_thursday = (3 - first_day.weekday()) % 7
    first_thursday = first_day + timedelta(days=days_to_first_thursday)
    return first_thursday + timedelta(days=14)


def generate_vn30_candidate_contracts(as_of: date) -> list[ContractInfo]:
    """Sinh danh sách ContractInfo cho các hợp đồng VN30F xung quanh ngày as_of."""
    month_codes = {
        1: "1",
        2: "2",
        3: "3",
        4: "4",
        5: "5",
        6: "6",
        7: "7",
        8: "8",
        9: "9",
        10: "A",
        11: "B",
        12: "C",
    }
    year_codes = {2026: "G", 2027: "H", 2028: "I"}

    contracts: list[ContractInfo] = []
    for y in (as_of.year, as_of.year + 1):
        y_code = year_codes.get(y)
        if not y_code:
            continue
        for m, m_code in month_codes.items():
            sym = f"{PREFIX_VN30}{y_code}{m_code}000"
            exp_date = get_third_thursday(y, m)
            exp_str = exp_date.strftime("%Y/%m/%d")
            contracts.append(
                ContractInfo(
                    symbol=sym,
                    name=f"VN30F {m:02d}/{y}",
                    board="DERIVATIVES",
                    first_trading_date="",
                    last_trading_date=exp_str,
                )
            )
    return contracts


async def resolve_front_month_symbol(
    as_of: date,
    ssi_fetcher: Any = None,
    fallback_generator: Callable[[date], list[ContractInfo]] | None = None,
) -> str:
    """Xác định mã hợp đồng front-month VN30F còn sống tại ngày as_of (Brief 91 Task 1).

    Ưu tiên 1: Lấy danh sách hợp đồng từ SSI API (nguồn sự thật duy nhất cho ngày đáo hạn thực tế).
    Ưu tiên 2 (Đường lùi): Tự tính theo quy tắc thứ Năm thứ ba (get_third_thursday), phát cảnh báo WARN.
    Nếu cả hai đường đều thất bại: ném RuntimeError, dừng sạch không ghi file.
    """
    ssi_contracts: list[ContractInfo] | None = None
    ssi_error: Exception | str | None = None

    if ssi_fetcher is not None:
        try:
            res = ssi_fetcher()
            if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                ssi_contracts = await res
            else:
                ssi_contracts = res
        except Exception as e:
            ssi_error = e

    # 1. Thử giải quyết từ nguồn SSI (Ưu tiên số 1)
    if ssi_contracts:
        living = filter_living_contracts(ssi_contracts, as_of)
        front = identify_front_month(living, as_of)
        if front:
            return front.symbol
        if ssi_error is None:
            ssi_error = "SSI không trả về hợp đồng VN30F nào còn sống"
    elif ssi_fetcher is not None and ssi_error is None:
        ssi_error = "SSI trả về danh sách hợp đồng rỗng"

    # 2. Đường lùi: Tự tính theo công thức thứ Năm thứ 3
    generator = fallback_generator or generate_vn30_candidate_contracts
    fallback_contracts = generator(as_of)
    fallback_living = filter_living_contracts(fallback_contracts, as_of)
    fallback_front = identify_front_month(fallback_living, as_of)

    if not fallback_front:
        raise RuntimeError(
            f"Cả hai nguồn (SSI và tự tính) đều không tìm thấy hợp đồng VN30F còn sống tại ngày {as_of}. "
            f"Lỗi SSI: {ssi_error}"
        )

    # Khi rơi vào đường lùi: phát cảnh báo WARN nêu rõ lý do và mã chọn được
    err_msg = str(ssi_error) if ssi_error else "không có kết nối SSI"
    alert(
        "WARN",
        f"Lấy hợp đồng từ SSI thất bại ({err_msg}), chuyển sang đường lùi tự tính: chọn {fallback_front.symbol}",
        symbol=fallback_front.symbol,
        as_of=as_of.isoformat(),
        ssi_error=err_msg,
    )
    return fallback_front.symbol


def compute_continuous_session_minutes(
    current_dt: datetime,
    since_dt: datetime | None = None,
) -> float:
    """Tính số phút đã trôi qua trong giờ giao dịch khớp lệnh liên tục của ngày hôm nay.

    Khớp lệnh liên tục:
    - Phiên sáng: 09:00 -> 11:30 (tối đa 150 phút)
    - Nghỉ trưa: 11:30 -> 13:00 (không tính)
    - Phiên chiều: 13:00 -> 14:45 (tối đa 105 phút)

    Nếu truyền since_dt, chỉ tính thời gian giao dịch liên tục nằm trong khoảng [since_dt, current_dt].
    Nếu không truyền since_dt, tính từ đầu ngày giao dịch (09:00).
    """
    dt_vn = current_dt.astimezone(TZ)
    d = dt_vn.date()

    m_start = datetime.combine(d, MORNING_START, tzinfo=TZ)
    m_end = datetime.combine(d, MORNING_END, tzinfo=TZ)
    a_start = datetime.combine(d, AFTERNOON_START, tzinfo=TZ)
    a_end = datetime.combine(d, AFTERNOON_END, tzinfo=TZ)

    start_vn = since_dt.astimezone(TZ) if since_dt is not None else m_start

    minutes = 0.0
    # Phiên sáng: giao của [start_vn, dt_vn] và [m_start, m_end]
    period_m_start = max(start_vn, m_start)
    if dt_vn > period_m_start and period_m_start < m_end:
        period_m_end = min(dt_vn, m_end)
        minutes += max(0.0, (period_m_end - period_m_start).total_seconds() / 60.0)

    # Phiên chiều: giao của [start_vn, dt_vn] và [a_start, a_end]
    period_a_start = max(start_vn, a_start)
    if dt_vn > period_a_start and period_a_start < a_end:
        period_a_end = min(dt_vn, a_end)
        minutes += max(0.0, (period_a_end - period_a_start).total_seconds() / 60.0)

    return minutes


def check_quote_rate_alarm(
    quote_count: int,
    elapsed_minutes: float,
    min_minutes: float = 10.0,
    min_expected_quotes: int = 1000,
) -> bool:
    """Hàm thuần (Brief 91 Task 2): Kiểm tra lưu lượng tin QUOTE sau 10 phút đầu.

    Trả về True nếu cần phát cảnh báo (lưu lượng thấp bất thường, nghi ghi sai mã).
    Trả về False nếu:
    - Chưa đủ 10 phút (elapsed_minutes < min_minutes)
    - Hoặc số tin QUOTE đạt chuẩn (quote_count >= min_expected_quotes).
    """
    if elapsed_minutes < min_minutes:
        return False
    return quote_count < min_expected_quotes




def classify_message(raw_msg: dict[str, Any]) -> str:
    """Phân loại tin nhận từ WebSocket SSI thành QUOTE, TRADE hoặc OTHER."""
    if not isinstance(raw_msg, dict):
        return "OTHER"

    msg_type = str(raw_msg.get("type", ""))
    if "QUOTE" in msg_type or "bid_prices" in raw_msg or "ask_prices" in raw_msg:
        return "QUOTE"
    if "TRADE" in msg_type or (
        "side" in raw_msg and ("price" in raw_msg or "total_volume" in raw_msg)
    ):
        return "TRADE"

    return "OTHER"


def get_orderbook_filepath(
    base_dir: Path | str,
    symbol: str,
    dt: datetime,
) -> Path:
    """Trả về đường dẫn file lưu trữ: data/orderbook/<symbol>/<YYYY-MM-DD>.jsonl.gz.

    Tạo sẵn thư mục cha nếu chưa tồn tại.
    """
    base = Path(base_dir)
    date_str = dt.astimezone(TZ).strftime("%Y-%m-%d")
    target_dir = base / symbol
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{date_str}.jsonl.gz"


def compute_market_silence_seconds(
    t1: datetime,
    t2: datetime,
    disconnect_intervals: list[tuple[datetime, datetime]] | None = None,
) -> float:
    """Tính số giây khoảng lặng thị trường giữa hai mốc thời gian trong giờ giao dịch.

    Bỏ qua hoàn toàn khoảng nghỉ trưa (11:30:00 -> 13:00:00) và ngoài giờ phiên.
    Chỉ tính thời gian thực sự nằm trong phiên sáng [09:00, 11:30] và chiều [13:00, 14:45].
    Nếu có disconnect_intervals, loại bỏ thời gian máy ghi bị mất kết nối nằm trong khoảng [t1, t2].
    """
    t1_vn = t1.astimezone(TZ)
    t2_vn = t2.astimezone(TZ)
    if t2_vn <= t1_vn:
        return 0.0

    # Nếu khác ngày lịch, không tính vượt ngày
    if t1_vn.date() != t2_vn.date():
        return 0.0

    d = t1_vn.date()
    m_s = datetime.combine(d, MORNING_START, tzinfo=TZ)
    m_e = datetime.combine(d, MORNING_END, tzinfo=TZ)
    a_s = datetime.combine(d, AFTERNOON_START, tzinfo=TZ)
    a_e = datetime.combine(d, AFTERNOON_END, tzinfo=TZ)

    def _overlap_seconds(start1: datetime, end1: datetime, start2: datetime, end2: datetime) -> float:
        s = max(start1, start2)
        e = min(end1, end2)
        return max(0.0, (e - s).total_seconds()) if e > s else 0.0

    # Giao cắt với phiên sáng [09:00, 11:30] và chiều [13:00, 14:45]
    sec_m = _overlap_seconds(t1_vn, t2_vn, m_s, m_e)
    sec_a = _overlap_seconds(t1_vn, t2_vn, a_s, a_e)
    base_session_sec = sec_m + sec_a

    if not disconnect_intervals or base_session_sec <= 0.0:
        return base_session_sec

    # Trừ đi các quãng disconnect nằm giữa [t1, t2] và nằm trong giờ phiên
    disconnect_in_session_sec = 0.0

    for d_start, d_end in disconnect_intervals:
        d_start_vn = d_start.astimezone(TZ)
        d_end_vn = d_end.astimezone(TZ)
        if d_end_vn <= d_start_vn:
            continue
        s_overlap = max(t1_vn, d_start_vn)
        e_overlap = min(t2_vn, d_end_vn)
        if e_overlap > s_overlap:
            disconnect_in_session_sec += _overlap_seconds(s_overlap, e_overlap, m_s, m_e)
            disconnect_in_session_sec += _overlap_seconds(s_overlap, e_overlap, a_s, a_e)

    return max(0.0, base_session_sec - disconnect_in_session_sec)


def compute_total_downtime_seconds(
    disconnect_intervals: list[tuple[datetime, datetime]],
) -> tuple[float, list[tuple[datetime, datetime, float]]]:
    """Hàm thuần (C2): Tính tổng thời gian máy ghi mất kết nối và danh sách chi tiết từng quãng."""
    total_sec = 0.0
    detailed: list[tuple[datetime, datetime, float]] = []
    for d_start, d_end in disconnect_intervals:
        d_start_vn = d_start.astimezone(TZ)
        d_end_vn = d_end.astimezone(TZ)
        dur = max(0.0, (d_end_vn - d_start_vn).total_seconds())
        if dur > 0:
            total_sec += dur
            detailed.append((d_start_vn, d_end_vn, dur))
    return total_sec, detailed


def detect_silence_gaps(
    timestamps: list[datetime],
    min_gap_seconds: float = 10.0,
    disconnect_intervals: list[tuple[datetime, datetime]] | None = None,
) -> tuple[float, list[tuple[datetime, datetime, float]], int]:
    """Dò khoảng lặng giữa các tin liên tiếp trong giờ giao dịch (C2).

    Parameters:
        timestamps: Danh sách các mốc thời gian nhận tin (đã sắp xếp tăng dần).
        min_gap_seconds: Ngưỡng tối thiểu (giây) để ghi nhận khoảng lặng (mặc định 10.0s).
        disconnect_intervals: Danh sách các quãng máy ghi mất kết nối (để trừ khỏi khoảng lặng).

    Returns:
        (max_gap_seconds, list_of_gaps, total_messages_considered)
        Mỗi phần tử trong list_of_gaps là: (t1, t2, gap_seconds)
    """
    total_messages = len(timestamps)
    if total_messages < 2:
        return 0.0, [], total_messages

    max_gap = 0.0
    long_gaps: list[tuple[datetime, datetime, float]] = []

    for i in range(len(timestamps) - 1):
        t1 = timestamps[i]
        t2 = timestamps[i + 1]
        gap_sec = compute_market_silence_seconds(
            t1, t2, disconnect_intervals=disconnect_intervals
        )
        max_gap = max(max_gap, gap_sec)
        if gap_sec >= min_gap_seconds:
            long_gaps.append((t1, t2, gap_sec))

    return max_gap, long_gaps, total_messages


def _parse_until_time(until_str: str | None) -> dt_time | None:
    """Parse chuỗi --until thành datetime.time."""
    if not until_str:
        return None
    until_str = until_str.strip()
    parts = until_str.split(":")
    if len(parts) == 2:
        return dt_time(int(parts[0]), int(parts[1]))
    if len(parts) == 3:
        return dt_time(int(parts[0]), int(parts[1]), int(parts[2]))
    raise ValueError(f"Định dạng --until không hợp lệ (kỳ vọng HH:MM hoặc HH:MM:SS): '{until_str}'")


def _load_dotenv(env_path: str = ".env") -> None:
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


async def record_orderbook_stream(
    symbol: str | None = None,
    until_time: dt_time | None = None,
    config_path: str = "config/config.yaml",
    data_dir: Path | str = "data/orderbook",
) -> dict[str, Any]:
    """Kết nối WebSocket SSI và ghi nhận dòng tin QUOTE / TRADE."""
    _load_dotenv()
    app_cfg = load_config(config_path)
    now_vn = datetime.now(TZ)
    today = now_vn.date()

    # Kiểm tra ngày giao dịch (C3): không chạy cuối tuần và ngày lễ
    holidays = getattr(app_cfg, "holidays", frozenset())
    if not is_trading_day(today, holidays):
        print(
            f"[{now_vn.strftime('%H:%M:%S')}] Hôm nay ({today}) không phải ngày giao dịch (cuối tuần hoặc ngày lễ). Bỏ qua phiên ghi."
        )
        return {
            "symbol": symbol or "",
            "skipped": True,
            "reason": "non_trading_day",
            "date": today.isoformat(),
        }

    recorded_symbol = symbol or "VN30F"
    counts = {"QUOTE": 0, "TRADE": 0, "OTHER": 0}

    try:
        db_dsn = app_cfg.db_dsn.replace("@localhost:", "@127.0.0.1:")
        storage = Storage(db_dsn)

        # Động xác định mã hợp đồng front-month nếu không chỉ định (Brief 91 Task 1)
        if not symbol:
            async def _fetch_from_ssi() -> list[ContractInfo]:
                auth_ssi = await ensure_authenticated(app_cfg, storage)
                try:
                    from ssi_sdk import AsyncData

                    data_ssi = AsyncData(auth_ssi)
                    return await discover_derivative_contracts(data_ssi)
                finally:
                    try:
                        await auth_ssi.close()
                    except Exception:
                        pass

            symbol = await resolve_front_month_symbol(today, ssi_fetcher=_fetch_from_ssi)
            print(f"[{now_vn.strftime('%H:%M:%S')}] Tự động xác định hợp đồng front-month VN30F: {symbol}")

        recorded_symbol = symbol

        out_path = get_orderbook_filepath(data_dir, symbol, now_vn)
        print(f"[{now_vn.strftime('%H:%M:%S')}] Khởi động máy ghi sổ lệnh {symbol}")
        print(f"  File ghi nhận: {out_path}")
        if until_time:
            print(f"  Thời điểm tự dừng: {until_time.strftime('%H:%M:%S')} (giờ VN)")

        from ssi_sdk import AsyncStream

        timestamps: list[datetime] = []

        # Nạp dữ liệu đã ghi trước đó trong ngày (nếu có) để thống kê toàn diện cuối phiên
        if out_path.exists() and out_path.stat().st_size > 0:
            try:
                with gzip.open(out_path, mode="rt", encoding="utf-8") as existing_f:
                    for line in existing_f:
                        line_s = line.strip()
                        if not line_s:
                            continue
                        m = json.loads(line_s)
                        c = classify_message(m)
                        counts[c] = counts.get(c, 0) + 1
                        r_ts = m.get("recv_ts")
                        if r_ts:
                            timestamps.append(datetime.fromisoformat(r_ts))
                print(f"  Đã nạp {sum(counts.values()):,} tin đã ghi trước đó trong ngày.")
            except Exception as e:
                print(f"  Cảnh báo: không thể nạp dữ liệu cũ: {e}")

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def _handle_signal() -> None:
            print("\nNhận tín hiệu ngắt (Ctrl+C / SIGTERM), đang dừng an toàn...")
            stop_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _handle_signal)
            except (NotImplementedError, RuntimeError):
                # Trên Windows, add_signal_handler có thể không hỗ trợ trong một số loop
                pass

        # Quản lý reconnect (C1) và các quãng downtime (C2)
        consecutive_failures = 0
        disconnect_intervals: list[tuple[datetime, datetime]] = []
        t_disconnect: datetime | None = None
        recording_start_dt = now_vn
        rate_alarm_checked = False

        # Mở file gzip chế độ append
        with gzip.open(out_path, mode="at", encoding="utf-8") as gz_file:

            def on_message(raw_msg: Any) -> None:
                recv_dt = datetime.now(TZ)
                msg_dict = (
                    dataclasses.asdict(raw_msg)
                    if dataclasses.is_dataclass(raw_msg)
                    else raw_msg
                )
                if not isinstance(msg_dict, dict):
                    return

                cat = classify_message(msg_dict)
                counts[cat] = counts.get(cat, 0) + 1

                if cat in ("QUOTE", "TRADE"):
                    msg_dict["recv_ts"] = recv_dt.isoformat()
                    line = json.dumps(msg_dict, ensure_ascii=False, default=str)
                    gz_file.write(line + "\n")
                    gz_file.flush()
                    timestamps.append(recv_dt)

            while not stop_event.is_set():
                now_dt = datetime.now(TZ)
                if not should_reconnect(
                    is_connected=False,
                    current_time=now_dt.time(),
                    until_time=until_time,
                    consecutive_failures=consecutive_failures,
                    max_retries=10,
                ):
                    if until_time and now_dt.time() >= until_time:
                        print(
                            f"\nĐã đạt mốc thời gian tự dừng ({until_time.strftime('%H:%M:%S')}), kết thúc phiên ghi."
                        )
                    elif consecutive_failures >= 10:
                        print(
                            "\nĐã vượt quá giới hạn 10 lần thử kết nối lại thất bại, dừng an toàn."
                        )
                    break

                auth = None
                stream = None
                try:
                    auth = await ensure_authenticated(app_cfg, storage)
                    stream = AsyncStream(auth)
                    stream.streaming.on_data = on_message
                    now_str = datetime.now(TZ).strftime("%H:%M:%S")
                    print(f"[{now_str}] Đang kết nối WebSocket SSI...")
                    await stream.streaming.connect()
                    print(f"[{now_str}] Đã kết nối, đang đăng ký nhận dữ liệu mã {symbol}...")
                    await stream.streaming.subscribe_symbol([symbol])
                    print(f"[{now_str}] Bắt đầu lắng nghe dữ liệu stream...\n")

                    # Nối thành công: ghi nhận quãng gián đoạn nếu có (C2)
                    if t_disconnect is not None:
                        t_reconnect = datetime.now(TZ)
                        disconnect_intervals.append((t_disconnect, t_reconnect))
                        downtime_sec = (t_reconnect - t_disconnect).total_seconds()
                        print(
                            f"[{t_reconnect.strftime('%H:%M:%S')}] Đã kết nối lại thành công sau {downtime_sec:.2f}s gián đoạn."
                        )
                        t_disconnect = None
                    consecutive_failures = 0

                    while not stop_event.is_set():
                        now_dt = datetime.now(TZ)
                        now_loop = now_dt.time()
                        if until_time and now_loop >= until_time:
                            stop_event.set()
                            print(
                                f"\nĐã đạt mốc thời gian tự dừng ({until_time.strftime('%H:%M:%S')}), kết thúc phiên ghi."
                            )
                            break

                        # Kiểm tra lưu lượng tin QUOTE sau 10 phút đầu khớp lệnh liên tục (Brief 91 Task 2)
                        if not rate_alarm_checked:
                            elapsed_cont_min = compute_continuous_session_minutes(
                                now_dt, since_dt=recording_start_dt
                            )
                            if elapsed_cont_min >= 10.0:
                                rate_alarm_checked = True
                                if check_quote_rate_alarm(counts["QUOTE"], elapsed_cont_min):
                                    warn_msg = (
                                        f"Cảnh báo lưu lượng thấp bất thường: chỉ nhận được {counts['QUOTE']} tin QUOTE "
                                        f"sau {elapsed_cont_min:.1f} phút giao dịch liên tục cho mã {symbol}. "
                                        f"Có thể đang ghi sai mã hợp đồng phái sinh!"
                                    )
                                    print(f"\n[CẢNH BÁO] {warn_msg}\n")
                                    alert(
                                        "WARN",
                                        warn_msg,
                                        symbol=symbol,
                                        quote_count=counts["QUOTE"],
                                        elapsed_minutes=elapsed_cont_min,
                                    )

                        # Tự động phát hiện ngắt kết nối từ SSI và nối lại (C1)
                        ws_client = getattr(stream.streaming, "_ws", None)
                        if ws_client is not None and not ws_client.is_connected:
                            t_disconnect = datetime.now(TZ)
                            print(
                                f"\n[{t_disconnect.strftime('%H:%M:%S')}] WebSocket bị ngắt từ server SSI, chuẩn bị kết nối lại..."
                            )
                            break

                        await asyncio.sleep(0.5)

                except KeyboardInterrupt:
                    print("\nNhận ngắt bàn phím (KeyboardInterrupt)...")
                    stop_event.set()
                    break
                except Exception as e:
                    consecutive_failures += 1
                    if t_disconnect is None:
                        t_disconnect = datetime.now(TZ)
                    backoff = compute_reconnect_backoff(consecutive_failures)
                    print(
                        f"\n[{datetime.now(TZ).strftime('%H:%M:%S')}] Lỗi kết nối WebSocket: {e} "
                        f"(thất bại lần {consecutive_failures}), thử lại sau {backoff:.1f}s..."
                    )
                    await asyncio.sleep(backoff)
                finally:
                    if stream is not None:
                        try:
                            await stream.streaming.disconnect()
                        except Exception:
                            pass
                    if auth is not None:
                        try:
                            await auth.close()
                        except Exception:
                            pass

                if not stop_event.is_set() and (not until_time or datetime.now(TZ).time() < until_time):
                    await asyncio.sleep(1.0)

        if t_disconnect is not None:
            disconnect_intervals.append((t_disconnect, datetime.now(TZ)))

        # Thống kê sau phiên ghi (C2: tách bạch downtime máy ghi khỏi market silence)
        file_size_bytes = out_path.stat().st_size if out_path.exists() else 0
        file_size_mb = file_size_bytes / (1024 * 1024)

        total_downtime, detailed_intervals = compute_total_downtime_seconds(disconnect_intervals)
        max_gap, long_gaps, total_considered = detect_silence_gaps(
            timestamps, min_gap_seconds=10.0, disconnect_intervals=disconnect_intervals
        )

        print("\n" + "=" * 65)
        print("=== BÁO CÁO THỐNG KÊ MÁY GHI SỔ LỆNH VN30F (BRIEF 87/90) ===")
        print("=" * 65)
        print(f"- Hợp đồng: {symbol}")
        print(f"- File dữ liệu: {out_path}")
        print(f"- Dung lượng file: {file_size_bytes:,} bytes ({file_size_mb:.2f} MB)")
        print(
            f"- Tổng số tin nhận: {sum(counts.values()):,} "
            f"(QUOTE: {counts['QUOTE']:,}, TRADE: {counts['TRADE']:,}, KHÁC: {counts['OTHER']:,})"
        )
        print(f"- Tổng số tin QUOTE/TRADE đã xét khoảng lặng: {total_considered:,}")
        print(
            f"- Thời gian máy ghi mất kết nối: {total_downtime:.2f} giây ({len(detailed_intervals)} quãng ngắt)"
        )
        if detailed_intervals:
            print("  + Chi tiết các quãng mất kết nối của máy ghi:")
            for d1, d2, dur in detailed_intervals:
                print(f"    * Từ {d1.strftime('%H:%M:%S')} đến {d2.strftime('%H:%M:%S')}: {dur:.2f} giây")
        print(f"- Khoảng lặng thị trường dài nhất (trong các quãng kết nối): {max_gap:.2f} giây")

        if long_gaps:
            print(f"- Danh sách {len(long_gaps)} khoảng lặng thị trường > 10.0s trong giờ phiên:")
            for t1, t2, sec in long_gaps:
                t1_s = t1.astimezone(TZ).strftime("%H:%M:%S")
                t2_s = t2.astimezone(TZ).strftime("%H:%M:%S")
                print(f"  + Từ {t1_s} đến {t2_s}: {sec:.2f} giây")
        else:
            print("- Không phát hiện khoảng lặng thị trường nào > 10.0 giây trong giờ giao dịch.")
        print("=" * 65 + "\n")

        # Kiểm tra dừng sớm ngoài ý muốn trên ngày giao dịch (Brief 94 Task 1)
        now_stop = datetime.now(TZ)
        # Dung sai 60 giay: vong lap co the thoat ngay truoc moc --until vai phan giay
        # (lam tron giay, do tre cua stream.wait()). Ca hong that o 25/09 la som 4,75 GIO,
        # nen 60 giay khong lam giam kha nang phat hien, ma bo duoc bao dong oan.
        if should_alert_early_stop(
            now_stop, until_time, is_trading_day=True, tolerance_seconds=60.0
        ):
            total_recorded = sum(counts.values())
            stop_str = now_stop.strftime("%H:%M:%S")
            until_str = until_time.strftime("%H:%M:%S") if until_time else "N/A"
            early_msg = (
                f"Máy ghi {recorded_symbol} dừng sớm ngoài ý muốn lúc {stop_str} (kỳ vọng chạy đến {until_str}). "
                f"Tổng số tin đã ghi được: {total_recorded:,} "
                f"(QUOTE: {counts['QUOTE']:,}, TRADE: {counts['TRADE']:,}, KHÁC: {counts['OTHER']:,})."
            )
            print(f"\n[CRITICAL] {early_msg}\n", file=sys.stderr)
            alert(
                "CRITICAL",
                early_msg,
                symbol=recorded_symbol,
                actual_stop=stop_str,
                until_time=until_str,
                recorded_counts=counts,
                total_recorded=total_recorded,
            )
            raise EarlyStopError(early_msg)

        return {
            "symbol": symbol,
            "file_path": str(out_path),
            "file_size_bytes": file_size_bytes,
            "counts": counts,
            "total_considered": total_considered,
            "total_downtime_seconds": total_downtime,
            "disconnect_intervals": detailed_intervals,
            "max_gap_seconds": max_gap,
            "long_gaps": long_gaps,
        }

    except EarlyStopError:
        raise
    except Exception as e:
        total_recorded = sum(counts.values())
        err_type = type(e).__name__
        crit_msg = (
            f"Máy ghi {recorded_symbol} gặp lỗi chưa xử lý và dừng đột ngột: [{err_type}] {e}. "
            f"Tổng số tin đã ghi được tới lúc chết: {total_recorded:,} "
            f"(QUOTE: {counts['QUOTE']:,}, TRADE: {counts['TRADE']:,}, KHÁC: {counts['OTHER']:,})."
        )
        print(f"\n[CRITICAL] {crit_msg}\n", file=sys.stderr)
        alert(
            "CRITICAL",
            crit_msg,
            error_type=err_type,
            error_message=str(e),
            symbol=recorded_symbol,
            recorded_counts=counts,
            total_recorded=total_recorded,
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Máy ghi dữ liệu sổ lệnh và dòng lệnh VN30F (Brief 87/90)"
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Mã hợp đồng phái sinh (mặc định: tự động xác định front-month còn sống)",
    )
    parser.add_argument(
        "--until",
        default=None,
        help="Mốc giờ VN tự dừng (định dạng HH:MM hoặc HH:MM:SS)",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Đường dẫn file config (mặc định: config/config.yaml)",
    )
    parser.add_argument(
        "--data-dir",
        default="data/orderbook",
        help="Thư mục gốc lưu trữ dữ liệu (mặc định: data/orderbook)",
    )
    args = parser.parse_args()

    until_time = _parse_until_time(args.until)

    try:
        asyncio.run(
            record_orderbook_stream(
                symbol=args.symbol,
                until_time=until_time,
                config_path=args.config,
                data_dir=args.data_dir,
            )
        )
    except Exception as e:
        print(f"\n[LỖI] Máy ghi gặp sự cố: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
