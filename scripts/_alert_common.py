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
"""

from collections.abc import Callable

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
