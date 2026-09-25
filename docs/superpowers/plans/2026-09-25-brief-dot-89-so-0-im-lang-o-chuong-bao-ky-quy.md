# Brief đợt 89 — Cùng lớp lỗi số 0 im lặng, nhưng ở chuông báo ký quỹ phái sinh

Ngày giao: 25/09/2026.
Base: main `d0a9a9c`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

Không gấp về giờ. Làm sau khi xong đợt 88 Task 1 (tối nay).

---

## 0. Vì sao có brief này

Đợt 88 vá lỗi `or 0` ở `account_sync._sync_balance`. Sau khi commit, tôi tự hỏi **lỗi này là một dòng hay
một lớp lỗi**, rồi grep cả `trading/`. Tìm thấy **cùng lớp lỗi ở `trading/collector/derivative_sync.py:55-59`
và `:70`**, và hệ quả ở đó **nặng hơn** chỗ tôi vừa vá:

```python
ratio_ssi  = float(ppmmr.account_ratio_ssi or 0)
ratio_vsdc = float(ppmmr.account_ratio_vsdc or 0)
level1 = float(ppmmr.used_limit_warning_level1_ssi or 0)
level2 = float(ppmmr.used_limit_warning_level2_ssi or 0)
level3 = float(ppmmr.used_limit_warning_level3_ssi or 0)
...
level = margin_alert_level(rc_call, ratio_ssi, ratio_vsdc, level1, level2, level3)
```

Và `margin_alert_level` (`derivative_sync.py:10-31`) quyết định như sau:

```python
if rc_call: return "CRITICAL"
ratio = max(account_ratio_ssi, account_ratio_vsdc)
if ratio >= level3: return "CRITICAL"
if ratio >= level2 or ratio >= level1: return "WARN"
return None
```

**Đây là chuông báo sắp bị gọi ký quỹ / cưỡng chế bán của tài khoản phái sinh.** Nó hỏng theo **hai chiều
ngược nhau**, tuỳ trường nào bị thiếu:

| Trường thiếu | `or 0` biến thành | Hệ quả |
|---|---|---|
| Các **ngưỡng** `level1/2/3` | `level3 = 0` | `ratio >= 0` **luôn đúng** → **luôn CRITICAL** mọi lần đồng bộ, dù tài khoản an toàn tuyệt đối |
| Các **tỷ lệ** `ratio_ssi/vsdc` | `ratio = 0` | Không đạt ngưỡng nào → **im lặng**, dù mức sử dụng ký quỹ thật có thể đang nguy hiểm |

Chiều thứ nhất là **báo động giả liên tục** (dùng lâu thành mù, không ai đọc chuông nữa). Chiều thứ hai là
**chuông chết câm** — đúng FEE-ALARM-2.

**Bối cảnh trung thực, đọc kỹ trước khi đánh giá mức độ khẩn:** docstring `margin_alert_level` tự ghi rằng
ngữ nghĩa các trường này **chưa được kiểm chứng dưới mức ký quỹ thật khác 0**, vì **tài khoản phái sinh
`0434228` chưa bao giờ được nạp tiền và chưa bao giờ giao dịch**. Nên lỗi này **chưa từng gây hại**. Nó chỉ
quan trọng đúng vào lúc tài khoản bắt đầu có vị thế thật — tức nếu hướng phái sinh đi tiếp. Vá bây giờ là
vá trước khi cần, không phải chữa cháy.

---

## 1. Ràng buộc

- Được sửa: `trading/collector/derivative_sync.py` và **`tests/test_derivative_sync.py`** — tôi đã kiểm:
  file này **đã tồn tại**, thêm test vào đó, đừng tạo file trùng. (`tests/test_derivative_risk.py` là file
  khác, cho `DerivativeRiskManager`, **không** liên quan `margin_alert_level` — đừng nhầm.)
- **Không** sửa `account_sync.py` (đã vá ở đợt 88), **không** sửa `storage/db.py`, **không** đổi ngữ nghĩa
  `margin_alert_level` (chỉ đổi cách chuẩn bị đầu vào cho nó).
- **Không** restart/build container. **Không** đặt lệnh. Không commit, không push.
- Nền hiện tại: **797 passed**, ruff sạch.

---

## Task 1 — Phân biệt "trường thiếu" với "giá trị 0 thật", cho cả hai nhóm

Áp **đúng khuôn mẫu đợt 88** (`account_sync._find_missing_balance_fields`) để hai chỗ trong repo nhất quán,
đừng phát minh cách khác:

- Trường **bắt buộc**: `account_ratio_ssi`, `account_ratio_vsdc`, `used_limit_warning_level1_ssi`,
  `used_limit_warning_level2_ssi`, `used_limit_warning_level3_ssi`.
- Thiếu (không có / `None` / chuỗi rỗng) **bất kỳ** trường nào trong nhóm đó → **KHÔNG lưu dòng margin**,
  **KHÔNG gọi `margin_alert_level`**, và phát **WARN** nêu rõ **tên các trường thiếu** + `account_no`.
- Giá trị **có mặt và bằng 0 thật** → xử lý bình thường như hiện nay.
- `total_equity` (dòng 70) và các trường ở `_sync_balance` phái sinh (dòng 42-46) là **trường phụ**: giữ
  `or 0`, không đưa vào nhóm bắt buộc. Chúng không tham gia quyết định chuông.

**Vì sao không gọi `margin_alert_level` khi thiếu:** gọi nó với ngưỡng bị nguỵ thành 0 sẽ sinh CRITICAL giả.
Không có dữ liệu thì câu trả lời đúng là "không biết", và "không biết" phải phát ra **WARN nêu lý do**, chứ
không phải một phán quyết về mức ký quỹ.

---

## Task 2 — Kiểm chứng

Test đơn vị (không cần mạng — dựng đối tượng `ppmmr` giả có/thiếu thuộc tính):

1. Đủ cả 5 trường, `ratio = 30`, `level1 = 50` → lưu bình thường, `margin_alert_level` trả `None`, không WARN.
2. **Ca dễ sai nhất — số 0 thật:** đủ cả 5 trường, `ratio_ssi = 0`, `ratio_vsdc = 0`, `level1/2/3 = 50/70/90`
   → **lưu bình thường, KHÔNG WARN** (tài khoản chưa dùng ký quỹ là trạng thái hợp lệ). Test này đỏ nghĩa là
   bản vá đang chặn cả số 0 hợp lệ.
3. Thiếu `used_limit_warning_level3_ssi` (`None`) → **không lưu**, đúng 1 WARN nêu tên trường đó, và
   **không** có alert CRITICAL nào.
4. Thiếu `account_ratio_ssi` → như ca 3, nêu đúng tên trường.
5. Thiếu **hai** trường → WARN nêu **cả hai** tên.
6. **Chứng minh lỗi cũ có thật:** với **code cũ** (`or 0`), `ratio = 10` và cả `level1/2/3` thiếu → phải cho
   ra `CRITICAL`. Viết test này **trước khi sửa** để thấy nó xanh trên code cũ, rồi sau khi sửa đổi kỳ vọng
   thành "không lưu + WARN". **Dán cả hai kết quả** — đây là bằng chứng lỗi tồn tại thật, không phải tôi suy diễn.
7. `rc_call = True` vẫn cho `CRITICAL` khi đủ trường (giữ nguyên hành vi, đừng vô tình chặn mất chuông thật).
8. **Kiểm thử phá hoại:** đổi điều kiện phát hiện thiếu thành `if False:`, xác nhận **đúng các ca 3, 4, 5**
   đỏ và **ca 1, 2, 7 vẫn xanh**. Khôi phục, xác nhận sạch.

---

## 2. Không làm

- Không sửa `account_sync.py`, `db.py`, không đổi ngữ nghĩa `margin_alert_level`.
- Không chặn số 0 **thật** (ca 2).
- Không đưa `total_equity` hay các trường số dư phái sinh vào nhóm bắt buộc.
- Không restart/build container, không đặt lệnh, không commit, không push.

## 3. Báo cáo cho Claude

1. Kết quả `grep`/đọc file cho biết đã có test nào cho `_sync_margin` chưa, và bạn thêm vào đâu.
2. Kết quả **ca 6 trên code cũ** (phải ra `CRITICAL`) và sau khi sửa — dán cả hai.
3. Kết quả 8 nhóm test + kiểm thử phá hoại (ca nào đỏ, ca nào **vẫn xanh**).
4. `uv run pytest -m "not integration" -q` (nền **797**) và `uv run ruff check trading tests scripts`.
5. Bất kỳ điều gì khác thường — nói thẳng.

---

## 4. Ghi chú của planner

**Bài học tôi rút cho chính mình:** đợt 88 tôi vá **một dòng** và coi là xong. Đúng ra phải hỏi ngay "đây là
một dòng hay một lớp lỗi?" và grep cả repo — việc đó mất 30 giây và tìm ra một chỗ nặng hơn. Từ nay, sau mỗi
lần vá một mẫu lỗi, tôi grep cả `trading/` tìm mẫu đó trước khi gọi là xong.

**Còn hai `or 0` tôi cố ý KHÔNG giao:** `octopus_pullback.py:220` và `octopus_combo.py:173`
(`atr = self._atr.last(...) or 0.0`). Ở đó ATR chưa đủ dữ liệu là trạng thái **bình thường và dự kiến**
trong giai đoạn warm-up, và giá trị 0 được dùng có kiểm soát. Không cùng loại với chuông báo. Đụng vào là mở
rộng phạm vi không cần thiết.
