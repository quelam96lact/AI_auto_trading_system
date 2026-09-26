"""Bang dac trung so lenh VN30F theo luoi 1 phut (Brief dot 93).

MUC DICH: tra loi cau hoi KHA THI — tu file so lenh da thu duoc, co dung duoc mot
bang dac trung theo LUOI THOI GIAN DEU, voi ty le thieu du lieu BIET RO, hay
khong? Neu khong thi phai sua may ghi truoc khi thu them phien.

KHONG PHAI PHEP DO TIN HIEU: mot phien la vo nghia ve thong ke. Cong cu nay
KHONG tinh tuong quan, KHONG kiem dinh, KHONG ket luan du lieu "tot"/"hua hen".

Nam quyet dinh da chot trong brief (khong tu doi):
0.  Gop phut theo `trading_time` (gio cua SAN), KHONG theo `recv_ts` (gio may ta
    nhan). Do tre duong truyen cua ta (do dot 79: trung vi 12s, toi da 61s) se
    bi nuong vao du lieu neu gop theo recv_ts, lam moi phep do sau lech pha.
0b. Phan loai QUOTE/TRADE dung lai `classify_message` cua may ghi — ngu nghia
    phan loai chi co MOT cho.
1.  Don vi diem (moi diem 100.000 VND), khong phai phan tram.
2.  Cot tu QUOTE lay QUOTE CUOI PHUT (anh chup so lenh luc quyet dinh), khong
    trung binh hoa — trung binh la tron nhieu trang thai khong cung ton tai.
3.  `imb` chuan hoa ve [-1, 1] bang cach chia cho tong.
4.  (them 26/09) Bao cao ca phan bo `recv_ts - trading_time`.

Quy uoc luoi phut:
- Sang: cac o bat dau 09:00..11:29 (150 o); Chieu: 13:00..14:29 (90 o) -> 240 o.
  Khung NUA MO [bat dau, ket thuc): tin tu moc ket thuc tro di la NGOAI khung.
- Chieu KET THUC 14:30, KHONG phai 14:45 (AFTERNOON_END cua may ghi). 14:30-14:45
  la phien ATC: file 25/09 cho thay moi tin 'TRADE' 14:30-14:44 co side='U',
  quantity=0 (tin chi bao, khong phai lenh khop), va 14:45 la lan khop ATC 5.757 HD
  mot phia. Gop chung vao dac trung khop lenh lien tuc la nhiem du lieu (Claude
  audit dot 93). May ghi van ghi toi 14:45 la DUNG cho viec cua no.
- Tin ngoai khung phien (vd 08:59, ATC 14:30-14:45) khong tao hang, chi dem rieng.

Phut khong co QUOTE -> cac cot tu QUOTE la None (khong noi suy, khong lay phut
truoc). Phut khong co TRADE -> ofi = 0, trade_qty = 0 (khong co lenh khop la GIA
TRI THAT, khac voi khong co du lieu).
"""

from __future__ import annotations

import argparse
import gzip
import json
import pathlib
import re
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any

# In tieng Viet tren Windows: cp1252 -> UnicodeEncodeError neu khong ep UTF-8
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name)
    if getattr(_stream, "encoding", None) and _stream.encoding.lower() not in ("utf-8", "utf8"):
        _stream.reconfigure(encoding="utf-8")

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.record_vn30f_orderbook import (
    AFTERNOON_START,
    MORNING_END,
    MORNING_START,
    classify_message,
)
from trading.calendar_vn import TZ

# Het khop lenh lien tuc buoi chieu (phai sinh HNX); 14:30-14:45 la ATC. Xem docstring.
# KHONG dung calendar_vn.CONTINUOUS_SESSIONS: do la khung CO PHIEU, sang bat dau 09:15;
# phai sinh khop lien tuc tu 09:00 (file 25/09 co tin 09:03-09:15 binh thuong).
CONTINUOUS_AFTERNOON_END = dt_time(14, 30)

DEPTH_TOP1 = 1
DEPTH_TOP5 = 5


@dataclass(frozen=True)
class MinuteRow:
    """Mot phut tren luoi: dac trung so lenh cua phut do."""

    minute: datetime
    n_quote: int
    n_trade: int
    n_other: int
    mid_close: float | None
    spread: float | None
    imb_top1: float | None
    imb_top5: float | None
    ofi: float
    trade_qty: float

    def usable(self) -> bool:
        """Hang dung duoc = co du mid_close, imb_top5, ofi (brief muc 2.5)."""
        return self.mid_close is not None and self.imb_top5 is not None and self.ofi is not None


def session_minutes(d: date) -> list[datetime]:
    """Luoi phut cua phien khop lenh lien tuc: 150 o sang + 90 o chieu = 240."""
    out: list[datetime] = []
    cur = datetime.combine(d, MORNING_START, tzinfo=TZ)
    end = datetime.combine(d, MORNING_END, tzinfo=TZ)
    while cur < end:
        out.append(cur)
        cur += timedelta(minutes=1)
    cur = datetime.combine(d, AFTERNOON_START, tzinfo=TZ)
    end = datetime.combine(d, CONTINUOUS_AFTERNOON_END, tzinfo=TZ)
    while cur < end:
        out.append(cur)
        cur += timedelta(minutes=1)
    return out


def parse_trading_time(raw: Any) -> datetime | None:
    """Doc `trading_time` cua san ('2026/09/25 09:03:51') thanh datetime gio VN."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    return None


def parse_recv_ts(raw: Any) -> datetime | None:
    """Doc `recv_ts` (ISO, co mui gio) thanh datetime."""
    if not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt


def _bucket_index(
    idx_of: dict[datetime, int], ts: datetime, session_date: date
) -> int | None:
    """Chi so o phut cua tin; None neu tin ngoai khung phien."""
    if ts.date() != session_date:
        return None
    floored = ts.replace(second=0, microsecond=0)
    # Khung nua mo: tin tu moc ket thuc tro di (11:30, 14:30) la NGOAI khung. Ban dau
    # gop CA PHUT ket thuc vao o cuoi - o 14:45 do chinh la lan khop ATC.
    return idx_of.get(floored)


def _imbalance(bid_volumes: list[Any], ask_volumes: list[Any], depth: int) -> float | None:
    """(sum bid - sum ask) / (sum bid + sum ask) tren `depth` buoc gia dau moi ben.

    Chia cho 0 (ca hai ben deu 0) -> None: khong co du lieu de noi gi, KHONG phai 0.
    """
    b = 0.0
    a = 0.0
    for v in bid_volumes[:depth]:
        try:
            b += float(v or 0)
        except (TypeError, ValueError):
            pass
    for v in ask_volumes[:depth]:
        try:
            a += float(v or 0)
        except (TypeError, ValueError):
            pass
    total = b + a
    if total == 0:
        return None
    return (b - a) / total


def quote_columns(msg: dict) -> tuple[float | None, float | None, float | None, float | None]:
    """(mid_close, spread, imb_top1, imb_top5) tu mot tin QUOTE."""
    bid_prices = msg.get("bid_prices") or []
    ask_prices = msg.get("ask_prices") or []
    bid_volumes = msg.get("bid_volumes") or []
    ask_volumes = msg.get("ask_volumes") or []
    if not bid_prices or not ask_prices:
        return None, None, None, None
    try:
        best_bid = float(bid_prices[0])
        best_ask = float(ask_prices[0])
    except (TypeError, ValueError):
        return None, None, None, None
    mid = (best_bid + best_ask) / 2
    spread = best_ask - best_bid
    return (
        mid,
        spread,
        _imbalance(bid_volumes, ask_volumes, DEPTH_TOP1),
        _imbalance(bid_volumes, ask_volumes, DEPTH_TOP5),
    )


def build_minute_features(
    messages: Iterable[dict],
    session_date: date,
    stats: dict | None = None,
) -> list[MinuteRow]:
    """Dung bang dac trung 1 phut tu luong tin.

    `stats` (tuy chon): dict do nguoi goi truyen vao de nhan them so lieu bao cao
    (tin ngoai khung, so tin khong doc duoc moc thoi gian, danh sach do tre giay).
    Khong truyen thi ham thuan tuy theo nghia khong tac dung phu ra ngoai ket qua.
    """
    grid = session_minutes(session_date)
    idx_of = {m: i for i, m in enumerate(grid)}
    size = len(grid)

    last_quote: list[dict | None] = [None] * size
    n_quote = [0] * size
    n_trade = [0] * size
    n_other = [0] * size
    ofi = [0.0] * size
    trade_qty = [0.0] * size

    outside = 0
    bad_time = 0
    latencies: list[float] = []

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        ts = parse_trading_time(msg.get("trading_time"))
        if ts is None:
            bad_time += 1
            continue

        if stats is not None:
            recv = parse_recv_ts(msg.get("recv_ts"))
            if recv is not None:
                latencies.append((recv - ts).total_seconds())

        cat = classify_message(msg)
        i = _bucket_index(idx_of, ts, session_date)
        if i is None:
            outside += 1
            continue

        if cat == "QUOTE":
            n_quote[i] += 1
            last_quote[i] = msg
        elif cat == "TRADE":
            n_trade[i] += 1
            try:
                q = float(msg.get("quantity") or 0)
            except (TypeError, ValueError):
                q = 0.0
            trade_qty[i] += q
            side = str(msg.get("side", ""))
            if side == "B":
                ofi[i] += q
            elif side == "S":
                ofi[i] -= q
        else:
            n_other[i] += 1

    rows: list[MinuteRow] = []
    for i, minute in enumerate(grid):
        mid = spread = imb1 = imb5 = None
        q = last_quote[i]
        if q is not None:
            mid, spread, imb1, imb5 = quote_columns(q)
        rows.append(
            MinuteRow(
                minute=minute,
                n_quote=n_quote[i],
                n_trade=n_trade[i],
                n_other=n_other[i],
                mid_close=mid,
                spread=spread,
                imb_top1=imb1,
                imb_top5=imb5,
                ofi=ofi[i],
                trade_qty=trade_qty[i],
            )
        )

    if stats is not None:
        stats["outside_session"] = outside
        stats["bad_time"] = bad_time
        stats["latencies"] = latencies

    return rows


def longest_missing_run(
    rows: list[MinuteRow], key: Callable[[MinuteRow], bool]
) -> tuple[int, datetime | None]:
    """Khoang DAI NHAT gom cac phut LIEN TIEP trong GIO GIAO DICH thoa `key`.

    Tra (so phut, moc bat dau). Khoang phai lien tiep theo gio giao dich: 11:29 va
    13:00 noi nhau trong danh sach nhung KHONG lien tiep (nghi trua o giua), nen
    mot khoang thieu khong duoc phep bac qua nghi trua.
    Tra (0, None) neu khong co phut nao thoa `key`.
    """
    best_n = 0
    best_start: datetime | None = None
    cur_n = 0
    cur_start: datetime | None = None
    prev_minute: datetime | None = None

    for r in rows:
        contiguous = prev_minute is not None and (r.minute - prev_minute) == timedelta(minutes=1)
        prev_minute = r.minute

        if not key(r):
            cur_n = 0
            cur_start = None
            continue

        if cur_n == 0 or not contiguous:
            cur_start = r.minute
            cur_n = 1
        else:
            cur_n += 1

        if cur_n > best_n:
            best_n = cur_n
            best_start = cur_start

    return best_n, best_start


# --- Bao cao (muc 2 cua brief) ----------------------------------------------------


def _pct(part: int, whole: int) -> float:
    return (part / whole * 100.0) if whole else 0.0


def _values(rows: list[MinuteRow], field: str) -> list[float]:
    out = []
    for r in rows:
        v = getattr(r, field)
        if v is not None:
            out.append(float(v))
    return out


def _min_med_max(values: list[float]) -> str:
    if not values:
        return "khong co gia tri"
    s = sorted(values)
    return f"min {s[0]:,.3f} | trung vi {s[len(s) // 2]:,.3f} | max {s[-1]:,.3f}"


def _p90(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, round(0.9 * (len(s) - 1)))
    return s[idx]


def _fmt_minute(m: datetime | None) -> str:
    return m.strftime("%Y-%m-%d %H:%M") if m else "(khong co)"


def format_quality_report(
    filepath: Path | str,
    rows: list[MinuteRow],
    stats: dict | None = None,
    latency_values: list[float] | None = None,
) -> str:
    """Bao cao chat luong — day la SAN PHAM CHINH cua brief nay."""
    stats = stats or {}
    latencies = latency_values if latency_values is not None else []
    n = len(rows)
    out: list[str] = []
    add = out.append

    add("=" * 70)
    add("=== BAO CAO CHAT LUONG BANG DAC TRUNG SO LENH (BRIEF 93) ===")
    add("=" * 70)
    add(f"File: {filepath}")
    add(f"Gop phut theo: trading_time (gio san). Luoi: {n} o phut (150 sang + 90 chieu)")

    # 1. So hang + khoang phu
    with_data = [r for r in rows if (r.n_quote + r.n_trade + r.n_other) > 0]
    add("")
    add("[1] SO HANG VA DO PHU")
    add(f"- So hang dung duoc tren luoi: {n}")
    add(f"- So phut CO tin (bat ky loai): {len(with_data)} / {n} ({_pct(len(with_data), n):.1f}%)")
    if with_data:
        add(f"- Khoang thoi gian bao phu: {_fmt_minute(with_data[0].minute)} -> {_fmt_minute(with_data[-1].minute)}")
    else:
        add("- Khoang thoi gian bao phu: (khong co tin nao)")
    add(f"- Tong QUOTE: {sum(r.n_quote for r in rows):,} | Tong TRADE: {sum(r.n_trade for r in rows):,}"
        f" | Khac: {sum(r.n_other for r in rows):,}")
    add(f"- Tin ngoai khung phien (bo qua): {stats.get('outside_session', 0):,}")
    add(f"- Tin khong doc duoc trading_time: {stats.get('bad_time', 0):,}")

    # 2. Ty le thieu tung cot
    add("")
    add("[2] TY LE THIEU TUNG COT (None)")
    for field in ("mid_close", "spread", "imb_top1", "imb_top5"):
        missing = sum(1 for r in rows if getattr(r, field) is None)
        add(f"- {field:10s}: thieu {missing:4d} / {n} ({_pct(missing, n):5.1f}%)")
    add("- ofi       : KHONG BAO GIO None (khong co TRADE => 0, la gia tri that)")
    add("- trade_qty : KHONG BAO GIO None (nhu tren)")

    # 3. Khoang thieu dai nhat
    add("")
    add("[3] KHOANG THIEU DAI NHAT (phut lien tiep)")
    no_msg_n, no_msg_start = longest_missing_run(rows, key=lambda r: (r.n_quote + r.n_trade + r.n_other) == 0)
    no_q_n, no_q_start = longest_missing_run(rows, key=lambda r: r.n_quote == 0)
    add(f"- Khong co TIN NAO        : {no_msg_n} phut lien tiep, bat dau {_fmt_minute(no_msg_start)}")
    add(f"- Khong co QUOTE (co the con TRADE): {no_q_n} phut lien tiep, bat dau {_fmt_minute(no_q_start)}")

    # 4. Thong ke mo ta + phat hien gia tri vo ly
    add("")
    add("[4] THONG KE MO TA (min | trung vi | max) — de PHAT HIEN GIA TRI VO LY")
    for field in ("mid_close", "spread", "imb_top1", "imb_top5", "ofi", "trade_qty", "n_quote", "n_trade"):
        add(f"- {field:10s}: {_min_med_max(_values(rows, field))}")

    spreads = _values(rows, "spread")
    mids = _values(rows, "mid_close")
    imbs = _values(rows, "imb_top1") + _values(rows, "imb_top5")
    add("")
    add("  Phat hien gia tri vo ly:")
    add(f"  - spread < 0 (khong the): {sum(1 for v in spreads if v < 0)}")
    add(f"  - spread == 0            : {sum(1 for v in spreads if v == 0)}")
    add(f"  - |imb| > 1 (sai cong thuc): {sum(1 for v in imbs if abs(v) > 1 + 1e-9)}")
    add(f"  - mid ngoai 1900-2000    : {sum(1 for v in mids if v < 1900 or v > 2000)}")

    # 5. So hang dung duoc
    usable = sum(1 for r in rows if r.usable())
    add("")
    add("[5] SO HANG DUNG DUOC (co du mid_close + imb_top5 + ofi) — CON SO QUYET DINH")
    add(f"- {usable} / {n} hang ({_pct(usable, n):.1f}%)")
    add(f"- Nhan voi 20 phien (neu giu nhip nay): ~{usable * 20:,} hang")

    # 6. Phan bo do tre
    add("")
    add("[6] PHAN BO 'recv_ts - trading_time' (giay) — CHI BAO CON SO, KHONG KET LUAN NGUYEN NHAN")
    if latencies:
        s = sorted(latencies)
        med = s[len(s) // 2]
        p90 = _p90(latencies)
        add(f"- So tin do duoc: {len(latencies):,}")
        add(f"- min {s[0]:,.3f}s | trung vi {med:,.3f}s | p90 {p90:,.3f}s | max {s[-1]:,.3f}s")
        add(f"- So tin co do tre AM (recv som hon moc san): {sum(1 for v in s if v < 0):,}"
            f" ({_pct(sum(1 for v in s if v < 0), len(s)):.1f}%)")
        add(f"- So tin tre > 60s: {sum(1 for v in s if v > 60):,}")
    else:
        add("- Khong do duoc tin nao (thieu recv_ts hoac trading_time)")

    add("=" * 70)
    return "\n".join(out)


def iter_file_messages(filepath: Path | str) -> Iterator[dict]:
    """Doc luong .jsonl.gz chi de doc; bo qua dong trong va dong khong parse duoc."""
    with gzip.open(Path(filepath), mode="rt", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                msg = json.loads(s) if isinstance(s, str) else None
            except ValueError:
                continue
            if isinstance(msg, dict):
                yield msg


def session_date_from_filename(filepath: Path | str) -> date | None:
    """Lay ngay phien tu ten file <YYYY-MM-DD>.jsonl.gz."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", Path(filepath).name)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dung bang dac trung so lenh theo luoi 1 phut (Brief 93)"
    )
    parser.add_argument("file", help="Duong dan file .jsonl.gz cua so lenh")
    parser.add_argument(
        "--date",
        default=None,
        help="Ngay phien YYYY-MM-DD (mac dinh: lay tu ten file)",
    )
    args = parser.parse_args()

    p = Path(args.file)
    if not p.exists():
        print(f"[LOI] File khong ton tai: {p}", file=sys.stderr)
        sys.exit(2)

    session_date = date.fromisoformat(args.date) if args.date else session_date_from_filename(p)
    if session_date is None:
        print("[LOI] Khong xac dinh duoc ngay phien; hay truyen --date", file=sys.stderr)
        sys.exit(2)

    stats: dict[str, Any] = {}
    rows = build_minute_features(iter_file_messages(p), session_date, stats=stats)
    print(format_quality_report(p, rows, stats=stats, latency_values=stats.get("latencies", [])))


if __name__ == "__main__":
    main()
