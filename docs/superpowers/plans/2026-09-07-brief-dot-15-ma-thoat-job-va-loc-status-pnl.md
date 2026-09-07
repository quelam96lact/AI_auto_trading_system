# Brief đợt 15 — Mã thoát của job giám sát + bộ lọc status của cầu dao lỗ

Ngày giao: 07/09/2026
Base: `0e75377` (main), cây làm việc sạch, 502 test xanh, ruff sạch.
Người giao: Claude (planner/auditor).

Brief này **tự chứa** — không cần đọc file nào khác để làm. Nếu muốn xem bối cảnh rộng
hơn thì ở `docs/superpowers/plans/2026-09-07-danh-gia-san-sang-golive-4-lop-va-brief-dot-15.md`
(mục L4-1 và L3-3), nhưng **không bắt buộc**.

Hai task độc lập nhau, làm theo thứ tự nào cũng được.

---

## 0. Ràng buộc — đọc hết trước khi gõ dòng đầu tiên

- `real_trading_enabled` giữ `false`. **Không bật, kể cả tạm thời, kể cả trong test thủ công.**
- **Không gọi SSI một lần nào trong đợt này** — kể cả API dữ liệu chỉ đọc. Hai task dưới
  đây không cần SSI. Nếu bạn thấy mình sắp gọi SSI thì bạn đang đi lạc.
- Không in giá trị secret (token, api_key, api_secret, chat_id) ra stdout, log, hay báo cáo.
- `.env` **không được sửa, không được commit**.
- `config/config.yaml` **không được sửa**. Trong lúc làm bạn có thể phát hiện
  `real_order_account: "0434221"` đang trỏ vào một tài khoản rỗng trong khi tiền nằm ở
  `0434226`. **Đúng, tôi đã biết, đã đo, đã ghi vào đánh giá.** Đó là quyết định của chủ dự
  án, không phải việc của đợt này. Đừng sửa.
- Không `TRUNCATE` / `DROP` / xoá dòng trên DB `trading`.
- Không sửa định nghĩa `PaperBroker`, `run_backtest`, `derivative_backtest`.
- **Chỉ sửa đúng các file được nêu tên trong từng task.** Phát hiện ngoài phạm vi thì
  **báo cáo, không tự sửa**. (Đợt 13 đã từng viết đè `scripts/probe_bars_5m_completeness.py`
  từ 481 xuống 184 dòng — một file đã commit của đợt 12 — mà không nhắc một chữ trong báo
  cáo. Tôi phải `git checkout` khôi phục. Đừng lặp lại.)
- **KHÔNG commit, KHÔNG push.** Cứ để thay đổi trong cây làm việc. Tôi audit xong mới commit.
- Trước khi sửa symbol: `gitnexus_impact`. Sau khi sửa: `gitnexus_detect_changes`.
  **Phiên của tôi hôm nay MCP gitnexus timeout (CONNECT_TIMEOUT).** Nếu bên bạn cũng vậy
  thì ghi thẳng vào báo cáo là không chạy được — **đừng im lặng bỏ qua, và tuyệt đối đừng
  bịa kết quả**.

---

## Task 1 — Trả lại mã thoát thật cho `scripts/run_if_docker_up.sh`

### File được sửa

`scripts/run_if_docker_up.sh` — **chỉ** file này. Repo không có khung test cho shell
script; bằng chứng của task này là 4 phép chạy tay ở mục "Kiểm chứng". **Không thêm file
test nào.**

### Vấn đề — đã đo, không phải suy đoán

Ba dòng cuối của file hiện tại:

```bash
"$@" >> "$LOG" 2>&1
echo "EXIT=$?" >> "$LOG"
```

Lệnh cuối cùng của script là `echo`, mà `echo` thì gần như luôn thành công. Vì vậy
script **luôn thoát 0**, bất kể job bên trong đúng hay sai.

`scripts/run_hidden.vbs` thì truyền mã thoát đàng hoàng (`rc = sh.Run(cmd, 0, True)` rồi
`WScript.Quit rc`), nên lỗi nằm đúng ở `run_if_docker_up.sh`, không phải ở lớp gọi.

Bằng chứng đối khớp, **cùng một lần chạy lúc 08:00 ngày 07/09/2026**:

| Nguồn | Nói gì |
|---|---|
| `logs/deploy-drift.log` | `2026-09-07 08:00:03 deploy-drift start` … `EXIT=1` |
| `schtasks /query /tn trading-deploy-drift /v` | `Last Result: 0` |

Job thất bại, Task Scheduler ghi thành công.

Vì sao đáng sửa dù Telegram vẫn kêu: (a) lịch sử `Last Result` của cả 4 task trading là
xanh vĩnh viễn, tức vô nghĩa; (b) trên Ubuntu, **cron gửi mail khi job thoát khác 0** —
kênh cảnh báo đó đang chết sẵn, trong khi `DEPLOYMENT.md` lại hướng dẫn chạy bằng cron.

### Yêu cầu

1. Khi job **chạy thật** (Docker đang lên): script phải thoát **đúng mã thoát của job**.
   Dòng `EXIT=<mã>` ghi vào log phải khớp với mã thoát của chính script.
2. Nhánh **SKIP** phải **giữ nguyên `exit 0`**. Có hai nhánh SKIP: không tìm thấy `.env`,
   và Docker chưa chạy. "Bỏ qua" không phải "thất bại" — đây là hành vi có chủ ý, nhánh
   Docker-chết đã có `docker_down_alert.py` riêng để kêu. Dòng `ALERT_EXIT=` vẫn phải được
   ghi như cũ.
3. **Không đổi bất cứ thứ gì khác**: thứ tự nạp `.env` trước khi kiểm Docker, `rotate_log`,
   `PYTHONIOENCODING=utf-8`, phép thay `localhost` → `127.0.0.1` trong `DB_DSN`, cách suy
   ra `PROJECT_NAME`, và **tất cả các khối chú thích**. Mỗi khối chú thích trong file đó là
   một bài học đã trả giá; đừng dọn dẹp chúng.

### Kiểm chứng — 4 phép, dán output thô của cả 4

| # | Lệnh | Phải thấy |
|---|---|---|
| 1.1 | `scripts/run_if_docker_up.sh t1.log t1 bash -c 'exit 3'` rồi `echo $?` | in `3`; `logs/t1.log` có `EXIT=3` |
| 1.2 | `scripts/run_if_docker_up.sh t2.log t2 bash -c 'exit 0'` rồi `echo $?` | in `0`; `logs/t2.log` có `EXIT=0` |
| 1.3 | `DOCKER_GATE_CONTAINER=khong-ton-tai scripts/run_if_docker_up.sh t3.log t3 echo hi` rồi `echo $?` | in `0`; `logs/t3.log` có `SKIP: docker chua chay` và dòng `ALERT_EXIT=` |
| 1.4 | `scripts/sched.sh deploy-drift` rồi `echo $?` | in `1`; `logs/deploy-drift.log` có `EXIT=1` |

**Phép 1.1 và 1.2 chỉ có nghĩa khi Docker đang lên** — nếu container postgres không chạy
thì cả hai sẽ rơi vào nhánh SKIP và trả 0, và bạn sẽ tưởng 1.2 đạt trong khi thật ra chưa
kiểm gì cả. Kiểm trước bằng `docker ps` và dán kết quả.

**Phép 1.3 — bắt buộc chạy ngoài khung 09:00–15:00** để `docker_down_alert.py` tự quyết
định không gửi. Trong báo cáo phải ghi rõ đã chạy lúc mấy giờ và **xác nhận không có tin
Telegram nào được gửi**. Không được gửi tin thử vào nhóm cảnh báo thật.

**Phép 1.4 — biết trước:** lệnh này **sẽ gửi một tin Telegram thật** báo lệch triển khai
image. Đó là cảnh báo **đúng** cho một tình trạng **có thật** (image collector/engine dựng
06/09 07:45, cũ hơn commit gần nhất chạm `trading/` 14 phút — chủ dự án chưa rebuild). Cứ
để nó gửi, nhưng **ghi vào báo cáo là đã gửi** để chủ dự án không tưởng là tin lạ.

**Phép 1.4 cũng ghi vào `logs/deploy-drift.log` thật — không được xoá hay sửa dòng nào
trong file log đó.**

Nếu đến lúc bạn chạy mà chủ dự án đã rebuild image xong thì phép 1.4 sẽ trả `0` chứ không
phải `1`. **Đừng ép nó ra 1.** Ghi lại đúng những gì thấy, nói rõ là drift đã được gỡ, và
thay bằng một phép khác chứng minh mã thoát khác 0 được truyền (1.1 đã làm việc đó).

### Dọn dẹp

Xoá `logs/t1.log`, `logs/t2.log`, `logs/t3.log` sau khi đã dán bằng chứng.

### Không được làm

Không sửa `run_hidden.vbs`. Không sửa `sched.sh`. Không sửa `log_rotate.sh`. Không tạo,
sửa hay xoá scheduled task nào (`schtasks`) — kể cả `trading-engine-cam` đang thiếu; đó là
việc của chủ dự án.

---

## Task 2 — `read_real_daily_pnl` phải lọc status như chỗ còn lại

### File được sửa

`trading/storage/db.py` và `tests/test_storage.py`. Chỉ hai file này.

### Vấn đề — đã đo, không phải suy đoán

Cùng một bảng `real_order_fills`, hai định nghĩa "fill có hiệu lực" khác nhau:

- `db.py:265-279` `read_real_highest_since_buy` — có lọc:
  `AND side = 'BUY' AND status IN ('placed', 'filled')`
- `db.py:816-832` `read_real_daily_pnl` — **không lọc gì**:
  `SELECT COALESCE(SUM(pnl), 0.0) FROM real_order_fills WHERE account_no = %s AND (...)::date = %s`

Điều này đáng lo vì `read_real_daily_pnl` chính là **cầu dao lỗ trong ngày**
(`trading/real_orders.py:115`).

Lược đồ DB cho thấy đây là thiếu sót chứ không phải chủ ý:

```
"real_order_fills_status_check" CHECK (status = ANY (ARRAY['placed','cancelled','filled']))
```

Ba trạng thái được dự trù từ đầu, nhưng `grep` toàn repo cho thấy **chỉ có một chỗ ghi vào
bảng này** (`write_real_order_fill`, gọi từ `scripts/confirm_real_order.py:178`) và nó chỉ
ghi `'placed'`. Không có chỗ nào cập nhật `status` về sau. Nghĩa là `'cancelled'` là trạng
thái sẽ tồn tại khi có vòng đối soát khớp lệnh — và khi đó `read_real_daily_pnl` sẽ cộng
cả PnL của lệnh đã bị huỷ vào cầu dao.

### Yêu cầu

1. Đặt **một** hằng số cấp module trong `trading/storage/db.py`:
   ```python
   EFFECTIVE_FILL_STATUSES = ("placed", "filled")
   ```
   kèm chú thích ngắn nói rõ **vì sao `'placed'` được tính là có hiệu lực**: hiện chưa có
   vòng đối soát khớp lệnh với SSI, nên lệnh đã đặt được coi là đã có hiệu lực; khi nào có
   vòng đối soát thì phải xem lại hằng số này.
2. Dùng hằng số đó ở **cả hai** truy vấn — `read_real_highest_since_buy` và
   `read_real_daily_pnl`. Đây là "một công thức, một chỗ" (tiền lệ `4ea4c8d`).

   **Truyền qua tham số truy vấn, đừng nội suy chuỗi vào SQL.** Cách sạch với psycopg là
   `AND status = ANY(%s)` rồi truyền `list(EFFECTIVE_FILL_STATUSES)`. Ghép f-string vào
   câu SQL thì vừa dễ sai vừa là thói quen xấu — cả hai truy vấn hiện có đều đang dùng
   tham số hoá, giữ nguyên phong cách đó.
3. **Giữ nguyên** phần `(ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date` trong
   `read_real_daily_pnl` — đó là một bản vá cũ có test riêng
   (`test_read_real_daily_pnl_uses_vn_calendar_day_not_utc`). Đừng vô tình làm hỏng.

### Tự kiểm trước khi sửa

Tôi đã đo lúc 07/09: `SELECT count(*) FROM real_order_fills` trên DB `trading` = **0**.
Nên thay đổi này **không đổi kết quả trên dữ liệu đang có**.

**Bạn hãy tự đo lại.** Nếu ra khác 0 thì **dừng lại và báo cáo**, đừng sửa tiếp — nghĩa là
đã có gì đó ghi vào bảng kể từ lúc tôi đo, và blast radius đã khác.

### Kiểm chứng

1. **Test mới** trong `tests/test_storage.py`, đặt ngay sau
   `test_read_real_daily_pnl_uses_vn_calendar_day_not_utc` (dòng 268-286), viết theo đúng
   khuôn các test sẵn có ở đó. Nội dung: ghi 3 dòng cùng một ngày Việt Nam —
   `'placed'` pnl=+100, `'filled'` pnl=+200, `'cancelled'` pnl=+9999 — rồi khẳng định
   `read_real_daily_pnl` trả về **`300.0`**, không phải `10299.0`.

   Ba giá trị status đó đều hợp lệ với CHECK constraint ở trên, nên `write_real_order_fill`
   nhận được cả ba.

   **Dùng `account_no="ACC_TEST"`** như các test xung quanh. Fixture `storage`
   (`tests/test_storage.py:45-59`) dọn `DELETE FROM real_order_fills WHERE account_no =
   'ACC_TEST'` trước mỗi test — đặt tên tài khoản khác thì dòng của bạn sẽ đọng lại và làm
   test khác chập chờn về sau.

   → **Kiểm chứng bằng:** test này **đỏ trên mã cũ**, **xanh trên mã mới**. Phải dán **cả
   hai** lần chạy, nguyên văn, kèm tên test.

2. **Không được làm hỏng test cũ.** Hai test `read_real_daily_pnl` sẵn có (dòng 226 và 268)
   đều ghi `status="filled"`, nên bộ lọc mới không được đụng tới chúng. Nếu chúng đỏ thì
   bạn đã sửa sai.

3. Toàn bộ suite xanh:
   ```
   docker compose --profile test up -d nats-test
   uv run pytest -q
   ```
   `tests/test_storage.py` có `pytestmark = pytest.mark.integration` và chạy trên DB
   **`trading_test`** (qua `TEST_DSN` trong `tests/conftest.py`). **Tuyệt đối không trỏ test
   vào DB `trading`** — bảng thật đang có 0 dòng và phải giữ nguyên 0 dòng sau khi bạn xong.
   Đo lại và dán bằng chứng ở cuối.

4. `uv run ruff check trading tests scripts` sạch.

5. **Phá hoại có chủ đích:** bỏ bộ lọc status ra khỏi `read_real_daily_pnl`, chạy lại,
   dán **tên test đỏ thật** kèm dòng assert lỗi. Rồi khôi phục, chạy lại xanh, và chạy
   `grep -rn "SABOTAGE" .` cho ra **rỗng**.

### Không được làm

Không đổi `write_real_order_fill`. Không đổi `scripts/confirm_real_order.py`. **Không xây
vòng đối soát trạng thái lệnh** — đó là việc lớn, cần API trạng thái lệnh của SSI, và đang
chờ chủ dự án quyết. Nếu bạn thấy chỗ nào khác cũng nên dùng `EFFECTIVE_FILL_STATUSES` thì
**báo cáo**, đừng tự mở rộng.

---

## 3. Báo cáo nghiệm thu phải có

1. **Output thô, nguyên văn** của từng phép kiểm ở cả hai task. Không tóm tắt. **Không tự
   gõ lại bảng số liệu** — dán đúng thứ chương trình in ra.
   *(Đợt 10 và đợt 14 đều từng có bảng bịa trong báo cáo dù code hoàn toàn đúng. Tôi sẽ
   chạy lại tất cả và đối chiếu từng con số, nên bịa chỉ làm mất thời gian cả hai bên.)*
2. Giờ chạy phép 1.3 + xác nhận **không** gửi Telegram.
3. Xác nhận phép 1.4 **đã** gửi một tin Telegram thật về lệch image (hoặc: drift đã được gỡ
   nên không có tin nào — nói rõ trường hợp nào).
4. Kết quả `docker ps` trước khi chạy 1.1/1.2.
5. `SELECT count(*) FROM real_order_fills` trên DB `trading`, đo **trước và sau** khi làm
   Task 2 — cả hai phải là 0.
6. `git status --short` và `git diff --stat` — để tôi thấy đúng những file được phép sửa,
   không hơn.
7. `gitnexus_impact` / `gitnexus_detect_changes`: dán kết quả, hoặc nói thẳng là MCP không
   kết nối được.
8. Bất cứ thứ gì bạn phát hiện **ngoài phạm vi** — liệt kê, không sửa.

---

## 4. Tiêu chí "xong"

- [ ] `run_if_docker_up.sh` truyền đúng mã thoát của job; hai nhánh SKIP vẫn thoát 0.
- [ ] 4 phép kiểm Task 1 có output thô.
- [ ] `EFFECTIVE_FILL_STATUSES` là hằng số duy nhất, dùng ở cả hai truy vấn.
- [ ] Test mới đỏ-trước-xanh-sau, có cả hai lần chạy.
- [ ] Hai test `read_real_daily_pnl` cũ vẫn xanh.
- [ ] Toàn bộ suite xanh, ruff sạch.
- [ ] Sabotage đã chạy, đã khôi phục, `grep -rn "SABOTAGE" .` rỗng.
- [ ] `logs/t1.log`, `t2.log`, `t3.log` đã xoá; `logs/deploy-drift.log` còn nguyên.
- [ ] `real_order_fills` trên DB `trading` vẫn 0 dòng.
- [ ] Chưa commit, chưa push.
