# Brief đợt 160 — ngày nến thiếu phải có người biết vào sáng hôm sau

## Bối cảnh — Claude đo chiều Chủ nhật 04/10

**Ngày 02/10 (thứ Sáu), `bars_daily` có 8 mã thay vì 174, và chưa ai được báo.**

```
select ngày VN, count(*) from bars_daily   →   23/09..01/10: 174–175 mỗi ngày;   02/10: 8
```

Chuỗi sự kiện, đọc từ `logs/` và Task Scheduler:

| Giờ 02/10 | Job | Điều xảy ra |
|---|---|---|
| 20:30 | `backfill` | `backfill SKIP: docker chua chay` → `ALERT_EXIT=0` (tin "Docker tắt" có gửi, nhưng không ai biết **ngày nến** bị thủng) |
| 21:00 | `daily-check` | **Không có dòng nào** trong `daily-data-check.log`; lần cuối là 10:27 sáng cùng ngày (chạy tay) |
| 22:09 | `daily-check` (chạy tay) | Task Scheduler trả `0x800710E0`, script không chạy |

Không chỗ nào bắt được, vì **cả `backfill` lẫn `daily-check` đều nằm trong `KHONG_CANH`**
(`scripts/heartbeat_check.py:149`): hai job chỉ chạy tối ngày giao dịch, tuổi phụ thuộc cuối tuần, nên đợt 142
có chủ ý không canh tuổi. Lý do đó vẫn đúng. Nhưng hệ quả là **job kiểm dữ liệu ngày đã chết thì không còn ai kiểm
dữ liệu ngày**.

Cửa sổ trượt `BACKFILL_DAYS=7` (`scripts/sched.sh:51`) sẽ **tự vá** 02/10 lúc 20:30 thứ Hai, **nếu** lần đó không
SKIP. Đây là lần thứ ba trong một tuần (28/09, 01/10, 02/10, xem memory "Docker sập làm mất ngày nến"). Lần nào cũng
tự lành hoặc được chạy bù, và lần nào cũng chỉ được phát hiện vì có người tình cờ nhìn.

### Cách tiếp cận: kiểm KẾT QUẢ, không kiểm job

Canh từng job buổi tối thì phải chép giờ chạy vào heartbeat, mà đợt 149 vừa bỏ giờ chép tay vì nó lệch với
`DEPLOYMENT.md` §9. Thay vào đó, kiểm **hệ quả** của cả chuỗi `backfill → daily-check`: **sáng ngày giao dịch, nến
ngày của ngày giao dịch liền trước có đủ không.** Một phép kiểm này bắt được mọi nguyên nhân (Docker tắt, máy ngủ,
task bị từ chối, backfill lỗi mạng, daily-check chết), mà không cần biết giờ chạy của job nào.

Heartbeat là chỗ đúng: nó chạy mỗi 5 phút trong giờ giao dịch, đã đọc `holidays`, đã có DB, đã có file trạng thái để
báo một lần, và **chính nó được `container-health` canh chéo** (đợt 142).

Sáng ra có tin thì người vận hành còn chạy `./scripts/sched.sh backfill` (`DEPLOYMENT.md` §9.6, idempotent) kịp
**trước** khi `account_sync` định giá vị thế bằng giá `bars_daily` cũ.

## Bắt buộc trước khi sửa

- GitNexus: `gitnexus_impact` (upstream) cho `main` của `scripts/daily_data_check.py` và `main` của
  `scripts/heartbeat_check.py`, **báo blast radius trong báo cáo**. Sau khi sửa thì chạy `gitnexus_detect_changes`.
  MCP không chạy được thì ghi rõ và thay bằng `grep` callsite.
- Đọc `scripts/daily_data_check.py:238-320` và `evaluate_daily_completeness` (`:153`). **Không viết logic đủ/thiếu
  thứ hai.**

## Việc 1 — tách phần "đánh giá một ngày" của `daily_data_check.main` thành hàm dùng lại được

Đưa đoạn từ `cfg = load_config(...)` tới lời gọi `evaluate_daily_completeness(...)` (`:259-302`) ra một hàm, ví dụ
`assess_date(storage, cfg, target_date, backfill_log) -> tuple[int, set[str], str]`. `main` gọi lại hàm đó. **Hành vi
`main` không đổi**: cùng thông báo, cùng mã thoát, cùng đường gửi qua outbox.

→ kiểm chứng: toàn bộ test hiện có của `daily_data_check` xanh **mà không sửa test nào**. Phải sửa test cũ mới xanh
nghĩa là hành vi đã đổi: dừng lại và báo cáo.

Lưu ý: `backfill_log` hiện là `Path("logs/backfill.log")` tương đối theo cwd. Hàm mới nhận nó làm tham số; `main`
truyền đúng giá trị cũ. Heartbeat truyền `Path(args.logs_dir) / "backfill.log"`.

## Việc 2 — heartbeat kiểm nến ngày của ngày giao dịch liền trước

Trong `heartbeat_check.main`, **chỉ khi đang trong giờ giao dịch** (cùng cổng giờ mà các phép kiểm khác đang dùng):

1. `P = previous_trading_day(today, holidays)`, lấy từ cùng chỗ mà `daily_data_check` đang import.
2. Nếu file trạng thái đã ghi "đã báo cho ngày `P`" thì bỏ qua. **Mỗi ngày `P` chỉ báo một lần**, không phải mỗi
   5 phút.
3. `code, missing, msg = assess_date(..., P, ...)`.
4. `code` là 1 thì WARN, là 2 thì CRITICAL. Tin phải có: **ngày `P`**, **số mã có / tổng**, và **câu lệnh khắc
   phục** `./scripts/sched.sh backfill` (kèm `DEPLOYMENT.md §9.6`). Gửi qua đúng đường cảnh báo mà heartbeat đang
   dùng (có hàng đợi gửi lại). Ghi "đã báo `P`" vào file trạng thái **chỉ khi không phải `--dry-run`**.
5. Lỗi DB/config trong bước này **không được làm chết** các phép kiểm khác của heartbeat: bắt lỗi, in ra, rồi đi tiếp.
   Đây là job canh mọi thứ khác (đợt 147 đã ghim kiểu lỗi này cho engine-consumer).

Sửa dòng `"daily-check"` và `"backfill"` trong `KHONG_CANH`: thêm một câu rằng **kết quả** của hai job này được
heartbeat kiểm qua độ đủ nến ngày của ngày giao dịch liền trước (đợt 160). Hai job vẫn ở `KHONG_CANH`, vì tuổi job
vẫn không canh được.

**Trùng tin có chủ ý:** nếu tối hôm trước `daily-check` đã báo thiếu thì 08:00 heartbeat báo lại. Chấp nhận, vì hai
tin nói hai việc khác nhau: "thiếu lúc 21:00" và "**sáng ra vẫn chưa ai vá**". Ghi điều này vào docstring.

## Việc 3 — đo tỉ lệ báo giả TRƯỚC khi coi là xong

Trên DB thật, **chỉ đọc**: chạy `assess_date` cho **10 ngày giao dịch gần nhất** (đến hết 02/10), rồi dán bảng
`ngày | mã | code | số mã có/tổng`.

- 02/10 phải ra `code ≥ 1`.
- Ngày nào ngoài 02/10 cũng ra `code ≥ 1` thì đó là **báo giả hằng ngày**. **Dừng, không chỉnh ngưỡng, không thêm
  loại trừ**: báo cáo ngày đó, mã thiếu, và vì sao. Claude sẽ quyết. Một chuông kêu mỗi sáng còn tệ hơn không có chuông.

## Test (file mới `tests/test_heartbeat_prev_day_bars.py`)

Dùng fake storage hoặc monkeypatch theo đúng khuôn của các test heartbeat hiện có. **Không chạm DB thật, không ghi
`logs/` thật.** Lưới an toàn đợt 145/148 phải còn xanh.

1. **Tái hiện 02/10:** hôm nay thứ Hai 05/10 09:00, `P` là thứ Sáu 02/10, có 8/174 mã → đúng **một** cảnh báo, trong
   tin có `2026-10-02`, `8` và `sched.sh backfill`.
2. Gọi lần hai cùng trạng thái → **không** báo thêm.
3. Đủ 174/174 → không báo.
4. Ngày liền trước là ngày nghỉ trong `holidays` → `P` lùi qua ngày nghỉ.
5. `--dry-run` → in tin, **không** ghi trạng thái.
6. `assess_date` ném lỗi → heartbeat vẫn chạy hết các phép kiểm còn lại.
7. Ngoài giờ giao dịch → không gọi `assess_date`.

→ kiểm chứng bằng phá thử: comment lời gọi `assess_date` trong heartbeat → test 1 đỏ, ghi nguyên văn dòng đỏ; khôi
phục → xanh.

## Việc 4 — `DEPLOYMENT.md` §9

Thêm **một đoạn ngắn** vào §9 (Dead-man's switch): heartbeat giờ còn kiểm nến ngày của ngày giao dịch liền trước, báo
một lần mỗi ngày, cách xử lý là §9.6. **Không chép giờ chạy job nào.**

## Giới hạn

- **KHÔNG commit, KHÔNG push.**
- **KHÔNG chạy `scripts/sched.sh` dưới bất kỳ hình thức nào, kể cả phá thử với cờ lạ.** Đây không phải lời nhắc chung
  chung: lệnh phá thử `sched.sh engine-consumer --khong-ton-tai` của một đợt trước đã ghi `EXIT=2` vào
  `logs/engine-consumer.log` **thật**, và kể từ đợt 156 heartbeat đọc dòng đó thành **CRITICAL giả** (Claude đã dọn,
  xem dưới). Muốn chạy heartbeat trên DB thật thì gọi thẳng
  `uv run python scripts/heartbeat_check.py --dry-run --state-file <file tạm>`, và đổi `localhost` thành `127.0.0.1`
  trong `DB_DSN` (memory "Dev env gotchas": `localhost` mất 130 giây mỗi lần kết nối).
- **KHÔNG chạy backfill, KHÔNG ghi DB `trading`.** Ngày 02/10 **để nguyên**: Claude và chủ dự án sẽ vá sau khi đợt
  này xong. Vá trước thì Việc 3 mất ca thật duy nhất để đo.
- **KHÔNG gửi Telegram thật.** KHÔNG lệnh `docker` nào. KHÔNG sửa Task Scheduler.
- KHÔNG đổi cài đặt pin/nguồn của task: chủ dự án đã chốt 29/09 rằng laptop là tạm và triển khai thật là VPS.
- **Chỉ sửa:** `scripts/daily_data_check.py` (chỉ tách hàm), `scripts/heartbeat_check.py`, `DEPLOYMENT.md` §9 (một
  đoạn), cộng một file test mới và file báo cáo. Không sửa `trading/`, `sched.sh`, `run_if_docker_up.sh`, hay test cũ.
- Thấy vấn đề ngoài phạm vi thì **ghi vào báo cáo, không tự sửa.**
- Trước khi chạy bộ đầy đủ:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng.

## Tiêu chí hoàn thành

1. Bảng 10 ngày của Việc 3. 02/10 ra `code ≥ 1`; các ngày khác ra `0`, hoặc có ngày khác ra `≥ 1` thì agent đã
   **dừng và báo** đúng như Việc 3 yêu cầu.
2. Bảy test mới xanh. Có dòng đỏ nguyên văn của phá thử.
3. Test cũ của `daily_data_check` và `heartbeat_check` xanh **mà không sửa dòng nào**.
4. `uv run ruff check trading tests scripts` sạch. `uv run pytest -q` cho số passed ≥ số đo **trước khi sửa** cộng 7,
   và 0 failed. Dán **cả hai** con số.
5. Blast radius từ GitNexus (hoặc `grep` thay thế), và kết quả `gitnexus_detect_changes`.
6. `git status` chỉ có: hai script, `DEPLOYMENT.md`, test mới, báo cáo.

## Phần Claude đã làm 04/10, ghi lại để không ai làm lại

- Dry-run heartbeat trên DB thật (gọi thẳng script, không qua `sched.sh`):
  `[CRITICAL] job theo lịch 'engine-consumer' THẤT BẠI: lần chạy gần nhất lúc 2026-10-02 22:38:59 kết thúc với mã
  thoát 2`. Nguồn: lệnh phá thử `--khong-ton-tai` chạy qua `sched.sh` thật. Nếu để nguyên, **08:00 thứ Hai
  05/10 sẽ có một tin CRITICAL giả**; tới 09:00 lần chạy thật của engine-consumer mới xoá nó.
- Claude dọn lúc 17:46 bằng **một lần chạy thật** `./scripts/sched.sh engine-consumer` (ngoài giờ thì job in
  "bỏ qua" và cho `EXIT=0`, không gửi gì), chứ **không** sửa tay file log. Dry-run heartbeat lại: không cảnh báo,
  `rc=0`.

## Báo cáo

`docs/superpowers/research/2026-10-04-dot-160-ngay-nen-thieu.md` gồm: blast radius, bảng 10 ngày, bảy test cùng dòng
đỏ của phá thử, hai con số pytest, brief sai ở đâu, và những gì không kiểm được.
