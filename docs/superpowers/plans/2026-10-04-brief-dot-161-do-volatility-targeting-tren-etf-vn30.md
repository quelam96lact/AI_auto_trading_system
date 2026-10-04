# Brief đợt 161 — đo volatility targeting trên ETF VN30 mua-và-giữ (CHỈ ĐO, không đụng engine)

## Bối cảnh

Chủ dự án hỏi về video "I Re-Created A Quant Trading Strategy With Claude Code (Nobel Prize Method)"
(Miles Deutscher, 15/07/2026). Ý chính của video:

1. Chiều giá gần như không dự đoán được, nhưng **độ biến động thì có** (biến động dồn cụm thành từng đợt).
2. Dự báo độ biến động ngày mai `σ̂`, rồi đặt **cỡ vị thế = biến động mục tiêu ÷ σ̂**. Thị trường càng dữ thì cầm
   càng ít.
3. Tác giả tự báo kết quả: với BTC, drawdown giảm từ 81% còn 63% và lãi hơn một chút; với Nasdaq 50 năm, rủi ro giảm
   nhưng **mất khoảng 1 điểm % lãi kép mỗi năm**.

**Vì sao đo trên ETF mà không đo trên chiến lược đang chạy:** chiến lược hiện tại lỗ ngay cả trước phí (memory
"Strategy has no measured edge"). Chỉnh cỡ lệnh không biến kỳ vọng âm thành dương. Volatility targeting chỉ có
nghĩa khi phủ lên một tài sản vốn đã có lãi kỳ vọng dương, và trong mọi thứ dự án đã đo, chỉ có ETF `E1VFVN30`
mua-và-giữ đạt điều đó (đợt 102).

**Vì sao không trùng đợt 64:** đợt 64 bật/tắt toàn bộ theo độ rộng thị trường, lật trạng thái 10–20 lần mỗi năm, và
thua mua-và-giữ 10/11 năm. Đợt này **chỉnh tỷ trọng liên tục, có ngưỡng chống lật**, và dựa trên tính dai dẳng
của biến động. Đợt 76–77 đã đo `realized_vol_20d` như tín hiệu **chiều giá** (không có tín hiệu). Tính dai dẳng dùng
để **chia vốn** thì chưa ai đo.

**Không dùng skill/plugin `garch-method`.** Lệnh cài của chủ dự án không thành công, và kể cả nếu cài được thì đó
cũng là code bên thứ ba chưa ai kiểm. Mọi thứ đo trong repo, bằng code của đợt này. Con số trong video **không phải
mốc** để so: rất có thể tác giả ước lượng GARCH trên toàn bộ lịch sử rồi backtest lại trên chính lịch sử đó, và
video không nhắc gì đến phí.

## Dữ liệu (Claude đã đo ngày 04/10)

- `bars_daily`, mã `E1VFVN30`: 2016-01-03 → 2026-09-30, **2.683 phiên**, trong đó **3 phiên có `close <= 0`**.
  Phải **loại** các phiên đó: memory "Nến giá 0 ATO/ATC" nói `bars_daily` cố ý giữ 71 nghìn dòng giá 0.
- `E1VFVN30` **không** có trong `exclusions.txt`.
- Đọc giá bằng `read_symbol_bars` mà `scripts/screen_momentum_portfolio.py` đang dùng, **đừng viết SQL mới**.
  `bars_daily` lưu 00:00 giờ VN tức 17:00 UTC hôm trước; dùng `ts::date` thô thì lệch một ngày (memory "Chạy bù
  job theo ngày").
- Phí và thuế lấy từ `trading/paper_broker.py`: `FEE_RATE`, `SELL_TAX_RATE`, `SLIPPAGE_BPS`. **Import, không gõ
  lại số.** Memory "VN fee rate is 0.25%" ghi lại lần một con số gõ tay đã làm hỏng cả hai cổng kiểm.
- MDD và Sharpe lấy từ `trading/metrics.py` (`max_drawdown`, `sharpe`).

## Thiết kế phép đo — CHỐT TRƯỚC, không chỉnh sau khi thấy kết quả

| Mục | Chốt |
|---|---|
| Giai đoạn | Làm ấm 2016 (chỉ để ước lượng σ̂, không giao dịch). Đo **2017-01-02 → 2026-09-30**. |
| Đối chứng | Mua-và-giữ 100%: mua ở **open** phiên đo đầu tiên, bán ở **close** phiên cuối, tính đủ phí, thuế và trượt giá. |
| Dự báo σ̂ (**biến thể chính**) | EWMA trên lợi suất log theo ngày, λ = 0,94 (chuẩn RiskMetrics), annualize bằng √252. |
| Biến động mục tiêu | Trung vị của mọi σ̂ **tính tới hết phiên t** (cửa sổ mở rộng từ đầu làm ấm). Không có tham số để chỉnh. |
| Tỷ trọng mục tiêu | `w*_t = min(1, mục_tiêu_t / σ̂_t)`. **Trần 1**: không vay margin dù tài khoản 0434226 là margin. |
| Thời điểm | Quyết định ở close phiên t, khớp ở **open phiên t+1**. Không dùng dữ liệu nào sau close phiên t. |
| Ngưỡng tái cân bằng | Chỉ giao dịch khi `|w*_t − w_hiện_tại| ≥ 0,20`. |
| Chi phí | Mỗi lần mua: `FEE_RATE` + trượt giá. Mỗi lần bán: `FEE_RATE` + `SELL_TAX_RATE` + trượt giá. |
| Tiền mặt | Lãi 0 (bảo thủ, ghi rõ trong báo cáo). |
| Khối lượng | Được dùng tỷ trọng lẻ. Ghi một câu vì sao làm tròn lô 100 không đổi kết luận. |

### Tiêu chí ĐẠT (chỉ xét biến thể chính, cả giai đoạn, sau mọi chi phí)

- **(a)** MDD của biến thể chính ≤ **⅔** MDD của mua-và-giữ, **và**
- **(b)** CAGR của biến thể chính ≥ CAGR mua-và-giữ **− 1,0 điểm %**.

Thiếu một trong hai là **KHÔNG ĐẠT**. **Biến thể nhạy không được cứu một biến thể chính không đạt.** Đây là phép đo
thứ 14 của dự án; chọn biến thể đẹp nhất sau khi đã thấy kết quả chính là lỗi so sánh bội mà
`trading/metrics.holm_adjust` sinh ra để chặn.

### Biến thể nhạy (chỉ báo cáo, không quyết định)

1. σ̂ = độ lệch chuẩn trượt 20 phiên, thay cho EWMA.
2. Ngưỡng tái cân bằng 0,10 và 0,30.
3. **GARCH(1,1)**, chạy bằng `uv run --with arch ...`. **Không thêm `arch` vào `pyproject.toml`.** Phải ước lượng
   lại theo cửa sổ mở rộng **mỗi 21 phiên, chỉ dùng dữ liệu tới phiên t**. Ước lượng một lần trên toàn bộ lịch sử
   là nhìn trước tương lai, chính lỗi nghi ngờ ở video. Ghi tham số `ω, α, β` của lần ước lượng cuối, để đối chiếu
   với lời video rằng "trí nhớ ≈ 85%".

## Việc

Kiểm GitNexus trước: `gitnexus_query` để tìm hàm dùng lại được. Nếu buộc phải **sửa** một symbol có sẵn (không nên),
chạy `gitnexus_impact` và báo blast radius. Sau khi xong, chạy `gitnexus_detect_changes`.

1. `scripts/measure_vol_target_etf.py`: các hàm thuần (σ̂ EWMA, σ̂ trượt, tỷ trọng, mô phỏng có ngưỡng và chi phí,
   tách theo năm) cộng một `main` chỉ-đọc DB, in bảng ra stdout.
   → kiểm chứng bằng test ở mục 2.
2. `tests/test_measure_vol_target_etf.py`, dữ liệu tổng hợp, không chạm DB:
   - Chuỗi có biến động không đổi thì `w*` không đổi và không có giao dịch nào sau lần mua đầu.
   - **Chống nhìn trước:** đổi mọi giá **sau** phiên t thì `w*_t` và mọi giao dịch tới phiên t không đổi.
   - Ngưỡng: lệch 0,19 thì không giao dịch, lệch 0,21 thì có.
   - Chi phí: mua rồi bán một vòng ở giá phẳng thì mất **đúng** `2·FEE_RATE + SELL_TAX_RATE + 2·trượt giá`
     (sai số nhỏ hơn 1e-9).
   - EWMA ba bước khớp số tính tay ghi trong test.
   - Phiên `close <= 0` bị loại.
   - GARCH: `pytest.importorskip("arch")`, mô phỏng chuỗi GARCH(1,1) với tham số biết trước, thu hồi được `α+β`
     sai lệch không quá 0,05.
   → kiểm chứng bằng phá thử: cho `w*_t` dùng `σ̂_{t+1}` thì test chống nhìn trước phải đỏ. Ghi nguyên văn dòng đỏ,
   rồi khôi phục.
3. Chạy trên DB thật (chỉ đọc), dán vào báo cáo:
   - Bảng tổng: CAGR, MDD, năm tệ nhất, tháng tệ nhất, Sharpe, số giao dịch, tổng phí, tỷ trọng trung bình. Có cả
     mua-và-giữ, biến thể chính và mọi biến thể nhạy.
   - Bảng theo năm 2017 → 2026 (năm 2026 ghi rõ là năm dở dang): lợi suất của biến thể chính và của mua-và-giữ;
     đếm số năm thắng, thua, hoà.
   - **Mua-và-giữ riêng giai đoạn 2017–2022**, CAGR ròng. Claude sẽ tự đối chiếu với một phép đo cũ; agent không
     cần tìm con số đó.
   - Kết luận: **ĐẠT** hoặc **KHÔNG ĐẠT** theo (a) và (b), kèm phép tính.

## Giới hạn

- **CHỈ ĐO.** Không sửa `trading/`, engine, `risk.py`, `paper_broker.py`, `config/`, `sched.sh`. Không ghi DB. Không
  `docker`. Không Telegram. **Không chạy `scripts/sched.sh` dưới bất kỳ hình thức nào.**
- Không commit, không push.
- **Chỉ tạo:** script mới, test mới, báo cáo. Không sửa file có sẵn nào. Script mới được `tests/` import nên tự động
  thoả quy ước `scripts/` của đợt 159; **không** thêm dòng vào bảng `scripts/README.md`.
- Không thêm dependency vào `pyproject.toml`.
- Kết quả xấu thì báo đúng như nó xấu. **Không** đổi λ, ngưỡng hay biến động mục tiêu để chạy lại.
- Thấy vấn đề ngoài phạm vi thì ghi vào báo cáo, không tự sửa.
- Trước khi chạy bộ đầy đủ:
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'pytest' }`
  phải rỗng.

## Tiêu chí hoàn thành

1. Test mới xanh (bỏ qua test GARCH nếu `arch` vắng mặt thì phải ghi rõ). Có dòng đỏ nguyên văn của phá thử.
2. `uv run ruff check trading tests scripts` sạch. `uv run pytest -q`: số passed ≥ số đo **trước khi sửa** cộng số
   test mới, 0 failed. Dán **cả hai** con số.
3. Báo cáo có đủ ba bảng của Việc 3 và kết luận ĐẠT hoặc KHÔNG ĐẠT kèm phép tính (a) và (b).
4. `git status` chỉ có: script mới, test mới, báo cáo.

## Báo cáo

`docs/superpowers/research/2026-10-04-dot-161-volatility-targeting-etf-vn30.md`: thiết kế đã chốt (chép bảng ở
trên), ba bảng kết quả, kết luận, brief sai ở đâu, và những gì không kiểm được. Thứ chắc chắn không kiểm được: dữ
liệu chỉ có giá đóng/mở ngày nên không mô phỏng được khớp lệnh trong phiên, và ETF có thể lệch NAV.
