"""ISO-4 / ISO-5: Chốt an toàn Telegram và SSI credentials cho suite test.

File này kiểm tra hàng rào cách ly cho cả ISO-4 (Telegram) lẫn ISO-5 (SSI secrets).
"""

import os


def test_telegram_env_neutralized_for_whole_suite():
    """Dù máy chạy test có sẵn TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID thật trong
    môi trường, conftest.py phải xóa chúng TRƯỚC khi bất kỳ test nào chạy —
    nếu không, trading/telegram.py::send_telegram() sẽ bắn tin thật ra ngoài.
    """
    assert not os.environ.get("TELEGRAM_BOT_TOKEN"), (
        "TELEGRAM_BOT_TOKEN con ton tai trong os.environ khi chay test — "
        "suite co the bắn Telegram that voi du lieu gia (xem ISO-4)."
    )
    assert not os.environ.get("TELEGRAM_CHAT_ID"), (
        "TELEGRAM_CHAT_ID con ton tai trong os.environ khi chay test — "
        "suite co the bắn Telegram that voi du lieu gia (xem ISO-4)."
    )


def test_ssi_env_neutralized_for_whole_suite():
    """ISO-5 (Brief đợt 23): Dù máy chạy test có sẵn secret SSI thật trong môi trường
    hoặc nạp từ .env qua setdefault(), conftest.py phải hard-set rỗng 5 biến SSI.
    """
    ssi_vars = [
        "SSI_CONSUMER_ID",
        "SSI_CONSUMER_SECRET",
        "SSI_API_KEY",
        "SSI_API_SECRET",
        "SSI_PRIVATE_KEY",
    ]
    for var in ssi_vars:
        assert not os.environ.get(var), (
            f"{var} còn tồn tại trong os.environ khi chạy test — "
            "suite có thể vô tình gọi SSI API thật (xem ISO-5)."
        )

