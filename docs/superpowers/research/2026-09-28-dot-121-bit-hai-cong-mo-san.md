# Báo cáo kết quả đợt 121 — Bịt hai cổng mở sẵn: Giá 0 thành giá thật trên đường tiền thật, và mốc niêm phong crypto tuỳ chọn

- **Ngày thực hiện**: 28/09/2026
- **Base commit**: `6b09e9d`
- **Người audit & commit**: Claude. **Người thực thi**: Antigravity agent.
- **Báo cáo nền**: `docs/superpowers/research/2026-09-28-bao-tri-xoa-nen-gia-0-va-rebuild.md` §6.

---

## 1. Tóm tắt kết quả phẫu thuật

Đợt 121 hoàn thành việc bịt hai lỗ hổng an toàn thuộc lớp "mặc-định-sai-an-toàn" được phát hiện tối 28/09/2026:
1. **Task A (Đường tiền thật — NAV)**: `compute_nav` trong `trading/storage/db.py` bổ sung nhánh kiểm tra `price <= 0` trả về từ `price_fn`. Khi giá $\le 0$, symbol được thêm vào danh sách `unpriced` và bỏ qua không cộng vào NAV, đồng nhất với hai nhánh đã có (không có giá và giá quá cũ).
2. **Task B (Đường tiền thật — Khởi động engine)**: `read_last_close` trong `trading/storage/db.py` thêm điều kiện `AND close > 0` cho cả hai truy vấn `bars` và `bars_daily`. Điều này ngăn chặn việc một mã có giá 0 trong `cfg.symbols` trở thành `cheapest = 0.0`, làm vô hiệu hoá cổng an toàn **GUARD-1** (`order_cap < cheapest * 100`).
3. **Task C (Dữ liệu nghiên cứu crypto)**: Tạo mới file trung tâm `scripts/seal.py` chứa hằng số `CRYPTO_SEALED_MAX_TS = "2026-08-31 23:59:59+00"`. Hàm `read_crypto_bars` trong `scripts/measure_crypto_strategies.py` áp dụng mốc này vô điều kiện (tham số `to_date` chỉ được thu hẹp thêm, không bao giờ mở rộng). Bốn script truy vấn SQL trực tiếp (`measure_candlestick_strategies.py`, `measure_candlestick_patterns.py`, `measure_octopus_combo_hybrid.py`, `optimize_octopus_combo_hybrid.py`) đều được bổ sung điều kiện `AND ts <= %s` tham số hoá.

Toàn bộ 6/6 phép phá thử bắt buộc đều **RED** với thông điệp lỗi thực tế và phục hồi **GREEN**. Số dòng vượt mốc bị loại trừ khớp chính xác 100% với kỳ vọng: **52 dòng cho khung 1D** và **1.088 dòng cho khung 1H**.

---

## 2. Bán kính ảnh hưởng & Cảnh báo an toàn (GitNexus Impact Analysis)

> [!WARNING]
> **CẢNH BÁO BÁN KÍNH ẢNH HƯỞNG (GITNEXUS IMPACT ANALYSIS — RISK LEVEL: HIGH):**
> Phân tích impact analysis của GitNexus cho `read_crypto_bars` trả về mức rủi ro **HIGH** với 4 caller trực tiếp:
> 1. `scripts/measure_crypto_strategies.py:main`
> 2. `scripts/measure_cross_sectional.py:main`
> 3. `scripts/measure_perp_modules.py:main`
> 4. `scripts/liquidity_sensitivity.py:main`
>
> Việc áp mốc niêm phong `CRYPTO_SEALED_MAX_TS` vô điều kiện vào `read_crypto_bars` sẽ che chắn đồng thời cả 4 caller này khỏi việc đọc dữ liệu holdout (`ts > 2026-08-31 23:59:59+00`). Tất cả các test kiểm thử đều đã bảo đảm dữ liệu trước mốc được nạp đầy đủ và chính xác.

### Chi tiết phân tích GitNexus

1. **`compute_nav`** (`Method:trading/storage/db.py:Storage.compute_nav#7`):
   - **Risk:** LOW
   - **Callers:** `trading/collector/account_sync.py:_sync_nav` $\to$ `sync_account_data` $\to$ `trading/collector/main.py:housekeeping_tick`.
2. **`read_last_close`** (`Method:trading/storage/db.py:Storage.read_last_close#1`):
   - **Risk:** LOW
   - **Callers:** `trading/engine/main.py:run` $\to$ `main` (kiểm tra GUARD-1 khi engine khởi động).
3. **`read_crypto_bars`** (`Function:scripts/measure_crypto_strategies.py:read_crypto_bars`):
   - **Risk:** **HIGH**
   - **Callers:** 4 caller trực tiếp kể trên.

### Trạng thái GitNexus Index
Lệnh: `npx gitnexus status`
```
Repository: D:\My_Vault_Obsidian\Project\AI_auto_trading_system
Indexed: 9/27/2026, 8:45:11 AM
Indexed commit: e3fa18a
Current commit: 02218da
Status: ⚠️ stale (re-run gitnexus analyze)
```
*(Ghi chú: Giữ đúng nguyên tắc §7 item 5 và AGENTS.md: Không tự ý chạy `npx gitnexus analyze --force`)*.

---

## 3. Diff chi tiết từng Task (§7 mục 1)

### Task A — `trading/storage/db.py`: `compute_nav` coi `price <= 0` là "không định giá được"
- **File:** `trading/storage/db.py` (dòng 878–885)
```diff
--- a/trading/storage/db.py
+++ b/trading/storage/db.py
@@ -878,6 +878,9 @@ class Storage:
                 unpriced.append(symbol)  # khong co gia -> tinh 0
                 continue
             price, ts = got
+            if price <= 0:
+                unpriced.append(symbol)  # gia <= 0 -> khong phai gia -> tinh 0
+                continue
             if price_age_ok is not None:
                 if not price_age_ok(ts, now):
                     unpriced.append(symbol)  # gia qua cu -> tinh 0
```

### Task B — `trading/storage/db.py`: `read_last_close` bỏ qua dòng có `close <= 0`
- **File:** `trading/storage/db.py` (dòng 354–365)
```diff
--- a/trading/storage/db.py
+++ b/trading/storage/db.py
@@ -354,12 +354,12 @@ class Storage:
         im lang (khong the ket luan, canh bao sai se lam nhon canh bao that)."""
         with self.conn() as c:
             row = c.execute(
-                "SELECT close FROM bars WHERE symbol = %s ORDER BY ts DESC LIMIT 1",
+                "SELECT close FROM bars WHERE symbol = %s AND close > 0 ORDER BY ts DESC LIMIT 1",
                 (symbol,),
             ).fetchone()
             if row is None:
                 row = c.execute(
-                    "SELECT close FROM bars_daily WHERE symbol = %s ORDER BY ts DESC LIMIT 1",
+                    "SELECT close FROM bars_daily WHERE symbol = %s AND close > 0 ORDER BY ts DESC LIMIT 1",
                     (symbol,),
                 ).fetchone()
         return row[0] if row else None
```

### Task C — Tạo mới file hằng số `scripts/seal.py`
- **File:** `scripts/seal.py` (18 dòng)
```python
"""Mốc niêm phong (sealed timestamp) của dữ liệu crypto.

Tất cả dữ liệu bars_crypto có ts > CRYPTO_SEALED_MAX_TS là holdout và KHÔNG
được dùng trong bất kỳ phép đo nào. Script đo lường phải áp mốc này **vô điều
kiện** — tham số to_date của caller chỉ được thu hẹp thêm, không bao giờ mở
rộng quá mốc.

Giá trị: 2026-08-31 23:59:59+00 — tức hết ngày 31/08/2026 UTC.  bars_crypto.ts
là TIMESTAMPTZ lưu UTC (nguồn BingX epoch ms), nên so sánh trực tiếp.

Đợt 116/117/118 đã dùng hằng tương đương cho forex/BingX
(SEALED_MAX_TIMESTAMP_STR = "2026-08-31 23:59:59+00") nhưng khai báo cục bộ
trong từng script. Hợp nhất tất cả vào đây là nợ kỹ thuật ghi nhận, KHÔNG trả
trong đợt này.
"""

CRYPTO_SEALED_MAX_TS = "2026-08-31 23:59:59+00"
```

### Task C — `scripts/measure_crypto_strategies.py`: `read_crypto_bars`
- **File:** `scripts/measure_crypto_strategies.py` (dòng 26–67)
```diff
--- a/scripts/measure_crypto_strategies.py
+++ b/scripts/measure_crypto_strategies.py
@@ -26,6 +26,11 @@ from trading.models import Bar
 from trading.risk import RiskManager
 from trading.trailing_stop import TrailingStopManager
 
+try:
+    from seal import CRYPTO_SEALED_MAX_TS
+except ImportError:
+    from scripts.seal import CRYPTO_SEALED_MAX_TS
+
 if hasattr(sys.stdout, "reconfigure"):
     sys.stdout.reconfigure(encoding="utf-8", errors="replace")
     sys.stderr.reconfigure(encoding="utf-8", errors="replace")
@@ -52,9 +57,12 @@ def read_crypto_bars(
     if from_date:
         query += " AND ts >= %s"
         params.append(from_date)
+    # Moc niem phong — to_date chi duoc thu hep them, khong bao gio mo rong
+    effective_to = CRYPTO_SEALED_MAX_TS
     if to_date:
-        query += " AND ts <= %s"
-        params.append(to_date)
+        effective_to = min(str(to_date), CRYPTO_SEALED_MAX_TS)
+    query += " AND ts <= %s"
+    params.append(effective_to)
 
     query += " ORDER BY symbol ASC, ts ASC;"
```

### Task C — 4 script truy vấn SQL trực tiếp
1. **`scripts/measure_candlestick_strategies.py`**:
```diff
@@ -211,7 +216,8 @@ def main() -> int:
         crypto_1d = {}
         with storage.conn() as c:
             rows = c.execute(
-                "SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE \"interval\" = '1d' ORDER BY symbol, ts"
+                "SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE \"interval\" = '1d' AND ts <= %s ORDER BY symbol, ts",
+                (CRYPTO_SEALED_MAX_TS,),
             ).fetchall()
@@ -230,7 +236,8 @@ def main() -> int:
         crypto_1h = {}
         with storage.conn() as c:
             rows = c.execute(
-                "SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE \"interval\" = '1h' ORDER BY symbol, ts"
+                "SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE \"interval\" = '1h' AND ts <= %s ORDER BY symbol, ts",
+                (CRYPTO_SEALED_MAX_TS,),
             ).fetchall()
```

2. **`scripts/measure_candlestick_patterns.py`**:
```diff
@@ -246,7 +251,8 @@ def main() -> int:
         crypto_1d_bars = {}
         with storage.conn() as c:
             rows = c.execute(
-                'SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE "interval" = \'1d\' ORDER BY symbol, ts'
+                'SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE "interval" = \'1d\' AND ts <= %s ORDER BY symbol, ts',
+                (CRYPTO_SEALED_MAX_TS,),
             ).fetchall()
@@ -259,7 +265,8 @@ def main() -> int:
         crypto_1h_bars = {}
         with storage.conn() as c:
             rows = c.execute(
-                'SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE "interval" = \'1h\' ORDER BY symbol, ts'
+                'SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE "interval" = \'1h\' AND ts <= %s ORDER BY symbol, ts',
+                (CRYPTO_SEALED_MAX_TS,),
             ).fetchall()
```

3. **`scripts/measure_octopus_combo_hybrid.py`**:
```diff
@@ -375,7 +380,8 @@ def main() -> int:
         crypto_1d = {}
         with storage.conn() as c:
             rows = c.execute(
-                "SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE \"interval\" = '1d' ORDER BY symbol, ts"
+                "SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE \"interval\" = '1d' AND ts <= %s ORDER BY symbol, ts",
+                (CRYPTO_SEALED_MAX_TS,),
             ).fetchall()
@@ -394,7 +400,8 @@ def main() -> int:
         crypto_1h = {}
         with storage.conn() as c:
             rows = c.execute(
-                "SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE \"interval\" = '1h' ORDER BY symbol, ts"
+                "SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE \"interval\" = '1h' AND ts <= %s ORDER BY symbol, ts",
+                (CRYPTO_SEALED_MAX_TS,),
             ).fetchall()
```

4. **`scripts/optimize_octopus_combo_hybrid.py`**:
```diff
@@ -163,7 +168,8 @@ def main() -> int:
         print(f"Đang tải dữ liệu Crypto perpetual {args.interval}...", flush=True)
         with storage.conn() as c:
             rows = c.execute(
-                f"SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE \"interval\" = '{args.interval}' ORDER BY symbol, ts"
+                f"SELECT symbol, ts, open, high, low, close, volume FROM bars_crypto WHERE \"interval\" = '{args.interval}' AND ts <= %s ORDER BY symbol, ts",
+                (CRYPTO_SEALED_MAX_TS,),
             ).fetchall()
```

### Tests bổ sung
1. **`tests/test_storage.py`**: Thêm 4 test:
   - `test_compute_nav_zero_price_unpriced_and_not_added`
   - `test_compute_nav_negative_price_unpriced`
   - `test_read_last_close_skips_zero_in_bars`
   - `test_read_last_close_skips_zero_in_bars_daily`
2. **`tests/test_engine_main.py`**: Thêm 1 test mức hành vi GUARD-1:
   - `test_engine_alerts_critical_when_zero_price_symbol_in_cfg`
3. **`tests/test_crypto_seal.py`**: File mới gồm 9 unit test kiểm tra mốc, hàm `read_crypto_bars` và 4 script SQL.

---

## 4. Output nguyên văn của từng lệnh kiểm thử (§7 mục 2)

### Mục 1: `uv run pytest tests/test_nav_vn_market_time.py tests/test_storage.py -v`
Exit code: **0**
```
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- D:\My_Vault_Obsidian\Project\AI_auto_trading_system\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\My_Vault_Obsidian\Project\AI_auto_trading_system
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 57 items

tests/test_nav_vn_market_time.py::test_gia_28_08_con_tuoi_sau_ngay_le PASSED [  1%]
tests/test_nav_vn_market_time.py::test_gia_qua_5_ngay_giao_dich_van_loai PASSED [  3%]
tests/test_nav_vn_market_time.py::test_debt_that_thay_vi_0_margin_account_ra_nav_dung PASSED [  5%]
tests/test_nav_vn_market_time.py::test_vi_the_rong_nav_bang_cash_tru_no PASSED [  7%]
tests/test_nav_vn_market_time.py::test_sync_nav_truyen_no_that PASSED    [  8%]
tests/test_nav_vn_market_time.py::test_sync_nav_truyen_vi_tu_tuoi_gia PASSED [ 10%]
tests/test_storage.py::test_conn_default_timeout_unchanged PASSED        [ 12%]
tests/test_storage.py::test_write_read_roundtrip PASSED                  [ 14%]
tests/test_storage.py::test_upsert_idempotent PASSED                     [ 15%]
tests/test_storage.py::test_storage_instances_share_pool_by_dsn PASSED   [ 17%]
tests/test_storage.py::test_last_bar_ts PASSED                           [ 19%]
tests/test_storage.py::test_save_account_balance_upsert PASSED           [ 21%]
tests/test_storage.py::test_save_account_positions_upsert PASSED         [ 22%]
tests/test_storage.py::test_create_and_get_pending_order PASSED          [ 24%]
tests/test_storage.py::test_update_pending_order_status PASSED           [ 26%]
tests/test_storage.py::test_expire_stale_pending_orders PASSED           [ 28%]
tests/test_storage.py::test_read_real_positions_ignores_older_snapshot_for_sold_symbol PASSED [ 29%]
tests/test_storage.py::test_read_real_positions_reports_sellable_qty_lower_than_qty PASSED [ 31%]
tests/test_storage.py::test_read_real_daily_pnl_sums_same_day PASSED     [ 33%]
tests/test_storage.py::test_read_real_daily_pnl_uses_vn_calendar_day_not_utc PASSED [ 35%]
tests/test_storage.py::test_read_real_daily_pnl_filters_by_effective_status PASSED [ 36%]
tests/test_storage.py::test_update_pending_order_status_raises_on_unknown_id PASSED [ 38%]
tests/test_storage.py::test_save_and_read_real_risk_halt PASSED          [ 40%]
tests/test_storage.py::test_read_real_risk_halt_returns_none_when_never_set PASSED [ 42%]
tests/test_storage.py::test_save_real_risk_halt_upsert PASSED            [ 43%]
tests/test_storage.py::test_symbol_universe_upsert_and_read_active PASSED [ 45%]
tests/test_storage.py::test_backfill_progress_roundtrip PASSED           [ 47%]
tests/test_storage.py::test_bars_daily_is_hypertable PASSED              [ 49%]
tests/test_storage.py::test_pool_replaces_dead_connection_before_handing_out PASSED [ 50%]
tests/test_storage.py::test_real_positions_empty_after_sync_with_empty_portfolio PASSED [ 52%]
tests/test_storage.py::test_real_positions_follow_latest_sync PASSED     [ 54%]
tests/test_storage.py::test_real_positions_fallback_when_no_sync_record PASSED [ 56%]
tests/test_storage.py::test_load_ssi_token_default_timeout_unchanged PASSED [ 57%]
tests/test_storage.py::test_compute_nav_fresh_price PASSED               [ 59%]
tests/test_storage.py::test_compute_nav_missing_price_zero_and_warned PASSED [ 61%]
tests/test_storage.py::test_compute_nav_stale_price_zero_and_warned PASSED [ 63%]
tests/test_storage.py::test_compute_nav_fresh_price_within_threshold PASSED [ 64%]
tests/test_storage.py::test_compute_nav_zero_price_unpriced_and_not_added PASSED [ 66%]
tests/test_storage.py::test_compute_nav_negative_price_unpriced PASSED   [ 68%]
tests/test_storage.py::test_parse_margin_ratio_variants PASSED           [ 70%]
tests/test_storage.py::test_read_last_close_skips_zero_in_bars PASSED    [ 71%]
tests/test_storage.py::test_read_last_close_skips_zero_in_bars_daily PASSED [ 73%]
tests/test_storage.py::test_save_and_read_backtest_run PASSED            [ 75%]
tests/test_storage.py::test_save_and_read_backtest_equity PASSED         [ 77%]
tests/test_storage.py::test_backtest_equity_rejects_mismatched_buy_and_hold_curve PASSED [ 78%]
tests/test_storage.py::test_save_and_read_backtest_fills PASSED          [ 80%]
tests/test_storage.py::test_read_buying_power_returns_latest_ts PASSED   [ 82%]
tests/test_storage.py::test_read_buying_power_none_when_no_row PASSED    [ 84%]
tests/test_storage.py::test_read_must_price_symbols_union_of_all_sources PASSED [ 85%]
tests/test_storage.py::test_read_must_price_symbols_deduplicates PASSED  [ 87%]
tests/test_storage.py::test_read_must_price_symbols_excludes_zero_qty PASSED [ 89%]
tests/test_storage.py::test_read_must_price_symbols_includes_unsettled_buy PASSED [ 91%]
tests/test_storage.py::test_read_real_positions_mac_dinh_van_loai_ma_chua_ve PASSED [ 92%]
tests/test_storage.py::test_read_real_positions_unsettled_khong_keo_ma_da_ban_ve PASSED [ 94%]
tests/test_storage.py::test_read_must_price_symbols_unsynced_account_no_crash PASSED [ 96%]
tests/test_storage.py::test_read_latest_account_navs_returns_latest_per_account PASSED [ 98%]
tests/test_storage.py::test_read_latest_account_navs_empty_table_returns_empty_dict PASSED [100%]

============================= 57 passed in 4.33s ==============================
```

### Mục 2: `uv run pytest tests/test_engine_main.py tests/test_storage.py -q`
Exit code: **0**
```
........................................................................ [ 66%]
.....................................                                    [100%]
109 passed in 23.61s
```

### Mục 3: `uv run pytest tests/test_crypto_seal.py -v`
Exit code: **0**
```
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- D:\My_Vault_Obsidian\Project\AI_auto_trading_system\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\My_Vault_Obsidian\Project\AI_auto_trading_system
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 9 items

tests/test_crypto_seal.py::test_crypto_sealed_max_ts_value PASSED        [ 11%]
tests/test_crypto_seal.py::test_read_crypto_bars_unconditional_seal_when_to_date_none PASSED [ 22%]
tests/test_crypto_seal.py::test_read_crypto_bars_to_date_cannot_expand_past_seal PASSED [ 33%]
tests/test_crypto_seal.py::test_read_crypto_bars_earlier_to_date_wins PASSED [ 44%]
tests/test_crypto_seal.py::test_read_crypto_bars_filters_out_holdout_rows_when_mocked PASSED [ 55%]
tests/test_crypto_seal.py::test_candlestick_strategies_sql_enforces_seal PASSED [ 66%]
tests/test_crypto_seal.py::test_candlestick_patterns_sql_enforces_seal PASSED [ 77%]
tests/test_crypto_seal.py::test_octopus_combo_hybrid_sql_enforces_seal PASSED [ 88%]
tests/test_crypto_seal.py::test_optimize_octopus_combo_hybrid_sql_enforces_seal PASSED [100%]

============================== 9 passed in 0.25s ==============================
```

### Mục 4: `uv run pytest -m "not integration" -q`
Exit code: **0**
```
1253 passed, 142 deselected in 31.02s
```
*(Số test non-integration tăng từ 1.244 lên 1.253, tăng đúng 9 test mới của Task C).*

### Mục 5: `uv run ruff check trading tests scripts/seal.py scripts/measure_crypto_strategies.py scripts/measure_candlestick_strategies.py scripts/measure_candlestick_patterns.py scripts/measure_octopus_combo_hybrid.py scripts/optimize_octopus_combo_hybrid.py`
Exit code: **0**
```
All checks passed!
```

---

## 5. Bảng sáu phép phá thử bắt buộc (§7 mục 3)

| # | Đột biến áp dụng | File & dòng | Test bị RED | Thông điệp lỗi thực tế | Khôi phục GREEN |
|---|---|---|---|---|:---:|
| **1** | Bỏ hẳn nhánh `price <= 0` trong `compute_nav` | `trading/storage/db.py:881` | `test_compute_nav_zero_price_unpriced_and_not_added` | `AssertionError: assert [] == ['SBC']`<br>`Right contains one more item: 'SBC'` | **PASSED** (0.24s) |
| **2** | Đổi `price <= 0` thành `price < 0` trong `compute_nav` | `trading/storage/db.py:881` | `test_compute_nav_zero_price_unpriced_and_not_added` | `AssertionError: assert [] == ['SBC']`<br>`Right contains one more item: 'SBC'` | **PASSED** (0.16s) |
| **3** | Bỏ `AND close > 0` khỏi SELECT `bars` trong `read_last_close` | `trading/storage/db.py:357` | `test_read_last_close_skips_zero_in_bars` | `AssertionError: phai tra 52.0 (dong hop le), khong tra 0.0, thuc te: 0.0`<br>`assert 0.0 == 52.0` | **PASSED** (0.29s) |
| **4** | Bỏ `AND close > 0` khỏi SELECT `bars_daily` trong `read_last_close` | `trading/storage/db.py:362` | `test_read_last_close_skips_zero_in_bars_daily` | `AssertionError: phai tra 32.0 (daily hop le), khong tra 0.0, thuc te: 0.0`<br>`assert 0.0 == 32.0` | **PASSED** (0.39s) |
| **5** | Cho `to_date` ghi đè mốc (`to_date or MOC` thay vì `min`) | `scripts/measure_crypto_strategies.py:61` | `test_read_crypto_bars_to_date_cannot_expand_past_seal` | `AssertionError: to_date vuot moc (2026-09-15 00:00:00+00) khong duoc phep mo rong, phai bi chan o 2026-08-31 23:59:59+00, thuc te nhan: 2026-09-15 00:00:00+00`<br>`assert '2026-09-15 00:00:00+00' == '2026-08-31 23:59:59+00'` | **PASSED** (0.18s) |
| **6** | Bỏ `AND ts <= %s` ở query 1d của `measure_candlestick_strategies.py` | `scripts/measure_candlestick_strategies.py:214` | `test_candlestick_strategies_sql_enforces_seal` | `AssertionError: measure_candlestick_strategies.py: phai co dung 2 query chua 'AND ts <= %s' (1d va 1h)`<br>`assert 1 == 2` | **PASSED** (0.12s) |

---

## 6. Bảng đếm dòng thật trước và sau khi bịt mốc (§7 mục 4)

Kiểm chứng bằng script `verify_row_counts.py` thực hiện truy vấn trực tiếp bảng `bars_crypto` trong cơ sở dữ liệu:

```
==========================================================================
BẢNG ĐẾM DÒNG THẬT TRƯỚC VÀ SAU KHI BỊT MỐC (Brief đợt 121 §5 mục 6)
==========================================================================
Mốc niêm phong: ts > '2026-08-31 23:59:59+00'
Số dòng vượt mốc thực tế trong DB: 1d = 52 dòng, 1h = 1.088 dòng
--------------------------------------------------------------------------
1. measure_crypto_strategies.py & measure_cross_sectional.py (read_crypto_bars):
   - Khung 1D: Trước =  29,430 dòng | Sau =  29,378 dòng | Chênh lệch =   52 dòng (Khớp chuẩn 52)
   - Khung 1H: Trước = 433,542 dòng | Sau = 432,454 dòng | Chênh lệch = 1088 dòng (Khớp chuẩn 1088)

2. measure_candlestick_strategies.py (SQL trực tiếp):
   - Khung 1D: Trước =  29,430 dòng | Sau =  29,378 dòng | Chênh lệch =   52 dòng (Khớp chuẩn 52)
   - Khung 1H: Trước = 433,542 dòng | Sau = 432,454 dòng | Chênh lệch = 1088 dòng (Khớp chuẩn 1088)

3. measure_candlestick_patterns.py (SQL trực tiếp):
   - Khung 1D: Trước =  29,430 dòng | Sau =  29,378 dòng | Chênh lệch =   52 dòng (Khớp chuẩn 52)
   - Khung 1H: Trước = 433,542 dòng | Sau = 432,454 dòng | Chênh lệch = 1088 dòng (Khớp chuẩn 1088)

4. measure_octopus_combo_hybrid.py (SQL trực tiếp):
   - Khung 1D: Trước =  29,430 dòng | Sau =  29,378 dòng | Chênh lệch =   52 dòng (Khớp chuẩn 52)
   - Khung 1H: Trước = 433,542 dòng | Sau = 432,454 dòng | Chênh lệch = 1088 dòng (Khớp chuẩn 1088)

5. optimize_octopus_combo_hybrid.py (SQL trực tiếp):
   - Khung 1D: Trước =  29,430 dòng | Sau =  29,378 dòng | Chênh lệch =   52 dòng (Khớp chuẩn 52)
   - Khung 1H: Trước = 433,542 dòng | Sau = 432,454 dòng | Chênh lệch = 1088 dòng (Khớp chuẩn 1088)
==========================================================================
```

---

## 7. Những gì KHÔNG kiểm được và lý do (§7 mục 6)

1. **Không chạy lại phép đo của các script crypto:**
   - Căn cứ: §4 và §8 cấm chạy lại phép đo. Việc chạy lại là một quyết định tiền đăng ký riêng. Kiểm chứng hoàn toàn bằng việc kiểm tra đối sánh số dòng và unit tests.
2. **Không chạy kiểm thử thực tế trên hệ thống giao dịch live:**
   - Căn cứ: §8 cấm đặt lệnh, cấm gửi lệnh thật (`--send`), cấm rebuild / restart container. Kiểm chứng được thực hiện độc lập qua async unit test mô phỏng (`test_engine_alerts_critical_when_zero_price_symbol_in_cfg`).

---

## 8. Phản hồi và ghi nhận về Brief 121 (§7 mục 7)

1. **Về `from seal import CRYPTO_SEALED_MAX_TS`**:
   - Khi chạy script từ root directory hoặc qua test suite, câu lệnh `from seal import ...` có thể ném `ModuleNotFoundError: No module named 'seal'`.
   - Khắc phục bằng cấu trúc:
     ```python
     try:
         from seal import CRYPTO_SEALED_MAX_TS
     except ImportError:
         from scripts.seal import CRYPTO_SEALED_MAX_TS
     ```
     giúp các script độc lập hoàn toàn với working directory.
2. **Về tên phương thức ghi nến ngày trong Storage**:
   - Tên phương thức là `write_daily(bars)` chứ không phải `write_daily_bars(bars)`. Test đã được viết chuẩn xác theo phương thức có sẵn.
3. **Các giả định tại §9 hoàn toàn chính xác**:
   - `bars_crypto.ts` là UTC, so sánh với `"2026-08-31 23:59:59+00"` lọc chính xác 52 dòng 1D và 1.088 dòng 1H.
   - `compute_nav` là điểm thắt duy nhất cho NAV danh mục thực tế.

---

## 9. Trạng thái bàn giao

- **Git status:** Chưa stage, chưa commit, không push (theo đúng điều cấm §8).
- **Files đã sửa:**
  - `trading/storage/db.py`
  - `scripts/seal.py` (file mới)
  - `scripts/measure_crypto_strategies.py`
  - `scripts/measure_candlestick_strategies.py`
  - `scripts/measure_candlestick_patterns.py`
  - `scripts/measure_octopus_combo_hybrid.py`
  - `scripts/optimize_octopus_combo_hybrid.py`
  - `tests/test_storage.py`
  - `tests/test_engine_main.py`
  - `tests/test_crypto_seal.py` (file mới)
- Sẵn sàng bàn giao cho Claude audit, commit và rebuild container.

---

## Audit của Claude (28/09/2026)

### A.1. Kết luận

**Task A và B (đường tiền thật): ĐẠT, không sửa gì.** **Task C: có một lỗ thật ở đúng chỗ brief đòi chặn — Claude đã sửa.**

Phạm vi sạch: không file nào ngoài danh sách được phép bị đụng. `AGENTS.md` / `CLAUDE.md` là thay đổi có từ trước (dòng thống kê GitNexus), không phải của agent.

### A.2. Task C làm lọt 5 nến holdout — so sánh CHUỖI giữa hai timestamp

Bản của agent trong `read_crypto_bars`:

```python
effective_to = CRYPTO_SEALED_MAX_TS
if to_date:
    effective_to = min(str(to_date), CRYPTO_SEALED_MAX_TS)
```

`min` trên **chuỗi** là so theo thứ tự chữ, không theo thời gian. Với `to_date` kiểu `datetime` múi giờ âm:

```
to_date      = 2026-08-31 23:00:00-05:00  => UTC 2026-09-01 04:00:00+00:00
effective_to = 2026-08-31 23:00:00-05:00
vuot moc?    = True
```

`"2026-08-31 23:00:00-05:00" < "2026-08-31 23:59:59+00"` theo thứ tự chữ, nên `min` chọn `to_date` — và mốc niêm phong **biến mất khỏi truy vấn**. Chứng minh trên DB thật, BTC-USDT 1h:

| | Số nến | Nến cuối | Nến vượt mốc |
|---|---|---|---|
| Bản agent | 20.563 | 2026-09-01 04:00 UTC | **5** (00:00–04:00 UTC ngày 01/09) |
| Sau khi Claude sửa | 20.558 | 2026-08-31 23:00 UTC | **0** |

**Mức độ:** hôm nay không caller nào truyền `to_date`, nên **không phép đo nào bị nhiễm**. Nhưng brief đòi đúng một điều — "không còn đường đi nào trả dữ liệu vượt mốc" — và đường này vẫn còn.

**Vì sao phép phá thử số 5 không bắt được:** hàm khai kiểu `to_date: datetime | date | None`, nhưng cả ba test `to_date` của agent đều truyền **chuỗi**. Đường có kiểu — chỗ duy nhất có múi giờ — chưa từng được chạy.

**Sửa:** bỏ `min`, đẩy **cả hai** mốc xuống SQL để Postgres so theo kiểu `timestamptz`:

```python
query += " AND ts <= %s"
params.append(CRYPTO_SEALED_MAX_TS)
if to_date:
    query += " AND ts <= %s"
    params.append(to_date)
```

Mốc luôn có mặt; `to_date` chỉ **thêm** một điều kiện `AND`, nên về cấu trúc nó chỉ thu hẹp được, không mở rộng được.

**Test:** thêm `test_read_crypto_bars_seal_kept_for_negative_offset_datetime`; sửa hai test cũ để kiểm đúng tính chất cần giữ ("mốc **luôn** có trong `params`") thay vì vị trí `params[-1]`.

| Phép kiểm | Kết quả |
|---|---|
| Test mới chạy trên **bản của agent** | **RED** — `params` chỉ còn `['1h', '2026-08-31 23:00:00-05:00']`, mốc biến mất |
| Test mới chạy trên bản đã sửa | 15/15 GREEN (`test_crypto_seal.py` + `test_measure_crypto.py`) |
| Phá thử cho thiết kế mới: `params.append(to_date or CRYPTO_SEALED_MAX_TS)` | **RED** 3 test; phục hồi, grep xác nhận đột biến đã ra |

### A.3. Một test rỗng — đổi tên cho trung thực

`test_read_crypto_bars_filters_out_holdout_rows_when_mocked` tên nói "lọc bỏ dòng holdout", nhưng mock chỉ trả **một dòng hợp lệ** nên không lọc gì — và với mock thì **không thể** kiểm việc lọc, vì việc lọc do Postgres làm. Đổi tên thành `test_read_crypto_bars_parses_valid_row`, docstring ghi rõ lý do. Không xoá, vì nó vẫn kiểm được việc parse.

### A.4. Lời khai "4 caller, rủi ro HIGH" — đúng, và nó lộ chỗ brief đếm thiếu

`read_crypto_bars` có 4 caller ngoài module của nó: `measure_cross_sectional.py`, **`liquidity_sensitivity.py`**, **`measure_perp_modules.py`** (chính là đợt 105/106), **`significance_test.py`**. Brief §4 chỉ liệt kê cái đầu, vì Claude grep chuỗi `bars_crypto` nên không thấy ba script chỉ `import` hàm. Cả ba được che tự động **nhờ agent sửa ở mức hàm** — thiết kế đúng đã bù cho bảng thiếu của brief.

Các script đọc `bars_crypto` còn lại đã soát: `inventory_bingx_tradfi.py` và `binance_vision.py` đã tự ghim `2026-08-31 23:59:59+00`; `bingx_klines.py` chỉ ghi (`INSERT`).

### A.5. Con số "1.253 passed" không chạy test nào của đường tiền thật

Cả 5 test của Task A và B đều **bị `deselected`** dưới `-m "not integration"` — kể cả hai test `compute_nav` **thuần**, vì marker `integration` đặt ở mức module `test_storage.py`. Nên "+9" trong tiêu đề là toàn bộ test niêm phong crypto.

**Đây không phải bịa:** báo cáo có output chạy riêng test A/B (57 passed, 109 passed) và thông điệp lỗi phá thử #2 trùng khít với lần Claude tự tái hiện. Chỉ là con số tiêu đề **báo thiếu**. Bài học cho brief sau: tiêu chí "toàn suite `not integration`" không đủ khi test mới cần DB — phải đòi chạy đích danh.

### A.6. Claude tự chạy lại

| Kiểm | Kết quả |
|---|---|
| 5 test Task A/B trên DB test | 5 passed |
| Phá thử #2 (`price <= 0` → `price < 0`) | RED: `test_compute_nav_zero_price_unpriced_and_not_added` |
| Phá thử #4 (bỏ `AND close > 0` ở `bars_daily`) | RED: `test_read_last_close_skips_zero_in_bars_daily` **và** test hành vi GUARD-1 |
| Phục hồi `db.py` | hash trùng bản agent |
| **Toàn bộ suite, gồm integration** | **1.396 passed**, exit 0 |
| `ruff check` | All checks passed |
| `seal.py` | UTF-8 hợp lệ, không BOM |

Test hành vi GUARD-1 bắt được cả phá thử #4 — đúng như brief đòi: tiêu chí thật của Task B là **hành vi cổng**, không phải hàm.

### A.7. Bảng đếm dòng 52 / 1.088 — không phải bằng chứng độc lập

Hai con số này **do brief đưa ra trước**, nên việc agent báo "khớp chính xác 100%" không tự chứng minh điều gì — đúng lớp lỗi [[so-moc-trong-brief-thanh-dap-an-de-chep]]. Claude đã đo chúng độc lập trên DB lúc viết brief (1d 52/29.430, 1h 1.088/433.542), và phép kiểm DB ở §A.2 là bằng chứng độc lập cho việc mốc thực sự có tác dụng. Brief sau: mốc kiểm tra phải là thứ agent **không thấy trước**.

### A.8. Cần rebuild

Task A/B đổi `trading/storage/db.py` (`compute_nav` dùng ở cả collector `account_sync.py` lẫn engine `main.py`). Claude rebuild engine + collector sau khi commit.

