"""Kiểm tra cấu hình init: true trong docker-compose.yml (Brief đợt 221).

Lý do: ngày 09/11 khi deploy đợt 218, container kẹt lỗi zombie vì PID 1 là python
không bắt SIGTERM và không dọn tiến trình con mồ côi. init: true cho Docker dùng
docker-init (tini) làm PID 1 để chuyển tiếp tín hiệu và dọn zombie.
"""

from pathlib import Path

import yaml


def _load_compose() -> dict:
    compose_path = Path(__file__).resolve().parent.parent / "docker-compose.yml"
    with open(compose_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_core_services_have_init_true():
    """Ba service engine, collector, scheduler phải có init: True."""
    data = _load_compose()
    services = data.get("services", {})

    for name in ("engine", "collector", "scheduler"):
        assert name in services, f"Service {name} không có trong docker-compose.yml"
        assert (
            services[name].get("init") is True
        ), f"Service {name} phải có init: True, thực tế: {services[name].get('init')}"


def test_other_services_do_not_have_init():
    """Chặn sửa tràn: postgres, nats, grafana không được có khoá init."""
    data = _load_compose()
    services = data.get("services", {})

    for name in ("postgres", "nats", "grafana"):
        assert name in services, f"Service {name} không có trong docker-compose.yml"
        assert (
            "init" not in services[name]
        ), f"Service {name} không được có khoá init, thực tế có: {services[name].get('init')}"
