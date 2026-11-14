# Brief đợt 236: giám sát thôi canh engine cũ + canh engine nến ngày

- **Ngày:** 15/11/2026. **Nền:** `docs/audit/2026-11-15-khao-sat-go-engine-cu.md` (đợt 235, Researcher), mục 1–4.
- **Mục tiêu:** sau đợt này, `docker compose stop engine` không gây tin nào, và engine nến ngày (đợt 233) có giám sát thay thế. **Đợt này không dừng, không xoá container, không xoá code engine cũ.** Lead tự rebuild scheduler và dừng engine sau khi audit.
- **Builder** viết code + test, KHÔNG commit/push, KHÔNG docker, KHÔNG `sched.sh`, KHÔNG ghi DB thật (test DB chỉ `trading_test`), không `npx`, không `taskkill` theo tên.

## 1. Phạm vi file

Được sửa: `trading/config.py`, `trading/engine/main.py` (CHỈ dòng định nghĩa `CAPITAL`), `scripts/heartbeat_check.py`, `scripts/container_health_check.py`, `scripts/deploy_drift_check.py`, và test tương ứng (`tests/test_heartbeat_check.py`, `tests/test_container_health_check.py`, `tests/test_deploy_drift_check.py`, thêm test mới nếu cần). Không đụng file khác; thấy cần thì báo.

Trước khi sửa mỗi hằng/hàm: `node .gitnexus/run.cjs impact "<ten>" --direction upstream --repo .` (index có thể cũ: bổ sung grep), dán kết quả.

## 2. Việc

1. **Gỡ bẫy import (làm TRƯỚC mọi việc khác).** Thêm `PAPER_ENGINE_CAPITAL = 100_000_000.0` vào `trading/config.py`. `trading/engine/main.py`: `CAPITAL = PAPER_ENGINE_CAPITAL` (import từ config, giữ tên `CAPITAL` để các chỗ khác không đổi). `scripts/heartbeat_check.py:81`: đổi `from trading.engine.main import CAPITAL` thành import `PAPER_ENGINE_CAPITAL` từ `trading.config` (giữ nghĩa, một nguồn). Sửa chú thích quanh dòng 79–80 cho đúng nguồn mới. **Kiểm chứng:** một test chứng minh `scripts/heartbeat_check.py` import được khi `trading.engine.main` không import được (ví dụ chèn `sys.modules["trading.engine.main"] = None` rồi `importlib.import_module` / `reload`).
2. **Bỏ `engine` khỏi 3 danh sách:** `heartbeat_check.SERVICES` (`:85`), `container_health_check.DEFAULT_SERVICES` (`:69`), `deploy_drift_check.SERVICES` và `SERVICE_WATCH_PATHS` (`:41`, `:45`). Sửa 4 test hỏng mà Researcher đã chỉ (3 trong `test_heartbeat_check.py` ~dòng 27/35/40, `test_deploy_drift_check.py::test_scheduler_in_services`) theo nghĩa mới, không xoá test.
3. **Phép kiểm tuổi sổ engine nến ngày** trong `heartbeat_check.py`, theo khuôn `prev_day_bars_alert` (`:1307`), chạy trong cùng cửa sổ, **tối đa 1 tin/ngày** (cùng cơ chế chống lặp của khuôn đó):
   - `prev = previous_trading_day(hôm nay, holidays)`.
   - `DAILY_ENGINE_GO_LIVE = date(2026, 11, 16)` (lần chạy thật đầu tiên).
   - Không có dòng `paper_daily_state`: CRITICAL chỉ khi `prev >= DAILY_ENGINE_GO_LIVE`; ngược lại im.
   - Có state và `last_processed_date < prev`: CRITICAL nêu `last_processed_date` và `prev`.
   - Bảng `paper_daily_state` chưa tồn tại: coi như không có dòng.
4. **Bất biến sổ mới:** `cash + Σ(qty × cost_per_share của paper_daily_lots) − capital` lệch `realized_pnl` quá 1 đồng → CRITICAL (tối đa 1 tin/ngày). `capital`, `cash`, `realized_pnl` đọc từ `paper_daily_state`. Không có state → bỏ qua. Dùng lại `ledger_deviation` (`:1195`) nếu khớp chữ ký; không sửa hàm đó.

## 3. Test (TDD, đỏ trước)

Phép phá (sao lưu ra ngoài repo rồi sửa; cấm `git checkout/restore/stash`), mỗi phép phải làm đỏ một test gọi đúng hàm sản phẩm:

| # | Phép phá |
|---|---|
| a | Đặt lại `from trading.engine.main import CAPITAL` trong heartbeat_check |
| b | Để `engine` lại trong `heartbeat_check.SERVICES` |
| c | Để `engine` lại trong `container_health_check.DEFAULT_SERVICES` |
| d | Để `engine` lại trong `deploy_drift_check.SERVICES` |
| e | Kiểm tuổi sổ dùng `<=` thay vì `<` (báo cả khi đã xử lý đúng phiên trước) |
| f | Không có state mà `prev < GO_LIVE` vẫn báo |
| g | Không có state mà `prev >= GO_LIVE` không báo |
| h | Bất biến sổ mới bỏ số hạng `realized_pnl` |
| i | Báo hai lần trong cùng ngày |

## 4. Tiêu chí hoàn thành (dán output thật)

1. Impact/grep trước khi sửa.
2. Test mới đỏ trước, xanh sau; bảng phá a–i với dòng `FAILED` nguyên văn.
3. `uv run ruff check trading tests scripts`; `uv run pytest -m "not integration" -q`; các test integration liên quan heartbeat (nếu có) trên DB test.
4. `node .gitnexus/run.cjs detect-changes --scope all --repo .`, `git status --short`, `git diff --stat`.
5. Một câu: "Tôi không chạy docker, không ghi DB thật, không sửa file ngoài §1."
6. Mọi chỗ brief mơ hồ mà Builder phải tự diễn giải.
