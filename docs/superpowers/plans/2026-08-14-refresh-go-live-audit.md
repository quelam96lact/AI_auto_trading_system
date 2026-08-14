# Kế hoạch: cập nhật GO_LIVE_AUDIT.md cho đúng thực tế

Ngày giao: 2026-08-14 tối. Nhánh: `feature/data-layer`. Base: `37035dd`.

**KHÔNG commit, KHÔNG push.** Việc này **chỉ sửa `GO_LIVE_AUDIT.md`** — không
đụng một dòng code nào.

---

## QUY TẮC TUYỆT ĐỐI CHO VIỆC NÀY

Tài liệu này tồn tại vì bản `DEPLOYMENT_READINESS.md` cũ đã khẳng định sai và
suýt làm người đọc tin hệ thống sẵn sàng hơn thực tế (xem chính mục "rác nguy
hiểm nhất" trong file, dòng 451).

Nó **đang lặp lại đúng lỗi nó sinh ra để chữa**: bảng backtest ở dòng 500-505 là
số tính bằng công thức có lỗi kế toán, và một trong hai "quan sát" bên dưới nói
ngược với sự thật đã đo.

Vì vậy:

- **Chỉ chép số đã đo.** Không thêm nhận định, dự đoán, khuyến nghị đầu tư, hay
  lời an ủi kiểu "cần tối ưu thêm". Nếu bạn viết một câu mà không chỉ được nó
  lấy số từ đâu — xoá câu đó.
- **Giữ nguyên tắc của chính file** (dòng 11): đính chính **tại chỗ** bằng khối
  `> ĐÍNH CHÍNH`, **KHÔNG xoá** kết luận cũ. Biết mình đã sai ở đâu là một phần
  giá trị của tài liệu.
- **Mọi con số phải ghi rõ lấy từ commit nào.**
- **KHÔNG chạy lại backtest.** Số dưới đây đã được audit dựng lại độc lập và
  khớp. Chạy lại chỉ tạo rủi ro lệch số. Nếu bạn nghi một con số — hỏi, đừng tự
  chạy rồi thay.
- **KHÔNG** đụng số tài khoản thật đang có trong file.

---

# SỬA 1 — bảng backtest 5 phút đang là số SAI (dòng 497-511)

Bảng hiện tại tính bằng công thức bỏ sót phí mua. `6664cd9` đã sửa và chạy lại.

Thêm khối `> ĐÍNH CHÍNH` ngay dưới bảng cũ, **giữ bảng cũ nguyên vẹn**:

```
sma_cross, 5m, 2026-04-03 -> 2026-08-07, khong chinh mot tham so nao (6664cd9):

                            CU (sai)                      MOI (dung)
  HII,IJC,AAA / 5.021.459   24 lenh 8,3%  -153.067    18 lenh 5,6%    -152.818
  HII,IJC,AAA / 1 ty        16 lenh 6,2% -32.571.418  14 lenh 7,1%  -31.907.394
  VCB,HPG,TCB / 5.021.459    0 lenh                    0 lenh (khong doi)
  VCB,HPG,TCB / 1 ty        17 lenh 52,9% -6.094.804  17 lenh 23,5% -14.552.406

Tach phi ra khoi ket qua (con so tra loi cau hoi bien loi the):
                            PnL gop truoc phi   phi+thue      PnL rong
  HII,IJC,AAA / 5.021.459        -118.160         34.659      -152.818
  HII,IJC,AAA / 1 ty          -22.834.951      9.072.443   -31.907.394
  VCB,HPG,TCB / 1 ty           -4.702.361      9.850.045   -14.552.406
```

Ghi rõ: dòng VCB,HPG,TCB / 1 tỷ tụt mạnh nhất (52,9% → 23,5% tỉ lệ thắng) vì
**năm lệnh trước đây chỉ "thắng" nhờ chưa tính phí vào lệnh**.

## SỬA 1b — một "quan sát" đang nói NGƯỢC sự thật

Dòng ~509 viết:

> lỗ trung bình mỗi lệnh RUN 1 = -6.378 ... phí vòng khứ hồi VN ~0,3-0,4% cộng
> slippage **chiếm phần lớn con số đó**

Sau khi tách phí (bảng trên), điều này **sai**: cả ba cấu hình có lệnh đều lỗ
**CẢ TRƯỚC KHI trả phí**. Phí làm vết thương sâu thêm, **không phải nguyên nhân**.

Đây là câu nguy hiểm nhất trong cả file vì nó chỉ sai hướng điều tra sang "giảm
phí". Đính chính tại chỗ, nêu rõ vì sao sai.

---

# SỬA 2 — thêm mục mới: đo trên bar NGÀY (`37035dd`)

Giả thuyết được kiểm: giao cắt SMA là công cụ bắt xu hướng, bar 5 phút phần lớn
là nhiễu. Dữ liệu: `bars_daily`, 1.551 mã, 2.969.328 dòng, 2016-01-03 → 2026-08-13.

Chép **cả hai bảng** (chưa lọc / đã lọc bar rác), vì việc lọc là lựa chọn có thể
bàn và người đọc phải tự so được:

```
Ky 10,5 nam. "DA LOC" = loai bar co OHLC <= 0.

                          lenh  win     gop truoc phi     phi+thue        rong
HII,IJC,AAA/5.021.459 chua   9  11,1%       -666.511        19.753    -686.265
                      loc   11  18,2%       -134.728        23.186    -157.914
HII,IJC,AAA/1 ty      chua   8  12,5%    -27.808.177     5.514.747 -33.322.924
                      loc    8  12,5%    khong doi
VCB,HPG,TCB/5.021.459 chua  26  46,2%        199.855        58.748     141.107
                      loc   26  46,2%    khong doi
VCB,HPG,TCB/1 ty      chua  52  30,8%     -3.059.961    27.395.721 -30.455.682
                      loc   52  30,8%    khong doi

Ky 2026-04-03 -> 2026-08-07 (cung ky ban 5m, 88 bar/ma, khong co bar rac):
  HII,IJC,AAA / 5.021.459   5 lenh 40,0%  rong    -58.330
  HII,IJC,AAA / 1 ty        5 lenh 40,0%  rong -16.138.631
  VCB,HPG,TCB / 5.021.459   0 lenh
  VCB,HPG,TCB / 1 ty        3 lenh  0,0%  rong  -9.909.374
```

## Phải ghi kèm — DỮ LIỆU BẨN

68 dòng có OHLC ≤ 0 trong `bars_daily` (IJC 62 · HII 3 · AAA 1 · VCB 1 · HPG 1 ·
TCB 0). Phần lớn là `open=high=low=0`, close thật, volume=0 — không phải `close=0`.

`PaperBroker` khớp lệnh tại `bar.open`, nên `open=0` nghĩa là lệnh khớp **giá 0**:

```
HII,IJC,AAA / 5.021.459 / 10,5 nam:
  2017-01-16 IJC SELL qty=200 price=0.0 pnl=-578.282,58
  -> chiem 84% khoan lo -686.265 cua dong do
```

## Phải ghi kèm — BỐN GIỚI HẠN CỦA PHÉP ĐO

Chép nguyên, đây là phần giữ cho tài liệu lương thiện:

1. **Mẫu quá nhỏ.** 0-5 lệnh trong 4,5 tháng; 8-52 lệnh trong 10,5 năm. Giao cắt
   SMA trên bar ngày rất hiếm. Đây là giới hạn của phép đo, không phải thứ chạy
   thêm là hết.
2. **MaxDD có phần tuỳ tiện.** Bar ngày làm mọi mã dùng chung một mốc thời gian,
   nên thứ tự các mã trong cùng ngày là tuỳ ý và MaxDD thừa hưởng điều đó. Đo
   thật trên VCB,HPG,TCB/1 tỷ: sắp theo `(ts)` → 9,15%; theo `(ts, symbol)` →
   9,24%. Số lệnh, win rate, PnL **không đổi**. Đừng trích MaxDD đến hai chữ số.
3. **`atr_pct_threshold = 0,001` đặt cho bar 5 phút.** Trên bar ngày ATR/giá lớn
   hơn hàng chục lần (HII 3,09% · IJC 2,28% · AAA 1,93% so với ~0,05-0,10% ở
   khung 5m) nên bộ lọc cho qua nhiều hơn. Không chỉnh — chỉ ghi nhận.
4. **Chưa xác nhận giá đã điều chỉnh chia tách/cổ tức.** Không tìm thấy bước
   nhảy qua đêm bất thường ngoài các bar rác trên, nhưng đó không phải bằng
   chứng đủ mạnh để khẳng định dữ liệu ĐÃ điều chỉnh.

## Một quan sát, ghi rõ là CHƯA KẾT LUẬN

`VCB,HPG,TCB / 5.021.459 / 10,5 năm` là cấu hình **duy nhất có lãi** (+141.107).
Cùng mã, cùng kỳ, chỉ đổi vốn lên 1 tỷ thì lỗ 30,4 triệu — vốn nhỏ lọc bớt lệnh
(26 thay vì 52) và những lệnh sống sót tốt hơn.

Ghi kèm ba con số làm người đọc tự thấy vì sao chưa thể mừng: 26 lệnh / 10,5 năm
≈ 2,5 lệnh mỗi năm; 141.107 trên vốn 5 triệu suốt 10,5 năm ≈ **0,25%/năm**; và
nó phụ thuộc vào việc bộ lọc kích thước lệnh vô tình chặn bớt tín hiệu.

**KHÔNG** viết khuyến nghị. Chỉ đặt số cạnh nhau.

---

# SỬA 3 — checklist "Thứ tự đề xuất" (dòng 513-539) đã lỗi thời

Hai danh sách ở mục này còn liệt kê việc **đã xong hoặc không còn tồn tại**:

- **"Chốt `real_order_capital`"** (xuất hiện ở CẢ HAI danh sách, đều là mục 1):
  `real_order_capital` **đã bị bỏ khỏi config** ở `63e6028`; engine đọc số dư
  thật từ `account_balance_snapshot`. Mục này không còn nghĩa.
- **"Quyết định cách sửa `save_account_positions`"**: đã xong ở `55df5dd`
  (bảng `account_sync_log` phân biệt "chưa đồng bộ" với "đã đồng bộ và rỗng").
- Mục "Nạp lịch sử SMA lúc khởi động" và "Sửa mất trailing stop sau restart":
  **tự kiểm** trạng thái thật rồi mới đánh dấu — đừng tin danh sách cũ.

Đính chính tại chỗ. Việc **còn thật sự tồn**:

1. Quyết định `real_order_account` — `0434221` (rỗng) hay `0434226` (có cổ phiếu
   thật, trong đó 1500 VCB)
2. Kiểm cron dead-man's switch trên VPS — chưa từng xác minh ở đó
3. **Câu hỏi biên lợi thế** — nay đã có thêm dữ liệu khung ngày, xem mục mới

---

# SỬA 4 — mục "`save_account_positions` — CHƯA SỬA" (dòng 359)

Đã sửa ở `55df5dd`. Đính chính tại chỗ, nêu cách sửa đã chọn (bảng
`account_sync_log`, và nhánh fallback giữ hành vi cũ khi chưa có mốc đồng bộ).

---

# SỬA 5 — thêm mục: hai lỗi kế toán PnL và các cảnh báo mới

Ngắn gọn, vì chúng là lý do bảng backtest đổi số:

- `6664cd9` — `realized_pnl` bỏ sót **phí MUA** (cổ phiếu). Đo trên DB sản xuất:
  cash giảm 328.798 nhưng sổ ghi −209.381; chênh 119.417 = tổng phí 5 lệnh mua
  ngày 14/08. Sai một chiều, luôn báo lỗ nhẹ hơn thực tế.
- `2982900` — cùng hạng lỗi ở lớp phái sinh (phí MỞ vị thế).
- `engine_state.realized_pnl` trong DB đã được sửa tay từ −209.381,13 thành
  −328.798,31 (2026-08-14), và engine đã rebuild để nạp lại.
- `7700992` + `d775ebb` — ba cảnh báo mới: dữ liệu ngừng chảy, token SSI sắp/đã
  hết hạn, và **hai sổ sách lệch nhau**. Cái cuối chính là thứ đã lẽ ra bắt được
  hai lỗi trên ngay ngày đầu: bất biến
  `cash + Σ(avg_price × qty) − CAPITAL == realized_pnl`.

---

# Ràng buộc

- **CHỈ** sửa `GO_LIVE_AUDIT.md`. Không đụng code, không đụng file khác.
- Không xoá nội dung cũ — đính chính tại chỗ.
- Giữ nguyên văn phong và ngôn ngữ hiện có của file.

# Kiểm chứng

- `git diff --stat` → **đúng 1 file**, và số dòng **xoá phải ~0** (chỉ thêm).
  Nếu có dòng bị xoá, giải thích từng dòng.
- `uv run pytest -q` → 304 passed (việc này không đụng code, số phải y nguyên).
- Đọc lại toàn bộ file một lượt và **tự trả lời**: còn câu nào trong tài liệu
  mâu thuẫn với số mới không? Báo cáo nếu có, đừng lặng lẽ bỏ qua.

# Nếu thấy kế hoạch sai

Dừng và phản biện. Đặc biệt: nếu bạn thấy tài liệu đã dài tới mức việc đính
chính tại chỗ làm nó **khó đọc hơn là hữu ích**, nói ra. Có lập luận rằng nên
viết một bản tóm tắt trạng thái ở đầu file thay vì chồng thêm khối đính chính
thứ tám. Tôi chọn giữ nguyên tắc cũ vì tính nhất quán, nhưng có thể tôi sai.
