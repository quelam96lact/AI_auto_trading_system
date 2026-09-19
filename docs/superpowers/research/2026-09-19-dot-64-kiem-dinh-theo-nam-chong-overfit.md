# Báo cáo kỹ thuật Đợt 64 — Kiểm định theo từng năm, chống overfit cho buy-and-hold có nhịp

- **Ngày thực hiện:** 19/09/2026
- **Người thực thi:** Gemini Flash 3.8
- **Người bàn giao & kiểm định:** Claude (auditor)
- **Base commit:** `177575c`

---

## 1. Bảng số liệu kiểm định 11 năm (2016 – 2026)

Lệnh thực thi:
```bash
uv run python scripts/measure_regime_hold.py --task by-year --exclude-file exclusions.txt
```

Nguyên văn kết quả đo lường:

```text
================================================================================
ĐO LƯỜNG CHIẾN LƯỢC BUY-AND-HOLD THEO NHỊP THỊ TRƯỜNG (BRIEF 61)
Rổ mã: 1308 mã (đã loại 246 mã theo exclusions.txt)
Vốn giả lập: 1,000,000,000 VNĐ / mã | Phí: 0.25% | Thuế bán: 0.10% | Trượt: 5 bps
================================================================================

=======================================================================================================================================
BẢNG KIỂM ĐỊNH THEO TỪNG NĂM: BUY-AND-HOLD CÓ NHỊP VS B&H THUẦN
=======================================================================================================================================
Năm   | %ngày HOLD  | Số lần đổi trạng thái  | PnL có nhịp (tỷ)   | PnL B&H thuần (tỷ)  | Chênh lệch (tỷ)  | MDD có nhịp  | MDD B&H    | skipped_buys
-----------------------------------------------------------------------------------------------------------------------------------------------------
2016  | 99.6%       | 2 (2M/1B)              |             +86.35 |              +96.25 |            -9.90 |      -10.76% |    -10.76% |            0
2017  | 100.0%      | 0 (1M/0B)              |            +188.41 |             +188.41 |            +0.00 |      -14.29% |    -14.29% |            0
2018  | 76.8%       | 8 (5M/4B)              |              -3.92 |              +12.13 |           -16.04 |      -38.45% |    -38.45% |            0
2019  | 100.0%      | 0 (1M/0B)              |            +107.25 |             +107.25 |            -0.00 |       -4.01% |     -4.01% |            0
2020  | 75.0%       | 12 (7M/6B)             |            +221.06 |             +338.06 |          -117.00 |      -40.23% |    -37.92% |            0
2021  | 100.0%      | 0 (1M/0B)              |           +1234.58 |            +1234.58 |            +0.00 |       -9.43% |     -9.43% |            0
2022  | 32.9%       | 1 (1M/1B)              |            -138.77 |             -329.43 |          +190.66 |      -20.46% |    -38.58% |            0
2023  | 61.8%       | 3 (2M/1B)              |             +56.77 |             +220.16 |          -163.39 |      -32.59% |    -33.34% |            0
2024  | 99.6%       | 2 (2M/1B)              |            +175.30 |             +186.91 |           -11.62 |      -35.88% |    -35.88% |            0
2025  | 98.0%       | 6 (4M/3B)              |            +140.95 |             +194.59 |           -53.64 |      -23.99% |    -22.82% |            0
2026  | 39.5%       | 9 (5M/5B)              |             -92.72 |              -59.13 |           -33.59 |      -30.66% |    -28.58% |            0
-----------------------------------------------------------------------------------------------------------------------------------------------------
thắng B&H 1/11 năm, thua 10/11 năm
=======================================================================================================================================
```

*Ghi chú về vốn:* Vốn được reset về 1 tỷ VNĐ / mã vào đầu mỗi năm (không dồn lãi/lỗ năm trước sang năm sau, mỗi năm là một phép đo độc lập). Do đó tổng PnL cộng dồn 11 năm độc lập khác với đường vốn liên tục của `--task all`.

---

## 2. Nhận xét mô tả số liệu (Thuần mô tả, không kết luận)

- **Tỷ lệ số năm thắng / thua:** Chiến lược có PnL cao hơn B&H thuần ở **1/11 năm** (năm 2022). Ở **10/11 năm** còn lại, chiến lược có PnL thấp hơn hoặc bằng B&H thuần:
  - 3 năm hòa tuyệt đối (+0.00 tỷ): 2017, 2019, 2021 (thị trường 100% ngày HOLD, không có nhịp CASH nào).
  - 7 năm thua B&H: 2016 (-9.90 tỷ), 2018 (-16.04 tỷ), 2020 (-117.00 tỷ), 2023 (-163.39 tỷ), 2024 (-11.62 tỷ), 2025 (-53.64 tỷ), 2026 (-33.59 tỷ).
- **Năm chênh lệch dương lớn nhất:** Năm **2022** (+190.66 tỷ). Tỷ lệ ngày HOLD năm này thấp nhất (32.9%), chiến lược chỉ lỗ -138.77 tỷ so với mức lỗ -329.43 tỷ của B&H thuần. MDD được kiềm chế ở -20.46% so với -38.58% của B&H.
- **Các năm chênh lệch âm lớn nhất:**
  - Năm **2023**: chênh lệch **-163.39 tỷ** (chiến lược đạt +56.77 tỷ trong khi B&H đạt +220.16 tỷ; %ngày HOLD là 61.8%).
  - Năm **2020**: chênh lệch **-117.00 tỷ** (chiến lược đạt +221.06 tỷ trong khi B&H đạt +338.06 tỷ; %ngày HOLD là 75.0%, số lần đổi trạng thái là 12 lần).
  - Năm **2025**: chênh lệch **-53.64 tỷ** (chiến lược đạt +140.95 tỷ so với +194.59 tỷ của B&H).

---

## 3. Git diff `scripts/measure_regime_hold.py`

Khẳng định: 4 hàm cốt lõi `simulate_symbol_regime_hold`, `run_regime_hold_benchmark`, `compute_max_drawdown`, `count_regime_switches` **không thay đổi một dòng**. Chỉ thêm hàm phụ trợ `get_year_ranges` và nhánh `by-year` trong `main()`.

```diff
diff --git a/scripts/measure_regime_hold.py b/scripts/measure_regime_hold.py
index 0f9fd06..05924f0 100644
--- a/scripts/measure_regime_hold.py
+++ b/scripts/measure_regime_hold.py
@@ -337,6 +337,24 @@ def run_regime_hold_benchmark(
     }
 
 
+def get_year_ranges(
+    start_year: int = 2016, end_year: int = 2026
+) -> list[tuple[int, datetime, datetime]]:
+    """Tạo danh sách các khoảng thời gian theo từng năm dương lịch (Brief 64).
+
+    - 2016 đến 2025: trọn năm [YYYY-01-01, YYYY-12-31 23:59:59] (giờ TZ).
+    - 2026: cắt tại 28/08/2026 [2026-01-01, 2026-08-28 23:59:59] khớp ranh giới out_to.
+    """
+    ranges = []
+    for y in range(start_year, end_year + 1):
+        if y == 2026:
+            end_dt = datetime(2026, 8, 28, 23, 59, 59, tzinfo=TZ)
+        else:
+            end_dt = datetime(y, 12, 31, 23, 59, 59, tzinfo=TZ)
+        ranges.append((y, datetime(y, 1, 1, tzinfo=TZ), end_dt))
+    return ranges
+
+
 def main() -> None:
     ap = argparse.ArgumentParser(
         description="Đo lường Buy-and-Hold theo nhịp thị trường (Brief 61)"
@@ -348,7 +366,11 @@ def main() -> None:
         default="docs/superpowers/research/2026-09-02-breadth-daily.csv",
     )
     ap.add_argument("--capital", type=float, default=DEFAULT_CAPITAL)
-    ap.add_argument("--task", choices=["in-sample", "out-sample", "all"], default="all")
+    ap.add_argument(
+        "--task",
+        choices=["in-sample", "out-sample", "all", "by-year"],
+        default="all",
+    )
     args = ap.parse_args()
 
     dsn = resolve_dsn(args.dsn)
@@ -451,6 +473,53 @@ def main() -> None:
         print(f"  Max Drawdown có nhịp     : {out_res['strat_mdd']:>18.2%}")
         print(f"  Max Drawdown B&H thuần   : {out_res['bh_mdd']:>18.2%}")
 
+    # 3. KIỂM ĐỊNH THEO TỪNG NĂM: 2016 -> 2026 (Brief 64)
+    if args.task in ["by-year"]:
+        year_ranges = get_year_ranges(2016, 2026)
+
+        print("\n" + "=" * 135)
+        print("BẢNG KIỂM ĐỊNH THEO TỪNG NĂM: BUY-AND-HOLD CÓ NHỊP VS B&H THUẦN")
+        print("=" * 135)
+        header = (
+            f"{'Năm':<5} | {'%ngày HOLD':<11} | {'Số lần đổi trạng thái':<22} | "
+            f"{'PnL có nhịp (tỷ)':<18} | {'PnL B&H thuần (tỷ)':<19} | "
+            f"{'Chênh lệch (tỷ)':<16} | {'MDD có nhịp':<12} | {'MDD B&H':<10} | {'skipped_buys':<12}"
+        )
+        print(header)
+        print("-" * len(header))
+
+        wins = 0
+        losses = 0
+        for y, y_frm, y_to in year_ranges:
+            y_res = run_regime_hold_benchmark(
+                storage, symbols, y_frm, y_to, prior_regime_by_date, args.capital
+            )
+            st = y_res["regime_stats"]
+            hold_pct = f"{st['hold_ratio']:.1%}"
+            switches = f"{st['switches']} ({st['buy_switches']}M/{st['sell_switches']}B)"
+            strat_pnl_ty = y_res["strat_pnl"] / 1e9
+            bh_pnl_ty = y_res["bh_pnl"] / 1e9
+            diff_ty = y_res["diff_bh"] / 1e9
+            strat_mdd = f"{y_res['strat_mdd']:.2%}"
+            bh_mdd = f"{y_res['bh_mdd']:.2%}"
+            skipped = y_res.get("skipped_buys", 0)
+
+            if y_res["strat_pnl"] > y_res["bh_pnl"]:
+                wins += 1
+            else:
+                losses += 1
+
+            print(
+                f"{y:<5} | {hold_pct:<11} | {switches:<22} | "
+                f"{strat_pnl_ty:>+18.2f} | {bh_pnl_ty:>+19.2f} | "
+                f"{diff_ty:>+16.2f} | {strat_mdd:>12} | {bh_mdd:>10} | {skipped:>12}"
+            )
+
+        print("-" * len(header))
+        total_years = len(year_ranges)
+        print(f"thắng B&H {wins}/{total_years} năm, thua {losses}/{total_years} năm")
+        print("=" * 135)
+
 
 if __name__ == "__main__":
     main()
```

---

## 4. File test mới `tests/test_regime_hold_by_year.py`

Toàn bộ nội dung:

```python
"""Unit test kiểm chứng logic chia ranh giới theo năm cho Buy-and-Hold theo nhịp (Brief 64).

Yêu cầu Task 2.1:
1. Dựng bars giả trải dài đúng 2 năm dương lịch liên tiếp (2023-2024), có phiên sát ranh giới 31/12 và 01/01.
2. Chạy hàm chia theo năm (get_year_ranges) cho 2 năm này và chạy benchmark.
3. Độc lập, gọi run_regime_hold_benchmark thủ công 2 lần với ranh giới [2023-01-01, 2023-12-31 23:59:59]
   và [2024-01-01, 2024-12-31 23:59:59].
4. Khẳng định kết quả hai cách giống hệt nhau ở mọi trường metrics: strat_pnl, bh_pnl, strat_mdd,
   bh_mdd, total_buy_trades, total_sell_trades.
"""

from datetime import date, datetime

import pytest

from scripts.measure_regime_hold import (
    TZ,
    get_year_ranges,
    run_regime_hold_benchmark,
)
from trading.models import Bar


class DummyStorage:
    """Mock storage cho phép lọc daily bars theo start <= ts < end."""

    def __init__(self, bars: list[Bar]):
        self._bars = bars

    def read_daily_bars(
        self, symbol: str, start: datetime, end: datetime
    ) -> list[Bar]:
        return [
            b
            for b in self._bars
            if b.symbol == symbol and start <= b.ts < end
        ]


def _make_bar(d: date, open_p: float, close_p: float, symbol: str = "TEST") -> Bar:
    dt = datetime(d.year, d.month, d.day, 15, 0, 0, tzinfo=TZ)
    return Bar(
        symbol=symbol,
        ts=dt,
        open=open_p,
        high=max(open_p, close_p) * 1.01,
        low=min(open_p, close_p) * 0.99,
        close=close_p,
        volume=100_000.0,
    )


def test_ranh_gioi_chia_nam_chinh_xac_khong_lech_va_khong_ro_ri():
    """Kiểm chứng chia năm độc lập khớp 100% với gọi thủ công từng ranh giới năm."""
    # 1. Dựng bars giả trải dài 2 năm 2023 - 2024, có phiên sát ranh giới 31/12/2023 và 01/01/2024
    d_2023_1 = date(2023, 3, 15)
    d_2023_2 = date(2023, 8, 20)
    d_2023_edge = date(2023, 12, 31)  # Bar sát ranh giới cuối năm 2023

    d_2024_edge = date(2024, 1, 1)   # Bar sát ranh giới đầu năm 2024
    d_2024_1 = date(2024, 6, 10)
    d_2024_2 = date(2024, 12, 31)   # Bar cuối năm 2024

    bars = [
        _make_bar(d_2023_1, 10.0, 12.0),
        _make_bar(d_2023_2, 12.0, 11.0),
        _make_bar(d_2023_edge, 11.0, 15.0),
        _make_bar(d_2024_edge, 20.0, 22.0),
        _make_bar(d_2024_1, 22.0, 18.0),
        _make_bar(d_2024_2, 18.0, 25.0),
    ]

    prior_regime_by_date = {
        d_2023_1: "RISK_ON",
        d_2023_2: "RISK_OFF",
        d_2023_edge: "RISK_ON",
        d_2024_edge: "RISK_ON",
        d_2024_1: "RISK_OFF",
        d_2024_2: "RISK_ON",
    }

    storage = DummyStorage(bars)
    symbols = ["TEST"]
    capital = 1_000_000_000.0

    # 2. Chạy qua logic get_year_ranges cho 2 năm 2023-2024
    year_ranges = get_year_ranges(2023, 2024)
    assert len(year_ranges) == 2

    by_year_results = {}
    for y, y_frm, y_to in year_ranges:
        res = run_regime_hold_benchmark(
            storage, symbols, y_frm, y_to, prior_regime_by_date, capital
        )
        by_year_results[y] = res

    # 3. Chạy độc lập thủ công 2 lần với đúng ranh giới
    manual_2023_frm = datetime(2023, 1, 1, tzinfo=TZ)
    manual_2023_to = datetime(2023, 12, 31, 23, 59, 59, tzinfo=TZ)
    res_manual_2023 = run_regime_hold_benchmark(
        storage, symbols, manual_2023_frm, manual_2023_to, prior_regime_by_date, capital
    )

    manual_2024_frm = datetime(2024, 1, 1, tzinfo=TZ)
    manual_2024_to = datetime(2024, 12, 31, 23, 59, 59, tzinfo=TZ)
    res_manual_2024 = run_regime_hold_benchmark(
        storage, symbols, manual_2024_frm, manual_2024_to, prior_regime_by_date, capital
    )

    # 4. Khẳng định kết quả hai cách giống hệt nhau ở từng metrics
    metric_keys = [
        "strat_pnl",
        "bh_pnl",
        "strat_mdd",
        "bh_mdd",
        "total_buy_trades",
        "total_sell_trades",
    ]

    # Kiểm tra năm 2023
    for key in metric_keys:
        assert by_year_results[2023][key] == pytest.approx(res_manual_2023[key]), (
            f"Năm 2023 lệch ở metric {key}: {by_year_results[2023][key]} != {res_manual_2023[key]}"
        )

    # Kiểm tra năm 2024
    for key in metric_keys:
        assert by_year_results[2024][key] == pytest.approx(res_manual_2024[key]), (
            f"Năm 2024 lệch ở metric {key}: {by_year_results[2024][key]} != {res_manual_2024[key]}"
        )

    # Đảm bảo bar ngày 31/12/2023 thực sự được xử lý trong 2023
    bars_in_2023 = storage.read_daily_bars("TEST", year_ranges[0][1], year_ranges[0][2])
    assert len(bars_in_2023) == 3
    assert bars_in_2023[-1].ts.date() == date(2023, 12, 31)

    # Đảm bảo bar ngày 01/01/2024 thực sự được xử lý trong 2024
    bars_in_2024 = storage.read_daily_bars("TEST", year_ranges[1][1], year_ranges[1][2])
    assert len(bars_in_2024) == 3
    assert bars_in_2024[0].ts.date() == date(2024, 1, 1)
```

---

## 5. Bằng chứng test phân biệt được (Mục 2.2)

### 5.1. Khi tạm chỉnh sai ranh giới năm thành `30/12`: ĐỎ (FAILED)

Tạm sửa trong `get_year_ranges`:
```python
        else:
            end_dt = datetime(y, 12, 30, 23, 59, 59, tzinfo=TZ)
```

Chạy `uv run pytest tests/test_regime_hold_by_year.py -v`:

```text
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- D:\My_Vault_Obsidian\Project\AI_auto_trading_system\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\My_Vault_Obsidian\Project\AI_auto_trading_system
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

tests/test_regime_hold_by_year.py::test_ranh_gioi_chia_nam_chinh_xac_khong_lech_va_khong_ro_ri FAILED [100%]

================================== FAILURES ===================================
_________ test_ranh_gioi_chia_nam_chinh_xac_khong_lech_va_khong_ro_ri _________

    def test_ranh_gioi_chia_nam_chinh_xac_khong_lech_va_khong_ro_ri():
...
        # Kiểm tra năm 2023
        for key in metric_keys:
>           assert by_year_results[2023][key] == pytest.approx(res_manual_2023[key]), (
                f"Năm 2023 lệch ở metric {key}: {by_year_results[2023][key]} != {res_manual_2023[key]}"
            )
E           AssertionError: Năm 2023 lệch ở metric strat_pnl: 191625733.16257095 != 613604415.4508212
E           assert 191625733.16257095 == 613604415.4508212 ± 613.604
E             
E             comparison failed
E             Obtained: 191625733.16257095
E             Expected: 613604415.4508212 ± 613.604

tests\test_regime_hold_by_year.py:123: AssertionError
---------------------------- Captured stderr call -----------------------------
    Đã đo 1/1 mã...
    Đã đo 1/1 mã...
    Đã đo 1/1 mã...
    Đã đo 1/1 mã...
=========================== short test summary info ===========================
FAILED tests/test_regime_hold_by_year.py::test_ranh_gioi_chia_nam_chinh_xac_khong_lech_va_khong_ro_ri
============================== 1 failed in 0.27s ==============================
```

### 5.2. Khi khôi phục về chuẩn `31/12`: XANH (PASSED)

Khôi phục `end_dt = datetime(y, 12, 31, 23, 59, 59, tzinfo=TZ)`:

```text
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- D:\My_Vault_Obsidian\Project\AI_auto_trading_system\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\My_Vault_Obsidian\Project\AI_auto_trading_system
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 1 item

tests/test_regime_hold_by_year.py::test_ranh_gioi_chia_nam_chinh_xac_khong_lech_va_khong_ro_ri PASSED [100%]

============================== 1 passed in 0.17s ==============================
```

---

## 6. Kết quả hồi quy tổng (Mục 2.4)

### 6.1. Ruff linter
Lệnh: `uv run ruff check trading tests scripts`
Kết quả:
```text
All checks passed!
```

### 6.2. Pytest suite
Lệnh: `uv run pytest -m "not integration" -q`
Kết quả:
```text
703 passed, 113 deselected in 16.68s
```
Tổng số test passed tăng từ 699 lên 703:
- +1 test `test_send_tra_none_bi_coi_la_that_bai` (`tests/test_docker_down_alert.py`)
- +2 test logging (`tests/test_logging_setup.py`)
- +1 test chia năm ranh giới (`tests/test_regime_hold_by_year.py`)
Không có bất kỳ test cũ nào bị hồi quy hay hỏng hóc.
