# Brief đợt 229: cờ tắt chiến lược của engine (dừng giao dịch paper 3 mã mà không gây báo động giả)

Ngày 13/11/2026. Người giao: Claude (Lead). Người làm: **Builder**. **Hạn: 18:00 Chủ nhật 15/11** (Lead cần deploy trước phiên thứ Hai 16/11). Làm việc này **trước** Việc 2 (chạy khám phá) của đợt 227.

## Bối cảnh

- Chủ dự án quyết định 13/11: bỏ chiến lược paper trên HPG/IJC/AAA, giữ collector.
- Khảo sát đợt 228 (`docs/audit/2026-11-14-khao-sat-engine-truoc-khi-viet-lai.md`, mục A và C) cho thấy:
  - `docker compose stop engine` sẽ sinh khoảng 60–63 tin CRITICAL heartbeat mỗi ngày giao dịch, cộng tin của container-health, engine-consumer, deploy-drift;
  - `scripts/heartbeat_check.py:81` và `scripts/check_silent_engine.py:28` import `CAPITAL` và `_default_strategy` từ `trading/engine/main.py` ở mức module. Đổi tên hoặc xoá hai symbol này làm bốn job chết im lặng;
  - hiện **không có vị thế paper nào mở** (ba dòng `positions` đều `qty = 0`).
- Quyết định của Lead: **giữ container engine chạy, tắt chiến lược bằng một cờ**. Engine vẫn nhận nến, ack consumer NATS, ghi heartbeat; không sinh tín hiệu, không đặt lệnh. Không job giám sát nào phải sửa.

## Việc phải làm

1. **Chiến lược rỗng**, file mới `trading/strategies/null_strategy.py`, lớp `NullStrategy` thoả đúng Protocol `Strategy` (`trading/strategy.py:26-52`):
   - `on_bar` trả `None`; `compute_crossover` không sinh tín hiệu (trả đúng kiểu mà Protocol yêu cầu cho "không có gì"); `last_crossover` và `last_atr` trả `None`;
   - `warmup_bars = 1`. **Không được là 0**: `main.py:282` gọi `read_last_bars(sym, 0)`, rồi `:306 clean_hist[-1]` ném `IndexError` và engine chết lúc khởi động.
2. **Cờ**: biến môi trường `ENGINE_STRATEGY_DISABLED`. Giá trị `"1"` là tắt; không đặt hoặc giá trị khác là chạy như cũ.
   - Chỗ sửa duy nhất trong luồng: `trading/engine/main.py:237`. Khi `strategy is None` và cờ bật thì dùng `NullStrategy()`, ngược lại `_default_strategy()` như cũ.
   - **Không sửa** `_default_strategy()`, không đổi tên `CAPITAL` hay `_default_strategy`. `check_silent_engine.py` phát lại `_default_strategy()` trên DB; giữ nguyên thì job này không báo động.
   - Khi cờ bật, lúc khởi động gửi **một** `alert("INFO", ...)` nêu rõ engine đang chạy ở chế độ tắt chiến lược theo `ENGINE_STRATEGY_DISABLED`.
3. **`docker-compose.yml`**: thêm đúng một dòng vào `environment` của service `engine`: `ENGINE_STRATEGY_DISABLED: "1"`, kèm một dòng chú thích ghi ngày 13/11, đợt 229, và lý do. Không đụng service khác.
4. **Test** (thêm vào `tests/test_engine_main.py` hoặc file mới `tests/test_null_strategy.py`; dùng đúng kiểu fake/fixture mà `test_engine_main.py` đang dùng):
   - (a) cờ bật: engine khởi động được với mã có lịch sử nến, **không** ném `IndexError`; nạp một chuỗi nến mà với `_default_strategy` hoặc chiến lược test có sinh lệnh, thì với cờ bật **không có lệnh nào** được đặt, và message vẫn được ack;
   - (b) cờ bật: heartbeat của engine vẫn được ghi (dùng cách mà test hiện có đang kiểm heartbeat/idle_maintenance; nếu chưa có test nào kiểm thì báo Lead trước khi tự dựng);
   - (c) cờ không đặt, và cờ = `"0"`: chiến lược là `_default_strategy()` như cũ (`test_default_strategy_la_octopus` phải còn pass, không sửa);
   - (d) tham số `strategy=` truyền tường minh thắng cờ (các test hiện có ghim `sma_cross` qua tham số này phải còn pass khi cờ bật trong môi trường test);
   - (e) `NullStrategy().warmup_bars >= 1`.
   - Test (a) phải **thất bại trên code cũ** (code cũ bỏ qua cờ nên vẫn đặt lệnh). Gửi output thật.

## Trước khi sửa

- `node .gitnexus/run.cjs impact <hàm chứa main.py:237> --direction upstream --repo .` và `... context _default_strategy --repo .`. Báo caller, process, mức rủi ro. HIGH/CRITICAL thì báo Lead trước khi sửa. **Không npx.**
- Grep `_default_strategy` và `CAPITAL` trong `scripts/` và `tests/` (GitNexus không index `scripts/`), liệt kê.

## Cách làm việc: BẮT BUỘC dùng worktree riêng

`scripts/heartbeat_check.py` chạy từ thư mục chính và import `trading/engine/main.py` từ đó.

- `git worktree add ../AI_auto_trading_system-dot229 -b dot229 HEAD`. Làm mọi việc trong đó. Commit trong nhánh `dot229` thì được.
- Không sửa file nào trong thư mục chính. Các file `research227_*` đang làm dở ở thư mục chính cứ để nguyên.

## Phạm vi

- **Được sửa:** `trading/engine/main.py` (chỉ quanh dòng 237 và import cần thiết), `docker-compose.yml` (một dòng + chú thích), `tests/test_engine_main.py`.
- **Được tạo:** `trading/strategies/null_strategy.py`, `tests/test_null_strategy.py`.
- **Không đụng:** `trading/engine/logic.py`, `trading/strategy.py`, `trading/strategies/` (file khác), `trading/config.py`, `config/config.yaml`, mọi file trong `scripts/`, collector, scheduler.
- Giữ style hiện có. Thấy vấn đề khác thì báo.

## Cấm

- `docker compose up/stop/restart/build`: **Lead deploy**, Builder không.
- Chạy `sched.sh`, gửi Telegram, ghi DB thật, ghi `logs/`.
- Commit lên `main`, push, `npx`.

## Tiêu chí hoàn thành (bằng chứng gửi Lead)

1. Output impact/context và danh sách grep.
2. Tên test mới; output test (a) **trên code cũ** (thất bại) và toàn bộ test mới trên code mới (pass), chép nguyên văn.
3. `uv run pytest tests/test_engine_main.py tests/test_null_strategy.py tests/test_engine_logic.py tests/test_silent_engine_guard.py tests/test_heartbeat_check.py -q`.
4. `uv run pytest -m "not integration" -q`: tổng pass/fail. `uv run ruff check trading tests scripts`.
5. `git -C <worktree> log --oneline main..dot229` và `diff --stat main..dot229`.
6. Mọi chỗ brief mơ hồ mà Builder phải tự diễn giải.
