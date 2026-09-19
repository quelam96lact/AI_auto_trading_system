# Brief đợt 61 — Buy-and-hold có nhịp: nắm giữ khi thị trường khoẻ, về tiền mặt khi xấu

Ngày giao: 19/09/2026 (thứ Bảy, tối).
Base: `dc9dd73` (main).
Người giao: Claude (planner/auditor).
Người thực thi: **Gemini Flash 3.8**.

Yêu cầu chủ dự án: "chiến lược buy and hold theo nhịp thị trường". Đây là ý **khác** với
đợt 9 (đã đo, đã bác). Brief này nói rõ khác nhau ở đâu, và đóng băng đúng một cách hiểu trước
khi giao — không để agent tự diễn giải.

---

## 0. Đọc trước khi làm gì — hai tiền lệ đã có, đừng lặp lại hoặc bỏ qua

### 0.1. Đợt 9/10 đã đo một ý gần giống, và nó thua đậm

`docs/superpowers/research/2026-09-02-market-regime-strategy-report.md`: chuyển **giữa các
chiến lược chủ động** (`daily_breakout`, `octopus_pullback`, `sma_cross`) theo chế độ thị trường.
Kết quả ngoài mẫu (2023→2026-08): **−8,82 tỷ**, so với mua-và-giữ cùng kỳ **+657,97 tỷ**. Kết
luận đã đóng: không triển khai, không thử ngưỡng khác để cứu vớt.

**Ý lần này khác ở một điểm cốt lõi:** không chuyển sang chiến lược chủ động nào cả. Chỉ có
**hai trạng thái** — đang **NẮM GIỮ** (mua-và-giữ cả rổ, không giao dịch chủ động) hoặc đang
**TIỀN MẶT** (đã bán hết, không giữ gì). Đây là bộ lọc xu hướng lên toàn bộ mua-và-giữ, không
phải một chiến lược tìm điểm vào/ra.

### 0.2. Hạ tầng chế độ thị trường đã có, đã test, đừng viết lại

`scripts/market_regime.py` (breadth, phân loại RISK_ON/NEUTRAL/RISK_OFF/UNKNOWN, chống
look-ahead) và `docs/superpowers/research/2026-09-02-breadth-daily.csv` (2.662 phiên,
2016-01-04 → 2026-08-28) **đã tồn tại, đã qua kiểm chứng phá hoại hai lần** (đợt 9 và đợt 10).
**Dùng lại nguyên xi** hàm `load_breadth_regimes` trong `scripts/measure_market_regime.py` và
định nghĩa ngưỡng 0,60/0,40 — **không tính lại breadth, không đổi ngưỡng**.

### 0.3. Tôi đã đo trước tần suất đổi trạng thái — đủ rẻ để đáng thử

Với quy tắc "RISK_OFF → tiền mặt, còn lại → nắm giữ" áp lên toàn chuỗi:

```
Tong so phien: 2662
So lan doi HOLD/CASH: 43 (ca chuoi)
  Trong mau (2016-2022): 23 lan doi / 1752 phien | giu 83,4% thoi gian
  Ngoai mau (2023-2026): 20 lan doi / 910 phien  | giu 78,1% thoi gian
```

**43 lần đổi trạng thái trong 10,6 năm** — khác hẳn đợt 9 (`daily_breakout` sinh 4.140–6.936
lệnh riêng ở mỗi chế độ). Đây là lý do ý này đáng đo: chi phí giao dịch không tự nhiên giết chết
nó như đợt 9.

---

## 1. Ràng buộc — giống hệt đợt 9, lý do giống hệt đợt 9

- **Không sửa bất kỳ file nào trong `trading/`.** Chỉ đọc (import). File mới nằm trong
  `scripts/` và `tests/`.
- **Không sửa `config/config.yaml`.**
- **Không commit, không push.** Claude audit rồi mới commit.
- `real_trading_enabled` giữ `false`. Không gọi API đặt/huỷ lệnh SSI.
- **Không `TRUNCATE`, không `DROP`, không xoá dòng.** Chỉ đọc `bars_daily`. Ghi kết quả ra file
  trong `docs/`, không ghi DB.
- Không in secret. `.env` không sửa.
- Phát hiện ngoài phạm vi thì **báo cáo, không tự sửa**.

---

## 2. Task 1 — Định nghĩa chính xác quy tắc, đóng băng TRƯỚC khi viết code đo

**Đây không phải chi tiết kỹ thuật — đây là điều quyết định kết quả có đáng tin hay không.**
Ghi nguyên văn quy tắc dưới đây vào đầu báo cáo, **trước** khi chạy bất cứ số nào.

### 2.1. Trạng thái và tín hiệu

Mỗi ngày `d`, danh mục ở đúng một trong hai trạng thái:

| Trạng thái | Điều kiện (dùng `regime(d-1)`, đúng quy ước chống nhìn trộm của đợt 9) |
|---|---|
| **NẮM GIỮ** | `regime(d-1) ∈ {RISK_ON, NEUTRAL, UNKNOWN}` |
| **TIỀN MẶT** | `regime(d-1) == RISK_OFF` |

`UNKNOWN` chỉ xảy ra trong 199 phiên đầu 2016 (đợt 10 đã xác nhận, không ảnh hưởng kỳ ngoài mẫu)
— xếp vào NẮM GIỮ vì đó là trạng thái mặc định khi chưa có tín hiệu, không phải một lựa chọn có
chủ đích cần tinh chỉnh.

**Đây là MỘT quy tắc duy nhất, đóng băng trước khi chạy.** Không thử `RISK_ON` một mình so với
`RISK_ON + NEUTRAL`, không thử ngưỡng khác. Nếu bạn thấy mình muốn thử biến thể thứ hai: được,
nhưng phải khai báo **cả hai** trong báo cáo kèm số lần đã thử — đúng luật đợt 9.

### 2.2. Cơ chế giao dịch khi trạng thái đổi

- Ngày `d`, nếu trạng thái đổi từ TIỀN MẶT → NẮM GIỮ: **mua** toàn bộ rổ tại `Open(d)`, vốn chia
  đều cho từng mã, đúng công thức `_buy_and_hold` trong `trading/backtest.py` (giá mua gồm
  trượt giá `+slip`, phí mua gộp vào giá vốn).
- Ngày `d`, nếu trạng thái đổi từ NẮM GIỮ → TIỀN MẶT: **bán** toàn bộ rổ tại `Open(d)`, trừ
  trượt giá và phí bán + thuế bán — đúng công thức `_buy_and_hold`, chỉ khác giá tham chiếu là
  `Open(d)` thay vì bar cuối kỳ.
- Ngày không đổi trạng thái: không giao dịch. Khi đang NẮM GIỮ, giá trị danh mục biến động theo
  giá đóng cửa (mark-to-market), không phải chuyện cần tính PnL thực hiện.
- **Dùng đúng ba hằng số phí đã có** (không tự đặt số mới): `FEE_RATE`, `SELL_TAX_RATE`,
  `SLIPPAGE_BPS` — tìm trong `trading/paper_broker.py`, dùng lại, đừng khai báo lại.
- Rổ mã: **giống hệt** rổ dùng cho mốc mua-và-giữ ở đợt 9 (1.308 mã sau khi loại theo
  `exclusions.txt`). Dùng lại logic lọc đã có trong `measure_market_regime.py`/
  `measure_strategy.py`, đừng viết lại bộ lọc.

### 2.3. Vì sao đây KHÔNG phải chi tiết vặt

Nếu bạn tự chọn "bán ở `Close(d-1)` thay vì `Open(d)`", hay "chia lại vốn theo tỷ trọng mới mỗi
lần vào lại" thay vì giữ nguyên số lượng cổ phiếu tính từ lần mua gần nhất, kết quả sẽ lệch mà
không ai biết lệch bao nhiêu. Làm đúng như mục 2.2, không tự tối ưu hoá.

---

## 3. Task 2 — Đo trong mẫu, rồi ngoài mẫu, đúng ranh giới đợt 9

**Kỳ trong mẫu: 2016-01-04 → 2022-12-31.**
**Kỳ ngoài mẫu: 2023-01-01 → 2026-08-28.** (Giữ nguyên ranh giới đợt 9 để so sánh trực tiếp
được với các con số đã có — **không** kéo dài tới hôm nay trong lần đo chính.)

Với **mỗi** kỳ, tính và báo cáo:

1. **PnL cuối kỳ** của danh mục NẮM GIỮ/TIỀN MẶT theo quy tắc đã đóng băng.
2. **Số lần đổi trạng thái** (mua toàn bộ + bán toàn bộ tính riêng).
3. **Max drawdown** của đường vốn (đỉnh-tới-đáy tệ nhất, tính trên giá trị danh mục theo ngày,
   không phải chỉ điểm đầu/cuối). **Đây là số quan trọng nhất của brief này** — lý do làm bộ lọc
   này là để giảm sụt giảm sâu, không chỉ để tăng lãi. Không có số này thì không trả lời được câu
   hỏi thật.
4. **So với mua-và-giữ thuần** cùng kỳ, cùng rổ, cùng vốn — **tự tính lại**, đừng chép số cũ từ
   báo cáo đợt 9 dù chúng có sẵn (+1.007,12 tỷ trong mẫu, +657,97 tỷ ngoài mẫu). Nếu số bạn tính
   ra khác số cũ, dừng lại và báo cáo — đó là dấu hiệu lệch dữ liệu hoặc lỗi, không phải chuyện
   nhỏ.
5. **Max drawdown của chính mua-và-giữ thuần** cùng kỳ, để so sánh trực tiếp mục 3.

**Không cần chạy Task 2 trước rồi mới đóng băng quy tắc như đợt 9** — quy tắc ở đây đã đóng băng
sẵn từ mục 2.1 (chỉ có một quy tắc, không có bảng 3×3 để chọn từ đó). Chạy thẳng trong mẫu rồi
ngoài mẫu, dán cả hai.

---

## 4. Task 3 — Test

File mới `tests/test_regime_hold.py`. Tất định, không chạm DB.

Bắt buộc bốn test:

1. `test_khong_doi_khi_regime_khong_doi` — chuỗi regime toàn `RISK_ON`: không có giao dịch nào
   ngoài lần mua đầu tiên.
2. `test_mua_ban_dung_gia_va_phi` — dựng tay 1 mã, 1 lần đổi trạng thái, kiểm giá mua/bán và phí
   khớp chính xác công thức `_buy_and_hold` (không chỉ khớp gần đúng).
3. `test_khong_nhin_trom_tuong_lai` — thêm regime của ngày `d+1` không được làm đổi quyết định
   giao dịch của ngày `d`. Tái dùng đúng kiểu kiểm chứng của `test_market_regime.py`.
4. `test_max_drawdown_dung` — dựng tay một đường vốn có hình dạng biết trước (ví dụ
   100→150→80→120), kiểm max drawdown tính ra đúng −46,67%.

### Kiểm chứng phá hoại (bắt buộc, theo lệ dự án)

Với test 2 và test 3: cố tình phá code cho đỏ, **dán nguyên văn output đỏ**, rồi khôi phục.

---

## 5. Báo cáo cho Claude

1. Quy tắc đóng băng (mục 2.1–2.2), dán **trước** mọi con số.
2. Bảng trong mẫu: PnL, số lần đổi trạng thái, max drawdown — cả cho quy tắc HOLD/CASH và cho
   mua-và-giữ thuần.
3. Bảng ngoài mẫu: y hệt cấu trúc mục 2, kèm đối chiếu với số cũ của đợt 9 (+657,97 tỷ) — khớp
   hay lệch, nếu lệch thì vì sao.
4. Bốn test + hai lượt phá hoại, dán nguyên văn output đỏ.
5. `uv run pytest -m "not integration" -q` — không có test nào đỏ **thêm** ngoài
   `test_backtest_cli.py::test_cli_registry_no_longer_offers_sma_cross` (đã biết, không phải lỗi
   của bạn — xem đợt 9 mục 8).
6. `uv run ruff check trading tests scripts` sạch.
7. Mọi con số kèm **lệnh chính xác để chạy lại**.

**Không commit, không push.**

---

## 6. Việc KHÔNG làm

- **Không đụng `trading/`.**
- **Không sửa engine.** Đây là giai đoạn ĐO — dựng vào engine chỉ xảy ra nếu số liệu sống sót,
  và đó là quyết định của chủ dự án sau khi đọc báo cáo, không phải mặc định.
- **Không thử áp quy tắc lên rổ mã hẹp hơn** (ví dụ nhóm cổ phiếu ổn định VPI/STB/FPT đã tìm
  trước đó) — đó là một câu hỏi khác, để brief sau nếu kết quả lần này đáng theo tiếp.
- **Không dò ngưỡng breadth khác 0,40/0,60.**
- **Không kéo dài kỳ ngoài mẫu** tới ngày hôm nay trong phép đo chính — giữ nguyên ranh giới đợt
  9 để so sánh được. Nếu muốn, có thể thêm **một mục phụ, ghi rõ là phụ**, đo từ 2026-08-29 tới
  hôm nay bằng dữ liệu mới hơn — nhưng không trộn vào bảng so sánh chính.
- **Không sửa `scripts/market_regime.py` hay `scripts/measure_market_regime.py`** — chỉ `import`
  từ chúng.

---

## 7. Nếu kết quả tốt hơn mua-và-giữ thuần — vẫn chưa xong

Một kết quả PnL nhỉnh hơn hoặc max drawdown thấp hơn mua-và-giữ thuần **trong mẫu** không đủ để
kết luận gì — đợt 9 cho thấy chính xác cái bẫy này (bảng 3×3 đẹp trong mẫu, sụp hoàn toàn ngoài
mẫu). Con số ngoài mẫu là con số duy nhất có ý nghĩa quyết định. Nếu cả hai kỳ đều tốt hơn mua-và-
giữ thuần, đó vẫn chỉ là **một** phép đo đáng để chủ dự án cân nhắc bước tiếp theo, không phải
lý do để tự ý dựng vào engine.
