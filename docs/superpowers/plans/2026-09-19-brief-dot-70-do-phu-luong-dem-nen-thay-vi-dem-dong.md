# Brief đợt 70 — Độ phủ luồng phải đếm NẾN, và cổng go-live phải nói số liệu bao nhiêu tuổi

Ngày giao: 19/09/2026 (thứ Bảy, tối).
Base: main hiện tại (`ff774e1`).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Vì sao đây là việc đáng làm nhất trước thứ Hai

Sau khi gỡ lệch triển khai, `scripts/check_golive_gate.py` đã từ **EXIT 2 (chặn)** xuống
**EXIT 1 (chỉ còn cảnh báo)**. Thứ duy nhất còn lại là mục 6:

```
6 | Độ phủ luồng phiên gần nhất | 89.5% | [CẢNH BÁO]
    WARN: ... phien chieu 2026-09-18 dat 89.5% (51/57 nen)
```

Nhưng đợt 67 và audit của tôi đã chứng minh con số này **hỏng theo hai cách độc lập**:

**Hỏng 1 — lệch đơn vị.** Tử số đếm **số dòng log**, mẫu số đếm **số nến**:

- `count_stream_bars_closed` (`scripts/stream_health_check.py:100-105`) chỉ đếm dòng chứa
  `"bars closed"`, **không** cộng trường `n`.
- `fetch_expected_bars_from_db` (`:249-251`) tính mẫu số `= slots × symbols`, tức **số nến**.
- Mà `trading/collector/main.py:121-128` phát **một alert cho cả lô**:
  `alert("INFO", "bars closed", n=len(bars), symbols=[...], ...)`.

Một dòng có thể đại diện nhiều nến. Truy vấn DB cho phiên chiều 18/09 ra đúng **19 slot × 3 mã =
57 nến**, tức **không thiếu nến nào** — "89,5%" là hiện vật của phép đo, không phải lỗ hổng dữ
liệu. Sai số luôn theo **một chiều**: báo thấp hơn thực tế.

**Hỏng 2 — số liệu cũ, không ai biết là cũ.** `check_golive_gate.read_latest_stream_coverage`
(`:81`) **không đo lại** — nó đọc **dòng cuối** của `logs/stream-health.log`. Con số 89,5% hiện
trên bảng kiểm là kết quả lưu từ **18/09 15:10**, và bảng kiểm không hề nói điều đó.

Thứ Hai 22/09 là phép đo quyết định. **Đo bằng một cái thước sai và lại còn cũ thì kết quả không
dùng để quyết định gì được.** Sửa thước trước khi đo.

**Giảm rủi ro:** `stream_health_check.py` chạy trên **host** qua `scripts/sched.sh`, **không** nằm
trong image Docker — sửa nó không cần dựng lại container nào.

---

## 1. Ràng buộc

- **Không đổi mẫu số** (`fetch_expected_bars_from_db`) — nó đang đúng.
- **Không đổi ngưỡng** `--min-coverage-warn 0.90` / `--min-coverage-crit 0.50`.
- **Không đụng `trading/`** — đặc biệt không đổi cách `collector/main.py` phát alert.
- Không deploy, không restart container. Không commit, không push.

---

## Task 1 — Tử số đếm nến, giữ luôn số dòng làm chẩn đoán

### 1.0. Đã có sẵn một bản làm ĐÚNG trong repo — theo nó, đừng nghĩ ra cách thứ hai

`scripts/measure_session_stream_metrics.py` **đã giải đúng bài này từ trước**:

```python
# :136-142  — lay n, du phong 1
bars_closed_events.append({"ts": ts_vn, "n": data.get("n", 1), ...})

# :154-156 — in CA HAI con so
print(f"So lan chot nen ('bars closed'): {len(bars_closed_events)}")   # so DONG
stream_bars_total = sum(e.get("n", 1) for e in bars_closed_events)
print(f"So nen chot tu luong: {stream_bars_total}")                     # so NEN
```

Đây chính xác là thiết kế ở mục 1.1–1.2 dưới đây. **Bám đúng ngữ nghĩa của bản này** (cùng tên
trường `n`, cùng quy ước dự phòng `1`, cùng việc giữ cả hai con số) để hai chỗ không bao giờ trả
lời khác nhau về cùng một phiên.

**Có nên gộp thành một hàm dùng chung không?** Có thể đáng, nhưng hai nơi đang phục vụ hai mục
đích khác nhau (bản kia còn gom `lag_ms`, `snapshots`). **Đợt này đừng gộp** — sát ngày đo, đổi
thêm một file nữa là thêm rủi ro. Thay vào đó: **nêu ý kiến của bạn trong báo cáo** về việc có nên
trích hàm chung hay không và trích thế nào, để tôi quyết sau phép đo thứ Hai.

### 1.1. Quy tắc, đóng băng

Với mỗi dòng chứa `"bars closed"` **và** có mốc thời gian rơi trong phiên:

1. Tách phần JSON trong dòng (cả hai định dạng đều có: file bền vững
   `2026-09-19T11:00:18.316714Z {...}` và docker logs `collector-1  | 2026-...Z {...}`).
2. Lấy trường `n` (số nến chốt trong lô đó) và **cộng dồn**.
3. **Dự phòng bắt buộc:** nếu không đọc được JSON, hoặc không có trường `n`, hoặc `n` không phải
   số nguyên dương → tính dòng đó là **1 nến** (giữ hành vi cũ) và **đếm riêng** số dòng như vậy.
   Log cũ có thể có định dạng khác; im lặng bỏ qua chúng là cách làm hỏng phép đo lần nữa.

### 1.2. Giữ cả hai con số

Hàm phải trả về **cả hai**: số nến (tử số mới) **và** số dòng (cách đếm cũ). Lý do: mọi số liệu
lịch sử đã ghi (`72/81` phiên sáng, `51/57` phiên chiều 18/09) đều theo cách đếm cũ — vứt nó đi là
mất khả năng đối chiếu. Cách trả về (tuple, dataclass hay dict) do bạn chọn, miễn **không phá
chữ ký hàm theo kiểu làm nơi gọi khác chết im lặng** — kiểm bằng cách grep toàn bộ nơi gọi
`count_stream_bars_closed` trước khi đổi, và liệt kê chúng trong báo cáo.

### 1.3. Dòng thông báo phải nói rõ đang nói về cái gì

Thông báo `WARN:`/`dung:` hiện ghi `(51/57 nen)` trong khi 51 là số **dòng** — chính chỗ này đã
làm tôi và agent hiểu nhầm suốt hai đợt. Sau khi sửa, thông báo phải ghi rõ số nến, và kèm số
dòng trong ngoặc, ví dụ:

```
WARN: do phu luong phien chieu ngay 2026-09-18 dat 100.0% (57/57 nen, tu 51 dong log),
duoi/tren nguong ...
```

Nếu có dòng phải dùng dự phòng ở mục 1.1.3, thêm `(N dong khong doc duoc n, tinh 1 nen/dong)`.

---

## Task 2 — Cổng go-live phải nói số liệu bao nhiêu tuổi

`read_latest_stream_coverage` (`scripts/check_golive_gate.py:81`) hiện chỉ trả về tỷ lệ và một
chuỗi tóm tắt. Bổ sung: trả thêm **thời điểm** của dòng log đã đọc (mốc `YYYY-MM-DD HH:MM` ở đầu
dòng `stream-health start` tương ứng, hoặc mốc bạn xác định được — nói rõ bạn lấy từ đâu).

Mục 6 của bảng kiểm phải hiển thị thời điểm đó và tuổi của nó, ví dụ:
`89.5% (do luc 18/09 15:10, 2 ngay truoc)`.

**Không** tự động đổi kết luận ĐẠT/CẢNH BÁO dựa trên tuổi trong đợt này — chỉ **hiện** nó ra.
Quyết định "số liệu cũ bao nhiêu thì không được dùng làm căn cứ" là việc của tôi và chủ dự án,
không phải mặc định tôi áp đặt vào code lúc này.

---

## Task 3 — Kiểm chứng

### 3.1. Đây là ĐỔI HỢP ĐỒNG, không phải nắn test cho xanh

`tests/test_stream_health_check.py::test_1_stream_bars_closed_inside_session` hiện có **3 dòng,
mỗi dòng `"n": 3`**, và khẳng định `cnt == 3` — docstring ghi thẳng *"3 dòng → đếm đúng 3"*. Tức
hợp đồng cũ **cố ý** đếm dòng. Sửa nó là đổi hợp đồng, **được phép**, theo đúng tiền lệ đợt 56
§1.3b (đã viện dẫn ở brief đợt 62).

Với **mỗi** test bạn sửa: ghi rõ trong báo cáo giá trị cũ, giá trị mới, và **vì sao** giá trị mới
mới là đúng. Test nào không liên quan tới cách đếm thì **không được đụng**.

### 3.2. Test mới bắt buộc

1. **Gộp lô**: một dòng duy nhất `"n": 3` → tử số = **3 nến**, và số dòng = **1**. Đây là chính
   kịch bản làm hỏng phép đo, phải có test riêng.
2. **Dự phòng**: một dòng `"bars closed"` **không có** trường `n` → tính 1 nến, và bộ đếm "dòng
   không đọc được n" tăng 1.
3. **Không đổi hành vi lọc phiên**: dòng ngoài khung phiên vẫn bị loại (test 3 cũ phải vẫn xanh).

### 3.3. Chứng minh test phân biệt được

Tạm khôi phục cách đếm dòng, chạy test ở 3.2.1 → phải **ĐỎ** (ra 1 thay vì 3). Khôi phục → xanh.
Dán nguyên văn cả hai lần.

### 3.4. Đo lại phiên 18/09 bằng thước mới

Chạy lại trên dữ liệu thật và **đặt cạnh số cũ**:

```bash
uv run python scripts/stream_health_check.py --date 2026-09-18 --session chieu \
  --min-coverage-warn 0.90 --min-coverage-crit 0.50
```

Báo cáo: số nến / số dòng / mẫu số / tỷ lệ mới, so với `51/57 = 89,5%` cũ.

**Lưu ý trung thực:** `logs/bars_closed.log` **không có** dòng `"bars closed"` nào của phiên
18/09 (handler bền vững chỉ lên sóng tối 18/09), và docker logs của container cũ đã mất khi dựng
lại container. Nên rất có thể bạn **không lấy lại được** dữ liệu 18/09 để đo. **Nếu vậy, nói thẳng
là không đo lại được** — đừng bịa một con số, và đừng coi kết quả rỗng là "0 nến". Thay vào đó
dựng một file log giả có gộp lô để chứng minh thước mới chạy đúng.

---

## 4. Không làm

- Không đổi mẫu số, không đổi ngưỡng cảnh báo.
- Không đụng `trading/collector/main.py` (cách phát alert giữ nguyên).
- Không tự đổi kết luận ĐẠT/CẢNH BÁO theo tuổi số liệu (Task 2).
- Không sửa các test không liên quan tới cách đếm.
- Không deploy, không restart, không commit, không push.

---

## 5. Báo cáo cho Claude

1. Danh sách mọi nơi gọi `count_stream_bars_closed` (mục 1.2) trước và sau khi đổi. Để đối chiếu,
   tôi đã tự grep trước khi giao và thấy **đúng 9 chỗ**: định nghĩa tại
   `stream_health_check.py:85`, ba lời gọi trong `main()` cùng file (`:451`, `:453`, `:455`), và
   năm lời gọi trong `tests/test_stream_health_check.py`. `read_latest_stream_coverage` có đúng
   một nơi gọi (`check_golive_gate.py:432`). **Nếu bạn tìm ra khác con số này, báo lại** — nghĩa
   là một trong hai chúng ta sót.
2. Ý kiến về việc có nên trích hàm chung với `measure_session_stream_metrics.py` (mục 1.0).
2. `git diff scripts/stream_health_check.py`, `git diff scripts/check_golive_gate.py`.
3. `git diff tests/test_stream_health_check.py` + bảng "test nào đổi, cũ → mới, vì sao".
4. Bằng chứng test phân biệt được (3.3), nguyên văn cả lần đỏ lẫn lần xanh.
5. Kết quả Task 3.4 (hoặc lời nói thẳng là không đo lại được, kèm chứng minh bằng log giả).
6. Ảnh chụp mục 6 của `check_golive_gate.py` sau khi sửa (dán nguyên văn dòng đó).
7. `uv run pytest -m "not integration" -q` (hiện 706) và `uv run ruff check trading tests scripts`.
