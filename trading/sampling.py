"""Module phân chia tập mẫu và cơ chế khóa holdout ngoài mẫu (Brief đợt 9).

CƠ CHẾ KỶ LUẬT NGOÀI MẪU:
1. Phân chia theo thời gian trên chuỗi bars_daily (2016-01-04 -> 2026-08-13):
   - Train:      2016-01-04 -> 2022-06-30 (phát triển, quét tham số thoải mái).
   - Validation: 2022-07-01 -> 2023-12-31 (chọn cấu hình cuối cùng).
   - Holdout:    2024-01-01 -> 2026-08-13 (kiểm tra đúng MỘT lần trước go-live).
2. Khóa cơ chế: Bất kỳ thao tác nạp dữ liệu nào chồng lấn vào kỳ Holdout mà KHÔNG truyền
   unlock_holdout=True đều bị TỪ CHỐI (raise PermissionError).
3. Ghi vết truy xuất: Mỗi lần mở khóa Holdout đều được tự động ghi nhật ký vào
   docs/holdout-unlock-log.md.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Literal

from trading.calendar_vn import TZ
from trading.models import Bar

TRAIN_START = date(2016, 1, 4)
TRAIN_END = date(2022, 6, 30)

VAL_START = date(2022, 7, 1)
VAL_END = date(2023, 12, 31)

HOLDOUT_START = date(2024, 1, 1)
HOLDOUT_END = date(2026, 8, 13)

SplitName = Literal["train", "validation", "holdout", "all"]


def get_split_range(split: SplitName) -> tuple[date, date]:
    """Lấy khoảng ngày bắt đầu và kết thúc cho từng tập mẫu."""
    if split == "train":
        return TRAIN_START, TRAIN_END
    elif split == "validation":
        return VAL_START, VAL_END
    elif split == "holdout":
        return HOLDOUT_START, HOLDOUT_END
    elif split == "all":
        return TRAIN_START, HOLDOUT_END
    else:
        raise ValueError(f"Tập mẫu không hợp lệ: {split}")


def log_holdout_unlock(
    strategy_name: str,
    config_info: str,
    reason: str,
    log_file: str = "docs/holdout-unlock-log.md",
) -> None:
    """Ghi nhật ký mở khóa tập Holdout (append-only)."""
    p = Path(log_file)
    p.parent.mkdir(parents=True, exist_ok=True)

    now_str = datetime.now(tz=TZ).strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"| {now_str} | {strategy_name} | {config_info} | {reason} |\n"

    if not p.exists():
        header = (
            "# NHẬT KÝ MỞ KHÓA TẬP DỮ LIỆU NGOÀI MẪU (HOLDOUT UNLOCK LOG)\n\n"
            "| Thời gian | Chiến lược | Cấu hình tham số | Lý do mở khóa |\n"
            "|---|---|---|---|\n"
        )
        p.write_text(header + log_entry, encoding="utf-8")
    else:
        with p.open("a", encoding="utf-8") as f:
            f.write(log_entry)


def filter_bars_by_split(
    bars: list[Bar],
    split: SplitName,
    unlock_holdout: bool = False,
    strategy_name: str = "UNKNOWN",
    config_info: str = "DEFAULT",
    unlock_reason: str = "",
    log_file: str = "docs/holdout-unlock-log.md",
) -> list[Bar]:
    """Lọc danh sách bar theo tập mẫu thời gian có cơ chế khóa bảo vệ Holdout.

    Args:
        bars: Danh sách bar lịch sử.
        split: "train", "validation", "holdout", "all".
        unlock_holdout: Cờ cho phép truy cập tập holdout hoặc tập all chứa holdout.
        strategy_name: Tên chiến lược (phục vụ ghi log khi mở holdout).
        config_info: Thông tin tham số (phục vụ ghi log).
        unlock_reason: Lý do mở khóa holdout.
        log_file: Đường dẫn file nhật ký.

    Returns:
        list[Bar]: Danh sách bar thuộc tập mẫu yêu cầu.

    Raises:
        PermissionError: Nếu truy cập kỳ Holdout mà không có unlock_holdout=True.
    """
    if split in ("holdout", "all"):
        if not unlock_holdout:
            raise PermissionError(
                f"TẬP DỮ LIỆU HOLDOUT (từ {HOLDOUT_START}) ĐANG BỊ KHÓA! "
                "Cấm truy cập tập holdout khi đang phát triển/quét tham số. "
                "Để mở khóa kiểm tra đúng 1 lần, phải truyền cờ unlock_holdout=True kèm unlock_reason."
            )
        # Ghi log mở khóa khi có cờ
        log_holdout_unlock(
            strategy_name=strategy_name,
            config_info=config_info,
            reason=unlock_reason or "Holdout evaluation",
            log_file=log_file,
        )

    start_d, end_d = get_split_range(split)

    return [b for b in bars if start_d <= b.ts.date() <= end_d]
