# Brief đợt 68 — Truy nguyên lệch PnL giữa `engine_state` và `pnl_daily`

Ngày giao: 19/09/2026 (thứ Bảy, tối).
Base: main hiện tại (`9559975`).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

---

## 0. Sự việc — đo được, không suy đoán

Sau khi dựng lại container hôm nay, engine in ra lúc khởi động:

```json
{"level": "INFO", "msg": "engine restored state", "cash": 94367687.69003572,
 "realized_pnl": 144974.89003572706, "positions": {"IJC": 400, "AAA": 400}}
```

Nhưng bảng `pnl_daily` lại nói khác:

| date | realized | unrealized | fees |
|---|---|---|---|
| 2026-07-15 | +45,00 | +200,00 | 165,00 |
| 2026-08-14 | −209.381,13 | 0 | 286.453,02 |
| 2026-08-19 | −60.739,08 | −13.833,26 | 40.435,34 |
| 2026-09-03 | 0 | +20.879,54 | 14.407,20 |
| **Tổng** | **−270.075,21** | | **341.460,56** |

Hai con số cùng mô tả "lãi/lỗ đã thực hiện luỹ kế" của **cùng một tài khoản paper**, nhưng lệch
**415.050,10 đồng và trái dấu nhau**.

Một quan sát của tôi, **coi là manh mối chứ đừng coi là kết luận**: giá vốn hai vị thế đang giữ là
`400 × 7.372,06 + 400 × 7.071,16 = 5.777.288`, cộng với `cash 94.367.687,69` ra `100.144.975,69`
— chênh đúng `+144.975` so với vốn gốc 100 triệu. Tức con số của `engine_state` **tự nhất quán**
với giả định vốn gốc 100 triệu. Nhưng điều đó **không chứng minh** nó đúng: cách tính đó gộp giá
vốn vị thế đang mở vào, nên nó có thể đang gọi nhầm một thứ khác là "realized".

## 1. Vì sao việc này đáng làm ngay

Đây là paper trading nên chưa mất tiền thật. Nhưng nếu có lúc nào bật `real_trading_enabled`, thì
**không được phép tồn tại hai nguồn số lãi/lỗ mâu thuẫn nhau** mà không ai biết bên nào đúng — đó
là cách người ta tưởng mình đang lãi trong khi đang lỗ. Grafana và mọi báo cáo đều đọc từ một
trong hai nguồn này.

---

## 2. Ràng buộc

**Đây là ĐIỀU TRA, không phải sửa lỗi.** Tuyệt đối:

- **Không sửa cách tính PnL** ở bất kỳ đâu trong đợt này.
- **Không "sửa" bằng cách làm một bên khớp bên kia** — chưa biết bên nào đúng thì ép khớp là giấu
  lỗi, không phải sửa lỗi.
- Không ghi, sửa, xoá dữ liệu trong DB (chỉ `SELECT`).
- Không đụng container, không deploy, không bật `real_trading_enabled`.
- Không commit, không push.

---

## Task 1 — Dựng số gốc độc lập từ bảng `orders`

Bảng `orders` là **bằng chứng nguyên thuỷ** (18 lệnh, từ 2026-07-15 đến 2026-09-03). Cả
`engine_state` lẫn `pnl_daily` đều là **số dẫn xuất**. Vì vậy phải tự tính lại từ `orders`, rồi
mới có cơ sở phán xử bên nào đúng.

1. Lấy toàn bộ `orders` (symbol, side, qty, price, ts).
2. Tự tính lãi/lỗ **đã thực hiện** theo từng vòng mua-bán khớp nhau, dùng đúng biểu phí VN đã
   đóng băng trong `trading/paper_broker.py` (`FEE_RATE`, `SELL_TAX_RATE`, `SLIPPAGE_BPS`) —
   **import từ đó, không chép lại hằng số** (một công thức, một chỗ).
3. Nêu rõ quy ước khớp lệnh bạn dùng (FIFO hay bình quân gia quyền) và **vì sao** — nếu hai quy
   ước cho hai kết quả khác nhau, báo cáo **cả hai**.
4. Cho biết `price` trong bảng `orders` là giá **đã gồm** trượt giá/phí hay **chưa** — tra trong
   `paper_broker.py` xem lúc ghi lệnh nó ghi giá nào. Đây là chỗ rất dễ tính trùng hoặc bỏ sót phí.

**Kết quả cần có:** một con số "realized PnL luỹ kế tính từ orders", kèm bảng từng vòng khớp để
tôi soát lại được bằng tay.

## Task 2 — Tìm chỗ mỗi con số được sinh ra

1. `engine_state.realized_pnl`: tìm nơi ghi (grep `engine_state`, `realized_pnl`), xem nó cộng
   dồn theo công thức nào, tại thời điểm nào. Lưu ý `updated_at` của dòng đó là **2026-09-10**,
   trong khi lệnh cuối là **2026-09-03** — giải thích vì sao lệch ngày.
2. `pnl_daily`: tìm nơi ghi. Trả lời rõ: cột `realized` là **gộp cả phí** hay **chưa trừ phí**?
   Bảng này có ghi dòng cho ngày **không có lệnh** không (hiện chỉ có 4 dòng)?
3. Đối chiếu ba con số: số bạn tự tính (Task 1) — `engine_state` — `pnl_daily`.

## Task 3 — Kết luận

Trả lời đúng một trong các khả năng, kèm bằng chứng:

- (a) `engine_state` đúng, `pnl_daily` sai — chỉ ra sai ở đâu.
- (b) `pnl_daily` đúng, `engine_state` sai — chỉ ra sai ở đâu.
- (c) **Cả hai đều "đúng" nhưng đang đo hai đại lượng khác nhau** (ví dụ một bên gồm phí, một bên
  không; một bên gộp giá vốn vị thế mở) — nếu vậy, nói rõ mỗi bên thực sự đo cái gì, và vì sao
  việc đặt tên giống nhau là nguy hiểm.
- (d) Cả hai đều sai.

**Nếu chưa đủ dữ liệu để kết luận, nói "chưa đủ" và nêu cần thêm gì** — đó là câu trả lời hợp lệ
và tốt hơn nhiều so với một kết luận đoán mò. **Đừng sửa gì.**

---

## 3. Báo cáo cho Claude

1. Bảng từng vòng khớp lệnh + con số realized PnL tự tính (Task 1), kèm quy ước đã chọn.
2. Đường dẫn:dòng nơi ghi `engine_state.realized_pnl` và nơi ghi `pnl_daily`, kèm công thức.
3. Bảng đối chiếu ba con số.
4. Kết luận (a)/(b)/(c)/(d) kèm bằng chứng.
5. Xác nhận **không sửa một dòng code nào**, không ghi DB (`git status --short` phải sạch trừ các
   file vốn đã bẩn sẵn).
