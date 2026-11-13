"""Bar, daily, derivative, timeframe, foreign-flow, and completeness storage mixin."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from trading.calendar_vn import TZ
from trading.collector.foreign_flow import ForeignFlow
from trading.models import Bar, IndexValue

_UPSERT_BAR = """
INSERT INTO {table} (symbol, ts, open, high, low, close, volume, source)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (symbol, ts) DO UPDATE SET
  open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
  close = EXCLUDED.close, volume = EXCLUDED.volume, source = EXCLUDED.source
"""

_UPSERT_TF_BAR = """
INSERT INTO bars_derivative_tf (symbol, interval, ts, open, high, low, close, volume, source)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (symbol, interval, ts) DO UPDATE SET
  open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
  close = EXCLUDED.close, volume = EXCLUDED.volume, source = EXCLUDED.source
"""

_UPSERT_STOCK_TF_BAR = """
INSERT INTO bars_tf (symbol, interval, ts, open, high, low, close, volume, source)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (symbol, interval, ts) DO UPDATE SET
  open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
  close = EXCLUDED.close, volume = EXCLUDED.volume, source = EXCLUDED.source
"""


class BarStorageMixin:
    """Mixin quan ly du lieu nến (1m/5m/daily/tf/derivative), index va khoi ngoai."""

    def _write(self, table: str, bars: list[Bar]) -> None:
        if not bars:
            return
        with self.conn() as c:
            c.cursor().executemany(
                _UPSERT_BAR.format(table=table),
                [
                    (b.symbol, b.ts, b.open, b.high, b.low, b.close, b.volume, b.source)
                    for b in bars
                ],
            )

    def write_bars(self, bars: list[Bar]) -> None:
        self._write("bars", bars)

    def write_daily(self, bars: list[Bar]) -> None:
        self._write("bars_daily", bars)

    def write_derivative_bars(self, bars: list[Bar]) -> None:
        self._write("bars_derivative", bars)

    def write_derivative_tf_bars(self, bars: list[Bar], interval: str) -> None:
        if not bars:
            return
        with self.conn() as c:
            c.cursor().executemany(
                _UPSERT_TF_BAR,
                [
                    (b.symbol, interval, b.ts, b.open, b.high, b.low, b.close, b.volume, b.source)
                    for b in bars
                ],
            )

    def write_stock_tf_bars(self, bars: list[Bar], interval: str) -> None:
        if not bars:
            return
        with self.conn() as c:
            c.cursor().executemany(
                _UPSERT_STOCK_TF_BAR,
                [
                    (b.symbol, interval, b.ts, b.open, b.high, b.low, b.close, b.volume, b.source)
                    for b in bars
                ],
            )

    def read_stock_tf_bars(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]:
        query = (
            "SELECT symbol, ts, open, high, low, close, volume, source FROM bars_tf "
            "WHERE symbol = %s AND interval = %s"
        )
        params: list[object] = [symbol, interval]
        if start is not None:
            query += " AND ts >= %s"
            params.append(start)
        if end is not None:
            query += " AND ts < %s"
            params.append(end)
        query += " ORDER BY ts"
        with self.conn() as c:
            rows = c.execute(query, tuple(params)).fetchall()
        return [Bar(*r) for r in rows]

    def read_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "5m",
    ) -> list[Bar]:
        if interval == "5m":
            with self.conn() as c:
                rows = c.execute(
                    "SELECT symbol, ts, open, high, low, close, volume, source FROM bars "
                    "WHERE symbol = %s AND ts >= %s AND ts < %s ORDER BY ts",
                    (symbol, start, end),
                ).fetchall()
            return [Bar(*r) for r in rows]
        return self.read_stock_tf_bars(symbol, interval, start, end)

    def read_derivative_tf_bars(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]:
        query = (
            "SELECT symbol, ts, open, high, low, close, volume, source FROM bars_derivative_tf "
            "WHERE symbol = %s AND interval = %s"
        )
        params: list[object] = [symbol, interval]
        if start is not None:
            query += " AND ts >= %s"
            params.append(start)
        if end is not None:
            query += " AND ts < %s"
            params.append(end)
        query += " ORDER BY ts"
        with self.conn() as c:
            rows = c.execute(query, tuple(params)).fetchall()
        return [Bar(*r) for r in rows]

    def read_derivative_bars(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "5m",
    ) -> list[Bar]:
        if interval == "5m":
            with self.conn() as c:
                rows = c.execute(
                    "SELECT symbol, ts, open, high, low, close, volume, source FROM bars_derivative "
                    "WHERE symbol = %s AND ts >= %s AND ts < %s ORDER BY ts",
                    (symbol, start, end),
                ).fetchall()
            return [Bar(*r) for r in rows]
        return self.read_derivative_tf_bars(symbol, interval, start, end)

    def read_daily_bars(self, symbol: str, start: datetime, end: datetime) -> list[Bar]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume, source FROM bars_daily "
                "WHERE symbol = %s AND ts >= %s AND ts < %s ORDER BY ts",
                (symbol, start, end),
            ).fetchall()
        return [Bar(*r) for r in rows]

    def last_bar_ts(self, symbol: str) -> datetime | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT max(ts) FROM bars WHERE symbol = %s", (symbol,)
            ).fetchone()
        return row[0]

    def read_last_bars(self, symbol: str, n: int) -> list[Bar]:
        """n bar gan nhat cua symbol, sap xep TANG DAN theo ts (de nap tuan tu
        vao chien luoc) — dung cho WARM-UP SMA/ATR luc engine khoi dong (rui
        ro 5 GO_LIVE_AUDIT: consumer durable khong phat lai tu dau, khong nap
        lich su thi engine mu ~1h45' sau restart, im lang). Method moi — khong
        caller cu nao bi anh huong."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume, source "
                "FROM bars WHERE symbol = %s ORDER BY ts DESC LIMIT %s",
                (symbol, n),
            ).fetchall()
        bars = [Bar(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in rows]
        bars.reverse()  # DESC -> ASC theo ts
        return bars

    def write_index_values(self, vals: list[IndexValue]) -> None:
        """Ghi nhận danh sách IndexValue vào DB.

        LƯU Ý: Hàm công khai này hiện chưa có caller trong production do mảng chỉ số
        (VNINDEX/VN30) đang tạm dừng có chủ đích (xem trading/collector/feed.py:
        'KHÔNG map IndexValue cho tới khi có nguồn dữ liệu thật khác'). KHÔNG XOÁ.
        """
        if not vals:
            return
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO index_values (index_id, ts, value) VALUES (%s, %s, %s) "
                "ON CONFLICT (index_id, ts) DO UPDATE SET value = EXCLUDED.value",
                [(v.index_id, v.ts, v.value) for v in vals],
            )

    def read_anchor_bar(self, symbol: str, fill_ts: datetime) -> Bar | None:
        """Bar neo `A` = bar ĐẦU TIÊN có `ts >= fill_ts`.

        Luật này đọc từ luồng sống, KHÔNG đoán: `engine/logic.py:36` gọi
        `broker.on_bar(bar)` (khớp lệnh, cập nhật vị thế) TRƯỚC `engine/logic.py:44`
        gọi `strategy.on_bar(bar, broker)`, và `PaperBroker` ghi `Fill(..., bar.ts, ...)`
        (`paper_broker.py:203`) — nên bar mà lệnh BUY khớp CHÍNH LÀ bar đầu tiên
        `strategy.on_bar` thấy `held > 0`, tức `ts == fill_ts` (dấu `>=`, không phải `>`).
        """
        with self.conn() as c:
            row = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume, source FROM bars "
                "WHERE symbol = %s AND ts >= %s ORDER BY ts ASC LIMIT 1",
                (symbol, fill_ts),
            ).fetchone()
        return Bar(*row) if row else None

    def read_bars_until(self, symbol: str, until_ts: datetime, n: int) -> list[Bar]:
        """`n` bar CUỐI có `ts <= until_ts`, sắp TĂNG DẦN (khuôn `read_last_bars`).

        Dùng để chạy lại ATR tại bar neo lúc khởi động (brief đợt 107 §1 bước 3).
        """
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol, ts, open, high, low, close, volume, source FROM bars "
                "WHERE symbol = %s AND ts <= %s ORDER BY ts DESC LIMIT %s",
                (symbol, until_ts, n),
            ).fetchall()
        bars = [Bar(*r) for r in rows]
        bars.reverse()  # DESC -> ASC theo ts
        return bars

    def read_last_close(self, symbol: str) -> float | None:
        """Gia dong cua gan nhat cua symbol (bars truoc, bars_daily sau) —
        dung de kiem tra tran gia tri lenh that luc khoi dong (GUARD-1): neu
        tran khong du mua noi 1 lo 100 cp thi duong dat lenh that INERT (se
        khong bao gio sinh lenh BUY) — phai alert CRITICAL, khong duoc im
        lang. Tra None neu ca hai bang rong cho symbol nay — caller bo qua
        im lang (khong the ket luan, canh bao sai se lam nhon canh bao that)."""
        with self.conn() as c:
            row = c.execute(
                "SELECT close FROM bars WHERE symbol = %s AND close > 0 ORDER BY ts DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            if row is None:
                row = c.execute(
                    "SELECT close FROM bars_daily WHERE symbol = %s AND close > 0 ORDER BY ts DESC LIMIT 1",
                    (symbol,),
                ).fetchone()
        return row[0] if row else None

    def read_latest_bar(self, symbol: str) -> tuple[datetime, float] | None:
        """(ts, close) cua bar moi nhat — bars_daily truoc (ma dang giu nhu
        CAP/HCM/SSI/TCX chi co daily), bars 5m sau (ma cau hinh). MARGIN-1:
        dung de dinh gia vi the dang giu khi tinh NAV."""
        with self.conn() as c:
            row = c.execute(
                "SELECT ts, close FROM bars_daily WHERE symbol = %s ORDER BY ts DESC LIMIT 1",
                (symbol,),
            ).fetchone()
            if row is None:
                row = c.execute(
                    "SELECT ts, close FROM bars WHERE symbol = %s ORDER BY ts DESC LIMIT 1",
                    (symbol,),
                ).fetchone()
        return (row[0], row[1]) if row else None

    def write_foreign_flow(self, rows: list[ForeignFlow]) -> int:
        """Ghi hoac cap nhat du lieu giao dich khoi ngoai theo ngay (Brief 190).

        Upsert bang ON CONFLICT (symbol, trading_date) DO UPDATE.
        Khong delete, khong truncate.
        Tra ve so dong ghi/cap nhat.
        """
        if not rows:
            return 0
        sql = """
            INSERT INTO foreign_flow_daily (
                symbol, trading_date, buy_vol, sell_vol, buy_val, sell_val,
                net_vol, net_val, current_room, close_price
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, trading_date) DO UPDATE SET
                buy_vol = EXCLUDED.buy_vol,
                sell_vol = EXCLUDED.sell_vol,
                buy_val = EXCLUDED.buy_val,
                sell_val = EXCLUDED.sell_val,
                net_vol = EXCLUDED.net_vol,
                net_val = EXCLUDED.net_val,
                current_room = EXCLUDED.current_room,
                close_price = EXCLUDED.close_price,
                ingested_at = now()
        """
        params = [
            (
                r.symbol,
                r.trading_date,
                r.buy_vol,
                r.sell_vol,
                r.buy_val,
                r.sell_val,
                r.net_vol,
                r.net_val,
                r.current_room,
                r.close_price,
            )
            for r in rows
        ]
        with self.conn() as c:
            c.cursor().executemany(sql, params)
        return len(params)

    def read_foreign_flow(
        self, symbol: str, frm: date, to: date
    ) -> list[ForeignFlow]:
        """Doc du lieu giao dich khoi ngoai cua symbol tu ngay frm den to (Brief 190).
        Sap theo trading_date ASC.
        """
        sql = """
            SELECT symbol, trading_date, buy_vol, sell_vol, buy_val, sell_val,
                   net_vol, net_val, current_room, close_price, ingested_at
            FROM foreign_flow_daily
            WHERE symbol = %s AND trading_date >= %s AND trading_date <= %s
            ORDER BY trading_date ASC
        """
        with self.conn() as c:
            rows = c.execute(sql, (symbol, frm, to)).fetchall()
        return [
            ForeignFlow(
                symbol=r[0],
                trading_date=r[1],
                buy_vol=r[2],
                sell_vol=r[3],
                buy_val=r[4],
                sell_val=r[5],
                net_vol=r[6],
                net_val=r[7],
                current_room=r[8],
                close_price=r[9],
                ingested_at=r[10],
            )
            for r in rows
        ]

    def read_foreign_flow_day_counts(
        self, frm: date, to: date
    ) -> dict[date, int]:
        """Doc so dong giao dich khoi ngoai theo ngay trong khoang [frm, to] (Brief 190b).
        Tra ve dict {trading_date: count}. Ngay khong co dong nao khong co trong dict.
        """
        sql = """
            SELECT trading_date, count(*)
            FROM foreign_flow_daily
            WHERE trading_date >= %s AND trading_date <= %s
            GROUP BY 1
            ORDER BY 1 ASC
        """
        with self.conn() as c:
            rows = c.execute(sql, (frm, to)).fetchall()
        return {r[0]: r[1] for r in rows}

    def read_foreign_flow_last_date(self) -> date | None:
        """Doc ngay lon nhat co du lieu trong foreign_flow_daily (Brief 200).
        Tra ve None neu bang trong hoac tat ca NULL.
        """
        sql = "SELECT max(trading_date) FROM foreign_flow_daily"
        with self.conn() as c:
            row = c.execute(sql).fetchone()
        return row[0] if row and row[0] is not None else None

    def read_5m_active_symbol_day_counts(
        self, frm: date, to: date
    ) -> dict[date, int]:
        """Doc so ma khac nhau trong bars theo ngay gio VN trong khoang [frm, to] (Brief 198),
        chi tinh cac ma co symbol_universe.is_active = true.
        Ngay tinh theo gio VN: (b.ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date.
        Loc khoang bang ts de dung index: b.ts >= 00:00 VN cua frm va b.ts < 00:00 VN cua to + 1 ngay.
        Ngay khong co ma nao thi khong co khoa trong dict.
        """
        ts_frm = datetime(frm.year, frm.month, frm.day, 0, 0, 0, tzinfo=TZ)
        to_next = to + timedelta(days=1)
        ts_to = datetime(to_next.year, to_next.month, to_next.day, 0, 0, 0, tzinfo=TZ)
        sql = """
            SELECT (b.ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date, count(DISTINCT b.symbol)
            FROM bars b
            JOIN symbol_universe u ON u.symbol = b.symbol
            WHERE u.is_active = true
              AND b.ts >= %s
              AND b.ts < %s
            GROUP BY 1
            ORDER BY 1 ASC
        """
        with self.conn() as c:
            rows = c.execute(sql, (ts_frm, ts_to)).fetchall()
        return {r[0]: r[1] for r in rows}

    def read_daily_active_symbol_day_counts(
        self, frm: date, to: date
    ) -> dict[date, int]:
        """Doc so ma khac nhau trong bars_daily theo ngay gio VN trong khoang [frm, to] (Brief 199),
        chi tinh cac ma co symbol_universe.is_active = true.
        Ngay tinh theo gio VN: (b.ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date.
        Loc khoang bang ts de dung index: b.ts >= 00:00 VN cua frm va b.ts < 00:00 VN cua to + 1 ngay.
        Ngay khong co ma nao thi khong co khoa trong dict.
        """
        ts_frm = datetime(frm.year, frm.month, frm.day, 0, 0, 0, tzinfo=TZ)
        to_next = to + timedelta(days=1)
        ts_to = datetime(to_next.year, to_next.month, to_next.day, 0, 0, 0, tzinfo=TZ)
        sql = """
            SELECT (b.ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date, count(DISTINCT b.symbol)
            FROM bars_daily b
            JOIN symbol_universe u ON u.symbol = b.symbol
            WHERE u.is_active = true
              AND b.ts >= %s
              AND b.ts < %s
            GROUP BY 1
            ORDER BY 1 ASC
        """
        with self.conn() as c:
            rows = c.execute(sql, (ts_frm, ts_to)).fetchall()
        return {r[0]: r[1] for r in rows}

    def read_daily_symbol_counts(self) -> dict[date, int]:
        """Thống kê số lượng symbol có bar theo từng ngày (quy về Asia/Ho_Chi_Minh)."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS d, "
                "       count(DISTINCT symbol) AS n "
                "FROM bars_daily "
                "GROUP BY 1 ORDER BY 1"
            ).fetchall()
        return {r[0]: int(r[1]) for r in rows}

    def read_symbol_completeness_summaries(
        self, symbols: list[str] | None = None
    ) -> list[dict]:
        """Thống kê theo mã: first_date, last_date, total_bars, dirty_bars."""
        query = (
            "SELECT symbol, "
            "       MIN((ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date) AS first_date, "
            "       MAX((ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date) AS last_date, "
            "       COUNT(*) AS total_bars, "
            "       COUNT(*) FILTER (WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0) AS dirty_bars "
            "FROM bars_daily "
        )
        params: tuple = ()
        if symbols:
            query += "WHERE symbol = ANY(%s) "
            params = (list(symbols),)
        query += "GROUP BY symbol ORDER BY symbol"
        with self.conn() as c:
            rows = c.execute(query, params).fetchall()
        return [
            {
                "symbol": r[0],
                "first_date": r[1],
                "last_date": r[2],
                "total_bars": int(r[3]),
                "dirty_bars": int(r[4]),
            }
            for r in rows
        ]

    def read_symbol_present_dates(self, symbol: str) -> set[date]:
        """Lấy danh sách các ngày có bar của 1 mã (chỉ gọi cho các mã có lỗ hổng)."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date "
                "FROM bars_daily WHERE symbol = %s ORDER BY 1",
                (symbol,),
            ).fetchall()
        return {r[0] for r in rows}

    def read_daily_bar_dates(
        self, symbols: list[str], start: date, end: date
    ) -> dict[str, list[date]]:
        """{ma: [ngay VN co bar daily]} voi start <= ngay < end. Dung cho phep loc
        ma chi-thu-Sau cua daily_data_check (dot 97). Ngay quy ve Asia/Ho_Chi_Minh:
        bars_daily luu 00:00 VN = 17:00 UTC hom truoc, ts::date se lui mot ngay."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol, (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date FROM bars_daily "
                "WHERE (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date >= %s "
                "AND (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date < %s "
                "AND symbol = ANY(%s)",
                (start, end, list(symbols)),
            ).fetchall()
        out: dict[str, list[date]] = {}
        for sym, d in rows:
            out.setdefault(sym, []).append(d)
        return out

    def read_symbols_with_bar_on_date(
        self, day: date, symbols: list[str] | None = None
    ) -> set[str]:
        """Tập các mã có bar trong 1 ngày cụ thể (quy về Asia/Ho_Chi_Minh)."""
        query = (
            "SELECT DISTINCT symbol FROM bars_daily "
            "WHERE (ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date = %s "
        )
        params: list = [day]
        if symbols:
            query += "AND symbol = ANY(%s)"
            params.append(list(symbols))
        with self.conn() as c:
            rows = c.execute(query, tuple(params)).fetchall()
        return {r[0] for r in rows}
