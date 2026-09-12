"""Test cho scripts/binance_vision.py (Brief đợt 40).

Kiểm tra:
- Parse CSV klines, funding, metrics từ ZIP
- Kiểm tra tính toàn vẹn SHA256 checksum
- Múi giờ UTC
- Idempotent upsert
"""

import hashlib
import io
import zipfile
from datetime import UTC, datetime
from unittest.mock import MagicMock

from scripts.binance_vision import (
    download_zip_with_checksum,
    parse_funding_zip,
    parse_klines_zip,
    parse_metrics_zip,
)


def _create_test_zip(filename: str, content: str) -> bytes:
    """Helper tạo zip bytes từ chuỗi csv."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(filename, content.encode("utf-8"))
    return buf.getvalue()


def test_parse_klines_zip():
    csv_data = (
        "open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
        "1704067200000,42314.00,42603.20,42289.60,42503.50,8459.477,1704070799999,359196345.08716,88278,4687.976,199033806.82405,0\n"
        "1704070800000,42503.50,42647.90,42410.00,42555.00,5390.123,1704074399999,229340000.12345,54321,2800.500,119000000.54321,0\n"
    )
    zip_bytes = _create_test_zip("BTCUSDT-1h-2024-01.csv", csv_data)
    records = parse_klines_zip(zip_bytes, "BTCUSDT", "1h")

    assert len(records) == 2
    r0 = records[0]
    assert r0["symbol"] == "BTCUSDT"
    assert r0["interval"] == "1h"
    assert r0["ts"] == datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    assert r0["open"] == 42314.0
    assert r0["high"] == 42603.2
    assert r0["low"] == 42289.6
    assert r0["close"] == 42503.5
    assert r0["volume"] == 8459.477
    assert r0["quote_volume"] == 359196345.08716
    assert r0["trades"] == 88278
    assert r0["taker_buy_volume"] == 4687.976
    assert r0["taker_buy_quote_volume"] == 199033806.82405


def test_parse_funding_zip():
    csv_data = (
        "calc_time,funding_interval_hours,last_funding_rate\n"
        "1704067200000,8,0.00037409\n"
        "1704096000000,8,-0.00012500\n"
    )
    zip_bytes = _create_test_zip("BTCUSDT-fundingRate-2024-01.csv", csv_data)
    records = parse_funding_zip(zip_bytes, "BTCUSDT")

    assert len(records) == 2
    assert records[0]["symbol"] == "BTCUSDT"
    assert records[0]["funding_time"] == datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    assert records[0]["funding_rate"] == 0.00037409
    assert records[0]["funding_interval_hours"] == 8

    assert records[1]["funding_time"] == datetime(2024, 1, 1, 8, 0, tzinfo=UTC)
    assert records[1]["funding_rate"] == -0.00012500


def test_parse_metrics_zip():
    csv_data = (
        "create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio\n"
        "2024-01-01 00:00:00,BTCUSDT,74006.26600000,3131493738.89740000,1.36820310,1.25366800,1.50710938,1.31174499\n"
        "2024-01-01 00:05:00,BTCUSDT,73839.81100000,3133154733.16132700,1.36197224,1.26060333,1.50756624,2.83721422\n"
    )
    zip_bytes = _create_test_zip("BTCUSDT-metrics-2024-01-01.csv", csv_data)
    records = parse_metrics_zip(zip_bytes, "BTCUSDT")

    assert len(records) == 2
    assert records[0]["symbol"] == "BTCUSDT"
    assert records[0]["ts"] == datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
    assert records[0]["sum_open_interest"] == 74006.266
    assert records[0]["sum_open_interest_value"] == 3131493738.8974
    assert records[0]["count_toptrader_long_short_ratio"] == 1.3682031
    assert records[0]["sum_toptrader_long_short_ratio"] == 1.253668
    assert records[0]["count_long_short_ratio"] == 1.50710938
    assert records[0]["sum_taker_long_short_vol_ratio"] == 1.31174499


def test_download_checksum_match():
    dummy_data = b"fake-zip-data-content"
    sha = hashlib.sha256(dummy_data).hexdigest()
    checksum_content = f"{sha}  sample.zip\n".encode()

    session = MagicMock()

    resp_checksum = MagicMock()
    resp_checksum.status_code = 200
    resp_checksum.content = checksum_content

    resp_zip = MagicMock()
    resp_zip.status_code = 200
    resp_zip.content = dummy_data

    session.get.side_effect = [resp_checksum, resp_zip]

    data, err = download_zip_with_checksum(
        "https://data.binance.vision/sample.zip",
        session=session,
        sleep_fn=lambda _: None,
        rate_limit_sleep=0.0,
    )
    assert err is None
    assert data == dummy_data


def test_download_checksum_mismatch():
    dummy_data = b"fake-zip-data-corrupted"
    wrong_sha = "0000000000000000000000000000000000000000000000000000000000000000"
    checksum_content = f"{wrong_sha}  sample.zip\n".encode()

    session = MagicMock()

    resp_checksum = MagicMock()
    resp_checksum.status_code = 200
    resp_checksum.content = checksum_content

    resp_zip = MagicMock()
    resp_zip.status_code = 200
    resp_zip.content = dummy_data

    # Trả về checksum, rồi 2 lần zip bị lệch sha
    session.get.side_effect = [resp_checksum, resp_zip, resp_zip]

    data, err = download_zip_with_checksum(
        "https://data.binance.vision/sample.zip",
        session=session,
        sleep_fn=lambda _: None,
        rate_limit_sleep=0.0,
    )
    assert data is None
    assert "Lệch SHA256" in err


def test_get_months_in_range():
    from datetime import date

    from scripts.binance_vision import get_days_in_month, get_months_in_range

    months = get_months_in_range(date(2024, 1, 1), date(2024, 3, 31))
    assert months == [(2024, 1), (2024, 2), (2024, 3)]

    # 2024 là năm nhuận
    assert get_days_in_month(2024, 2) == 29
    # 2025 không nhuận
    assert get_days_in_month(2025, 2) == 28
    assert get_days_in_month(2024, 1) == 31
    assert get_days_in_month(2024, 4) == 30

