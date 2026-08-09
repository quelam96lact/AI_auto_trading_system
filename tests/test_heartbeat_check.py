from datetime import datetime, timedelta

from scripts.heartbeat_check import stale_services
from trading.calendar_vn import TZ

NOW = datetime(2026, 7, 15, 10, 0, tzinfo=TZ)


def test_no_stale_when_all_services_fresh():
    rows = [
        ("collector", NOW - timedelta(seconds=30)),
        ("engine", NOW - timedelta(seconds=45)),
    ]
    assert stale_services(rows, NOW, 300) == []


def test_service_past_max_age_is_stale():
    rows = [
        ("collector", NOW - timedelta(seconds=30)),
        ("engine", NOW - timedelta(seconds=600)),
    ]
    assert stale_services(rows, NOW, 300) == ["engine"]


def test_missing_service_row_is_stale():
    rows = [("collector", NOW - timedelta(seconds=30))]
    assert stale_services(rows, NOW, 300) == ["engine"]


def test_all_services_missing_are_stale():
    assert stale_services([], NOW, 300) == ["collector", "engine"]
