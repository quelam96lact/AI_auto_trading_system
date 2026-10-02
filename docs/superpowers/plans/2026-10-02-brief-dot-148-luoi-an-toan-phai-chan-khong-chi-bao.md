# Brief đợt 148 — lưới an toàn của test phải CHẶN việc ghi file trạng thái thật, không chỉ báo sau

Việc nhỏ, chỉ sửa `tests/conftest.py`.

## Vì sao — xảy ra thật khi audit đợt 147

Lưới an toàn đợt 145 dùng `sys.addaudithook` để **ghi nhận** mọi lần tiến trình pytest mở-để-ghi, xoá
hay đổi tên một file `logs/.*state*` / `logs/.*last*`, rồi làm phiên đỏ ở cuối. Nó **không chặn**: file
thật vẫn bị ghi.

Khi audit đợt 147, Claude chạy lại phá thử "`main` bỏ qua `--state-file`". Test đỏ đúng như mong muốn,
lưới cũng báo đúng. Nhưng `logs/.engine_consumer_last_check` **thật** đã bị ghi đè bằng dữ liệu của test:

```
{"stream_seq": 100, "last_seq": 100, "ts": 1790958446.85, ...}     <- giá trị thật lúc đó ~28.847
mtime: 23:22:34 (lần phá thử của agent)  ->  23:27:26 (lần phá thử của Claude)
```

Phá thử là việc thường ngày trong mọi lần audit của dự án này. Lưới chỉ báo nghĩa là **mỗi phá thử làm
bẩn trạng thái thật một lần**, và phải có người nhớ dọn. Lần này Claude đã xoá file bẩn (bản sao giữ
ngoài repo). Lần sau có thể không ai để ý.

## Giới hạn

- **KHÔNG commit, KHÔNG push**, không sửa task, không restart container, không gửi Telegram thật.
- **Chỉ sửa** `tests/conftest.py` (và thêm test cho chính lưới nếu cần, trong một file test riêng). Không
  đụng `scripts/`, `trading/`.
- Lưới chỉ được tác động lên **chính tiến trình pytest**. Cron ghi các file đó từ tiến trình khác, và
  phải tiếp tục ghi bình thường trong lúc test chạy.
- Phát hiện pytest khác đang chạy: `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng trước khi chạy bộ đầy đủ.

## Việc

1. Trong audit hook: khi sự kiện là mở-để-ghi, xoá, hoặc đổi tên **vào** một file trạng thái thật trong
   `logs/` của repo, thì **ném ngoại lệ ngay trong hook**. Audit hook ném thì thao tác bị huỷ trước khi
   chạm đĩa. Thông báo phải nêu tên file, loại thao tác và tên test. Vẫn giữ báo cáo cuối phiên như
   hiện nay.
2. Mở để **đọc** thì vẫn cho phép. Có test cần đọc file thật? Kiểm, và nêu trong báo cáo.
3. Quy tắc nhận diện file giữ nguyên như đợt 145 (`logs/.*state*`, `logs/.*last*`, kể cả `.tmp` đi
   kèm), để không mở rộng phạm vi ngoài ý muốn.

## Tiêu chí hoàn thành

1. **Tái hiện đúng sự cố trên:** làm lại phá thử "`main` truyền `state_file=None`" trong
   `scripts/engine_consumer_check.py`. Ghi lại mtime và nội dung của `logs/.engine_consumer_last_check`
   (hoặc việc nó không tồn tại) **trước** và **sau** khi chạy test. Kỳ vọng: test đỏ, lưới báo, và
   **file thật không đổi** (cùng mtime, cùng nội dung, hoặc vẫn không tồn tại). Khôi phục, đối chiếu
   hash.
2. Đối chứng: tạm vô hiệu bước chặn (chỉ báo như cũ) → cùng phá thử đó làm file thật **bị** ghi. Dán bằng
   chứng, rồi **xoá file bẩn đó** và nói rõ trong báo cáo.
3. Cron không bị ảnh hưởng: chạy `uv run pytest -q` đầy đủ trong khung có ít nhất một lần
   `container-health` chạy theo lịch (mỗi 10 phút). Dán dòng `start`/`EXIT=0` của lần đó, và mtime của
   `logs/.container_health_state.json` cho thấy cron vẫn ghi được.
4. `ruff` sạch; `uv run pytest -q` ≥ **1.748 passed** cộng số test mới.

## Báo cáo

`docs/superpowers/research/2026-10-02-dot-148-luoi-an-toan-chan.md`: số đo nguyên văn, brief sai ở đâu,
cái gì không kiểm được.
