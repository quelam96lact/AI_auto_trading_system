import argparse
import asyncio
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from trading.calendar_vn import TZ
from trading.config import Config, load_config
from trading.models import Bar
from trading.storage.db import Storage

_PAGE_SIZE = 100  # xác minh findings Task 6: page trả đúng pageSize record
_MAX_RANGE_DAYS = 30  # xác minh findings Task 6: API giới hạn range 30 ngày/call


def parse_intraday_response(raw: dict) -> list[Bar]:
    """Chuẩn hóa response intraday thành Bar 5m.
    API trả bar 1m (resolution=1, findings Task 6): gom theo bucket 5m
    (open đầu, high max, low min, close cuối, volume tổng)."""
    rows = raw.get("data") or raw.get("Data") or []
    by_bucket: dict[tuple, list] = defaultdict(list)
    out: list[Bar] = []
    for r in rows:
        # field names theo findings Task 6: Symbol, TradingDate, Time, Open..Volume (PascalCase)
        sym = r.get("Symbol") or r.get("symbol")
        ts = _row_ts(r)  # ghép TradingDate + Time, gán TZ
        bucket = ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)
        by_bucket[(sym, bucket)].append((ts, r))
    for (sym, bucket), items in sorted(by_bucket.items(), key=lambda kv: kv[0]):
        items.sort(key=lambda x: x[0])
        opens = float(_f(items[0][1], "Open"))
        closes = float(_f(items[-1][1], "Close"))
        highs = max(float(_f(r, "High")) for _, r in items)
        lows = min(float(_f(r, "Low")) for _, r in items)
        vol = sum(int(float(_f(r, "Volume") or 0)) for _, r in items)
        out.append(Bar(sym, bucket, opens, highs, lows, closes, vol))
    return out


def parse_daily_response(raw: dict) -> list[Bar]:
    """Chuẩn hóa response daily (Time=null → ts = 00:00 ngày giao dịch, findings Task 6)."""
    rows = raw.get("data") or raw.get("Data") or []
    out: list[Bar] = []
    for r in rows:
        sym = r.get("Symbol") or r.get("symbol")
        out.append(
            Bar(
                sym,
                _row_ts(r),
                float(_f(r, "Open")),
                float(_f(r, "High")),
                float(_f(r, "Low")),
                float(_f(r, "Close")),
                int(float(_f(r, "Volume") or 0)),
            )
        )
    out.sort(key=lambda b: b.ts)
    return out


def _f(row: dict, name: str):
    return row.get(name) or row.get(name.lower())


def _row_ts(row: dict) -> datetime:
    """TradingDate 'dd/MM/yyyy' + Time 'HH:MM:SS' (null ở daily) → tz-aware VN (findings Task 6)."""
    d = _f(row, "TradingDate")
    day = datetime.strptime(str(d), "%d/%m/%Y").date()
    t = _f(row, "Time")
    if not t:
        return datetime(day.year, day.month, day.day, tzinfo=TZ)
    tt = datetime.strptime(str(t), "%H:%M:%S").time()
    return datetime(
        day.year, day.month, day.day, tt.hour, tt.minute, tt.second, tzinfo=TZ
    )


class SSIRestClientLegacy:
    """Client SDK cũ (ssi_fc_data) — giữ làm rollback reference (PLAN mục 7).

    Không còn ai gọi sau Phase 2 (main.py đã chuyển sang SSIRestClient mới).
    KHÔNG xoá tới khi Phase 4 E2E ổn định ≥2 phiên."""

    def __init__(self, cfg: Config):
        from ssi_fc_data.fc_md_client import MarketDataClient  # findings Task 6
        from ssi_fc_data.model import model

        class _SdkCfg:
            auth_type = "Bearer"
            consumerID = cfg.ssi_consumer_id
            consumerSecret = cfg.ssi_consumer_secret
            url = "https://fc-data.ssi.com.vn/"
            stream_url = "https://fc-datahub.ssi.com.vn/"

        self._model = model
        self._client = MarketDataClient(_SdkCfg())

    @staticmethod
    def _fmt(d: date) -> str:
        return d.strftime("%d/%m/%Y")  # findings Task 6: dd/MM/yyyy

    def _paged_rows(self, call, make_req, frm: date, to: date) -> list[dict]:
        """Gọi API theo chunk ≤30 ngày, loop pageIndex tới đủ totalRecord; throttle 0.25s/call."""
        rows: list[dict] = []
        chunk_start = frm
        while chunk_start <= to:
            chunk_end = min(chunk_start + timedelta(days=_MAX_RANGE_DAYS - 1), to)
            got, page = 0, 1
            while True:
                time.sleep(0.25)  # throttle giữa các call
                resp = call(None, make_req(chunk_start, chunk_end, page)) or {}
                data = resp.get("data") or []
                rows.extend(data)
                got += len(data)
                total = int(resp.get("totalRecord") or 0)
                if not data or got >= total:
                    break
                page += 1
            chunk_start = chunk_end + timedelta(days=1)
        return rows

    def daily_ohlc(self, symbol: str, frm: date, to: date) -> list[Bar]:
        rows = self._paged_rows(
            self._client.daily_ohlc,
            lambda s, e, p: self._model.daily_ohlc(
                symbol=symbol,
                fromDate=self._fmt(s),
                toDate=self._fmt(e),
                pageIndex=p,
                pageSize=_PAGE_SIZE,
                ascending=True,
            ),
            frm,
            to,
        )
        return parse_daily_response({"data": rows})

    def intraday_ohlc(self, symbol: str, frm: date, to: date) -> list[Bar]:
        # Gom raw rows của MỌI page/chunk rồi mới bucket 5m một lần — tránh bar lửng ở biên page.
        rows = self._paged_rows(
            self._client.intraday_ohlc,
            lambda s, e, p: self._model.intraday_ohlc(
                symbol=symbol,
                fromDate=self._fmt(s),
                toDate=self._fmt(e),
                pageIndex=p,
                pageSize=_PAGE_SIZE,
                ascending=True,
                resolution=1,
            ),
            frm,
            to,
        )
        return parse_intraday_response({"data": rows})


def _parse_trading_date(s: str) -> datetime:
    # Xác nhận thật 2026-07-25: "YYYY/MM/DD HH:mm:ss" (xem
    # tests/fixtures/ssi_sdk_ohlc_5m_vcb.json), gán TZ VN.
    dt = datetime.strptime(s, "%Y/%m/%d %H:%M:%S")
    return dt.replace(tzinfo=TZ)


def _ohlc_rows_to_bars(rows) -> list[Bar]:
    """Map list[OHLCData] (ssi-sdk mới) → list[Bar], sort theo ts.

    KHÔNG dùng lại parse_intraday_response/parse_daily_response — field và
    format khác hẳn (OHLCData đã parse sẵn, trading_date có cả giờ)."""
    out = [
        Bar(
            r.symbol,
            _parse_trading_date(r.trading_date),
            float(r.open_price),
            float(r.high_price),
            float(r.low_price),
            float(r.close_price),
            int(r.volume),
        )
        for r in rows
    ]
    out.sort(key=lambda b: b.ts)
    return out


class SSIRestClient:
    """Client REST mới dùng ssi-sdk (AsyncData). Auth lazy qua ensure_authenticated:

    refresh_token trong bảng ssi_auth_state → refresh() không cần OTP.
    Caller phải `await client.close()` sau khi dùng xong."""

    def __init__(self, cfg: Config, storage: Storage):
        self._cfg = cfg
        self._storage = storage
        self._auth = None  # AsyncAuth, lazy — xem _ensure_data()
        self._data = None  # AsyncData, lazy

    async def _ensure_data(self):
        if self._data is None:
            from ssi_sdk import AsyncData

            from trading.collector.ssi_auth import ensure_authenticated

            self._auth = await ensure_authenticated(self._cfg, self._storage)
            self._data = AsyncData(self._auth)
        return self._data

    async def close(self) -> None:
        if self._auth is not None:
            await self._auth.close()

    @staticmethod
    def _fmt_day(d: date) -> str:
        return d.strftime("%Y/%m/%d")

    @staticmethod
    def _fmt_intraday(d: date, end_of_day: bool) -> str:
        # intraday BẮT BUỘC có giờ (đã xác nhận thật — thiếu giờ bị lỗi
        # 400213 "Invalid Date/Timestamp")
        t = "23:59:59" if end_of_day else "00:00:00"
        return f"{d:%Y/%m/%d} {t}"

    async def daily_ohlc(self, symbol: str, frm: date, to: date) -> list[Bar]:
        data = await self._ensure_data()
        rows = await data.market_data.get_ohlc_1day_historical(  # tên xác nhận Task 1.2
            symbol, self._fmt_day(frm), self._fmt_day(to)
        )
        return _ohlc_rows_to_bars(rows)

    async def intraday_ohlc(self, symbol: str, frm: date, to: date) -> list[Bar]:
        data = await self._ensure_data()
        rows = await self._paged_intraday(data, symbol, frm, to)
        return _ohlc_rows_to_bars(rows)

    async def _paged_intraday(self, data, symbol: str, frm: date, to: date):
        # Response KHÔNG expose totalRecord (khác SDK cũ) — heuristic: nếu
        # trang trả đủ `size` dòng thì có thể còn trang sau, gọi tiếp;
        # nếu trả ít hơn `size` thì chắc chắn hết.
        size = 1000
        all_rows, page = [], 1
        while True:
            rows = await data.market_data.get_ohlc_5minute_historical(
                symbol,
                self._fmt_intraday(frm, end_of_day=False),
                self._fmt_intraday(to, end_of_day=True),
                page=page,
                size=size,
            )
            all_rows.extend(rows)
            if len(rows) < size:
                break
            page += 1
        return all_rows


async def run_backfill(storage, client, symbols: list[str], today: date) -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        for sym in symbols:
            last = storage.last_bar_ts(sym)
            frm = last.astimezone(TZ).date() if last else today - timedelta(days=7)
            intraday = [
                b
                for b in await client.intraday_ohlc(sym, frm, today)
                if last is None or b.ts > last
            ]
            storage.write_bars(intraday)
            storage.write_daily(await client.daily_ohlc(sym, frm, today))
            counts[sym] = len(intraday)
    except Exception as e:
        from trading.alerts import alert

        alert("WARN", "backfill failed, skipping", error=str(e)[:100])
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()
    cfg = load_config(args.config)
    storage = Storage(cfg.db_dsn)
    storage.init_schema()

    async def _run():
        client = SSIRestClient(cfg, storage)
        try:
            counts = await run_backfill(
                storage, client, cfg.symbols, datetime.now(TZ).date()
            )
        finally:
            await client.close()
        print(counts)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
