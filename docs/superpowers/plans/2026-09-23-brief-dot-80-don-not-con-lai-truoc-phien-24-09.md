# Brief đợt 80 — Dọn nốt phần còn lại trong tối nay, trước phiên 24/09

Ngày giao: 23/09/2026 (thứ Tư, tối muộn). **Task 1 phải xong TỐI NAY, trước 09:00 mai.**
Base: main `7a969a3`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Bối cảnh

Đợt 79 đã vá đèn xanh giả của cổng go-live (cổng nay báo đúng **EXIT 2**). Còn lại bốn việc, trong
đó **một việc gấp**: trạng thái chỉ báo trong bộ nhớ engine hiện đang sai và sẽ bước vào phiên 24/09
với cửa sổ thiếu trọn một ngày.

Bằng chứng tôi tự thu, ngay lúc viết brief này:

```
# Warm-up của engine (chưa restart lại kể từ 22:10)
2026-09-23T15:10:38Z  warm-up HPG xong  bars=201  until="2026-09-22 07:45:00+00:00"  (= 22/09 14:45 VN)

# Nhưng DB đã có đủ nến 23/09 (backfill nạp lúc 22:16 VN, tức SAU warm-up 5,5 phút)
SELECT max(ts AT TIME ZONE 'Asia/Ho_Chi_Minh') FROM bars WHERE symbol='HPG';  ->  2026-09-23 14:45:00
```

Nếu để nguyên, 09:15 mai engine vào phiên với chỉ báo nhảy cóc qua trọn phiên 23/09.

---

## 1. Ràng buộc chung

- Được phép sửa: `scripts/check_golive_gate.py`, `tests/test_check_golive_gate.py`.
- **Không** sửa `trading/` trong đợt này (kể cả `account_sync.py` — xem Task 2, đó là việc **chẩn
  đoán**, không phải việc vá).
- Không thêm dependency.
- Không commit, không push.
- Nền hiện tại: **746 passed**, ruff sạch.

---

## Task 1 — GẤP: nạp lại warm-up cho engine (làm trước, làm ngay)

Đây là task **vận hành**, không sửa code. Brief 79 cấm restart container; **đợt này cho phép, giới
hạn đúng service `engine`**.

1. Ghi lại trạng thái trước: `docker ps --format "{{.Names}} {{.Status}}"`.
2. `docker compose restart engine` (**chỉ `engine`** — không đụng collector/postgres/nats/grafana).
3. Chờ engine khởi động xong, rồi đọc `logs/engine_alerts.log` lấy **3 dòng `warm-up ... xong` mới
   nhất**.

**Tiêu chí hoàn thành — không mơ hồ:** cả ba dòng phải có `"until": "2026-09-23 07:45:00+00:00"`
(= 23/09 14:45 VN). Nếu vẫn ra `2026-09-22 ...` thì **task này THẤT BẠI** — dừng lại, báo cáo ngay,
đừng restart lần nữa và đừng tự suy diễn.

4. Kiểm tra tiếp: có dòng WARN `GAP-1` nào phát sinh sau restart không? **Kỳ vọng: không có** (chưa
   có nến live nào sau warm-up vì đã ngoài giờ phiên). Nếu có, dán nguyên văn.
5. Xác nhận vị thế được khôi phục đúng: dòng `engine restored state` phải vẫn là
   `{"IJC": 400, "AAA": 400}`. Nếu khác, báo ngay.

---

## Task 2 — Chẩn đoán `nav = 0`, **chỉ chẩn đoán, cấm vá**

Khi audit đợt 79 tôi phát hiện `account_nav_snapshot` có **11/4106 dòng `nav = 0`** cho tài khoản
`0434221`, dòng gần nhất lúc **23/09 22:36 VN** — tức mới tối nay. Và:

```
 ts                            | nav | unpriced_symbols
 2026-09-23 15:36:56.24445+00  |   0 | {}
 2026-09-15 15:51:19.693301+00 |   0 | {}
 ...
```

`unpriced_symbols` **rỗng** — nghĩa là đây **không phải** ca "có vị thế nhưng không định giá được"
mà `compute_nav` đã lường trước (`trading/storage/db.py:756-790`). Theo công thức
`nav = cash - debt + Σ(qty × giá)` ở `trading/collector/account_sync.py:135-160`, `nav = 0` với
`unpriced` rỗng chỉ xảy ra khi **vừa không có vị thế nào, vừa `withdrawable - total_debt == 0`**.

Docstring của `_sync_nav` đã ghi nhận **hai lần trước** NAV ra 0 sai (margin debt nạp cứng 0.0; và
lỗi đếm tuổi giá theo ngày lịch thay vì ngày giao dịch). Đây có thể là lần thứ ba, nguyên nhân khác.

**Việc của bạn — chỉ đọc, chỉ báo cáo:**

1. Lấy đúng 11 mốc `ts` có `nav = 0`.
2. Với mỗi mốc, truy `account_balance_snapshot` (bản ghi gần nhất **trước hoặc bằng** mốc đó) — lấy
   `withdrawable` và `total_debt`.
3. Với mỗi mốc, truy `account_position_snapshot` — tại thời điểm đó có vị thế nào không.
4. Lập bảng: `ts | withdrawable | total_debt | số vị thế | nav ghi nhận`.
5. Đối chiếu với các mốc **liền trước và liền sau** (cách ~5 phút) để thấy giá trị nhảy từ bình
   thường sang 0 rồi về bình thường hay không.

**Tiêu chí hoàn thành:** bảng số nguyên văn, đủ 11 dòng, kèm các mốc lân cận.

**Cấm tuyệt đối:** không sửa `account_sync.py`, không sửa `db.py`, không xóa dòng nào trong DB,
**không tự kết luận nguyên nhân**. Đợt 77 đã cho thấy vì sao — diễn giải là việc của tôi.

---

## Task 3 — Bịt khung báo động giả 14:45–15:10 của tiêu chí 6

Tiêu chí 6 (đợt 79) coi một phiên là "hoàn tất" từ **14:45**. Nhưng job đo độ phủ chạy muộn hơn —
tôi đã tự kiểm lịch tác vụ Windows:

```
TaskName                  Trigger
trading-stream-health     2026-09-18T15:10:00+07:00
```

Nên mỗi phiên có khoảng **14:45 → 15:10** mà phiên đã đóng nhưng số đo chưa tồn tại: cổng sẽ FAIL dù
hệ thống hoàn toàn khỏe. **Báo động giả cũng làm hỏng lòng tin vào chuông báo, đúng họ với
FEE-ALARM-2.**

**Yêu cầu:** trong `get_latest_completed_trading_day()`, thay mốc cắt `time(14, 45)` bằng một hằng số
đặt tên, khai báo ở đầu file kèm chú thích dẫn chiếu tới tác vụ `trading-stream-health` (15:10) và
phần biên an toàn, ví dụ:

```python
# Tieu chi 6 chi coi phien la "hoan tat" sau khi job do do phu da co co hoi chay.
# Tac vu Windows `trading-stream-health` chay 15:10:00 +07; cong them bien an toan.
STREAM_COVERAGE_READY_TIME = time(15, 25)
```

Con số 15:25 là đề xuất của tôi (15:10 + 15 phút). Nếu bạn thấy lý do kỹ thuật để chọn khác, **nói
ra trong báo cáo**, đừng tự đổi im lặng.

**Kiểm chứng:**
1. Test **đỏ trước**: chạy cổng lúc `23/09 14:50`, số đo từ `22/09` → kỳ vọng tiêu chí 6 **PASS**
   (vì phiên 23/09 chưa tính là hoàn tất). Test này phải đỏ với code hiện tại.
2. Test giữ ca đúng: chạy lúc `23/09 15:30`, số đo từ `22/09` → vẫn **FAIL**.
3. Ba test cũ của Task 1 đợt 79 phải **vẫn xanh** (đặc biệt test sáng thứ Hai).
4. **Kiểm thử phá hoại:** đổi hằng số về `time(14, 45)`, xác nhận **đúng test mới** đỏ. Khôi phục,
   xác nhận sạch. Dán số lượng test đỏ ở mỗi bước.

---

## Task 4 — Tiêu chí 2 không được coi `nav = 0` là ĐẠT

Độc lập với Task 2: **bất kể nguyên nhân là gì, cổng go-live không được bật đèn xanh khi NAV bằng 0.**
Hiện tại `scripts/check_golive_gate.py` chỉ kiểm `nav is not None`, nên một bản ghi `nav = 0` vẫn ra
`[ĐẠT]` — và đây không phải giả thuyết, tối nay đã có một dòng như vậy lúc 22:36.

**Yêu cầu:** tiêu chí 2 trả **FAIL** khi `nav <= 0`, với ghi chú nói rõ rằng NAV bằng 0 nghĩa là số
liệu tài khoản không dùng được để tính rủi ro, không phải là "tài khoản rỗng".

Thứ tự ưu tiên khi nhiều điều kiện cùng đúng: `nav is None` → FAIL (giữ nguyên); `nav <= 0` → FAIL;
`nav` cũ hơn 24h → WARN; còn lại → PASS. Viết sao cho thứ tự này đọc ra được từ code.

**Kiểm chứng:** test đỏ trước cho `nav=0.0` (kỳ vọng FAIL, exit 2); test giữ `nav` dương tươi → PASS;
test `nav` dương nhưng cũ 28h → WARN (test cũ đợt 79 phải vẫn xanh). Kèm kiểm thử phá hoại như trên.

---

## 2. Không làm

- Không restart collector/postgres/nats/grafana. Chỉ `engine`, đúng một lần, ở Task 1.
- Không sửa bất cứ file nào trong `trading/`.
- Không xóa/sửa dữ liệu trong DB.
- Không tự kết luận nguyên nhân `nav = 0`.
- Không commit, không push.

## 3. Báo cáo cho Claude

1. Task 1: trạng thái container trước/sau, **3 dòng `warm-up ... xong` nguyên văn**, dòng
   `engine restored state`, và có/không GAP-1.
2. Task 2: bảng 11 dòng + các mốc lân cận, nguyên văn.
3. Task 3: dòng test đỏ trước khi sửa → xanh sau khi sửa → kết quả kiểm thử phá hoại. Nếu bạn chọn
   mốc khác 15:25, nói rõ lý do.
4. Task 4: tương tự Task 3.
5. `uv run pytest -m "not integration" -q` (nền **746**) và `uv run ruff check trading tests scripts`.
6. Bất kỳ điều gì khác thường — nói thẳng, kể cả ngoài phạm vi.

---

## 4. Hệ quả cần chủ dự án biết trước (không phải việc của agent)

**Cổng go-live sẽ chặn suốt ngày mai, kể cả khi mọi thứ chạy hoàn hảo.** Vì job `stream-health`
15:10 hôm nay đã ghi `SKIP: docker chua chay`, sẽ **không bao giờ** có số đo độ phủ cho phiên 23/09.
Tiêu chí 6 do đó FAIL cho tới khi job 15:10 **ngày 24/09** chạy thành công. Đây là hành vi **đúng**,
không phải lỗi mới — nhưng nghĩa là **go-live sớm nhất là chiều 24/09**, không phải sáng.

**Về hướng vá gốc warm-up-trước-backfill** (tôi đã nêu 3 hướng ở brief 79, chưa nhận được lựa chọn):
Task 1 tối nay chính là hướng (3) làm bằng tay. Nếu bác muốn tôi viết brief vá thật, **tôi đề xuất
hướng (1)** — engine chờ backfill xong rồi mới warm-up — vì nó sửa đúng quan hệ nhân quả và vẫn
kiểm chứng được bằng test, trong khi hướng (2) biến GAP-1 từ một cái chuông thành một cơ chế tự
động, khó kiểm chứng hơn nhiều. Hướng (3) thì đã tự chứng minh là không đáng tin: nó phụ thuộc vào
việc có người nhớ làm, và chính sự phụ thuộc đó đã làm mất phiên 23/09.
