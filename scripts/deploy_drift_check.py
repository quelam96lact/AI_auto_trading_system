"""Cảnh báo lệch triển khai: code đã sửa mà container vẫn chạy image cũ.

Brief 2026-09-01 (đợt 7). Từ 15/08 đến 01/09/2026 collector/engine chạy image
build 15/08 — mọi sửa trong trading/ hai tuần chưa từng chạy, và không ai biết
vì phép kiểm cần có người nhớ chạy. Script này tự kêu một lần mỗi ngày.

So mốc BUILD của image (docker inspect .Created) với commit GẦN NHẤT chạm
trading/ (git log -1 --format=%ct -- trading/). Cả hai phía đều là epoch giây —
KHÔNG so chuỗi ISO (git in múi địa phương +07:00, docker in UTC Z; so chuỗi
cho kết quả ngược, đã gặp thật 01/09).

Exit code: 0 = ổn, 1 = có cảnh báo đã gửi.

Lệch triển khai không khẩn cấp theo phút như service chết nên KHÔNG thêm vào
heartbeat_check.py — chuông đó chỉ được phụ thuộc DB + config; docker/git là
mở rộng bề mặt phụ thuộc của chính cái chuông báo (bài học 51ff6de: một phụ
thuộc mới là một cách mới để chuông chết câm). Script này hỏng thì không kéo
theo gì.
"""

import os
import subprocess
import sys
from datetime import datetime

from trading.telegram import send_telegram

SERVICES = ("collector", "engine")

# Neo theo vi tri CHINH SCRIPT, khong theo cwd. Do that 01/09: chay tu thu muc
# khac (scheduled task co the co cwd bat ky) thi `git log -- trading/` that bai
# va script bao "khong doc duoc commit" — mot chuong bao chi dung khi duoc goi
# tu dung cho la chuong bao khong dang tin.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _human_drift(seconds: int) -> str:
    """Độ lệch dưới dạng người đọc hiểu: phút / giờ / ngày."""
    if seconds < 3600:
        return f"{seconds // 60} phút"
    if seconds < 86400:
        return f"{seconds // 3600} giờ {seconds % 3600 // 60} phút"
    return f"{seconds // 86400} ngày {seconds % 86400 // 3600} giờ"


def drift_report(commit_epoch: int, images: dict[str, int | None]) -> list[str]:
    """So mốc build image với commit gần nhất chạm trading/.

    images: {"collector": epoch, "engine": epoch}; None = không đọc được
    (container không chạy / không có image). Rỗng = mọi thứ ổn.

    Quy tắc:
    - image cũ hơn commit ⇒ cảnh báo, nêu rõ lệch bao nhiêu và service nào.
    - None ⇒ cảnh báo riêng, KHÔNG im lặng coi như ổn (thiếu dữ liệu thì từ
      chối + báo, không bao giờ rơi về giá trị dễ dãi).
    - image bằng đúng commit_epoch ⇒ ổn (build ngay sau commit).
    """
    messages = []
    for service, image_epoch in images.items():
        if image_epoch is None:
            messages.append(
                f"[deploy-drift] {service}: KHÔNG đọc được image build — "
                "container không chạy hoặc không có image, không xác nhận được "
                "đang chạy code hiện tại"
            )
        elif image_epoch < commit_epoch:
            messages.append(
                f"[deploy-drift] {service}: image CŨ hơn commit gần nhất chạm "
                f"trading/ ({_human_drift(commit_epoch - image_epoch)}) — "
                "dựng lại container (docker compose build collector engine && "
                "docker compose up -d --no-deps collector engine)"
            )
    return messages


def _git_trading_commit_epoch() -> int | None:
    """Epoch giây của commit gần nhất chạm trading/. None = không đọc được."""
    try:
        r = subprocess.run(
            ["git", "-C", REPO, "log", "-1", "--format=%ct", "--", "trading/"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception:
        return None
    if r.returncode != 0:
        return None
    try:
        return int(r.stdout.strip())
    except ValueError:
        return None


def _image_created_epoch(container: str) -> int | None:
    """Epoch giây build của image container đang dùng. None = không đọc được."""
    try:
        img = subprocess.run(
            ["docker", "inspect", "-f", "{{.Image}}", container],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if img.returncode != 0:
            return None
        created = subprocess.run(
            ["docker", "inspect", "-f", "{{.Created}}", img.stdout.strip()],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if created.returncode != 0:
            return None
        iso = created.stdout.strip()
        # docker in UTC dạng "2026-09-01T13:33:33.982599925Z" — fromisoformat
        # (Python >= 3.11) đọc 'Z' trực tiếp
        dt = datetime.fromisoformat(iso)
        return int(dt.timestamp())
    except Exception:
        return None


def _print_safe(text: str) -> None:
    """In lý do cảnh báo mà KHÔNG BAO GIỜ ném.

    Khuôn này lấy từ scripts/heartbeat_check.py:153. 2026-09-01: print() đã làm
    CHẾT chuông báo trên Windows — stdout chuyển hướng ra file, Python chọn
    cp1252, ký tự tiếng Việt không mã hoá được -> UnicodeEncodeError ném ra
    trước send_telegram. In không được phép làm chết script.
    """
    try:
        print(text)
        return
    except Exception:
        pass
    # Hạ cấp: mất dấu tiếng Việt còn hơn mất cả cảnh báo.
    try:
        print(text.encode("ascii", "replace").decode("ascii"))
    except Exception:
        pass


def _alert(messages: list[str]) -> int:
    """In ly do ra stdout TRUOC roi moi gui — neu send_telegram nem thi van
    con ban ghi o log (khuon heartbeat_check). Gui hong khong duoc lam chet
    script, nhung PHAI de lai dau vet."""
    text = "\n".join(messages)
    _print_safe(text)
    try:
        send_telegram(text)
    except Exception as e:
        _print_safe(f"[deploy-drift] GUI TELEGRAM HONG: {type(e).__name__}: {e}")
    return 1


def main() -> int:
    # Ép utf-8 để lý do cảnh báo còn dấu tiếng Việt; thất bại cũng không sao,
    # _print_safe đã có đường lui.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    commit_epoch = _git_trading_commit_epoch()
    if commit_epoch is None:
        # Cung phai KEU: mot chuong tu bao ma im lang dung luc chinh no hong
        # thi vo dung. Truoc day nhanh nay chi in ra stdout roi return 1.
        return _alert(
            [
                (
                    "[deploy-drift] KHÔNG đọc được commit gần nhất chạm "
                    "trading/ (git lỗi?) — không xác nhận được trạng thái "
                    "triển khai"
                )
            ]
        )

    images = {svc: _image_created_epoch(f"ai_auto_trading_system-{svc}-1") for svc in SERVICES}
    messages = drift_report(commit_epoch, images)

    if messages:
        return _alert(messages)
    _print_safe("OK: không lệch triển khai — image của collector và engine mới hơn commit gần nhất chạm trading/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
