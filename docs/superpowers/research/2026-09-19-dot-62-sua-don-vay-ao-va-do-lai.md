# Báo cáo Đợt 62: Sửa đòn bẩy ảo, đo lại Buy-and-Hold theo nhịp thị trường

> **Người thực hiện:** Senior Dev / AI Engineer  
> **Thời điểm thực hiện:** 2026-09-19  
> **Tài liệu tham chiếu:** `docs/superpowers/plans/2026-09-19-brief-dot-62-sua-don-vay-ao-va-do-lai.md`  
> **Căn cứ từ chối đợt 61:** `docs/superpowers/research/2026-09-19-dot-61-audit-tu-choi-don-vay-ao.md`  
> **Đối tượng thẩm định:** Claude (Planner / Auditor)  

---

## 1. Cơ chế sửa lỗi đòn bẩy ảo (Task 1)

Lỗi ở đợt 61: `simulate_symbol_regime_hold` tính `qty` cố định 1 lần duy nhất ở đầu kỳ 10 năm từ vốn ban đầu, rồi tái sử dụng cho mọi lần mua lại sau đó. Khi giá mua lại cao hơn giá bán trước đó, tài khoản mua cổ phiếu vượt quá số tiền mặt đang có, dẫn đến `cash < 0` (đòn bẩy ảo).

### Quy tắc sửa đổi đã đóng băng:
1. **Tính lại `qty` từ `cash` thực tế tại thời điểm mua:** Mỗi khi trạng thái chuyển từ `TIỀN MẶT (CASH) → NẮM GIỮ (HOLD)`:
   ```python
   buy_p = Open(d) * (1 + slip)
   buy_qty = int(cash // (buy_p * (1 + fee_rate)))
   buy_qty = (buy_qty // lot_size) * lot_size
   ```
2. **Kiểm tra sức mua tối thiểu:**
   - Nếu `buy_qty < lot_size` hoặc `buy_qty <= 0`: Không mua, giữ nguyên trạng thái TIỀN MẶT (`pos = 0`), ghi nhận `skipped_buys += 1`.
   - Nếu đủ tiền: Trừ tiền `cash -= buy_qty * buy_p * (1 + fee_rate)`, gán `pos = buy_qty`, `buy_trades += 1`.
3. **Bất biến bắt buộc:** `cash >= 0.0` tại mọi thời điểm, trong mọi bước giao dịch và mark-to-market. Đã thêm kiểm tra `assert cash >= 0.0` và ghi nhận `min_cash_seen = min(min_cash_seen, cash)`.
4. **Giữ nguyên ranh giới:** Chỉ sửa bên trong `simulate_symbol_regime_hold` của `scripts/measure_regime_hold.py`. Toàn bộ phần đọc dữ liệu, tính B&H thuần (`bh_pnl`, `bh_daily_equity`), đếm chuyển trạng thái (`count_regime_switches`), và hàm chạy benchmark/CLI giữ nguyên không đổi một dòng.

---

## 2. Bằng chứng kiểm thử phân biệt được (Task 1.3.3)

### 2.1. Test mới `test_cash_khong_bao_gio_am`
Dựng kịch bản theo đúng kiểm toán của Claude: Mua tại 10.0, bán tại 10.0, mua lại tại 30.0 (giá tăng gấp 3 lần).
- Vốn gốc: 1.000.000 VNĐ.

### 2.2. Khi chạy với logic cũ (Tái hiện lỗi đòn bẩy ảo)
Lệnh chạy: `uv run pytest tests/test_regime_hold.py -k test_cash_khong_bao_gio_am`
**Output đỏ nguyên văn:**
```
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0
rootdir: D:\My_Vault_Obsidian\Project\AI_auto_trading_system
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 5 items / 4 deselected / 1 selected

tests\test_regime_hold.py F                                              [100%]

================================== FAILURES ===================================
_________________________ test_cash_khong_bao_gio_am __________________________

    def test_cash_khong_bao_gio_am():
        """Test 5 (bắt buộc, Brief 62): Dựng kịch bản audit (bán thấp, mua lại cao gấp 3 lần),
        khẳng định cash không âm ở bất kỳ thời điểm nào trong suốt mô phỏng.
        """
        capital = 1_000_000.0
        dates = [
            date(2026, 1, 1),
            date(2026, 1, 4),
            date(2026, 1, 7),
            date(2026, 1, 10),
        ]
        bars = [
            _make_bar(dates[0], 10.0, 10.0),  # Mua ở 10.0
            _make_bar(dates[1], 10.0, 10.0),  # Bán ở 10.0
            _make_bar(dates[2], 30.0, 30.0),  # Mua lại ở 30.0 (giá cao gấp 3 lần)
            _make_bar(dates[3], 35.0, 35.0),  # Cuối kỳ đóng ở 35.0
        ]
        prior_regime = {
            dates[0]: "RISK_ON",
            dates[1]: "RISK_OFF",
            dates[2]: "RISK_ON",
            dates[3]: "RISK_ON",
        }
        res = simulate_symbol_regime_hold(bars, prior_regime, capital=capital)
>       assert res["min_cash_seen"] >= 0.0
E       assert -2006955.2402499993 >= 0.0

tests\test_regime_hold.py:162: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_regime_hold.py::test_cash_khong_bao_gio_am - assert -200695...
======================= 1 failed, 4 deselected in 0.34s =======================
```
*Kết quả:* Test phát hiện chính xác `cash` bị âm `-2.006.955,24 VNĐ` (-200,7% vốn gốc) như báo cáo kiểm toán chỉ ra.

### 2.3. Khi chạy với logic mới (Đã sửa)
Lệnh chạy: `uv run pytest tests/test_regime_hold.py -v`
```
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- D:\My_Vault_Obsidian\Project\AI_auto_trading_system\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\My_Vault_Obsidian\Project\AI_auto_trading_system
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 5 items

tests/test_regime_hold.py::test_khong_doi_khi_regime_khong_doi PASSED    [ 20%]
tests/test_regime_hold.py::test_mua_ban_dung_gia_va_phi PASSED           [ 40%]
tests/test_regime_hold.py::test_khong_nhin_trom_tuong_lai PASSED         [ 60%]
tests/test_regime_hold.py::test_max_drawdown_dung PASSED                 [ 80%]
tests/test_regime_hold.py::test_cash_khong_bao_gio_am PASSED             [100%]

============================== 5 passed in 0.24s ==============================
```
Toàn bộ 5/5 test đều XANH:
- `test_mua_ban_dung_gia_va_phi` (Test 2) đã được cập nhật đúng: nhịp 2 tính `qty2` từ `cash2` sau nhịp 1.
- Ba test cũ (Test 1, Test 3, Test 4) giữ nguyên hành vi và đều XANH.
- Test 5 khẳng định `min_cash_seen >= 0.0`.

---

## 3. Bảng đối chiếu Task 2: Số cũ (Bị từ chối) vs Số mới (Chuẩn hóa)

Lệnh thực thi độc lập:
```powershell
uv run python scripts/measure_regime_hold.py --task all --exclude-file exclusions.txt
```

### 3.1. Kỳ Trong Mẫu (In-Sample: 2016-01-04 → 2022-12-31 | 1.752 phiên)

| Tiêu chí | Đợt 61 (Cũ - Bị từ chối) | Đợt 62 (Mới - Đã sửa đòn bẩy ảo) | Thay đổi (Đợt 62 vs Đợt 61) |
|---|:---:|:---:|:---:|
| **PnL Buy-and-Hold có nhịp** | **+1.463.554.350.971 VNĐ**<br>(**+1.463,55 tỷ**) | **+1.407.487.492.799 VNĐ**<br>(**+1.407,49 tỷ**) | **-56.066.858.172 VNĐ**<br>(**-56,07 tỷ** do trừ đòn bẩy ảo) |
| **PnL Mua-và-giữ thuần** | **+1.007.120.339.803 VNĐ**<br>(**+1.007,12 tỷ**) | **+1.007.120.339.803 VNĐ**<br>(**+1.007,12 tỷ**) | **0 VNĐ** (Giữ nguyên 100% không đổi) |
| **Chênh lệch (Có nhịp vs Thuần)** | **+456,43 tỷ** | **+400,37 tỷ** | **-56,07 tỷ** |
| **Max Drawdown Có nhịp** | **-40.30%** | **-40.10%** | **+0.20%** (Cải thiện nhẹ) |
| **Max Drawdown B&H thuần** | **-46.99%** | **-46.99%** | **0.00%** (Giữ nguyên 100% không đổi) |
| **Tổng số lần `skipped_buys`** | *Chưa đo* | **0 lần** (trên toàn bộ 1.308 mã) | Không có mã nào hết tiền |

### 3.2. Kỳ Ngoài Mẫu (Out-of-Sample: 2023-01-01 → 2026-08-28 | 910 phiên)

| Tiêu chí | Đợt 61 (Cũ - Bị từ chối) | Đợt 62 (Mới - Đã sửa đòn bẩy ảo) | Thay đổi (Đợt 62 vs Đợt 61) |
|---|:---:|:---:|:---:|
| **PnL Buy-and-Hold có nhịp** | **+323.719.766.624 VNĐ**<br>(**+323,72 tỷ**) | **+312.721.170.447 VNĐ**<br>(**+312,72 tỷ**) | **-10.998.596.177 VNĐ**<br>(**-11,00 tỷ** do trừ đòn bẩy ảo) |
| **PnL Mua-và-giữ thuần** | **+657.939.888.607 VNĐ**<br>(**+657,94 tỷ**) | **+657.939.888.607 VNĐ**<br>(**+657,94 tỷ**) | **0 VNĐ** (Giữ nguyên 100% không đổi) |
| **Chênh lệch (Có nhịp vs Thuần)** | **-334,22 tỷ** | **-345,22 tỷ** | **-11,00 tỷ** |
| **Max Drawdown Có nhịp** | **-39.55%** | **-37.75%** | **+1.80%** (Sụt giảm bớt sâu hơn) |
| **Max Drawdown B&H thuần** | **-33.34%** | **-33.34%** | **0.00%** (Giữ nguyên 100% không đổi) |
| **Tổng số lần `skipped_buys`** | *Chưa đo* | **0 lần** (trên toàn bộ 1.308 mã) | Không có mã nào hết tiền |

---

## 4. Phân tích kết quả định lượng sau khi sửa đúng

1. **PnL giảm ở cả 2 kỳ (-56,07 tỷ và -11,00 tỷ):**
   - Hoàn toàn khớp với dự đoán logic trong audit của Claude: Ở các lần mua lại khi thị trường hồi phục mạnh, giá cổ phiếu cao hơn đáng kể so với thời điểm bán ra ở đáy. Bản cũ vô tình "vay ảo" để mua đủ số cổ phiếu cũ, nên ăn thêm phần tăng trưởng của lượng cổ phiếu mua bằng tiền không có thật. Khi bị giới hạn chặt chẽ theo số dư tiền mặt thực có, số lượng cổ phiếu mua lại ít hơn, do đó lợi nhuận thực tế giảm xuống mức trung thực.
2. **Max Drawdown phản ánh đúng đường vốn thật:**
   - Trong mẫu: Max Drawdown đổi từ `-40.30%` thành `-40.10%`.
   - Ngoài mẫu: Max Drawdown đổi từ `-39.55%` thành `-37.75%`.
   - Cả hai số đo Max Drawdown đều thay đổi, phản ánh chính xác đường vốn không còn bị bóp méo bởi đòn bẩy âm.
3. **Số lần `skipped_buys` bằng 0 trên cả rổ 1.308 mã:**
   - Với mức vốn giả lập ban đầu 1 tỷ VNĐ / mã, ngay cả đối với các cổ phiếu sụt giảm mạnh nhất qua các chu kỳ gãy sóng, số tiền mặt thu hồi sau khi bán vẫn ở mức hàng chục/hàng trăm triệu VNĐ, luôn đủ để mua tối thiểu 1 lô cổ phiếu khi có tín hiệu mua lại. Không có hiện tượng mã nào bị "hết đạn" hoàn toàn.
4. **Kết luận cốt lõi về chiến lược Buy-and-Hold có nhịp:**
   - **Trong mẫu (2016–2022):** Chiến lược có nhịp vẫn mang lại hiệu quả vượt trội so với mua-và-giữ thuần (+1.407,49 tỷ so với +1.007,12 tỷ, chênh lệch **+400,37 tỷ**), và Max Drawdown thấp hơn (-40.10% so với -46.99%), nhờ tránh được 2 cú sụp đổ lịch sử năm 2018 và 2022.
   - **Ngoài mẫu (2023–2026):** Hiện tượng bẫy dao động (whipsaw) và chi phí ma sát (phí giao dịch, thuế bán, trượt giá qua 20 lần đổi trạng thái) khiến chiến lược có nhịp **thua xa mua-và-giữ thuần** (+312,72 tỷ so với +657,94 tỷ, tức **thua -345,22 tỷ VNĐ**), đồng thời Max Drawdown lại sâu hơn (-37.75% so với -33.34%).

---

## 5. Chi tiết Thay đổi Code (`git diff`)

### 5.1. `git diff scripts/measure_regime_hold.py`
> **Cam kết:** Chỉ phần trong hàm `simulate_symbol_regime_hold` thay đổi, toàn bộ các hàm khác và phần còn lại của file **không đổi một dòng nào**.

```diff
--- a/scripts/measure_regime_hold.py
+++ b/scripts/measure_regime_hold.py
@@ -87,6 +87,8 @@
             "daily_equity": {},
             "bh_pnl": 0.0,
             "bh_daily_equity": {},
+            "skipped_buys": 0,
+            "min_cash_seen": capital,
         }
 
     slip = slippage_bps / 10_000
@@ -104,6 +106,8 @@
             "daily_equity": {},
             "bh_pnl": 0.0,
             "bh_daily_equity": {},
+            "skipped_buys": 0,
+            "min_cash_seen": capital,
         }
 
     # 1. Đường vốn Mua-và-giữ thuần
@@ -126,8 +130,11 @@
     # 2. Chiến lược Buy-and-Hold theo nhịp (HOLD / CASH)
     cash = capital
+    min_cash_seen = float(capital)
+    skipped_buys = 0
-    pos = 0  # 0: CASH, qty: HOLD
+    pos = 0  # Số lượng cổ phiếu nắm giữ (0: CASH, buy_qty: HOLD)
+    current_state = "CASH"
     buy_trades = 0
     sell_trades = 0
     daily_equity: dict[date, float] = {}
@@ -137,17 +144,28 @@
         reg = prior_regime_by_date.get(b_date, "UNKNOWN")
         target_state = "HOLD" if reg != "RISK_OFF" else "CASH"
 
         # Đầu ngày: thực hiện giao dịch nếu trạng thái đổi
-        if target_state == "HOLD" and pos == 0:
-            # Mua lại đúng qty cổ phiếu đã xác định
+        if target_state == "HOLD" and current_state == "CASH":
+            # Chuyển từ TIỀN MẶT -> NẮM GIỮ: Tính qty mới từ cash đang có
             buy_p = b.open * (1 + slip)
-            cost = qty * buy_p * (1 + fee_rate)
-            cash -= cost
-            pos = qty
-            buy_trades += 1
-        elif target_state == "CASH" and pos > 0:
-            # Bán toàn bộ pos ra tiền mặt
+            buy_qty = int(cash // (buy_p * (1 + fee_rate)))
+            buy_qty = (buy_qty // lot_size) * lot_size
+            if buy_qty < lot_size or buy_qty <= 0:
+                # Không đủ tiền mua nổi 1 lô: ở lại trạng thái TIỀN MẶT
+                skipped_buys += 1
+            else:
+                cost = buy_qty * buy_p * (1 + fee_rate)
+                cash -= cost
+                if cash < 0 and cash > -1e-7:
+                    cash = 0.0
+                assert cash >= 0.0, f"Invariant violated: cash={cash}"
+                pos = buy_qty
+                buy_trades += 1
+                min_cash_seen = min(min_cash_seen, cash)
+            current_state = "HOLD"
+        elif target_state == "CASH" and current_state == "HOLD":
+            # Chuyển từ NẮM GIỮ -> TIỀN MẶT: Bán toàn bộ pos
             if pos > 0:
                 sell_p = b.open * (1 - slip)
                 proceeds = pos * sell_p * (1 - fee_rate - sell_tax_rate)
                 cash += proceeds
                 pos = 0
                 sell_trades += 1
+                min_cash_seen = min(min_cash_seen, cash)
+            current_state = "CASH"
 
         # Cuối ngày: tính giá trị danh mục mark-to-market
         is_last_bar = (i == len(clean) - 1)
         if is_last_bar and pos > 0:
             # Đóng vị thế tại Close ngày cuối kỳ
             sell_p = b.close * (1 - slip)
             proceeds = pos * sell_p * (1 - fee_rate - sell_tax_rate)
             cash += proceeds
             pos = 0
             sell_trades += 1
+            min_cash_seen = min(min_cash_seen, cash)
             daily_equity[b_date] = cash
         else:
             if pos > 0:
@@ -176,6 +194,8 @@
         "daily_equity": daily_equity,
         "bh_pnl": bh_pnl,
         "bh_daily_equity": bh_daily_equity,
+        "skipped_buys": skipped_buys,
+        "min_cash_seen": min_cash_seen,
     }
```

### 5.2. `git diff tests/test_regime_hold.py`
```diff
--- a/tests/test_regime_hold.py
+++ b/tests/test_regime_hold.py
@@ -73,23 +73,36 @@
     slip = SLIPPAGE_BPS / 10_000
     fee = FEE_RATE
     tax = SELL_TAX_RATE
+    lot_size = 100
 
-    # Tính tay đúng từng cắc
-    buy_p0 = 10.0 * (1 + slip)
-    qty = int(capital // (buy_p0 * (1 + fee)))
-
     # Nhịp 1: mua 10.0, bán 12.0
-    cost1 = qty * (10.0 * (1 + slip)) * (1 + fee)
-    proceeds1 = qty * (12.0 * (1 - slip)) * (1 - fee - tax)
+    buy_p1 = 10.0 * (1 + slip)
+    qty1 = int(capital // (buy_p1 * (1 + fee)))
+    qty1 = (qty1 // lot_size) * lot_size
+    cost1 = qty1 * buy_p1 * (1 + fee)
+    cash1 = capital - cost1
 
-    # Nhịp 2: mua lại 11.0, đóng 16.0
-    cost2 = qty * (11.0 * (1 + slip)) * (1 + fee)
-    proceeds2 = qty * (16.0 * (1 - slip)) * (1 - fee - tax)
+    sell_p1 = 12.0 * (1 - slip)
+    proceeds1 = qty1 * sell_p1 * (1 - fee - tax)
+    cash2 = cash1 + proceeds1
 
-    expected_pnl = (proceeds1 - cost1) + (proceeds2 - cost2)
+    # Nhịp 2: mua lại từ cash2 ở 11.0, đóng ở Close=16.0 ngày cuối kỳ
+    buy_p2 = 11.0 * (1 + slip)
+    qty2 = int(cash2 // (buy_p2 * (1 + fee)))
+    qty2 = (qty2 // lot_size) * lot_size
+    cost2 = qty2 * buy_p2 * (1 + fee)
+    cash3 = cash2 - cost2
 
-    res = simulate_symbol_regime_hold(bars, prior_regime, capital=capital)
+    sell_p2 = 16.0 * (1 - slip)
+    proceeds2 = qty2 * sell_p2 * (1 - fee - tax)
+    cash4 = cash3 + proceeds2
+
+    expected_pnl = cash4 - capital
+
+    res = simulate_symbol_regime_hold(bars, prior_regime, capital=capital, lot_size=lot_size)
 
+    assert res["min_cash_seen"] >= 0.0
     assert res["buy_trades"] == 2
     assert res["sell_trades"] == 2
     assert pytest.approx(res["pnl"], rel=1e-6) == expected_pnl
@@ -133,4 +146,34 @@
     expected = (80.0 - 150.0) / 150.0  # -70 / 150 = -0.466666...
     assert pytest.approx(mdd, rel=1e-4) == expected
     assert f"{mdd:.2%}" == "-46.67%"
+
+
+def test_cash_khong_bao_gio_am():
+    """Test 5 (bắt buộc, Brief 62): Dựng kịch bản audit (bán thấp, mua lại cao gấp 3 lần),
+    khẳng định cash không âm ở bất kỳ thời điểm nào trong suốt mô phỏng.
+    """
+    capital = 1_000_000.0
+    dates = [
+        date(2026, 1, 1),
+        date(2026, 1, 4),
+        date(2026, 1, 7),
+        date(2026, 1, 10),
+    ]
+    bars = [
+        _make_bar(dates[0], 10.0, 10.0),  # Mua ở 10.0
+        _make_bar(dates[1], 10.0, 10.0),  # Bán ở 10.0
+        _make_bar(dates[2], 30.0, 30.0),  # Mua lại ở 30.0 (giá cao gấp 3 lần)
+        _make_bar(dates[3], 35.0, 35.0),  # Cuối kỳ đóng ở 35.0
+    ]
+    prior_regime = {
+        dates[0]: "RISK_ON",
+        dates[1]: "RISK_OFF",
+        dates[2]: "RISK_ON",
+        dates[3]: "RISK_ON",
+    }
+    res = simulate_symbol_regime_hold(bars, prior_regime, capital=capital)
+    assert res["min_cash_seen"] >= 0.0
+    assert res["buy_trades"] == 2
+    assert res["sell_trades"] == 2
```

---

## 6. Kiểm tra Linter & Toàn bộ Test Suite Dự án

### 6.1. Linter (`ruff`)
Lệnh chạy: `uv run ruff check trading tests scripts`
```
All checks passed!
```

### 6.2. Test Suite toàn dự án (`pytest`)
Lệnh chạy: `uv run pytest -m "not integration" -q`
```
699 passed, 113 deselected in 21.73s
```
Toàn bộ 699 test unit/property đều **PASSED 100%**. Không có test nào đỏ thêm.

---

## 7. Cam kết an toàn & Bàn giao
- Không chỉnh sửa bất kỳ file nào trong `trading/` hay engine.
- Không sửa `config/config.yaml`, không sửa `.env`.
- Cơ sở dữ liệu SQLite chỉ đọc (`bars_daily`).
- Chưa thực hiện `git commit` hay `git push`. Toàn bộ thay đổi sẵn sàng để Claude thẩm định và audit.
