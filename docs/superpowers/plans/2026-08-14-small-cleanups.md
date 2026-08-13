# Kế hoạch: ba việc nhỏ — Grafana, CLAUDE.md, GO_LIVE_AUDIT

Ngày giao: 2026-08-14 sáng sớm. Nhánh: `feature/data-layer`. Base: `95b84d9`.

**KHÔNG commit, KHÔNG push.**

Ba việc **độc lập**, không việc nào đụng code sản xuất trong `trading/`.

---

## BỐI CẢNH VẬN HÀNH — đọc trước khi làm gì

Stack thật **đang chạy** và phiên giao dịch mở lúc **9:00**. Hôm nay là phiên
đầu tiên hệ thống có thể thực sự sinh lệnh (trước `95b84d9` sizing chặn tất cả
về mặt số học).

- **KHÔNG** restart/rebuild container nào.
- **KHÔNG** đụng `config/config.yaml`.
- Chạy `pytest` thì **an toàn** — suite đã tách sang DB `trading_test` + NATS
  4223 từ `51eb353`. Nhưng nhớ `docker compose --profile test up -d nats-test`
  nếu nó chưa chạy.

---

# VIỆC 1 — Grafana: panel giá không được hardcode mã nữa

`grafana/provisioning/dashboards/trading.json` panel id=1:

```
title:  "Gia (VCB)"
rawSql: SELECT ts AS time, close FROM bars WHERE symbol = 'VCB' ORDER BY ts
```

Rổ mã đã đổi sang `[HII, IJC, AAA]` (`63e6028`), nên panel này **đang đứng
hình** — nó vẽ dữ liệu VCB dừng ở 13/08 và sẽ không bao giờ nhúc nhích nữa.

## Cách sửa đã chốt: biến template, KHÔNG đổi sang mã cứng khác

Đổi `'VCB'` thành `'HII'` chỉ dời vấn đề sang lần đổi rổ mã tiếp theo. Dùng
biến để nó **tự đúng mãi**.

`templating` trong file hiện là `{}` — thêm mới, không sửa gì có sẵn:

- biến tên `symbol`, kiểu `query`, datasource PostgreSQL (dùng đúng datasource
  các panel khác đang dùng)
- query:
  `SELECT DISTINCT symbol FROM bars WHERE ts > now() - interval '7 days' ORDER BY 1`
- `multi: false`, `includeAll: false`, `refresh: 2` (on time range change)

Rồi panel 1:
- `title`: `"Gia ($symbol)"`
- `rawSql`: `... WHERE symbol = '$symbol' ...`

**Đánh đổi phải ghi vào comment/mô tả nếu chỗ đó cho phép:** cửa sổ 7 ngày sẽ
còn lẫn VCB/HPG/TCB thêm khoảng một tuần nữa rồi tự rụng. Chọn 7 ngày thay vì
2 ngày vì sáng thứ Hai cửa sổ 2 ngày sẽ **rỗng** (cuối tuần không có bar) và
biến sẽ không có giá trị nào.

## Ràng buộc việc 1

- Chỉ sửa `grafana/provisioning/dashboards/trading.json`, chỉ panel id=1 và
  khối `templating`.
- **KHÔNG** đụng 6 panel còn lại.
- Giữ JSON hợp lệ — chạy `python -c "import json;json.load(open(...))"` để chắc.

## Kiểm chứng việc 1

1. JSON parse được (dán output).
2. `grep` chứng minh không còn chuỗi `'VCB'` nào trong panel 1.
3. Nếu Grafana đang chạy (cổng 3000): nạp lại và xác nhận dropdown `symbol` có
   HII/IJC/AAA. Nếu Grafana không chạy thì **nói rõ là chưa kiểm được trực
   quan** — đừng tuyên bố nó hoạt động khi chưa nhìn thấy.

---

# VIỆC 2 — CLAUDE.md: lệnh test đang thiếu, tức là đang SAI

`CLAUDE.md` mục "Build, lint, test commands" liệt kê:

```
uv run pytest -m "not integration" -v
uv run pytest tests/test_parser.py -v
uv run ruff check trading tests
```

Sau `51eb353` (tách hạ tầng test), chạy **suite đầy đủ** cần thêm một bước, và
tài liệu không nói. `README.md` đã được cập nhật ở `f1a410f`; `CLAUDE.md` thì
chưa — hai tài liệu đang mâu thuẫn nhau.

## Phải làm

Thêm vào đúng khối bash đó, sau dòng unit test:

```bash
# Suite day du (gom integration) — can Postgres + NATS RIENG cho test
docker compose --profile test up -d nats-test
uv run pytest -q
```

Kèm một câu ngắn nói vì sao có `nats-test`: test chạy trên DB `trading_test` +
NATS 4223 để không bao giờ đụng hệ thống thật.

## Ràng buộc việc 2

- **CHỈ** thêm vào khối lệnh đó. **KHÔNG** sửa bất kỳ phần nào khác của
  `CLAUDE.md` — đặc biệt không đụng mục "Nguyên tắc lập kế hoạch" hay khối
  `<!-- gitnexus:start -->` (khối đó do công cụ tự sinh).
- Giữ nguyên văn phong và ngôn ngữ hiện có của từng mục.

---

# VIỆC 3 — GO_LIVE_AUDIT.md: cập nhật ba commit + phát hiện chiến lược lỗ

Tài liệu dừng ở `edaf026`. Ba commit sau đó chưa được phản ánh, và **một trong
số đó lật ngược kết luận chính của cả bản audit**.

## QUY TẮC TUYỆT ĐỐI CHO VIỆC NÀY

Chỉ chép **số đã đo**. **KHÔNG** thêm nhận định, dự đoán, khuyến nghị đầu tư,
hay lời an ủi kiểu "cần tối ưu thêm". Nếu bạn thấy mình đang viết một câu mà
không chỉ được nó lấy số từ đâu — xoá câu đó.

Tài liệu này tồn tại vì bản `DEPLOYMENT_READINESS.md` cũ đã khẳng định sai và
suýt làm người đọc tin hệ thống sẵn sàng hơn thực tế. Đừng lặp lại.

## Nội dung phải thêm

### a) Bảng trạng thái ở đầu — thêm 2 dòng

- `real_order_capital` → **bỏ khỏi config**, engine đọc số dư thật (`63e6028`)
- Rổ mã → `[HII, IJC, AAA]` (`63e6028`)

### b) Mục mới: "Luồng paper không thể mua — phát hiện 13/08 khuya" (`95b84d9`)

Chép nguyên các số này:

```
approve_sized ap hai luat chong nhau:
  qty        = capital * risk_pct / (atr * atr_multiplier)      # 0,01 va 2,0
  rang buoc:   ref_price * qty <= capital * max_order_value_pct # 0,20
Thay qty vao, CAPITAL TRIET TIEU ca hai ve:
  ref_price / atr <= 40   <=>   atr / ref_price >= 2,5%

ATR/gia CAO NHAT tung dat tren bar 5 phut:
  HII 2,003%  |  IJC 1,350%  |  AAA 0,937%   -> KHONG bar nao dat 2,5%
```

Nêu rõ: điều này giải thích vì sao `orders` chỉ có 1 dòng từ 15/07 và engine
chạy trọn phiên 13/08 sinh 0 lệnh. Crossover **có** xảy ra (9-56 lần mỗi mã qua
được bộ lọc ATR) rồi bị vứt **im lặng** ở khâu sizing.

Nêu rõ đường lệnh **thật** không dính (dùng `approve()` với `qty=100` cố định).

Đã sửa bằng `qty = min(qty_atr, qty_cap)`, kèm đánh đổi: khi vướng trần, rủi ro
mỗi lệnh nhỏ hơn `risk_pct` — không còn là hằng số, nhưng chỉ nhỏ đi.

### c) Mục mới: "Backtest sau khi gỡ bế tắc"

Chép nguyên bảng, **không bình luận thêm**:

```
sma_cross, 5m, 2026-04-03 -> 2026-08-07, khong chinh mot tham so nao:

  HII,IJC,AAA / 5.021.459    24 lenh  win  8,3%  PnL   -153.067   MaxDD 3,8%
  HII,IJC,AAA / 1 ty         16 lenh  win  6,2%  PnL -32.571.418  MaxDD 4,1%
  VCB,HPG,TCB / 5.021.459     0 lenh  (1 lo VCB ~6tr > tran 1,004tr — dung so hoc)
  VCB,HPG,TCB / 1 ty         17 lenh  win 52,9%  PnL  -6.094.804  MaxDD 1,9%
```

Rồi đúng một câu kết luận: **cả bốn cấu hình đều lỗ.**

Thêm hai quan sát, ghi rõ là **chưa kết luận**:
- lỗ trung bình mỗi lệnh RUN 1 = -6.378 trên lệnh ~860.000 = -0,74%; phí vòng
  khứ hồi VN ~0,3-0,4% cộng slippage chiếm phần lớn con số đó
- RUN 2 có ít giao dịch hơn RUN 1 (16 vs 24) dù vốn gấp 200 lần

### d) Sửa mục "Thứ tự đề xuất"

Câu chốt hiện tại nói chỉ cần xong (1)(2)(5) là có thể bàn tới bật
`real_trading_enabled`. **Không còn đúng.** Thay bằng: câu hỏi chặn đường bây
giờ không phải "khi nào bật tiền thật" mà là "chiến lược này có biên lợi thế
không" — vì nó đã được đo là lỗ trên 4 tháng dữ liệu gần nhất.

## Ràng buộc việc 3

- Chỉ sửa `GO_LIVE_AUDIT.md`.
- **KHÔNG xoá** phần cũ. Giữ nguyên tắc đã dùng ở `edaf026`: đính chính tại chỗ
  bằng khối `> ĐÍNH CHÍNH` / mục mới, không viết lại lịch sử.

---

# Toàn bộ

- `uv run pytest -q` → 273 passed (không việc nào đụng code, số phải y nguyên).
- `uv run ruff check trading tests` → sạch.
- JSON Grafana parse được.

# Nếu thấy kế hoạch sai

Dừng và phản biện. Đặc biệt việc 1: nếu biến template Grafana không làm được
với datasource/phiên bản hiện tại, **nói ra** thay vì âm thầm quay về hardcode
một mã khác.
