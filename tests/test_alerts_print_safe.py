"""Gói B2 (brief 04/09): _print_safe gộp về trading/alerts.py — một bản duy nhất.

Tiêu chí 2: ép print ném UnicodeEncodeError => hàm trả về êm; ép CẢ HAI lần in
ném => vẫn êm. Dead-man's switch (heartbeat_check) tuyệt đối không được ném.
"""

import builtins

from trading import alerts


def test_print_safe_khong_nem_khi_print_chet(monkeypatch):
    """Lần in đầu ném (UnicodeEncodeError kiểu cp1252) => hàm trả về êm sau khi
    hạ cấp ASCII. Không được lan ra ngoài."""

    calls: list[str] = []

    def fake_print(*args, **kwargs):
        text = args[0] if args else ""
        calls.append(text)
        if len(calls) == 1:
            raise UnicodeEncodeError("cp1252", "dữ", 0, 1, "không mã hoá được")

    monkeypatch.setattr(builtins, "print", fake_print)
    alerts._print_safe("dữ liệu ngừng chảy")  # không được ném
    assert len(calls) == 2
    assert calls[1] == "d? li?u ng?ng ch?y"  # bản ASCII hạ cấp (replace = '?')


def test_print_safe_khong_nem_khi_ca_hai_lan_chet(monkeypatch):
    """Cả lần in đầu lẫn lần hạ cấp ASCII đều ném => vẫn êm (FEE-ALARM-2:
    chuông không được chết theo đường in)."""

    def fake_print(*args, **kwargs):
        raise UnicodeEncodeError("cp1252", "x", 0, 1, "không mã hoá được")

    monkeypatch.setattr(builtins, "print", fake_print)
    alerts._print_safe("cảnh báo")  # không được ném — pass nghĩa là đạt


def test_print_safe_in_binh_thuong(monkeypatch, capsys):
    """Đường thường: in thẳng text gốc, không hạ cấp."""

    alerts._print_safe("máy chủ vẫn ổn")
    assert capsys.readouterr().out == "máy chủ vẫn ổn\n"
