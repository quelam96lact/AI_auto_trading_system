# Plan 2026-08-10 — Mục B (điều tra flake) + C3/C4 (dọn dẹp)

Ba việc ĐỘC LẬP nhau. Làm theo thứ tự C3 → C4 → B1 (B1 để cuối vì nó có thể
không ra kết quả, và không được để nó chặn hai việc kia).

**KHÔNG commit, KHÔNG push.** Claude audit rồi mới commit.

---

## C3 — `scripts/load_token_to_db.py` (việc rõ ràng nhất, làm trước)

### Vấn đề 1 — đòi 6 biến env không dùng đến

`load_config()` (`trading/config.py:40-49`) đọc `os.environ["SSI_CONSUMER_ID"]`,
`SSI_CONSUMER_SECRET`, `SSI_API_KEY`, `SSI_API_SECRET`, `SSI_PRIVATE_KEY` —
`KeyError` nếu thiếu. Nhưng `load_token_to_db.py` chỉ dùng **`cfg.db_dsn`**, mà
`db_dsn` cũng lấy từ `os.environ["DB_DSN"]` (`config.py:40`) chứ KHÔNG từ file
YAML. Nghĩa là tham số `--config` không đóng góp gì cho script này.

**Sửa:** bỏ `load_config` và `--config`, đọc thẳng `os.environ["DB_DSN"]`. Thiếu
biến thì in thông báo nói rõ tên biến và thoát mã 1 — KHÔNG để `KeyError` trần.

**KHÔNG đụng `trading/config.py`.** Nó là code sản xuất, collector và engine
đều gọi `load_config` và chúng *cần* đủ 6 biến. Sửa ở đó là sai chỗ.

### Vấn đề 2 — `print()` tiếng Việt làm crash SAU KHI đã ghi DB xong

Dòng 45-46 in tiếng Việt có dấu → `UnicodeEncodeError` trên Windows cp1252.
Crash xảy ra *sau* `save_ssi_token()`, nên DB đã ghi thành công nhưng người dùng
thấy traceback và tưởng thất bại. Runbook đang né bằng `PYTHONIOENCODING=utf-8`.

**Sửa:** bỏ dấu tiếng Việt trong mọi `print()` của file này (cùng lý do
`RUNBOOK_OTP_AUTH.txt` đã viết không dấu). Không đổi sang tiếng Anh, chỉ bỏ dấu.

### Vấn đề 3 — RÒ MẬT KHẨU: dòng 45 in cả DSN

```python
print(f"Đã nạp token vào ssi_auth_state (DB: {cfg.db_dsn}).")
```

`db_dsn` có dạng `postgresql://user:password@host:5432/db` — dòng này in mật
khẩu Postgres ra console, và console thường bị copy vào chat/issue/log.

**Sửa:** không in DSN. In host/database thôi, hoặc bỏ hẳn phần trong ngoặc.
Dòng 46 (`refresh_token_expires_at`) GIỮ NGUYÊN nội dung — runbook nói rõ chỉ
được báo cáo trường `expires_at`/`refresh_token_expires_at`, đó là mốc an toàn.

### Kiểm chứng C3 — cả 3 phải paste output

1. **Chỉ có `DB_DSN`, không có biến `SSI_*` nào** → script chạy XONG, không
   `KeyError`. Chạy trong shell sạch, ví dụ (Git Bash):
   `env -u SSI_CONSUMER_ID -u SSI_CONSUMER_SECRET -u SSI_API_KEY -u SSI_API_SECRET -u SSI_PRIVATE_KEY DB_DSN='postgresql://trading:trading@127.0.0.1:5432/trading' uv run python scripts/load_token_to_db.py`
2. **Không có `DB_DSN`** → thông báo nói rõ thiếu biến `DB_DSN`, exit code 1,
   KHÔNG traceback. Paste cả `echo $?`.
3. **KHÔNG đặt `PYTHONIOENCODING`** → chạy hết, không `UnicodeEncodeError`.
   Đây là điểm chính; nếu vẫn crash là chưa xong.
4. Grep xác nhận không còn in DSN: `grep -n "db_dsn\|DB_DSN" scripts/load_token_to_db.py`
   — paste, và không dòng `print` nào chứa DSN đầy đủ.

**Nếu `scripts/.ssi_sdk_token.json` không tồn tại trên máy bạn:** script sẽ dừng
ở nhánh "chưa có token" trước khi tới phần DB. Vẫn kiểm chứng được mục 2 và 3,
còn mục 1 thì BÁO LẠI là không kiểm chứng được thay vì giả vờ đã chạy.
**TUYỆT ĐỐI KHÔNG mở, không in, không paste nội dung file token đó.**

### Cập nhật `RUNBOOK_OTP_AUTH.txt`

Bước dùng `load_token_to_db.py` đang ghi `--config config/config.yaml` và dặn
đặt `PYTHONIOENCODING`. Sau khi sửa thì cả hai không cần nữa cho bước này. Sửa
đúng bước đó, KHÔNG viết lại runbook. Giữ nguyên quy ước không dấu của file.

---

## C4 — `.gitignore` (CHỈ THÊM DÒNG, CẤM XÓA FILE)

`git status` đang có 15 mục `??`. `.gitignore` hiện liệt kê từng file spike
`.json` một; chưa có mẫu nào che `.py`.

**Thêm mẫu cho:** `scripts/.spike_*.py`, `scripts/.repro_*.py`, `.gitnexus_rpc.py`,
`.1devtool/`, `.claude/worktrees/`.

**KHÔNG đụng tới:**
- `docs/superpowers/plans/*.md` — kế hoạch, sẽ commit thật.
- File `.md` tên tiếng Việt ở gốc repo — tài liệu của chủ dự án. BÁO CÁO nó,
  đừng ignore, đừng xóa.
- Các dòng `.json` đã có sẵn — để yên, đừng "tiện thể" gộp thành wildcard.

**CẤM `git rm`, `rm`, `git clean`.** Việc này chỉ thêm dòng vào `.gitignore`.

### Kiểm chứng C4
`git status --short` — paste TRƯỚC và SAU. Sau khi sửa, danh sách `??` chỉ còn
lại: các file trong `docs/superpowers/plans/` và file `.md` tiếng Việt ở gốc.

---

## B1 — Điều tra: tại sao `purge_stream` thỉnh thoảng không ăn

**Đây là ĐIỀU TRA, không phải sửa code. KHÔNG sửa bất kỳ file nào ở bước này.**
Kết quả "KHÔNG TÌM RA" là kết quả hợp lệ và được chấp nhận. Kết quả bịa ra thì
không.

Nền: commit `d62384d` làm fixture báo lỗi ngay khi purge không ăn, nhưng chưa
biết *vì sao* nó không ăn. Đọc `docs/superpowers/plans/2026-08-10-nats-test-isolation-flake.md`
để nắm bối cảnh.

### Hai điều ĐÃ loại trừ — đừng điều tra lại

- **Message tới sau purge do publisher chậm:** `BarPublisher.publish()` (
  `trading/bus/publisher.py:45`) `await js.publish(...)`, tức đã chờ PubAck. Đã
  loại.
- **`test_collector_main.py` làm bẩn stream:** nó dùng publisher giả, không nối
  NATS thật. Đã loại.

### Việc cần làm — theo thứ tự, dừng ngay khi có bằng chứng

1. **Liệt kê ĐẦY ĐỦ mọi test publish vào NATS thật.** Không đoán — grep cả
   `tests/` tìm chỗ tạo `BarPublisher`, gọi `nats.connect`, hay `js.publish`.
   Paste danh sách kèm file:dòng. Nếu có file nào ngoài `test_engine_main.py`
   thì đó là ứng viên số một, BÁO NGAY, đừng tự sửa.
2. **Kiểm tra một giả thuyết cụ thể, kiểm chứng được:** `purge_stream` có bao
   giờ trả về OK trong khi `stream_info` vẫn còn message không? Viết script
   dùng-một-lần (đặt ở scratchpad hoặc `scripts/.probe_*.py`, có dấu chấm đầu
   tên nên pytest không thu gom): publish N message → purge → đọc
   `stream_info().state.messages` ngay lập tức, lặp vài trăm vòng, đếm số lần
   khác 0. Paste con số thật.
   - Nếu **luôn = 0**: giả thuyết này SAI, ghi rõ như vậy và đi tiếp bước 3.
   - Nếu **thỉnh thoảng ≠ 0**: đã tìm ra. BÁO NGAY, dừng lại, đừng sửa gì.
3. **Nếu bước 1 và 2 đều không ra:** dừng. Viết báo cáo nói rõ đã loại trừ được
   những gì và còn lại giả thuyết nào chưa kiểm chứng được. KHÔNG đoán bừa.

### Kiểm chứng B1
Báo cáo phải phân biệt rạch ròi hai loại câu: "tôi đo được X" (kèm số) và "tôi
nghĩ có thể là Y" (nói rõ là phỏng đoán chưa kiểm chứng). Trộn hai loại này là
lỗi nặng hơn cả việc không tìm ra nguyên nhân.

Xoá script dò tìm sau khi xong, hoặc để tên bắt đầu bằng dấu chấm. Không commit.

---

## Phạm vi phẫu thuật — toàn bộ nhiệm vụ

**Được sửa:** `scripts/load_token_to_db.py`, `RUNBOOK_OTP_AUTH.txt`, `.gitignore`.

**CẤM đụng:** `trading/config.py`, `trading/bus/publisher.py`,
`trading/engine/main.py`, `trading/storage/db.py`, `tests/test_engine_main.py`
(vừa commit `d62384d`), `AGENTS.md`, `CLAUDE.md`, và mọi file khác trong
`trading/`.

**CẤM:** `ruff check --fix`, `git commit`, `git push`, `git rm`, `git clean`,
`rm` bất kỳ file nào của dự án.

**Bắt buộc trước khi sửa symbol nào:** chạy `gitnexus_impact` và báo blast radius.

## Dừng lại và hỏi nếu

- C3: sửa xong mà bỏ `load_config` lại làm hỏng thứ gì khác.
- C4: có file `??` bạn không chắc thuộc loại nào.
- B1: bước 1 tìm ra file test khác publish vào NATS thật — báo, đừng sửa.
