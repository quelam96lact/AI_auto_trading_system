# Brief đợt 88 — Vá lỗi "số 0 im lặng" ở đồng bộ tài khoản, và bắt tận tay trong khung 22h

Ngày giao: 24/09/2026, 22:00.
Base: main `5a85205`.
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

**Task 1 phải bắt đầu TRƯỚC 22:05 tối nay.** Task 2–3 làm lúc nào cũng được.

---

## 0. Bối cảnh — việc tồn lâu nhất chưa vá

Đợt 80 tôi phát hiện `account_nav_snapshot` có **11/4106 dòng `nav = 0`**, và **cả 11 dòng đều rơi vào
giờ 22 giờ VN** trong khi giờ 22 chỉ chiếm 3,4% số bản ghi (xác suất ngẫu nhiên ~5×10⁻¹⁷). Truy ngược
thì nguồn lỗi nằm ở `account_balance_snapshot`: chính bảng đó có đúng 11 dòng `withdrawable = 0,
total_debt = 0`, khớp 1:1.

Tôi đã hoãn việc vá **hai lần** với lý do "chưa biết SSI trả về gì trong khung đó". Tối nay tôi đọc code
và thấy **không cần biết mới vá được** — lỗi tự lộ ra trong `trading/collector/account_sync.py:49-65`:

```python
raw = await auth.rest_client.get(EP_ACCOUNT_BALANCE, params={...})
equity = raw.get("equity")
if not equity:
    return                                              # <- CÓ chốt cho ca thiếu cả khối
storage.save_account_balance(
    account_no=account_no, ts=ts,
    account_balance=float(equity.get("accountBalance") or 0),
    total_debt=float(equity.get("totalDebt") or 0),      # <- KHÔNG có chốt cho ca thiếu TỪNG trường
    withdrawable=float(equity.get("withdrawable") or 0),
    ...
)
```

`equity.get("withdrawable") or 0` biến **trường thiếu / `None` / chuỗi rỗng** thành **số 0**, rồi ghi vào
DB như một số đo thật. Hàm đã có chốt cho ca "thiếu cả khối `equity`" (`if not equity: return`) nhưng
**không** có chốt cho ca "có khối nhưng thiếu từng trường". Đó chính là lỗ.

**Đây là lỗi số 0 im lặng, cùng họ FEE-ALARM-2.** Hệ quả không nhỏ: `_sync_nav` lấy `withdrawable` này
tính NAV → NAV = 0; và NAV là **vốn rủi ro của đường lệnh thật** (`engine/main.py`, NAV-CI). Cổng go-live
đợt 80 nay chặn `nav <= 0`, nên vốn đã bớt nguy hiểm — nhưng gốc vẫn chưa vá.

---

## 1. Ràng buộc

- Được sửa: `trading/collector/account_sync.py` và `tests/test_account_sync.py` (**đã tồn tại** — tôi
  kiểm rồi, thêm test vào đó, đừng tạo file trùng), cùng **một** script thăm dò mới ở Task 1.
- `EP_ACCOUNT_BALANCE` là hằng số của SDK (`from ssi_sdk.constant import EP_ACCOUNT_BALANCE`,
  `account_sync.py:3`). Script Task 1 **import lại hằng số đó**, không tự gõ đường dẫn endpoint.
- **Không** sửa `storage/db.py`, `_sync_buying_power`, `_sync_nav`, `compute_nav`.
- **Không** xoá hay sửa dòng nào đã có trong DB. 11 dòng `nav = 0` cũ là **bằng chứng lịch sử**, giữ lại.
- **Không** restart/build container. Collector đang chạy thật.
- **Không** gọi method đặt lệnh. Chỉ đọc.
- Không thêm dependency. Không commit, không push.
- Nền hiện tại: **790 passed**, ruff sạch.

---

## Task 1 — GẤP, trước 22:05: bắt tận tay phản hồi thật trong khung 22h

Khung lỗi quan sát được: **22:06 → 22:51**. Các mốc đã ghi nhận: 22:06, 22:11, 22:16, 22:20, 22:36,
22:39, 22:44, 22:49, 22:51.

Viết `scripts/probe_account_balance_22h.py` — **chỉ đọc, không ghi DB**:

1. Xác thực bằng `trading.collector.ssi_auth.ensure_authenticated(cfg, storage)` — **cùng đường collector
   dùng**, không dùng `make_auth()` (bài học đợt 87).
2. Cứ **60 giây** một lần, từ lúc chạy tới **23:00**, gọi đúng endpoint `EP_ACCOUNT_BALANCE` với
   `clientId` + `accountNo` = `0434221` (dùng lại hằng số và cách gọi trong `account_sync.py:50-53`,
   không tự viết URL).
3. Ghi **nguyên văn JSON thô** mỗi lần gọi ra `data/probe/account_balance_<ngày>.jsonl` kèm `recv_ts`.
   (`/data/` đã trong `.gitignore` từ đợt 87.)
4. In ra màn hình mỗi lần gọi: giờ VN, **danh sách khoá có trong `equity`**, và giá trị thô (chưa
   `float()`) của `withdrawable`, `totalDebt`, `accountBalance`.

**Điều cần trả lời — và chỉ trả lời bằng dữ liệu, không suy diễn:**
- Khi bất thường xảy ra: khối `equity` **có tồn tại** không? Trường `withdrawable` **có mặt** không?
  Nếu có mặt thì giá trị thô là gì — `null`, `""`, `"0"`, hay `0`?
- Nếu **đêm nay không xảy ra** bất thường: nói rõ là không xảy ra, kèm số lần gọi. **Đó là kết quả hợp
  lệ**, không phải thất bại. Chỉ 8/37 ngày có hiện tượng này nên xác suất bắt được đêm nay chỉ khoảng 20%.
  Task 2 **không phụ thuộc** vào việc bắt được.

**Cấm:** không chạy quá 23:00, không gọi dày hơn 60 giây/lần (đừng tạo tải bất thường lên tài khoản thật).

---

## Task 2 — Vá lỗi số 0 im lặng (làm được ngay, không cần chờ Task 1)

**Quy tắc:** phân biệt **"trường thiếu"** với **"giá trị thật bằng 0"**.

- Nếu **bất kỳ** trường nào trong `accountBalance`, `totalDebt`, `withdrawable` **thiếu** (không có khoá,
  hoặc `None`, hoặc chuỗi rỗng) → **KHÔNG ghi dòng nào** vào `account_balance_snapshot`, và phát
  **WARN** nêu rõ **tên các trường bị thiếu** + `account_no`. Cùng tinh thần với chốt `if not equity:
  return` đã có, nhưng ở mức từng trường và **có tiếng** (chốt cũ trả về im lặng).
- Nếu trường **có mặt và bằng 0 thật** (số `0`, hoặc chuỗi `"0"`) → **ghi bình thường**. Số 0 thật là
  trạng thái hợp lệ, không được chặn.
- `buyUnmatched` / `sellUnmatched` giữ nguyên `or 0` — đây là các trường phụ, thiếu thì coi như 0 là hợp
  lý và không ảnh hưởng NAV. **Chỉ** ba trường trên là trường bắt buộc.

**Vì sao WARN chứ không CRITICAL, và vì sao bỏ ghi chứ không ghi 0:** không ghi thì `_sync_nav` dùng dòng
gần nhất còn tốt (cách nhau 5 phút), và cổng go-live có lá chắn độ tươi NAV 24h (đợt 79) sẽ tự kêu nếu
tình trạng kéo dài. Ghi 0 thì phá thẳng vốn rủi ro. Một lần thiếu thoáng qua chưa phải sự cố nghiêm
trọng, nhưng **im lặng thì không chấp nhận được**.

**Kiểm chứng — test đơn vị, không cần mạng (tách hàm thuần nếu cần):**
1. `equity` đủ ba trường, `withdrawable = 5021712` → ghi đúng giá trị, **không** WARN.
2. `equity` thiếu khoá `withdrawable` → **không ghi**, có đúng 1 WARN nêu tên `withdrawable`.
3. `equity` có `withdrawable = None` → như ca 2.
4. `equity` có `withdrawable = ""` → như ca 2.
5. **Ca dễ sai nhất:** `withdrawable = 0` và `totalDebt = 0` (số 0 **thật**) → **ghi bình thường**, không
   WARN. Nếu ca này đỏ thì bản vá đang chặn cả số 0 hợp lệ.
6. Thiếu **hai** trường → WARN nêu **cả hai** tên.
7. Giữ nguyên hành vi cũ: `raw` không có khối `equity` → không ghi, không nổ.
8. **Kiểm thử phá hoại:** đổi điều kiện phát hiện thiếu thành `if False:`, xác nhận **đúng các test 2, 3,
   4, 6** đỏ và **test 1, 5 vẫn xanh**. Khôi phục, xác nhận sạch. Nếu test 5 cũng đỏ thì nó đang kiểm sai.

---

## Task 3 — Đếm lại sau khi vá, để biết mẫu số

Truy vấn và dán nguyên văn:

```sql
SELECT count(*) AS tong,
       count(*) FILTER (WHERE withdrawable = 0 AND total_debt = 0) AS dong_0
FROM account_balance_snapshot WHERE account_no = '0434221';
```

Con số `dong_0` phải **vẫn là 11** (không xoá lịch sử). Khác 11 → báo ngay, nghĩa là có gì đó đã sửa DB
ngoài ý muốn.

---

## 2. Không làm

- Không sửa `db.py`, `_sync_buying_power`, `_sync_nav`, `compute_nav`.
- Không xoá/sửa dòng nào trong DB.
- Không chặn số 0 **thật** (ca test 5).
- Không restart/build container, không đặt lệnh, không commit, không push.
- Không triển khai bản vá vào container trong đợt này — việc đó làm sau, ngoài giờ phiên.

## 3. Báo cáo cho Claude

1. Task 1: số lần gọi, khoảng giờ, và **kết quả thật** — bắt được bất thường (kèm khoá + giá trị thô) hay
   không bắt được. Nói thẳng nếu không bắt được.
2. Task 2: kết quả 7 nhóm test + kiểm thử phá hoại (test nào đỏ, test nào vẫn xanh).
3. Task 3: nguyên văn truy vấn đếm.
4. `uv run pytest -m "not integration" -q` (nền **790**) và `uv run ruff check trading tests scripts`.
5. Bất kỳ điều gì khác thường — nói thẳng.

---

## 4. Các việc tồn khác — trạng thái, để chủ dự án thấy toàn cảnh

| Việc | Trạng thái | Ai làm |
|---|---|---|
| Đợt 87 Task 1–2: thăm dò + ghi thử sổ lệnh | **Brief xong (`965dd92`), chạy 25/09 09:03** | agent, mai |
| Đợt 88 (brief này): vá số 0 im lặng | mới giao | agent |
| Triển khai bản vá đợt 88 vào container | chờ đợt 88 xong | tôi, ngoài giờ phiên |
| **Biểu phí phái sinh thật** | **CHẶN** hướng backtest phái sinh | **chủ dự án** — cần nguồn từ SSI/HNX/VSD |
| Lỗ giữa phiên: GAP-1 chỉ cảnh báo, không tự vá | hoãn có ý thức (hướng 2 brief 79, tôi không khuyến nghị) | chờ quyết |
| Lỗ dữ liệu 06/07, 07/07 | không vá được (lỗ ở nguồn SSI), đã ghi nhận | — |
| T3/T4: đặt+huỷ một lệnh thật, tổng duyệt go-live | cần phiên sống + quyết định của chủ | **chủ dự án** |

**Việc chặn thật sự duy nhất là biểu phí.** Mọi hướng phái sinh dừng ở sàng lọc tín hiệu (không cần phí)
và không đi tiếp được tới backtest cho tới khi có biểu phí kèm nguồn.
