# Brief đợt 149 — bỏ lịch chạy chép tay trong `KHONG_CANH`, và ghép tài liệu hàng đợi cảnh báo vào `DEPLOYMENT.md`

Hai việc nhỏ, đều là tài liệu nằm trong code và tài liệu vận hành. Không đổi hành vi nào.

## Việc 1 — `KHONG_CANH` ghi sai 9 trên 10 giờ chạy

`scripts/heartbeat_check.py::KHONG_CANH` (đợt 142) giải thích vì sao từng job không được canh, kèm
**giờ chạy chép tay**. Claude đối chiếu với cron thật trong `DEPLOYMENT.md` §9 và task Windows đang chạy:

| Job | `KHONG_CANH` ghi | Thật (§9 / Task Scheduler) |
|---|---|---|
| `daily-check` | 21:00 | 21:00 ✅ |
| `backfill` | 21:15 | **20:30** |
| `deploy-drift` | 08:30 và 13:15 | **08:00** |
| `engine-cam` | 09:15–14:45 | **15:15**, một lần |
| `engine-consumer` | 09:00–14:50 | **mỗi 5 phút, 09:00–15:59** (`*/5 9-15`) |
| `stream-health` | 09:20, 11:35, 13:20, 14:50 | **15:10**, một lần |
| `orderbook-recorder` | 08:55–14:46 | **khởi động 08:40** |
| `orderbook-daily-check` | 15:05 | **15:30** |
| `host-preflight` | 07:45 | **07:00 Chủ nhật** |
| `restore-drill` | 03:30 Chủ nhật | **04:00 Chủ nhật** |

Các giờ này không ảnh hưởng hành vi (chỉ là chuỗi giải thích), nhưng người đọc sẽ tin nó. Đây là một
bản sao thứ hai của lịch, viết tay, và đã sai ngay từ ngày đầu. Claude bỏ sót khi audit đợt 142.

**Sửa:** viết lại mọi lý do trong `KHONG_CANH` **không chứa giờ cụ thể**. Mỗi lý do nêu **loại** lịch
(vd "chỉ chạy buổi tối ngày giao dịch", "chỉ chạy trong phiên", "chu kỳ tuần") và **vì sao** không canh
được bằng ngưỡng tuổi cố định. Thêm một câu chú thích trên khối: giờ chạy thật nằm ở `DEPLOYMENT.md` §9,
không chép lại ở đây.

**Ghim chống tái phát:** một test khẳng định không lý do nào trong `KHONG_CANH` khớp mẫu giờ
`\b\d{1,2}:\d{2}\b`. Trong `SCHEDULE_WATCH_JOBS`, `formula_note` **được** chứa giờ, vì đó là số học của
ngưỡng; nhưng thêm một test đối chiếu **giờ gốc** của 5 job canh (02:00, 02:30, 03:00, `*/10`, `*/6`)
với dòng cron tương ứng trong `DEPLOYMENT.md` §9 (đọc từ chính file, không viết cứng). Lịch đổi mà
ngưỡng không đổi theo thì test đỏ.

## Việc 2 — ghép tài liệu hàng đợi cảnh báo vào `DEPLOYMENT.md`

Đợt 143–144 thêm hàng đợi gửi lại cho `trading.alerts.alert` (file `alert_outbox_<dịch vụ>.jsonl` dưới
`/app/logs`, tức `./logs` trên host). `DEPLOYMENT.md` **chưa nhắc tới** nó (Claude grep:
`alert_outbox` → 0 dòng). Báo cáo đợt 143 có sẵn đoạn đề xuất ở mục
`## Đề xuất cho DEPLOYMENT.md` (dòng ~90 của
`docs/superpowers/research/2026-10-02-dot-143-hang-doi-canh-bao.md`).

**Sửa:** thêm một mục ngắn vào `DEPLOYMENT.md`, ở phần giám sát/cảnh báo. **Đối chiếu với code hiện
tại**, không chép nguyên đoạn đề xuất: đợt 144 đã đổi hành vi sau khi đoạn đó được viết. Mục phải
nói:
- file nằm đâu, tên gì, mỗi dòng là gì;
- khi nào nó tồn tại (chỉ khi có tin gửi hỏng chưa gửi lại được) và khi nào tự xoá;
- giới hạn 200 tin, cắt tin dài, xử lý tin hỏng vĩnh viễn (đợt 144);
- thư mục log không ghi được thì hàng đợi **tắt** và có CRITICAL (đợt 144). Trên VPS, `logs/` phải
  thuộc uid 10001; dẫn tới đúng chỗ `DEPLOYMENT.md` đã ghi `mkdir -p logs && sudo chown 10001:10001 logs` (Claude thấy ở khoảng dòng 57; tự tìm lại, đừng tin số dòng);
- xoá tay file này được không, và hệ quả (mất các tin chưa gửi).
- Ghi rõ: hàng đợi chỉ có hiệu lực **sau khi image collector/engine được build lại** từ commit có
  đợt 143–144.

## Giới hạn

- **KHÔNG commit, KHÔNG push**, không sửa task, không restart/build container, không gửi Telegram thật.
- Chỉ sửa: `scripts/heartbeat_check.py` (**chỉ** các chuỗi trong `KHONG_CANH` và chú thích trên khối),
  test tương ứng, và `DEPLOYMENT.md`. Không đổi giá trị nào của `SCHEDULE_WATCH_JOBS`.
- `heartbeat_check.py` chạy thẳng từ cây làm việc, 08:00–15:00 ngày giao dịch. Sửa chuỗi thì rủi ro
  thấp, nhưng vẫn **chỉ lưu vào repo chính ngoài khung đó**. Sau khi lưu, chạy ngay
  `scripts/sched.sh heartbeat --dry-run` để chứng minh không lỗi cú pháp.
- Phát hiện pytest khác đang chạy: `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng trước khi chạy bộ đầy đủ.
- GitNexus: `detect_changes` sau khi sửa; báo 0 thay đổi thì `npx gitnexus analyze` rồi đo lại.

## Tiêu chí hoàn thành

1. So AST theo hàm giữa `HEAD` và bản mới của `heartbeat_check.py`: **chỉ phần thân module** (nơi định
   nghĩa `KHONG_CANH`) khác; không hàm nào khác. Dán kết quả.
2. Phá thử, ghi nguyên văn dòng đỏ, khôi phục, đối chiếu hash:
   - đưa lại một giờ (vd `"Chỉ chạy 21:15 ..."`) vào một lý do → test chống giờ đỏ;
   - đổi `0 2 * * *` thành `0 1 * * *` trong **một bản sao tạm** của `DEPLOYMENT.md` mà test đọc → test
     đối chiếu đỏ. Test phải nhận được đường dẫn file để phá thử trên bản sao; **không sửa
     `DEPLOYMENT.md` thật để phá thử**.
3. `test_deployment_doc.py` xanh. `grep alert_outbox DEPLOYMENT.md` có kết quả. Dán mục mới.
4. `scripts/sched.sh heartbeat --dry-run`: `EXIT=0`, không traceback.
5. `ruff` sạch; `uv run pytest -q` ≥ **1.748 passed** cộng số test mới.

## Báo cáo

`docs/superpowers/research/2026-10-03-dot-149-lich-chep-tay-va-tai-lieu-hang-doi.md`: số đo nguyên văn,
những chỗ đoạn đề xuất của đợt 143 đã lỗi thời so với code, brief sai ở đâu, cái gì không kiểm được.
