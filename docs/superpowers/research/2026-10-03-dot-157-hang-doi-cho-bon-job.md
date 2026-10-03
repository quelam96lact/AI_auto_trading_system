# Đợt 157 — hàng đợi gửi lại cho bốn job mất tin lâu nhất

Job: `daily-check`, `backup-check`, `disk-check`, `restore-drill`. Không commit, không push.

## Đã làm
- Mỗi script thêm `--logs-dir` (mặc định suy từ vị trí file), hằng `OUTBOX_NAME = alert_outbox_<job>.jsonl`, và thay lời gọi `send_telegram` bằng `send_with_outbox(msg, send=send_telegram, outbox_path=...)`.
- Mã thoát giữ nguyên: ba job đầu xếp hàng → vẫn trả **2**; `daily-check` giữ nguyên `code`. Thêm dòng `[HANG DOI] Tin CHƯA tới người, đã xếp hàng trong ...`.
- `_alert_common.py`, `trading/alerts.py`, `heartbeat_check.py`, `sched.sh`, `run_if_docker_up.sh` không sửa.
- Test: `tests/test_outbox_four_jobs.py` (24 test). Ba file test cũ chỉ thêm `--logs-dir tmp_path` cho các ca gửi (nếu không ca gửi hỏng sẽ ghi vào `logs/` thật).

## 1. AST theo hàm (HEAD so với bản mới)
```
backup_check     added [] removed [] changed ['build_parser', 'main']
disk_check       added [] removed [] changed ['build_parser', 'main']
restore_drill    added [] removed [] changed ['build_parser', 'main']
daily_data_check added [] removed [] changed ['build_parser', 'main']
```

## 2. Bảng bốn ca × bốn job (mã thoát đo bằng test, `tmp_path`)
| Ca | backup-check | disk-check | restore-drill | daily-check |
|---|---|---|---|---|
| 1 gửi được | exit 1, không có file | exit 1, không có file | exit 1, không có file | exit 2 (=`code`), không có file |
| 2 gửi hỏng | exit **2**, 1 tin trong file | exit **2**, 1 tin | exit **2**, 1 tin | exit 2 (=`code`), 1 tin |
| 3 lần sau gửi được | gửi 2 tin: cũ (kèm `[GỬI TRỄ]`) rồi mới; file tự xoá | như vậy | như vậy | như vậy |
| 4 `--dry-run` | không gửi, không file | không gửi, không file | không gửi, không file | không gửi, không file |

## 3. Phá thử (hash khôi phục khớp cả ba lần)
1. Coi "xếp hàng" là "đã gửi" (ba job `return 1`, daily `sys.exit(0)`): 10 test đỏ, gồm
   `FAILED test_xep_hang_KHONG_doi_ma_thoat_bang_chinh_sach_dot_156_phu_thuoc_vao_day[backup-check|disk-check|restore-drill|daily-check]`
   (dòng đỏ: `assert code == EXPECTED_FAILED_SEND_EXIT[job]`). Nó làm sai bảng đợt 156: ba job này có `normal_exit_codes = {0,1}`, nên mã 1 làm heartbeat im lặng trong khi tin còn nằm trong hàng đợi.
2. Quay lại đường dẫn cứng (`Path(args.logs_dir)` → `Path(DEFAULT_LOGS_DIR)`): 4 test đỏ `test_ca2_gui_hong_...[mọi job]` (`assert code == EXPECTED_FAILED_SEND_EXIT[job]`; file không nằm ở `tmp_path`).
3. Bỏ `outbox.flush()` (tạm sửa `_alert_common.py`, đã khôi phục): `FAILED test_ca3_lan_sau_gui_duoc_tin_cu_di_truoc_roi_tin_moi_va_file_tu_xoa[...]` ở cả 4 job.

## 4. Chạy thật sau khi chép vào repo chính (22:07, tránh 00/06/12/18 và 03:00)
- `sched.sh backup-check --dry-run` → `EXIT=0`, log `2026-10-03 22:07:00 backup-check start / EXIT=0`, không traceback.
- `sched.sh disk-check --dry-run` → `EXIT=0`, log `2026-10-03 22:07:04 disk-check start / EXIT=0`.
- Lưu ý: `sched.sh` tự thêm cờ riêng nên stdout rỗng; kết quả đọc từ log. Phải gọi bằng Git Bash (`bash` mặc định của PowerShell là WSL, không có `/bin/bash`).

## 5. Kiểm tra chung
- `ruff check .` sạch. `uv run pytest -q` ở worktree: **1812 passed** (1788 + 24), 0 failed; không có tiến trình pytest chạy trước đó.
- `logs/alert_outbox_*`: 0 file.

## Cái giá của thiết kế file riêng
Mỗi job có file hàng đợi riêng (không khoá file nên không dùng file chung). Hệ quả: tin hỏng của job hằng ngày chờ đến lần chạy hôm sau (`daily-check` 21:00, `backup-check` 03:00, `disk-check` 6 giờ), `restore-drill` chờ đến Chủ nhật sau (7 ngày). Tôi không thấy cách làm file chung an toàn mà brief bỏ sót.

## Tương tác với bảng mã thoát đợt 156
Hai lớp không trùng nhau: hàng đợi giữ tin; mã 2 của ba job đầu nằm ngoài `{0,1}` nên heartbeat báo "job chưa gửi được". `daily-check`: mã thoát không đổi theo việc gửi được; mã 2 có hai nghĩa như brief đã nêu, không sửa.

## Brief sai ở đâu / điểm lệch
- Hàng đợi gắn tiền tố `[GỬI TRỄ — phát lúc ...]` khi gửi lại, nên "tin cũ" không bằng nguyên văn tin đã xếp; test dùng `in`.
- Tên file hàng đợi theo nhãn có gạch ngang (`alert_outbox_daily-check.jsonl`), không theo tên log `daily-data-check`.
- Dòng số trong brief (`:416`, `:189`...) khớp HEAD.

## Không kiểm được
- GitNexus `impact`/`detect_changes` không có trong công cụ của phiên này; thay bằng AST theo hàm và 4 hàm `main` chỉ có caller là `__main__` và test.
- Không chạy `restore-drill` thật và không gửi Telegram thật; chỉ test bằng mock.
- Đường gửi lại thật (Telegram sống lại sau lúc hỏng) chưa quan sát trên máy thật.

---

## Audit của Claude (04/10/2026, ~02:20)

### A.1. Kết luận: ĐẠT, kèm một test Claude thêm vì phép ghim của `daily-check` không phân biệt được.

### A.2. Phạm vi
AST theo hàm: bốn script chỉ `build_parser` và `main` đổi. Ba file test cũ chỉ thêm `--logs-dir` trỏ vào
`tmp_path`; mọi khẳng định mã thoát (`== 1`, `== 2`) giữ nguyên, không nới. `restore_drill` vẫn
`assert_called_once()` — tức `flush()` trên hàng đợi rỗng không gửi thêm lần nào.

### A.3. Bằng chứng chạy thật, ngoài phần agent nghiệm thu
Code vào cây làm việc lúc 22:07 ngày 03/10, nên job theo lịch đã chạy với nó:

```
2026-10-04 00:00:03 disk-check start      EXIT=0
2026-10-04 02:00:04 backup                EXIT=0   (backup_db.sh, ngoài phạm vi)
```

`disk-check` 00:00 là lần chạy **thật, qua cron, không truyền `--logs-dir`** → mặc định suy từ vị trí file
hoạt động đúng. Đây là điều test không chứng minh được.

### A.4. Phá thử của Claude (khác ba ca agent)

| Phá thử | Kết quả |
|---|---|
| M2 — thêm mã 2 vào diện bình thường của `backup-check` **trong bảng đợt 156** | `test_xep_hang_...[backup-check]` **đỏ** |
| M1 — `daily-check` trả 2 khi tin bị xếp hàng | **xanh** ở bộ test của đợt 157; chỉ một test không liên quan (`test_data_quality.py`) đỏ, do may |

M2 là phép kiểm ràng buộc **theo chiều ngược**: ai nới bảng đợt 156 về sau sẽ bị test đợt 157 chặn. Tốt.

### A.5. Chỗ phép ghim không có hiệu lực, và cách bịt
Test ghim của agent parametrize cả bốn job, nhưng dựng `daily-check` với `DAILY_CODE = 2`
(`tests/test_outbox_four_jobs.py:20`). Phá thử "xếp hàng thì trả 2" **cũng** ra 2, nên hai hành vi khác
nhau cho cùng một con số — phép ghim không phân biệt được.

Claude thêm `test_daily_check_ma_1_xep_hang_van_tra_1_khong_bi_keo_thanh_2`: dựng phát hiện mã **1** ("sót
mã active"), tin bị xếp hàng, và đòi mã thoát **vẫn là 1**. Lúc đó "giữ nguyên" = 1 khác "kéo theo gửi hỏng"
= 2, nên ghim có hiệu lực. Với phá thử M1: `AssertionError: ... phai van la 1, thuc te 2`.

Test cũng khẳng định bảng đợt 156 coi mã 1 của `daily-check` là bình thường — nếu mã thoát nhảy sang 2,
heartbeat sẽ báo thêm "job thất bại" cho một job vốn đã xử lý đúng.

Hash `scripts/daily_data_check.py` sau mọi lần khôi phục: `b0a56ed2e5dd069e`.

### A.6. Điểm agent nêu là "lệch so với brief" — thực ra brief sai
Khi gửi lại, hàng đợi gắn tiền tố `[GỬI TRỄ — phát lúc ...]`. Đó là hành vi có từ đợt 143 và đã ghi trong
`DEPLOYMENT.md` §8.6. Brief của Claude viết "người nhận được **tin cũ trước**, rồi tin mới" mà không nhắc
tiền tố, nên agent so bằng `in` thay vì nguyên văn là **đúng**. Lỗi ở brief, không ở agent.

### A.7. Dọn dẹp và cái chưa kiểm được
- `logs/alert_outbox_*`: không có file nào. Worktree đã xoá.
- GitNexus không chạy được trong phiên của agent (MCP hay chết). Claude thay bằng so AST theo hàm, và bằng
  lần chạy cron thật ở A.3.
- Chưa quan sát đường gửi lại **thật** khi Telegram sống lại sau lúc hỏng. Muốn thấy phải có một lần gửi
  hỏng thật; không dựng được mà không cắt mạng.
