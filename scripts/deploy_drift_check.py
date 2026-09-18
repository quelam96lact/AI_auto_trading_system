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

# Hai loi goi: `uv run python scripts/x.py` (scripts/ o sys.path[0]) va
# `from scripts import deploy_drift_check` (test). Khuon nay lay tu
# measure_octopus_matched_basket.py — thieu no thi test chay RIENG file nay se
# ModuleNotFoundError, con chay ca suite lai qua vi module khac da chen
# scripts/ vao sys.path truoc. Da gap that 05/09 khi tach _alert_common.
try:
    from _alert_common import alert_and_fail
except ImportError:
    from scripts._alert_common import alert_and_fail

from trading.alerts import _print_safe
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


def drift_report(commit_epoch: int, images: dict[str, int | str | None]) -> list[str]:
    """So mốc build image với commit gần nhất chạm trading/.

    images: {"collector": epoch_or_status, "engine": epoch_or_status};
    - int: epoch giây build image
    - 'image_missing': container đang chạy nhưng image đã biến mất
    - None / 'container_down': container không chạy

    Quy tắc:
    - container đang chạy nhưng image biến mất ⇒ cảnh báo nghiêm trọng (chạy code không ai truy được).
    - container không chạy ⇒ cảnh báo container không chạy.
    - image cũ hơn commit ⇒ cảnh báo, nêu rõ lệch bao nhiêu và service nào.
    - image bằng hoặc mới hơn commit_epoch ⇒ ổn.
    """
    messages = []
    for service, val in images.items():
        if val == "image_missing":
            messages.append(
                f"[deploy-drift] {service}: container đang chạy nhưng image đã BIẾN MẤT "
                "(bị xoá hoặc build mới đè tag) — đang chạy code không ai truy được!"
            )
        elif val is None or val == "container_down":
            messages.append(
                f"[deploy-drift] {service}: container KHÔNG chạy — "
                "không xác nhận được đang chạy code hiện tại"
            )
        elif isinstance(val, (int, float)) and val < commit_epoch:
            messages.append(
                f"[deploy-drift] {service}: image CŨ hơn commit gần nhất chạm "
                f"trading/ ({_human_drift(commit_epoch - int(val))}) — "
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


def _image_created_epoch(container: str) -> int | str | None:
    """Epoch giây build của image container đang dùng.
    Trả về:
    - int: epoch giây khi đọc thành công.
    - 'image_missing': container đang chạy nhưng image đã biến mất (bị xoá/đè tag).
    - None: container không chạy hoặc docker lỗi.
    """
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
        image_id = img.stdout.strip()
        if not image_id:
            return None
        created = subprocess.run(
            ["docker", "inspect", "-f", "{{.Created}}", image_id],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if created.returncode != 0:
            return "image_missing"
        iso = created.stdout.strip()
        # docker in UTC dạng "2026-09-01T13:33:33.982599925Z" — fromisoformat
        # (Python >= 3.11) đọc 'Z' trực tiếp
        dt = datetime.fromisoformat(iso)
        return int(dt.timestamp())
    except Exception:
        return None


def _alert(messages: list[str]) -> int:
    """In ly do ra stdout TRUOC roi moi gui. Cong thuc o `_alert_common` —
    `send_telegram` truyen vao de no van la bien toan cuc cua MODULE NAY, vi
    test monkeypatch theo day."""
    return alert_and_fail("[deploy-drift]", messages, send_telegram)


def get_container_name(service: str, project_name: str | None = None) -> str:
    """Suy ra tên container cho service theo Docker Compose convention:
    Ưu tiên project_name tham số -> COMPOSE_PROJECT_NAME từ môi trường -> tên thư mục REPO (chuẩn hoá chữ thường, ký tự lạ -> _).

    CO HAI BAN CUA QUY TAC NAY — ngoai le co chu y cua "mot cong thuc mot noi"
    (4ea4c8d). Ban kia: run_if_docker_up.sh (bien PROJECT_NAME). Ly do khong
    gop: cong Docker trong run_if_docker_up.sh phai chay duoc ngay ca khi
    Python/uv hong — goi Python de hoi ten container se bien mot loi Python
    thanh "Docker chet". Doi mot ban thi PHAI doi ban kia; da doi chieu
    07/09, ca hai cung cho ra `ai_auto_trading_system-postgres-1`.
    """
    if project_name is None:
        project_name = os.environ.get("COMPOSE_PROJECT_NAME")
    if not project_name:
        import re

        base = os.path.basename(REPO).lower()
        project_name = re.sub(r"[^a-z0-9_-]", "_", base)
    return f"{project_name}-{service}-1"


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

    images = {svc: _image_created_epoch(get_container_name(svc)) for svc in SERVICES}
    messages = drift_report(commit_epoch, images)

    if messages:
        return _alert(messages)
    _print_safe(
        "OK: không lệch triển khai — image của collector và engine mới hơn commit gần nhất chạm trading/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
