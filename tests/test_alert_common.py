"""Tests cho scripts/_alert_common.py — khuôn chuông tự kêu.

Brief đợt 58 (2026-09-19) Task 1:
- send trả False -> in GUI TELEGRAM HONG: send tra ve False, trả 1.
- send ném Exception -> in GUI TELEGRAM HONG: {type(e)}: {e}, trả 1.
- send trả True -> KHÔNG in GUI TELEGRAM HONG, trả 1.
"""

from scripts._alert_common import alert_and_fail


def test_send_tra_false_in_gui_telegram_hong_va_tra_1(capsys):
    """Khi send trả False -> in câu báo gửi hỏng và vẫn thoát với mã 1."""
    ret = alert_and_fail("[test-alert]", ["canh bao 1", "canh bao 2"], lambda msg: False)
    assert ret == 1
    out = capsys.readouterr().out
    assert "canh bao 1" in out
    assert "[test-alert] GUI TELEGRAM HONG: send tra ve False" in out


def test_send_nem_exception_in_gui_telegram_hong_va_tra_1(capsys):
    """Khi send ném Exception -> bắt được exception, in loại lỗi và vẫn thoát mã 1."""
    def _exploding_send(msg):
        raise ConnectionResetError("Connection lost to Telegram")

    ret = alert_and_fail("[test-alert]", ["loi mang"], _exploding_send)
    assert ret == 1
    out = capsys.readouterr().out
    assert "loi mang" in out
    assert "[test-alert] GUI TELEGRAM HONG: ConnectionResetError: Connection lost to Telegram" in out


def test_send_tra_true_khong_in_gui_telegram_hong_va_tra_1(capsys):
    """Khi send trả True -> in nội dung cảnh báo ban đầu, KHÔNG in câu gửi hỏng, trả 1."""
    ret = alert_and_fail("[test-alert]", ["noi dung binh thuong"], lambda msg: True)
    assert ret == 1
    out = capsys.readouterr().out
    assert "noi dung binh thuong" in out
    assert "GUI TELEGRAM HONG" not in out
