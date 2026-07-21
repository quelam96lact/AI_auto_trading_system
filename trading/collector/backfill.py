import argparse
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


class SSIRestClient:
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


def run_backfill(storage, client, symbols: list[str], today: date) -> dict[str, int]:
    counts: dict[str, int] = {}
    try:
        for sym in symbols:
            last = storage.last_bar_ts(sym)
            frm = last.astimezone(TZ).date() if last else today - timedelta(days=7)
            intraday = [
                b
                for b in client.intraday_ohlc(sym, frm, today)
                if last is None or b.ts > last
            ]
            storage.write_bars(intraday)
            storage.write_daily(client.daily_ohlc(sym, frm, today))
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
    counts = run_backfill(
        storage, SSIRestClient(cfg), cfg.symbols, datetime.now(TZ).date()
    )
    print(counts)


if __name__ == "__main__":
    main()
