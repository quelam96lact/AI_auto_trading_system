"""Unit tests cho scripts/measure_octopus_5m_universe.py (Brief đợt 11 - Task 1).

Kiểm chứng các bất biến bắt buộc:
1. get_universe_symbols truy vấn trực tiếp từ bảng bars, KHÔNG đọc config.yaml.
2. Không áp dụng exclusions.txt.
3. Dùng lại measure_symbol_5m từ scripts.measure_octopus_5m.
"""

from unittest.mock import MagicMock

from scripts.measure_octopus_5m_universe import get_universe_symbols


def test_get_universe_symbols_queries_bars_table():
    """get_universe_symbols phải truy vấn SELECT DISTINCT symbol FROM bars ORDER BY symbol."""
    mock_storage = MagicMock()
    mock_conn = MagicMock()

    mock_storage.conn.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.fetchall.return_value = [("AAA",), ("HII",), ("IJC",), ("VCB",)]

    symbols = get_universe_symbols(mock_storage)

    assert symbols == ["AAA", "HII", "IJC", "VCB"]
    mock_conn.execute.assert_called_once_with("SELECT DISTINCT symbol FROM bars ORDER BY symbol")


def test_measure_universe_does_not_read_config_yaml(monkeypatch):
    """Chứng minh script không đọc config/config.yaml để lấy rổ mã khảo sát toàn rổ."""
    from scripts import measure_octopus_5m_universe as mod

    mock_storage = MagicMock()
    mock_conn = MagicMock()
    mock_storage.conn.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.fetchall.return_value = [("AAA",), ("IJC",)]

    # Mock resolve_dsn and Storage
    monkeypatch.setattr(mod, "resolve_dsn", lambda dsn: "postgresql://mock")
    monkeypatch.setattr(mod, "Storage", lambda dsn: mock_storage)

    # Mock measure_symbol_5m
    mock_measure = MagicMock(return_value={
        "symbol": "AAA",
        "n_bars": 100,
        "trades": 0,
        "winning_trades": 0,
        "win_rate": 0.0,
        "strat_pnl": 0.0,
        "bh_pnl": 0.0,
        "diff": 0.0,
        "trade_pnls": [],
        "daily_pnl": {},
        "max_drawdown": 0.0,
    })
    monkeypatch.setattr(mod, "measure_symbol_5m", mock_measure)

    # Đảm bảo hàm open không bao giờ được gọi với config.yaml
    real_open = open

    def guarded_open(file, *args, **kwargs):
        filename = str(file)
        if "config.yaml" in filename or "exclusions.txt" in filename:
            raise AssertionError(f"Script vi phạm: CẤM đọc {filename} để lấy rổ mã!")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", guarded_open)

    # Chạy main với argv rỗng (mặc định lấy toàn rổ)
    monkeypatch.setattr("sys.argv", ["measure_octopus_5m_universe.py"])
    rc = mod.main()

    assert rc == 0
    assert mock_measure.call_count == 2
    mock_conn.execute.assert_called_once_with("SELECT DISTINCT symbol FROM bars ORDER BY symbol")


def test_measure_universe_does_not_apply_exclusions_txt():
    """Kiểm tra mã nguồn của script mới tuyệt đối không tải hay lọc exclusions.txt."""
    import ast
    from pathlib import Path

    script_path = Path(__file__).parent.parent / "scripts" / "measure_octopus_5m_universe.py"
    tree = ast.parse(script_path.read_text(encoding="utf-8"))

    # Kiểm tra tất cả string literals trong AST ngoài docstrings
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val = node.value.lower()
            assert "exclusions.txt" not in val or "không áp" in val or "tuyệt đối không" in val
