# Brief đợt 69 — Grafana đọc PnL luỹ kế từ `engine_state`, nói rõ `pnl_daily` là sổ gì

Ngày giao: 19/09/2026 (thứ Bảy, tối).
Base: main hiện tại (`8b461a8`).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Vì sao

Đợt 68 đã truy ra: `engine_state.realized_pnl` = **+144.974,89** là con số đúng về mặt tài sản,
còn `sum(pnl_daily.realized)` = **−270.075,21** vì `pnl_daily` thiếu hai mảnh (khoản đóng tay HII
ngày 10/09, và phí mua sót ngày 14/08 trước commit `6664cd9`).

Nhưng `grafana/provisioning/dashboards/trading.json` panel `id=2` đang đọc **thẳng** `pnl_daily`.
Nghĩa là người vận hành mở bảng điều khiển ra sẽ thấy danh mục **đang lỗ −270k**, trong khi thực
tế **đang lãi +145k** — sai cả dấu.

Chủ dự án đã chọn **hướng 3**: **không viết lại lịch sử** (không chèn lệnh vá vào `orders`, không
sửa số cũ trong `pnl_daily`), mà **sửa đúng chỗ đang nói sai** — cho Grafana lấy con số luỹ kế từ
`engine_state`, và ghi rõ `pnl_daily` thực chất là **nhật ký phát sinh tự động theo ngày**, không
phải PnL luỹ kế của tài khoản.

---

## 1. Ràng buộc

- **Không sửa dữ liệu**: không `UPDATE`/`INSERT`/`DELETE` vào `pnl_daily`, `orders`, `engine_state`.
  Chỉ sửa file JSON của dashboard.
- **Không đụng code Python trong `trading/` và `scripts/`.** Riêng `tests/` được sửa **đúng một
  file** cho Task 4 (`tests/test_dashboard_queries.py`), chỉ **thêm** test, không sửa test cũ.
- Không restart/build container (Grafana tự nạp lại dashboard provisioned).
- Không commit, không push.

---

## Task 1 — Thêm panel "PnL luỹ kế thực tế", kèm tuổi của số liệu

### 1.1. Vì sao phải kèm tuổi

`engine_state` chỉ có **đúng một dòng** (`id=1`) — nó là **ảnh chụp tại một thời điểm**, không
phải chuỗi thời gian. Hiện tại `updated_at` của nó là **2026-09-10**, tức đã **9 ngày**. Hiện một
con số 9 ngày tuổi mà không nói nó bao nhiêu tuổi thì chỉ là đổi một cái bẫy này lấy một cái bẫy
khác. Vì vậy panel **bắt buộc** hiển thị cả thời điểm cập nhật và số ngày đã trôi qua.

### 1.2. Panel mới

Thêm **một** panel kiểu `table`, đặt ở **trên cùng**, chiếm trọn chiều ngang:

- `gridPos`: `{"h": 4, "w": 24, "x": 0, "y": 0}`
- `title`: `PnL luy ke thuc te (engine_state — nguon dung)`
- `description`: giải thích ngắn rằng đây là con số luỹ kế đúng của tài khoản giấy, gồm **cả** các
  can thiệp thủ công; khác với panel "PnL theo ngay" vốn chỉ ghi nhận lệnh tự động.
- `rawSql`:
  ```sql
  SELECT realized_pnl AS "Realized PnL luy ke",
         cash AS "Tien mat",
         updated_at AS "Cap nhat luc",
         round(extract(epoch FROM (now() - updated_at)) / 86400) AS "So ngay truoc"
  FROM engine_state WHERE id = 1
  ```
- `id`: dùng một id chưa có (hiện đã dùng 1–7, nên dùng `8`).
- Datasource: **dùng đúng cùng datasource với 7 panel hiện có** — copy nguyên khối `datasource`
  của panel `id=2`, đừng tự bịa uid.

### 1.3. Dịch 7 panel cũ xuống

Hàng `y=0` hiện đã kín (panel 1 ở `x=0,w=12` và panel 2 ở `x=12,w=12`). Panel mới cao 4, nên
**cộng đúng 4 vào `y` của cả 7 panel cũ**, giữ nguyên `x`, `w`, `h` của từng panel.

Đây là phép biến đổi cơ học — làm sai một panel là bố cục vỡ. Sau khi sửa phải kiểm lại bằng máy
(xem Task 3), **đừng chỉ nhìn bằng mắt**.

---

## Task 2 — Nói rõ panel cũ đo cái gì

Panel `id=2` hiện có `title` là `PnL theo ngay` — cái tên đó khiến người đọc tưởng là PnL của tài
khoản. Sửa:

- `title` → `PnL theo ngay (chi lenh tu dong)`
- Thêm `description` nói rõ: bảng `pnl_daily` chỉ ghi ngày **có lệnh khớp tự động**; **không** có
  dòng cho ngày không có lệnh; **không** gồm can thiệp thủ công (ví dụ khoản đóng tay HII ngày
  10/09); và số ngày 14/08 còn thiếu phí mua vì chạy trước commit `6664cd9`. Xem
  `docs/superpowers/research/2026-09-19-dot-68-lech-pnl-giua-engine-state-va-pnl-daily.md`.

**Không đổi `rawSql` của panel này** — dữ liệu của nó vẫn đúng với vai trò nhật ký phát sinh.

---

## Task 3 — Kiểm chứng bằng máy, không bằng mắt

Viết một đoạn kiểm (chạy một lần, không cần giữ lại trong repo) và **dán nguyên văn kết quả**:

1. **JSON hợp lệ**: `json.load` file dashboard không ném lỗi. Nếu JSON hỏng thì dashboard biến mất
   khỏi Grafana — đây là rủi ro lớn nhất của đợt này.
2. **Đủ 8 panel**, id từ 1 đến 8, không trùng id.
3. **7 panel cũ giữ nguyên `x`, `w`, `h`**, và `y` **tăng đúng 4** so với bản trong git
   (`git show HEAD:grafana/provisioning/dashboards/trading.json`). In bảng đối chiếu từng panel:
   `id | y_cu -> y_moi | x, w, h co doi khong`.
4. **`rawSql` của cả 7 panel cũ không đổi một ký tự** — so sánh chuỗi với bản trong git.
5. Panel mới có đúng `rawSql` ở mục 1.2 và truy vấn được: chạy thẳng câu SQL đó vào DB, dán kết
   quả (phải ra 1 dòng, `Realized PnL luy ke` = 144974.89…).

---

## Task 4 — Test canh truy vấn panel mới (bổ sung sau khi tôi tự soát brief)

`tests/test_dashboard_queries.py` có **đúng một test cho mỗi panel** của dashboard — 7 test cho
7 panel hiện có (`test_price_panel_query`, `test_pnl_panel_query`, …). Đó là quy ước cố ý: mọi
truy vấn dashboard đều được chạy thật vào DB để nếu ai đó đổi tên cột thì test đỏ chứ không phải
đợi người vận hành phát hiện bảng trống.

Panel thứ 8 phải theo đúng quy ước đó. Thêm `test_pnl_luy_ke_panel_query`:

1. Ghi dữ liệu bằng `storage.write_engine_state(cash, realized_pnl)` (xem `trading/storage/db.py`
   và chỗ gọi ở `trading/engine/main.py:312`) — **dùng hàm có sẵn, không `INSERT` tay**.
2. Chạy **đúng nguyên văn** câu SQL của panel mới ở mục 1.2 (copy y hệt, để test canh đúng chuỗi
   dashboard dùng — giống cách `test_pnl_panel_query` chép nguyên câu của panel `id=2`).
3. Khẳng định trả về **một** dòng, `realized_pnl` và `cash` đúng giá trị vừa ghi, và
   `"So ngay truoc"` bằng `0` (vừa ghi xong).
4. Giữ nguyên style file: `pytestmark = pytest.mark.integration`, dùng fixture `storage` sẵn có.
   Nếu cần dọn dẹp trước test thì thêm vào fixture theo đúng khuôn các dòng `DELETE` đang có.

**Lưu ý khi chạy:** cả file này là `integration`, nên `pytest -m "not integration"` **sẽ không**
chạy nó. Muốn kiểm phải dùng suite đầy đủ với DB/NATS riêng cho test (xem `CLAUDE.md`):

```bash
docker compose --profile test up -d nats-test
uv run pytest -q
```

Test chạy trên `TEST_DSN` (DB `trading_test`), **không** đụng `engine_state` của hệ thống thật —
xác nhận lại điều này trong báo cáo.

---

## 4. Không làm

- **Không sửa `pnl_daily`, `orders`, `engine_state`** (dù chỉ một dòng).
- **Không chèn lệnh "vá" cho khoản HII 10/09** — chủ dự án đã chọn không viết lại lịch sử.
- Không đổi `rawSql` của 7 panel cũ.
- Không sửa `backtest.json` hay dashboard khác.
- Không restart/build container.
- Không commit, không push.

---

## 5. Báo cáo cho Claude

1. `git diff grafana/provisioning/dashboards/trading.json`.
2. Kết quả 5 mục kiểm chứng ở Task 3, dán nguyên văn.
3. `git diff tests/test_dashboard_queries.py` và kết quả chạy `test_pnl_luy_ke_panel_query`
   (Task 4), dán nguyên văn.
4. Xác nhận không đụng dữ liệu DB thật và không đụng code trong `trading/` hay `scripts/`
   (`git diff --stat -- trading/ scripts/` phải rỗng — riêng `tests/` thì có thay đổi hợp lệ của
   Task 4).
