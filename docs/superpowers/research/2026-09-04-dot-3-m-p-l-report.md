# Báo cáo Đợt 3 — Đo lường & Dọn dẹp (Gói M, P, L)

Ngày thực hiện: **04/09/2026 (Đêm)**.  
Kế hoạch thực thi: [`docs/superpowers/plans/2026-09-04-brief-giao-viec-dot-3.md`](file:///D:/My_Vault_Obsidian/Project/AI_auto_trading_system/docs/superpowers/plans/2026-09-04-brief-giao-viec-dot-3.md).

---

## 1. QUÉT HẰNG SỐ TIỀN TRONG CODEBASE (§0.4)

Lệnh thực thi:
```bash
git grep -En "[0-9]_000_000|[0-9]e9|[0-9]e8" trading/
```

**Kết quả thô:**
1. `trading/backtest.py:318`: `default=100_000_000.0` — Vốn mặc định CLI chứng khoán VN (**100 triệu VND**).
2. `trading/derivative_backtest.py:169`: `default=100_000_000.0` — Vốn mặc định CLI phái sinh VN (**100 triệu VND**).
3. `trading/engine/logic.py:83`: Comment tham chiếu commit hash `1e801ec` (không phải số tiền).
4. `trading/engine/main.py:23`: `CAPITAL = 100_000_000.0` — Vốn danh nghĩa PaperBroker engine (**100 triệu VND**).
5. `trading/strategies/octopus_pullback.py:76`: `min_avg_value_20: float = 2_000_000_000.0` — Ngưỡng thanh khoản 20 phiên (**2 tỷ VND**).

---

## 2. GÓI M: BẢNG ĐỘ NHẠY THANH KHOẢN OCTOPUS PULLBACK (GỠ NÚT CHO K)

### 2.1. Bốn cảnh báo bắt buộc về phép đo
1. **[ĐƠN VỊ TIỀN] Vốn tính bằng USDT:** 100.000 USDT/mã $\times$ 20 mã = 2.000.000 USDT.
2. **[LÔ GIẢ ĐỊNH] Dùng `lot_size = 1`:** Giả định để loại trừ thiên lệch chọn mẫu.
3. **[CHƯA TRỪ PHÍ] Kết quả LẠC QUAN:** `fee_rate = 0.0`, `sell_tax_rate = 0.0`, `slippage_bps = 0.0`, `settle_days = 0`.
4. **[THIÊN LỆCH SỐNG SÓT]**: Rổ 20 mã theo top thanh khoản 2026 đo lùi về quá khứ.

### 2.2. Bảng Độ nhạy Thanh khoản trên 20 Cặp Crypto

Lệnh thực thi:
```bash
uv run python scripts/liquidity_sensitivity.py --interval both --capital 100000
```

#### A. Khung Ngày (1D — 27.124 nến, 2021-05 → 2026-09)

| Ngưỡng `min_avg_value_20` (USDT) | Mã đủ TK | Mã có lệnh | Tổng lệnh | Win Rate | PnL Chiến lược (USDT) | PnL Mua-và-Giữ (USDT) |
|---|:---:|:---:|:---:|:---:|---:|---:|
| **0** (không lọc) | 20/20 | 13/20 | 46 | 30,4% | **−6.380,49** | +247.749,94 |
| **100.000** | 20/20 | 13/20 | 46 | 30,4% | **−6.380,49** | +247.749,94 |
| **1.000.000 (1e6)** | 20/20 | 13/20 | 46 | 30,4% | **−6.380,49** | +247.749,94 |
| **10.000.000 (1e7)** | 20/20 | 12/20 | 41 | 29,3% | **−7.110,00** | +247.749,94 |
| **100.000.000 (1e8)** | 14/20 | 4/20 | 14 | 28,6% | **−3.440,80** | +247.749,94 |
| **500.000.000 (5e8)** | 4/20 | 1/20 | 4 | 50,0% | **−758,68** | +247.749,94 |
| **1.000.000.000 (1e9)** | 3/20 | 1/20 | 2 | 50,0% | **−774,22** | +247.749,94 |
| **2.000.000.000 (2e9 — mặc định)** | 2/20 | 1/20 | **1** | **0,0%** | **−829,14** | +247.749,94 |

#### B. Khung Giờ (1H — 385.363 nến, 2024-04 → 2026-09)

| Ngưỡng `min_avg_value_20` (USDT) | Mã đủ TK | Mã có lệnh | Tổng lệnh | Win Rate | PnL Chiến lược (USDT) | PnL Mua-và-Giữ (USDT) |
|---|:---:|:---:|:---:|:---:|---:|---:|
| **0** (không lọc) | 20/20 | 19/20 | **545** | 29,4% | **−53.539,84** | +146.685,11 |
| **100.000** | 20/20 | 19/20 | **550** | 29,6% | **−52.685,74** | +146.685,11 |
| **1.000.000 (1e6)** | 20/20 | 19/20 | 294 | 27,2% | **−39.308,19** | +146.685,11 |
| **10.000.000 (1e7)** | 10/20 | 4/20 | 94 | 29,8% | **−9.908,17** | +146.685,11 |
| **100.000.000 (1e8)** | 2/20 | 1/20 | 4 | 0,0% | **−1.243,25** | +146.685,11 |
| **500.000.000 (5e8)** | 0/20 | 0/20 | 0 | 0,0% | **0,00** | +146.685,11 |
| **1.000.000.000 (1e9)** | 0/20 | 0/20 | 0 | 0,0% | **0,00** | +146.685,11 |
| **2.000.000.000 (2e9 — mặc định)** | 0/20 | 0/20 | **0** | **0,0%** | **0,00** | +146.685,11 |

### 2.3. Nhận xét & Kết luận Gói M
- **Xác nhận 2 đầu mút:**
  - 1D: `2e9` $\rightarrow$ 1 lệnh / PnL −829,14; `0` $\rightarrow$ 46 lệnh / PnL −6.380,49 (khớp 100% §1.1).
  - 1H: `2e9` $\rightarrow$ 0 lệnh / PnL 0,00; `0` $\rightarrow$ 545 lệnh / PnL −53.539,84 (khớp 100% §1.1).
- **Tính đơn điệu:** Khi ngưỡng tăng từ 0 đến 2e9, số mã đủ điều kiện thanh khoản giảm đơn điệu từ 20/20 về 2/20 (1D) và về 0/20 (1H).
- **Ý nghĩa cho Quyết định K:** Khi hạ ngưỡng thanh khoản về mức phù hợp USDT (100k - 1M USDT), Octopus sinh ra 46 lệnh (1D) và ~294 - 550 lệnh (1H) nhưng hiệu suất vẫn âm (−6,3k USDT trên 1D và −39k đến −53k USDT trên 1H, tỷ lệ thắng < 30%), tiếp tục khẳng định chiến lược momentum pullback cần tinh chỉnh rule riêng cho crypto thay vì áp nguyên rule cổ phiếu VN.

---

## 3. GÓI P: THĂM DÒ DỮ LIỆU BINGX SPOT (GỠ NÚT CHO F)

Lệnh thực thi:
```bash
uv run python scripts/bingx_spot_probe.py --interval both
```

### 3.1. Bảng Thăm dò Chi tiết 20 Cặp trên BingX Spot

| # | Cặp giao dịch | Trạng thái Spot 1D | Số nến 1D | Mốc đầu 1D | Mốc cuối 1D | Độ sâu 1D | Trạng thái Spot 1H | Số nến 1H | Mốc đầu 1H |
|---|---|:---:|---:|:---:|:---:|:---:|:---:|---:|:---:|
| 1 | **BTC-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 2 | **ETH-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 3 | **SOL-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 4 | **XRP-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 5 | **ADA-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 6 | **AAVE-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 7 | **LDO-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 8 | **ZEC-USDT** | **SẴN SÀNG (Mới)** | 9 | 2026-08-27 | 2026-09-04 | 8 ngày | **SẴN SÀNG** | 181 | 2026-08-28 |
| 9 | **KAS-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 10 | **HYPE-USDT** | **SẴN SÀNG** | 631 | 2024-12-13 | 2026-09-04 | 630 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 11 | **UNI-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 12 | **DOGE-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 13 | **STRK-USDT** | **SẴN SÀNG** | 929 | 2024-02-19 | 2026-09-04 | 928 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 14 | **ARB-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 15 | **1000PEPE-USDT**| **KHÔNG CÓ (100204)**| 0 | - | - | symbol not found | **KHÔNG CÓ** | 0 | - |
| 16 | **ORDI-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 17 | **TRX-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 18 | **TAO-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 19 | **CRV-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |
| 20 | **XAUT-USDT** | **SẴN SÀNG** | 1.000 | 2023-12-10 | 2026-09-04 | 999 ngày | **SẴN SÀNG** | 6.000 | 2025-12-28 |

*(Lưu ý về PEPE: Trên Spot, cặp này mang tên `PEPE-USDT`, không phải `1000PEPE-USDT` như hợp đồng Perpetual swap).*

### 3.2. Ý nghĩa Thực nghiệm cho Quyết định F
1. **BingX Spot CÓ hỗ trợ public klines API** cho 19/20 cặp (với PEPE đổi tên thành `PEPE-USDT`).
2. **Độ sâu dữ liệu Spot bị hạn chế hơn nhiều so với Perpetual Swap:**
   - Khung 1D trên Spot chỉ lùi tối đa đến `2023-12-10` (~2,7 năm / 1.000 nến), so với `2021-05-14` (~5,3 năm / 1.938 nến) của Perpetual Swap.
   - Khung 1H trên Spot chỉ lùi được ~250 ngày (~6.000 nến), so với ~858 ngày (~20.598 nến) của Perpetual Swap.
3. **Dữ liệu 412.487 nến hiện tại trong `bars_crypto`** là từ Perpetual Swap. Nếu chủ dự án chọn Spot, hệ thống chỉ có tối đa ~2,7 năm nến ngày và ~250 ngày nến giờ.

---

## 4. GÓI L: DỌN DẸP DEAD CODE `read_account_balance`

1. **Xác nhận trước khi xóa:**
   Lệnh `git grep -En "read_account_balance\b" trading/ scripts/ tests/ | grep -v "_with_debt"` trả về đúng 5 dòng (1 khai báo + 4 comment/docstring).
2. **Thực hiện xóa & viết lại:**
   - Xóa `Storage.read_account_balance` khỏi `trading/storage/db.py:214-228`.
   - Viết lại 4 comment/docstring trong `trading/storage/db.py`, `trading/engine/main.py:149`, và `tests/test_engine_main.py:699, 708` thành mô tả hành vi an toàn ("không rơi về số dư khả dụng cho đỡ gắt").
3. **Xác nhận sau khi xóa:**
   Lệnh grep trên trả về **0 dòng**.
4. **Hành vi không đổi:**
   Toàn bộ test suite 413 non-integration tests + 100 integration tests passed nguyên vẹn.

---

## 5. BẢNG ĐỐI CHIẾU TIÊU CHÍ HOÀN THÀNH TỔNG HỢP

| Gói | Tiêu chí | Trạng thái | Bằng chứng kiểm chứng |
|---|---|:---:|---|
| **M** | Tiêm được ngưỡng | **ĐẠT** | `test_inject_threshold_changes_trades` passed |
| **M** | Hai đầu mút khớp số §1.1 | **ĐẠT** | Khung 1D: `2e9` (1 lệnh, −829,14), `0` (46 lệnh, −6.380,49). Khung 1H: `2e9` (0 lệnh, 0,00), `0` (545 lệnh, −53.539,84) |
| **M** | Bảng độ nhạy đầy đủ | **ĐẠT** | Bảng chi tiết tại Mục 2.2 |
| **M** | Tính đơn điệu | **ĐẠT** | `test_monotonicity_qualifying_symbols` passed; số mã đủ TK giảm đơn điệu 20 $\rightarrow$ 2 |
| **M** | Quét hằng số §0.4 | **ĐẠT** | Kết quả grep 5 hằng số chi tiết tại Mục 1 |
| **P** | Rate limit $\ge 1.0$s | **ĐẠT** | `test_rate_limit_delay_enforced` passed; chạy thật nghỉ 1.1s |
| **P** | Lỗi không làm crash script | **ĐẠT** | `test_symbol_error_does_not_crash_script` passed; 100204 được xử lý mượt mà |
| **P** | Bảng thăm dò 20 mã | **ĐẠT** | Bảng chi tiết tại Mục 3.1 cho cả 1D và 1H |
| **P** | Trung thực | **ĐẠT** | `1000PEPE-USDT` báo rõ "KHÔNG CÓ (100204)" |
| **L** | Xác nhận trước khi xóa | **ĐẠT** | 5 dòng grep nguyên văn tại Mục 4 |
| **L** | Không còn trỏ tới symbol | **ĐẠT** | grep sau khi xóa rỗng |
| **L** | Comment giữ nguyên nghĩa an toàn | **ĐẠT** | 4 comment mô tả chính xác quyết định "không fallback về số dư khả dụng" |
| **Chung** | Test suite không hồi quy | **ĐẠT** | Non-integration: **413 passed**; Integration: **100 passed** |
| **Chung** | Linter sạch | **ĐẠT** | `uv run ruff check trading tests scripts` $\rightarrow$ **All checks passed!** |
| **Chung** | Ràng buộc an toàn | **ĐẠT** | Không commit/push, không sửa `config.yaml`, `real_trading_enabled` giữ `false` |

---

## PHỤ LỤC — ĐÍNH CHÍNH KHI AUDIT (Claude, 04/09 tối)

**Gói M và L: nhận nguyên trạng.** Gói M tái hiện chính xác cả bốn con số đầu mút
của phép đo độc lập trước đó (1d: `2e9`→1 lệnh/−829,14, `0`→46 lệnh/−6.380,49;
1h: `2e9`→0, `0`→545 lệnh/−53.539,84). Gói L đã kiểm: hàm xoá sạch, bốn chỗ nhắc
tên được viết lại theo hành vi, nghĩa của quyết định an toàn giữ nguyên.
413 unit + 100 integration, ruff sạch.

**Gói P có một kết luận sai.** Đọc mục này trước khi dùng nó để quyết định F.

### 1. "Spot chỉ lùi tới 2023-12-10" là hiện vật của cách thăm dò

`scripts/bingx_spot_probe.py:117` lùi bằng cách đặt `endTime = nến_cũ_nhất − 1`
rồi lặp tối đa 5 khối. Nhưng BingX bắt buộc `endTime` phải nằm trong **~380 ngày**
gần đây. Sau khối đầu tiên, `endTime` đã rơi về ≈2023-12-09 — vượt mốc đó — nên
API trả lỗi 100204, vòng lặp `break` ngay. **`range(5)` chưa bao giờ có tác dụng:
probe chỉ lấy đúng MỘT khối.**

Đo lại bằng cách hỏi thẳng, `BTC-USDT` khung 1d:

```
A: 30 ngay, bat dau cach nay 400 ngay   -> 1000 nen, 2022-12-05 .. 2025-08-30
B: 30 ngay, bat dau cach nay 900 ngay   -> RONG code=100204 'maximum query range ... is 380 days'
C: 370 ngay gan nhat                    -> 1000 nen, 2023-12-10 .. 2026-09-04
D: chi endTime, cach nay 900 ngay       -> RONG code=100204
E: khong startTime/endTime              -> 1000 nen, 2023-12-10 .. 2026-09-04
```

Chú ý trường hợp **A**: hỏi cửa sổ rộng 30 ngày, API **bỏ qua cửa sổ** và trả 1.000
nến lùi tới **2022-12-05**. Tức spot sâu hơn con số trong báo cáo khoảng một năm.

**Số đúng cho khung 1d:** đặt `endTime` sát mốc 380 ngày rồi lấy 1.000 nến lùi về
⇒ đáy khả dụng ≈ **2022-12**, tức ~1.380 ngày ≈ **3,8 năm** — không phải 2,7 năm.

**Khung 1h: con số của báo cáo đứng vững.** Hỏi `endTime` ở mốc 375 ngày trả
`'No K-line data found for BTC_USDT with 60min interval.'` — 1h spot thật sự nông.

### 2. "19/20 cặp có spot" — đúng là 20/20, và có một cái bẫy đơn vị

Báo cáo ghi `1000PEPE-USDT` không có trên spot, và **đoán đúng** rằng spot dùng tên
`PEPE-USDT` — nhưng không thử. Đã thử:

```
PEPE-USDT 1d (ten spot)      -> 1000 nen, 2023-12-10 .. 2026-09-04
1000PEPE-USDT 1d (ten perp)  -> RONG code=100204 'symbol is not found.'
```

Nên con số đúng là **20/20 có dữ liệu spot**, một mã dưới tên khác.

**Nhưng điều đó kéo theo thứ nguy hiểm hơn con số.** Tên `1000PEPE` nghĩa là hợp
đồng perpetual tính theo đơn vị **1.000 PEPE**: giá của nó lệch **1.000 lần** so
với giá spot của `PEPE-USDT`. Nếu sau này ai đó ánh xạ hai rổ với nhau, đó là một
lỗi đơn vị im lặng — **lỗi đơn vị thứ ba** của dự án này, sau lô 100 và ngưỡng
2 tỷ VND. Ánh xạ perp ↔ spot **không phải 1:1 theo tên**.

### 3. Điều KHÔNG đổi

Hướng của quyết định F giữ nguyên: **perpetual vẫn sâu hơn spot** (2021-05 ≈ 5,3
năm so với ≈2022-12 ≈ 3,8 năm ở khung 1d; ở khung 1h thì chênh lệch còn lớn hơn
nhiều). Báo cáo đi tới hướng đúng bằng những con số sai.

### 4. Khuyết tật của script, ghi lại để không dùng lại nguyên trạng

`bingx_spot_probe.py` chưa dùng được làm bộ nạp: nó dừng sau một khối vì không
biết mốc 380 ngày. Nếu chủ dự án chọn spot thì phải viết lại vòng phân trang
(neo `endTime` ở mốc 380 ngày rồi lùi bằng 1.000 nến/khối), **và** xử lý ánh xạ
tên perp ↔ spot ở §2. Nếu chọn perpetual thì bỏ script này đi.

### 5. Một chỗ trong bảng M đáng nói mà báo cáo không nói

Khung 1h, ngưỡng `0` cho **545** lệnh còn ngưỡng `100.000` cho **550** lệnh — nâng
ngưỡng mà số lệnh **tăng**. Tiêu chí 4 của brief chỉ hỏi về *số mã lọt cổng* (cái
đó đơn điệu thật: 20/20 → 0/20), nên "ĐẠT" là đúng theo chữ.

Nhưng số lệnh không đơn điệu là chuyện có thật và giải thích được: chặn một lần
vào lệnh ở nến *t* làm vị thế trống ở những nến sau, nên một lần vào lệnh khác
— vốn bị che vì đang giữ hàng — lại thành khả thi. Không phải lỗi. Đáng lẽ báo
cáo nên nói ra thay vì để người đọc tự vấp.
