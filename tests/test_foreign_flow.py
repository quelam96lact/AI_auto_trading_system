"""Unit tests cho parser, fetch_day va script backfill_foreign_flow.

Brief 190 (2026-10-23) cac buoc 3.1, 3.2, 3.3.
"""

from __future__ import annotations

import copy
import json
from datetime import date
from pathlib import Path

import pytest

import scripts.backfill_foreign_flow as bff_module
from trading.collector.foreign_flow import (
    ForeignFlow,
    fetch_day,
    parse_daily_stock_price,
)

FIXTURE_PATH = Path("tests/fixtures/ssi_daily_stock_price.json")


def _load_fixture() -> dict:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ============ 3.1: Parser tests ============


def test_parse_daily_stock_price_fixture_vcb_hpg():
    """3.1.1: Fixture voi allowed = {'VCB', 'HPG'}:
    - giu 2 dong, not_in_universe = 1 (E1VFVN30)
    - VCB co net_vol == -310798, buy_val == 9944021500.0, trading_date == date(2026, 10, 22).
    """
    fixture = _load_fixture()
    allowed = {"VCB", "HPG"}
    flows, counts = parse_daily_stock_price(fixture, allowed)

    assert counts["rows"] == 3
    assert counts["kept"] == 2
    assert counts["not_in_universe"] == 1
    assert counts["bad_row"] == 0
    assert counts["net_mismatch"] == 0

    sym_map = {f.symbol: f for f in flows}
    assert set(sym_map.keys()) == {"VCB", "HPG"}

    vcb = sym_map["VCB"]
    assert vcb.net_vol == -310798
    assert vcb.buy_val == 9944021500.0
    assert vcb.trading_date == date(2026, 10, 22)
    assert vcb.sell_vol == 486529
    assert vcb.buy_vol == 175731
    assert vcb.current_room == 845720541
    assert vcb.close_price == 56300.0


def test_parse_daily_stock_price_bad_symbol_rejected():
    """3.1.2: Chep mot dong fixture, doi Symbol thanh '0.8536:':
    dong bi loai vi khong thuoc universe (not_in_universe tang 1)."""
    fixture = _load_fixture()
    row = copy.deepcopy(fixture["data"][0])
    row["Symbol"] = "0.8536:"

    allowed = {"VCB", "HPG"}
    flows, counts = parse_daily_stock_price({"data": [row]}, allowed)

    assert len(flows) == 0
    assert counts["rows"] == 1
    assert counts["kept"] == 0
    assert counts["not_in_universe"] == 1
    assert counts["bad_row"] == 0


def test_parse_daily_stock_price_missing_field_bad_row():
    """3.1.3: Dong co ForeignBuyVolTotal = '' hoac None:
    bad_row tang 1, dong khong duoc luu."""
    allowed = {"VCB"}

    # Truong hop ForeignBuyVolTotal = ""
    row_empty = {
        "Symbol": "VCB",
        "TradingDate": "22/10/2026",
        "ForeignBuyVolTotal": "",
        "ForeignSellVolTotal": "100",
        "ForeignBuyValTotal": "1000",
        "ForeignSellValTotal": "2000",
        "NetBuySellVol": "-50",
        "NetBuySellVal": "-1000",
    }
    flows, counts = parse_daily_stock_price({"data": [row_empty]}, allowed)
    assert len(flows) == 0
    assert counts["bad_row"] == 1
    assert counts["kept"] == 0

    # Truong hop ForeignBuyVolTotal = None
    row_none = copy.deepcopy(row_empty)
    row_none["ForeignBuyVolTotal"] = None
    flows, counts = parse_daily_stock_price({"data": [row_none]}, allowed)
    assert len(flows) == 0
    assert counts["bad_row"] == 1
    assert counts["kept"] == 0


def test_parse_daily_stock_price_net_mismatch_kept_and_counted():
    """3.1.4: Dong tong hop co NetBuySellVol lech buy - sell: van giu, net_mismatch tang 1."""
    allowed = {"VCB"}
    row_mismatch = {
        "Symbol": "VCB",
        "TradingDate": "22/10/2026",
        "ForeignBuyVolTotal": "100",
        "ForeignSellVolTotal": "40",
        "ForeignBuyValTotal": "1000.0",
        "ForeignSellValTotal": "400.0",
        "NetBuySellVol": "999",  # lech: 100 - 40 = 60 != 999
        "NetBuySellVal": "600.0",
    }
    flows, counts = parse_daily_stock_price({"data": [row_mismatch]}, allowed)
    assert len(flows) == 1
    assert counts["kept"] == 1
    assert counts["net_mismatch"] == 1
    assert flows[0].net_vol == 999  # luu dung nhu API tra


def test_parse_daily_stock_price_trading_date_day_month_order():
    """3.1.5: Dong tong hop co TradingDate = '03/04/2026' phai cho ra date(2026, 4, 3) (ngay 3 thang 4)."""
    allowed = {"VCB"}
    row = {
        "Symbol": "VCB",
        "TradingDate": "03/04/2026",
        "ForeignBuyVolTotal": "10",
        "ForeignSellVolTotal": "5",
        "ForeignBuyValTotal": "100.0",
        "ForeignSellValTotal": "50.0",
        "NetBuySellVol": "5",
        "NetBuySellVal": "50.0",
    }
    flows, _counts = parse_daily_stock_price({"data": [row]}, allowed)
    assert len(flows) == 1
    assert flows[0].trading_date == date(2026, 4, 3)
    assert flows[0].trading_date.day == 3
    assert flows[0].trading_date.month == 4


# ============ 3.2: fetch_day tests ============


class FakeMarketDataClient:
    def __init__(self, responses_by_market_page):
        # responses_by_market_page: dict[(market, page)] -> resp dict or Exception
        self.responses = responses_by_market_page
        self.calls = []

    def daily_stock_price(self, _input_data, req):
        if hasattr(req, "market"):
            market = req.market
            page = req.pageIndex
        else:
            market = req.get("market")
            page = req.get("pageIndex")
        self.calls.append((market, page))
        resp = self.responses.get((market, page))
        if isinstance(resp, Exception):
            raise resp
        return resp


def test_fetch_day_pagination_called_page_3():
    """3.2.1: Client gia co totalRecord = 2645 cho HOSE, tra 1000/1000/645 dong:
    tong phai la 2645, va trang 3 phai duoc goi."""
    row = {"Symbol": "HPG", "TradingDate": "22/10/2026"}
    responses = {
        ("HOSE", 1): {
            "status": "Success",
            "totalRecord": 2645,
            "data": [row] * 1000,
        },
        ("HOSE", 2): {
            "status": "Success",
            "totalRecord": 2645,
            "data": [row] * 1000,
        },
        ("HOSE", 3): {
            "status": "Success",
            "totalRecord": 2645,
            "data": [row] * 645,
        },
    }
    client = FakeMarketDataClient(responses)
    rows, meta = fetch_day(client, date(2026, 10, 22), markets=("HOSE",), sleep=0)

    assert len(rows) == 2645
    assert meta["total_records"] == 2645
    assert ("HOSE", 3) in client.calls


def test_fetch_day_nodatafound_returns_empty():
    """3.2.2: NoDataFound o ca 3 san: tra danh sach rong, khong raise."""
    responses = {
        ("HOSE", 1): {"status": "NoDataFound", "data": [], "totalRecord": 0},
        ("HNX", 1): {"status": "NoDataFound", "data": [], "totalRecord": 0},
        ("UPCOM", 1): {"status": "NoDataFound", "data": [], "totalRecord": 0},
    }
    client = FakeMarketDataClient(responses)
    rows, meta = fetch_day(
        client, date(2026, 10, 25), markets=("HOSE", "HNX", "UPCOM"), sleep=0
    )

    assert rows == []
    assert meta["total_records"] == 0


def test_fetch_day_retry_success():
    """3.2.3: status loi mot lan roi thanh cong: ket qua du."""
    call_count = {"HOSE_p1": 0}

    class RetryClient:
        def __init__(self):
            self.calls = []

        def daily_stock_price(self, _input_data, req):
            self.calls.append(req)
            call_count["HOSE_p1"] += 1
            if call_count["HOSE_p1"] == 1:
                return {"status": "InternalError", "message": "Temporarily unavailable"}
            return {
                "status": "Success",
                "totalRecord": 1,
                "data": [{"Symbol": "VCB", "TradingDate": "22/10/2026"}],
            }

    client = RetryClient()
    rows, _meta = fetch_day(client, date(2026, 10, 22), markets=("HOSE",), sleep=0)
    assert len(rows) == 1
    assert len(client.calls) == 2  # Thu 2 lan


def test_fetch_day_retry_failure_raises():
    """3.2.4: Loi hai lan lien tiep: raise RuntimeError."""

    class FailingClient:
        def daily_stock_price(self, _input_data, req):
            return {"status": "Error", "message": "Persistent failure"}

    client = FailingClient()
    with pytest.raises(RuntimeError):
        fetch_day(client, date(2026, 10, 22), markets=("HOSE",), sleep=0)


def test_fetch_day_sleep_callable():
    """3.2.5: Tham so sleep truyen vao duoc (callable), test khong phai ngu that."""
    slept = []
    responses = {
        ("HOSE", 1): {
            "status": "Success",
            "totalRecord": 2,
            "data": [{"Symbol": "VCB"}],
        },
        ("HOSE", 2): {
            "status": "Success",
            "totalRecord": 2,
            "data": [{"Symbol": "HPG"}],
        },
    }
    client = FakeMarketDataClient(responses)
    fetch_day(
        client,
        date(2026, 10, 22),
        markets=("HOSE",),
        page_size=1,
        sleep=lambda: slept.append(1),
    )
    assert len(slept) > 0


# ============ 3.3: Backfill CLI tests ============


class FakeStorage:
    def __init__(self, allowed_symbols):
        self._allowed = set(allowed_symbols)
        self.written_flows = []

    def read_symbol_universe(self) -> set[str]:
        return self._allowed

    def write_foreign_flow(self, flows: list[ForeignFlow]) -> int:
        self.written_flows.extend(flows)
        return len(flows)


def test_backfill_foreign_flow_main_success(capsys):
    """3.3.1: main() chay voi client gia va storage gia tren 3 ngay (1 ngay NoDataFound):
    ma thoat 0, storage nhan dung 2 ngay du lieu."""
    # 2026-10-21 (Wed): co phien
    # 2026-10-22 (Thu): NoDataFound (no_session)
    # 2026-10-23 (Fri): co phien
    d1 = date(2026, 10, 21)
    d3 = date(2026, 10, 23)

    row1 = {
        "Symbol": "VCB",
        "TradingDate": "21/10/2026",
        "ForeignBuyVolTotal": "100",
        "ForeignSellVolTotal": "50",
        "ForeignBuyValTotal": "1000",
        "ForeignSellValTotal": "500",
        "NetBuySellVol": "50",
        "NetBuySellVal": "500",
    }
    row3 = {
        "Symbol": "VCB",
        "TradingDate": "23/10/2026",
        "ForeignBuyVolTotal": "200",
        "ForeignSellVolTotal": "100",
        "ForeignBuyValTotal": "2000",
        "ForeignSellValTotal": "1000",
        "NetBuySellVol": "100",
        "NetBuySellVal": "1000",
    }

    class MultiDayClient:
        def daily_stock_price(self, _input_data, req):
            market = req.market if hasattr(req, "market") else req.get("market")
            if market != "HOSE":
                return {"status": "NoDataFound", "totalRecord": 0, "data": []}
            d_str = req.fromDate if hasattr(req, "fromDate") else req.get("fromDate")
            if d_str == "21/10/2026":
                return {"status": "Success", "totalRecord": 1, "data": [row1]}
            elif d_str == "22/10/2026":
                return {"status": "NoDataFound", "totalRecord": 0, "data": []}
            elif d_str == "23/10/2026":
                return {"status": "Success", "totalRecord": 1, "data": [row3]}
            return {"status": "NoDataFound", "totalRecord": 0, "data": []}

    storage = FakeStorage(["VCB"])
    client = MultiDayClient()

    args = [
        "--from",
        "2026-10-21",
        "--to",
        "2026-10-23",
        "--sleep",
        "0",
    ]
    code = bff_module.main(args, client=client, storage=storage)
    assert code == 0
    assert len(storage.written_flows) == 2
    dates = {f.trading_date for f in storage.written_flows}
    assert dates == {d1, d3}

    captured = capsys.readouterr()
    assert "2026-10-22 no_session" in captured.out
    assert "last_done=2026-10-23" in captured.out


def test_backfill_foreign_flow_main_api_error_exit_2(capsys):
    """3.3.2: Client gia loi o ngay thu 2: ma thoat 2 va in last_done bang ngay 1."""
    d1_row = {
        "Symbol": "VCB",
        "TradingDate": "21/10/2026",
        "ForeignBuyVolTotal": "100",
        "ForeignSellVolTotal": "50",
        "ForeignBuyValTotal": "1000",
        "ForeignSellValTotal": "500",
        "NetBuySellVol": "50",
        "NetBuySellVal": "500",
    }

    class FailingDay2Client:
        def daily_stock_price(self, _input_data, req):
            market = req.market if hasattr(req, "market") else req.get("market")
            d_str = req.fromDate if hasattr(req, "fromDate") else req.get("fromDate")
            if d_str == "21/10/2026":
                if market == "HOSE":
                    return {"status": "Success", "totalRecord": 1, "data": [d1_row]}
                return {"status": "NoDataFound", "totalRecord": 0, "data": []}
            else:
                return {"status": "InternalError", "message": "Server Error"}

    storage = FakeStorage(["VCB"])
    client = FailingDay2Client()

    args = [
        "--from",
        "2026-10-21",
        "--to",
        "2026-10-22",
        "--sleep",
        "0",
    ]
    code = bff_module.main(args, client=client, storage=storage)
    assert code == 2
    assert len(storage.written_flows) == 1

    captured = capsys.readouterr()
    assert "last_done=2026-10-21" in captured.out


def test_backfill_foreign_flow_main_loads_real_config_path(monkeypatch):
    """Audit 24/10: nhanh khong tiem storage phai nap config bang load_config
    va tao Storage tu cfg.db_dsn (truoc day goi Config.from_yaml khong ton tai)."""
    seen = {}

    class _Cfg:
        db_dsn = "postgresql://gia"

    def fake_load_config(path):
        seen["path"] = path
        return _Cfg()

    def fake_storage(dsn):
        seen["dsn"] = dsn
        return FakeStorage([])

    monkeypatch.setattr(bff_module, "load_config", fake_load_config)
    monkeypatch.setattr(bff_module, "Storage", fake_storage)

    code = bff_module.main(["--from", "2026-10-21", "--to", "2026-10-21"])
    assert code == 3  # universe rong -> dung truoc khi tao client that
    assert seen == {"path": "config/config.yaml", "dsn": "postgresql://gia"}


def test_backfill_foreign_flow_main_empty_universe_exit_3(capsys):
    """3.3.3: symbol_universe rong: ma thoat 3."""
    storage = FakeStorage([])  # rong
    client = FakeMarketDataClient({})

    args = [
        "--from",
        "2026-10-21",
        "--to",
        "2026-10-21",
        "--sleep",
        "0",
    ]
    code = bff_module.main(args, client=client, storage=storage)
    assert code == 3
    captured = capsys.readouterr()
    assert "symbol_universe is empty" in captured.err
