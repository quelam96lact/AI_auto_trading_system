import argparse
import asyncio
import logging
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

from trading.calendar_vn import TZ
from trading.config import Config, load_config
from trading.data_quality import is_dirty_bar
from trading.models import Bar
from trading.storage.db import Storage

logger = logging.getLogger("trading.collector.backfill")

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
    # Intraday: "YYYY/MM/DD HH:mm:ss" (xác nhận thật 2026-07-25, xem
    # tests/fixtures/ssi_sdk_ohlc_5m_vcb.json). Daily: chỉ "YYYY/MM/DD",
    # KHÔNG có giờ (xác nhận thật 2026-08-07, gọi trực tiếp API timeFrame=1d)
    # -> gán 00:00 giờ VN, giống quy ước daily cũ ở parse_daily_response.
    try:
        dt = datetime.strptime(s, "%Y/%m/%d %H:%M:%S")
    except ValueError:
        dt = datetime.strptime(s, "%Y/%m/%d")
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

    async def _reset_auth(self) -> None:
        """Đóng auth cũ và bỏ cache. Lỗi khi đóng KHÔNG được che mất lỗi gốc."""
        auth = getattr(self, "_auth", None)
        self._auth = None
        self._data = None
        if auth is not None:
            try:
                await auth.close()
            except Exception:
                pass  # lỗi đóng auth cũ không được nuốt mất lỗi gốc 401

    async def _fetch_with_reauth(self, data, method: str, *args, **kwargs):
        """Gọi 1 method market_data; gặp AuthenticationError (401/403 — cùng
        class trong ssi_sdk, xác minh rest_client.py:31-42) thì re-auth ĐÚNG
        MỘT LẦN rồi thử lại. Lần thứ hai lỗi thì để exception bay ra — nếu
        refresh_token hết hạn thì retry vô ích, phải fail to cho người vận
        hành biết (chạy OTP thủ công).

        Trả về (rows, data_moi): vòng lặp chunk PHẢI dùng data trả về này cho
        chunk tiếp theo — _reset_auth() đóng object cũ (auth.close()), giữ
        biến `data` cũ sẽ gọi HTTP client đã đóng (bug thật, Claude repro:
        RuntimeError 'Cannot send a request' ở chunk 2 sau 401 chunk 1)."""
        from ssi_sdk.exceptions import AuthenticationError

        try:
            rows = await getattr(data.market_data, method)(*args, **kwargs)
            return rows, data
        except AuthenticationError:
            await self._reset_auth()
            data = await self._ensure_data()
            rows = await getattr(data.market_data, method)(*args, **kwargs)
            logger.info(
                "re-authenticated after AuthenticationError, retrying %s", method
            )
            return rows, data

    async def close(self) -> None:
        if self._auth is not None:
            await self._auth.close()

    @staticmethod
    def _fmt_intraday(d: date, end_of_day: bool) -> str:
        # intraday/daily BẮT BUỘC có giờ (đã xác nhận thật — thiếu giờ bị lỗi
        # 400213 "Invalid Date/Timestamp", SDK bọc thành HTTP 500). Xác nhận
        # thật 2026-08-07: daily_ohlc cũng bị lỗi y hệt vì trước đó dùng
        # _fmt_day() (chỉ "%Y/%m/%d", thiếu giờ) — không phải lỗi riêng của
        # VCB như tưởng ban đầu, cả 3 mã (VCB/HPG/TCB) đều 500 trên daily.
        t = "23:59:59" if end_of_day else "00:00:00"
        return f"{d:%Y/%m/%d} {t}"

    async def daily_ohlc(self, symbol: str, frm: date, to: date) -> list[Bar]:
        data = await self._ensure_data()
        rows = await self._paged_daily(data, symbol, frm, to)
        return _ohlc_rows_to_bars(rows)

    async def _paged_daily(self, data, symbol: str, frm: date, to: date):
        """Chunk daily theo NĂM (366 ngày/chunk) — get_ohlc_1day_historical
        chặn 1000 dòng/call và trả CỬA SỔ MỚI NHẤT, mất âm thầm phần cũ.
        Đo thật 2026-08-09: gọi 10 năm 1 lần chỉ trả 2021-2025; chunk 1 năm
        trả đủ 2016=251/2018=248/2021=250 bar (dưới trần 1000)."""
        size = 1000
        by_ts: dict[str, object] = {}
        chunk_start = frm
        while chunk_start <= to:
            chunk_end = min(chunk_start + timedelta(days=365), to)
            rows, data = await self._fetch_with_reauth(
                data,
                "get_ohlc_1day_historical",
                symbol,
                self._fmt_intraday(chunk_start, end_of_day=False),
                self._fmt_intraday(chunk_end, end_of_day=True),
                page=1,
                size=size,
            )
            for r in rows:
                by_ts[r.trading_date] = r
            chunk_start = chunk_end + timedelta(days=1)
        return list(by_ts.values())

    async def intraday_ohlc(self, symbol: str, frm: date, to: date) -> list[Bar]:
        data = await self._ensure_data()
        rows = await self._paged_intraday(data, symbol, frm, to)
        return _ohlc_rows_to_bars(rows)

    async def _paged_intraday(self, data, symbol: str, frm: date, to: date):
        # `page` KHÔNG phải OFFSET cursor chuẩn (xác nhận thật, commit
        # 95f563f): gọi lại cùng khoảng frm..to với page tăng dần chủ yếu trả
        # lặp lại cửa sổ dữ liệu mới nhất thay vì tiến về dữ liệu cũ hơn, làm
        # mất dữ liệu cũ nhất một cách âm thầm. Thay bằng chunk theo ngày (7
        # ngày/chunk, luôn dưới `size`) + dedupe theo trading_date — cùng
        # pattern đã chứng minh đúng ở spike_ssi_sdk_derivative_ohlc_stream.py.
        size = 1000
        by_ts: dict[str, object] = {}
        chunk_start = frm
        while chunk_start <= to:
            chunk_end = min(chunk_start + timedelta(days=6), to)
            rows, data = await self._fetch_with_reauth(
                data,
                "get_ohlc_5minute_historical",
                symbol,
                self._fmt_intraday(chunk_start, end_of_day=False),
                self._fmt_intraday(chunk_end, end_of_day=True),
                page=1,
                size=size,
            )
            for r in rows:
                by_ts[r.trading_date] = r
            chunk_start = chunk_end + timedelta(days=1)
        return list(by_ts.values())


_DAILY_ONLY_LOOKBACK_DAYS = 10


async def run_backfill(
    storage, client, symbols: list[str], today: date, daily_only: bool = False
) -> dict[str, int]:
    """daily_only=True: CHI keo bar ngay, bo hoan toan intraday (MARGIN-2).

    Dung cho ma DANG NAM GIU nhung khong giao dich (CAP/HCM/SSI/TCX): NAV chi
    can gia dong cua, keo bar 5m cho chung la lang phi loi goi va ghi rac vao
    bang `bars`. Cua so co dinh _DAILY_ONLY_LOOKBACK_DAYS ngay thay vi
    `last_bar_ts` — ham do doc bang `bars` (5m), ma khong giao dich thi VINH
    VIEN None nen cua so 7 ngay cua nhanh cu chi dung do tinh co. Ghi bar la
    UPSERT (_UPSERT_BAR) nen keo trung ngay khong sinh dong thua.
    """
    from trading.alerts import alert

    counts: dict[str, int] = {}
    for sym in symbols:
        try:
            if daily_only:
                frm = today - timedelta(days=_DAILY_ONLY_LOOKBACK_DAYS)
                daily = await client.daily_ohlc(sym, frm, today)
                storage.write_daily(daily)
                counts[sym] = len(daily)
                continue
            last = storage.last_bar_ts(sym)
            frm = last.astimezone(TZ).date() if last else today - timedelta(days=7)
            intraday = [
                b
                for b in await client.intraday_ohlc(sym, frm, today)
                if last is None or b.ts > last
            ]
            # DIRTY-1b (brief dot 109): khong ghi nen rac (gia <= 0) vao `bars`.
            # Cung MOT luat voi duong stream: `data_quality.is_dirty_bar`.
            clean_intraday = [b for b in intraday if not is_dirty_bar(b)]
            rac = [b for b in intraday if is_dirty_bar(b)]
            if rac:
                alert(
                    "WARN",
                    f"backfill {sym}: bo {len(rac)} bar rac (co gia <= 0) khoi "
                    f"intraday truoc khi ghi",
                    symbol=sym,
                    so_bar_rac=len(rac),
                    ts_dau=rac[0].ts.isoformat(),
                    ts_cuoi=rac[-1].ts.isoformat(),
                )
            storage.write_bars(clean_intraday)
            storage.write_daily(await client.daily_ohlc(sym, frm, today))
            counts[sym] = len(clean_intraday)
        except Exception as e:
            alert(
                "WARN",
                "backfill failed for symbol, skipping",
                symbol=sym,
                error=str(e)[:100],
            )
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
