"""Kiểm tra chất lượng file sổ lệnh VN30F hằng ngày sau phiên (Brief 94 Task 2).

Chức năng:
1. Nếu hôm nay không phải ngày giao dịch -> thoát 0 im lặng (dùng is_trading_day từ trading.calendar_vn).
2. Xác định mã front-month hôm nay và đường dẫn file kỳ vọng data/orderbook/<symbol>/<hôm nay>.jsonl.gz.
3. Nếu file không tồn tại trên ngày giao dịch -> alert("CRITICAL", ...) và thoát mã 2.
4. Nếu file tồn tại -> gọi lại verify_orderbook_file:
   - Nếu không đạt -> alert("WARN", ...) nêu rõ lý do và thoát mã 1.
   - Nếu đạt -> in tóm tắt ra stdout, thoát mã 0, không gửi Telegram.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import io
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows to avoid UnicodeEncodeError
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

# Ensure repo root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.record_vn30f_orderbook import resolve_front_month_symbol
from scripts.verify_orderbook_file import VerificationResult, verify_orderbook_file
from trading.alerts import alert
from trading.calendar_vn import TZ, is_trading_day
from trading.config import load_config


@dataclass(frozen=True)
class DailyCheckDecision:
    """Kết quả đánh giá kiểm tra file sổ lệnh cuối ngày."""

    exit_code: int
    alert_level: str | None  # "CRITICAL", "WARN", hoặc None
    message: str
    is_silent: bool
    reasons: list[str] = dataclasses.field(default_factory=list)


def evaluate_daily_orderbook_check(
    is_trading_day: bool,
    file_exists: bool,
    verification_result: VerificationResult | None = None,
    target_date: date | None = None,
    symbol: str | None = None,
    expected_path: str | Path | None = None,
) -> DailyCheckDecision:
    """Hàm thuần (Brief 94 Task 2): Đánh giá 4 kịch bản kiểm tra file sổ lệnh.

    1. Ngày không giao dịch -> thoát 0 im lặng (is_silent=True, alert_level=None).
    2. Ngày giao dịch nhưng thiếu file -> thoát 2, alert CRITICAL.
    3. File tồn tại nhưng không đạt chuẩn nghiệm thu -> thoát 1, alert WARN.
    4. File tồn tại và đạt chuẩn nghiệm thu -> thoát 0 im lặng (in stdout, alert_level=None).
    """
    date_str = target_date.isoformat() if target_date else "hôm nay"
    sym_str = symbol or "VN30F"
    file_desc = str(expected_path) if expected_path else f"data/orderbook/{sym_str}/{date_str}.jsonl.gz"

    # 1. Kịch bản ngày không giao dịch
    if not is_trading_day:
        return DailyCheckDecision(
            exit_code=0,
            alert_level=None,
            message=f"Ngày {date_str} không phải ngày giao dịch (cuối tuần hoặc ngày lễ). Bỏ qua kiểm tra sổ lệnh.",
            is_silent=True,
            reasons=[],
        )

    # 2. Kịch bản ngày giao dịch nhưng file không tồn tại
    if not file_exists:
        msg = (
            f"Hôm nay ({date_str}) là ngày giao dịch nhưng không tìm thấy file sổ lệnh kỳ vọng: {file_desc}! "
            f"Máy ghi có thể chưa bao giờ chạy hoặc Task Scheduler bị lỗi."
        )
        return DailyCheckDecision(
            exit_code=2,
            alert_level="CRITICAL",
            message=msg,
            is_silent=False,
            reasons=[f"File sổ lệnh {file_desc} không tồn tại trên ngày giao dịch."],
        )

    # 3. Kịch bản file tồn tại nhưng không đạt chuẩn nghiệm thu
    if verification_result is None or not verification_result.is_valid:
        reasons = verification_result.reasons if verification_result else ["Không có kết quả nghiệm thu."]
        reasons_summary = "; ".join(reasons)
        msg = (
            f"File sổ lệnh ngày {date_str} ({sym_str}) không đạt tiêu chuẩn chất lượng: {reasons_summary}"
        )
        return DailyCheckDecision(
            exit_code=1,
            alert_level="WARN",
            message=msg,
            is_silent=False,
            reasons=reasons,
        )

    # 4. Kịch bản file tồn tại và đạt chuẩn
    msg = f"File sổ lệnh ngày {date_str} ({sym_str}) đạt đầy đủ tiêu chuẩn chất lượng."
    return DailyCheckDecision(
        exit_code=0,
        alert_level=None,
        message=msg,
        is_silent=True,
        reasons=[],
    )


def _load_dotenv(env_path: str = ".env") -> None:
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


async def check_orderbook_daily(
    target_date: date | None = None,
    symbol: str | None = None,
    data_dir: Path | str = "data/orderbook",
    config_path: str = "config/config.yaml",
) -> int:
    """Quy trình kiểm tra file sổ lệnh hằng ngày sau phiên (chạy lúc 15:30)."""
    _load_dotenv()
    now_vn = datetime.now(TZ)
    d = target_date or now_vn.date()

    app_cfg = load_config(config_path)
    holidays = getattr(app_cfg, "holidays", frozenset())

    # 1. Kiểm tra ngày giao dịch
    if not is_trading_day(d, holidays):
        decision = evaluate_daily_orderbook_check(
            is_trading_day=False,
            file_exists=False,
            target_date=d,
        )
        print(f"[{now_vn.strftime('%H:%M:%S')}] {decision.message}")
        return decision.exit_code

    # 2. Xác định mã front-month nếu chưa chỉ định
    sym = symbol
    if not sym:
        try:
            from scripts.measure_derivative_contract_volume import (
                discover_derivative_contracts,
            )
            from trading.collector.ssi_auth import ensure_authenticated
            from trading.storage.db import Storage

            db_dsn = app_cfg.db_dsn.replace("@localhost:", "@127.0.0.1:")
            storage = Storage(db_dsn)

            async def _fetch_from_ssi():
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

            sym = await resolve_front_month_symbol(d, ssi_fetcher=_fetch_from_ssi)
        except Exception:
            # Rơi về công thức tự tính nếu SSI không truy cập được
            sym = await resolve_front_month_symbol(d)

    expected_file = Path(data_dir) / sym / f"{d.isoformat()}.jsonl.gz"
    file_exists = expected_file.exists() and expected_file.stat().st_size > 0

    # 3. File không tồn tại -> Báo động CRITICAL, thoát 2
    if not file_exists:
        decision = evaluate_daily_orderbook_check(
            is_trading_day=True,
            file_exists=False,
            target_date=d,
            symbol=sym,
            expected_path=expected_file,
        )
        print(f"[{now_vn.strftime('%H:%M:%S')}] [CRITICAL] {decision.message}", file=sys.stderr)
        alert(
            "CRITICAL",
            decision.message,
            target_date=d.isoformat(),
            symbol=sym,
            expected_file=str(expected_file),
        )
        return decision.exit_code

    # 4. File tồn tại -> Gọi verify_orderbook_file kiểm tra chất lượng
    metrics, v_result = await verify_orderbook_file(
        expected_file,
        expected_symbol=sym,
    )

    decision = evaluate_daily_orderbook_check(
        is_trading_day=True,
        file_exists=True,
        verification_result=v_result,
        target_date=d,
        symbol=sym,
        expected_path=expected_file,
    )

    if not decision.is_silent and decision.alert_level:
        print(f"[{now_vn.strftime('%H:%M:%S')}] [{decision.alert_level}] {decision.message}", file=sys.stderr)
        alert(
            decision.alert_level,
            decision.message,
            target_date=d.isoformat(),
            symbol=sym,
            file=str(expected_file),
            reasons=decision.reasons,
            coverage_ratio=metrics.coverage_ratio,
            empty_slots=metrics.empty_slots,
        )
    else:
        print(f"[{now_vn.strftime('%H:%M:%S')}] [OK] {decision.message}")

    return decision.exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kiểm tra chất lượng file sổ lệnh VN30F hằng ngày sau phiên (Brief 94 Task 2)"
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Ngày kiểm tra theo định dạng YYYY-MM-DD (mặc định: hôm nay)",
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help="Mã hợp đồng phái sinh (mặc định: tự động xác định front-month)",
    )
    parser.add_argument(
        "--data-dir",
        default="data/orderbook",
        help="Thư mục gốc lưu trữ dữ liệu (mặc định: data/orderbook)",
    )
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Đường dẫn file config (mặc định: config/config.yaml)",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    target_date = date.fromisoformat(args.date) if args.date else None

    exit_code = asyncio.run(
        check_orderbook_daily(
            target_date=target_date,
            symbol=args.symbol,
            data_dir=args.data_dir,
            config_path=args.config,
        )
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
