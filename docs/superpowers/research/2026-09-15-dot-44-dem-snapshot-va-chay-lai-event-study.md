# Báo cáo Đợt 44 — Đếm snapshot để hết mù, và chạy lại event study cho đúng

- **Ngày thực hiện:** 14/09/2026 (ngoài giờ giao dịch phiên chiều).
- **Người thực hiện:** Gemini Flash 3.8 (theo phân công Brief 44 của Claude).
- **Mục tiêu:**
  1. Task 1 (Đường VN): Đếm snapshot mỗi bucket trong `BarLatch`, thêm vào alert `bars closed`, gắn chuông im lặng trong phiên 120s trong `housekeeping_tick`, triển khai container ngoài giờ có tag rollback.
  2. Task 2 (Đường VN): Đo thêm ba phiên 15/09, 16/09, 17/09 sau 15:05 -> **CHƯA LÀM — chưa tới phiên**.
  3. Task 3 (Đường Crypto): Sửa event study module C theo phân phối null thống kê giá trị lớn nhất (max-statistic) qua hoán vị khối 48h (1,000 lần) và ngưỡng chi phí vòng lệnh `2 * BINGX_PERP_TAKER = 0.0010`. Đánh giá theo 4 tiêu chí chốt trước (§3.3).

---

## 1. Task 1 (Đường VN) — Đếm snapshot & Chuông im lặng trong phiên

### 1.1. Kết quả 7 tiêu chí kiểm chứng (§1.3)

| # | Tiêu chí | Kết quả | Chi tiết kiểm chứng |
|---|---|---|---|
| 1 | Toàn bộ 8 test cũ của `test_collector_latch.py` pass 100%, không sửa assert nào | **ĐẠT** | `git diff tests/test_collector_latch.py` chỉ có dấu `+` (thêm mới), không có dòng bị xoá hoặc sửa. |
| 2 | Ba snapshot cùng bucket, bucket đóng -> `snapshot_count = 3` | **ĐẠT** | Test `test_latch_three_snapshots_closed_reports_count_three` pass. |
| 3 | Bucket đóng bằng `flush_due` cũng trả đúng số đếm snapshot | **ĐẠT** | Test `test_latch_flush_due_reports_correct_snapshot_count` pass (`snapshot_count = 3`). |
| 4 | Số đếm reset khi sang bucket mới, không cộng dồn | **ĐẠT** | Test `test_latch_snapshot_count_resets_on_new_bucket` pass (`closed_t0 = 3`, `closed_t1 = 2`). |
| 5 | Hành vi đóng nến không đổi (kịch bản đợt 36) | **ĐẠT** | Test `test_latch_close_behavior_unchanged_dot36_scenario` pass: `pub.publish` gọi đúng 1 lần, alert `bars closed` có `snapshots=[3]`. |
| 6 | Chuông im lặng trong phiên (120s im lặng -> phát 1 WARN, lặp lại không spam, ngoài giờ không phát) | **ĐẠT** | Test `test_silence_alarm_in_trading_hours_and_outside` pass toàn diện các nhánh. |
| 7 | Full test suite, ruff sạch, cổng cứng VN khớp tuyệt đối | **ĐẠT** | **748 passed** (tăng 7 tests so với mốc 741), ruff sạch 100%, cổng cứng VN khớp từng chữ số. |

### 1.2. Triển khai container ngoài giờ giao dịch (§1.4)

- **Thời điểm thực hiện:** ~16:35 giờ Việt Nam (ngoài giờ giao dịch, sau 15:00).
- **Tag ảnh rollback trước khi build:**
  ```bash
  docker tag ai_auto_trading_system-collector dot44-rollback-collector:pre
  ```
- **ID ảnh vừa build:**
  `sha256:9c66a1dc8ec21c5ed860490fbd0556a9da4cfcd70556d77eaa4ce6ad0ac65a3e`
- **ID ảnh đang chạy:**
  `sha256:9c66a1dc8ec21c5ed860490fbd0556a9da4cfcd70556d77eaa4ce6ad0ac65a3e`
  *(Hai ID khớp nhau 100%)*
- **Kiểm tra code mới bên trong container đang chạy:**
  ```bash
  docker exec ai_auto_trading_system-collector-1 grep -c "snapshots" /app/trading/collector/main.py
  # Output: 8
  ```
  Code mới đã có mặt và đang chạy thực tế trong container `collector`.

---

## 2. Task 2 (Đường VN) — Đo thêm ba phiên, chưa chỉnh `grace`

**Trạng thái:** **CHƯA LÀM — chưa tới phiên.**
Hôm nay là chiều thứ Hai 14/09/2026. Các phiên đo tiếp theo (thứ Ba 15/09, thứ Tư 16/09, thứ Năm 17/09) sẽ được thu thập sau 15:05 mỗi ngày bằng `scripts/stream_health_check.py` và `scripts/measure_session_stream_metrics.py`.

---

## 3. Task 3 (Đường Crypto) — Chạy lại Event Study cho đúng

### 3.1. Cập nhật phương pháp (§3.1, §3.2, §3.3)

1. **Thống kê giá trị lớn nhất (Max-statistic null distribution):**
   - Với mỗi lần hoán vị khối 48h (1,000 lần), tính lợi suất trung bình sau sự kiện ở cả 3 chân trời (1h, 4h, 24h).
   - Quy mỗi lợi suất thành phân vị thực nghiệm qua `empirical_percentile_rank` (import từ `trading.metrics`) trong phân phối riêng của chân trời đó.
   - Lấy giá trị lớn nhất trong 3 phân vị: $M^{(b)} = \max(p_{\text{1h}}^{(b)}, p_{\text{4h}}^{(b)}, p_{\text{24h}}^{(b)})$.
   - Ngưỡng tới hạn `max_null_p95` là phân vị 95 của phân phối max null này (tính bằng `calculate_percentile` từ `trading.metrics`).
2. **Khấu trừ chi phí vòng lệnh trước thống kê:**
   - Phí taker một vòng lệnh: `ROUND_TRIP_FEE = 2 * BINGX_PERP_TAKER = 0.0010` (10 điểm cơ bản / 0.10%), import từ `trading.crypto_fees`.
   - `loi_the_rong = (mean_event - mean_uncond) - ROUND_TRIP_FEE`.
3. **Tiêu chí chốt trước 4 điều kiện (§3.3):**
   - Điều 1: Số sự kiện $N \ge 30$.
   - Điều 2: `loi_the_rong > 0` ở ít nhất một chân trời.
   - Điều 3: Phân vị lớn nhất của kết quả thật vượt phân vị 95 của phân phối null giá trị lớn nhất (`max_actual_rank > max_null_p95`).
   - Điều 4: Chân trời thoả (2) và chân trời thoả (3) là **cùng một chân trời**.

### 3.2. Kết quả kiểm chứng unit tests Task 3 (§3.4)

- Đã cập nhật `tests/test_event_study.py`:
  - 5 tests cũ tiếp tục pass 100%.
  - Bổ sung `test_6_net_edge_formula_exact_deduction`: xác nhận `loi_the_rong` trừ đúng 0.0010.
  - Bổ sung `test_7_high_percentile_but_negative_net_edge_concludes_negative`: xác nhận chân trời có phân vị cao nhưng lợi thế ròng âm thì kết luận toàn cuộc là **ÂM**.
  - Khẳng định đối chứng dương (`test_3_positive_control`) vẫn xanh áp đảo cả 4 điều kiện (`overall_pass is True`).
- Kết quả test: **7 passed in 0.63s**.

### 3.3. Kết quả chạy thật trên dữ liệu In-Sample (BTCUSDT 2024-01-01 -> 2025-12-31 UTC)

Lệnh chạy terminal:
```bash
python scripts/event_study_module_c.py
```

Output nguyên văn:
```text
=== EVENT STUDY: MODULE C THIẾU VẾ LIQUIDATION ===
Tập phân tích: BTCUSDT IS 2024-01-01 -> 2025-12-31 UTC (Năm 2026 niêm phong)

Tổng số giờ trong IS: 17544 nến.
Số sự kiện kích hoạt (module C thiếu vế liquidation): 72

--- BẢNG SỐ GIỜ THOẢ MÃN TỪNG VẾ RIÊNG LẺ (§4.3) ---
1. Xu hướng (close>EMA50 & EMA20>EMA50 & EMA50_t>EMA50_{t-3}): 7850 giờ (44.74%)
2. Funding (funding_z < +1.0):                                    12820 giờ (73.07%)
3. OI (oi_chg_3h <= -0.015):                                      1173 giờ (6.69%)
4. Nến xác nhận (close > EMA20):                                  9304 giờ (53.03%)
5. Order flow (delta_norm > 0 & cvd_3h_t > cvd_3h_{t-3}):         5048 giờ (28.77%)
-> HỢP CẢ 5 VẾ (module C thiếu vế liquidation):                                  72 giờ (0.41%)

--- PHÉP ĐO LỢI THẾ RÒNG VÀ KIỂM ĐỊNH GIÁ TRỊ LỚN NHẤT (Brief 44 §3.1, §3.2) ---
Phí vòng lệnh: 2 * BINGX_PERP_TAKER = 0.10% (10 bps)
Ngưỡng thống kê Max Null P95: 98.05%
Chân trời  | Lợi suất TB SK (%) | K.điều kiện (%) | Chênh lệch (%)  | Lợi thế ròng (%) | Phân vị (%)  | Vượt Max P95? | Lợi thế ròng > 0?
--------------------------------------------------------------------------------------------------------------------------
1h         | +0.1285%            | +0.0055%      | +0.1231%        | +0.0231%         |  97.50%      | Không         | CÓ
4h         | +0.2334%            | +0.0218%      | +0.2116%        | +0.1116%         |  94.10%      | Không         | CÓ
24h        | +0.1972%            | +0.1288%      | +0.0684%        | -0.0316%         |  57.80%      | Không         | KHÔNG

Chân trời đạt phân vị lớn nhất: 1h (97.50%)

================ KẾT LUẬN TIÊU CHÍ CHỐT TRƯỚC (Brief 44 §3.3) ================
1. Số sự kiện N >= 30: 72 -> ĐẠT
2. Lợi thế ròng > 0 ở ít nhất 1 chân trời: ĐẠT
3. Phân vị lớn nhất (97.50%) vượt Max Null P95 (98.05%): KHÔNG ĐẠT
4. Chân trời thoả (2) và (3) là cùng một chân trời (1h): KHÔNG ĐẠT
--------------------------------------------------------------------------------
>>> KẾT LUẬN TOÀN CUỘC: ÂM — Không thoả mãn đủ 4 điều kiện chốt trước.
```

### 3.4. Đánh giá kết quả

- Ngưỡng tới hạn của phân phối null giá trị lớn nhất là **98.05%** (cao hơn ngưỡng 95% đơn lẻ vì đã hiệu chỉnh cho việc thử 3 chân trời song song).
- Chân trời có phân vị cao nhất là **1h** với phân vị **97.50%** < 98.05% $\implies$ **Không đạt ý nghĩa thống kê**.
- Mặc dù chân trời 1h và 4h có lợi thế ròng dương sau phí (+2.31 bps và +11.16 bps), nhưng dưới bài kiểm tra thống kê khắt khe đúng chuẩn chống data-snooping, kết quả không vượt qua ngưỡng may rủi.
- **KẾT LUẬN: ÂM.**
- Tuân thủ nghiêm ngặt Brief §3.3: **Năm 2026 tiếp tục niêm phong.** Không mở Out-of-Sample cho cấu hình này.

---

## 4. Tình trạng kỹ thuật toàn hệ thống

1. **Test Suite:** **748 passed** in 53.81s (vượt mốc 741 cũ đúng 7 tests mới).
2. **Linter:** `ruff check .` -> **All checks passed!** (0 cảnh báo, 0 lỗi).
3. **Cổng cứng VN:** Khớp tuyệt đối từng chữ số:
   ```text
   TỔNG: strat -1,615,319,902 | BH 1,897,587,481,903 | diff -1,899,202,801,806 | lệnh 1,514 | mã sinh lệnh 439 | mã đủ thanh khoản 748 | dòng bẩn 10,459
   ```

---

## 5. Bảng Git Status & Git Diff

### `git status --short`
```text
 M AGENTS.md
 M CLAUDE.md
 M README.md
 M scripts/event_study_module_c.py
 M tests/test_collector_latch.py
 M tests/test_event_study.py
 M trading/collector/latch.py
 M trading/collector/main.py
?? docs/superpowers/research/2026-09-15-dot-44-dem-snapshot-va-chay-lai-event-study.md
```

### `git diff --stat` (trên các file đợt 44)
```text
 scripts/event_study_module_c.py | 122 ++++++++++++----
 tests/test_collector_latch.py   | 302 ++++++++++++++++++++++++++++++++++++++++
 tests/test_event_study.py       |  78 +++++++++++
 trading/collector/latch.py      |  23 +++
 trading/collector/main.py       |  62 +++++++-
```

### `git diff tests/test_collector_latch.py`
Toàn bộ 8 assertions/tests cũ được giữ nguyên 100%. Diff chỉ chứa phần thêm mới:
```diff
@@ -204,4 +204,306 @@
     assert closed is not None
     assert closed.ts == t1
     assert closed.close == 101.5
+
+
+# ============ Brief đợt 44 Task 1: Snapshot Counting & Silence Alarm Tests ============
+
+
+def test_latch_three_snapshots_closed_reports_count_three():
+    """Brief 44 Tiêu chí 2: Ba snapshot vào cùng một bucket, bucket đóng -> snapshot_count = 3."""
+    latch = BarLatch(interval_seconds=300, grace_seconds=60)
+    t0 = datetime(2026, 9, 10, 9, 30, tzinfo=TZ)
+    t1 = datetime(2026, 9, 10, 9, 35, tzinfo=TZ)
+
+    b1 = Bar("SSI", t0, 30.0, 30.5, 29.8, 30.2, 1000)
+    b2 = Bar("SSI", t0, 30.0, 30.8, 29.8, 30.6, 5000)
+    b3 = Bar("SSI", t0, 30.0, 31.0, 29.7, 30.9, 12000)
+    b4 = Bar("SSI", t1, 31.0, 31.2, 30.8, 31.1, 500)
+
+    latch.offer(b1)
+    latch.offer(b2)
+    latch.offer(b3)
+    closed = latch.offer(b4)
+
+    assert closed is not None
+    assert closed.symbol == "SSI"
+    assert closed.ts == t0
+    assert getattr(closed, "snapshot_count", None) == 3
+
+
+def test_latch_flush_due_reports_correct_snapshot_count():
+    """Brief 44 Tiêu chí 3: Bucket đóng bằng flush_due cũng trả đúng số đếm snapshot."""
+    latch = BarLatch(interval_seconds=300, grace_seconds=60)
+    t0 = datetime(2026, 9, 10, 14, 45, tzinfo=TZ)
+
+    b1 = Bar("VCB", t0, 90.0, 90.5, 89.8, 90.2, 10000)
+    b2 = Bar("VCB", t0, 90.0, 90.8, 89.8, 90.4, 30000)
+    b3 = Bar("VCB", t0, 90.0, 91.0, 89.5, 90.5, 50000)
+
+    latch.offer(b1)
+    latch.offer(b2)
+    latch.offer(b3)
+
+    # Sau hạn grace: 14:45 + 300s + 60s = 14:51:00 -> 14:51:05
+    now_after = t0 + timedelta(seconds=365)
+    due = latch.flush_due(now_after)
+
+    assert len(due) == 1
+    assert due[0].symbol == "VCB"
+    assert due[0].ts == t0
+    assert due[0].close == 90.5
+    assert getattr(due[0], "snapshot_count", None) == 3
+
+
+def test_latch_snapshot_count_resets_on_new_bucket():
+    """Brief 44 Tiêu chí 4: Số đếm reset khi sang bucket mới — bucket thứ hai không cộng dồn bucket thứ nhất."""
+    latch = BarLatch(interval_seconds=300, grace_seconds=60)
+    t0 = datetime(2026, 9, 10, 9, 30, tzinfo=TZ)
+    t1 = datetime(2026, 9, 10, 9, 35, tzinfo=TZ)
+    t2 = datetime(2026, 9, 10, 9, 40, tzinfo=TZ)
+
+    # Khung t0: 3 snapshot
+    b0_1 = Bar("SSI", t0, 30.0, 30.5, 29.8, 30.2, 1000)
+    b0_2 = Bar("SSI", t0, 30.0, 30.8, 29.8, 30.6, 5000)
+    b0_3 = Bar("SSI", t0, 30.0, 31.0, 29.7, 30.9, 12000)
+
+    latch.offer(b0_1)
+    latch.offer(b0_2)
+    latch.offer(b0_3)
+
+    # Khung t1: snapshot đầu tiên tới -> chốt khung t0
+    b1_1 = Bar("SSI", t1, 31.0, 31.2, 30.8, 31.1, 500)
+    closed_t0 = latch.offer(b1_1)
+    assert closed_t0 is not None
+    assert getattr(closed_t0, "snapshot_count", None) == 3
+
+    # Khung t1: nhận thêm snapshot thứ hai
+    b1_2 = Bar("SSI", t1, 31.0, 31.5, 30.8, 31.3, 1500)
+    assert latch.offer(b1_2) is None
+
+    # Khung t2: snapshot đầu tiên tới -> chốt khung t1
+    b2_1 = Bar("SSI", t2, 31.5, 31.8, 31.2, 31.6, 800)
+    closed_t1 = latch.offer(b2_1)
+    assert closed_t1 is not None
+    assert closed_t1.ts == t1
+    # Số đếm của khung t1 phải là 2, KHÔNG cộng dồn 3 của khung t0 (không thành 5)
+    assert getattr(closed_t1, "snapshot_count", None) == 2
+
+
+async def test_latch_close_behavior_unchanged_dot36_scenario(monkeypatch):
+    """Brief 44 Tiêu chí 5: Hành vi đóng nến không đổi — dựng lại đúng kịch bản test đợt 36
+    (ba snapshot khung A, một snapshot khung B) và khẳng định pub.publish vẫn được gọi đúng một lần,
+    với đúng giá trị cũ, và alert 'bars closed' kèm snapshots=[3].
+    """
+    import asyncio
+    from unittest.mock import AsyncMock, MagicMock
+
+    import trading.collector.main as collector_main
+
+    alerts_seen = []
+    monkeypatch.setattr(
+        collector_main,
+        "alert",
+        lambda level, msg, **kwargs: alerts_seen.append((level, msg, kwargs)),
+    )
+
+    t0 = datetime(2026, 9, 10, 9, 30, tzinfo=TZ)
+    t1 = datetime(2026, 9, 10, 9, 35, tzinfo=TZ)
+
+    bars_sequence = [
+        Bar("VCB", t0, 90.0, 90.5, 89.8, 90.2, 1000),
+        Bar("VCB", t0, 90.0, 90.8, 89.8, 90.4, 5000),
+        Bar("VCB", t0, 90.0, 91.0, 89.7, 90.9, 12000),  # snapshot 3 của khung A
+        Bar("VCB", t1, 91.0, 91.5, 90.8, 91.2, 2000),   # snapshot 1 của khung B
+    ]
+
+    seq_idx = 0
+
+    def fake_parse(msg):
+        nonlocal seq_idx
+        b = bars_sequence[seq_idx]
+        seq_idx += 1
+        return b
+
+    monkeypatch.setattr(collector_main, "parse_interval_message", fake_parse)
+
+    wd = MagicMock()
+    storage = MagicMock()
+    pub = MagicMock()
+    pub.publish = AsyncMock()
+
+    persist_tasks = set()
+    latch = BarLatch(interval_seconds=300, grace_seconds=60)
+    handler = collector_main.make_stream_message_handler(
+        wd, storage, pub, persist_tasks=persist_tasks, latch=latch
+    )
+
+    # Gửi 3 message khung A
+    handler({"dummy": 1})
+    handler({"dummy": 2})
+    handler({"dummy": 3})
+
+    # Gửi 1 message khung B
+    handler({"dummy": 4})
+
+    # Chờ các task async hoàn thành
+    if persist_tasks:
+        await asyncio.gather(*list(persist_tasks))
+
+    # pub.publish ĐÚNG 1 LẦN với đúng giá trị cũ
+    assert pub.publish.call_count == 1, f"pub.publish phai duoc goi dung 1 lan, thuc te={pub.publish.call_count}"
+    published_bar = pub.publish.call_args[0][0]
+    assert published_bar.symbol == "VCB"
+    assert published_bar.ts == t0
+    assert published_bar.close == 90.9
+    assert published_bar.volume == 12000
+
+    # Kiểm tra alert 'bars closed' có chứa snapshots=[3]
+    bars_closed_alerts = [
+        (lvl, msg, kw)
+        for lvl, msg, kw in alerts_seen
+        if lvl == "INFO" and msg == "bars closed"
+    ]
+    assert len(bars_closed_alerts) == 1
+    closed_alert_kw = bars_closed_alerts[0][2]
+    assert closed_alert_kw["symbols"] == ["VCB"]
+    assert closed_alert_kw["snapshots"] == [3]
+
+
+async def test_silence_alarm_in_trading_hours_and_outside(monkeypatch):
+    """Brief 44 Tiêu chí 6: Test chuông im lặng:
+    - Giả lập 120s không snapshot trong giờ -> phát đúng một WARN.
+    - Lặp thêm tick nữa -> không phát thêm.
+    - Ngoài giờ -> không phát.
+    - Nhận snapshot mới -> sau 120s im lặng tiếp theo -> phát lại đúng 1 WARN cho đợt mới.
+    """
+    import time
+    from unittest.mock import MagicMock
+
+    import trading.collector.main as collector_main
+    from trading.collector.main import HousekeepingState, housekeeping_tick
+    from trading.config import Config
+
+    cfg = Config(
+        symbols=["VCB"],
+        indices=[],
+        bar_interval_minutes=5,
+        ssi_equity_accounts=[],
+        holidays=set(),
+        db_dsn="postgresql://x:***@localhost/db",
+        nats_url="nats://localhost:4222",
+        nats_stream="BARS",
+        watchdog_stale_seconds=180,
+        watchdog_max_failures=3,
+        ssi_consumer_id="c",
+        ssi_consumer_secret="s",
+        ssi_api_key="k",
+        ssi_api_secret="a",
+        ssi_private_key="pk",
+        real_trading_enabled=False,
+        real_order_account="ACC",
+    )
+
+    alerts_seen = []
+    monkeypatch.setattr(
+        collector_main,
+        "alert",
+        lambda level, msg, **kwargs: alerts_seen.append((level, msg, kwargs)),
+    )
+
+    storage = MagicMock()
+    wd = MagicMock()
+    latch = BarLatch(interval_seconds=300, grace_seconds=60)
+    state = HousekeepingState()
+
+    fake_mono = 1000.0
+    fake_wall = datetime(2026, 9, 10, 10, 0, 0, tzinfo=TZ)  # Thứ 5, 10:00:00 (trong phiên)
+
+    monkeypatch.setattr(time, "monotonic", lambda: fake_mono)
+
+    class _FrozenDt:
+        def __init__(self, dt_val):
+            self._dt = dt_val
+
+        def now(self, tz=None):
+            return self._dt
+
+    frozen_dt = _FrozenDt(fake_wall)
+    monkeypatch.setattr(collector_main, "datetime", frozen_dt)
+
+    # Tick 1 (t=0s trong phiên): Khởi tạo, chưa có 120s trôi qua
+    await housekeeping_tick(cfg, storage, wd, state, latch=latch)
+    silent_warns = [
+        (lvl, msg, kw)
+        for lvl, msg, kw in alerts_seen
+        if lvl == "WARN" and "khong nhan snapshot nao" in msg
+    ]
+    assert len(silent_warns) == 0
+
+    # Tick 2 (t=120s trong phiên, không snapshot nào tới): Phát đúng 1 WARN
+    fake_mono += 120.0
+    frozen_dt._dt = fake_wall + timedelta(seconds=120)
+    await housekeeping_tick(cfg, storage, wd, state, latch=latch)
+
+    silent_warns = [
+        (lvl, msg, kw)
+        for lvl, msg, kw in alerts_seen
+        if lvl == "WARN" and "khong nhan snapshot nao" in msg
+    ]
+    assert len(silent_warns) == 1
+    assert silent_warns[0][2]["seconds"] == 120
+    assert silent_warns[0][2]["last_snapshot_ts"] is None
+
+    # Tick 3 (t=150s trong phiên, vẫn chưa có snapshot): KHÔNG phát thêm (không spam)
+    fake_mono += 30.0
+    frozen_dt._dt = fake_wall + timedelta(seconds=150)
+    await housekeeping_tick(cfg, storage, wd, state, latch=latch)
+
+    silent_warns = [
+        (lvl, msg, kw)
+        for lvl, msg, kw in alerts_seen
+        if lvl == "WARN" and "khong nhan snapshot nao" in msg
+    ]
+    assert len(silent_warns) == 1, "Khong duoc spam chuong im lang moi tick"
+
+    # Nhận một snapshot mới
+    b_snap = Bar("VCB", datetime(2026, 9, 10, 10, 0, tzinfo=TZ), 90.0, 90.5, 89.8, 90.2, 1000)
+    latch.offer(b_snap)
+
+    # Tick 4 (30s sau snapshot mới): Không alert vì mới 30s
+    fake_mono += 30.0
+    frozen_dt._dt = fake_wall + timedelta(seconds=180)
+    await housekeeping_tick(cfg, storage, wd, state, latch=latch)
+    silent_warns = [
+        (lvl, msg, kw)
+        for lvl, msg, kw in alerts_seen
+        if lvl == "WARN" and "khong nhan snapshot nao" in msg
+    ]
+    assert len(silent_warns) == 1
+
+    # Tick 5 (125s sau snapshot mới): Lại im lặng 125s -> phát thêm 1 WARN cho đợt mới
+    fake_mono += 95.0  # tổng từ snapshot: 30 + 95 = 125s
+    frozen_dt._dt = fake_wall + timedelta(seconds=275)
+    await housekeeping_tick(cfg, storage, wd, state, latch=latch)
+    silent_warns = [
+        (lvl, msg, kw)
+        for lvl, msg, kw in alerts_seen
+        if lvl == "WARN" and "khong nhan snapshot nao" in msg
+    ]
+    assert len(silent_warns) == 2
+    assert silent_warns[1][2]["seconds"] == 125
+    assert silent_warns[1][2]["last_snapshot_ts"] == b_snap.ts.isoformat()
+
+    # Ngoài giờ giao dịch: 16:00:00 (phiên đã đóng)
+    outside_wall = datetime(2026, 9, 10, 16, 0, 0, tzinfo=TZ)
+    frozen_dt._dt = outside_wall
+    fake_mono += 500.0  # trôi qua 500s ngoài giờ
+    await housekeeping_tick(cfg, storage, wd, state, latch=latch)
+
+    silent_warns = [
+        (lvl, msg, kw)
+        for lvl, msg, kw in alerts_seen
+        if lvl == "WARN" and "khong nhan snapshot nao" in msg
+    ]
+    assert len(silent_warns) == 2, "Ngoai gio giao dich KHONG duoc phat chuong im lang"
```
