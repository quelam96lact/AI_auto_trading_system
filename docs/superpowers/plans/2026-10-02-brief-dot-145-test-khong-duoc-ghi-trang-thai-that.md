# Brief đợt 145 — test không bao giờ được ghi vào file trạng thái THẬT

**Hạn chót: trước 08:00 thứ Hai 05/10/2026**, lúc heartbeat chạy thật lần đầu với code đợt 142.

## Vì sao — Claude tái hiện khi audit đợt 142

`scripts/heartbeat_check.py::main` (từ đợt 142) đọc log thật trong `logs/` và **ghi** trạng thái vào
`DEFAULT_SCHEDULE_STATE_FILE` = `logs/.schedule_health_state.json` của repo chính. Các test cũ trong
`tests/test_heartbeat_check.py` gọi `main([])`, nên **mỗi lần chạy pytest trong repo chính lại ghi đè
file trạng thái thật** bằng dữ kiện giả:

```
"container-health": {"status": "stale", "last_called": null, "checked_at": "2026-08-14 10:00:00"}  (cả 5 job)
```

Tái hiện của Claude (dời file đi rồi chạy từng file test):

```
tests/test_schedule_watch.py         -> file trang thai that ton tai sau test: False
tests/test_heartbeat_check.py        -> file trang thai that ton tai sau test: True
tests/test_container_health_check.py -> file trang thai that ton tai sau test: False
```

Hậu quả: heartbeat thật gửi 5 tin "ĐÃ CHẠY LẠI" oan. Nặng hơn, nếu một job **thật sự** chết, nó thấy
trạng thái trước là `stale`, coi như "đã báo", và **im lặng**.

Claude đã xoá file bẩn. Nó sẽ quay lại ở lần chạy pytest kế tiếp trong repo chính.

## Giới hạn

- **KHÔNG commit, KHÔNG push**, không restart container, không sửa task, không gửi Telegram thật.
- Lịch chạy thẳng từ cây làm việc. Heartbeat chạy 08:00–15:00 ngày giao dịch, nên **chỉ chép vào repo
  chính ngoài khung đó**, hoặc làm trong worktree như đợt 142. Hôm nay là thứ Sáu chiều; cuối tuần
  heartbeat không chạy.
- Chỉ sửa: `scripts/heartbeat_check.py` (chỉ chỗ chọn đường dẫn state/log), `tests/test_heartbeat_check.py`,
  `tests/test_schedule_watch.py`, và `tests/conftest.py` (Việc 2). Không đổi logic phán xử.
- Không chạy hai bộ test đầy đủ cùng lúc với agent khác (đợt 144 có thể đang chạy): kiểm
  `Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'pytest' }` rỗng trước khi
  chạy `uv run pytest -q`.
- **Trong lúc làm, đừng chạy `tests/test_heartbeat_check.py` trong repo chính trước khi đã sửa**; nó sẽ
  ghi lại file bẩn. Nếu lỡ thì xoá `logs/.schedule_health_state.json` và nói rõ trong báo cáo.
- GitNexus: `impact` trước khi sửa symbol, `detect_changes` sau khi sửa.

## Việc

1. **Đường dẫn tiêm được:** `main` nhận được đường dẫn file trạng thái lịch và thư mục log (qua tham số
   của `main` hoặc cờ dòng lệnh, chọn một, nói rõ vì sao). Mặc định giữ nguyên cho cron. Mọi test gọi
   `main` phải truyền thư mục tạm (`tmp_path`). Không test nào được đọc `logs/` thật.
2. **Lưới an toàn cho cả bộ test, không riêng file này:** một fixture `autouse` cấp phiên trong
   `tests/conftest.py`. Nó ghi lại trạng thái (tồn tại? mtime? nội dung băm?) của **mọi** file
   `logs/.*state*.json` trong repo **trước** phiên test, so lại **sau** phiên, và làm phiên **đỏ** nếu có
   file nào bị tạo hoặc sửa, nêu tên file. Dự án có ít nhất ba file kiểu này
   (`.container_health_state.json`, `.schedule_health_state.json`, và file của bản ghi sổ lệnh nếu
   có — tự tìm, liệt kê trong báo cáo). Lưu ý: cron có thể ghi `.container_health_state.json` thật
   **trong lúc** test đang chạy (container-health chạy mỗi 10 phút, 24/7). Xử lý cho đúng, đừng để
   lưới an toàn đỏ oan vì cron. Ví dụ: chỉ xét file mà một test có thể chạm tới, hoặc so nội dung với
   dấu hiệu của test (ngày giả). Nói rõ chọn cách nào và vì sao.

## Tiêu chí hoàn thành

1. Tái hiện trước khi sửa: dời `logs/.schedule_health_state.json` (nếu có), chạy
   `tests/test_heartbeat_check.py` → file xuất hiện (dán bằng chứng), rồi xoá. **Sau khi sửa**: chạy lại
   y hệt → file **không** xuất hiện.
2. Lưới an toàn hoạt động: **phá thử** bằng cách cho một test ghi `logs/.schedule_health_state.json` thật
   → phiên pytest đỏ, nêu đúng tên file. Khôi phục, đối chiếu hash.
3. Lưới an toàn không đỏ oan: chạy `uv run pytest -q` đầy đủ **hai lần liên tiếp** trong repo chính lúc
   container-health đang chạy theo lịch (có ít nhất một mốc 10 phút rơi vào giữa) → cả hai xanh. Dán
   giờ bắt đầu/kết thúc và dòng log container-health rơi vào khoảng đó.
4. `scripts/sched.sh heartbeat --dry-run` sau khi sửa: **không** có dòng "ĐÃ CHẠY LẠI" nào (vì không còn
   trạng thái bẩn), không gửi Telegram. Dán log.
5. Cuối cùng: `logs/.schedule_health_state.json` không tồn tại, hoặc nếu tồn tại thì dán nội dung để
   chứng minh không phải dữ kiện của test.
6. `ruff` sạch; `uv run pytest -q` ≥ **1.729 passed** cộng số test mới.

## Báo cáo

`docs/superpowers/research/2026-10-02-dot-145-test-khong-ghi-trang-thai-that.md`: số đo nguyên văn,
giờ chép vào repo chính, brief sai ở đâu, cái gì không kiểm được.
