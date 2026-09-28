"""Sàng lọc SMC (sweep / bos / fvg) trên cổ phiếu VN, nến ngày, giữ 2-8 tuần — Brief đợt 101.

Thiết kế ĐĂNG KÝ TRƯỚC (mọi tham số chốt trong brief, không đổi sau khi thấy dữ liệu):
- Nguồn: `bars_daily` qua Storage.read_daily_bars. Ngày của nến tính theo GIỜ VN
  (`bar_date` của đợt 99), KHÔNG dùng `.date()` trên datetime UTC.
- Niêm phong: đọc tới 2022-12-31; nến từ 2023-01-01 (giờ VN) trở đi thì NÉM LỖI.
- Vũ trụ, loại mã hỏng (`exclusions.txt`), bỏ nến rác (OHLC <= 0), thanh khoản >= 1 tỷ đồng
  (trung bình `close x volume` của 20 nến TRƯỚC t): y hệt đợt 99.
- Nến tín hiệu trong 2016-01-04 -> 2022-10-31 (khác đợt 99: khung giữ dài nhất ở đây là 40 phiên).
- Ba sự kiện SMC, CHỈ CHIỀU MUA, tính tại đóng cửa nến t, chỉ dùng nến <= t của cùng mã:
  (a) sweep: N = 20 phiên; L = min(low[t-20..t-1]); sự kiện khi low[t] < L và close[t] > L.
  (b) bos: swing high fractal k = 2 (`_la_swing_high` của đợt 98, chỉ được BIẾT từ nến j+2);
      S_h = swing high đã xác nhận gần nhất với j + 2 <= t; sự kiện khi close[t-1] <= S_h
      và close[t] > S_h.
  (c) fvg: sự kiện khi low[t] > high[t-2].
- Chung: volume[t] > 0 và đạt thanh khoản tại t; nghỉ 20 nến cho TỪNG loại, TỪNG mã;
  KHÔNG có bộ lọc xu hướng (SMC không yêu cầu nó).
- Vào tại open[t+1] (bỏ nếu mở giá trần theo sàn hoặc volume[t+1] = 0 -> `entry_status`);
  thoát tại close[t+k] với k thuộc {10, 20, 40}; ròng qua `net_return` (phí, thuế, trượt giá).
- Đối chứng CÙNG NGÀY: mọi mã khác trong vũ trụ đạt thanh khoản tại t và vào/thoát được theo
  §1.3 — KHÔNG có điều kiện xu hướng (khác đợt 99, vì sự kiện SMC cũng không có);
  `baseline_k` = trung bình r_k GỘP của rổ; `excess_k = r_k - baseline_k`; rổ < 5 mã thì bỏ
  khỏi phép so vượt trội (đếm và báo).
- Kiểm định: k = 20, một phía, bootstrap theo khối THÁNG DƯƠNG LỊCH (2.000 lần, seed 42) qua
  `bootstrap_by_month`; ba phép thử hiệu chỉnh Holm (0,05/3; 0,05/2; 0,05/1). Kết luận CÓ LỢI THẾ
  khi đạt Holm ở k = 20 VÀ trung bình r_20_ròng > 0 VÀ trung vị excess_20 > 0.
- k = 10 và k = 40: chỉ mô tả, KHÔNG kết luận. Dưới 100 lần hợp lệ: IT_SU_KIEN.

Không dùng pandas/numpy (repo không có). Dùng lại hàm của đợt 99 và đợt 98, KHÔNG chép lại.
"""

from __future__ import annotations

import argparse
import io
import sys
import time
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from scripts._db_common import resolve_dsn
from scripts.screen_vn30f_smc import _la_swing_high
from trading.calendar_vn import TZ
from trading.metrics import holm_adjust
from trading.models import Bar
from trading.stock_study import (
    BasketEntry,
    apply_cooldown,
    bar_date,
    basket_for_day,
    bootstrap_by_month,
    clean_bars,
    compute_targets,
    entry_status,
    excess_k,
    liquidity_ok,
    load_universe,
    make_basket_entry,
    month_key,
    net_return,
    validate_sealed_bars,
)
from trading.storage.db import Storage

# --- Nguong va tham so da dang ky truoc --------------------------------------------
IS_SIGNAL_START = date(2016, 1, 4)
IS_SIGNAL_END = date(2022, 10, 31)          # khac dot 99 (30/11) vi khung dai nhat la 40 phien
READ_FROM = datetime(2016, 1, 1, tzinfo=TZ)
READ_TO = datetime(2023, 1, 1, tzinfo=TZ)

SWEEP_N = 20                                 # so phien tinh day cho sweep
FRACTAL_K = 2                                # fractal cho swing high (mac dinh cua _la_swing_high)
MIN_TURNOVER_VND = 1_000_000_000.0           # 1 ty dong, y het dot 99
TURNOVER_WINDOW = 20                          # cua so thanh khoan, y het dot 99
COOLDOWN_BARS = 20                           # nghi 20 nen cho TUNG loai, TUNG ma

TARGET_KS = (10, 20, 40)                     # ~2, 4, 8 tuan
MAIN_K = 20                                  # khung chinh de ket luan
MIN_CONTROL = 5                              # ro doi chung toi thieu
MIN_EVENTS = 100                             # duoi nguong nay thi IT_SU_KIEN
N_BOOTSTRAP = 2000
BOOTSTRAP_SEED = 42
CI_LOW_PCT = 2.5                              # 2.5%, y het dot 99
CI_HIGH_PCT = 97.5                            # 97.5%, y het dot 99
ALPHA = 0.05
EVENT_TYPES = ("sweep", "bos", "fvg")


def in_is_signal(d: date) -> bool:
    """Ngay tin hieu co nam trong In-Sample khong (2016-01-04 -> 2022-10-31)."""
    return IS_SIGNAL_START <= d <= IS_SIGNAL_END


# --- Ba luat su kien SMC (duong THO, chua loc thanh khoan/volume/nghi) -------------

def sweep_candidates(bars: list[Bar], n: int = SWEEP_N) -> list[int]:
    """Sweep day: low[t] < min(low[t-n..t-1]) VA close[t] > day do. Nen t phai co du n nen truoc."""
    lows = [b.low for b in bars]
    out: list[int] = []
    for t in range(n, len(bars)):
        day_truoc = min(lows[t - n:t])
        if bars[t].low < day_truoc and bars[t].close > day_truoc:
            out.append(t)
    return out


def confirmed_swing_levels(bars: list[Bar], k: int = FRACTAL_K) -> list[float | None]:
    """Muc swing high DA XAC NHAN tai tung nen t (chi dung nen <= t).

    Tai nen t, swing tai j = t - k vua duoc xac nhan; neu j la swing high thi muc
    swing moi nhat = high[j], nguoc lai giu muc cu. Tra ve list cung do dai `bars`.
    """
    out: list[float | None] = [None] * len(bars)
    muc: float | None = None
    for t in range(len(bars)):
        j = t - k
        if j >= 0 and _la_swing_high(bars, j, k):
            muc = bars[j].high
        out[t] = muc
    return out


def bos_candidates(bars: list[Bar], k: int = FRACTAL_K) -> list[int]:
    """Pha dinh dao dong: close[t-1] <= S_h VA close[t] > S_h, S_h = swing da xac nhan (j+2 <= t)."""
    levels = confirmed_swing_levels(bars, k)
    out: list[int] = []
    for t in range(1, len(bars)):
        muc = levels[t]
        if muc is None:
            continue
        if bars[t - 1].close <= muc and bars[t].close > muc:
            out.append(t)
    return out


def fvg_candidates(bars: list[Bar]) -> list[int]:
    """Khoang trong gia tang: low[t] > high[t-2] (lon hon HAN, bang thi khong)."""
    return [t for t in range(2, len(bars)) if bars[t].low > bars[t - 2].high]


# --- Loc chung (volume, thanh khoan) + thoi gian nghi -------------------------------

def _dem(drop: dict[str, int] | None, key: str) -> None:
    if drop is not None:
        drop[key] = drop.get(key, 0) + 1


def _dat_chung(bars: list[Bar], t: int, min_turnover: float, drop: dict[str, int] | None) -> bool:
    """volume[t] > 0 VA dat thanh khoan tai t."""
    if bars[t].volume == 0:
        _dem(drop, "volume_0")
        return False
    if not liquidity_ok(bars, t, window=TURNOVER_WINDOW, min_turnover=min_turnover):
        _dem(drop, "duoi_thanh_khoan")
        return False
    return True


def _loc(bars: list[Bar], cand: list[int], min_turnover: float, drop: dict[str, int] | None) -> list[int]:
    kept = [t for t in cand if _dat_chung(bars, t, min_turnover, drop)]
    return apply_cooldown(kept, cooldown=COOLDOWN_BARS)


def find_sweep_events(
    bars: list[Bar], min_turnover: float = MIN_TURNOVER_VND, drop: dict[str, int] | None = None
) -> list[int]:
    """Su kien sweep cua MOT ma, da loc volume/thanh khoan va ap thoi gian nghi."""
    return _loc(bars, sweep_candidates(bars), min_turnover, drop)


def find_bos_events(
    bars: list[Bar], min_turnover: float = MIN_TURNOVER_VND, drop: dict[str, int] | None = None
) -> list[int]:
    """Su kien bos cua MOT ma, da loc volume/thanh khoan va ap thoi gian nghi."""
    return _loc(bars, bos_candidates(bars), min_turnover, drop)


def find_fvg_events(
    bars: list[Bar], min_turnover: float = MIN_TURNOVER_VND, drop: dict[str, int] | None = None
) -> list[int]:
    """Su kien fvg cua MOT ma, da loc volume/thanh khoan va ap thoi gian nghi."""
    return _loc(bars, fvg_candidates(bars), min_turnover, drop)


def find_all_events(
    bars: list[Bar], min_turnover: float = MIN_TURNOVER_VND, drop: dict[str, int] | None = None
) -> dict[str, list[int]]:
    """Ba loai su kien cua MOT ma; thoi gian nghi tinh RIENG tung loai."""
    return {
        "sweep": find_sweep_events(bars, min_turnover, drop),
        "bos": find_bos_events(bars, min_turnover, drop),
        "fvg": find_fvg_events(bars, min_turnover, drop),
    }


# --- Muc tieu: thieu khung nao thi dem khung do -------------------------------------

def missing_ks(tg: Mapping[int, float | None], ks: tuple[int, ...] = TARGET_KS) -> list[int]:
    """Cac khung khong co du du lieu (thieu nen sau t)."""
    return [k for k in ks if tg.get(k) is None]


def count_drops(tg: Mapping[int, float | None], drop: dict[str, int], ks: tuple[int, ...] = TARGET_KS) -> None:
    """Cong so khung thieu du lieu vao bo dem (thieu_du_lieu_<k>)."""
    for k in missing_ks(tg, ks):
        _dem(drop, f"thieu_du_lieu_{k}")

# --- Thong ke ------------------------------------------------------------------------

def median_of(vals: list[float]) -> float | None:
    """Trung vi (trung binh hai so giua khi so phan tu chan); None khi rong."""
    if not vals:
        return None
    s = sorted(vals)
    m = len(s) // 2
    if len(s) % 2 == 1:
        return s[m]
    return (s[m - 1] + s[m]) / 2.0


def top10_share(vals: list[float]) -> float | None:
    """Tong 10 gia tri LON NHAT chia tong (None khi rong hoac tong = 0)."""
    if not vals:
        return None
    total = sum(vals)
    if total == 0:
        return None
    return sum(sorted(vals, reverse=True)[:10]) / total


def verdict_for_event(
    n_valid: int, holm_pass: bool, mean_net: float | None, med_excess: float | None
) -> str:
    """Ket luan theo §1.5: du su kien, dat Holm, trung binh r_20_rong > 0, trung vi excess_20 > 0."""
    if n_valid < MIN_EVENTS:
        return f"IT_SU_KIEN (n = {n_valid} < {MIN_EVENTS})"
    if holm_pass and mean_net is not None and mean_net > 0 and med_excess is not None and med_excess > 0:
        return "CO_LOI_THE"
    return "KHONG_CO_LOI_THE"


# --- Ban ghi su kien va phep do ------------------------------------------------------

@dataclass(slots=True)
class EventRec:
    kind: str
    symbol: str
    day: date
    exchange: str
    t: int
    entry_open: float
    r: dict[int, float | None] = field(default_factory=dict)
    r_net: dict[int, float | None] = field(default_factory=dict)
    baseline: dict[int, float | None] = field(default_factory=dict)
    excess: dict[int, float | None] = field(default_factory=dict)


def _read(storage: Storage, sym: str) -> tuple[list[Bar], int]:
    """Doc + kiem niem phong + bo nen rac cho MOT ma."""
    bars = storage.read_daily_bars(sym, READ_FROM, READ_TO)
    if not bars:
        return [], 0
    validate_sealed_bars(bars)
    return clean_bars(bars)


def run_screen(
    storage: Storage,
    exclude_file: str = "exclusions.txt",
    limit: int = 0,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Chay toan bo phep do (mot lan). Tra ve dict ket qua de in bao cao."""
    t0 = time.perf_counter()
    universe, exchange, n_all, _excluded = load_universe(storage, exclude_file)
    if limit > 0:
        universe = universe[:limit]

    events: list[EventRec] = []
    symbols_kept = 0
    n_junk = 0
    drop: dict[str, int] = defaultdict(int)

    # Luot 1: su kien cua tung ma (chi dung du lieu cua ma do)
    t_read = 0.0
    for sym in universe:
        t1 = time.perf_counter()
        bars, junk = _read(storage, sym)
        t_read += time.perf_counter() - t1
        if not bars:
            continue
        n_junk += junk
        if len(bars) < SWEEP_N + 1:
            continue
        symbols_kept += 1
        ex = exchange.get(sym, "")
        for kind, idx in find_all_events(bars, drop=drop).items():
            for t in idx:
                d = bar_date(bars[t])
                if not in_is_signal(d):
                    drop["ngoai_IS"] += 1
                    continue
                st = entry_status(bars, t, ex)
                if st != "ok":
                    drop[st] += 1
                    continue
                tg = compute_targets(bars, t, ks=TARGET_KS)
                count_drops(tg, drop)
                entry_open = bars[t + 1].open
                events.append(
                    EventRec(
                        kind=kind,
                        symbol=sym,
                        day=d,
                        exchange=ex,
                        t=t,
                        entry_open=entry_open,
                        r=tg,
                        r_net={
                            k: (net_return(entry_open, bars[t + k].close) if tg.get(k) is not None else None)
                            for k in TARGET_KS
                        },
                    )
                )

    # Luot 2: ro doi chung cho NHUNG NGAY co su kien (doc lai du lieu, chi giu ngay su kien)
    event_day_ords = {e.day.toordinal() for e in events}
    basket_by_day: dict[int, dict[str, BasketEntry]] = defaultdict(dict)
    for sym in universe:
        bars, _junk = _read(storage, sym)
        if not bars:
            continue
        ex = exchange.get(sym, "")
        for i in range(len(bars)):
            od = bar_date(bars[i]).toordinal()
            if od not in event_day_ords:
                continue
            e = make_basket_entry(
                sym,
                bars,
                i,
                ex,
                min_turnover=MIN_TURNOVER_VND,
                window=TURNOVER_WINDOW,
                ks=TARGET_KS,
            )
            if e is not None:
                basket_by_day[od][sym] = e

    for ev in events:
        entries = basket_for_day(basket_by_day.get(ev.day.toordinal(), {}), ev.symbol)
        for k in TARGET_KS:
            baseline, excess, _n = excess_k(ev.r.get(k), entries, k, min_control=MIN_CONTROL)
            ev.baseline[k] = baseline
            ev.excess[k] = excess
            if excess is None:
                drop[f"ro_nho_{k}"] += 1

    # Thong ke theo tung loai su kien
    res: dict[str, Any] = {
        "n_symbols_all": n_all,
        "n_universe": len(universe),
        "n_symbols_kept": symbols_kept,
        "n_junk": n_junk,
        "drop": drop,
        "events": events,
        "types": {},
    }
    p_by_name: dict[str, float] = {}
    for kind in EVENT_TYPES:
        rows = [e for e in events if e.kind == kind]
        stats = {k: _stats(rows, k) for k in TARGET_KS}
        by_month: dict[tuple[int, int], list[float]] = defaultdict(list)
        xs: list[float] = []
        for e in rows:
            v = e.excess.get(MAIN_K)
            if v is not None:
                by_month[month_key(e.day)].append(v)
                xs.append(v)
        boot = bootstrap_by_month(
            dict(by_month),
            n=n_bootstrap,
            seed=seed,
            ci_low_pct=CI_LOW_PCT,
            ci_high_pct=CI_HIGH_PCT,
        )
        res["types"][kind] = {
            "n": len(rows),
            "by_year": _count_by(rows, lambda e: e.day.year),
            "by_exchange": _count_by(rows, lambda e: e.exchange),
            "stats": stats,
            "boot": boot,
            "top10": top10_share(xs),
        }
        if boot["p"] is not None:
            p_by_name[kind] = boot["p"]

    holm = holm_adjust(p_by_name, ALPHA) if p_by_name else {}
    for kind in EVENT_TYPES:
        t_res = res["types"][kind]
        st = t_res["stats"][MAIN_K]
        t_res["holm_pass"] = bool(holm.get(kind, False))
        t_res["verdict"] = verdict_for_event(
            st["n_excess"], bool(holm.get(kind, False)), st["mean_r_net"], st["median_excess"]
        )
    res["holm"] = holm
    res["elapsed"] = time.perf_counter() - t0
    res["t_read"] = t_read
    return res


def _count_by(rows: list[EventRec], fn: Any) -> dict[Any, int]:
    out: dict[Any, int] = defaultdict(int)
    for e in rows:
        out[fn(e)] += 1
    return dict(sorted(out.items(), key=lambda kv: str(kv[0])))


def _stats(rows: list[EventRec], k: int) -> dict[str, Any]:
    """Thong ke mot khung k cua mot loai su kien."""
    r = [v for v in (e.r.get(k) for e in rows) if v is not None]
    r_net = [v for v in (e.r_net.get(k) for e in rows) if v is not None]
    baseline = [v for v in (e.baseline.get(k) for e in rows) if v is not None]
    excess = [v for v in (e.excess.get(k) for e in rows) if v is not None]
    return {
        "n_event": len(rows),
        "n_excess": len(excess),
        "mean_r": (sum(r) / len(r)) if r else None,
        "median_r": median_of(r),
        "mean_r_net": (sum(r_net) / len(r_net)) if r_net else None,
        "mean_baseline": (sum(baseline) / len(baseline)) if baseline else None,
        "mean_excess": (sum(excess) / len(excess)) if excess else None,
        "median_excess": median_of(excess),
        "share_pos": (sum(1 for v in excess if v > 0) / len(excess)) if excess else None,
    }


# --- In bao cao ----------------------------------------------------------------------

def _fmt(v: float | None, spec: str = "+.4f") -> str:
    return format(v, spec) if v is not None else "n/a"


def _pct(v: float | None, spec: str = "+.2%") -> str:
    return format(v, spec) if v is not None else "n/a"


def print_report(res: dict[str, Any]) -> None:
    print("=== BÁO CÁO SÀNG LỌC SMC TRÊN CỔ PHIẾU VN, NẾN NGÀY (BRIEF ĐỢT 101) ===")
    print()
    print("[1] VŨ TRỤ MÃ")
    print(f"- Mã có nến trong bars_daily: {res['n_symbols_all']}")
    print(f"- Vũ trụ sau khi loại mã hỏng: {res['n_universe']} mã")
    print(f"- Mã đủ độ dài để xét (>= {SWEEP_N + 1} nến): {res['n_symbols_kept']}")
    print(f"- Số nến rác bị bỏ (OHLC <= 0): {res['n_junk']}")
    print(f"- Mốc nến tín hiệu: {IS_SIGNAL_START} -> {IS_SIGNAL_END}")
    print()
    print("[2] SỰ KIỆN THEO TỪNG LOẠI")
    for kind in EVENT_TYPES:
        t_res = res["types"][kind]
        print(f"- {kind}: {t_res['n']} sự kiện vào được lệnh trong IS")
        print(f"    theo năm: {t_res['by_year']}")
        print(f"    theo sàn: {t_res['by_exchange']}")
    print("- Số bị bỏ (chung cho cả ba loại):")
    for key in sorted(res["drop"]):
        print(f"    {key}: {res['drop'][key]}")
    print()
    print("[3] THỐNG KÊ THEO LOẠI × KHUNG (lợi nhuận thập phân, không phải %)")
    for kind in EVENT_TYPES:
        print(f"- {kind}")
        print("  k   | n có excess | TB r_gộp   | Trung vị r  | TB r_ròng  | TB baseline | TB excess  |"
              " Trung vị excess | tỷ lệ excess>0")
        for k in TARGET_KS:
            s = res["types"][kind]["stats"][k]
            print(f"  {k:<3} | {s['n_excess']:<11} | {_fmt(s['mean_r']):<10} | {_fmt(s['median_r']):<11} |"
                  f" {_fmt(s['mean_r_net']):<10} | {_fmt(s['mean_baseline']):<11} | {_fmt(s['mean_excess']):<10} |"
                  f" {_fmt(s['median_excess']):<15} | {_pct(s['share_pos'])}")
    print()
    print(f"[4] BA PHÉP THỬ CHÍNH (k = {MAIN_K}, một phía, bootstrap theo khối tháng, Holm)")
    for kind in EVENT_TYPES:
        t_res = res["types"][kind]
        b = t_res["boot"]
        print(f"- {kind}:")
        print(f"    số tháng dùng làm khối: {b['n_months']}; số sự kiện có excess_{MAIN_K}: "
              f"{t_res['stats'][MAIN_K]['n_excess']}")
        print(f"    trung bình excess_{MAIN_K}: {_fmt(b['mean'])}")
        print(f"    KTC 95% (bootstrap): [{_fmt(b['ci_low'])}, {_fmt(b['ci_high'])}]")
        print(f"    p gốc (tỷ lệ mẫu bootstrap có trung bình <= 0): {_fmt(b['p'], '.4f')}")
        print(f"    Holm (đạt hay không): {t_res['holm_pass']}")
        s = t_res["stats"][MAIN_K]
        print(f"    (a) đạt Holm: {t_res['holm_pass']}")
        print(f"    (b) trung bình r_{MAIN_K}_ròng > 0: {_fmt(s['mean_r_net'])}")
        print(f"    (c) trung vị excess_{MAIN_K} > 0: {_fmt(s['median_excess'])}")
        print(f"    => {t_res['verdict']}")
    print()
    print("[5] KIỂM ĐỘ LỆCH (tỷ trọng 10 sự kiện excess_20 lớn nhất trong tổng)")
    for kind in EVENT_TYPES:
        sh = res["types"][kind]["top10"]
        print(f"- {kind}: {_pct(sh) if sh is not None else 'n/a'}")
    print()
    print("[6] THỜI GIAN CHẠY")
    print(f"- Tổng: {res['elapsed']:.1f}s (đọc dữ liệu lượt 1: {res['t_read']:.1f}s)")
    print()
    print("=== KẾT LUẬN (theo mục 4 của brief) ===")
    co = [k for k in EVENT_TYPES if res["types"][k]["verdict"] == "CO_LOI_THE"]
    if co:
        print(f"- CÓ LỢI THẾ ở: {', '.join(co)} (theo cả ba điều kiện §1.5, k = {MAIN_K}).")
        print("  KHÔNG mở tập từ 2023, KHÔNG xây chiến lược. Chờ Claude quyết (mở một lần duy nhất).")
    else:
        print("- KHÔNG sự kiện nào đạt -> SMC dạng máy trên cổ phiếu, giữ 2-8 tuần: KHÔNG có lợi thế "
              "so với cổ phiếu đủ thanh khoản cùng ngày, sau chi phí.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Sàng lọc SMC trên cổ phiếu VN nến ngày (Brief đợt 101)")
    ap.add_argument("--dsn", default=None, help="DSN Postgres (mặc định lấy từ .env)")
    ap.add_argument("--exclude-file", default="exclusions.txt")
    ap.add_argument("--limit", type=int, default=0, help="Giới hạn số mã (0 = tất cả)")
    args = ap.parse_args()

    storage = Storage(resolve_dsn(args.dsn))
    res = run_screen(storage, exclude_file=args.exclude_file, limit=args.limit)
    print_report(res)


if __name__ == "__main__":
    main()
