"""Tests for crypto data seal enforcement (Brief đợt 121 Task C).

Verifies that:
1. CRYPTO_SEALED_MAX_TS is defined and equals '2026-08-31 23:59:59+00'.
2. read_crypto_bars unconditionally enforces the seal when to_date is None.
3. read_crypto_bars does NOT allow to_date to expand beyond the seal.
4. Earlier to_date takes precedence over the seal.
5. All 4 SQL-direct scripts enforce the seal via parameterized query.
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from scripts.seal import CRYPTO_SEALED_MAX_TS


def test_crypto_sealed_max_ts_value():
    """CRYPTO_SEALED_MAX_TS phai dung 2026-08-31 23:59:59+00."""
    assert CRYPTO_SEALED_MAX_TS == "2026-08-31 23:59:59+00"


def test_read_crypto_bars_unconditional_seal_when_to_date_none():
    """Task C: to_date=None van phai ap CRYPTO_SEALED_MAX_TS vao query va params."""
    from scripts.measure_crypto_strategies import read_crypto_bars

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    read_crypto_bars(mock_conn, interval="1d", to_date=None)

    assert mock_cursor.execute.called
    query, params = mock_cursor.execute.call_args[0]
    assert "ts <= %s" in query, f"Query phai co chan ts <= %s, thuc te: {query}"
    assert params[-1] == CRYPTO_SEALED_MAX_TS, f"Param cuoi phai la moc seal, thuc te: {params[-1]}"


def test_read_crypto_bars_to_date_cannot_expand_past_seal():
    """Task C (Pha thu 5): to_date sau moc niem phong KHONG DUOC mo rong moc.

    Neu ai do dung `to_date or MOC` thay vi `min`, to_date='2026-09-15' se
    ghi de moc seal va lam test nay RED.
    """
    from scripts.measure_crypto_strategies import read_crypto_bars

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    # Truyen to_date vuot qua moc seal
    future_to = "2026-09-15 00:00:00+00"
    read_crypto_bars(mock_conn, interval="1d", to_date=future_to)

    query, params = mock_cursor.execute.call_args[0]
    assert query.count("ts <= %s") == 2, f"Phai co HAI chan tren (moc + to_date), thuc te: {query}"
    assert CRYPTO_SEALED_MAX_TS in params, (
        f"to_date vuot moc ({future_to}) khong duoc THAY THE moc seal; "
        f"moc phai van nam trong params, thuc te: {params}"
    )


def test_read_crypto_bars_earlier_to_date_wins():
    """Task C: to_date som hon moc seal thi moc som hon thang (thu hep)."""
    from scripts.measure_crypto_strategies import read_crypto_bars

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    earlier_to = "2026-08-15 00:00:00+00"
    read_crypto_bars(mock_conn, interval="1d", to_date=earlier_to)

    query, params = mock_cursor.execute.call_args[0]
    # Hai dieu kien AND: Postgres tu lay cai CHAT hon, nen to_date som hon thang.
    assert query.count("ts <= %s") == 2
    assert earlier_to in params, f"to_date som hon ({earlier_to}) phai co trong params, thuc te: {params}"
    assert CRYPTO_SEALED_MAX_TS in params, f"Moc seal van phai co mat, thuc te: {params}"


def test_read_crypto_bars_seal_kept_for_negative_offset_datetime():
    """Audit dot 121: to_date kieu datetime mui gio am KHONG duoc lam mat moc.

    datetime(2026, 8, 31, 23, 0, UTC-5) = 04:00 UTC ngay 01/09, da VUOT moc.
    Ban dau dung min(str(to_date), MOC): theo thu tu CHU "2026-08-31 23:00:00-05:00"
    nho hon "2026-08-31 23:59:59+00" nen min chon to_date, va 5 nen holdout
    BTC-USDT 1h (00:00-04:00 UTC 01/09) lot qua tren DB that. Moc phai LUON
    duoc truyen xuong SQL de Postgres so sanh theo kieu timestamptz.
    """
    from datetime import timedelta, timezone

    from scripts.measure_crypto_strategies import read_crypto_bars

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.fetchall.return_value = []

    to_tz_am = datetime(2026, 8, 31, 23, 0, tzinfo=timezone(timedelta(hours=-5)))
    read_crypto_bars(mock_conn, interval="1h", to_date=to_tz_am)

    query, params = mock_cursor.execute.call_args[0]
    assert CRYPTO_SEALED_MAX_TS in params, (
        f"to_date {to_tz_am} (= 04:00 UTC 01/09) da lam mat moc seal: {params}"
    )
    assert query.count("ts <= %s") == 2


def test_read_crypto_bars_parses_valid_row():
    """read_crypto_bars parse duoc mot dong hop le.

    Ten cu (`..._filters_out_holdout_rows_when_mocked`) noi test nay loc dong
    holdout, nhung mock chi tra MOT dong hop le nen khong loc gi - va voi mock
    thi khong the kiem viec loc, vi viec loc do Postgres lam. Viec loc that duoc
    kiem bang tham so SQL o cac test tren.
    """
    from scripts.measure_crypto_strategies import read_crypto_bars

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    ts_valid = datetime(2026, 8, 31, 23, 0, tzinfo=UTC)
    mock_cursor.fetchall.return_value = [
        ("BTC-USDT", ts_valid, 60000.0, 60500.0, 59900.0, 60200.0, 100.0),
    ]

    bars = read_crypto_bars(mock_conn, interval="1h")
    assert "BTC-USDT" in bars
    assert len(bars["BTC-USDT"]) == 1
    assert bars["BTC-USDT"][0].ts <= datetime(2026, 8, 31, 23, 59, 59, tzinfo=UTC)


# ============ Kiem tra 4 script SQL truc tiep (Pha thu 6) ============


def test_candlestick_strategies_sql_enforces_seal():
    """scripts/measure_candlestick_strategies.py phai import va ap dung CRYPTO_SEALED_MAX_TS o ca 2 query 1d va 1h."""
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "measure_candlestick_strategies.py"
    content = script_path.read_text(encoding="utf-8")

    assert "CRYPTO_SEALED_MAX_TS" in content
    # Count occurrences of 'AND ts <= %s' in crypto queries
    assert content.count("AND ts <= %s") == 2, (
        "measure_candlestick_strategies.py: phai co dung 2 query chua 'AND ts <= %s' (1d va 1h)"
    )
    assert content.count("(CRYPTO_SEALED_MAX_TS,)") == 2


def test_candlestick_patterns_sql_enforces_seal():
    """scripts/measure_candlestick_patterns.py phai import va ap dung CRYPTO_SEALED_MAX_TS o ca 2 query 1d va 1h."""
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "measure_candlestick_patterns.py"
    content = script_path.read_text(encoding="utf-8")

    assert "CRYPTO_SEALED_MAX_TS" in content
    assert content.count("AND ts <= %s") == 2, (
        "measure_candlestick_patterns.py: phai co dung 2 query chua 'AND ts <= %s' (1d va 1h)"
    )
    assert content.count("(CRYPTO_SEALED_MAX_TS,)") == 2


def test_octopus_combo_hybrid_sql_enforces_seal():
    """scripts/measure_octopus_combo_hybrid.py phai import va ap dung CRYPTO_SEALED_MAX_TS o ca 2 query 1d va 1h."""
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "measure_octopus_combo_hybrid.py"
    content = script_path.read_text(encoding="utf-8")

    assert "CRYPTO_SEALED_MAX_TS" in content
    assert content.count("AND ts <= %s") == 2, (
        "measure_octopus_combo_hybrid.py: phai co dung 2 query chua 'AND ts <= %s' (1d va 1h)"
    )
    assert content.count("(CRYPTO_SEALED_MAX_TS,)") == 2


def test_optimize_octopus_combo_hybrid_sql_enforces_seal():
    """scripts/optimize_octopus_combo_hybrid.py phai import va ap dung CRYPTO_SEALED_MAX_TS."""
    script_path = Path(__file__).resolve().parent.parent / "scripts" / "optimize_octopus_combo_hybrid.py"
    content = script_path.read_text(encoding="utf-8")

    assert "CRYPTO_SEALED_MAX_TS" in content
    assert "AND ts <= %s" in content, "optimize_octopus_combo_hybrid.py: query thieu 'AND ts <= %s'"
    assert "(CRYPTO_SEALED_MAX_TS,)" in content
