# Đợt 160 — ngày nến thiếu phải có người biết vào sáng hôm sau

Base: main `03e1a6a`. Ngày: Chủ nhật 04/10/2026. Người thực thi: Hermes (`f4a037ad-c2f2-4c60-bb00-e58273bb208a`).
Brief: `docs/superpowers/plans/2026-10-04-brief-dot-160-ngay-nen-thieu-phai-co-nguoi-biet-sang-hom-sau.md`.
Audit: Claude.

## 1. Blast radius và những gì đã sửa

**GitNexus chạy TRƯỚC khi sửa** (MCP không nối được nên dùng CLI qua wrapper
`python .gitnexus_rpc.py impact '<json>'`; phải truyền `target_uid` — gọi bằng tên trần
thì tool trả rỗng):

```
daily_data_check.main : "impactedCount": 1,   "risk": "LOW",  "summary": {"direct": 1}, "processes_affected": 0
heartbeat_check.main  : "impactedCount": 3,   "risk": "LOW",  "summary": {"direct": 1}, "processes_affected": 0
```

Cả hai **LOW** ⇒ không chạm ngưỡng dừng HIGH/CRITICAL của §Bắt buộc, đi tiếp.

`detect_changes` sau khi sửa:

```
"summary": { "changed_count": 27, "affected_count": 1, "changed_files": 3, "risk_level": "medium" }
```

Đã sửa:

| File | Việc |
|---|---|
| `scripts/daily_data_check.py` | Tách `assess_date(storage, cfg, target_date, backfill_log) -> (code, missing, msg)` ra khỏi `main` (đoạn từ `load_config` tới `evaluate_daily_completeness`), `main` gọi lại hàm đó. Hành vi `main` giữ nguyên: `cfg` vẫn đọc **trong** cùng khối `try` nên lỗi config vẫn ra đúng "LỖI TRUY VẤN DB" + exit 2 như trước. |
| `scripts/heartbeat_check.py` | Import `assess_date`; hằng `PREV_DAY_BARS_STATE_NAME`; `app_cfg_for_daily_check()`; `prev_day_bars_alert()`; gọi trong `main` khi `in_check_window`; sửa 2 dòng `KHONG_CANH`; docstring module. |
| `DEPLOYMENT.md` §9 | Một đoạn về phép kiểm mới + sửa "sáu thứ" → "bảy thứ" + thêm 1 dòng bảng (xem §6 mục 6). |
| `tests/test_heartbeat_prev_day_bars.py` | File test mới, 8 test. |

Không đụng `trading/`, `sched.sh`, `run_if_docker_up.sh`, test cũ, `latch/parser/storage`.

## 2. Bảng 10 ngày giao dịch gần nhất (Việc 3, chỉ đọc DB thật)

Chạy `assess_date` thật trên `trading`, `backfill_log = logs/backfill.log`, `DB_DSN` đổi
`localhost` → `127.0.0.1`:

```
ngay         thu      code  co/tong   ma thieu (dau 6)
------------------------------------------------------------------------
2026-09-21   Thu Hai  0     174/174
2026-09-22   Thu Ba   0     174/174
2026-09-23   Thu Tu   0     174/174
2026-09-24   Thu Nam  0     174/174
2026-09-25   Thu Sau  0     175/175
2026-09-28   Thu Hai  0     174/174
2026-09-29   Thu Ba   0     174/174
2026-09-30   Thu Tu   0     174/174
2026-10-01   Thu Nam  0     174/174
2026-10-02   Thu Sau  1     8/175     ABB, ACB, ACV, ANV, BAF, BCM (+161)
------------------------------------------------------------------------
Ngay co code >= 1: 1/10
```

⇒ 02/10 ra `code = 1` **đúng như yêu cầu**, và **chín ngày còn lại đều `code = 0`**: không
có báo giả hằng ngày ⇒ không phải dừng theo §Việc 3. (Ngày thứ Sáu có 175 mã thay vì 174 —
xem §6 mục 1.)

Một lỗi đo của tôi đã tự bắt được: lượt chạy đầu in `?/?` cho 9 ngày vì tôi chỉ parse
"Số mã có bar"/"Tổng số mã active" — nhánh **đầy đủ** của `evaluate_daily_completeness`
không có hai dòng đó (nó nói "toàn bộ N mã active đều đã có bar daily"). Đây là lỗi code
của script đo, đã sửa rồi **chạy lại**; bảng trên là lượt chạy sau khi sửa.

## 3. Test và phá thử

**8 test mới** (brief liệt kê 7 ca; tôi tách ca `code` 1 → WARN và `code` 2 → CRITICAL
thành hai test, cộng lại là 8 — không bỏ ca nào):

```
test_bao_dung_mot_lan_khi_thieu_8_tren_174          (ca 1: tái hiện 02/10, 8/175)
test_muc_2_thi_la_critical                          (code 2 -> CRITICAL)
test_goi_lan_hai_cung_trang_thai_thi_khong_bao_them (ca 2)
test_du_174_tren_174_thi_khong_bao                  (ca 3)
test_ngay_lien_truoc_la_ngay_nghi_thi_lui_tiep      (ca 4: 03/09 -> P = 28/08)
test_dry_run_in_tin_nhung_khong_ghi_trang_thai      (ca 5)
test_assess_date_nem_loi_thi_cac_phep_kiem_khac_van_chay  (ca 6)
test_ngoai_gio_giao_dich_thi_khong_goi_assess_date  (ca 7)
```

Test cũ **không sửa dòng nào** và vẫn xanh: `tests/test_heartbeat_check.py` +
`tests/test_daily_data_check.py` cùng file mới = **87 passed**.

**Phá thử** (sao lưu ra `%LOCALAPPDATA%\Temp\backup_dot160_heartbeat_check.py`, `cp` khôi
phục, so `sha256`; không dùng `git checkout/restore/stash`). Phép phá đúng như brief:
**tắt lời gọi `assess_date` trong heartbeat** (`if in_check_window:` → `if False:`).

```
=== DA PHA: tat phep kiem (if in_check_window -> if False) ===
FAILED tests/test_heartbeat_prev_day_bars.py::test_bao_dung_mot_lan_khi_thieu_8_tren_174
FAILED tests/test_heartbeat_prev_day_bars.py::test_muc_2_thi_la_critical
FAILED tests/test_heartbeat_prev_day_bars.py::test_goi_lan_hai_cung_trang_thai_thi_khong_bao_them
FAILED tests/test_heartbeat_prev_day_bars.py::test_du_174_tren_174_thi_khong_bao
FAILED tests/test_heartbeat_prev_day_bars.py::test_ngay_lien_truoc_la_ngay_nghi_thi_lui_tiep
FAILED tests/test_heartbeat_prev_day_bars.py::test_dry_run_in_tin_nhung_khong_ghi_trang_thai
FAILED tests/test_heartbeat_prev_day_bars.py::test_assess_date_nem_loi_thi_cac_phep_kiem_khac_van_chay
7 failed, 1 passed in 0.65s
```

Nguyên văn dòng đỏ của **test 1** (chạy riêng khi vẫn đang phá):

```
>       assert calls == [FRIDAY], f"phải kiểm đúng ngày liền trước, thực tế {calls}"
E       AssertionError: phải kiểm đúng ngày liền trước, thực tế []
E       assert [] == [datetime.date(2026, 10, 2)]
E         Right contains one more item: datetime.date(2026, 10, 2)
tests\test_heartbeat_prev_day_bars.py:154: AssertionError
FAILED tests/test_heartbeat_prev_day_bars.py::test_bao_dung_mot_lan_khi_thieu_8_tren_174
1 failed, 7 deselected in 0.44s
```

Khôi phục `cp` từ bản sao lưu: `8 passed`, `sha256 scripts/heartbeat_check.py =
0d80845982866767…`. Test **không** đỏ khi phá là ca 7 ("ngoài giờ giao dịch thì không gọi") —
đúng, vì ca đó khẳng định **không** gọi, mà bản phá cũng không gọi.

### Hai chỗ bộ test bắt được lỗi thật của tôi

1. **Test cũ `test_main_prints_message_to_stdout_before_sending` đỏ** khi tôi cho dòng
   "[WARN] heartbeat không kiểm được…" ra **stdout**. Test đó ghim hợp đồng "stdout phải
   bằng đúng nội dung gửi Telegram". ⇒ Chuyển dòng lỗi sang **stderr** (và viết không dấu,
   bọc `try`, vì stderr không được reconfigure utf-8 như stdout — in dấu có thể ném
   `UnicodeEncodeError` ngay trong `except`, tức chuông báo chết theo). Không sửa test cũ.
2. Kỳ vọng của tôi sai ở ca 2: tôi viết `len(sent2) == 1` trong khi `sent2` là list **của
   lượt chạy thứ hai** nên phải là `[]`. Sửa test, giữ mã.

## 4. Hai con số pytest (yêu cầu §Tiêu chí 4)

```
TRƯỚC (bản sao nguyên vẹn của HEAD):  1824 passed in 107.09s
SAU   (cây làm việc hiện tại):        1832 passed in  85.73s
```

Chênh **đúng 8** = 8 test mới; **0 failed** cả hai lượt; 1832 ≥ 1824 + 7 ⇒ đạt.

Nói thẳng cách đo: tôi **không** đo "trước" ngay từ đầu (đã lỡ sửa xong mới chạy bộ đầy
đủ), nên lấy số "trước" bằng bản sao nguyên vẹn của `HEAD` dựng ra **ngoài repo** —
`git archive HEAD | tar -x -C <scratch>/pristine_dot160` rồi chạy pytest bằng
`.venv/Scripts/python.exe` của repo, cùng `.env`, cùng `logs/` — **không** dùng
`git checkout/restore/stash` và không đụng cây làm việc. Con số 1824 là đo được, không
phải suy ra.

`uv run ruff check trading tests scripts` → `All checks passed!` (trước đó ruff bắt 2 lỗi
trong **file test của tôi**: F401 import thừa, RUF059 biến `calls1` không dùng — đã sửa).

Chạy thêm ca dry-run heartbeat trên DB thật (đúng cách brief cho phép, gọi thẳng script,
`--dry-run`, state file trong Temp, `DB_DSN` dùng `127.0.0.1`): `rc=0`, **không in gì** —
mọi phép kiểm cũ đều xanh (tin CRITICAL giả về `engine-consumer` mà Claude dọn lúc 17:46
đã sạch), và phép kiểm mới im lặng vì lúc chạy là **18:0x Chủ nhật, ngoài giờ giao dịch**
— đúng thiết kế.

## 5. `git status`

```
 M DEPLOYMENT.md
 M scripts/daily_data_check.py
 M scripts/heartbeat_check.py
?? tests/test_heartbeat_prev_day_bars.py            <- test mới
?? docs/superpowers/research/2026-10-04-dot-160-ngay-nen-thieu.md   <- báo cáo này
?? "Các chiến lược BTCUSDT perpetual 1H bổ sung cho EMA + Order Flow.md"   <- CÓ TỪ TRƯỚC, không phải đợt này
?? docs/superpowers/plans/2026-10-04-brief-dot-160-…md                     <- brief của Claude
```

Hai file `??` cuối đã có từ trước khi tôi bắt đầu (file `.md` BTCUSDT là của đợt 105/106,
brief là của Claude) — tôi không tạo, không sửa. Ngoài ra chỉ có 3 file được sửa + 1 test
mới + báo cáo, đúng §Tiêu chí 6.

## 6. Brief sai / chưa chính xác ở đâu

1. **"02/10 có 8 mã thay vì 174"** — đo thật là **8/175**. Ngày **thứ Sáu** có 175 mã
   active chứ không phải 174, vì `assess_date` chỉ loại nhóm mã "chỉ giao dịch thứ Sáu"
   khi `target_date.weekday() != 4`; hôm thứ Sáu nhóm đó được tính là active. Chính SQL
   trong brief cũng ghi "23/09..01/10: 174–175 mỗi ngày", nên con số 174 ở dòng 5 là con
   số của ngày thường, không phải của 02/10.
2. **"số mã có / tổng" trong tin**: `assess_date` trả `(code, missing, msg)` — **không**
   trả hai con số riêng. Hai con số đó chỉ tồn tại **bên trong `msg`**, và chỉ ở nhánh
   *sót mã* ("Tổng số mã active: N"/"Số mã có bar: M"); nhánh *đầy đủ* chỉ nói "toàn bộ N
   mã", nhánh *0 bar* chỉ nói "toàn bộ N mã active thiếu bar". Nên tin của heartbeat chứa
   **nguyên văn `msg`** (có đủ hai con số) chứ không phải chuỗi gọn "8/175". Muốn dạng gọn
   thì phải đổi chữ ký `assess_date` — brief lại chốt chữ ký 3 phần tử.
3. **"bắt lỗi, in ra, rồi đi tiếp"** không nói in ra **đâu** — in ra stdout làm đỏ một test
   cũ (mục 3). Tôi in ra **stderr**. Nếu ý brief là stdout thì phải sửa test cũ, mà §Tiêu
   chí 3 lại cấm sửa test cũ ⇒ hai yêu cầu không cùng tồn tại được; tôi chọn vế "không sửa
   test cũ".
4. **`cfg` cho `assess_date`**: brief chốt chữ ký `assess_date(storage, cfg, …)` nhưng
   heartbeat **cố ý** không dùng `trading.config.load_config` (hàm đó đòi đủ `SSI_*` trong
   môi trường, mà chuông báo phải chạy khi thiếu — lý do đã ghi sẵn trong `main`). Tôi
   dựng `Config` từ chính YAML heartbeat đã đọc (`app_cfg_for_daily_check`), các trường SSI
   để rỗng vì `assess_date` chỉ đọc `symbols`, `ssi_equity_accounts`, `holidays`.
5. **"file trạng thái"** không nói file nào. Tôi dùng **file riêng**
   `logs/.prev_day_bars_state.json`: không nhét khoá vào `.schedule_health_state.json` được
   vì `evaluate_schedule_health` **dựng lại toàn bộ** dict đó mỗi lần chạy nên khoá lạ sẽ
   bị xoá mất.
6. **Doc tự mâu thuẫn**: §9 có câu "Script kiểm **sáu thứ**" + bảng 6 dòng. Thêm phép kiểm
   thứ bảy mà để nguyên thì doc nói sai. Tôi sửa thành "bảy thứ" và thêm 1 dòng bảng —
   **vượt quá "một đoạn ngắn"** brief cho phép, nêu ra đây để Claude quyết giữ hay bỏ.
7. `KHONG_CANH`: đã thêm câu cho `daily-check` và `backfill`, **không** chép giờ nào
   (test cũ `test_khong_canh_reasons_contain_no_hardcoded_times` vẫn xanh).

## 7. Những gì KHÔNG kiểm được

1. **Chưa có ca thật trong giờ giao dịch.** Hôm nay Chủ nhật nên phép kiểm mới không chạy
   (đúng thiết kế, và tôi cố ý không giả lập thời gian trên script thật). Ca thật đầu tiên
   là **sáng thứ Hai 05/10** trong phiên: `P` = thứ Sáu 02/10, lúc đó 02/10 vẫn thiếu nếu
   chưa ai vá ⇒ dự đoán có **một** tin WARN kèm `./scripts/sched.sh backfill`. Đây là
   nghiệm thu thật, và cũng là lúc kiểm được chuỗi trạng thái → không báo lại lần hai.
2. **Tin đã tới người hay chưa** không kiểm được trong đợt này: tôi không gửi Telegram thật
   (đúng giới hạn). Đường gửi là đường cũ `send_with_outbox` + hàng đợi `heartbeat`.
3. **Quyết định "ghi trạng thái trước hay sau khi gửi"** là chỗ tôi chọn khác thói quen cũ
   và cần Claude soi: tôi ghi **ngay** khi đã xếp tin vào `messages` (không chờ kết quả
   gửi), vì `send_with_outbox` đã xếp tin vào hàng đợi khi gửi hỏng nên tin không mất, còn
   ghi muộn thì mỗi 5 phút lại báo lại cùng một ngày. Rủi ro còn lại: nếu gửi hỏng **và**
   ghi file hàng đợi cũng hỏng thì tin mất mà trạng thái đã ghi ⇒ ngày đó không ai báo
   nữa. Trạng thái lịch (`save_schedule_state`) thì ngược lại — chỉ lưu khi gửi **thành
   công**. Hai chỗ khác nhau là có chủ ý, nhưng nêu ra để không ai phải đoán.
4. **Số mã/tổng cho ngày rơi vào nhánh "hoãn phán quyết"** (0 bar + backfill chưa xong):
   script đo của tôi in `?/?` vì message của nhánh đó không chứa con số nào. Không ảnh
   hưởng 10 ngày đã đo, nhưng nếu Claude muốn bảng đo dùng lại được thì phải lấy số trực
   tiếp từ `storage`, không parse message.
5. **Không chạy `scripts/sched.sh` dưới bất kỳ hình thức nào** (kể cả cờ lạ) và **không
   lệnh `docker` nào** — nên "phép kiểm mới có thật sự chạy trong cron/Task Scheduler
   không" chưa kiểm được; cái kiểm được là `main()` chạy đúng khi gọi thẳng.
6. **`is_trading_time(now, holidays)` với `holidays` là `frozenset`** bị Pyright phàn nàn
   (`set[date]` vs `frozenset[date]`) — lỗi kiểu **có sẵn**, không phải do đợt này; tôi chỉ
   nhân tiện viết lại đúng dòng đó thành biến `in_check_window` nên nó hiện ra trong diff.
   Không sửa (ngoài phạm vi).

Tôi không commit, không push, không chạy `sched.sh`, không lệnh `docker`, không gửi
Telegram, không sửa Task Scheduler, không ghi DB `trading` — ngày 02/10 để nguyên.

---

## Audit của Claude (04/10/2026)

### Kết luận: ĐẠT.

| Kiểm | Kết quả |
|---|---|
| Phạm vi | `git status`: đúng hai script, `DEPLOYMENT.md`, test mới, báo cáo. Không có `logs/.prev_day_bars_state.json` nào bị tạo ở repo. |
| Tách `assess_date` | Đọc diff từng dòng: thân hàm trùng với đoạn cũ của `main`, đường gửi qua outbox giữ nguyên. Chỉ có một khác biệt nhỏ: `check_backfill_completed` và `evaluate_daily_completeness` giờ nằm **trong** `try`, nên nếu chúng ném lỗi thì thoát mã 2 với "LỖI TRUY VẤN DB" thay vì traceback. Chấp nhận được vì mã 2 vẫn nằm trong diện canh của bảng đợt 156. |
| `ruff check trading tests scripts` | sạch |
| `pytest` 8 test mới | 8 passed |
| `pytest -q` bộ đầy đủ | **1832 passed**, khớp số agent báo (1824 + 8) |
| `gitnexus_detect_changes` | 3 file, 1 luồng bị ảnh hưởng (`daily_data_check.main → _get_pool`), mức medium. Vài symbol "touched" ngoài diff (`get_last_called_timestamp`, `LEDGER_TOLERANCE`) là do số dòng bị dịch so với index cũ; đã đối chiếu diff thật. |

### Mô phỏng thứ Hai trên DB thật — phép kiểm agent không làm được

Gọi thẳng `prev_day_bars_alert` với `now` = 08:05 05/10 và 08:05 02/10, đọc DB thật, `alerted_for=None`, không gửi
gì, không ghi trạng thái:

- **05/10 → P = 02/10:** một tin `[WARN]` với 175 mã active, 8 mã có bar, 167 mã thiếu, kèm câu `./scripts/sched.sh
  backfill`. Gọi lần hai với `alerted_for="2026-10-02"`: không báo lại.
- **02/10 → P = 01/10:** không báo, đúng vì ngày đó đủ nến.

Tức là đường gọi thật, gồm `app_cfg_for_daily_check` dựng từ YAML thật và `Storage` thật, **không ném lỗi**. Điều
này quan trọng vì nhánh `except` chỉ in ra stderr (xem rủi ro bên dưới).

### Về các chỗ agent nói brief lệch: đồng ý cả năm

- 8/175 (không phải 8/174) là do nhóm mã chỉ giao dịch thứ Sáu, Claude đếm thô bằng SQL nên lệch.
- Dùng file trạng thái riêng là đúng: `.schedule_health_state.json` bị dựng lại toàn bộ mỗi lần chạy.
- In lỗi ra stderr là đúng, vì hợp đồng stdout bằng nội dung tin đã được ghim bằng test.
- Ghi trạng thái trước khi biết gửi được hay chưa (mục 3 của agent): chấp nhận. Muốn mất tin thì phải hỏng cả gửi
  lẫn ghi hàng đợi.

### Rủi ro còn lại, chưa sửa

Nếu `assess_date` ném lỗi ở **mọi** lần chạy (ví dụ một khoá YAML đổi tên), phép kiểm mới chết lặng: chỉ còn một dòng
`[WARN]` trong `heartbeat.log`, không có tin nào. Muốn báo ra ngoài thì phải chống spam (5 phút một lần), nên để
thành việc sau, nếu chủ dự án thấy cần.

### Nghiệm thu thật

08:00–08:05 thứ Hai 05/10: phải có **đúng một** tin WARN cho 02/10. Sau đó vá bằng `./scripts/sched.sh backfill`,
hoặc để backfill 20:30 tự vá. Tối đó kiểm lại `bars_daily` của 02/10 phải lên khoảng 175.
