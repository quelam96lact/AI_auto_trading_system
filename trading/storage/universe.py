"""Symbol universe, backfill progress, and backtest persistence mixin."""

from __future__ import annotations

from datetime import date

from trading.broker import Fill


class UniverseBacktestStorageMixin:
    """Mixin quan ly symbol_universe, backfill_progress va backtest_runs/equity/fills."""

    def upsert_symbol_universe(self, rows: list[dict]) -> None:
        if not rows:
            return
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO symbol_universe "
                "(symbol, exchange, avg_value_20d, avg_volume_20d, is_active, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, now()) "
                "ON CONFLICT (symbol) DO UPDATE SET "
                "exchange = EXCLUDED.exchange, avg_value_20d = EXCLUDED.avg_value_20d, "
                "avg_volume_20d = EXCLUDED.avg_volume_20d, is_active = EXCLUDED.is_active, "
                "updated_at = now()",
                [
                    (
                        r["symbol"],
                        r["exchange"],
                        r.get("avg_value_20d"),
                        r.get("avg_volume_20d"),
                        r["is_active"],
                    )
                    for r in rows
                ],
            )

    def read_active_universe(self) -> list[str]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol FROM symbol_universe WHERE is_active ORDER BY symbol"
            ).fetchall()
        return [r[0] for r in rows]

    def read_top_active_universe(self, limit: int = 3) -> list[str]:
        """Tra ve toi da `limit` ma active co thanh khoan 20d cao nhat."""
        if limit <= 0:
            return []
        with self.conn() as c:
            rows = c.execute(
                "SELECT symbol FROM symbol_universe WHERE is_active "
                "ORDER BY avg_value_20d DESC NULLS LAST, symbol ASC LIMIT %s",
                (limit,),
            ).fetchall()
        return [r[0] for r in rows]

    def read_symbol_universe(self) -> set[str]:
        """Doc toan bo ma trong symbol_universe (khong loc is_active)."""
        with self.conn() as c:
            rows = c.execute("SELECT symbol FROM symbol_universe").fetchall()
        return {r[0] for r in rows}

    def read_must_price_symbols(
        self, accounts: list[str], extra: list[str]
    ) -> list[str]:
        """Brief 2026-09-01 (dot 2): tap ma BAT BUOC phai co gia hang ngay.

        = extra (vi du cfg.symbols — ma engine giao dich) HOP voi ma dang nam
        giu cua TUNG tai khoan trong accounts. Day la vai thu hai cua is_active
        cu: ma dang nam giu phai duoc nap bar DU thanh khoan thap (CAP 0,63 ty
        < nguong 1 ty van phai co gia — neu khong sau 5 phien NAV tinh chung
        bang 0, ma NAV la so nhan kich thuoc lenh that, commit 6159d39).

        BAT BUOC dung lai self.read_real_positions(account) de lay ma dang nam —
        khong viet truy van account_position_snapshot moi (bai hoc 4ea4c8d: mot
        cong thuc hai ban). Ham do da xu ly: bam moc account_sync_log (phan biet
        "chua dong bo" voi "da dong bo va rong").

        goi H (04/09): goi voi include_unsettled=True — DAY LA CHO DUY NHAT
        trong ca ma san pham lam vay. Ly do: ma vua mua co `quantity = 0` suot
        cua so thanh toan T+2, dung nhung ngay no CAN duoc nap gia nhat. FOX
        (33% danh muc) vi the bi dinh gia bang gia 28/08 suot 5 phien, va IM
        LANG vi kiem tra tuoi gia dem theo ngay giao dich nen 28/08 -> 04/09
        chi la 2 ngay <= nguong 5. "Bat buoc co gia" phai bao gom ca ma chua
        ve — no van la tien cua tai khoan.

        Tra ve danh sach sap xep, khong trung.
        """
        must: set[str] = set(extra)
        for account in accounts:
            positions = self.read_real_positions(account, include_unsettled=True)
            must.update(positions.keys())
        return sorted(must)

    def get_backfill_progress(self, symbol: str, timeframe: str) -> dict | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT symbol, timeframe, last_done_date, status, error, attempted_until "
                "FROM backfill_progress WHERE symbol = %s AND timeframe = %s",
                (symbol, timeframe),
            ).fetchone()
        if row is None:
            return None
        return {
            "symbol": row[0],
            "timeframe": row[1],
            "last_done_date": row[2],
            "status": row[3],
            "error": row[4],
            "attempted_until": row[5],
        }

    def set_backfill_progress(
        self,
        symbol: str,
        timeframe: str,
        last_done_date,
        status: str,
        error: str | None = None,
        attempted_until=None,
    ) -> None:
        """Ghi trạng thái backfill. attempted_until = ngày ĐÃ HỎI API tới (kể cả
        khi mã không giao dịch — mảng rỗng); last_done_date = ngày bar THẬT cuối
        nhận được (chỉ tiến khi có dữ liệu). Tách hai khái niệm này từ
        2026-08-18 để skip dựa trên attempted_until (chống fetch lại vĩnh viễn)
        mà last_done_date vẫn trung thực (không ghi nhận độ phủ không có)."""
        with self.conn() as c:
            c.execute(
                "INSERT INTO backfill_progress "
                "(symbol, timeframe, last_done_date, status, error, attempted_until, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, now()) "
                "ON CONFLICT (symbol, timeframe) DO UPDATE SET "
                "last_done_date = EXCLUDED.last_done_date, status = EXCLUDED.status, "
                "error = EXCLUDED.error, attempted_until = EXCLUDED.attempted_until, "
                "updated_at = now()",
                (symbol, timeframe, last_done_date, status, error, attempted_until),
            )

    def save_backtest_run(
        self,
        symbol: str,
        strategy: str,
        timeframe: str,
        frm: date,
        to_date: date,
        capital: float,
        realized_pnl: float,
        unrealized_pnl: float,
        buy_and_hold_pnl: float,
        max_drawdown: float,
        win_rate: float,
        trades: int,
        filtered_bars: dict[str, int] | None = None,
    ) -> int:
        """Ghi 1 dong backtest_runs, tra ve run_id. filtered_bars la dict
        (tong cac ma) — luu TONG so bar rac vao cot filtered_bars (int)."""
        total_filtered = sum((filtered_bars or {}).values())
        with self.conn() as c:
            row = c.execute(
                "INSERT INTO backtest_runs "
                "(symbol, strategy, timeframe, frm, to_date, capital, realized_pnl, "
                " unrealized_pnl, buy_and_hold_pnl, max_drawdown, win_rate, trades, "
                " filtered_bars) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING run_id",
                (
                    symbol, strategy, timeframe, frm, to_date, capital,
                    realized_pnl, unrealized_pnl, buy_and_hold_pnl,
                    max_drawdown, win_rate, trades, total_filtered,
                ),
            ).fetchone()
        assert row is not None, "RETURNING run_id phai co dong"
        return int(row[0])

    def read_backtest_runs(self, limit: int = 100) -> list[dict]:
        """Doc cac lan chay backtest gan nhat (Grafana dung lam nguon bien)."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT run_id, ts, symbol, strategy, timeframe, frm, to_date, "
                "       capital, realized_pnl, unrealized_pnl, buy_and_hold_pnl, "
                "       max_drawdown, win_rate, trades, filtered_bars "
                "FROM backtest_runs ORDER BY run_id DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [
            {
                "run_id": int(r[0]), "ts": r[1], "symbol": r[2], "strategy": r[3],
                "timeframe": r[4], "frm": r[5], "to_date": r[6], "capital": r[7],
                "realized_pnl": r[8], "unrealized_pnl": r[9],
                "buy_and_hold_pnl": r[10], "max_drawdown": r[11],
                "win_rate": r[12], "trades": int(r[13]) if r[13] is not None else 0,
                "filtered_bars": int(r[14]) if r[14] is not None else 0,
            }
            for r in rows
        ]

    def save_backtest_equity(
        self, run_id: int, curve: list[tuple], bh_curve: list[tuple] | None = None
    ) -> None:
        """Ghi duong von (list[(ts, equity)]) kem duong mua-va-giu THAT.

        bh_curve phai cung do dai va cung moc ts voi curve (run_backtest bao
        dam dieu do). Grafana chi DOC hai cot nay — khong tinh benchmark trong
        SQL, vi do la ban thu hai cua cong thuc _buy_and_hold."""
        if not curve:
            return
        bh = [e for _, e in bh_curve] if bh_curve else [None] * len(curve)
        if len(bh) != len(curve):
            raise ValueError(
                f"bh_curve {len(bh)} diem != equity_curve {len(curve)} diem — "
                "hai duong phai cung moc ts thi moi ve chong len nhau duoc"
            )
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO backtest_equity (run_id, ts, equity, equity_bh) "
                "VALUES (%s,%s,%s,%s)",
                [(run_id, ts, eq, b) for (ts, eq), b in zip(curve, bh)],
            )

    def read_backtest_equity(self, run_id: int) -> list[tuple]:
        """Doc duong von theo run_id, sap theo ts. Tra (ts, equity, equity_bh)."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT ts, equity, equity_bh FROM backtest_equity "
                "WHERE run_id = %s ORDER BY ts",
                (run_id,),
            ).fetchall()
        return [
            (r[0], float(r[1]), float(r[2]) if r[2] is not None else None) for r in rows
        ]

    def save_backtest_fills(self, run_id: int, fills: list[Fill]) -> None:
        """Ghi cac lenh cua 1 lan chay backtest."""
        if not fills:
            return
        with self.conn() as c:
            c.cursor().executemany(
                "INSERT INTO backtest_fills (run_id, ts, side, qty, price, fee) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                [(run_id, f.ts, f.side, f.qty, f.price, f.fee) for f in fills],
            )

    def read_backtest_fills(self, run_id: int) -> list[tuple]:
        """Doc cac lenh theo run_id, sap theo ts (khong co pnl — khuon plan)."""
        with self.conn() as c:
            rows = c.execute(
                "SELECT ts, side, qty, price, fee FROM backtest_fills "
                "WHERE run_id = %s ORDER BY ts",
                (run_id,),
            ).fetchall()
        return [(r[0], r[1], int(r[2]), float(r[3]), float(r[4])) for r in rows]
