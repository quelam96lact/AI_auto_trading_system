from dataclasses import dataclass
from datetime import date, datetime

from trading.broker import Fill, Position
from trading.calendar_vn import trading_days_between_dates
from trading.models import Bar
from trading.strategy import Signal

# 0.25% - biểu phí SSI, đặt lệnh Online (không qua môi giới), giá trị GD
# dưới 100 triệu đồng/ngày/tài khoản. Nguồn: https://www.ssi.com.vn/khach-hang-ca-nhan/bieu-phi/bieu-gia-dich-vu-giao-dich-chung-khoan
# (hiệu lực 10/10/2025, đã bao gồm phí trả Sở). Các bậc giá trị GD cao hơn có
# mức phí khác (0.30% / 0.25%) - chưa hỗ trợ trong PaperBroker (dùng 1 rate cố định).
FEE_RATE = 0.0025
SELL_TAX_RATE = 0.001
SLIPPAGE_BPS = 5

# SPEC-1a: mua ngay D -> ban duoc tu ngay giao dich D+3 (lam tron len tu
# T+2,5, khop cach real_orders.py doc sellable_qty tu SSI). Dung NGAY
# GIAO DICH (so bar ngay), khong dung ngay lich.
SETTLE_DAYS = 3


@dataclass
class Lot:
    """Mot lo co phieu dang giu: so luong + ngay giao dich da mua (index vao
    danh sach cac ngay giao dich broker da thay). Dung de tinh phan da settle
    (T+2,5) theo FIFO — lo cu settle truoc."""

    day_index: int
    qty: int


class PaperBroker:
    def __init__(
        self,
        capital: float,
        fee_rate: float = FEE_RATE,
        sell_tax_rate: float = SELL_TAX_RATE,
        slippage_bps: float = SLIPPAGE_BPS,
        settle_days: int = SETTLE_DAYS,
    ):
        self.capital = capital
        self.cash = capital
        self.fee_rate = fee_rate
        self.sell_tax_rate = sell_tax_rate
        self.slippage_bps = slippage_bps
        # 2026-09-03 (goi B): settle_days thanh tham so — crypto khong co T+3,
        # dat 0 de ban duoc ngay. Mac dinh = SETTLE_DAYS (3) — hanh vi VN cu
        # giu NGUYEN (engine/main.py:58 goi PaperBroker(CAPITAL) khong doi).
        self.settle_days = settle_days
        self.positions: dict[str, Position] = {}
        self.realized_pnl = 0.0
        self._pending: dict[str, Signal] = {}
        # SPEC-1a: cac ngay giao dich da thay (theo thu tu xuat hien — gia dinh
        # bar den theo thu tu thoi gian, dung nhu run_backtest sort + engine
        # nhan bar song). Moi ngay lich moi = 1 ngay giao dich moi.
        self._trade_days: list[date] = []
        self._lots: dict[str, list[Lot]] = {}
        self._pending_buy_dates: dict[str, date] | None = None
        self._holidays: frozenset = frozenset()

    def _day_index(self, ts: datetime) -> int:
        """Tra index cua ngay giao dich chua `ts`; neu la ngay moi, them vao
        cuoi danh sach (gia dinh bar den theo thu tu thoi gian)."""
        d = ts.date()
        if not self._trade_days or self._trade_days[-1] != d:
            first_day = len(self._trade_days) == 0
            self._trade_days.append(d)
            if first_day and self._pending_buy_dates:
                self._resolve_pending_lots(d)
        return len(self._trade_days) - 1

    def _resolve_pending_lots(self, T: date) -> None:
        """Brief 96 Task 1b: phân giải lazy day_index cho các vị thế khôi phục.

        k = số ngày giao dịch d thỏa buy_date < d <= T.
        Gán lot.day_index = -k để tại ngày đầu tiên (today=0),
        today - lot.day_index = 0 - (-k) = k.
        """
        if not self._pending_buy_dates:
            return
        for sym, buy_date in self._pending_buy_dates.items():
            lots = self._lots.get(sym)
            if not lots:
                continue
            k = trading_days_between_dates(buy_date, T, self._holidays)
            for lot in lots:
                lot.day_index = -k
        self._pending_buy_dates = None

    def sellable_qty(self, symbol: str, ts: datetime) -> int:
        """SPEC-1a: phan co the ban hom nay = tong qty cac lo co day_index sao
        cho ngay hom nay >= day_index + settle_days (mua D -> ban duoc D+3)."""
        today = self._day_index(ts)
        return sum(
            lot.qty
            for lot in self._lots.get(symbol, [])
            if today - lot.day_index >= self.settle_days
        )

    def _consume_lots(self, symbol: str, qty: int, today: int) -> None:
        """Tru qty da ban khoi cac lo (FIFO: lo cu nhat — day_index nho nhat —
        truoc). Chi tru vao lo da settle (today - day_index >= settle_days); vi
        caller da gioi han qty <= sellable_qty nen luon du lo de tru."""
        lots = self._lots.get(symbol)
        if not lots:
            return
        remaining = qty
        kept: list[Lot] = []
        for lot in lots:
            if remaining <= 0:
                kept.append(lot)
                continue
            if today - lot.day_index < self.settle_days:
                kept.append(lot)  # chua settle — khong dong toi
                continue
            if lot.qty > remaining:
                kept.append(Lot(lot.day_index, lot.qty - remaining))
                remaining = 0
            else:
                remaining -= lot.qty
        if remaining > 0:  # phong thu: qty > sellable — khong duoc phep, giu nguyen
            raise AssertionError(
                f"consume_lots: khong du lo settle de tru {qty} (con {remaining})"
            )
        self._lots[symbol] = kept

    def position_qty(self, symbol: str) -> int:
        pos = self.positions.get(symbol)
        return pos.qty if pos else 0

    def submit(self, signal: Signal) -> None:
        self._pending[signal.symbol] = signal

    def force_exit(self, symbol: str, price: float, ts: datetime) -> Fill:
        """Dong phan vi the da SETTLE ngay lap tuc tai `price` — dung boi
        trailing stop. KHONG qua hang doi self._pending nhu submit()/on_bar()
        (khong co do tre 1 bar). SPEC-1a: phan chua settle (T+2,5) KHONG the
        ban — giong real_orders.py chi ban sellable_qty; neu chua co gi settle
        duoc thi tra Fill qty=0 (caller bo qua, vi the giu nguyen)."""
        pos = self.positions[symbol]
        today = self._day_index(ts)
        qty = min(pos.qty, self.sellable_qty(symbol, ts))
        if qty <= 0:
            return Fill(symbol, "SELL", 0, price, 0.0, ts, None)
        gross = price * qty
        fee = gross * self.fee_rate + gross * self.sell_tax_rate
        pnl = (price - pos.avg_price) * qty - fee
        self.realized_pnl += pnl
        self.cash += gross - fee
        pos.qty -= qty
        if pos.qty == 0:
            pos.avg_price = 0.0
        self._consume_lots(symbol, qty, today)
        return Fill(symbol, "SELL", qty, price, fee, ts, pnl)

    def on_bar(self, bar: Bar) -> list[Fill]:
        # SPEC-1a: ngay giao dich duoc danh dau cho MOI bar (ke ca bar khong
        # co lenh treo) — thi truong van troi qua ngay du khong co lenh cua ta.
        today = self._day_index(bar.ts)
        signal = self._pending.pop(bar.symbol, None)
        if signal is None:
            return []
        qty = signal.qty
        if signal.side == "SELL":
            # SPEC-1a: chi khop tren phan da settle — phan chua settle bi tu choi
            qty = min(qty, self.sellable_qty(bar.symbol, bar.ts))
            if qty <= 0:
                return []
        slip = bar.open * (self.slippage_bps / 10_000)
        price = bar.open + slip if signal.side == "BUY" else bar.open - slip
        gross = price * qty
        fee = gross * self.fee_rate + (
            gross * self.sell_tax_rate if signal.side == "SELL" else 0.0
        )

        pos = self.positions.setdefault(bar.symbol, Position(bar.symbol))
        pnl = None
        if signal.side == "BUY":
            new_qty = pos.qty + qty
            # FEE-ALARM-1: gop phi MUA vao gia von — truoc day avg_price dung
            # gross (chua gom phi) trong khi cash ngay duoi tru phi do -> hai
            # so sach lech nhau, realized_pnl bo sot phi mua cua MOI vong giao
            # dich, luon sai mot chieu (bao lo nhe hon thuc te). Do that:
            # cash giam 328.798 nhung realized_pnl chi ghi -209.381 (chenh
            # 119.417 = tong phi 5 lenh mua). avg_price gio la "gia von gom
            # phi" — da kiem: khong ai doc avg_price voi nghia "gia khop"
            # (trailing stop dung tu lich su lenh, engine/main.py:108).
            pos.avg_price = (pos.avg_price * pos.qty + gross + fee) / new_qty
            pos.qty = new_qty
            self.cash -= gross + fee
            # SPEC-1a: ghi nhan lo moi voi ngay giao dich hom nay
            self._lots.setdefault(bar.symbol, []).append(Lot(today, qty))
        else:
            pnl = (price - pos.avg_price) * qty - fee
            self.realized_pnl += pnl
            self.cash += gross - fee
            pos.qty -= qty
            if pos.qty == 0:
                pos.avg_price = 0.0
            self._consume_lots(bar.symbol, qty, today)

        return [Fill(bar.symbol, signal.side, qty, price, fee, bar.ts, pnl)]

    def unrealized_pnl(self, marks: dict[str, float]) -> float:
        return sum(
            (marks[s] - p.avg_price) * p.qty
            for s, p in self.positions.items()
            if p.qty > 0 and s in marks
        )

    @classmethod
    def restore(
        cls,
        capital: float,
        cash: float,
        realized_pnl: float,
        positions: dict[str, Position],
        buy_dates: dict[str, date] | None = None,
        holidays: frozenset = frozenset(),
        **kwargs,
    ) -> "PaperBroker":
        broker = cls(capital, **kwargs)
        broker.cash = cash
        broker.realized_pnl = realized_pnl
        broker.positions = positions
        # Brief 96 Task 1: Khôi phục vị thế theo ngày mua thật.
        # Mặc định day_index = 0 cho mọi vị thế (bảo thủ).
        # Nếu có buy_dates, _day_index sẽ phân giải lazy ngày mua ở bar đầu tiên
        # theo công thức k = count(trading days buy_date < d <= T) và gán day_index = -k.
        for sym, p in positions.items():
            if p.qty > 0:
                broker._lots[sym] = [Lot(day_index=0, qty=p.qty)]
        if buy_dates:
            broker._pending_buy_dates = dict(buy_dates)
            broker._holidays = holidays
        return broker
