# Prompt thực thi: SSI SDK Migration — Phase 0 (phần còn lại) + Phase 1

**Dùng prompt này để giao việc cho 1 agent coding khác (hoặc phiên Claude Code khác).**
**Đọc trước:** `PLAN_SSI_SDK_MIGRATION.md` (kế hoạch đầy đủ, đã audit) — prompt này chỉ giao đúng phần Phase 0 (còn lại) + Phase 1, KHÔNG phải toàn bộ plan.

---

## ⚠️ Giới hạn phạm vi — đọc kỹ trước khi bắt đầu

**CHỈ làm 4 task dưới đây (Task A-D). KHÔNG làm Phase 2/3/4/5** (viết lại `backfill.py`/`feed.py`/`parser.py`/`main.py`) — những phần đó cần dữ liệu mẫu thật (field format `trading_date`, `IntervalMessage`) mà dự án chưa ghi được (đang chờ user chạy script xác thực OTP thật). Nếu bạn thấy có thể "tiện thể" sửa luôn `backfill.py`/`feed.py`/`parser.py` — **đừng làm**, báo cáo lại thay vì tự ý mở rộng phạm vi.

**Trước khi sửa bất kỳ symbol nào** (vd `Config`, `Storage.init_schema`, `load_config`): chạy `gitnexus_impact({target: "<tên symbol>", direction: "upstream"})`, báo cáo blast radius (ai gọi, process nào bị ảnh hưởng, mức rủi ro) trước khi sửa. Nếu risk HIGH/CRITICAL, dừng lại và hỏi lại thay vì tự quyết.

**Sau khi xong tất cả task:** chạy `gitnexus_detect_changes()` để xác nhận thay đổi chỉ ảnh hưởng đúng scope mong đợi.

**KHÔNG tự commit, không tự push.** Báo cáo lại kết quả (diff, test output) để Claude (planner) audit rồi mới commit.

---

## Bối cảnh ngắn gọn

Dự án đang migrate từ SDK cũ `ssi_fc_data` sang SDK mới `ssi-sdk` (SSI FastConnect → SSI Developer Portal). Đã xác nhận qua đọc source code thật (không phải đoán):
- Auth: `api_key` + `api_secret` (KHÔNG cần `client_id`/`private_key` — 2 giá trị đó chỉ dùng cho Trading API, ngoài scope dự án hiện tại vì broker là `PaperBroker`).
- OTP chỉ cần **1 lần** để lấy `refresh_token`; sau đó `refresh()` không cần OTP (miễn `refresh_token` còn hạn).
- Script `scripts/spike_ssi_sdk_auth.py` đã viết + smoke-test xong (không cần sửa).

---

## Task A — Viết script lấy sample OHLC + streaming thật

**File tạo mới:** `scripts/spike_ssi_sdk_ohlc.py` (script tạm, KHÔNG phải production code — style giống `scripts/record_fixtures.py` và `scripts/spike_ssi_sdk_auth.py` đã có: docstring hướng dẫn ở đầu, hàm đơn giản, không argparse phức tạp).

**Mục tiêu:** Script này, khi user chạy với token thật đã lưu ở `scripts/.ssi_sdk_token.json` (từ `spike_ssi_sdk_auth.py`), phải:
1. Gọi `AsyncData.market_data.get_ohlc_5minute_historical(symbol, from_date, to_date)` cho 1 symbol (dùng `VCB`, khớp `config/config.yaml`), in/lưu raw `OHLCData` ra `scripts/.spike_ohlc_sample.json` — mục đích: xác nhận format thật của field `trading_date`.
2. Subscribe `AsyncStream.streaming.subscribe_symbol_ohlcv(["VCB"], Timeframe.MINUTE_5)`, lắng nghe trong khoảng thời gian truyền qua CLI (mặc định 120 giây), in/lưu mỗi `IntervalMessage` nhận được ra `scripts/.spike_stream_sample.jsonl` (mỗi dòng 1 JSON, dùng `dataclasses.asdict()` hoặc tương đương).
3. Đọc token đã lưu bằng cách tái sử dụng logic đọc file trong `spike_ssi_sdk_auth.py` (không cần OTP lại — nếu chưa có token/hết hạn, in lỗi rõ ràng yêu cầu chạy `spike_ssi_sdk_auth.py` trước).

**Kiểm chứng (không cần OTP/mạng thật — giống cách `spike_ssi_sdk_auth.py` đã được verify):**
```bash
uv run --with ssi-sdk python -c "
import ast
src = open('scripts/spike_ssi_sdk_ohlc.py', encoding='utf-8').read()
ast.parse(src)
print('OK: syntax hop le')
from ssi_sdk import AsyncAuth, AsyncData, AsyncStream, Config
from ssi_sdk.enums import Timeframe
print('OK: import cac symbol script dung deu ton tai')
"
```
Task A coi là xong khi lệnh trên chạy không lỗi (không cần chạy full script với credentials thật — đó là việc của user).

**Cập nhật `.gitignore`:** thêm `scripts/.spike_ohlc_sample.json` và `scripts/.spike_stream_sample.jsonl` (dữ liệu thị trường công khai nhưng đây là output tạm, không phải fixture chính thức — fixture chính thức sẽ ghi lại có kiểm soát ở Phase 2/3 sau).

---

## Task B — Thêm `ssi-sdk` làm dependency song song

**File sửa:** `pyproject.toml` — thêm `"ssi-sdk"` vào mảng `dependencies`, **giữ nguyên** `"ssi-fc-data"` (chưa gỡ, đợi Phase 5 sau khi Phase 4 E2E ổn định).

**Kiểm chứng:** `uv sync` chạy thành công, `uv run python -c "import ssi_sdk; import ssi_fc_data"` không lỗi (cả 2 package cùng cài được, không conflict).

---

## Task C — Thêm credentials mới vào `Config`

**File sửa:** `trading/config.py`

1. Thêm 2 field vào `Config` dataclass: `ssi_api_key: str`, `ssi_api_secret: str`.
2. Trong `load_config()`, đọc từ env: `ssi_api_key=os.environ["SSI_API_KEY"]`, `ssi_api_secret=os.environ["SSI_API_SECRET"]`.
3. **KHÔNG xoá** `ssi_consumer_id`/`ssi_consumer_secret` (vẫn cần cho `ssi_fc_data` tới Phase 5).
4. Cập nhật `docker-compose.yml` — trong service `collector`, thêm vào `environment:`:
   ```yaml
   SSI_API_KEY: ${SSI_API_KEY}
   SSI_API_SECRET: ${SSI_API_SECRET}
   ```
   (giữ nguyên `SSI_CONSUMER_ID`/`SSI_CONSUMER_SECRET` đã có).

**Kiểm chứng:** Thêm test vào `tests/test_config.py` cho 2 field mới (theo pattern test hiện có trong file — đọc file trước để khớp style, vd cách test hiện tại set env var giả rồi gọi `load_config()`). Chạy `uv run pytest tests/test_config.py -v` — pass, không phá test cũ nào trong file.

---

## Task D — Bảng lưu `refresh_token` bền vững

**Files sửa:** `trading/storage/schema.sql`, `trading/storage/db.py`
**File tạo mới:** `trading/collector/ssi_auth.py`

### D.1 — Schema
Đọc `trading/storage/schema.sql` trước để khớp style (tên cột, convention `IF NOT EXISTS` đang dùng). Thêm bảng mới, gợi ý tên `ssi_auth_state`:
```sql
CREATE TABLE IF NOT EXISTS ssi_auth_state (
    id INT PRIMARY KEY DEFAULT 1,
    access_token TEXT NOT NULL,
    expires_at BIGINT NOT NULL,
    refresh_token TEXT NOT NULL,
    refresh_token_expires_at BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (id = 1)
);
```
(1 dòng duy nhất, `id=1` cố định — collector chỉ có 1 phiên đăng nhập tại 1 thời điểm; `CHECK (id = 1)` ngăn insert thêm dòng thứ 2). Nếu style file hiện tại khác cách này (vd không dùng `CHECK`), ưu tiên khớp style có sẵn hơn đề xuất trên.

### D.2 — `Storage` methods
Thêm 2 method vào `trading/storage/db.py` theo đúng pattern các method hiện có (dùng `self.conn()`, `psycopg`):
- `save_ssi_token(access_token: str, expires_at: int, refresh_token: str, refresh_token_expires_at: int) -> None` — upsert vào `ssi_auth_state` (dùng `ON CONFLICT (id) DO UPDATE`).
- `load_ssi_token() -> dict | None` — đọc dòng `id=1`, trả `None` nếu chưa có.

### D.3 — Module bootstrap auth
Tạo `trading/collector/ssi_auth.py`:
```python
async def ensure_authenticated(cfg: Config, storage: Storage):
    """Trả về AsyncAuth đã có access_token hợp lệ.

    Đọc refresh_token đã lưu trong DB → nếu còn hạn, refresh() (không cần OTP).
    Nếu chưa có / refresh_token đã hết hạn → raise lỗi rõ ràng, yêu cầu người
    vận hành chạy `scripts/spike_ssi_sdk_auth.py` thủ công để lấy OTP mới rồi
    nạp lại vào DB. KHÔNG tự động xin/nhập OTP trong hàm này.
    """
```
- Đọc `storage.load_ssi_token()`. Nếu có và `refresh_token_expires_at` còn hạn (so với `time.time()`): tạo `AsyncAuth(Config(api_key=cfg.ssi_api_key, api_secret=cfg.ssi_api_secret))`, `set_token(Token.from_dict(...))`, gọi `token_manager.refresh()`, lưu token mới lại vào `storage.save_ssi_token(...)`, return `auth`.
- Nếu không có / hết hạn: `raise RuntimeError("SSI refresh_token missing/expired — run scripts/spike_ssi_sdk_auth.py manually to re-authenticate with OTP, then re-run collector")`.

**Kiểm chứng:** Viết test mới `tests/test_ssi_auth.py` (hoặc thêm vào file test collector liên quan nếu có sẵn — kiểm tra `tests/` trước khi tạo file mới, tránh trùng lặp). Test dùng fake/mock `AsyncAuth`/`token_manager` (không gọi mạng thật) cho 2 case: (1) có refresh_token còn hạn → gọi `refresh()` thành công, lưu lại token mới; (2) không có token đã lưu → raise `RuntimeError` đúng message. Chạy `uv run pytest tests/test_ssi_auth.py -v` — pass.

**Không sửa `trading/collector/main.py`** trong task này — việc wire `ensure_authenticated()` vào `main.py` thuộc Phase 3 (khi `feed.py`/`backfill.py` cũng được viết lại cùng lúc), làm riêng bây giờ sẽ để lại code chết không ai gọi.

---

## Sau khi hoàn thành cả 4 task

1. Chạy toàn bộ test suite: `uv run pytest -m "not integration" -v` — phải thấy **tất cả test cũ (51+) vẫn pass**, cộng thêm test mới của Task C/D.
2. Chạy `uv run ruff check trading tests scripts` — sửa nếu có lỗi lint mới phát sinh từ code bạn viết (không sửa lint warning có sẵn từ trước, ngoài phạm vi).
3. Chạy `gitnexus_detect_changes()` — dán kết quả vào báo cáo.
4. Báo cáo lại: danh sách file đã sửa/tạo, kết quả test, kết quả `gitnexus_detect_changes()`. **Không commit, không push.**
