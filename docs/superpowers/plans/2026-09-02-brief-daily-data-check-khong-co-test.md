# Brief đợt 11 — `daily_data_check.py` là chuông báo duy nhất không có test

Giao tối 02/09/2026. Việc nhỏ, làm được ngoài giờ, không chạm `trading/`.

---

## 0. Vì sao có brief này

Bốn chuông báo có lịch tự chạy. Ba cái có test:

```
CO    heartbeat_check          CO    deploy_drift_check
CO    docker_down_alert        KHONG daily_data_check
```

`daily_data_check.py` chạy 15:30 T2–T6, **có gọi `send_telegram`**, và không có
một dòng test nào. Nó là cái duy nhất trong bốn cái mà hành vi chỉ được biết
qua đọc code.

Điều đó đã sinh ra một khẳng định chưa được kiểm chứng: ngày 01/09 Claude kết
luận "ngày lễ không làm nó báo láo, vì trường hợp mất toàn bộ mã trả về code 0
và nhường Heartbeat 2A". Kết luận đó **đúng theo code**, nhưng chưa ai ghim nó
bằng test. Một khẳng định về chuông báo mà chỉ dựa vào đọc code là thứ dự án
này đã trả giá (01/09: `print()` giết `heartbeat_check` 5 lần liên tiếp, không
ai biết).

**Tin tốt: không cần sửa gì để kiểm được.** `evaluate_daily_completeness`
(`scripts/daily_data_check.py:52`) đã là hàm thuần, nhận
`(active_symbols, present_symbols)` và trả `(exit_code, missing, message)`.

---

## 1. Ràng buộc

- **KHÔNG sửa `scripts/daily_data_check.py`.** Không một dòng nào. Đây là bài
  kiểm chứng hành vi hiện có (characterization test), không phải refactor.
  Nếu có nhánh nào không kiểm được mà không sửa script ⇒ **báo cáo, đừng sửa.**
- Chỉ thêm `tests/test_daily_data_check.py`.
- **Không chạm `trading/`, `config/config.yaml`, `scripts/heartbeat_check.py`.**
- **Không commit, không push.** Claude audit rồi mới commit.
- `real_trading_enabled` giữ `false`. Không gọi API SSI. Không đụng DB.
- Không in giá trị bí mật. `.env` không sửa.
- Ngoài phạm vi thì báo cáo, không tự sửa.

---

## 2. Việc — ghim bốn nhánh của `evaluate_daily_completeness`

Test tất định, thuần, **không chạm DB, không chạm Docker, không `sleep`**.

| # | Tình huống | Phải khẳng định |
|---|---|---|
| 1 | `active_symbols` rỗng | `code == 0`, không có mã thiếu |
| 2 | **Không mã nào có bar** (ngày lễ / feed chết toàn diện) | `code == 0` — **không báo động**, nhường Heartbeat 2A |
| 3 | Đủ toàn bộ mã | `code == 0` |
| 4 | Thiếu vài mã trong khi mã khác vẫn có bar | `code == 1`, `missing` đúng tập, message nêu đủ số lượng |

**Test số 2 là lý do brief này tồn tại.** Đặt tên nói rõ ý nghĩa, ví dụ
`test_ngay_le_khong_bao_lao_nhuong_2A`, và viết docstring giải thích vì sao
"im lặng" ở đây là hành vi ĐÚNG chứ không phải thiếu sót — người đọc sau rất
dễ tưởng đây là bug và "sửa" nó thành báo động.

Thêm một test cho phần cắt danh sách: quá 15 mã thiếu thì message phải có phần
`... (+N mã nữa)` — đây là chỗ dễ lệch khi ai đó chỉnh chuỗi.

### Kiểm chứng phá hoại (bắt buộc, theo lệ dự án)

Với **test 2** và **test 4**: cố tình phá `evaluate_daily_completeness` cho
test đỏ, **dán nguyên văn output đỏ vào báo cáo**, rồi **khôi phục nguyên
trạng** (`git diff scripts/daily_data_check.py` phải rỗng khi nộp).

Phép phá đúng cho test 2: cho nhánh "không mã nào có bar" trả `1` thay vì `0`
— nếu test vẫn xanh thì nó không ghim được điều cần ghim.

---

## 3. Tiêu chí hoàn thành

| # | Bước | Kiểm chứng bằng |
|---|---|---|
| 1 | 5 test | `uv run pytest tests/test_daily_data_check.py -v` → 5 passed |
| 2 | Phá hoại | output đỏ nguyên văn của test 2 và test 4 |
| 3 | Script nguyên vẹn | `git diff scripts/daily_data_check.py` **rỗng** |
| 4 | Không hồi quy | `uv run pytest -m "not integration" -q` — không đỏ thêm |
| 5 | Lint | `uv run ruff check trading tests scripts` sạch |

---

## 4. Một phát hiện đã biết — BÁO CÁO, KHÔNG SỬA

`daily_data_check.py` là chuông báo **duy nhất không dùng `_print_safe`**. Ba
cái kia đều có. Nó gọi `print()` thẳng với chuỗi chứa `⚠️` và tiếng Việt
(dòng 132), **trước** khi gọi `send_telegram` (dòng 136).

Nghĩa là nếu `PYTHONIOENCODING=utf-8` không có mặt, `print()` sẽ ném
`UnicodeEncodeError` và giết tiến trình **trước khi cảnh báo kịp đi** — đúng
sự cố 01/09. Hiện nó chỉ được bảo vệ bởi biến môi trường mà
`run_if_docker_up.sh` đặt; chạy tay ngoài cổng là mất lá chắn đó.

**Không sửa trong đợt này.** Lý do: thêm `_print_safe` vào đây là tạo **bản
thứ tư** của cùng một hàm, trong khi việc gộp ba bản hiện có vào
`trading/alerts.py` đã được xếp lịch (task B2, mở khoá sau 14:45 ngày 03/09).
Sửa bây giờ là đi ngược hướng đã chọn.

Việc của bạn: **xác nhận phát hiện này còn đúng** (đọc code, ghi số dòng chính
xác vào báo cáo) để B2 gom luôn `daily_data_check.py` khi mở khoá.

---

## 5. Nói thẳng về khối lượng

Đây là **việc nhỏ**, và sổ tồn đọng cho loại việc "làm được ngoài giờ, không
chạm `trading/`" gần cạn. Đừng bịa thêm việc để lấp chỗ trống — nếu bạn xong
sớm, nộp sớm. Mọi thứ lớn còn lại (đường ống chiến lược, gộp `_print_safe`)
đều chạm `trading/` và bị khoá tới sau phiên 03/09, vì dựng lại container
trước phiên đầu tiên chạy code mới là tự huỷ phép đo.
