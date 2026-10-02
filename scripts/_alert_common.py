"""Khuôn chuông tự kêu dùng chung cho các job trong `scripts/`.

Tách 2026-09-05. `deploy_drift_check._alert` và `check_silent_engine._alert`
từng là hai bản chép của cùng một công thức, khác nhau đúng một chuỗi tiền tố —
đúng thứ `4ea4c8d` đã dọn một lần và `_db_common.py` được tách ra vì nó (sáu
bản chép đã bắt đầu lệch nhau).

Thứ tự IN TRƯỚC, GỬI SAU là phần quan trọng nhất, không phải chi tiết phong
cách: nếu `send` ném thì lý do cảnh báo vẫn còn trong log. Gửi hỏng không được
làm chết job, nhưng PHẢI để lại dấu vết — một log nói "đã cảnh báo" trong khi
Telegram không hề đi là một cách im lặng tệ hơn cả không có chuông.

`send` truyền vào chứ không import ở đây, để mỗi script giữ `send_telegram`
là biến toàn cục của CHÍNH NÓ — test hiện có (`test_deploy_drift_check.py`)
monkeypatch theo module gọi, và một lần tách khiến monkeypatch trượt sẽ làm
suite gửi Telegram thật.

HAI HỌ mã thoát cho job cảnh báo (đợt 132) — cả hai đều đúng, đừng gộp nhầm:

| Họ                        | Ai dùng                                            | `1` nghĩa là                  | Gửi Telegram hỏng |
|---------------------------|----------------------------------------------------|-------------------------------|-------------------|
| Theo phát hiện            | deploy_drift_check.py, check_silent_engine.py      | có vấn đề được phát hiện      | vẫn trả 1         |
|                           | (qua `alert_and_fail` ở đây)                       |                               |                   |
| Theo gửi được hay không   | docker_down_alert.py, container_health_check.py,   | đã gửi thành công             | trả 2             |
| (đợt 126)                 | backup_check.py, disk_check.py                     |                               |                   |

`alert_and_fail` thuộc họ thứ nhất và luôn trả 1: với `deploy-drift`, 1 mã hoá
"có lệch triển khai", không phải "đã gửi xong". Đó là quyết định có chủ ý, đã có
test ghim. Trước khi gộp hai họ này làm một, đọc `test_deploy_drift_check.py:86`.
"""

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from trading.alerts import _print_safe


def alert_and_fail(
    prefix: str,
    messages: list[str],
    send: Callable[[str], object],
) -> int:
    """In lý do rồi gửi. Luôn trả 1 — dùng làm mã thoát của job."""
    text = "\n".join(messages)
    _print_safe(text)
    try:
        ok = send(text)
        if ok is False:
            _print_safe(f"{prefix} GUI TELEGRAM HONG: send tra ve False")
    except Exception as e:
        _print_safe(f"{prefix} GUI TELEGRAM HONG: {type(e).__name__}: {e}")
    return 1


def load_json_state(path: str | Path, label: str) -> dict[str, Any]:
    """Đọc file trạng thái JSON. Nếu không tồn tại hoặc lỗi, trả về {}.
    Khi file không phải dict hoặc hỏng, in cảnh báo qua _print_safe và không bao giờ ném."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            _print_safe(
                f"[{label}] File trạng thái {path} không đúng định dạng dict — coi như lần đầu."
            )
            return {}
    except Exception as e:
        _print_safe(
            f"[{label}] File trạng thái {path} hỏng hoặc không đọc được ({e}) — coi như lần chạy đầu."
        )
        return {}


def save_json_state(path: str | Path, state: dict[str, Any]) -> None:
    """Ghi trạng thái ra file JSON an toàn qua file tạm và os.replace.
    Tạo thư mục cha nếu chưa có; lỗi ghi/replace được để ném lên cho nơi gọi quyết định."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = p.with_name(p.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, p)
