# Prompt thực thi: fix `ModuleNotFoundError` khi chạy script trong `scripts/`

**Dùng prompt này để giao việc cho 1 agent coding khác thực thi.**

Task nhỏ, 1 thay đổi chính. Không có plan doc riêng — mọi thứ cần biết nằm hết
trong file này.

---

## Vấn đề

Chạy bất kỳ script nào trong `scripts/` theo đường dẫn file đều hỏng:

```
$ uv run python scripts/confirm_real_order.py 42
ModuleNotFoundError: No module named 'trading'
```

Đây **không phải lỗi cosmetic**: `trading/real_orders.py:66` gửi đúng chuỗi
`uv run python scripts/confirm_real_order.py {order_id}` vào Telegram khi có
lệnh thật chờ xác nhận. Tức là người dùng nhận cảnh báo, gõ đúng lệnh được chỉ,
và lệnh đó không chạy → **luồng xác nhận lệnh thật đang hỏng end-to-end.**

## Nguyên nhân gốc (đã xác minh, không phải suy đoán)

`pyproject.toml` **thiếu section `[build-system]`**. Không có nó, `uv` coi
project là "virtual project" và **không cài** package `trading` vào `.venv`.
Bằng chứng đã chạy thật:

```
$ uv pip list | grep trading      # (rỗng — không có gì)
$ cd /c && .venv/Scripts/python.exe -c "import trading"
ModuleNotFoundError: No module named 'trading'
```

Lâu nay mọi thứ chạy được chỉ vì `cwd` tình cờ là repo root (Python thêm `''`
vào `sys.path`), còn `python scripts/x.py` đặt `sys.path[0] = scripts/` nên
không thấy `trading`. Pytest thì luôn chèn rootdir nên test không bao giờ lộ lỗi.

Đã kiểm chứng cách sửa bằng thí nghiệm cô lập trên project mẫu: thêm
`[build-system]` → `uv sync` cài project (editable) → chạy script theo đường dẫn
file thành công.

---

## ⚠️ Quy tắc bắt buộc

- **KHÔNG tự commit, KHÔNG tự push.** Làm xong, giữ working tree, báo cáo.
- **Chỉ được sửa đúng 2 file:** `pyproject.toml` và `DEPLOYMENT.md`.
- **KHÔNG sửa** `trading/real_orders.py`, `tests/test_real_orders.py`, bất kỳ
  file nào trong `trading/` hay `tests/`, và **không** sửa docstring của các
  script trong `scripts/`. Cách sửa này làm cho các lệnh hiện có chạy được như
  chúng vốn được viết — không có gì để đổi ở đó.
- **KHÔNG chạy `ruff --fix`** trên bất kỳ thư mục nào. Chỉ `ruff check` (đọc).
  Nếu `ruff check scripts` báo lỗi, đó là lỗi có sẵn từ trước — **dán nguyên văn
  output vào báo cáo, KHÔNG sửa.**
- Không cần `gitnexus_impact` (không sửa symbol code nào), nhưng **phải chạy
  `gitnexus_detect_changes()`** ở cuối và dán kết quả.

---

## Các bước

### Bước 1 — Ghi nhận trạng thái hỏng (bằng chứng "trước khi sửa")

Chạy và dán output:

```bash
uv pip list | grep -i trading || echo "(trading KHONG duoc cai)"
uv run python scripts/confirm_real_order.py 42
```

Kỳ vọng: `(trading KHONG duoc cai)` và `ModuleNotFoundError: No module named 'trading'`.

Nếu **không** ra như vậy → DỪNG, báo cáo, đừng sửa gì (môi trường khác với giả
định của task này).

### Bước 2 — Thêm `[build-system]` vào `pyproject.toml`

Thêm vào **cuối** file `pyproject.toml`, giữ nguyên mọi section có sẵn:

```toml

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"
```

Không đổi gì khác trong file đó.

### Bước 3 — Sync lại môi trường

```bash
uv sync --extra dev
uv pip list | grep -i trading
```

Kỳ vọng: `uv pip list` giờ có dòng `trading 0.1.0`.

**Lưu ý:** nếu `uv sync` báo lỗi kiểu `failed to remove file ... pytest.exe:
The process cannot access the file because it is being used by another process`
thì có tiến trình pytest khác đang chạy — đợi nó xong rồi chạy lại, đừng ép.

### Bước 4 — Kiểm chứng lệnh trong cảnh báo Telegram đã chạy được

```bash
uv run python scripts/confirm_real_order.py
```

Kỳ vọng: **argparse usage** (`usage: confirm_real_order.py [-h] ... order_id` +
`error: the following arguments are required: order_id`), **KHÔNG** còn
`ModuleNotFoundError`. Đây là tiêu chí thành công chính của task.

Kiểm thêm 1 script khác để chắc chắn không phải may rủi:

```bash
DB_DSN=postgresql://trading:trading@127.0.0.1:5432/trading uv run python scripts/heartbeat_check.py; echo "exit=$?"
```

Kỳ vọng: không còn `ModuleNotFoundError` (exit 0 hoặc 1 đều hợp lệ tuỳ giờ chạy
và trạng thái DB — script tự thoát sớm ngoài giờ giao dịch VN).

### Bước 5 — Regression

```bash
uv run pytest -m "not integration" -q
uv run ruff check trading tests scripts
```

Kỳ vọng: **177 passed** (không giảm, không tăng). Ruff: 6 file của đợt P0 sạch;
`scripts/` có thể còn 4 lỗi có sẵn từ trước — dán nguyên văn, **không sửa**.

### Bước 6 — Xác nhận Docker build không vỡ

`Dockerfile` dùng `pip install .`. Trước đây nó chạy nhờ setuptools fallback
ngầm; giờ `[build-system]` khai báo tường minh. Phải chứng minh build vẫn OK:

```bash
docker compose build engine
```

Kỳ vọng: build thành công. Dán 10 dòng cuối output.

Nếu Docker không chạy được trên máy bạn → nói thẳng là chưa kiểm chứng được
bước này, đừng bỏ qua im lặng.

### Bước 7 — Gỡ workaround trong `DEPLOYMENT.md`

Mục §9 hiện đang dùng dạng `-m` như một cách đi vòng. Sau khi sửa gốc, nó không
còn cần thiết nữa. Trong `DEPLOYMENT.md` §9:

1. Đổi trong dòng cron: `uv run python -m scripts.heartbeat_check` →
   `uv run python scripts/heartbeat_check.py`
2. **Xoá hẳn** đoạn giải thích ngay dưới khối cron, bắt đầu bằng
   "Phải dùng dạng `python -m scripts.heartbeat_check`, **không** phải..." cho
   đến hết câu "...`ModuleNotFoundError: No module named 'trading'`."
3. Giữ nguyên mọi phần còn lại của §9 (câu về `trading:trading`, ngưỡng
   `HEARTBEAT_MAX_AGE_SECONDS`, đoạn kiểm chứng `docker compose stop engine`).

Sau khi sửa, chạy lại đúng lệnh trong dòng cron để chứng minh nó thật sự chạy:

```bash
DB_DSN=postgresql://trading:trading@127.0.0.1:5432/trading uv run python scripts/heartbeat_check.py; echo "exit=$?"
```

---

## Tại sao không có unit test mới

Lỗi này thuộc về **cách môi trường được cài**, không phải logic trong code. Một
test kiểu "import `trading` từ cwd khác" sẽ phụ thuộc môi trường và dễ flaky,
lại không bảo vệ được điều thật sự quan trọng. Tiêu chí kiểm chứng ở đây là
output cụ thể của Bước 1 (trước) so với Bước 4 (sau) — rõ ràng và lặp lại được.
**Đừng tự thêm test cho phần này.**

---

## Tiêu chí hoàn thành

1. Bước 1 có bằng chứng lỗi TRƯỚC khi sửa.
2. `uv pip list` hiện `trading 0.1.0` sau `uv sync`.
3. `uv run python scripts/confirm_real_order.py` ra argparse usage, hết
   `ModuleNotFoundError`.
4. `uv run pytest -m "not integration" -q` → **177 passed**.
5. `docker compose build engine` thành công (hoặc nói rõ không kiểm chứng được).
6. `DEPLOYMENT.md` §9 đã gỡ workaround `-m` và lệnh trong đó chạy thật.
7. `git status --short` chỉ hiện thêm `pyproject.toml` và `DEPLOYMENT.md` so với
   trước khi bạn bắt đầu (ngoài các file vốn đã modified/untracked từ trước:
   `AGENTS.md`, `CLAUDE.md`, `trading/collector/main.py`, `trading/engine/main.py`,
   `tests/test_engine_main.py`, và nhóm untracked `.1devtool/`, `scripts/.spike_*`,
   v.v. — **không được đụng vào chúng**).
8. Không có commit/push nào do bạn tạo.

## Báo cáo lại (đủ, không tóm tắt)

1. Output Bước 1 (bằng chứng lỗi trước khi sửa).
2. Diff `pyproject.toml`.
3. Output Bước 3 (`uv sync` + `uv pip list | grep trading`).
4. Output Bước 4 (cả 2 lệnh).
5. Output Bước 5 (pytest + ruff — ruff dán nguyên văn kể cả khi có lỗi).
6. Output Bước 6 (docker build) hoặc lý do không chạy được.
7. Diff `DEPLOYMENT.md` + output lệnh cron chạy thật ở Bước 7.
8. `git status --short` và `gitnexus_detect_changes()`.
9. Phát hiện ngoài phạm vi (nếu có) — báo cáo, không sửa.

**Không tự commit, không tự push.** Chờ Claude audit.
