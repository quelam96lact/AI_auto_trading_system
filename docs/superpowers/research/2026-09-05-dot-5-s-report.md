# Báo cáo Đợt 5 — Chốt an toàn mục J (Gói S), Đo lường Đúng rổ (Gói Q) & Lịch nghỉ lễ (Gói R)

Ngày thực hiện: **05/09/2026 (Thứ Bảy)**.  
Kế hoạch thực thi: [`docs/superpowers/plans/2026-09-05-brief-giao-viec-dot-5.md`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/docs/superpowers/plans/2026-09-05-brief-giao-viec-dot-5.md).

---

## 1. TỔNG QUAN KẾT QUẢ ĐỢT 5

| Gói | Nội dung | File sản phẩm | Trạng thái | Ghi chú |
|:---:|---|---|:---:|---|
| **Gói S** | Chốt an toàn mục J (chặn nổ tiền thật khi chiến lược 1 chiều) | [`tests/test_real_trading_guard.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_real_trading_guard.py) | **HOÀN THÀNH** | 8/8 tests pass, đã phá hoại có kiểm soát (cả chốt chống mục ruỗng lẫn chốt thật) |
| **Gói Q** | So sánh đúng rổ 439 mã sinh lệnh cho Octopus Pullback | [`scripts/measure_octopus_matched_basket.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/scripts/measure_octopus_matched_basket.py)<br>[`tests/test_measure_octopus_matched_basket.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_measure_octopus_matched_basket.py) | **HOÀN THÀNH** | Chi tiết xem §2 bên dưới & file báo cáo Đợt 4 |
| **Gói R** | Tra cứu nguồn chính thức lịch nghỉ lễ 2026-2027 gỡ nút C3 | [`docs/superpowers/research/2026-09-05-dot-4-q-r-report.md`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/docs/superpowers/research/2026-09-05-dot-4-q-r-report.md) | **HOÀN THÀNH** | Căn cứ Điều 112 BLLĐ 2019, Thông báo BNV, HOSE/HNX/VSDC |

---

## 2. GÓI S: CHỐT AN TOÀN CHO MỤC J (TEST-ONLY)

### 2.1. Thiết kế Chốt An toàn
File test: [`tests/test_real_trading_guard.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_real_trading_guard.py).  
Bao gồm 4 lớp bảo vệ độc lập:

1. **Hàm thuần `_vi_pham_J(real_trading_enabled: bool, phat_duoc_bear: bool) -> bool`**:
   - Trả về `True` (vi phạm nguy hiểm) KHI VÀ CHỈ KHI `real_trading_enabled is True and phat_duoc_bear is False`.
   - Kiểm chứng đủ 4 tổ hợp:
     - `(True, False) -> True` (BẬT TIỀN THẬT + KHÔNG BÁN ĐƯỢC $\rightarrow$ VI PHẠM NGUY HIỂM)
     - `(True, True) -> False` (Bật tiền thật + 2 chiều $\rightarrow$ Hợp lệ)
     - `(False, False) -> False` (Tắt tiền thật + Dry-run $\rightarrow$ Hợp lệ)
     - `(False, True) -> False` (Tắt tiền thật + Dry-run $\rightarrow$ Hợp lệ)
2. **Phép dò `_can_emit_bear(strategy) -> bool`**:
   - Tạo chuỗi bar tất định (250 bar tăng qua warmup, sau đó 50 bar giảm dốc).
   - Đưa qua `strategy.compute_crossover(bar)` ghi nhận xem có lần nào phát `"bear"`.
3. **Chốt chống mục ruỗng (Anti-rot Invariant)**:
   - `SmaCrossStrategy` $\rightarrow$ BẮT BUỘC `_can_emit_bear == True`.
   - `OctopusPullbackStrategy` $\rightarrow$ BẮT BUỘC `_can_emit_bear == False`.
   - `_default_strategy()` $\rightarrow$ BẮT BUỘC là Octopus và `_can_emit_bear == False`.
4. **Chốt thật đọc từ file config (Live Config Guard)**:
   - Đọc trực tiếp `config/config.yaml` bằng `yaml.safe_load` (không dùng `load_config` để tránh kéo bí mật môi trường).
   - Lấy `real_trading_enabled`, dò `_default_strategy()`, và `assert not _vi_pham_J(...)`.

---

### 2.2. Kết quả Chạy Kiểm thử Gói S

Lệnh:
```bash
uv run pytest tests/test_real_trading_guard.py -v
```

Output:
```
============================= test session starts =============================
platform win32 -- Python 3.11.15, pytest-9.1.1, pluggy-1.6.0 -- D:\My_Vault_Obsidian\Project\AI_auto_trading_system\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\My_Vault_Obsidian\Project\AI_auto_trading_system
configfile: pyproject.toml
plugins: anyio-4.14.2, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 8 items

tests/test_real_trading_guard.py::test_vi_pham_J_pure_logic_four_combinations[True-False-True] PASSED [ 12%]
tests/test_real_trading_guard.py::test_vi_pham_J_pure_logic_four_combinations[True-True-False] PASSED [ 25%]
tests/test_real_trading_guard.py::test_vi_pham_J_pure_logic_four_combinations[False-False-False] PASSED [ 37%]
tests/test_real_trading_guard.py::test_vi_pham_J_pure_logic_four_combinations[False-True-False] PASSED [ 50%]
tests/test_real_trading_guard.py::test_anti_rot_sma_cross_must_emit_bear PASSED [ 62%]
tests/test_real_trading_guard.py::test_anti_rot_octopus_cannot_emit_bear PASSED [ 75%]
tests/test_real_trading_guard.py::test_anti_rot_default_strategy_is_octopus_and_cannot_emit_bear PASSED [ 87%]
tests/test_real_trading_guard.py::test_real_trading_guard_with_live_config PASSED [100%]

============================== 8 passed in 0.34s ==============================
```

---

### 2.3. Phá hoại có Kiểm soát (Destructive Testing) — Tiêu chí 4

#### (1) Phá hoại Chốt Chống Mục Ruỗng (Sabotage 1)
Tạm cho phép dò `_can_emit_bear` trả `False` cứng:
```
================================== FAILURES ===================================
___________________ test_anti_rot_sma_cross_must_emit_bear ____________________

    def test_anti_rot_sma_cross_must_emit_bear():
        strategy = SmaCrossStrategy()
>       assert _can_emit_bear(strategy) is True, (
            "ANTI-ROT FAILURE: SmaCrossStrategy không phát được tín hiệu 'bear' trên chuỗi bar mẫu! "
            "Phép dò _can_emit_bear đã bị mục ruỗng."
        )
E       AssertionError: ANTI-ROT FAILURE: SmaCrossStrategy không phát được tín hiệu 'bear' trên chuỗi bar mẫu! Phép dò _can_emit_bear đã bị mục ruỗng.
E       assert False is True
E        +  where False = _can_emit_bear(<trading.strategies.sma_cross.SmaCrossStrategy object at 0x000001E0C9ADDC50>)

tests\test_real_trading_guard.py:130: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_real_trading_guard.py::test_anti_rot_sma_cross_must_emit_bear
======================= 1 failed, 7 deselected in 0.43s =======================
```

#### (2) Phá hoại Chốt Thật (Sabotage 2)
Tạm giả lập `real_trading_enabled = True`:
```
================================== FAILURES ===================================
__________________ test_real_trading_guard_with_live_config ___________________

    def test_real_trading_guard_with_live_config():
        config_path = Path(__file__).parent.parent / "config" / "config.yaml"
        assert config_path.is_file(), f"Không tìm thấy file config tại {config_path}"
    
        with open(config_path, "r", encoding="utf-8") as f:
            cfg_data = yaml.safe_load(f) or {}
    
        real_trading_enabled = True  # SABOTAGE_TEST_REAL_TRADING_GUARD
        strategy = _default_strategy()
        phat_duoc_bear = _can_emit_bear(strategy)
    
>       assert not _vi_pham_J(real_trading_enabled, phat_duoc_bear), (
            f"NGUY HIỂM (VI PHẠM MỤC J): File config '{config_path.name}' đang bật real_trading_enabled=True, "
            f"nhưng engine đang chạy chiến lược '{strategy.__class__.__name__}' vốn KHÔNG BAO GIỜ phát "
            f"tín hiệu 'bear'. Hệ thống sẽ chỉ MUA thật mà KHÔNG BAO GIỜ BÁN thật! "
            f"Vui lòng tắt real_trading_enabled: false hoặc chuyển engine sang chiến lược hỗ trợ đóng vị thế thật."
        )
E       AssertionError: NGUY HIỂM (VI PHẠM MỤC J): File config 'config.yaml' đang bật real_trading_enabled=True, nhương engine đang chạy chiến lược 'OctopusPullbackStrategy' vốn KHÔNG BAO GIỜ phát tín hiệu 'bear'. Hệ thống sẽ chỉ MUA thật mà KHÔNG BAO GIỜ BÁN thật! Vui lòng tắt real_trading_enabled: false hoặc chuyển engine sang chiến lược hỗ trợ đóng vị thế thật.
E       assert not True
E        +  where True = _vi_pham_J(True, False)

tests\test_real_trading_guard.py:172: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_real_trading_guard.py::test_real_trading_guard_with_live_config
======================= 1 failed, 7 deselected in 0.47s =======================
```

#### (3) Khôi phục & Kiểm chứng Sạch sẽ
Lệnh:
```bash
git grep -rn "SABOTAGE" tests/
```
Output: Rỗng (Exit code 1 - không còn chuỗi đột biến).

---

## 3. TỔNG HỢP KIỂM CHỨNG TOÀN BỘ HỆ THỐNG

### 3.1. Unit Test Suite (Không cần Docker/DB/NATS)
Lệnh: `uv run pytest -m "not integration" -q`  
Kết quả: **422 passed, 100 deselected in 10.26s**

### 3.2. Integration Test Suite
Lệnh: `uv run pytest -m integration -q`  
Kết quả: **100 passed, 422 deselected in 59.42s**

### 3.3. Linter Check
Lệnh: `uv run ruff check trading tests scripts`  
Kết quả: **All checks passed!**

---

## 4. TỔNG KẾT BÀN GIAO CHO CLAUDE AUDIT

- **Gói S**: Đã hoàn thành 100% yêu cầu trong brief đợt 5, tạo file test độc lập [`tests/test_real_trading_guard.py`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/tests/test_real_trading_guard.py).
- **Gói Q & R**: Đã hoàn thành đầy đủ số liệu đo lường 3 rổ và căn cứ pháp lý lịch nghỉ lễ.
- **Tuân thủ quy tắc an toàn**:
  - Không sửa `trading/` bất kỳ dòng nào.
  - Không sửa `config/config.yaml`.
  - Không nạp lại `bars_crypto`, không tạo bảng DB mới.
  - `real_trading_enabled` vẫn giữ nguyên `false`.
  - Chưa commit / push, sẵn sàng để Claude audit.

---

## PHỤ LỤC — ĐÍNH CHÍNH KHI AUDIT (Claude, 05/09)

Gói S nhận được, thiết kế đúng brief: hàm thuần tách rời, bốn tổ hợp, đọc config
bằng `yaml.safe_load`, hai lần phá hoại có kiểm soát kèm output đỏ nguyên văn,
`grep SABOTAGE` rỗng. Không chạm `trading/`, không chạm `config/`.

**Nhưng chốt chống mục ruỗng chỉ hoạt động ở MỘT trong hai phía.**

### Phép dò chưa từng chạm tới logic tín hiệu của octopus

`_generate_deterministic_bars()` phát bar với `volume = 100_000` và giá 100→350,
tức giá trị giao dịch cao nhất **35 triệu/phiên**. Ngưỡng `min_avg_value_20` của
octopus là **2 tỷ**. Đo trực tiếp:

```
volume=     100,000: so bar cong thanh khoan MO = 0/300
volume=  20,000,000: so bar cong thanh khoan MO = 280/300
```

Cổng thanh khoản **đóng ở toàn bộ 300/300 bar**. Nghĩa là
`test_anti_rot_octopus_cannot_emit_bear` không hề kiểm chiến lược — octopus trả
`None` vì bar quá nhỏ, chưa bao giờ chạy tới chỗ quyết định tín hiệu. Test đó sẽ
xanh y hệt với **bất kỳ** chiến lược nào im lặng vì **bất kỳ** lý do nào.

Kết luận "octopus không phát bear" vẫn **đúng** (kiểu trả về của
`compute_crossover` chỉ có `None | "bull"`), nhưng bằng chứng đưa ra thì rỗng.
Phía sma_cross thì làm việc thật — nên chốt an toàn tổng thể không mục, chỉ là
yếu hơn nhiều so với vẻ ngoài của nó.

**Đây là lần thứ tư dự án vấp cùng một hình dạng lỗi:** một ngưỡng đúng trong hệ
quy chiếu thị trường thật (2 tỷ VND của HOSE) mang sang một hệ quy chiếu khác —
lần này là dữ liệu tổng hợp trong test. Ba lần trước: lô 100 áp lên crypto,
`min_avg_value_20` áp lên USDT, `1000PEPE` so với `PEPE`. Trớ trêu là **chính
hằng số này** đã gây ra lần thứ hai.

### Đã sửa khi audit

- `_VOLUME = 20_000_000` (giá trị 2–7 tỷ/phiên, trên ngưỡng), kèm chú thích nói
  rõ vì sao con số không tuỳ tiện.
- Thêm `test_phep_do_vuot_qua_duoc_cong_thanh_khoan_cua_octopus`: bắt phép dò
  phải mở được cổng, để lời khẳng định kia nói về **chiến lược** chứ không nói
  về độ nhỏ của dữ liệu giả.
- Phá hoại có kiểm soát cho chính test mới (hạ `_VOLUME` về 100.000):

```
E       AssertionError: Phep do KHONG cham toi logic tin hieu cua octopus: cong
        thanh khoan dong o toan bo bar (min_avg_value_20 = 2,000,000,000, gia tri
        bar mau qua nho). Tang _VOLUME cho toi khi cong mo.
E       assert 0 > 0
1 failed, 8 passed
```

Khôi phục, `grep -rn "SABOTAGE" tests/ scripts/ trading/` rỗng.

### Điều còn chưa chắc, ghi lại thay vì giấu

Kể cả với volume mới, octopus **không phát tín hiệu nào** trên chuỗi bar này —
không `"bear"` mà cũng không `"bull"`. Chuỗi tăng đều toàn nến xanh nên điều
kiện "≥2 nến đỏ trong 5 phiên trước" không bao giờ thoả. Vậy phép dò mới chứng
minh được là *cổng đã mở*, chưa chứng minh được *đường vào lệnh đã chạy*. Muốn
mạnh hơn nữa thì phải dựng một chuỗi pullback thật (xanh dài, hai nến đỏ, MACD
histogram còn dương) và bắt octopus phát `"bull"` ít nhất một lần. Chưa làm —
ghi vào đây để không ai tưởng chốt này mạnh hơn thực tế.

### Nền test sau audit

```
uv run pytest -m "not integration" -q  ->  423 passed
uv run pytest -m integration -q        ->  100 passed
uv run ruff check trading tests scripts -> All checks passed!
```
