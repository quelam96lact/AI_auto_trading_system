# Brief đợt 213: chuẩn hoá `localhost` thành `127.0.0.1` trong `load_config`

Ngày 08/11/2026. Người giao: Claude (Lead). Người làm: **Builder**.

Nguồn: dòng 1 trong `docs/audit/2026-11-08-ra-soat-refactor.md` (commit 7e3e317).

## Vấn đề

- Trên máy Windows này, `localhost` phân giải ra IPv6 trước. Mỗi lần kết nối DB qua `localhost` có thể treo khoảng 130 giây.
- Hiện nay hơn 10 script tự gọi `.replace("localhost", "127.0.0.1")`.
- Script nào quên gọi thì bị treo.

## Lời giải đã chốt (Lead quyết)

- **Một hàm thuần** `normalize_loopback(url: str) -> str` đặt trong `trading/config.py`.
- **Chỉ gọi hàm đó ở một chỗ** là `load_config`, cho hai trường `db_dsn` và `nats_url`.

## Không làm, và lý do

- **Không sửa `Storage.__init__` và `_get_pool`** trong `trading/storage/db.py`.
  - `_get_pool` có impact CRITICAL và nằm trên đường đặt lệnh thật.
  - DSN đi qua `load_config` thì đã được chuẩn hoá.
  - `scripts/_db_common.resolve_dsn` đã tự chuẩn hoá từ trước.
- **Không xoá các lệnh `.replace(...)` có sẵn trong `scripts/`.**
  - Sau đợt này chúng chỉ còn là thao tác thừa vô hại.
  - Nhiều file trong số đó là script đo hoặc probe đã công bố kết quả, nên giữ nguyên.
- **Không đổi `config.yaml`, `.env`, `.env.example` hay `docker-compose.yml`.**

## Cảnh báo rủi ro (đã ghi nhận)

- `impact` của `load_config` và `Config` ra **CRITICAL** (khoảng 65 symbol). Mọi service đều đi qua đây: engine, collector, scheduler, kể cả đường đặt lệnh thật.
- Lead chấp nhận rủi ro này vì ba điều kiện sau:
  - Thay đổi chỉ chạm tới **host** của URL, và chỉ khi host đúng bằng chuỗi `localhost`. Mọi giá trị khác phải giữ nguyên **từng ký tự**.
  - Trong container, DSN dùng `@postgres` và NATS dùng host `nats`, nên giá trị không đổi. Builder phải chứng minh điều này bằng test và bằng cách đọc `docker-compose.yml`.
  - Lead sẽ tự kiểm sau khi deploy.
- Nếu `impact` còn chỉ ra caller nào khác `load_config` gọi trực tiếp tới `normalize_loopback` thì **dừng lại và báo Lead**. Hàm này mới, nên lẽ ra không có caller nào khác.

## Quy tắc chung

- **Trước khi sửa `load_config`:** chạy `node .gitnexus/run.cjs impact "load_config" --direction upstream --repo .` (không dùng `npx`).
  - Index cũ thì chạy `node .gitnexus/run.cjs analyze --index-only` trước.
  - Ghi số caller và mức risk vào báo cáo.
- **Sau khi sửa:** chạy `node .gitnexus/run.cjs detect-changes --scope all --repo .`.
- Chỉ được sửa `trading/config.py`, `tests/test_config.py`, và nếu thật cần thì thêm một file test mới. Không đụng file nào khác.
- Không commit, không push. Không chạy `sched.sh`, không chạy script thật, không gọi DB hay API thật.

## Các bước

### 1. Viết test trước

Viết test trong `tests/test_config.py` và chạy để thấy test **đỏ**, vì hàm chưa tồn tại. Test cho `normalize_loopback` cần có ít nhất các trường hợp sau.

| Đầu vào | Kết quả mong đợi |
|---|---|
| `postgresql://trading:trading@localhost:5432/trading` | `postgresql://trading:trading@127.0.0.1:5432/trading` |
| `postgresql://trading:trading@postgres:5432/trading` | không đổi |
| `nats://localhost:4222` | `nats://127.0.0.1:4222` |
| `nats://nats:4222` | không đổi |
| `postgresql://u:localhost@db:5432/x` (mật khẩu chứa chữ localhost) | không đổi |
| `postgresql://u:p@localhost-db:5432/x` (host chỉ chứa chữ localhost) | không đổi |
| `postgresql://u:p@LOCALHOST:5432/x` | `postgresql://u:p@127.0.0.1:5432/x` |
| `postgresql://u:p@localhost/x` (không có cổng) | `postgresql://u:p@127.0.0.1/x` |
| `host=localhost dbname=x` (dạng key=value, không phải URL) | không đổi |
| `postgresql://u:p@[::1]:5432/x` | không đổi |
| chuỗi rỗng | chuỗi rỗng |

Thêm 2 test cho `load_config`, dùng `monkeypatch.setenv` và file yaml tạm trong `tmp_path` (theo đúng cách các test hiện có trong `tests/test_config.py` đang làm):
- `DB_DSN` và `NATS_URL` dùng `localhost` thì `cfg.db_dsn` và `cfg.nats_url` ra `127.0.0.1`.
- `NATS_URL` không đặt và yaml có `nats://localhost:4222` thì `cfg.nats_url == "nats://127.0.0.1:4222"`.

→ **Kiểm chứng:** chạy `uv run pytest tests/test_config.py -q`. Các test mới phải đỏ, test cũ phải xanh.

### 2. Viết hàm

- Dùng `urllib.parse.urlsplit`.
- Chỉ thay khi URL có scheme **và** `hostname` (đã hạ chữ thường) đúng bằng `"localhost"`.
- Khi thay, chỉ thay phần host trong `netloc`. Giữ nguyên user, mật khẩu, cổng, path và query.
- Mọi trường hợp khác, kể cả khi parse lỗi, trả lại **đúng chuỗi đầu vào**.
- Thêm một dòng docstring nói lý do: "Windows: localhost ra IPv6 trước, mỗi kết nối DB treo ~130s".

→ **Kiểm chứng:** `uv run pytest tests/test_config.py -q` xanh toàn bộ.

### 3. Gọi hàm trong `load_config`

- Chỉ bọc hai biểu thức đang có:
  - `db_dsn=normalize_loopback(os.environ["DB_DSN"])`
  - `nats_url=normalize_loopback(os.environ.get("NATS_URL") or raw["nats"]["url"])`
- Không đổi gì khác trong hàm.

→ **Kiểm chứng:** `git diff trading/config.py` chỉ gồm import, hàm mới, và đúng 2 dòng trong `load_config`.

### 4. Chứng minh giá trị trong container không đổi

- Đọc `docker-compose.yml` và liệt kê, cho từng service engine, collector và scheduler:
  - giá trị `DB_DSN` (đến từ `environment:` hay `env_file`);
  - giá trị `NATS_URL`.
- Ghi rõ host của từng giá trị. **Chỉ ghi host, không chép mật khẩu.**
- Với mỗi giá trị, chỉ ra nó rơi vào dòng nào trong bảng test ở bước 1.
- Nếu có service mà giá trị **sẽ đổi** sau đợt này thì dừng lại và báo Lead.

## Kiểm chứng cuối

- `uv run pytest -m "not integration" -q`: mốc trước refactor là **2283 passed** (ghi lại số thực tế đo trước khi sửa). Sau refactor phải là mốc + số test mới, **0 failed**.
- `uv run ruff check trading tests scripts`: sạch.
- Nội dung `logs/alert_outbox_*` thật không đổi trước và sau khi chạy test.

## Báo cáo cho Lead

- Kết quả `git diff --stat`.
- Kết quả `impact` của `load_config`: số caller và mức risk.
- Kết quả `detect-changes`.
- Bảng ở bước 4: service, biến, host, và giá trị đó có đổi hay không.
- Số test pass trước và sau, và số test mới.
