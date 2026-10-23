"""Module xu ly va thu thap du lieu giao dich khoi ngoai tu SSI DailyStockPrice.

Brief 190 (2026-10-23):
Nguon: ssi_fc_data MarketDataClient.daily_stock_price.
Luu tru: bang foreign_flow_daily.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ForeignFlow:
    """Dong du lieu giao dich khoi ngoai theo ngay cua mot ma co phieu."""

    symbol: str
    trading_date: date
    buy_vol: int
    sell_vol: int
    buy_val: float
    sell_val: float
    net_vol: int
    net_val: float
    current_room: int | None = None
    close_price: float | None = None
    ingested_at: datetime | None = None


def parse_daily_stock_price(
    resp: dict, allowed: set[str]
) -> tuple[list[ForeignFlow], dict[str, int]]:
    """Phan tich du lieu giao dich khoi ngoai tu response API SSI DailyStockPrice.

    Quy tac:
    - Loc theo universe trong `allowed`. Ma khong thuoc allowed -> tang not_in_universe.
    - Luu net_* dung nhu API tra ve, khong tu tinh lai.
    - Dong co net khac buy - sell: van luu, nhung tang net_mismatch.
    - Dong thieu truong hoac gia tri khong phai so: khong luu, tang bad_row.
    - Ngay doc theo dd/MM/yyyy.

    Tra ve:
        (flows, counters)
        counters: {"rows": ..., "kept": ..., "not_in_universe": ..., "bad_row": ..., "net_mismatch": ...}
    """
    counters = {
        "rows": 0,
        "kept": 0,
        "not_in_universe": 0,
        "bad_row": 0,
        "net_mismatch": 0,
    }
    data = resp.get("data") or []
    counters["rows"] = len(data)
    flows: list[ForeignFlow] = []

    for row in data:
        sym = row.get("Symbol")
        if not sym or sym not in allowed:
            counters["not_in_universe"] += 1
            continue

        date_str = row.get("TradingDate")
        buy_vol_str = row.get("ForeignBuyVolTotal")
        sell_vol_str = row.get("ForeignSellVolTotal")
        buy_val_str = row.get("ForeignBuyValTotal")
        sell_val_str = row.get("ForeignSellValTotal")
        net_vol_str = row.get("NetBuySellVol")
        net_val_str = row.get("NetBuySellVal")

        # Kiem tra cac truong bat buoc
        if (
            date_str is None
            or str(date_str).strip() == ""
            or buy_vol_str is None
            or str(buy_vol_str).strip() == ""
            or sell_vol_str is None
            or str(sell_vol_str).strip() == ""
            or buy_val_str is None
            or str(buy_val_str).strip() == ""
            or sell_val_str is None
            or str(sell_val_str).strip() == ""
            or net_vol_str is None
            or str(net_vol_str).strip() == ""
            or net_val_str is None
            or str(net_val_str).strip() == ""
        ):
            counters["bad_row"] += 1
            continue

        try:
            # Ngay doc theo dd/MM/yyyy (ngay truoc, thang sau)
            trading_date = datetime.strptime(str(date_str).strip(), "%d/%m/%Y").date()
            buy_vol = int(float(str(buy_vol_str).strip()))
            sell_vol = int(float(str(sell_vol_str).strip()))
            buy_val = float(str(buy_val_str).strip())
            sell_val = float(str(sell_val_str).strip())
            net_vol = int(float(str(net_vol_str).strip()))
            net_val = float(str(net_val_str).strip())
        except (ValueError, TypeError):
            counters["bad_row"] += 1
            continue

        # Kiem tra net mismatch (net khac buy - sell): van luu nhung dem
        if (
            net_vol != (buy_vol - sell_vol)
            or abs(net_val - (buy_val - sell_val)) > 1e-3
        ):
            counters["net_mismatch"] += 1

        # Cac truong tuy chon
        room_str = row.get("ForeignCurrentRoom")
        current_room: int | None = None
        if room_str is not None and str(room_str).strip() != "":
            try:
                current_room = int(float(str(room_str).strip()))
            except (ValueError, TypeError):
                current_room = None

        close_str = row.get("ClosePrice")
        close_price: float | None = None
        if close_str is not None and str(close_str).strip() != "":
            try:
                close_price = float(str(close_str).strip())
            except (ValueError, TypeError):
                close_price = None

        flow = ForeignFlow(
            symbol=str(sym),
            trading_date=trading_date,
            buy_vol=buy_vol,
            sell_vol=sell_vol,
            buy_val=buy_val,
            sell_val=sell_val,
            net_vol=net_vol,
            net_val=net_val,
            current_room=current_room,
            close_price=close_price,
        )
        flows.append(flow)
        counters["kept"] += 1

    return flows, counters


def _make_stock_price_req(
    symbol: str, date_str: str, page: int, page_size: int, market: str
):
    from ssi_fc_data.model import model

    return model.daily_stock_price(
        symbol=symbol,
        fromDate=date_str,
        toDate=date_str,
        pageIndex=page,
        pageSize=page_size,
        market=market,
    )


def _call_daily_stock_price(client, req):
    # Audit 23/10: goi dung chu ky SDK (None, req); bo nhanh bat TypeError
    # vi TypeError tu ben trong SDK se bi goi lai sai tham so va che loi that
    return client.daily_stock_price(None, req)


def fetch_day(
    client,
    d: date,
    markets: tuple[str, ...] = ("HOSE", "HNX", "UPCOM"),
    page_size: int = 1000,
    sleep: float | Callable[[], None] | None = None,
) -> tuple[list[dict], dict]:
    """Lay toan bo du lieu DailyStockPrice trong ngay `d` cho cac san trong `markets`.

    Phan trang toi khi du totalRecord cho tung san.
    Gap status loi la: thu lai 1 lan, lan hai van loi thi raise RuntimeError.
    NoDataFound o ca 3 san: khong co phien, tra danh sach rong khong raise.
    """

    def _do_sleep():
        if callable(sleep):
            sleep()
        elif isinstance(sleep, (int, float)) and sleep > 0:
            time.sleep(sleep)

    date_str = d.strftime("%d/%m/%Y")
    all_rows: list[dict] = []
    market_counts: dict[str, int] = {}

    for market in markets:
        market_rows: list[dict] = []
        page = 1
        while True:
            req = _make_stock_price_req("", date_str, page, page_size, market)

            resp = None
            last_err = None
            for attempt in range(2):
                try:
                    resp = _call_daily_stock_price(client, req) or {}
                    status = str(resp.get("status") or "")
                    msg = str(resp.get("message") or "")

                    if "NoDataFound" in status or "NoDataFound" in msg:
                        resp = {"status": "NoDataFound", "data": [], "totalRecord": 0}
                        last_err = None
                        break

                    # Check hop le
                    if status in ("Success", "200", "OK") or (
                        not status and "data" in resp
                    ):
                        last_err = None
                        break

                    last_err = RuntimeError(
                        f"SSI API error for {market} page {page}: status='{status}', message='{msg}'"
                    )
                except Exception as ex:
                    last_err = ex

                if attempt == 0:
                    _do_sleep()

            if resp is None or (
                last_err is not None
                and resp.get("status") not in ("Success", "200", "OK", "NoDataFound")
            ):
                if last_err is not None:
                    raise last_err
                raise RuntimeError(
                    f"SSI API failed after retry for {market} page {page}"
                )

            if resp.get("status") == "NoDataFound":
                break

            data = resp.get("data") or []
            market_rows.extend(data)
            all_rows.extend(data)

            total = int(resp.get("totalRecord") or 0)
            if not data or len(market_rows) >= total:
                break

            page += 1
            _do_sleep()

        market_counts[market] = len(market_rows)

    meta = {
        "date": d,
        "total_records": len(all_rows),
        "by_market": market_counts,
    }
    return all_rows, meta
